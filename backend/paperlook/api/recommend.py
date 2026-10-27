from __future__ import annotations

from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel

from .. import db, papers as papers_repo
from ..errors import AppError
from ..jobs import manager
from ..recommend import engine

router = APIRouter(tags=["recommend"])


class RunIn(BaseModel):
    mode: str = "today"  # today | more | auto (auto never uses AI)
    refresh: bool = False


@router.post("/recommend/run")
def run(body: RunIn):
    mode = body.mode if body.mode in ("today", "more", "auto") else "today"
    job = manager.submit("recommend", lambda j: engine.run(j, mode=mode, refresh=body.refresh), meta={"mode": mode})
    return job.to_dict()


@router.get("/recommend/active")
def active():
    j = manager.find_active("recommend", None)
    return j.to_dict() if j else None


def _items_for_batches(batch_ids: list[int]) -> list[dict[str, Any]]:
    if not batch_ids:
        return []
    marks = ",".join("?" for _ in batch_ids)
    rows = db.query(
        f"SELECT r.*, p.* , r.id AS rec_id, r.created_at AS rec_created_at FROM recommendations r "
        f"JOIN papers p ON p.id = r.paper_id WHERE r.batch_id IN ({marks}) ORDER BY r.batch_id DESC, r.rank ASC",
        batch_ids,
    )
    ids = [r["paper_id"] for r in rows]
    ai = papers_repo.ai_status_summary(ids)
    states = {pid: papers_repo.get_state(pid) for pid in ids}
    out = []
    for r in rows:
        paper = papers_repo._decode({k: r[k] for k in r if k in papers_repo.COLUMNS or k == "id"} | {"id": r["paper_id"]})
        out.append({
            "rec_id": r["rec_id"], "batch_id": r["batch_id"], "rank": r["rank"], "score": r["score"],
            "breakdown": db.loads(r["breakdown"], {}), "reasons": db.loads(r["reasons"], []),
            "direction_name": r["direction_name"], "ai": db.loads(r["ai"], None),
            "recommended_at": r["rec_created_at"],
            "paper": papers_repo.card(paper, states[r["paper_id"]]),
            "ai_status": ai.get(r["paper_id"], {}),
        })
    return out


def _batch(row: dict[str, Any]) -> dict[str, Any]:
    return {"id": row["id"], "created_at": row["created_at"], "day": row["day"], "params": db.loads(row["params"], {}),
            "stats": db.loads(row["stats"], {}), "message": row["message"]}


@router.get("/recommend/today")
def today():
    day = engine.local_today().isoformat()
    batches = [_batch(r) for r in db.query("SELECT * FROM rec_batches WHERE day = ? ORDER BY id DESC", (day,))]
    items = _items_for_batches([b["id"] for b in batches])
    last = db.query_one("SELECT * FROM rec_batches ORDER BY id DESC LIMIT 1")
    return {
        "day": day,
        "batches": batches,
        "items": items,
        "last_batch": _batch(last) if last else None,
        "active_job": (lambda j: j.to_dict() if j else None)(manager.find_active("recommend", None)),
    }


@router.get("/recommend/history")
def history(days: int = 30, before: str | None = None):
    params: list[Any] = []
    where = ""
    if before:
        where = "WHERE day < ?"
        params.append(before)
    day_rows = db.query(f"SELECT DISTINCT day FROM rec_batches {where} ORDER BY day DESC LIMIT ?", (*params, max(1, min(days, 120))))
    out = []
    for dr in day_rows:
        batches = [_batch(r) for r in db.query("SELECT * FROM rec_batches WHERE day = ? ORDER BY id DESC", (dr["day"],))]
        out.append({"day": dr["day"], "batches": batches, "items": _items_for_batches([b["id"] for b in batches])})
    return out


@router.get("/recommend/batches/{batch_id}")
def batch(batch_id: int):
    r = db.query_one("SELECT * FROM rec_batches WHERE id = ?", (batch_id,))
    if not r:
        raise AppError("推荐批次不存在", status_code=404)
    return {**_batch(r), "items": _items_for_batches([batch_id])}
