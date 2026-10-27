from __future__ import annotations

import time
from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel

from .. import db, directions as dirs, secrets_store, settings_store
from ..ai import prompts
from ..ai.client import DEFAULT_MODELS, AIError, DeepSeekClient, get_client, is_configured
from ..errors import AppError
from ..sources import REGISTRY

router = APIRouter(tags=["settings"])


# ---------------- general settings ----------------

@router.get("/settings")
def get_settings():
    return settings_store.get_settings()


@router.patch("/settings")
def patch_settings(patch: dict[str, Any]):
    patch.pop("ai_key", None)  # keys never travel through the settings document
    return settings_store.update_settings(patch)


@router.get("/meta")
def meta():
    return {
        "direction_presets": dirs.PRESETS,
        "arxiv_categories": dirs.ARXIV_CATEGORIES,
        "ranking_presets": settings_store.RANKING_PRESETS,
        "time_preferences": settings_store.TIME_PREFERENCE_HALF_LIFE,
        "default_models": DEFAULT_MODELS,
    }


# ---------------- research directions ----------------

class DirectionIn(BaseModel):
    name: str
    keywords: list[str] = []
    exclude: list[str] = []
    categories: list[str] = []
    weight: int = 3
    enabled: bool = True


@router.get("/directions")
def list_directions():
    return dirs.list_directions()


@router.post("/directions")
def create_direction(body: DirectionIn):
    try:
        return dirs.create_direction(body.model_dump())
    except ValueError as e:
        raise AppError(str(e))


class PresetsIn(BaseModel):
    keys: list[str]


@router.post("/directions/presets")
def add_presets(body: PresetsIn):
    existing = {d["name"] for d in dirs.list_directions()}
    created = []
    for p in dirs.PRESETS:
        if p["key"] in body.keys and p["name"] not in existing:
            created.append(dirs.create_direction({"name": p["name"], "keywords": p["keywords"],
                                                  "categories": p["categories"], "weight": 3}))
    if created:
        settings_store.update_settings({"onboarded": True})
    return created


@router.patch("/directions/{direction_id}")
def update_direction(direction_id: int, body: dict[str, Any]):
    try:
        return dirs.update_direction(direction_id, body)
    except KeyError:
        raise AppError("研究方向不存在", status_code=404)
    except ValueError as e:
        raise AppError(str(e))


@router.delete("/directions/{direction_id}")
def delete_direction(direction_id: int):
    dirs.delete_direction(direction_id)
    return {"ok": True}


class SuggestIn(BaseModel):
    name: str
    description: str = ""


@router.post("/directions/suggest")
def suggest_keywords(body: SuggestIn):
    """Explicit, user-triggered AI call: suggest keywords/categories for a direction."""
    if not body.name.strip():
        raise AppError("请先填写研究方向名称")
    client = get_client()
    try:
        data, _ = client.chat_json(
            [{"role": "system", "content": prompts.SUGGEST_SYSTEM},
             {"role": "user", "content": prompts.suggest_task(body.name.strip(), body.description.strip(), dirs.ARXIV_CATEGORIES)}],
            thinking=False, max_tokens=2000, temperature=0.3, kind="suggest_keywords")
    finally:
        client.close()
    valid_cats = {c["id"] for c in dirs.ARXIV_CATEGORIES}
    kws = [str(k).strip() for k in data.get("keywords", []) if str(k).strip()][:15]
    return {
        "keywords": kws,
        "exclude": [str(k).strip() for k in data.get("exclude", []) if str(k).strip()][:10],
        "categories": [c for c in data.get("categories", []) if c in valid_cats][:4],
    }


# ---------------- sources ----------------

def _last_source_stats() -> dict[str, Any]:
    r = db.query_one("SELECT stats, created_at FROM rec_batches ORDER BY id DESC LIMIT 1")
    if not r:
        return {}
    stats = db.loads(r["stats"], {}).get("sources", {})
    return {k: {**v, "at": r["created_at"]} for k, v in stats.items()}


@router.get("/sources")
def list_sources():
    settings = settings_store.get_settings()
    last = _last_source_stats()
    out = []
    for sid, src in REGISTRY.items():
        info = src.info()
        key = secrets_store.get_secret(src.key_secret) if src.key_secret else None
        info.update(enabled=bool(settings["sources"].get(sid)), key_configured=bool(key),
                    key_masked=secrets_store.mask(key), last=last.get(sid))
        out.append(info)
    hf = settings["signals"].get("hf_daily", True)
    return {"sources": out, "signals": [{
        "id": "hf_daily", "name": "Hugging Face 社区热度", "enabled": hf,
        "description": "用 Hugging Face Daily Papers 的点赞数作为 arXiv 论文的社区关注度信号（仅影响排序，不作为论文来源）。",
    }]}


class SourcePatch(BaseModel):
    enabled: bool | None = None
    api_key: str | None = None
    remove_key: bool = False


@router.patch("/sources/{source_id}")
def patch_source(source_id: str, body: SourcePatch):
    if source_id == "hf_daily":
        if body.enabled is not None:
            settings_store.update_settings({"signals": {"hf_daily": body.enabled}})
        return list_sources()
    src = REGISTRY.get(source_id)
    if not src:
        raise AppError("未知的论文来源", status_code=404)
    if body.enabled is not None:
        settings_store.update_settings({"sources": {source_id: body.enabled}})
    if src.key_secret:
        if body.remove_key:
            secrets_store.delete_secret(src.key_secret)
        elif body.api_key and body.api_key.strip():
            secrets_store.set_secret(src.key_secret, body.api_key.strip())
    return list_sources()


# ---------------- AI (DeepSeek) configuration ----------------

def _ai_config() -> dict[str, Any]:
    s = settings_store.get_settings()["ai"]
    key = secrets_store.get_secret(secrets_store.DEEPSEEK)
    models = db.cache_get("deepseek_models") or []
    return {
        "configured": bool(key),
        "key_masked": secrets_store.mask(key),
        "base_url": s["base_url"],
        "model": s["model"],
        "models": sorted(set(models) | set(DEFAULT_MODELS) | {s["model"]}),
        "thinking_for_analysis": s["thinking_for_analysis"],
        "secret_backend": secrets_store.backend_name(),
        "last_test": db.cache_get("deepseek_last_test"),
    }


@router.get("/ai/config")
def ai_config():
    return _ai_config()


class KeyIn(BaseModel):
    api_key: str


@router.put("/ai/key")
def set_key(body: KeyIn):
    key = body.api_key.strip()
    if len(key) < 10 or " " in key:
        raise AppError("API Key 格式不正确，请从 DeepSeek 开放平台复制完整的 Key（通常以 sk- 开头）。")
    secrets_store.set_secret(secrets_store.DEEPSEEK, key)
    db.cache_set("deepseek_last_test", None)
    return _ai_config()


@router.delete("/ai/key")
def delete_key():
    secrets_store.delete_secret(secrets_store.DEEPSEEK)
    db.cache_set("deepseek_last_test", None)
    return _ai_config()


class TestIn(BaseModel):
    api_key: str | None = None  # test a key before saving it
    chat: bool = True


@router.post("/ai/test")
def test_ai(body: TestIn):
    """Explicit connection test: auth + balance + a tiny chat completion with the chosen model."""
    s = settings_store.get_settings()["ai"]
    key = (body.api_key or "").strip() or secrets_store.get_secret(secrets_store.DEEPSEEK)
    if not key:
        raise AppError("请先填写 API Key", code="not_configured")
    client = DeepSeekClient(key, s["base_url"], s["model"], timeout=60)
    result: dict[str, Any] = {"ok": False, "steps": [], "at": db.now_iso()}
    try:
        t0 = time.monotonic()
        try:
            models = client.list_models()
            db.cache_set("deepseek_models", models)
            result["models"] = models
            result["steps"].append({"name": "身份验证", "ok": True, "detail": f"可用模型：{', '.join(models) or '未返回'}"})
        except AIError as e:
            result["steps"].append({"name": "身份验证", "ok": False, "detail": e.message})
            result["error"] = e.message
            result["error_code"] = e.code
            return _finish_test(result, body)
        try:
            bal = client.balance()
            if bal is not None:
                infos = bal.get("balance_infos") or []
                text = "，".join(f"{b.get('total_balance')} {b.get('currency')}" for b in infos) or "未知"
                result["balance"] = {"available": bal.get("is_available"), "infos": infos}
                result["steps"].append({"name": "账户余额", "ok": bool(bal.get("is_available")),
                                        "detail": f"余额 {text}" + ("" if bal.get("is_available") else "（余额不足，无法调用）")})
        except AIError as e:
            result["steps"].append({"name": "账户余额", "ok": False, "detail": e.message})
        if body.chat:
            try:
                res = client.chat([{"role": "user", "content": "Reply with the single word: OK"}], thinking=False,
                                  max_tokens=8, kind="connection_test", retries=1)
                result["steps"].append({"name": f"模型调用（{s['model']}）", "ok": True,
                                        "detail": f"响应正常，用时 {time.monotonic() - t0:.1f} 秒"})
                result["model_used"] = res.model
            except AIError as e:
                result["steps"].append({"name": f"模型调用（{s['model']}）", "ok": False, "detail": e.message})
                result["error"] = e.message
                result["error_code"] = e.code
                return _finish_test(result, body)
        result["ok"] = all(st["ok"] for st in result["steps"])
        if not result["ok"] and not result.get("error"):
            result["error"] = next(st["detail"] for st in result["steps"] if not st["ok"])
        return _finish_test(result, body)
    finally:
        client.close()


def _finish_test(result: dict[str, Any], body: TestIn) -> dict[str, Any]:
    if not body.api_key:  # only remember results for the saved key
        db.cache_set("deepseek_last_test", {k: result.get(k) for k in ("ok", "at", "error", "steps")})
    return result


class AIPrefs(BaseModel):
    base_url: str | None = None
    model: str | None = None
    thinking_for_analysis: bool | None = None


@router.patch("/ai/config")
def patch_ai(body: AIPrefs):
    patch = {k: v for k, v in body.model_dump().items() if v is not None}
    if patch:
        settings_store.update_settings({"ai": patch})
    return _ai_config()


@router.get("/ai/available")
def ai_available():
    return {"configured": is_configured()}
