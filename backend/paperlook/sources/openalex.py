"""OpenAlex: open catalogue of journal and conference papers with citation counts and venue statistics.
Works without a key (small shared daily budget per IP); a free key raises the budget 10x.
We exclude repository records (arXiv etc.) because arXiv is queried directly."""
from __future__ import annotations

import re
from datetime import date
from typing import Any

from .. import db, secrets_store
from ..textutil import collapse_ws
from .base import RateLimiter, RawPaper, Source, SourceError, SourceQuery, clean_doi, code_signals, find_arxiv_id, get_with_retry, parse_date

API = "https://api.openalex.org"
limiter = RateLimiter(0.2)
SELECT = ",".join([
    "id", "doi", "title", "publication_date", "primary_location", "best_oa_location", "authorships",
    "abstract_inverted_index", "cited_by_count", "type", "fwci", "citation_normalized_percentile", "ids", "primary_topic",
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
    text = " ".join(w for _, w in positions)
    return collapse_ws(text) or None


def _search_expr(keywords: list[str]) -> str:
    terms = []
    for kw in keywords[:15]:
        kw = re.sub(r'[",:|()]', " ", kw).strip()
        if kw:
            terms.append(f'"{kw}"' if " " in kw or "-" in kw else kw)
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
    quality = "exact"
    note = "OpenAlex 记录的最早出版日期"
    if published is None:
        quality, note = "unknown", "来源未提供出版日期"
    elif published.month == 1 and published.day == 1:
        quality, note = "approx", "OpenAlex 仅提供了年份级别的日期（显示为 1 月 1 日）"
    elif published > today:
        quality, note = "approx", "记录的出版日期晚于今天（可能是期刊卷期日期）"
    authors = [((a.get("author") or {}).get("display_name") or "").strip() for a in (w.get("authorships") or [])[:60]]
    abstract = rebuild_abstract(w.get("abstract_inverted_index"))
    oa_id = (w.get("id") or "").rsplit("/", 1)[-1]
    signals: dict[str, Any] = {"citations": w.get("cited_by_count") or 0}
    if src.get("id"):
        signals["openalex_source_id"] = src["id"].rsplit("/", 1)[-1]
        signals["venue_type"] = src.get("type")
    pct = w.get("citation_normalized_percentile") or {}
    if isinstance(pct, dict) and pct.get("value") is not None:
        signals["citation_percentile"] = pct.get("value")
    if w.get("fwci") is not None:
        signals["fwci"] = w.get("fwci")
    topic = (w.get("primary_topic") or {}).get("display_name")
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
        url=(f"https://doi.org/{doi}" if doi else pl.get("landing_page_url")) or w.get("id"),
        pdf_url=oa.get("pdf_url"),
        categories=[topic] if topic else [],
        signals=signals,
    )


class OpenAlexSource(Source):
    id = "openalex"
    name = "OpenAlex"
    description = "开放学术图谱，收录期刊与会议论文，提供引用数和期刊/会议影响力统计，用于补充正式发表的论文。"
    homepage = "https://openalex.org"
    key_policy = "optional"
    key_secret = secrets_store.OPENALEX
    key_help = "无需 Key 即可使用（与同一网络共享少量每日额度）。在 openalex.org/settings/api 免费申请 Key 可获得 10 倍额度。"
    default_enabled = True
    coverage = "期刊与会议 · 全学科"

    def search(self, q: SourceQuery) -> list[RawPaper]:
        if not q.keywords:
            return []  # OpenAlex has no arXiv-style categories; keyword-less directions are arXiv-only.
        today = date.today()
        filters = [
            f"title_and_abstract.search:{_search_expr(q.keywords)}",
            f"from_publication_date:{q.date_from.isoformat()}",
            f"to_publication_date:{min(q.date_to, today).isoformat()}",
            "primary_location.source.type:!repository",
            "type:article|preprint|review|book-chapter",
        ]
        params = {
            "filter": ",".join(filters),
            "per_page": min(100, q.max_results),
            "sort": "relevance_score:desc",
            "select": SELECT,
        }
        resp = get_with_retry(f"{API}/works", params=params, headers=_headers(), source_name="OpenAlex", limiter=limiter)
        data = resp.json()
        if "results" not in data:
            raise SourceError(f"OpenAlex 返回异常：{data.get('message') or data.get('error') or '未知错误'}")
        out = []
        for w in data["results"]:
            p = parse_work(w, today)
            if p:
                out.append(p)
        return out


def fetch_source_stats(source_ids: list[str]) -> dict[str, dict[str, Any]]:
    """Venue statistics (2-year mean citedness ~ impact factor, h-index). Cached 30 days."""
    result: dict[str, dict[str, Any]] = {}
    missing: list[str] = []
    for sid in set(source_ids):
        cached = db.cache_get(f"oa_source:{sid}", max_age_seconds=30 * 86400)
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
                        "select": "id,display_name,type,summary_stats,host_organization_name"},
                headers=_headers(), source_name="OpenAlex", limiter=limiter, attempts=2,
            )
        except SourceError:
            break
        for s in resp.json().get("results", []):
            sid = s["id"].rsplit("/", 1)[-1]
            stats = s.get("summary_stats") or {}
            info = {
                "name": s.get("display_name"),
                "type": s.get("type"),
                "two_year_mean_citedness": stats.get("2yr_mean_citedness"),
                "h_index": stats.get("h_index"),
            }
            result[sid] = info
            db.cache_set(f"oa_source:{sid}", info)
    return result
