"""Obtain a paper's full text from legal, openly accessible locations.

Order: arXiv HTML (structured, keeps LaTeX)  ->  arXiv PDF  ->  open-access PDF link from metadata.
Nothing is scraped from publisher pages; if no open copy exists we say so clearly.
"""
from __future__ import annotations

import logging
from typing import Any

import httpx

import copy

from .. import config, db, i18n
from ..errors import AppError
from ..i18n import msg, t
from ..jobs import Job
from .arxiv_html import HtmlNotAvailable, parse_arxiv_html
from .pdf import parse_pdf

log = logging.getLogger(__name__)
MAX_PDF_BYTES = 60 * 1024 * 1024


class FulltextUnavailable(AppError):
    def __init__(self, reasons: list[dict]):
        text = t("ft.unavailable_because", reasons="; ".join(i18n.render(r) for r in reasons)) if reasons \
            else t("err.no_fulltext")
        super().__init__(text, status_code=404, code="fulltext_unavailable")
        self.reasons = reasons


_LEGACY_TITLES = {"正文前内容": "doc.front", "（无标题章节）": "doc.untitled"}


def render_doc(doc: dict[str, Any]) -> dict[str, Any]:
    """The stored document with its interface texts (source label, warnings, placeholder titles, notes) in the
    current language. Paper text itself is never changed."""
    out = dict(doc)
    out["source_label"] = i18n.render(doc.get("source_label"))
    out["warnings"] = [i18n.render(w) for w in doc.get("warnings", [])]
    sections = []
    for s in doc.get("sections", []):
        key = s.get("title_key") or _LEGACY_TITLES.get(s.get("title") or "")
        notes = any(b.get("type") == "unparsed" and b.get("note") for b in s.get("blocks", []))
        if key or notes:
            s = copy.copy(s)
            if key:
                s["title"] = t(key)
            if notes:
                s["blocks"] = [dict(b, note=i18n.render(b["note"])) if b.get("type") == "unparsed" and b.get("note")
                               else b for b in s["blocks"]]
        sections.append(s)
    out["sections"] = sections
    return out


def _client() -> httpx.Client:
    return httpx.Client(headers={"User-Agent": config.USER_AGENT}, timeout=httpx.Timeout(60.0, connect=15.0),
                        follow_redirects=True)


def get_cached(paper_id: str) -> dict[str, Any] | None:
    r = db.query_one("SELECT doc, fetched_at FROM fulltext WHERE paper_id = ?", (paper_id,))
    if not r:
        return None
    doc = db.loads(r["doc"], None)
    if doc:
        doc["fetched_at"] = r["fetched_at"]
    return doc


def _store(paper_id: str, doc: dict[str, Any]) -> None:
    db.execute(
        "INSERT INTO fulltext(paper_id, source, source_url, doc, fetched_at) VALUES(?,?,?,?,?) "
        "ON CONFLICT(paper_id) DO UPDATE SET source=excluded.source, source_url=excluded.source_url, doc=excluded.doc, "
        "fetched_at=excluded.fetched_at",
        (paper_id, doc["source"], doc["source_url"], db.dumps(doc), db.now_iso()),
    )


def _download_pdf(client: httpx.Client, url: str) -> bytes:
    with client.stream("GET", url) as resp:
        if resp.status_code in (401, 402, 403):
            raise PdfProblem(msg("ft.pdf_auth", status=resp.status_code))
        if resp.status_code >= 400:
            raise PdfProblem(msg("ft.pdf_http", status=resp.status_code))
        chunks = []
        size = 0
        for chunk in resp.iter_bytes():
            size += len(chunk)
            if size > MAX_PDF_BYTES:
                raise PdfProblem(msg("ft.pdf_too_big"))
            chunks.append(chunk)
    data = b"".join(chunks)
    if not data.startswith(b"%PDF"):
        raise PdfProblem(msg("ft.not_pdf"))
    return data


class PdfProblem(ValueError):
    def __init__(self, message: dict):
        super().__init__(str(message))
        self.message = message


def fetch(paper: dict[str, Any], job: Job | None = None) -> dict[str, Any]:
    reasons: list[dict] = []
    arxiv_id = paper.get("arxiv_id")

    def progress(msg: str) -> None:
        if job:
            job.update(message=msg, force=True)

    with _client() as client:
        if arxiv_id:
            progress(t("job.ft.html"))
            try:
                resp = client.get(f"https://arxiv.org/html/{arxiv_id}")
                if resp.status_code == 404:
                    raise HtmlNotAvailable(msg("ft.html_none"))
                if resp.status_code >= 400:
                    raise HtmlNotAvailable(f"HTTP {resp.status_code}")
                doc = parse_arxiv_html(resp.text, str(resp.url))
                _store(paper["id"], doc)
                return doc
            except HtmlNotAvailable as e:
                reasons.append(msg("ft.html_unavailable", reason=e.reason))
            except httpx.HTTPError as e:
                reasons.append(msg("ft.html_fetch_failed", error=type(e).__name__))
            except Exception as e:
                log.exception("arXiv HTML parse failed for %s", arxiv_id)
                reasons.append(msg("ft.html_parse_failed", error=type(e).__name__))

        pdf_candidates: list[tuple[str, str]] = []
        if arxiv_id:
            pdf_candidates.append((f"https://arxiv.org/pdf/{arxiv_id}", "doc.src.pdf_arxiv"))
        if paper.get("pdf_url") and "arxiv.org" not in (paper.get("pdf_url") or ""):
            pdf_candidates.append((paper["pdf_url"], "doc.src.pdf_oa"))
        for url, label in pdf_candidates:
            if job:
                job.check_cancelled()
            progress(t("job.ft.pdf_download"))
            try:
                data = _download_pdf(client, url)
                progress(t("job.ft.pdf_parse"))
                doc = parse_pdf(data, msg(label), url)
                _store(paper["id"], doc)
                return doc
            except httpx.HTTPError as e:
                reasons.append(msg("ft.pdf_download_failed", label=msg(label), error=type(e).__name__))
            except PdfProblem as e:
                reasons.append(msg("ft.pdf_problem", label=msg(label), problem=e.message))
            except ValueError as e:
                problem = e.args[0] if e.args and isinstance(e.args[0], dict) else str(e)
                reasons.append(msg("ft.pdf_problem", label=msg(label), problem=problem))
            except Exception as e:
                log.exception("PDF parse failed for %s", url)
                reasons.append(msg("ft.pdf_parse_failed", label=msg(label), error=type(e).__name__))

    if not arxiv_id and not paper.get("pdf_url"):
        reasons.append(msg("ft.no_open_copy"))
    raise FulltextUnavailable(reasons)


def ensure(paper: dict[str, Any], job: Job | None = None) -> dict[str, Any]:
    return get_cached(paper["id"]) or fetch(paper, job)
