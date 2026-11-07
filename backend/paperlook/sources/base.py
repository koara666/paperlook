"""Common types for paper sources. A source turns a SourceQuery into RawPaper records.

To add a source: subclass `Source`, implement `search`, and register it in sources/__init__.py.
"""
from __future__ import annotations

import logging
import re
import threading
import time
from dataclasses import asdict, dataclass, field
from datetime import date
from typing import Any

import httpx

from .. import config, i18n

log = logging.getLogger(__name__)


class SourceError(Exception):
    """A user-presentable failure of one source (the run continues with the other sources).

    `message` is a stored message (i18n.msg) or plain text; `code` is one of
    timeout | network | rate_limit | server | refused | bad_data | config."""

    def __init__(self, message: str | dict[str, Any], *, retryable: bool = True, code: str = "error"):
        super().__init__(str(message))
        self.message = message
        self.retryable = retryable
        self.code = code

    @property
    def text(self) -> str:
        return i18n.render(self.message)


@dataclass
class SourceQuery:
    keywords: list[str]
    exclude: list[str]
    categories: list[str]
    date_from: date
    date_to: date
    max_results: int = 150
    # ISO 639-1 codes of the paper languages wanted (empty = any language).
    languages: list[str] = field(default_factory=list)


@dataclass
class RawPaper:
    source: str
    source_id: str
    title: str
    abstract: str | None = None
    authors: list[str] = field(default_factory=list)
    published: date | None = None
    # exact: day-precise first publication date; approx: only month/year known or questionable; unknown
    date_quality: str = "exact"
    date_note: str | None = None
    updated: date | None = None
    venue: str | None = None
    doi: str | None = None
    arxiv_id: str | None = None
    openalex_id: str | None = None
    s2_id: str | None = None
    pmid: str | None = None
    url: str | None = None
    pdf_url: str | None = None
    html_url: str | None = None
    categories: list[str] = field(default_factory=list)
    comment: str | None = None
    journal_ref: str | None = None
    # ISO 639-1 language of title/abstract as reported by the source (detect_language refines it).
    language: str | None = None
    signals: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["published"] = self.published.isoformat() if self.published else None
        d["updated"] = self.updated.isoformat() if self.updated else None
        return d


class Source:
    id: str = ""
    name: str = ""
    description: str = ""
    homepage: str = ""
    # "none" | "optional" | "recommended"
    key_policy: str = "none"
    key_secret: str | None = None
    key_help: str = ""
    default_enabled: bool = False
    coverage: str = ""

    def search(self, q: SourceQuery) -> list[RawPaper]:  # pragma: no cover - interface
        raise NotImplementedError

    def info(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "description": i18n.t(self.description) if self.description else "",
            "homepage": self.homepage,
            "key_policy": self.key_policy,
            "key_help": i18n.t(self.key_help) if self.key_help else "",
            "coverage": i18n.t(self.coverage) if self.coverage else "",
            "default_enabled": self.default_enabled,
        }


# ---------------- shared HTTP helpers ----------------

_client_lock = threading.Lock()
_client: httpx.Client | None = None


def http() -> httpx.Client:
    global _client
    with _client_lock:
        if _client is None:
            _client = httpx.Client(
                headers={"User-Agent": config.USER_AGENT},
                timeout=httpx.Timeout(40.0, connect=15.0),
                follow_redirects=True,
            )
        return _client


class RateLimiter:
    """Ensures a minimum interval between calls (process-wide, thread-safe)."""

    def __init__(self, min_interval: float):
        self.min_interval = min_interval
        self._lock = threading.Lock()
        self._last = 0.0

    def wait(self) -> None:
        with self._lock:
            delta = time.monotonic() - self._last
            if delta < self.min_interval:
                time.sleep(self.min_interval - delta)
            self._last = time.monotonic()


def _retry_after(resp: httpx.Response) -> float | None:
    try:
        return max(0.0, float(resp.headers.get("retry-after", "")))
    except ValueError:
        return None


def get_with_retry(url: str, *, params: Any = None, headers: dict | None = None, source_name: str,
                   limiter: RateLimiter | None = None, attempts: int = 3, timeout: float | None = None,
                   backoff_429: float = 2.0) -> httpx.Response:
    """GET with retries. A 429 waits the server's Retry-After (capped at 60 s) or backoff_429 × attempt."""
    last_exc: Exception | None = None
    wait = 0.0
    for attempt in range(attempts):
        if limiter:
            limiter.wait()
        try:
            kwargs: dict[str, Any] = {"params": params, "headers": headers}
            if timeout:
                kwargs["timeout"] = timeout
            resp = http().get(url, **kwargs)
        except httpx.TimeoutException as e:
            last_exc = SourceError(i18n.msg("src.timeout", source=source_name), code="timeout")
            log.info("%s timeout (attempt %d): %s", source_name, attempt + 1, e)
        except httpx.HTTPError as e:
            last_exc = SourceError(i18n.msg("src.network", source=source_name, error=type(e).__name__), code="network")
            log.info("%s network error (attempt %d): %s", source_name, attempt + 1, e)
        else:
            if resp.status_code == 429:
                last_exc = SourceError(i18n.msg("src.rate_limit", source=source_name), code="rate_limit")
                ra = _retry_after(resp)
                wait = min(ra, 60.0) if ra is not None else backoff_429 * (attempt + 1)
                log.info("%s 429 (attempt %d), waiting %.0fs", source_name, attempt + 1, wait)
            elif resp.status_code >= 500:
                last_exc = SourceError(i18n.msg("src.server", source=source_name, status=resp.status_code), code="server")
            elif resp.status_code >= 400:
                raise SourceError(i18n.msg("src.refused", source=source_name, status=resp.status_code),
                                  retryable=False, code="refused")
            else:
                return resp
        if attempt < attempts - 1:
            time.sleep(wait or 2.0 * (attempt + 1))
            wait = 0.0
    assert last_exc is not None
    raise last_exc


# ---------------- small parsing helpers ----------------

ARXIV_ID_RE = re.compile(r"(?:arxiv\.org/(?:abs|pdf|html)/|arxiv[:\s]|10\.48550/arxiv\.)(\d{4}\.\d{4,5}|[a-z\-]+(?:\.[A-Z]{2})?/\d{7})(?:v\d+)?", re.I)
GITHUB_RE = re.compile(r"https?://(?:www\.)?github\.com/[\w.\-]+/[\w.\-]+", re.I)
CODE_HINT_RE = re.compile(r"\b(code|implementation|project page)\b[^.]{0,60}\b(available|released|public|open[- ]source)", re.I)


def find_arxiv_id(*texts: str | None) -> str | None:
    for t in texts:
        if not t:
            continue
        m = ARXIV_ID_RE.search(t)
        if m:
            return m.group(1)
    return None


def clean_doi(doi: str | None) -> str | None:
    if not doi:
        return None
    d = doi.strip().lower()
    for prefix in ("https://doi.org/", "http://doi.org/", "https://dx.doi.org/", "doi:"):
        if d.startswith(prefix):
            d = d[len(prefix):]
    return d or None


def parse_date(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(value[:10])
    except ValueError:
        return None


def code_signals(*texts: str | None) -> dict[str, Any]:
    out: dict[str, Any] = {}
    joined = " ".join(t for t in texts if t)
    m = GITHUB_RE.search(joined)
    if m:
        out["code_url"] = m.group(0).rstrip(".,;)")
    elif CODE_HINT_RE.search(joined):
        out["code_mentioned"] = True
    return out
