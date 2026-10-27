"""PubMed (NCBI E-utilities): biomedical and life-science literature. Free; key optional."""
from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from datetime import date

from .. import secrets_store
from ..textutil import collapse_ws
from .base import RateLimiter, RawPaper, Source, SourceError, SourceQuery, clean_doi, code_signals, get_with_retry

EUTILS = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
limiter = RateLimiter(0.4)
_MONTHS = {m: i for i, m in enumerate(["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], 1)}


def _term(q: SourceQuery) -> str:
    kws = []
    for kw in q.keywords[:15]:
        kw = re.sub(r'["()\[\]]', " ", kw).strip()
        if kw:
            kws.append(f'"{kw}"[tiab]')
    return "(" + " OR ".join(kws) + ")"


def _date_from(el: ET.Element | None) -> tuple[date | None, bool]:
    """Returns (date, is_exact_day)."""
    if el is None:
        return None, False
    y = el.findtext("Year")
    m = el.findtext("Month")
    d = el.findtext("Day")
    if not y or not y.isdigit():
        return None, False
    month = 1
    exact = False
    if m:
        month = int(m) if m.isdigit() else _MONTHS.get(m[:3].lower(), 1)
    day = int(d) if d and d.isdigit() else 1
    exact = bool(m and d)
    try:
        return date(int(y), month, day), exact
    except ValueError:
        return None, False


def parse_efetch(xml_text: str) -> list[RawPaper]:
    root = ET.fromstring(xml_text)
    out: list[RawPaper] = []
    for art in root.findall(".//PubmedArticle"):
        pmid = art.findtext(".//MedlineCitation/PMID")
        a = art.find(".//Article")
        if a is None or not pmid:
            continue
        title = collapse_ws("".join(a.find("ArticleTitle").itertext()) if a.find("ArticleTitle") is not None else "")
        if not title:
            continue
        abstract_parts = []
        for t in a.findall(".//Abstract/AbstractText"):
            label = t.get("Label")
            txt = collapse_ws("".join(t.itertext()))
            abstract_parts.append(f"{label}: {txt}" if label else txt)
        abstract = " ".join(abstract_parts) or None
        authors = []
        for au in a.findall(".//AuthorList/Author"):
            name = " ".join(x for x in [au.findtext("ForeName"), au.findtext("LastName")] if x)
            if name:
                authors.append(name)
        # Electronic publication date is the first public appearance; fall back to issue date.
        pub, exact = _date_from(a.find("ArticleDate"))
        note = "PubMed 电子出版日期"
        if pub is None:
            pub, exact = _date_from(a.find(".//Journal/JournalIssue/PubDate"))
            note = "PubMed 期刊卷期日期"
        doi = None
        for el in a.findall("ELocationID"):
            if el.get("EIdType") == "doi":
                doi = clean_doi(el.text)
        journal = collapse_ws(a.findtext(".//Journal/Title") or "") or None
        sig = code_signals(abstract)
        out.append(RawPaper(
            source="pubmed", source_id=pmid, title=title, abstract=abstract, authors=authors[:60],
            published=pub, date_quality="exact" if exact else ("approx" if pub else "unknown"),
            date_note=note if exact else (note + "（仅精确到月/年）"),
            venue=journal, doi=doi, pmid=pmid, url=f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/", signals=sig,
        ))
    return out


class PubMedSource(Source):
    id = "pubmed"
    name = "PubMed"
    description = "美国国家医学图书馆的生物医学文献数据库，适合医学影像、生物信息等交叉方向。"
    homepage = "https://pubmed.ncbi.nlm.nih.gov"
    key_policy = "optional"
    key_secret = secrets_store.PUBMED
    key_help = "无需 Key 即可使用；NCBI API Key 可提高请求频率上限。"
    default_enabled = False
    coverage = "生物医学与生命科学期刊"

    def search(self, q: SourceQuery) -> list[RawPaper]:
        if not q.keywords:
            return []
        key = secrets_store.get_secret(secrets_store.PUBMED)
        params = {
            "db": "pubmed", "term": _term(q), "retmax": min(q.max_results, 100), "sort": "relevance",
            "datetype": "pdat", "mindate": q.date_from.strftime("%Y/%m/%d"), "maxdate": q.date_to.strftime("%Y/%m/%d"),
            "retmode": "json",
        }
        if key:
            params["api_key"] = key
        resp = get_with_retry(f"{EUTILS}/esearch.fcgi", params=params, source_name="PubMed", limiter=limiter)
        ids = (resp.json().get("esearchresult") or {}).get("idlist") or []
        if not ids:
            return []
        fparams = {"db": "pubmed", "id": ",".join(ids), "retmode": "xml"}
        if key:
            fparams["api_key"] = key
        resp = get_with_retry(f"{EUTILS}/efetch.fcgi", params=fparams, source_name="PubMed", limiter=limiter, timeout=60)
        try:
            return parse_efetch(resp.text)
        except ET.ParseError as e:
            raise SourceError(f"PubMed 返回了无法解析的数据：{e}")
