"""arXiv (export API). Free, no key, reliable v1 submission dates, abstracts and full text (HTML/PDF).
Terms of use ask for at most one request every 3 seconds."""
from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from datetime import timedelta

from ..textutil import collapse_ws, latex_typography
from .base import RateLimiter, RawPaper, Source, SourceError, SourceQuery, clean_doi, code_signals, get_with_retry, parse_date

API_URL = "https://export.arxiv.org/api/query"
NS = {"a": "http://www.w3.org/2005/Atom", "arxiv": "http://arxiv.org/schemas/atom", "os": "http://a9.com/-/spec/opensearch/1.1/"}

limiter = RateLimiter(3.1)

_SAFE_KW = re.compile(r'["()]')


def _kw_clause(kw: str) -> str:
    kw = _SAFE_KW.sub(" ", kw).strip()
    if not kw:
        return ""
    return f'ti:"{kw}" OR abs:"{kw}"'


def build_query(q: SourceQuery) -> str:
    parts: list[str] = []
    cats = [c for c in q.categories if re.fullmatch(r"[a-z\-]+(\.[A-Za-z\-]+)?", c)]
    if cats:
        parts.append("(" + " OR ".join(f"cat:{c}" for c in cats) + ")")
    kws = [c for c in (_kw_clause(k) for k in q.keywords[:20]) if c]
    if kws:
        parts.append("(" + " OR ".join(kws) + ")")
    if not parts:
        raise SourceError("研究方向缺少关键词和分类", retryable=False)
    # submittedDate is the v1 submission time (UTC) - i.e. first publication on arXiv.
    start = q.date_from.strftime("%Y%m%d") + "0000"
    end = (q.date_to + timedelta(days=1)).strftime("%Y%m%d") + "0000"
    parts.append(f"submittedDate:[{start} TO {end}]")
    return " AND ".join(parts)


def strip_version(arxiv_id: str) -> str:
    return re.sub(r"v\d+$", "", arxiv_id)


def parse_feed(xml_text: str) -> tuple[list[RawPaper], int]:
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError as e:
        raise SourceError(f"arXiv 返回了无法解析的数据：{e}")
    total_el = root.find("os:totalResults", NS)
    total = int(total_el.text) if total_el is not None and total_el.text else 0
    papers: list[RawPaper] = []
    for entry in root.findall("a:entry", NS):
        raw_id = (entry.findtext("a:id", default="", namespaces=NS) or "").strip()
        m = re.search(r"arxiv\.org/abs/(.+)$", raw_id)
        if not m:
            continue
        full_id = m.group(1)
        aid = strip_version(full_id)
        title = latex_typography(collapse_ws(entry.findtext("a:title", default="", namespaces=NS)))
        if not title or title.lower() == "error":
            continue
        abstract = latex_typography(collapse_ws(entry.findtext("a:summary", default="", namespaces=NS)))
        authors = [collapse_ws(a.findtext("a:name", default="", namespaces=NS)) for a in entry.findall("a:author", NS)]
        cats = [c.get("term") for c in entry.findall("a:category", NS) if c.get("term")]
        primary = entry.find("arxiv:primary_category", NS)
        if primary is not None and primary.get("term") in cats:
            cats.remove(primary.get("term"))
            cats.insert(0, primary.get("term"))
        comment = collapse_ws(entry.findtext("arxiv:comment", default="", namespaces=NS)) or None
        journal_ref = collapse_ws(entry.findtext("arxiv:journal_ref", default="", namespaces=NS)) or None
        doi = clean_doi(entry.findtext("arxiv:doi", default="", namespaces=NS))
        published = parse_date(entry.findtext("a:published", default="", namespaces=NS))
        updated = parse_date(entry.findtext("a:updated", default="", namespaces=NS))
        signals = code_signals(comment, abstract)
        papers.append(
            RawPaper(
                source="arxiv",
                source_id=aid,
                title=title,
                abstract=abstract or None,
                authors=[a for a in authors if a],
                published=published,
                date_quality="exact" if published else "unknown",
                date_note="arXiv 首个版本 (v1) 提交日期" if published else None,
                updated=updated,
                venue=None,
                doi=doi,
                arxiv_id=aid,
                url=f"https://arxiv.org/abs/{aid}",
                pdf_url=f"https://arxiv.org/pdf/{aid}",
                html_url=f"https://arxiv.org/html/{aid}",
                categories=cats,
                comment=comment,
                journal_ref=journal_ref,
                signals=signals,
            )
        )
    return papers, total


class ArxivSource(Source):
    id = "arxiv"
    name = "arXiv"
    description = "计算机、数学、物理等领域最主要的预印本平台。每天更新，发布日期可靠，可获取全文（HTML/PDF）。"
    homepage = "https://arxiv.org"
    key_policy = "none"
    default_enabled = True
    coverage = "预印本 · CS/AI/数学/物理/统计/电子工程"

    def search(self, q: SourceQuery) -> list[RawPaper]:
        query = build_query(q)
        out: list[RawPaper] = []
        # One request per direction for the usual 200 results: arXiv throttles by request count per IP.
        page_size = 200
        start = 0
        while start < q.max_results:
            params = {
                "search_query": query,
                "start": start,
                "max_results": min(page_size, q.max_results - start),
                # Relevance within the date window; our own ranker re-scores everything anyway.
                "sortBy": "relevance",
                "sortOrder": "descending",
            }
            try:
                # A throttled IP stays blocked well beyond a short retry window (and each refusal takes ~15 s),
                # so retry once; the engine then falls back to arXiv papers indexed by OpenAlex.
                resp = get_with_retry(API_URL, params=params, source_name="arXiv", limiter=limiter, timeout=90,
                                      attempts=2, backoff_429=5.0)
            except SourceError as e:
                if "429" in e.message:
                    raise SourceError("arXiv 暂时限制了访问频率（HTTP 429），稍后获取推荐时会自动重试") from None
                raise
            papers, total = parse_feed(resp.text)
            out.extend(papers)
            start += page_size
            if not papers or start >= total:
                break
        return out

    def fetch_by_ids(self, ids: list[str]) -> list[RawPaper]:
        if not ids:
            return []
        resp = get_with_retry(API_URL, params={"id_list": ",".join(ids), "max_results": len(ids)},
                              source_name="arXiv", limiter=limiter, timeout=60)
        papers, _ = parse_feed(resp.text)
        return papers
