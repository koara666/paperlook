"""Semantic Scholar Academic Graph. Good venue/citation metadata across CS.
Anonymous access shares a global rate limit and is frequently refused (HTTP 429), so a free
API key is recommended; the source is disabled by default."""
from __future__ import annotations

import re
from datetime import date
from typing import Any

from .. import i18n, secrets_store
from ..textutil import collapse_ws
from .base import RateLimiter, RawPaper, Source, SourceError, SourceQuery, clean_doi, code_signals, get_with_retry, parse_date

API = "https://api.semanticscholar.org/graph/v1"
limiter = RateLimiter(1.1)
FIELDS = ("paperId,title,abstract,authors,venue,publicationVenue,publicationDate,year,externalIds,"
          "citationCount,influentialCitationCount,openAccessPdf,url,fieldsOfStudy")


def _query(keywords: list[str]) -> str:
    terms = []
    for kw in keywords[:15]:
        kw = re.sub(r'["|+\-()~*]', " ", kw).strip()
        kw = " ".join(kw.split())
        if kw:
            terms.append(f'"{kw}"' if " " in kw else kw)
    return " | ".join(terms)


def parse_item(it: dict[str, Any], today: date) -> RawPaper | None:
    title = collapse_ws(it.get("title") or "")
    if not title:
        return None
    ext = it.get("externalIds") or {}
    published = parse_date(it.get("publicationDate"))
    quality, note = "exact", "date.s2"
    if published is None:
        quality, note = "unknown", "date.year_only"
    elif published > today:
        quality, note = "approx", "date.future"
    venue = it.get("venue") or ((it.get("publicationVenue") or {}).get("name"))
    arxiv_id = ext.get("ArXiv")
    doi = clean_doi(ext.get("DOI"))
    abstract = collapse_ws(it.get("abstract") or "") or None
    pdf = (it.get("openAccessPdf") or {}).get("url") or None
    signals: dict[str, Any] = {
        "citations": it.get("citationCount") or 0,
        "influential_citations": it.get("influentialCitationCount") or 0,
    }
    signals.update(code_signals(abstract))
    return RawPaper(
        source="semantic_scholar",
        source_id=it["paperId"],
        title=title,
        abstract=abstract,
        authors=[a.get("name", "") for a in (it.get("authors") or [])[:60] if a.get("name")],
        published=published,
        date_quality=quality,
        date_note=note,
        venue=venue or None,
        doi=doi,
        arxiv_id=arxiv_id,
        s2_id=it["paperId"],
        pmid=ext.get("PubMed"),
        url=it.get("url"),
        pdf_url=pdf,
        categories=list(it.get("fieldsOfStudy") or [])[:3],
        signals=signals,
    )


class SemanticScholarSource(Source):
    id = "semantic_scholar"
    name = "Semantic Scholar"
    description = "source.s2.desc"
    homepage = "https://www.semanticscholar.org"
    key_policy = "recommended"
    key_secret = secrets_store.SEMANTIC_SCHOLAR
    key_help = "source.s2.key_help"
    default_enabled = False
    coverage = "source.s2.coverage"

    def search(self, q: SourceQuery) -> list[RawPaper]:
        if not q.keywords:
            return []
        key = secrets_store.get_secret(secrets_store.SEMANTIC_SCHOLAR)
        headers = {"x-api-key": key} if key else {}
        params = {
            "query": _query(q.keywords),
            "fields": FIELDS,
            "publicationDateOrYear": f"{q.date_from.isoformat()}:{q.date_to.isoformat()}",
            "sort": "publicationDate:desc",
        }
        try:
            resp = get_with_retry(f"{API}/paper/search/bulk", params=params, headers=headers,
                                  source_name="Semantic Scholar", limiter=limiter, attempts=2 if not key else 3)
        except SourceError as e:
            if e.code == "rate_limit" and not key:
                raise SourceError(i18n.msg("src.s2_anonymous"), code="rate_limit")
            raise
        today = date.today()
        out = []
        for it in (resp.json().get("data") or [])[: q.max_results]:
            p = parse_item(it, today)
            if p:
                out.append(p)
        return out
