"""Recommendation run: fetch -> merge -> time filter -> drop already-seen -> enrich -> score -> select -> persist.

Uses only free, non-AI data APIs unless the user explicitly enabled "AI re-rank" in settings.
Each direction may override the global time window (fields such as history publish a few papers a month)
and restrict the paper languages; both decide candidacy per direction.
"""
from __future__ import annotations

import hashlib
import logging
import re
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta
from typing import Any

from .. import db, directions as directions_mod, i18n, papers as papers_repo, settings_store
from ..errors import AppError
from ..i18n import msg, t
from ..jobs import Job
from ..sources import REGISTRY, RawPaper, SourceError, SourceQuery
from ..sources import hf_daily
from ..sources.openalex import fetch_source_stats
from . import dedupe, feedback, ranker
from .relevance import compile_direction

log = logging.getLogger(__name__)

PER_DIRECTION_MAX = {"arxiv": 200, "openalex": 100, "cinii": 100, "semantic_scholar": 150, "pubmed": 100}
POOL_MAX_AGE = 2 * 3600
# A pool where some source failed (e.g. arXiv 429) is reused only briefly, so the next run retries that source.
PARTIAL_POOL_MAX_AGE = 10 * 60
# A direction with fewer candidates than this (after filters) gets a "few papers" hint.
SPARSE_CANDIDATES = 3


def local_today() -> date:
    return datetime.now().date()


def direction_window(d: dict[str, Any], global_window: int) -> int:
    return int(d.get("window_days") or global_window)


def _pool_key(dirs: list[dict], sources: list[str], window: int, today: date) -> str:
    basis = db.dumps({"d": [(d["id"], d["keywords"], d["exclude"], d["categories"], d.get("languages") or [],
                             direction_window(d, window)) for d in dirs],
                      "s": sorted(sources), "w": window, "t": today.isoformat(), "v": 2})
    return "pool:" + hashlib.sha1(basis.encode()).hexdigest()[:16]


def _query(d: dict[str, Any], sid: str, window: int, today: date, max_results: int | None = None) -> SourceQuery:
    return SourceQuery(keywords=d["keywords"], exclude=d["exclude"], categories=d["categories"],
                       date_from=today - timedelta(days=direction_window(d, window)), date_to=today,
                       max_results=max_results or PER_DIRECTION_MAX.get(sid, 100), languages=d.get("languages") or [])


def _fetch_pool(job: Job, dirs: list[dict], sources: list[str], window: int, today: date) -> tuple[list[dict], dict]:
    total_steps = len(sources) * len(dirs)
    job.update(total=total_steps + 3, progress=0, message=t("job.rec.connecting"), force=True)
    source_stats: dict[str, Any] = {}

    def fetch_one(sid: str) -> tuple[str, list[RawPaper], list[Any]]:
        src = REGISTRY[sid]
        found: list[RawPaper] = []
        errors: list[Any] = []
        for d in dirs:
            if job.cancelled:
                break
            job.update(message=t("job.rec.searching", source=src.name, direction=d["name"]))
            try:
                found.extend(src.search(_query(d, sid, window, today)))
            except SourceError as e:
                errors.append(e.message)
                if not e.retryable or e.code == "rate_limit":
                    job.advance(len(dirs) - dirs.index(d))
                    break
            except Exception as e:  # never let one source kill the run
                log.exception("source %s failed", sid)
                errors.append(msg("src.crashed", source=src.name, error=type(e).__name__))
            job.advance()
        return sid, found, errors

    raw: list[RawPaper] = []
    with ThreadPoolExecutor(max_workers=max(1, len(sources))) as ex:
        for sid, found, errors in ex.map(fetch_one, sources):
            raw.extend(found)
            uniq = list({db.dumps(e): e for e in errors}.values())  # de-duplicate, keep order
            source_stats[sid] = {"name": REGISTRY[sid].name, "fetched": len(found), "errors": uniq}
    job.check_cancelled()
    raw.extend(_arxiv_fallback(job, dirs, sources, source_stats, window, today))
    merged = dedupe.merge(raw)
    return merged, source_stats


def _arxiv_fallback(job: Job, dirs: list[dict], sources: list[str], source_stats: dict, window: int,
                    today: date) -> list[RawPaper]:
    """The arXiv API often throttles whole IPs (HTTP 429, 2026). Then fetch arXiv papers through OpenAlex,
    which indexes them with the same v1 dates (but a few days late), so a refused arXiv still yields papers."""
    ax = source_stats.get("arxiv")
    if not ax or not ax["errors"] or "openalex" not in sources or job.cancelled:
        return []
    job.update(message=t("job.rec.arxiv_fallback"), force=True)
    found: list[RawPaper] = []
    for d in dirs:
        try:
            found.extend(REGISTRY["openalex"].search(_query(d, "openalex", window, today, 100), arxiv_only=True))  # type: ignore[call-arg]
        except SourceError as e:
            log.info("arXiv fallback via OpenAlex failed: %s", e.text)
            break
    ax["fallback"] = {"via": "OpenAlex", "fetched": len(found)}
    return found


def run(job: Job, mode: str = "today", refresh: bool = False) -> dict[str, Any]:
    settings = settings_store.get_settings()
    dirs = directions_mod.list_directions(enabled_only=True)
    if not dirs:
        raise AppError(t("err.no_directions"), code="no_directions")
    sources = [sid for sid, on in settings["sources"].items() if on and sid in REGISTRY]
    if not sources:
        raise AppError(t("err.no_sources"), code="no_sources")

    count = settings["daily_count"]
    window = settings["window_days"]
    today = local_today()
    windows = {d["id"]: direction_window(d, window) for d in dirs}
    date_from = today - timedelta(days=max(windows.values()))

    pool_key = _pool_key(dirs, sources, window, today)
    cached = None if refresh else db.cache_get(pool_key, max_age_seconds=POOL_MAX_AGE)
    if cached and cached.get("partial"):
        cached = db.cache_get(pool_key, max_age_seconds=PARTIAL_POOL_MAX_AGE)
    if cached:
        merged, source_stats = cached["papers"], cached["source_stats"]
        job.update(total=3, progress=0, message=t("job.rec.cached"), force=True)
    else:
        merged, source_stats = _fetch_pool(job, dirs, sources, window, today)
        total_fetched = sum(s["fetched"] for s in source_stats.values())
        if total_fetched == 0:
            errs = [e for s in source_stats.values() for e in s["errors"]]
            if errs:
                raise AppError(t("err.sources_failed", errors="; ".join(str(i18n.render(e)) for e in errs[:3])),
                               code="sources_failed")
        db.cache_set(pool_key, {"papers": merged, "source_stats": source_stats,
                                "partial": any(s["errors"] for s in source_stats.values())})

    stats: dict[str, Any] = {"sources": source_stats, "merged": len(merged)}

    # 1) time window: decides candidacy only (ordering comes from freshness later). Each direction's own
    #    window is checked again when scoring; here the widest window applies.
    in_window = []
    no_date = 0
    for p in merged:
        pub = p.get("published")
        if not pub or p.get("date_quality") == "unknown":
            no_date += 1
            continue
        try:
            d = date.fromisoformat(pub)
        except ValueError:
            no_date += 1
            continue
        if date_from <= d <= today:
            in_window.append(p)
    stats.update(in_window=len(in_window), no_reliable_date=no_date)

    # 2) never repeat papers already recommended or dismissed
    seen = papers_repo.seen_identity_keys()
    fresh = [p for p in in_window if not (set(dedupe.identity_keys(p)) & seen)]
    stats["already_seen"] = len(in_window) - len(fresh)
    job.advance(message=t("job.rec.quality"))
    job.check_cancelled()

    # 3) enrichment signals (free APIs, cached)
    if settings["signals"].get("hf_daily"):
        arxiv_ids = {p["arxiv_id"] for p in fresh if p.get("arxiv_id")}
        if arxiv_ids:
            hf, hf_err = hf_daily.fetch_signals(date_from, today)
            for p in fresh:
                info = hf.get(p.get("arxiv_id") or "")
                if info:
                    p["signals"]["hf_upvotes"] = info["upvotes"]
                    if info.get("github_repo"):
                        p["signals"]["hf_github_repo"] = info["github_repo"]
            stats["hf_daily"] = {"matched": sum(1 for p in fresh if p["signals"].get("hf_upvotes")), "error": hf_err}
    venue_ids = [p["signals"]["openalex_source_id"] for p in fresh if p.get("signals", {}).get("openalex_source_id")]
    venue_stats = fetch_source_stats(venue_ids) if venue_ids else {}
    job.advance(message=t("job.rec.ranking"))

    # 4) score & select
    compiled = [compile_direction({**d, "window_days": windows[d["id"]]}) for d in dirs]
    half_life = settings_store.half_life_days(settings)
    weights = settings["weights"]
    scored, rstats = ranker.score_candidates(fresh, compiled, weights, today, half_life, venue_stats,
                                             prefer_reviews=bool(settings.get("prefer_reviews")))
    stats.update(rstats)
    stats["relevant"] = len(scored)

    # The user's own feedback (stars, notes, "not interested"…) adjusts the order, never candidacy.
    if settings.get("personalize", True) and scored:
        prefs = feedback.preferences([s.paper for s in scored])
        for i, s in enumerate(scored):
            s.pref = prefs.get(i)
            ranker.compute_score(s, weights)
        stats["personalized"] = bool(prefs)

    ai_info: dict[str, Any] | None = None
    # "auto" runs (triggered by opening the app) never spend API tokens.
    if settings.get("ai_rerank") and scored and mode != "auto":
        ai_info = _ai_rerank(job, scored, compiled, weights, count)
        stats["ai_rerank"] = ai_info

    chosen = ranker.select(scored, compiled, count)
    job.check_cancelled()
    per_dir = {d.id: {"name": d.name, "window": d.window_days, "candidates": 0, "chosen": 0} for d in compiled}
    for s in scored:
        per_dir[s.direction.id]["candidates"] += 1
    for s in chosen:
        per_dir[s.direction.id]["chosen"] += 1
    stats["directions"] = per_dir

    # 5) persist
    message, hints = _summary(len(chosen), count, window, stats, compiled)
    stats["hints"] = hints
    with db.transaction():
        batch_id = db.execute(
            "INSERT INTO rec_batches(created_at, day, params, stats, message) VALUES(?,?,?,?,?)",
            (db.now_iso(), today.isoformat(), db.dumps({
                "mode": mode, "count": count, "window_days": window, "weights": weights,
                "time_preference": settings["time_preference"], "sources": sources,
                "directions": [{"id": d["id"], "name": d["name"], "window_days": windows[d["id"]]} for d in dirs],
                "ai_rerank": bool(ai_info and ai_info.get("used")),
                "personalized": bool(stats.get("personalized")),
            }), db.dumps(stats), db.dumps(message) if message else None),
        )
        for rank, s in enumerate(chosen, start=1):
            pid = papers_repo.upsert(s.paper)
            s.reasons = ranker.build_reasons(s, today)
            db.execute(
                "INSERT INTO recommendations(batch_id, paper_id, rank, score, breakdown, reasons, direction_id, direction_name, ai, created_at) "
                "VALUES(?,?,?,?,?,?,?,?,?,?)",
                (batch_id, pid, rank, s.score, db.dumps(ranker.breakdown(s, weights)), db.dumps(s.reasons),
                 s.direction.id, s.direction.name, db.dumps(s.ai) if s.ai else None, db.now_iso()),
            )
    job.advance(message=t("job.done"))
    return {"batch_id": batch_id, "count": len(chosen), "requested": count,
            "message": render_message(db.dumps(message) if message else None)}


def _ai_rerank(job: Job, scored: list[ranker.Scored], compiled, weights, count: int) -> dict[str, Any]:
    from ..ai import rerank as ai_rerank
    from ..ai.client import is_configured

    if not is_configured():
        return {"used": False, "note": msg("rec.rerank_no_key")}
    pool = sorted(scored, key=lambda s: s.score, reverse=True)[: min(40, max(20, count * 4))]
    job.update(message=t("job.rec.rerank", n=len(pool)), force=True)
    try:
        results, usage = ai_rerank.rerank(pool, compiled)
    except AppError as e:
        return {"used": False, "note": msg("rec.rerank_failed", error=e.message)}
    for i, s in enumerate(pool):
        r = results.get(i)
        if r:
            s.ai = r
            ranker.compute_score(s, weights)
    return {"used": True, "candidates": len(pool), "usage": usage}


def _summary(found: int, requested: int, window: int, stats: dict[str, Any],
             directions: list) -> tuple[list[dict] | None, dict[str, Any]]:
    """Explain a short or failed result and suggest what to change. Returns (stored messages, hints for the UI)."""
    failed = [s["name"] for s in stats["sources"].values() if s["errors"] and s["fetched"] == 0]
    parts: list[dict] = []
    hints: dict[str, Any] = {}
    if found == 0:
        parts.append(msg("rec.none_found", window=window))
    elif found < requested:
        parts.append(msg("rec.few_found", window=window, found=found, requested=requested))
    if found < requested:
        if window <= 3:
            parts.append(msg("rec.weekend_hint"))
            hints["widen_to"] = 7
        else:
            parts.append(msg("rec.widen_hint"))
            hints["widen_to"] = next((w for w in (7, 14, 30, 90, 180, 365) if w > window), None)
    # Directions with (almost) no candidates: typically slow-publishing fields or very specific keywords.
    sparse = []
    for d in directions:
        n = stats["directions"][d.id]["candidates"]
        if n < SPARSE_CANDIDATES and d.window_days < 365:
            suggest = next(w for w in (30, 90, 180, 365) if w > d.window_days)
            sparse.append({"id": d.id, "name": d.name, "candidates": n, "window": d.window_days, "suggest": suggest})
    if sparse and found < requested:
        hints["sparse"] = sparse
    if failed:
        parts.append(msg("rec.sources_failed", sources=failed))
    return (parts or None), hints


def render_message(stored: str | None) -> str | None:
    """rec_batches.message: JSON list of stored messages (1.3+) or plain Chinese text (older)."""
    if not stored:
        return None
    value = db.loads(stored, None) if stored[:1] in "[{" else None
    if value is None:  # 1.x: Chinese sentences joined by spaces
        return " ".join(str(i18n.render(s)) for s in re.split(r"(?<=。)\s*", stored) if s)
    if isinstance(value, list):
        return " ".join(str(i18n.render(m)) for m in value)
    return str(i18n.render(value))
