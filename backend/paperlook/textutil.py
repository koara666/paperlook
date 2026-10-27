"""Text normalisation helpers shared by matching, de-duplication and quote verification."""
from __future__ import annotations

import re
import unicodedata

_NON_ALNUM = re.compile(r"[^0-9a-z\u4e00-\u9fff]+")
_WS = re.compile(r"\s+")


def normalize(text: str | None) -> str:
    """Lowercase, strip accents, turn punctuation/hyphens into single spaces."""
    if not text:
        return ""
    t = unicodedata.normalize("NFKD", text)
    t = "".join(c for c in t if not unicodedata.combining(c))
    t = t.lower()
    t = _NON_ALNUM.sub(" ", t)
    return _WS.sub(" ", t).strip()


def title_key(title: str | None) -> str:
    """Key for duplicate detection: normalised title without spaces."""
    return normalize(title).replace(" ", "")


def collapse_ws(text: str | None) -> str:
    return _WS.sub(" ", text or "").strip()


_MATH_SPAN = re.compile(r"(\$[^$]*\$)")


def latex_typography(text: str | None) -> str:
    """arXiv metadata keeps LaTeX text conventions: -- / --- dashes and ``quotes''. Convert them
    outside $math$ spans so titles/abstracts read naturally."""
    if not text:
        return text or ""
    parts = _MATH_SPAN.split(text)
    for i in range(0, len(parts), 2):  # even indexes are outside math
        p = parts[i].replace("---", "—").replace("--", "–")
        p = re.sub(r"``(.*?)''", r"“\1”", p)
        parts[i] = p.replace("``", "“").replace("''", "”")
    return "".join(parts)


def strip_latex_inline(text: str) -> str:
    """Very rough LaTeX cleanup for titles/abstracts coming from arXiv metadata."""
    t = re.sub(r"\\(emph|textit|textbf|mathrm|mathbf|text)\{([^{}]*)\}", r"\2", text)
    return collapse_ws(t)


def truncate(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    cut = text[:limit]
    sp = cut.rfind(" ")
    if sp > limit * 0.7:
        cut = cut[:sp]
    return cut + "…"
