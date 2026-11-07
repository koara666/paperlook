"""OpenAlex: open catalogue of journal and conference papers in every discipline and language, with citation
counts and venue statistics. Works without a key (small shared daily budget per IP); a free key raises it.

Per direction two searches run: one over all venues and one restricted to CWTS "core" journals, so the
established journals of a field are not crowded out by high-volume low-impact venues. arXiv is queried
directly and therefore excluded here, except as a fallback when the arXiv API refuses us (arxiv_only=True):
OpenAlex's dates for arXiv works match arXiv v1 dates, but it indexes new arXiv papers a few days late.
Other preprint servers and working-paper series (bioRxiv, SSRN, NBER, university repositories …) are kept:
in many fields that is where new work appears. Zenodo is excluded: anything can be uploaded there."""
from __future__ import annotations

import re
from datetime import date
from typing import Any

from .. import db, i18n, secrets_store
from ..recommend.venues import venue_from_name
from ..textutil import collapse_ws, has_cjk
from .base import RateLimiter, RawPaper, Source, SourceError, SourceQuery, clean_doi, code_signals, find_arxiv_id, get_with_retry, parse_date

API = "https://api.openalex.org"
ARXIV_SOURCE = "S4306400194"  # "arXiv (Cornell University)"
# arXiv (fetched directly); Zenodo and Figshare accept any upload without moderation.
EXCLUDED_SOURCES = (ARXIV_SOURCE, "S4306400562", "S4377196282")
TYPES = "article|preprint|review|book-chapter|report"
CORE_RESULTS = 50
limiter = RateLimiter(0.2)
SELECT = ",".join([
    "id", "doi", "title", "publication_date", "primary_location", "best_oa_location", "authorships",
    "abstract_inverted_index", "cited_by_count", "type", "fwci", "citation_normalized_percentile", "ids",
    "primary_topic", "language",
])


def _headers() -> dict[str, str]:
    key = secrets_store.get_secret(secrets_store.OPENALEX)
    # Header (not query param) so the key never appears in URLs or logs.
    return {"Authorization": f"Bearer {key}"} if key else {}


def rebuild_abstract(inv: dict[str, list[int]] | None) -> str | None:
    if not inv:
        return None
    positions: list[tuple[int, str]] = []
    for word, idxs in inv.items():
        for i in idxs:
            positions.append((i, word))
    positions.sort()
    # Tokens are split on whitespace, so CJK text arrives in long runs: join two CJK runs without a space.
    text = ""
    for _, w in positions:
        text += w if text and has_cjk(text[-1]) and has_cjk(w[0]) else (" " + w if text else w)
    return collapse_ws(text) or None


def _search_expr(keywords: list[str]) -> str:
    terms = []
    for kw in keywords[:15]:
        kw = re.sub(r'[",:|()!]', " ", kw).strip()
        if kw:
            # CJK words have no spaces to tokenise on: they only match reliably as quoted phrases.
            terms.append(f'"{kw}"' if " " in kw or "-" in kw or not kw.isascii() else kw)
    return " OR ".join(terms)


def parse_work(w: dict[str, Any], today: date) -> RawPaper | None:
    title = collapse_ws(w.get("title") or "")
    if not title:
        return None
    pl = w.get("primary_location") or {}
    src = pl.get("source") or {}
    oa = w.get("best_oa_location") or {}
    doi = clean_doi(w.get("doi"))
    arxiv_id = find_arxiv_id(doi, oa.get("landing_page_url"), oa.get("pdf_url"), pl.get("landing_page_url"))
    published = parse_date(w.get("publication_date"))
    quality, note = "exact", "date.openalex"
    if published is None:
        quality, note = "unknown", "date.unknown"
    elif published.month == 1 and published.day == 1:
        quality, note = "approx", "date.openalex_year"
    elif published > today:
        quality, note = "approx", "date.future"
    authors = [((a.get("author") or {}).get("display_name") or "").strip() for a in (w.get("authorships") or [])[:60]]
    abstract = rebuild_abstract(w.get("abstract_inverted_index"))
    oa_id = (w.get("id") or "").rsplit("/", 1)[-1]
    signals: dict[str, Any] = {"citations": w.get("cited_by_count") or 0}
    on_arxiv = (src.get("id") or "").endswith("/" + ARXIV_SOURCE)
    if on_arxiv:
        # An arXiv preprint (fallback search): arXiv is not a venue, so no venue name or venue statistics.
        src = {}
        if published and quality == "exact":
            note = "date.arxiv_openalex"
    if src.get("id"):
        signals["openalex_source_id"] = src["id"].rsplit("/", 1)[-1]
        signals["venue_type"] = src.get("type")
    if w.get("type"):
        signals["work_type"] = w["type"]
    pct = w.get("citation_normalized_percentile") or {}
    if isinstance(pct, dict) and pct.get("value") is not None:
        signals["citation_percentile"] = pct.get("value")
    if w.get("fwci") is not None:
        signals["fwci"] = w.get("fwci")
    topic = w.get("primary_topic") or {}
    if (topic.get("field") or {}).get("id"):
        signals["field"] = topic["field"]["id"].rsplit("/", 1)[-1]
    signals.update(code_signals(abstract))
    return RawPaper(
        source="openalex",
        source_id=oa_id,
        title=title,
        abstract=abstract,
        authors=[a for a in authors if a],
        published=published,
        date_quality=quality,
        date_note=note,
        venue=src.get("display_name"),
        doi=doi,
        arxiv_id=arxiv_id,
        openalex_id=oa_id,
        pmid=((w.get("ids") or {}).get("pmid") or "").rsplit("/", 1)[-1] or None,
        url=f"https://arxiv.org/abs/{arxiv_id}" if on_arxiv and arxiv_id
        else (f"https://doi.org/{doi}" if doi else pl.get("landing_page_url")) or w.get("id"),
        pdf_url=f"https://arxiv.org/pdf/{arxiv_id}" if on_arxiv and arxiv_id else oa.get("pdf_url"),
        html_url=f"https://arxiv.org/html/{arxiv_id}" if on_arxiv and arxiv_id else None,
        categories=[topic["display_name"]] if topic.get("display_name") else [],
        language=w.get("language"),
        signals=signals,
    )


class OpenAlexSource(Source):
    id = "openalex"
    name = "OpenAlex"
    description = "source.openalex.desc"
    homepage = "https://openalex.org"
    key_policy = "optional"
    key_secret = secrets_store.OPENALEX
    key_help = "source.openalex.key_help"
    default_enabled = True
    coverage = "source.openalex.coverage"

    def _query(self, q: SourceQuery, filters: list[str], per_page: int) -> list[RawPaper]:
        params = {"filter": ",".join(filters), "per_page": min(100, per_page), "sort": "relevance_score:desc",
                  "select": SELECT}
        resp = get_with_retry(f"{API}/works", params=params, headers=_headers(), source_name="OpenAlex", limiter=limiter)
        data = resp.json()
        if "results" not in data:
            raise SourceError(i18n.msg("src.bad_data", source="OpenAlex", error=str(data.get("message") or data.get("error") or "?")), code="bad_data")
        today = date.today()
        out = []
        for w in data["results"]:
            p = parse_work(w, today)
            # "report" covers working-paper series (NBER …) but also annual reports, minutes and grey literature:
            # keep reports only from curated series.
            if p and (w.get("type") != "report" or venue_from_name(p.venue)):
                out.append(p)
        return out

    def search(self, q: SourceQuery, arxiv_only: bool = False) -> list[RawPaper]:
        if not q.keywords:
            return []  # OpenAlex has no arXiv-style categories; keyword-less directions are arXiv-only.
        today = date.today()
        base = [
            f"title_and_abstract.search:{_search_expr(q.keywords)}",
            f"from_publication_date:{q.date_from.isoformat()}",
            f"to_publication_date:{min(q.date_to, today).isoformat()}",
        ]
        if q.languages:
            base.append("language:" + "|".join(q.languages))
        if arxiv_only:
            return self._query(q, base + [f"primary_location.source.id:{ARXIV_SOURCE}"], q.max_results)
        base += [f"primary_location.source.id:!{s}" for s in EXCLUDED_SOURCES] + [f"type:{TYPES}"]
        out = self._query(q, base, q.max_results)
        # Core journals are almost all English-language; skip that search when only CJK papers are wanted.
        wants_english = not q.languages or "en" in q.languages
        if wants_english and any(k.isascii() for k in q.keywords):
            seen = {p.source_id for p in out}
            try:
                core = self._query(q, base + ["primary_location.source.is_core:true"], CORE_RESULTS)
            except SourceError:
                core = []  # the main search already succeeded
            out += [p for p in core if p.source_id not in seen]
        return out


def fetch_source_stats(source_ids: list[str]) -> dict[str, dict[str, Any]]:
    """Venue statistics (2-year mean citedness ~ impact factor, h-index, core-journal flag, main field).
    Cached 30 days."""
    result: dict[str, dict[str, Any]] = {}
    missing: list[str] = []
    for sid in set(source_ids):
        cached = db.cache_get(f"oa_source2:{sid}", max_age_seconds=30 * 86400)
        if cached is not None:
            result[sid] = cached
        else:
            missing.append(sid)
    for i in range(0, len(missing), 50):
        chunk = missing[i:i + 50]
        try:
            resp = get_with_retry(
                f"{API}/sources",
                params={"filter": "openalex:" + "|".join(chunk), "per_page": 50,
                        "select": "id,display_name,type,summary_stats,host_organization_name,is_core,topics,works_count"},
                headers=_headers(), source_name="OpenAlex", limiter=limiter, attempts=2,
            )
        except SourceError:
            break
        for s in resp.json().get("results", []):
            sid = s["id"].rsplit("/", 1)[-1]
            stats = s.get("summary_stats") or {}
            topics = s.get("topics") or []
            field = ((topics[0].get("field") or {}).get("id") or "").rsplit("/", 1)[-1] if topics else ""
            info = {
                "name": s.get("display_name"),
                "type": s.get("type"),
                "two_year_mean_citedness": stats.get("2yr_mean_citedness"),
                "h_index": stats.get("h_index"),
                "is_core": bool(s.get("is_core")),
                "field": field or None,
                "works_count": s.get("works_count"),
            }
            result[sid] = info
            db.cache_set(f"oa_source2:{sid}", info)
    return result
