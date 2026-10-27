"""Recommendation run: fetch -> merge -> time filter -> drop already-seen -> enrich -> score -> select -> persist.

Uses only free, non-AI data APIs unless the user explicitly enabled "AI re-rank" in settings.
"""
from __future__ import annotations

import hashlib
import logging
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta
from typing import Any

from .. import db, directions as directions_mod, papers as papers_repo, settings_store
from ..errors import AppError
from ..jobs import Job
from ..sources import REGISTRY, RawPaper, SourceError, SourceQuery
from ..sources import hf_daily
from ..sources.openalex import fetch_source_stats
from . import dedupe, ranker
from .relevance import compile_direction

log = logging.getLogger(__name__)

PER_DIRECTION_MAX = {"arxiv": 200, "openalex": 100, "semantic_scholar": 150, "pubmed": 100}
POOL_MAX_AGE = 2 * 3600


def local_today() -> date:
    return datetime.now().date()


def _pool_key(dirs: list[dict], sources: list[str], window: int, today: date) -> str:
    basis = db.dumps({"d": [(d["id"], d["keywords"], d["exclude"], d["categories"]) for d in dirs],
                      "s": sorted(sources), "w": window, "t": today.isoformat()})
    return "pool:" + hashlib.sha1(basis.encode()).hexdigest()[:16]


def _fetch_pool(job: Job, dirs: list[dict], sources: list[str], date_from: date, today: date) -> tuple[list[dict], dict]:
    total_steps = len(sources) * len(dirs)
    job.update(total=total_steps + 3, progress=0, message="正在连接论文来源…", force=True)
    source_stats: dict[str, Any] = {}

    def fetch_one(sid: str) -> tuple[str, list[RawPaper], list[str]]:
        src = REGISTRY[sid]
        found: list[RawPaper] = []
        errors: list[str] = []
        for d in dirs:
            if job.cancelled:
                break
            job.update(message=f"正在检索 {src.name}：{d['name']}")
            q = SourceQuery(keywords=d["keywords"], exclude=d["exclude"], categories=d["categories"],
                            date_from=date_from, date_to=today, max_results=PER_DIRECTION_MAX.get(sid, 100))
            try:
                found.extend(src.search(q))
            except SourceError as e:
                errors.append(e.message)
                if not e.retryable or "429" in e.message or "频率" in e.message:
                    job.advance(len(dirs) - dirs.index(d))
                    break
            except Exception as e:  # never let one source kill the run
                log.exception("source %s failed", sid)
                errors.append(f"{src.name} 出现异常：{type(e).__name__}")
            job.advance()
        return sid, found, errors

    raw: list[RawPaper] = []
    with ThreadPoolExecutor(max_workers=max(1, len(sources))) as ex:
        for sid, found, errors in ex.map(fetch_one, sources):
            raw.extend(found)
            # de-duplicate error strings, keep order
            uniq = list(dict.fromkeys(errors))
            source_stats[sid] = {"name": REGISTRY[sid].name, "fetched": len(found), "errors": uniq}
    job.check_cancelled()
    merged = dedupe.merge(raw)
    return merged, source_stats


def run(job: Job, mode: str = "today", refresh: bool = False) -> dict[str, Any]:
    settings = settings_store.get_settings()
    dirs = directions_mod.list_directions(enabled_only=True)
    if not dirs:
        raise AppError("还没有启用的研究方向。请先添加至少一个研究方向。", code="no_directions")
    sources = [sid for sid, on in settings["sources"].items() if on and sid in REGISTRY]
    if not sources:
        raise AppError("没有启用任何论文来源。请在「设置 → 论文来源」中至少启用一个来源。", code="no_sources")

    count = settings["daily_count"]
    window = settings["window_days"]
    today = local_today()
    date_from = today - timedelta(days=window)

    pool_key = _pool_key(dirs, sources, window, today)
    cached = None if refresh else db.cache_get(pool_key, max_age_seconds=POOL_MAX_AGE)
    if cached:
        merged, source_stats = cached["papers"], cached["source_stats"]
        job.update(total=3, progress=0, message="使用最近一次检索结果…", force=True)
    else:
        merged, source_stats = _fetch_pool(job, dirs, sources, date_from, today)
        total_fetched = sum(s["fetched"] for s in source_stats.values())
        if total_fetched == 0:
            errs = [e for s in source_stats.values() for e in s["errors"]]
            if errs:
                raise AppError("所有论文来源都请求失败：" + "；".join(errs[:3]), code="sources_failed")
        db.cache_set(pool_key, {"papers": merged, "source_stats": source_stats})

    stats: dict[str, Any] = {"sources": source_stats, "merged": len(merged)}

    # 1) time window: decides candidacy only (ordering comes from freshness later)
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
    job.advance(message="正在评估论文质量信号…")
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
    job.advance(message="正在计算推荐排序…")

    # 4) score & select
    compiled = [compile_direction(d) for d in dirs]
    half_life = settings_store.half_life_days(settings)
    weights = settings["weights"]
    scored, rstats = ranker.score_candidates(fresh, compiled, weights, today, half_life, venue_stats)
    stats.update(rstats)
    stats["relevant"] = len(scored)

    ai_info: dict[str, Any] | None = None
    # "auto" runs (triggered by opening the app) never spend API tokens.
    if settings.get("ai_rerank") and scored and mode != "auto":
        ai_info = _ai_rerank(job, scored, compiled, weights, count)
        stats["ai_rerank"] = ai_info

    chosen = ranker.select(scored, compiled, count)
    job.check_cancelled()

    # 5) persist
    message = _summary_message(len(chosen), count, window, stats)
    with db.transaction():
        batch_id = db.execute(
            "INSERT INTO rec_batches(created_at, day, params, stats, message) VALUES(?,?,?,?,?)",
            (db.now_iso(), today.isoformat(), db.dumps({
                "mode": mode, "count": count, "window_days": window, "weights": weights,
                "time_preference": settings["time_preference"], "sources": sources,
                "directions": [{"id": d["id"], "name": d["name"]} for d in dirs],
                "ai_rerank": bool(ai_info and ai_info.get("used")),
            }), db.dumps(stats), message),
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
    job.advance(message="完成")
    return {"batch_id": batch_id, "count": len(chosen), "requested": count, "message": message}


def _ai_rerank(job: Job, scored: list[ranker.Scored], compiled, weights, count: int) -> dict[str, Any]:
    from ..ai import rerank as ai_rerank
    from ..ai.client import is_configured

    if not is_configured():
        return {"used": False, "note": "已开启 AI 精排，但尚未配置 DeepSeek API Key，本次使用常规排序。"}
    pool = sorted(scored, key=lambda s: s.score, reverse=True)[: min(40, max(20, count * 4))]
    job.update(message=f"AI 精排中（{len(pool)} 篇候选）…", force=True)
    try:
        results, usage = ai_rerank.rerank(pool, compiled)
    except AppError as e:
        return {"used": False, "note": f"AI 精排失败，已使用常规排序：{e.message}"}
    for i, s in enumerate(pool):
        r = results.get(i)
        if r:
            s.ai = r
            ranker.compute_score(s, weights)
    return {"used": True, "candidates": len(pool), "usage": usage}


def _summary_message(found: int, requested: int, window: int, stats: dict[str, Any]) -> str | None:
    failed = [s["name"] for s in stats["sources"].values() if s["errors"] and s["fetched"] == 0]
    parts = []
    if found == 0:
        parts.append(f"最近 {window} 天内没有找到新的相关论文。")
    elif found < requested:
        parts.append(f"最近 {window} 天内只找到 {found} 篇新的相关论文（目标 {requested} 篇）。")
    if found < requested:
        if window <= 3:
            parts.append("arXiv 周末不发布新论文，可以把时间范围扩大到 7 天。")
        else:
            parts.append("可以扩大时间范围，或为研究方向补充更多关键词。")
    if failed:
        parts.append("以下来源本次请求失败：" + "、".join(failed) + "。")
    return " ".join(parts) or None
