"""Backup / restore and cache management. Secrets are never included in backups."""
from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import Response
from pydantic import BaseModel

from .. import config, db, settings_store
from ..errors import AppError
from ..i18n import t

router = APIRouter(tags=["data"])

TABLES = ["directions", "papers", "paper_state", "rec_batches", "recommendations", "ai_results", "translations"]


@router.get("/data/export")
def export_backup(include_fulltext: bool = False):
    payload: dict[str, Any] = {
        "app": config.APP_NAME, "version": config.VERSION, "format": 1,
        "exported_at": db.now_iso(), "settings": settings_store.get_settings(),
    }
    for table in TABLES + (["fulltext"] if include_fulltext else []):
        payload[table] = db.query(f"SELECT * FROM {table}")
    name = f"paperlook-backup-{datetime.now().strftime('%Y%m%d-%H%M')}.json"
    return Response(db.dumps(payload), media_type="application/json",
                    headers={"Content-Disposition": f'attachment; filename="{name}"'})


@router.post("/data/import")
async def import_backup(request: Request):
    try:
        data = await request.json()
    except Exception:
        raise AppError(t("err.backup_invalid"))
    if not isinstance(data, dict) or data.get("app") != config.APP_NAME:
        raise AppError(t("err.backup_not_paperlook"))
    counts: dict[str, int] = {}
    with db.transaction() as conn:
        for table in TABLES + ["fulltext"]:
            rows = data.get(table) or []
            if not isinstance(rows, list):
                continue
            cols_info = conn.execute(f"PRAGMA table_info({table})").fetchall()
            valid = {c[1] for c in cols_info}
            n = 0
            for r in rows:
                if not isinstance(r, dict):
                    continue
                keys = [k for k in r if k in valid]
                if not keys:
                    continue
                conn.execute(f"INSERT OR REPLACE INTO {table}({', '.join(keys)}) VALUES({', '.join('?' for _ in keys)})",
                             [r[k] for k in keys])
                n += 1
            counts[table] = n
    if isinstance(data.get("settings"), dict):
        settings_store.replace_settings(data["settings"])
    return {"ok": True, "counts": counts}


class ClearIn(BaseModel):
    target: str


@router.post("/data/clear")
def clear(body: ClearIn):
    target = body.target
    if target == "fulltext_cache":
        db.execute("DELETE FROM fulltext WHERE paper_id NOT IN (SELECT DISTINCT paper_id FROM translations)")
    elif target == "search_cache":
        db.execute("DELETE FROM kv_cache WHERE key LIKE 'pool:%' OR key LIKE 'hf_daily:%'")
    elif target == "history":
        # Forget what was recommended (papers may be recommended again). Starred papers and AI results stay.
        db.execute("DELETE FROM recommendations")
        db.execute("DELETE FROM rec_batches")
        db.execute("DELETE FROM kv_cache WHERE key LIKE 'pool:%'")
    elif target == "usage":
        db.execute("DELETE FROM api_usage")
    else:
        raise AppError(t("err.unknown_clear"))
    db.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    return {"ok": True}
