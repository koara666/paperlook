"""Interface language for every user-visible string the backend produces (errors, progress messages,
recommendation reasons, quality labels, source descriptions …).

    t("err.no_directions")                 -> text in the current interface language
    msg("rec.match", direction="CV")       -> {"$t": "rec.match", "p": {...}} stored in the database and
                                              rendered when it is served, so switching the language also
                                              changes text that was produced earlier
    render(obj)                            -> resolves stored messages inside dicts/lists for an API response

The catalog lives in i18n_catalog.py (every key has zh/en/ja/ko; test_i18n.py checks placeholders match).
Text stored by versions before 1.3 is plain Chinese; render() maps the fixed sentences and the templates
marked as persisted back to their key, so old recommendations follow the language too.
"""
from __future__ import annotations

import contextvars
import os
import re
import sys
import threading
import time
from typing import Any

from .i18n_catalog import M, PERSISTED

LANGS = ("zh", "en", "ja", "ko")
# Placeholders a translation may use although the Chinese text does not (test_i18n.py).
EXTRA_PARAMS = {"ai.gm.quota_daily": {"hour_next"}}
FALLBACK = "en"
LANG_NAMES = {"zh": "简体中文", "en": "English", "ja": "日本語", "ko": "한국어"}
# Language names as written inside prompts / messages of each language.
LANG_LABEL = {
    "zh": {"zh": "中文", "en": "英文", "ja": "日文", "ko": "韩文"},
    "en": {"zh": "Chinese", "en": "English", "ja": "Japanese", "ko": "Korean"},
    "ja": {"zh": "中国語", "en": "英語", "ja": "日本語", "ko": "韓国語"},
    "ko": {"zh": "중국어", "en": "영어", "ja": "일본어", "ko": "한국어"},
}

_override: contextvars.ContextVar[str | None] = contextvars.ContextVar("paperlook_lang", default=None)
_cache_lock = threading.Lock()
_cache: tuple[float, str, str] | None = None  # (time, db path, lang)


def system_language() -> str:
    """Interface language of the operating system (used until the user picks one)."""
    try:
        if sys.platform == "win32":
            import ctypes

            primary = ctypes.windll.kernel32.GetUserDefaultUILanguage() & 0x3FF  # type: ignore[attr-defined]
            return {0x04: "zh", 0x11: "ja", 0x12: "ko"}.get(primary, "en")
    except Exception:  # pragma: no cover - platform specific
        pass
    for var in ("LC_ALL", "LC_MESSAGES", "LANG", "LANGUAGE"):
        v = (os.environ.get(var) or "").lower()
        if v and v not in ("c", "posix", "c.utf-8"):
            code = v[:2]
            return code if code in LANGS else "en"
    return "en"


def normalize_lang(value: Any) -> str | None:
    v = str(value or "").strip().lower().replace("_", "-")
    if not v:
        return None
    if v.startswith("zh"):
        return "zh"
    code = v[:2]
    return code if code in LANGS else None


def invalidate() -> None:
    global _cache
    with _cache_lock:
        _cache = None


def current() -> str:
    """The interface language: an explicit override (tests, a request), else the user's setting."""
    o = _override.get()
    if o:
        return o
    global _cache
    from . import db, settings_store

    path = str(db._db_path)
    with _cache_lock:
        if _cache and _cache[1] == path and time.monotonic() - _cache[0] < 5:
            return _cache[2]
    lang = normalize_lang(settings_store.get_settings().get("language")) or system_language()
    with _cache_lock:
        _cache = (time.monotonic(), path, lang)
    return lang


class use:
    """Context manager forcing a language: `with i18n.use("ja"): ...`."""

    def __init__(self, lang: str):
        self.lang = lang if lang in LANGS else FALLBACK
        self._token: contextvars.Token | None = None

    def __enter__(self) -> str:
        self._token = _override.set(self.lang)
        return self.lang

    def __exit__(self, *exc: Any) -> None:
        if self._token is not None:
            _override.reset(self._token)


class _Params(dict):
    def __missing__(self, key: str) -> str:  # a missing parameter never breaks a message
        return "{" + key + "}"


def t(key: str, lang: str | None = None, **params: Any) -> str:
    lang = lang or current()
    entry = M.get(key)
    if entry is None:
        return key
    text = entry.get(lang) or entry.get(FALLBACK) or entry.get("zh") or key
    if not params:
        return text
    rendered = {k: join(v, lang) if isinstance(v, list) else render(v, lang) for k, v in params.items()}
    if lang == "en" and "|" in text:  # "{n} paper|{n} papers": the count is n (or window / found)
        one, _, other = text.partition("|")
        count = next((rendered[k] for k in ("n", "window", "found") if k in rendered), None)
        text = one if str(count) == "1" else other
    return text.format_map(_Params(rendered))


def msg(key: str, **params: Any) -> dict[str, Any]:
    """A message to store and render later in whatever language is current then."""
    return {"$t": key, "p": params} if params else {"$t": key}


def is_msg(v: Any) -> bool:
    return isinstance(v, dict) and "$t" in v


def join(parts: list[Any], lang: str | None = None) -> str:
    """Join list items with the language's enumeration comma."""
    lang = lang or current()
    sep = {"zh": "、", "ja": "、", "en": ", ", "ko": ", "}[lang]
    return sep.join(str(render(p, lang)) for p in parts)


def render(obj: Any, lang: str | None = None) -> Any:
    """Resolve stored messages (and legacy Chinese sentences) anywhere inside a JSON-like value."""
    if isinstance(obj, str):
        return obj if (lang or current()) == "zh" else _legacy(obj, lang or current())
    if isinstance(obj, dict):
        if "$t" in obj:
            return t(obj["$t"], lang or current(), **(obj.get("p") or {}))
        return {k: render(v, lang) for k, v in obj.items()}
    if isinstance(obj, list):
        return [render(v, lang) for v in obj]
    return obj


def render_key(value: Any, lang: str | None = None) -> Any:
    """A stored catalog key ("date.arxiv_v1"), stored message, or legacy Chinese text -> display text."""
    if isinstance(value, str) and value in M:
        return t(value, lang)
    return render(value, lang)


# ---- text from versions before 1.3 (stored as plain Chinese) ----

_legacy_fixed: dict[str, str] | None = None
_legacy_templates: list[tuple[re.Pattern[str], str]] | None = None


def _build_legacy() -> None:
    global _legacy_fixed, _legacy_templates
    fixed: dict[str, str] = {}
    templates: list[tuple[re.Pattern[str], str]] = []
    for key in PERSISTED:
        zh = M[key]["zh"]
        if "{" not in zh:
            fixed[zh] = key
            continue
        parts = re.split(r"\{(\w+)\}", zh)
        rx = ""
        for i, part in enumerate(parts):
            rx += re.escape(part) if i % 2 == 0 else f"(?P<{part}>.+?)"
        templates.append((re.compile("^" + rx + "$", re.S), key))
    _legacy_fixed, _legacy_templates = fixed, templates


def _legacy(text: str, lang: str) -> str:
    if not text or not any("一" <= c <= "鿿" for c in text[:40]):
        return text
    if _legacy_fixed is None:
        _build_legacy()
    key = _legacy_fixed.get(text)  # type: ignore[union-attr]
    if key:
        return t(key, lang)
    for rx, key in _legacy_templates:  # type: ignore[union-attr]
        m = rx.match(text)
        if m:
            return t(key, lang, **m.groupdict())
    return text
