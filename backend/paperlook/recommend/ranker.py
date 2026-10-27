"""Combine relevance, quality and freshness into one explainable score, then pick papers.

    score = w_r * relevance + w_q * quality + w_f * freshness      (weights sum to 1)

Guards against a single factor dominating:
  - a paper must reach MIN_RELEVANCE for some direction to be a candidate at all
    (quality/freshness can never pull in an off-topic paper)
  - quality is shrunk toward neutral when evidence is thin (see quality.py)
  - freshness has a floor (see freshness.py)

Directions: each paper is assigned to its best-matching direction. Slots are split across
directions in proportion to their "attention" weight (largest-remainder method); unused slots
go to the best remaining papers overall. The final list is ordered by score.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import date
from typing import Any

from .freshness import age_days, freshness
from .quality import assess
from .relevance import CompiledDirection, RelevanceResult, score_paper

MIN_RELEVANCE = 0.3


@dataclass
class Scored:
    paper: dict[str, Any]
    direction: CompiledDirection
    relevance: RelevanceResult
    other_directions: list[str]
    quality: dict[str, Any]
    freshness: float
    score: float = 0.0
    ai: dict[str, Any] | None = None
    reasons: list[str] = field(default_factory=list)

    @property
    def relevance_score(self) -> float:
        if self.ai and self.ai.get("relevance") is not None:
            # Blend keyword relevance with the model's judgement (explicitly opted-in AI re-rank).
            return 0.4 * self.relevance.score + 0.6 * float(self.ai["relevance"])
        return self.relevance.score


def score_candidates(papers: list[dict[str, Any]], directions: list[CompiledDirection], weights: dict[str, float],
                     today: date, half_life: float, venue_stats: dict[str, dict[str, Any]]) -> tuple[list[Scored], dict[str, int]]:
    stats = {"excluded_keyword": 0, "low_relevance": 0}
    out: list[Scored] = []
    for p in papers:
        results = []
        excluded_somewhere = False
        for d in directions:
            r = score_paper(d, p.get("title") or "", p.get("abstract"), p.get("categories") or [])
            if r.excluded:
                # Exclusions are per direction: the paper may still fit another direction.
                excluded_somewhere = True
                continue
            results.append((d, r))
        matching = [(d, r) for d, r in results if r.score >= MIN_RELEVANCE]
        if not matching:
            stats["excluded_keyword" if excluded_somewhere else "low_relevance"] += 1
            continue
        matching.sort(key=lambda x: (x[1].score, x[0].weight), reverse=True)
        best_d, best_r = matching[0]
        q = assess(p, today, venue_stats)
        f = freshness(p.get("published"), p.get("date_quality"), today, half_life)
        s = Scored(paper=p, direction=best_d, relevance=best_r, other_directions=[d.name for d, _ in matching[1:]],
                   quality=q, freshness=f)
        compute_score(s, weights)
        out.append(s)
    return out, stats


def compute_score(s: Scored, weights: dict[str, float]) -> None:
    s.score = round(
        weights["relevance"] * s.relevance_score + weights["quality"] * s.quality["score"] + weights["freshness"] * s.freshness,
        4,
    )


def allocate_quotas(count: int, directions: list[CompiledDirection], available: dict[int, int]) -> dict[int, int]:
    active = [d for d in directions if available.get(d.id, 0) > 0]
    if not active:
        return {}
    total_w = sum(d.weight for d in active)
    raw = {d.id: count * d.weight / total_w for d in active}
    quotas = {k: min(available[k], math.floor(v)) for k, v in raw.items()}
    remaining = count - sum(quotas.values())
    for k in sorted(raw, key=lambda k: raw[k] - math.floor(raw[k]), reverse=True):
        if remaining <= 0:
            break
        if quotas[k] < available[k]:
            quotas[k] += 1
            remaining -= 1
    return quotas


def select(scored: list[Scored], directions: list[CompiledDirection], count: int) -> list[Scored]:
    by_dir: dict[int, list[Scored]] = {}
    for s in sorted(scored, key=lambda x: x.score, reverse=True):
        by_dir.setdefault(s.direction.id, []).append(s)
    quotas = allocate_quotas(count, directions, {k: len(v) for k, v in by_dir.items()})
    chosen: list[Scored] = []
    chosen_ids: set[int] = set()
    for did, q in quotas.items():
        for s in by_dir[did][:q]:
            chosen.append(s)
            chosen_ids.add(id(s))
    if len(chosen) < count:
        for s in sorted(scored, key=lambda x: x.score, reverse=True):
            if len(chosen) >= count:
                break
            if id(s) not in chosen_ids:
                chosen.append(s)
                chosen_ids.add(id(s))
    chosen.sort(key=lambda x: x.score, reverse=True)
    return chosen


def build_reasons(s: Scored, today: date) -> list[str]:
    reasons: list[str] = []
    r = s.relevance
    parts = []
    if r.title_hits:
        parts.append("标题含 " + "、".join(r.title_hits[:3]))
    if r.abstract_hits:
        parts.append("摘要含 " + "、".join(r.abstract_hits[:3]))
    if not parts and r.category_match:
        parts.append("属于该方向的 arXiv 分类")
    reasons.append(f"匹配「{s.direction.name}」：" + "；".join(parts) if parts else f"匹配「{s.direction.name}」")
    if s.ai and s.ai.get("reason"):
        reasons.append("AI 评估：" + s.ai["reason"])
    for sig in s.quality["signals"]:
        reasons.append(sig["label"])
    age = age_days(s.paper.get("published"), today)
    if age is not None:
        when = "今天发布" if age == 0 else ("昨天发布" if age == 1 else f"{age} 天前发布")
        if s.paper.get("date_quality") == "approx":
            when += "（日期为近似值）"
        reasons.append(when)
    if s.other_directions:
        reasons.append("同时相关：" + "、".join(s.other_directions[:2]))
    return reasons


def breakdown(s: Scored, weights: dict[str, float]) -> dict[str, Any]:
    return {
        "total": s.score,
        "relevance": round(s.relevance_score, 4),
        "keyword_relevance": round(s.relevance.score, 4),
        "ai_relevance": (s.ai or {}).get("relevance"),
        "quality": s.quality["score"],
        "quality_confidence": s.quality["confidence"],
        "quality_insufficient": s.quality["insufficient"],
        "quality_signals": s.quality["signals"],
        "freshness": s.freshness,
        "weights": weights,
        "matched": {"title": s.relevance.title_hits, "abstract": s.relevance.abstract_hits,
                    "category": s.relevance.category_match},
    }
