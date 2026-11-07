from __future__ import annotations

import re
import time
from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel

from .. import __version__, db, directions as dirs, i18n, secrets_store, settings_store
from ..ai import prompts
from ..ai import client as ai_client
from ..ai.client import DEFAULT_MODELS, GEMINI_DEFAULT_MODELS, PROVIDERS, AIError, get_client, is_configured
from ..errors import AppError
from ..i18n import t
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
        "version": __version__,
        "language": i18n.current(),
        "languages": [{"code": c, "name": i18n.LANG_NAMES[c]} for c in i18n.LANGS],
        "paper_languages": [{"code": c, "name": t(f"plang.{c}")} for c in dirs.PAPER_LANGUAGES],
        "direction_presets": dirs.presets(),
        "preset_groups": dirs.preset_groups(),
        "fields": dirs.fields(),
        "arxiv_categories": dirs.arxiv_categories(),
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
    languages: list[str] = []
    fields: list[str] = []
    window_days: int | None = None
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
    for p in dirs.presets():
        if p["key"] in body.keys and p["name"] not in existing:
            created.append(dirs.create_direction({
                "name": p["name"], "keywords": p["keywords"], "categories": p["categories"], "fields": p["fields"],
                "languages": p["languages"], "window_days": p["window_days"], "weight": 3}))
    if created:
        settings_store.update_settings({"onboarded": True})
    return created


@router.patch("/directions/{direction_id}")
def update_direction(direction_id: int, body: dict[str, Any]):
    try:
        return dirs.update_direction(direction_id, body)
    except KeyError:
        raise AppError(t("err.direction_not_found"), status_code=404)
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
        raise AppError(t("err.direction_name_first"))
    client = get_client()
    cats, fields = dirs.arxiv_categories(), dirs.fields()
    try:
        data, _ = client.chat_json(
            [{"role": "system", "content": prompts.suggest_system()},
             {"role": "user", "content": prompts.suggest_task(body.name.strip(), body.description.strip(), cats, fields,
                                                              i18n.current())}],
            thinking=False, max_tokens=2000, temperature=0.3, kind="suggest_keywords")
    finally:
        client.close()
    valid_cats = {c["id"] for c in cats}
    kws = [str(k).strip() for k in data.get("keywords", []) if str(k).strip()][:16]
    try:
        window = int(data.get("window_days") or 0) or None
    except (TypeError, ValueError):
        window = None
    return {
        "keywords": kws,
        "exclude": [str(k).strip() for k in data.get("exclude", []) if str(k).strip()][:10],
        "categories": [c for c in data.get("categories", []) if c in valid_cats][:4],
        "fields": [str(f) for f in data.get("fields", []) if str(f) in dirs.FIELDS][:3],
        "window_days": max(1, min(365, window)) if window else None,
    }


# ---------------- sources ----------------

def _last_source_stats() -> dict[str, Any]:
    r = db.query_one("SELECT stats, created_at FROM rec_batches ORDER BY id DESC LIMIT 1")
    if not r:
        return {}
    stats = i18n.render(db.loads(r["stats"], {}).get("sources", {}))
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
        "id": "hf_daily", "name": t("source.hf.name"), "enabled": hf, "description": t("source.hf.desc"),
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
        raise AppError(t("err.unknown_source"), status_code=404)
    if body.enabled is not None:
        settings_store.update_settings({"sources": {source_id: body.enabled}})
    if src.key_secret:
        if body.remove_key:
            secrets_store.delete_secret(src.key_secret)
        elif body.api_key and body.api_key.strip():
            secrets_store.set_secret(src.key_secret, body.api_key.strip())
    return list_sources()


# ---------------- AI service configuration (DeepSeek / Gemini) ----------------

def _provider_config(provider: str) -> dict[str, Any]:
    s = settings_store.get_settings()["ai"]
    key = secrets_store.get_secret(PROVIDERS[provider]["secret"])
    models = db.cache_get(f"{provider}_models") or []
    if provider == "gemini":
        g = s["gemini"]
        return {
            "configured": bool(key), "key_masked": secrets_store.mask(key), "label": PROVIDERS[provider]["label"],
            "model": g["model"], "models": sorted(set(models) | set(GEMINI_DEFAULT_MODELS) | {g["model"]}),
            "base_url": g["base_url"], "proxy": g["proxy"], "free_tier": g["free_tier"],
            "rpm": ai_client.free_tier_rpm(g["model"]),
            "requests_today": ai_client.gemini_requests_today(),
            "reset_hour_beijing": ai_client.gemini_reset_hour_beijing(),
            "last_test": db.cache_get("gemini_last_test"),
        }
    return {
        "configured": bool(key), "key_masked": secrets_store.mask(key), "label": PROVIDERS[provider]["label"],
        "model": s["model"], "models": sorted(set(models) | set(DEFAULT_MODELS) | {s["model"]}),
        "base_url": s["base_url"], "last_test": db.cache_get("deepseek_last_test"),
    }


def _ai_config() -> dict[str, Any]:
    s = settings_store.get_settings()["ai"]
    provider = s["provider"]
    providers = {p: _provider_config(p) for p in PROVIDERS}
    active = providers[provider]
    return {
        "provider": provider,
        "providers": providers,
        # the active provider's fields, flattened (status badge, onboarding, …)
        "label": active["label"],
        "configured": active["configured"],
        "key_masked": active["key_masked"],
        "model": active["model"],
        "models": active["models"],
        "base_url": active["base_url"],
        "last_test": active["last_test"],
        "thinking_for_analysis": s["thinking_for_analysis"],
        "output_language": s.get("output_language", "auto"),
        "effective_output_language": prompts.output_language(),
        "secret_backend": secrets_store.backend_name(),
    }


def _provider(name: str | None) -> str:
    if name is None:
        return ai_client.active_provider()
    if name not in PROVIDERS:
        raise AppError(t("err.unknown_provider"), status_code=400)
    return name


@router.get("/ai/config")
def ai_config():
    return _ai_config()


class KeyIn(BaseModel):
    api_key: str
    provider: str | None = None


@router.put("/ai/key")
def set_key(body: KeyIn):
    provider = _provider(body.provider)
    key = body.api_key.strip()
    if len(key) < 10 or " " in key:
        raise AppError(t("err.key_format_deepseek" if provider == "deepseek" else "err.key_format_gemini"))
    secrets_store.set_secret(PROVIDERS[provider]["secret"], key)
    db.cache_set(f"{provider}_last_test", None)
    return _ai_config()


@router.delete("/ai/key")
def delete_key(provider: str | None = None):
    provider = _provider(provider)
    secrets_store.delete_secret(PROVIDERS[provider]["secret"])
    db.cache_set(f"{provider}_last_test", None)
    return _ai_config()


class TestIn(BaseModel):
    api_key: str | None = None  # test a key before saving it
    chat: bool = True
    provider: str | None = None


@router.post("/ai/test")
def test_ai(body: TestIn):
    """Explicit connection test: auth (+ balance for DeepSeek) + a tiny call with the chosen model."""
    provider = _provider(body.provider)
    label = PROVIDERS[provider]["label"]
    key = (body.api_key or "").strip() or secrets_store.get_secret(PROVIDERS[provider]["secret"])
    if not key:
        raise AppError(t("err.key_missing"), code="not_configured")
    client = ai_client.make_client(provider, key, timeout=60)
    model = client.model
    result: dict[str, Any] = {"ok": False, "steps": [], "at": db.now_iso(), "provider": provider}
    try:
        t0 = time.monotonic()
        try:
            models = client.list_models()
            db.cache_set(f"{provider}_models", models)
            result["models"] = models
            shown = models if len(models) <= 8 else models[:8] + [t("test.more_models", n=len(models))]
            result["steps"].append({"name": t("test.auth"), "ok": True,
                                    "detail": t("test.models", models=", ".join(shown) or t("test.none_returned"))})
        except AIError as e:
            result["steps"].append({"name": t("test.auth"), "ok": False, "detail": e.message})
            result["error"] = e.message
            result["error_code"] = e.code
            return _finish_test(result, body, provider)
        if provider == "deepseek":
            try:
                bal = client.balance()
                if bal is not None:
                    infos = bal.get("balance_infos") or []
                    text = ", ".join(f"{b.get('total_balance')} {b.get('currency')}" for b in infos) or t("test.unknown")
                    result["balance"] = {"available": bal.get("is_available"), "infos": infos}
                    result["steps"].append({"name": t("test.balance"), "ok": bool(bal.get("is_available")),
                                            "detail": t("test.balance_ok" if bal.get("is_available") else "test.balance_low",
                                                        balance=text)})
            except AIError as e:
                result["steps"].append({"name": t("test.balance"), "ok": False, "detail": e.message})
        if body.chat:
            try:
                res = client.chat([{"role": "user", "content": "Reply with the single word: OK"}], thinking=False,
                                  max_tokens=8, kind="connection_test", retries=1)
                result["steps"].append({"name": t("test.call", model=model), "ok": True,
                                        "detail": t("test.call_ok", seconds=f"{time.monotonic() - t0:.1f}")})
                result["model_used"] = res.model
            except AIError as e:
                result["steps"].append({"name": t("test.call", model=model), "ok": False, "detail": e.message})
                result["error"] = e.message
                result["error_code"] = e.code
                return _finish_test(result, body, provider)
        result["ok"] = all(st["ok"] for st in result["steps"])
        if not result["ok"] and not result.get("error"):
            result["error"] = next(st["detail"] for st in result["steps"] if not st["ok"])
        if result["ok"]:
            result["message"] = t("test.ok", provider=label)
        return _finish_test(result, body, provider)
    finally:
        client.close()


def _finish_test(result: dict[str, Any], body: TestIn, provider: str) -> dict[str, Any]:
    if not body.api_key:  # only remember results for the saved key
        db.cache_set(f"{provider}_last_test", {k: result.get(k) for k in ("ok", "at", "error", "steps")})
    return result


_PROXY_RE = re.compile(r"^(https?|socks5h?)://[^\s/]+(:\d+)?/?$", re.I)


class AIPrefs(BaseModel):
    provider: str | None = None
    base_url: str | None = None
    model: str | None = None
    thinking_for_analysis: bool | None = None
    output_language: str | None = None
    gemini_model: str | None = None
    gemini_base_url: str | None = None
    gemini_proxy: str | None = None
    gemini_free_tier: bool | None = None


@router.patch("/ai/config")
def patch_ai(body: AIPrefs):
    if body.provider is not None:
        _provider(body.provider)
    fields = body.model_dump()
    patch: dict[str, Any] = {k: v for k, v in fields.items() if v is not None and not k.startswith("gemini_")}
    gemini: dict[str, Any] = {k.removeprefix("gemini_"): v for k, v in fields.items()
                              if v is not None and k.startswith("gemini_")}
    if "proxy" in gemini:
        gemini["proxy"] = gemini["proxy"].strip()
        if gemini["proxy"] and not _PROXY_RE.match(gemini["proxy"]):
            raise AppError(t("err.proxy_format"))
    if "base_url" in gemini and gemini["base_url"].strip() and not re.match(r"^https?://", gemini["base_url"].strip()):
        raise AppError(t("err.base_url_format"))
    if gemini:
        patch["gemini"] = gemini
    if patch:
        settings_store.update_settings({"ai": patch})
    return _ai_config()


@router.get("/ai/available")
def ai_available():
    return {"configured": is_configured()}
