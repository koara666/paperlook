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
import re
from dataclasses import dataclass, field
from datetime import date
from typing import Any

from ..i18n import msg
from . import feedback
from .freshness import age_days, freshness
from .quality import assess, is_review
from .relevance import CompiledDirection, RelevanceResult, score_paper

# A single keyword mentioned once in the abstract (0.33) is not enough: that is usually an incidental mention.
MIN_RELEVANCE = 0.36
# "Prefer surveys and tutorials" (settings.prefer_reviews): ordering bonus on relevance.
REVIEW_BONUS = 0.08
# Ordering penalties on relevance (candidacy stays keyword-based):
FIELD_PENALTY = 0.15  # OpenAlex files the paper under a field the direction does not name
MINOR_PENALTY = 0.15  # book reviews, editorials, commentaries: short pieces, not research articles
_NOTICE = re.compile(r"^\s*(?:corrigendum|erratum|correction to|retraction|retracted|withdrawn|expression of concern|"
                     r"front matter|back matter|table of contents|issue information|masthead|editorial board|"
                     r"index to volume|訂正|正误|勘误|정오표)\b", re.I)
_MINOR = re.compile(r"^\s*(?:book review|editorial\b|introduction to the special issue|preface\b|foreword\b|"
                    r"commentary\b|comment on|reply to|response to|in memoriam|obituary)|^\s*\[?(?:書評|书评|新刊紹介|紹介|"
                    r"서평|추도|评《)|書評と紹介|著『[^』]+』\s*$", re.I)


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
    pref: feedback.Preference | None = None
    review: bool = False
    review_bonus: float = 0.0
    field_mismatch: str | None = None  # the paper's OpenAlex field when it is not among the direction's fields
    minor: bool = False  # book review / editorial / commentary
    reasons: list[Any] = field(default_factory=list)

    @property
    def relevance_score(self) -> float:
        base = self.relevance.score
        if self.ai and self.ai.get("relevance") is not None:
            # Blend keyword relevance with the model's judgement (explicitly opted-in AI re-rank).
            base = 0.4 * self.relevance.score + 0.6 * float(self.ai["relevance"])
        if self.pref:
            # The user's own feedback (see feedback.py): ordering only, candidacy stays keyword-based.
            base = base + self.pref.adjust
        base += self.review_bonus - (FIELD_PENALTY if self.field_mismatch else 0.0) - (MINOR_PENALTY if self.minor else 0.0)
        return min(1.0, max(0.0, base))


def eligible(d: CompiledDirection, p: dict[str, Any], today: date) -> str | None:
    """Why a paper cannot be a candidate of this direction (its own window and languages), or None."""
    if d.languages and p.get("language") and p["language"] not in d.languages:
        return "language"
    age = age_days(p.get("published"), today)
    if age is not None and age > d.window_days:
        return "window"
    return None


def score_candidates(papers: list[dict[str, Any]], directions: list[CompiledDirection], weights: dict[str, float],
                     today: date, half_life: float, venue_stats: dict[str, dict[str, Any]],
                     prefer_reviews: bool = False) -> tuple[list[Scored], dict[str, int]]:
    stats = {"excluded_keyword": 0, "low_relevance": 0, "other_language": 0, "notices": 0}
    out: list[Scored] = []
    for p in papers:
        if _NOTICE.search(p.get("title") or ""):  # errata, retraction notices, tables of contents
            stats["notices"] += 1
            continue
        results = []
        excluded_somewhere = False
        reasons_out: set[str] = set()
        for d in directions:
            why = eligible(d, p, today)
            if why:
                reasons_out.add(why)
                continue
            r = score_paper(d, p.get("title") or "", p.get("abstract"), p.get("categories") or [])
            if r.excluded:
                # Exclusions are per direction: the paper may still fit another direction.
                excluded_somewhere = True
                continue
            results.append((d, r))
        matching = [(d, r) for d, r in results if r.score >= MIN_RELEVANCE]
        if not matching:
            if not results and "language" in reasons_out:
                stats["other_language"] += 1
            else:
                stats["excluded_keyword" if excluded_somewhere else "low_relevance"] += 1
            continue
        matching.sort(key=lambda x: (x[1].score, x[0].weight), reverse=True)
        best_d, best_r = matching[0]
        q = assess(p, today, venue_stats)
        # Within a long window (slow fields) "recent" is relative: the half-life grows with the window.
        f = freshness(p.get("published"), p.get("date_quality"), today, max(half_life, best_d.window_days / 6))
        review = is_review(p)
        paper_field = (p.get("signals") or {}).get("field")
        mismatch = paper_field if best_d.fields and paper_field and paper_field not in best_d.fields else None
        s = Scored(paper=p, direction=best_d, relevance=best_r, other_directions=[d.name for d, _ in matching[1:]],
                   quality=q, freshness=f, review=review, review_bonus=REVIEW_BONUS if review and prefer_reviews else 0.0,
                   field_mismatch=mismatch, minor=bool(_MINOR.search(p.get("title") or "")))
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


def build_reasons(s: Scored, today: date) -> list[Any]:
    """Why this paper was recommended, as stored messages (rendered in the interface language when shown)."""
    reasons: list[Any] = []
    r = s.relevance
    if r.title_hits:
        reasons.append(msg("reason.title_hits", direction=s.direction.name, keywords=r.title_hits[:3]))
    if r.abstract_hits:
        reasons.append(msg("reason.abstract_hits", direction=s.direction.name, keywords=r.abstract_hits[:3]))
    if not r.title_hits and not r.abstract_hits:
        reasons.append(msg("reason.category", direction=s.direction.name))
    pref_reason = feedback.reason(s.pref)
    if pref_reason:
        reasons.append(pref_reason)
    if s.review:
        reasons.append(msg("reason.review"))
    if s.field_mismatch:
        reasons.append(msg("reason.field_mismatch", field=msg(f"field.{s.field_mismatch}")))
    if s.minor:
        reasons.append(msg("reason.minor"))
    if s.ai and s.ai.get("reason"):
        reasons.append(msg("reason.ai", reason=s.ai["reason"]))
    for sig in s.quality["signals"]:
        reasons.append(sig["label"])
    age = age_days(s.paper.get("published"), today)
    if age is not None:
        key = "reason.today" if age == 0 else ("reason.yesterday" if age == 1 else "reason.days_ago")
        reasons.append(msg(key + ("_approx" if s.paper.get("date_quality") == "approx" else ""), n=age))
    if s.other_directions:
        reasons.append(msg("reason.also", directions=s.other_directions[:2]))
    return reasons


def breakdown(s: Scored, weights: dict[str, float]) -> dict[str, Any]:
    return {
        "total": s.score,
        "relevance": round(s.relevance_score, 4),
        "keyword_relevance": round(s.relevance.score, 4),
        "ai_relevance": (s.ai or {}).get("relevance"),
        "preference": s.pref.to_dict() if s.pref else None,
        "quality": s.quality["score"],
        "quality_confidence": s.quality["confidence"],
        "quality_insufficient": s.quality["insufficient"],
        "quality_signals": s.quality["signals"],
        "freshness": s.freshness,
        "review": s.review,
        "review_bonus": s.review_bonus or None,
        "field_mismatch": s.field_mismatch,
        "minor": s.minor or None,
        "weights": weights,
        "matched": {"title": s.relevance.title_hits, "abstract": s.relevance.abstract_hits,
                    "category": s.relevance.category_match},
    }
