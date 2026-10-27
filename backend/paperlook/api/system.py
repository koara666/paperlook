from __future__ import annotations

import platform
import time

from fastapi import APIRouter

from .. import config, db, secrets_store
from ..ai.client import is_configured, usage_summary
from ..jobs import manager

router = APIRouter(tags=["system"])
STARTED = time.time()


@router.get("/health")
def health():
    return {"ok": True, "app": config.APP_NAME, "version": config.VERSION}


@router.get("/status")
def status():
    counts = {
        "papers": (db.query_one("SELECT COUNT(*) AS n FROM papers") or {}).get("n", 0),
        "recommendations": (db.query_one("SELECT COUNT(*) AS n FROM recommendations") or {}).get("n", 0),
        "fulltexts": (db.query_one("SELECT COUNT(*) AS n FROM fulltext") or {}).get("n", 0),
        "ai_results": (db.query_one("SELECT COUNT(*) AS n FROM ai_results WHERE kind != 'glossary'") or {}).get("n", 0),
        "translated_units": (db.query_one("SELECT COUNT(*) AS n FROM translations") or {}).get("n", 0),
    }
    return {
        "app": config.APP_NAME,
        "version": config.VERSION,
        "data_dir": str(config.DATA_DIR),
        "db_size": db.file_size_bytes(),
        "counts": counts,
        "ai_configured": is_configured(),
        "secret_backend": secrets_store.backend_name(),
        "python": platform.python_version(),
        "uptime_seconds": int(time.time() - STARTED),
        "active_jobs": len(manager.active()),
    }


@router.get("/usage")
def usage():
    return usage_summary()


@router.get("/jobs/{job_id}")
def get_job(job_id: str):
    j = manager.get(job_id)
    if not j:
        from ..errors import AppError
        raise AppError("任务不存在", status_code=404)
    return j


@router.post("/jobs/{job_id}/cancel")
def cancel_job(job_id: str):
    return {"cancelled": manager.cancel(job_id)}


@router.get("/jobs")
def list_jobs(paper_id: str | None = None):
    return manager.active(paper_id)
