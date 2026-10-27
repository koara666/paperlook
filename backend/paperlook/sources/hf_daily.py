"""Hugging Face Daily Papers - used only as a *signal* (community attention) for arXiv papers,
never as a candidate source. Covers mostly ML/AI papers; absence from the list is NOT treated
as a negative signal."""
from __future__ import annotations

import logging
from datetime import date, datetime, timedelta, timezone
from typing import Any

from .. import db
from .base import RateLimiter, SourceError, get_with_retry

log = logging.getLogger(__name__)
URL = "https://huggingface.co/api/daily_papers"
limiter = RateLimiter(0.3)
MAX_DAYS = 14


def fetch_signals(date_from: date, date_to: date) -> tuple[dict[str, dict[str, Any]], str | None]:
    """Returns ({arxiv_id: {upvotes, github_repo, github_stars}}, error_message)."""
    out: dict[str, dict[str, Any]] = {}
    error = None
    # HF indexes days in UTC and rejects dates after the current UTC day.
    today = datetime.now(timezone.utc).date()
    date_to = min(date_to, today)
    start = max(date_from, date_to - timedelta(days=MAX_DAYS))
    d = start
    while d <= date_to:
        key = f"hf_daily:{d.isoformat()}"
        # Past days rarely change; today's list keeps growing.
        cached = db.cache_get(key, max_age_seconds=3 * 3600 if d >= today - timedelta(days=1) else 7 * 86400)
        if cached is None:
            try:
                resp = get_with_retry(URL, params={"date": d.isoformat(), "limit": 100}, source_name="Hugging Face",
                                      limiter=limiter, attempts=2, timeout=20)
                items = resp.json()
                cached = {}
                for it in items if isinstance(items, list) else []:
                    p = it.get("paper") or {}
                    pid = p.get("id")
                    if not pid:
                        continue
                    cached[pid] = {
                        "upvotes": int(p.get("upvotes") or 0),
                        "github_repo": p.get("githubRepo"),
                        "github_stars": p.get("githubStars"),
                    }
                db.cache_set(key, cached)
            except (SourceError, ValueError) as e:
                msg = getattr(e, "message", str(e))
                # The newest day's list is often not open yet (HTTP 400) - expected, not an error.
                if d < today:
                    error = msg
                log.info("HF daily papers unavailable for %s: %s", d, msg)
                cached = {}
        for pid, info in cached.items():
            prev = out.get(pid)
            if not prev or info["upvotes"] > prev["upvotes"]:
                out[pid] = info
        d += timedelta(days=1)
    return out, error
