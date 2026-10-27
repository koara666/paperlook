from __future__ import annotations

from typing import Any
from urllib.parse import quote

from fastapi import APIRouter
from fastapi.responses import Response
from pydantic import BaseModel

from .. import db, export, papers as papers_repo, settings_store
from ..ai import analyze, translate
from ..ai.client import is_configured, not_configured_error
from ..errors import AppError
from ..fulltext import fetcher
from ..jobs import manager

router = APIRouter(tags=["papers"])

AI_KINDS = ("summary", "modules", "contributions", "abstract_translation")


def _require(paper_id: str) -> dict[str, Any]:
    p = papers_repo.get_paper(paper_id)
    if not p:
        raise AppError("论文不存在", status_code=404)
    return p


def _latest_rec(paper_id: str) -> dict[str, Any] | None:
    r = db.query_one("SELECT * FROM recommendations WHERE paper_id = ? ORDER BY id DESC LIMIT 1", (paper_id,))
    if not r:
        return None
    return {"score": r["score"], "breakdown": db.loads(r["breakdown"], {}), "reasons": db.loads(r["reasons"], []),
            "direction_name": r["direction_name"], "ai": db.loads(r["ai"], None), "recommended_at": r["created_at"],
            "batch_id": r["batch_id"]}


def _job_brief(j: dict[str, Any] | None) -> dict[str, Any] | None:
    if not j:
        return None
    return {k: j.get(k) for k in ("id", "status", "progress", "total", "message", "error", "error_code", "created_at", "updated_at")}


def _feature_status(paper_id: str, kind: str, job_kind: str, has_result: bool, result_time: str | None,
                    enabled: bool) -> dict[str, Any]:
    active = manager.find_active(job_kind, paper_id)
    latest = manager.latest(job_kind, paper_id)
    if active:
        status = "running"
        job = active.to_dict()
    else:
        job = latest
        if has_result:
            status = "done"
        elif latest and latest["status"] in ("failed", "interrupted", "partial", "cancelled"):
            status = "failed" if latest["status"] != "partial" else "partial"
        else:
            status = "idle"
        # a failed *regeneration* after an existing result: keep showing the result but surface the error
        if has_result and latest and result_time and latest["status"] == "failed" and (latest["updated_at"] or "") > result_time:
            status = "done"
    if not enabled and status in ("idle",):
        status = "disabled"
    return {"status": status, "job": _job_brief(job)}


def ai_state(paper: dict[str, Any], doc: dict[str, Any] | None) -> dict[str, Any]:
    settings = settings_store.get_settings()
    features = settings["ai"]["features"]
    out: dict[str, Any] = {}
    for kind in AI_KINDS:
        res = analyze.get_result(paper["id"], kind)
        enabled = features.get(kind, True) if kind != "abstract_translation" else True
        st = _feature_status(paper["id"], kind, f"ai:{kind}", bool(res), res["created_at"] if res else None, enabled)
        st["result"] = res
        st["enabled"] = enabled
        # an abstract-based analysis can be upgraded once full text is available
        st["upgradable"] = bool(res and (res.get("basis") or {}).get("type") == "abstract" and doc)
        out[kind] = st
    tstat = translate.status(paper["id"], doc)
    st = _feature_status(paper["id"], "translate", "translate", tstat["done"] > 0 and tstat["done"] >= tstat["total"] > 0,
                         None, features.get("translate", True))
    if st["status"] == "idle" and tstat["done"] > 0:
        st["status"] = "partial"
    st.update(progress=tstat, enabled=features.get("translate", True))
    out["translate"] = st
    return out


@router.get("/papers")
def library(filter: str = "all", q: str = "", limit: int = 30, offset: int = 0):
    where = ["1=1"]
    params: list[Any] = []
    if filter == "starred":
        where.append("COALESCE(s.starred,0) = 1")
    elif filter == "unread":
        where.append("s.read_at IS NULL")
    elif filter == "read":
        where.append("s.read_at IS NOT NULL")
    elif filter == "analyzed":
        where.append("(p.id IN (SELECT paper_id FROM ai_results WHERE kind IN ('summary','modules','contributions')) "
                     "OR p.id IN (SELECT paper_id FROM translations))")
    if filter != "dismissed":
        where.append("COALESCE(s.dismissed,0) = 0")
    else:
        where.append("COALESCE(s.dismissed,0) = 1")
    if q.strip():
        like = f"%{q.strip()}%"
        where.append("(p.title LIKE ? OR p.abstract LIKE ? OR p.authors LIKE ? OR p.venue LIKE ?)")
        params += [like, like, like, like]
    w = " AND ".join(where)
    total = (db.query_one(f"SELECT COUNT(*) AS n FROM papers p LEFT JOIN paper_state s ON s.paper_id = p.id WHERE {w}", params) or {}).get("n", 0)
    rows = db.query(
        f"SELECT p.*, (SELECT MAX(r.created_at) FROM recommendations r WHERE r.paper_id = p.id) AS last_rec "
        f"FROM papers p LEFT JOIN paper_state s ON s.paper_id = p.id WHERE {w} "
        f"ORDER BY COALESCE(last_rec, p.created_at) DESC LIMIT ? OFFSET ?",
        (*params, max(1, min(limit, 100)), max(0, offset)),
    )
    ids = [r["id"] for r in rows]
    ai = papers_repo.ai_status_summary(ids)
    items = []
    for r in rows:
        p = papers_repo._decode(r)
        rec = _latest_rec(p["id"])
        items.append({"paper": papers_repo.card(p), "ai_status": ai.get(p["id"], {}),
                      "recommendation": {k: rec[k] for k in ("score", "direction_name", "recommended_at", "ai")} if rec else None})
    return {"items": items, "total": total}


@router.get("/papers/{paper_id}")
def detail(paper_id: str):
    p = _require(paper_id)
    doc = fetcher.get_cached(paper_id)
    ft = None
    if doc:
        ft = {"available": True, "source": doc["source"], "source_label": doc.get("source_label"),
              "source_url": doc.get("source_url"), "fetched_at": doc.get("fetched_at"), "stats": doc.get("stats"),
              "warnings": doc.get("warnings", [])}
    ft_job = manager.latest("fulltext", paper_id)
    return {
        "paper": p,
        "state": papers_repo.get_state(paper_id),
        "recommendation": _latest_rec(paper_id),
        "fulltext": ft,
        "fulltext_job": _job_brief(ft_job),
        "ai": ai_state(p, doc),
        "ai_configured": is_configured(),
    }


class StateIn(BaseModel):
    read: bool | None = None
    starred: bool | None = None
    dismissed: bool | None = None
    opened: bool | None = None
    note: str | None = None


@router.patch("/papers/{paper_id}/state")
def set_state(paper_id: str, body: StateIn):
    _require(paper_id)
    return papers_repo.set_state(paper_id, **{k: v for k, v in body.model_dump().items() if v is not None})


# ---------------- full text ----------------

@router.get("/papers/{paper_id}/fulltext")
def get_fulltext(paper_id: str):
    p = _require(paper_id)
    doc = fetcher.get_cached(paper_id)
    if not doc:
        active = manager.find_active("fulltext", paper_id)
        return {"available": False, "job": _job_brief(active.to_dict() if active else manager.latest("fulltext", paper_id))}
    tmap = translate.translated_map(paper_id)
    return {
        "available": True,
        "doc": doc,
        "translations": tmap,
        "translation_status": translate.status(paper_id, doc),
        "glossary": translate.get_glossary(paper_id),
        "paper_title": p["title"],
    }


class FulltextIn(BaseModel):
    force: bool = False


@router.post("/papers/{paper_id}/fulltext")
def fetch_fulltext(paper_id: str, body: FulltextIn):
    p = _require(paper_id)
    if not body.force and fetcher.get_cached(paper_id):
        return {"status": "cached"}

    def work(job):
        doc = fetcher.fetch(p, job)
        return {"source": doc["source"], "stats": doc.get("stats")}

    if body.force:
        db.execute("DELETE FROM translations WHERE paper_id = ?", (paper_id,))
    return manager.submit("fulltext", work, paper_id=paper_id).to_dict()


# ---------------- AI analyses (explicitly triggered) ----------------

class AIRunIn(BaseModel):
    force: bool = False


@router.post("/papers/{paper_id}/ai/{kind}")
def run_ai(paper_id: str, kind: str, body: AIRunIn):
    _require(paper_id)
    if kind not in AI_KINDS:
        raise AppError("未知的 AI 功能", status_code=404)
    if not is_configured():
        raise not_configured_error()
    if not body.force and analyze.get_result(paper_id, kind):
        return {"status": "cached"}
    return manager.submit(f"ai:{kind}", lambda j: analyze.run(j, paper_id, kind), paper_id=paper_id).to_dict()


class TranslateIn(BaseModel):
    sections: list[str] | None = None
    force: bool = False


@router.post("/papers/{paper_id}/translate")
def run_translate(paper_id: str, body: TranslateIn):
    _require(paper_id)
    if not is_configured():
        raise not_configured_error()
    active = manager.find_active("translate", paper_id)
    if active:
        return active.to_dict()
    return manager.submit("translate", lambda j: translate.run(j, paper_id, body.sections, body.force),
                          paper_id=paper_id).to_dict()


@router.post("/papers/{paper_id}/translate/cancel")
def cancel_translate(paper_id: str):
    active = manager.find_active("translate", paper_id)
    if active:
        active.cancel()
    return {"cancelled": bool(active)}


@router.get("/papers/{paper_id}/export")
def export_paper(paper_id: str, type: str = "translation", mode: str = "bilingual"):
    p = _require(paper_id)
    if type == "analysis":
        text = export.analysis_markdown(p)
        name = "AI分析"
    else:
        doc = fetcher.get_cached(paper_id)
        if not doc:
            raise AppError("尚未获取全文，无法导出译文。", status_code=404)
        text = export.translation_markdown(p, doc, "zh" if mode == "zh" else "bilingual")
        name = "译文" if mode == "zh" else "双语对照"
    safe = "".join(c for c in p["title"][:60] if c.isalnum() or c in " -_").strip() or "paper"
    filename = f"{safe} - {name}.md"
    return Response(text, media_type="text/markdown; charset=utf-8",
                    headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(filename)}"})
