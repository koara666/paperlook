"""Obtain a paper's full text from legal, openly accessible locations.

Order: arXiv HTML (structured, keeps LaTeX)  ->  arXiv PDF  ->  open-access PDF link from metadata.
Nothing is scraped from publisher pages; if no open copy exists we say so clearly.
"""
from __future__ import annotations

import logging
from typing import Any

import httpx

from .. import config, db
from ..errors import AppError
from ..jobs import Job
from .arxiv_html import HtmlNotAvailable, parse_arxiv_html
from .pdf import parse_pdf

log = logging.getLogger(__name__)
MAX_PDF_BYTES = 60 * 1024 * 1024


class FulltextUnavailable(AppError):
    def __init__(self, reasons: list[str]):
        msg = "无法获取全文：" + "；".join(reasons) if reasons else "无法获取全文"
        super().__init__(msg, status_code=404, code="fulltext_unavailable")
        self.reasons = reasons


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
            raise ValueError(f"PDF 链接需要授权访问（HTTP {resp.status_code}）")
        if resp.status_code >= 400:
            raise ValueError(f"PDF 下载失败（HTTP {resp.status_code}）")
        chunks = []
        size = 0
        for chunk in resp.iter_bytes():
            size += len(chunk)
            if size > MAX_PDF_BYTES:
                raise ValueError("PDF 文件过大（超过 60MB）")
            chunks.append(chunk)
    data = b"".join(chunks)
    if not data.startswith(b"%PDF"):
        raise ValueError("该链接返回的不是 PDF 文件（可能是出版商页面或需要订阅）")
    return data


def fetch(paper: dict[str, Any], job: Job | None = None) -> dict[str, Any]:
    reasons: list[str] = []
    arxiv_id = paper.get("arxiv_id")

    def progress(msg: str) -> None:
        if job:
            job.update(message=msg, force=True)

    with _client() as client:
        if arxiv_id:
            progress("正在获取 arXiv HTML 全文…")
            try:
                resp = client.get(f"https://arxiv.org/html/{arxiv_id}")
                if resp.status_code == 404:
                    raise HtmlNotAvailable("作者未提供 HTML 版本")
                if resp.status_code >= 400:
                    raise HtmlNotAvailable(f"HTTP {resp.status_code}")
                doc = parse_arxiv_html(resp.text, str(resp.url))
                _store(paper["id"], doc)
                return doc
            except HtmlNotAvailable as e:
                reasons.append(f"arXiv HTML 版本不可用（{e}）")
            except httpx.HTTPError as e:
                reasons.append(f"arXiv HTML 获取失败（{type(e).__name__}）")
            except Exception as e:
                log.exception("arXiv HTML parse failed for %s", arxiv_id)
                reasons.append(f"arXiv HTML 解析失败（{type(e).__name__}）")

        pdf_candidates: list[tuple[str, str]] = []
        if arxiv_id:
            pdf_candidates.append((f"https://arxiv.org/pdf/{arxiv_id}", "PDF（arXiv）"))
        if paper.get("pdf_url") and "arxiv.org" not in (paper.get("pdf_url") or ""):
            pdf_candidates.append((paper["pdf_url"], "PDF（开放获取）"))
        for url, label in pdf_candidates:
            if job:
                job.check_cancelled()
            progress("正在下载 PDF…")
            try:
                data = _download_pdf(client, url)
                progress("正在解析 PDF（较长论文可能需要半分钟）…")
                doc = parse_pdf(data, label, url)
                _store(paper["id"], doc)
                return doc
            except httpx.HTTPError as e:
                reasons.append(f"{label} 下载失败（{type(e).__name__}）")
            except ValueError as e:
                reasons.append(f"{label}：{e}")
            except Exception as e:
                log.exception("PDF parse failed for %s", url)
                reasons.append(f"{label} 解析失败（{type(e).__name__}）")

    if not arxiv_id and not paper.get("pdf_url"):
        reasons.append("该论文没有可合法访问的开放全文（可能需要通过出版商订阅阅读）")
    raise FulltextUnavailable(reasons)


def ensure(paper: dict[str, Any], job: Job | None = None) -> dict[str, Any]:
    return get_cached(paper["id"]) or fetch(paper, job)
