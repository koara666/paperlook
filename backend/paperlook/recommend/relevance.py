"""Keyword relevance between a paper and a research direction.

Transparent and explainable on purpose (every point of score maps to a visible matched keyword):
  - each keyword scores 1.0 if it appears in the title, 0.55-0.8 if only in the abstract
    (more occurrences -> higher), 0 otherwise
  - keyword scores are combined with a saturating "noisy-OR": 1 - prod(1 - 0.6 * s_k)
    so several matches beat one, but no single field dominates
  - arXiv category overlap adds a small bonus
  - any exclusion keyword in title/abstract removes the paper from that direction
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from ..textutil import normalize

KW_STRENGTH = 0.6
CATEGORY_BONUS_PRIMARY = 0.12
CATEGORY_BONUS_CROSS = 0.06
CATEGORY_ONLY_BASE = 0.5  # directions without keywords: relevance from category membership


def _word_pattern(word: str) -> str:
    w = re.escape(word)
    # light plural/inflection tolerance: model(s), network(s), class(es)
    if len(word) > 3 and word.isalpha():
        if word.endswith("s"):
            return w + "?"
        return w + "(?:s|es)?"
    return w


def is_acronym(raw: str) -> bool:
    return len(raw) >= 2 and " " not in raw and raw.replace("-", "").isupper()


@dataclass
class Keyword:
    display: str
    pattern: re.Pattern[str]
    acronym: bool  # acronyms match case-sensitively against the raw text

    def count(self, raw_text: str, norm_text: str) -> int:
        return len(self.pattern.findall(raw_text if self.acronym else norm_text))


def compile_keyword(kw: str) -> Keyword | None:
    """Acronyms typed in capitals (e.g. CLIP, RAG) match case-sensitively; everything else is
    matched on normalised text (case/hyphen/plural insensitive)."""
    raw = kw.strip()
    if not raw:
        return None
    if is_acronym(raw):
        pat = re.compile(rf"(?<![A-Za-z0-9]){re.escape(raw)}s?(?![A-Za-z0-9])")
        return Keyword(raw, pat, True)
    norm = normalize(raw)
    if not norm:
        return None
    words = norm.split(" ")
    body = r"\s?".join(_word_pattern(w) for w in words)  # "multi modal" == "multimodal"
    return Keyword(raw, re.compile(rf"(?<![a-z0-9]){body}(?![a-z0-9])"), False)


@dataclass
class CompiledDirection:
    id: int
    name: str
    weight: int
    categories: list[str]
    keywords: list[Keyword]
    exclude: list[Keyword]
    raw: dict[str, Any] = field(default_factory=dict)


def compile_direction(d: dict[str, Any]) -> CompiledDirection:
    kws = [c for c in (compile_keyword(k) for k in d.get("keywords", [])) if c]
    exc = [c for c in (compile_keyword(k) for k in d.get("exclude", [])) if c]
    return CompiledDirection(id=d["id"], name=d["name"], weight=int(d.get("weight", 3)),
                             categories=list(d.get("categories", [])), keywords=kws, exclude=exc, raw=d)


@dataclass
class RelevanceResult:
    score: float
    excluded: bool = False
    excluded_by: str | None = None
    title_hits: list[str] = field(default_factory=list)
    abstract_hits: list[str] = field(default_factory=list)
    category_match: str | None = None  # "primary" | "cross" | None


def score_paper(direction: CompiledDirection, title: str, abstract: str | None, categories: list[str]) -> RelevanceResult:
    abstract = abstract or ""
    t_norm, a_norm = normalize(title), normalize(abstract)
    for kw in direction.exclude:
        if kw.count(title, t_norm) or kw.count(abstract, a_norm):
            return RelevanceResult(score=0.0, excluded=True, excluded_by=kw.display)

    cat_match = None
    if direction.categories and categories:
        if categories[0] in direction.categories:
            cat_match = "primary"
        elif any(c in direction.categories for c in categories):
            cat_match = "cross"

    title_hits: list[str] = []
    abstract_hits: list[str] = []
    prod = 1.0
    for kw in direction.keywords:
        if kw.count(title, t_norm):
            s = 1.0
            title_hits.append(kw.display)
        else:
            n = kw.count(abstract, a_norm)
            if n == 0:
                continue
            s = min(0.8, 0.55 + 0.1 * (n - 1))
            abstract_hits.append(kw.display)
        prod *= 1.0 - KW_STRENGTH * s

    if direction.keywords:
        score = 1.0 - prod
        if score > 0 and cat_match:
            score += CATEGORY_BONUS_PRIMARY if cat_match == "primary" else CATEGORY_BONUS_CROSS
    elif cat_match:
        score = CATEGORY_ONLY_BASE + (0.15 if cat_match == "primary" else 0.0)
    else:
        score = 0.0
    return RelevanceResult(score=min(1.0, score), title_hits=title_hits, abstract_hits=abstract_hits,
                           category_match=cat_match)
