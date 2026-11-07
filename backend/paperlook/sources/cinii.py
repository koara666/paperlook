"""CiNii Research (National Institute of Informatics, Japan): Japanese academic articles from J-STAGE, university
repositories (IRDB), JaLC/Crossref and the National Diet Library index. Free, no key (OpenSearch API).

Only queried for directions that use Japanese/Chinese characters in their keywords or ask for Japanese papers:
for English keywords OpenAlex already covers the same journals. CiNii also indexes general magazines (via the
National Diet Library); a record is kept only if it has a DOI or a repository/J-STAGE link, or appears in a
journal on the curated venue list, so popular-magazine articles do not become candidates."""
from __future__ import annotations

import re
from datetime import date
from typing import Any

from .. import i18n
from ..recommend.venues import venue_from_name
from ..textutil import collapse_ws, has_cjk, strip_html
from .base import RateLimiter, RawPaper, Source, SourceError, SourceQuery, clean_doi, code_signals, get_with_retry

API = "https://cir.nii.ac.jp/opensearch/articles"
limiter = RateLimiter(1.0)
_ACADEMIC_HOSTS = re.compile(r"(jstage\.jst\.go\.jp|\.repo\.nii\.ac\.jp|jxiv\.jst\.go\.jp|hdl\.handle\.net|\.ac\.jp/|"
                             r"repository|sitereports\.nabunken\.go\.jp)", re.I)
_PDF = re.compile(r"jstage\.jst\.go\.jp/article/.+/_pdf", re.I)


def wanted(q: SourceQuery) -> bool:
    return "ja" in q.languages or (not q.languages and any(has_cjk(k) for k in q.keywords)) or \
        ("zh" in q.languages and any(has_cjk(k) for k in q.keywords))


def _query(keywords: list[str]) -> str:
    kws = [k for k in keywords if has_cjk(k)] or keywords
    terms = []
    for kw in kws[:12]:
        kw = re.sub(r'["()]', " ", kw).strip()
        if kw:
            terms.append(f'"{kw}"' if " " in kw else kw)
    return " OR ".join(terms)


def _date(value: str | None) -> tuple[date | None, str]:
    v = (value or "").strip()
    m = re.match(r"^(\d{4})(?:-(\d{1,2}))?(?:-(\d{1,2}))?", v)
    if not m:
        return None, "unknown"
    y, mo, d = int(m.group(1)), int(m.group(2) or 1), int(m.group(3) or 1)
    try:
        return date(y, mo, d), "exact" if m.group(3) else "approx"
    except ValueError:
        return None, "unknown"


def parse_item(it: dict[str, Any], today: date) -> RawPaper | None:
    title = collapse_ws(it.get("title") or "")
    if not title:
        return None
    ids = it.get("dc:identifier") or []
    if isinstance(ids, dict):
        ids = [ids]
    doi = next((clean_doi(x.get("@value")) for x in ids if x.get("@type") == "cir:DOI"), None)
    hdl = next((x.get("@value") for x in ids if x.get("@type") == "cir:HDL"), None)
    uris = [x.get("@value") or "" for x in ids if x.get("@type") == "cir:URI"]
    venue = collapse_ws(it.get("prism:publicationName") or "") or None
    academic = bool(doi or hdl or any(_ACADEMIC_HOSTS.search(u) for u in uris) or venue_from_name(venue))
    if not academic:
        return None
    published, quality = _date(it.get("prism:publicationDate"))
    if published and published > today:
        quality = "approx"
    note = {"exact": "date.cinii", "approx": "date.cinii_month", "unknown": "date.unknown"}[quality]
    creators = it.get("dc:creator") or []
    if isinstance(creators, str):
        creators = [creators]
    abstract = strip_html(it.get("description")) or None
    link = ((it.get("link") or {}).get("@id")) or it.get("@id")
    crid = (it.get("@id") or "").rsplit("/", 1)[-1]
    pdf = next((u for u in uris if _PDF.search(u)), None)
    subjects = it.get("dc:subject") or []
    if isinstance(subjects, str):
        subjects = [subjects]
    return RawPaper(
        source="cinii", source_id=crid, title=title, abstract=abstract,
        authors=[collapse_ws(c) for c in creators if c][:60], published=published, date_quality=quality,
        date_note=note, venue=venue, doi=doi, url=f"https://doi.org/{doi}" if doi else link, pdf_url=pdf,
        categories=[str(s) for s in subjects[:4]], signals=code_signals(abstract),
    )


class CiNiiSource(Source):
    id = "cinii"
    name = "CiNii Research"
    description = "source.cinii.desc"
    homepage = "https://cir.nii.ac.jp"
    key_policy = "none"
    default_enabled = True
    coverage = "source.cinii.coverage"

    def search(self, q: SourceQuery) -> list[RawPaper]:
        if not q.keywords or not wanted(q):
            return []
        params = {
            "q": _query(q.keywords), "format": "json", "count": min(200, q.max_results),
            "from": q.date_from.strftime("%Y%m"), "until": q.date_to.strftime("%Y%m"),
        }
        resp = get_with_retry(API, params=params, source_name="CiNii Research", limiter=limiter, timeout=40)
        try:
            data = resp.json()
        except ValueError as e:
            raise SourceError(i18n.msg("src.bad_data", source="CiNii Research", error=str(e)), code="bad_data")
        today = date.today()
        items = data.get("items") or []
        return [p for p in (parse_item(it, today) for it in items if isinstance(it, dict)) if p]
