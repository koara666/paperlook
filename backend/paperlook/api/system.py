from __future__ import annotations

import platform
import re
import time

import httpx
from fastapi import APIRouter

from .. import config, db, secrets_store
from ..errors import AppError
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
        "packaged": config.FROZEN,
        "uptime_seconds": int(time.time() - STARTED),
        "active_jobs": len(manager.active()),
    }


def parse_version(v: str) -> tuple[int, int, int, int, str] | None:
    """SemVer -> sortable tuple; a pre-release (1.1.0-beta.1) sorts before its release (1.1.0)."""
    m = re.match(r"^v?(\d+)\.(\d+)\.(\d+)(?:-([0-9A-Za-z.-]+))?$", (v or "").strip())
    if not m:
        return None
    pre = m.group(4) or ""
    return int(m.group(1)), int(m.group(2)), int(m.group(3)), 0 if pre else 1, pre


@router.get("/update")
def check_update():
    """Explicit (button) check of the latest GitHub release. Nothing is downloaded or installed."""
    url = f"https://api.github.com/repos/{config.GITHUB_REPO}/releases/latest"
    try:
        r = httpx.get(url, timeout=15, headers={"User-Agent": config.USER_AGENT, "Accept": "application/vnd.github+json"})
    except httpx.HTTPError as e:
        raise AppError(f"无法连接 GitHub 检查更新（{type(e).__name__}），请检查网络后重试。", code="network")
    if r.status_code == 404:
        return {"current": config.VERSION, "latest": None, "has_update": False,
                "url": f"https://github.com/{config.GITHUB_REPO}/releases"}
    if r.status_code != 200:
        raise AppError(f"GitHub 暂时无法访问（HTTP {r.status_code}），请稍后重试。", code="network")
    rel = r.json()
    latest = str(rel.get("tag_name") or "").removeprefix("v")
    cur, new = parse_version(config.VERSION), parse_version(latest)
    return {
        "current": config.VERSION,
        "latest": latest or None,
        "has_update": bool(cur and new and new > cur),
        "url": rel.get("html_url") or f"https://github.com/{config.GITHUB_REPO}/releases",
        "published_at": rel.get("published_at"),
        "notes": (rel.get("body") or "")[:4000],
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
