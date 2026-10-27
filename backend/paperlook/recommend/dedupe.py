"""Merge records of the same paper found in several sources.

Two records are the same paper if they share an arXiv id, DOI, PubMed id, or the same normalised
title. Fields are taken from the highest-priority source and gaps filled from the others.
"""
from __future__ import annotations

from typing import Any, Iterable

from ..sources import PRIORITY, RawPaper
from ..textutil import title_key

_ARXIV_DOI_PREFIX = "10.48550/arxiv."


class _UnionFind:
    def __init__(self, n: int):
        self.p = list(range(n))

    def find(self, x: int) -> int:
        while self.p[x] != x:
            self.p[x] = self.p[self.p[x]]
            x = self.p[x]
        return x

    def union(self, a: int, b: int) -> None:
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.p[rb] = ra


def identity_keys(p: dict[str, Any] | RawPaper) -> list[str]:
    get = p.get if isinstance(p, dict) else (lambda k: getattr(p, k))
    keys = []
    if get("arxiv_id"):
        keys.append("arxiv:" + get("arxiv_id").lower())
    doi = get("doi")
    if doi:
        if doi.startswith(_ARXIV_DOI_PREFIX):
            keys.append("arxiv:" + doi[len(_ARXIV_DOI_PREFIX):])
        else:
            keys.append("doi:" + doi)
    if get("pmid"):
        keys.append("pmid:" + str(get("pmid")))
    tk = title_key(get("title"))
    if len(tk) >= 24:  # short titles ("Introduction") are too ambiguous to merge on
        keys.append("title:" + tk)
    return keys


def merge(records: Iterable[RawPaper]) -> list[dict[str, Any]]:
    recs = list(records)
    uf = _UnionFind(len(recs))
    first_by_key: dict[str, int] = {}
    for i, r in enumerate(recs):
        for k in identity_keys(r):
            if k in first_by_key:
                uf.union(first_by_key[k], i)
            else:
                first_by_key[k] = i
    groups: dict[int, list[RawPaper]] = {}
    for i, r in enumerate(recs):
        groups.setdefault(uf.find(i), []).append(r)
    return [merge_group(g) for g in groups.values()]


def merge_group(group: list[RawPaper]) -> dict[str, Any]:
    group = sorted(group, key=lambda r: PRIORITY.get(r.source, 9))
    base = group[0]
    out = base.to_dict()
    out["sources"] = []
    seen_src = set()
    for r in group:
        if (r.source, r.source_id) not in seen_src:
            seen_src.add((r.source, r.source_id))
            out["sources"].append({"source": r.source, "id": r.source_id, "url": r.url})
        d = r.to_dict()
        for field in ("abstract", "venue", "openalex_id", "s2_id", "pmid", "pdf_url", "html_url", "comment",
                      "journal_ref", "arxiv_id", "url"):
            if not out.get(field) and d.get(field):
                out[field] = d[field]
        if not out.get("authors") and d.get("authors"):
            out["authors"] = d["authors"]
        # Prefer a publisher DOI over an arXiv DOI.
        if d.get("doi") and (not out.get("doi") or out["doi"].startswith(_ARXIV_DOI_PREFIX)) \
                and not d["doi"].startswith(_ARXIV_DOI_PREFIX):
            out["doi"] = d["doi"]
        # Signals: keep the strongest evidence.
        sig = out.setdefault("signals", {})
        for k, v in (d.get("signals") or {}).items():
            if k in ("citations", "influential_citations"):
                sig[k] = max(sig.get(k) or 0, v or 0)
            elif k not in sig:
                sig[k] = v
    out["published"], out["date_quality"], out["date_note"] = earliest_date(group)
    return out


def earliest_date(group: list[RawPaper]) -> tuple[str | None, str, str | None]:
    """First public appearance: earliest exact date; else earliest approximate date."""
    exact = [r for r in group if r.published and r.date_quality == "exact"]
    if exact:
        r = min(exact, key=lambda x: x.published)
        return r.published.isoformat(), "exact", r.date_note
    approx = [r for r in group if r.published]
    if approx:
        r = min(approx, key=lambda x: x.published)
        return r.published.isoformat(), r.date_quality, r.date_note
    return None, "unknown", "来源未提供可靠的发布日期"
