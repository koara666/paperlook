"""Text normalisation helpers shared by matching, de-duplication and quote verification."""
from __future__ import annotations

import re
import unicodedata
from collections import Counter

_NON_WORD = re.compile(r"[\W_]+")  # Unicode-aware: keeps letters/digits of every script
_WS = re.compile(r"\s+")


def _fold(ch: str) -> str:
    # Accents are stripped for Latin letters only: NFKD on kana/Hangul would split が into か + ゛.
    if ord(ch) < 0x0370:
        return "".join(c for c in unicodedata.normalize("NFKD", ch) if not unicodedata.combining(c))
    return ch


def normalize(text: str | None) -> str:
    """Lowercase, strip Latin accents, unify full/half width, turn punctuation/hyphens into single spaces.
    Letters of every script (CJK, kana, Hangul, Cyrillic …) are kept."""
    if not text:
        return ""
    t = unicodedata.normalize("NFKC", text)
    t = "".join(_fold(c) for c in t).lower()
    t = _NON_WORD.sub(" ", t)
    return _WS.sub(" ", t).strip()


def title_key(title: str | None) -> str:
    """Key for duplicate detection: normalised title without spaces."""
    return normalize(title).replace(" ", "")


def key_weight(key: str) -> int:
    """Length of a title key where each CJK/kana/Hangul character counts double (they carry about a word each)."""
    return sum(2 if is_cjk_char(c) else 1 for c in key)


def collapse_ws(text: str | None) -> str:
    return _WS.sub(" ", text or "").strip()


# ---------------- scripts and languages ----------------

def is_cjk_char(c: str) -> bool:
    o = ord(c)
    return (0x4E00 <= o <= 0x9FFF or 0x3400 <= o <= 0x4DBF or 0x3040 <= o <= 0x30FF or 0xAC00 <= o <= 0xD7AF
            or 0x1100 <= o <= 0x11FF or 0x3130 <= o <= 0x318F or 0xF900 <= o <= 0xFAFF or 0x20000 <= o <= 0x2FA1F)


def has_cjk(text: str | None) -> bool:
    return any(is_cjk_char(c) for c in text or "")


def has_kana(text: str | None) -> bool:
    return any(0x3040 <= ord(c) <= 0x30FF and c not in "・ー" for c in text or "")


def has_hangul(text: str | None) -> bool:
    return any(0xAC00 <= ord(c) <= 0xD7AF for c in text or "")


_STOPWORDS = {
    "en": "the of and in to is for with on that by this we are from an as be which".split(),
    "de": "der die und das ist zu den mit von im nicht des sich auf für eine dem".split(),
    "fr": "le la les des et est une dans du pour que sur au par sont qui".split(),
    "es": "el la los las del y en que una por con para es se su".split(),
    "pt": "o os da das do dos e em que uma para com não por são".split(),
    "it": "il la che di della delle e per una sono nel con gli dei".split(),
    "ru": "и в не на что с по это как из к для от".split(),
}
_WORD = re.compile(r"[^\W\d_]+")


def detect_language(text: str | None, hint: str | None = None, title: str | None = None) -> str | None:
    """Best-guess ISO 639-1 language of a title/abstract. Scripts decide CJK; a few stop words decide the
    main Latin-script languages; `hint` (e.g. OpenAlex's language) is used when the text is inconclusive."""
    t = text or ""
    if not t.strip():
        return hint
    # A title in Chinese/Japanese/Korean script decides: English papers never have CJK titles, while CJK papers
    # often come with an English abstract.
    if title is not None and has_cjk(title):
        lang = detect_language(title)
        if lang in ("zh", "ja", "ko"):
            return lang
    counts = Counter()
    for c in t:
        o = ord(c)
        if 0xAC00 <= o <= 0xD7AF:
            counts["hangul"] += 1
        elif 0x3040 <= o <= 0x30FF and c not in "・ー":
            counts["kana"] += 1
        elif 0x4E00 <= o <= 0x9FFF or 0x3400 <= o <= 0x4DBF:
            counts["han"] += 1
        elif 0x0400 <= o <= 0x04FF:
            counts["cyrillic"] += 1
        elif 0x0E00 <= o <= 0x0E7F:
            counts["thai"] += 1
        elif 0x0600 <= o <= 0x06FF:
            counts["arabic"] += 1
        elif 0x0900 <= o <= 0x097F:
            counts["devanagari"] += 1
        elif 0x0370 <= o <= 0x03FF:
            counts["greek"] += 1
        elif c.isalpha() and o < 0x0250:
            counts["latin"] += 1
    total = sum(counts.values()) or 1
    if counts["hangul"] / total > 0.15:
        return "ko"
    if counts["kana"] and (counts["kana"] + counts["han"]) / total > 0.15:  # Chinese never uses kana
        return "ja"
    if counts["han"] / total > 0.2:
        return "zh"
    for script, lang in (("cyrillic", "ru"), ("thai", "th"), ("arabic", "ar"), ("devanagari", "hi"), ("greek", "el")):
        if counts[script] / total > 0.3:
            return hint if hint and lang == "ru" and hint in ("uk", "bg", "sr", "kk") else lang
    if counts["latin"] / total > 0.5:
        words = Counter(w.lower() for w in _WORD.findall(t[:3000]))
        scores = {lang: sum(words[w] for w in sw) for lang, sw in _STOPWORDS.items() if lang != "ru"}
        best = max(scores, key=scores.get)
        if scores[best] >= 3 and scores[best] >= 1.5 * max(v for k, v in scores.items() if k != best):
            return best
        return hint if hint and hint not in ("zh", "ja", "ko") else "en"
    return hint


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


_TAG = re.compile(r"<[^>]+>")


def strip_html(text: str | None) -> str:
    import html

    return collapse_ws(html.unescape(_TAG.sub(" ", text or "")))


def truncate(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    cut = text[:limit]
    sp = cut.rfind(" ")
    if sp > limit * 0.7:
        cut = cut[:sp]
    return cut + "…"
