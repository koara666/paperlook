"""User settings: defaults, validation and persistence (single JSON document in `settings`)."""
from __future__ import annotations

import copy
import threading
from typing import Any

from . import db

DEFAULT_SETTINGS: dict[str, Any] = {
    "daily_count": 5,
    "window_days": 7,
    # How strongly newer papers are favoured inside the window (half-life of the freshness decay).
    "time_preference": "balanced",  # latest | balanced | relaxed
    "ranking_preset": "balanced",  # balanced | relevance | quality | fresh | custom
    "weights": {"relevance": 0.55, "quality": 0.25, "freshness": 0.20},
    "sources": {"arxiv": True, "openalex": True, "semantic_scholar": False, "pubmed": False},
    "signals": {"hf_daily": True},
    # Optional DeepSeek re-ranking of the candidate pool. Off by default: costs tokens.
    "ai_rerank": False,
    # Run the (non-AI) search automatically the first time the app is opened each day.
    "auto_fetch_on_open": False,
    "ai": {
        "provider": "deepseek",  # deepseek | gemini
        # DeepSeek (kept at the top level of "ai" for compatibility with 1.0 settings and backups)
        "base_url": "https://api.deepseek.com",
        "model": "deepseek-flash",
        "gemini": {
            "model": "gemini-3.5-flash-lite",
            "base_url": "https://generativelanguage.googleapis.com",
            # Empty = use the system proxy (Gemini is not reachable from mainland China without one).
            "proxy": "",
            # Free tier: rate-limit ourselves and use fewer, larger translation requests.
            "free_tier": True,
        },
        "thinking_for_analysis": False,
        "features": {"translate": True, "summary": True, "modules": True, "contributions": True},
        "translate_appendix": True,
        "keep_english_terms": True,
        "concurrency": 4,
    },
    "reading": {"theme": "system", "font_size": "md", "translation_view": "bilingual"},
    "onboarded": False,
}

RANKING_PRESETS: dict[str, dict[str, float]] = {
    "balanced": {"relevance": 0.55, "quality": 0.25, "freshness": 0.20},
    "relevance": {"relevance": 0.70, "quality": 0.15, "freshness": 0.15},
    "quality": {"relevance": 0.45, "quality": 0.40, "freshness": 0.15},
    "fresh": {"relevance": 0.45, "quality": 0.15, "freshness": 0.40},
}

TIME_PREFERENCE_HALF_LIFE = {"latest": 3.0, "balanced": 7.0, "relaxed": 21.0}

_lock = threading.Lock()
_KEY = "user"


def _deep_merge(base: dict, patch: dict) -> dict:
    out = copy.deepcopy(base)
    for k, v in patch.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _deep_merge(out[k], v)
        else:
            out[k] = copy.deepcopy(v)
    return out


def _clamp(v: Any, lo: float, hi: float, default: float) -> float:
    try:
        f = float(v)
    except (TypeError, ValueError):
        return default
    return max(lo, min(hi, f))


def _validate(s: dict) -> dict:
    d = DEFAULT_SETTINGS
    s["daily_count"] = int(_clamp(s.get("daily_count"), 1, 50, d["daily_count"]))
    s["window_days"] = int(_clamp(s.get("window_days"), 1, 365, d["window_days"]))
    if s.get("time_preference") not in TIME_PREFERENCE_HALF_LIFE:
        s["time_preference"] = d["time_preference"]
    preset = s.get("ranking_preset")
    if preset in RANKING_PRESETS:
        s["weights"] = dict(RANKING_PRESETS[preset])
    else:
        s["ranking_preset"] = "custom"
        w = s.get("weights") or {}
        w = {k: _clamp(w.get(k), 0.0, 1.0, d["weights"][k]) for k in ("relevance", "quality", "freshness")}
        total = sum(w.values()) or 1.0
        w = {k: v / total for k, v in w.items()} if sum(w.values()) else dict(d["weights"])
        # Relevance keeps a 20% floor (after normalising) so a paper can never be recommended
        # mostly for being new or popular; the other two share the rest proportionally.
        if w["relevance"] < 0.2:
            rest = w["quality"] + w["freshness"] or 1.0
            w = {"relevance": 0.2, "quality": 0.8 * w["quality"] / rest, "freshness": 0.8 * w["freshness"] / rest}
        s["weights"] = {k: round(v, 4) for k, v in w.items()}
    ai = s["ai"]
    ai["concurrency"] = int(_clamp(ai.get("concurrency"), 1, 8, 4))
    base_url = str(ai.get("base_url") or "").strip().rstrip("/")
    ai["base_url"] = base_url or d["ai"]["base_url"]
    ai["model"] = str(ai.get("model") or d["ai"]["model"]).strip()
    if ai.get("provider") not in ("deepseek", "gemini"):
        ai["provider"] = "deepseek"
    g, dg = ai["gemini"], d["ai"]["gemini"]
    g["model"] = str(g.get("model") or dg["model"]).strip().removeprefix("models/")
    g["base_url"] = str(g.get("base_url") or "").strip().rstrip("/") or dg["base_url"]
    g["proxy"] = str(g.get("proxy") or "").strip()
    g["free_tier"] = bool(g.get("free_tier", True))
    if s["reading"].get("theme") not in ("system", "light", "dark"):
        s["reading"]["theme"] = "system"
    if s["reading"].get("font_size") not in ("sm", "md", "lg"):
        s["reading"]["font_size"] = "md"
    if s["reading"].get("translation_view") not in ("bilingual", "zh", "en"):
        s["reading"]["translation_view"] = "bilingual"
    return s


def get_settings() -> dict[str, Any]:
    row = db.query_one("SELECT value FROM settings WHERE key = ?", (_KEY,))
    stored = db.loads(row["value"], {}) if row else {}
    return _validate(_deep_merge(DEFAULT_SETTINGS, stored or {}))


def update_settings(patch: dict[str, Any]) -> dict[str, Any]:
    with _lock:
        current = get_settings()
        # Choosing explicit weights switches the preset to "custom" unless a preset is also given.
        if "weights" in patch and "ranking_preset" not in patch:
            patch = {**patch, "ranking_preset": "custom"}
        merged = _validate(_deep_merge(current, patch))
        db.execute(
            "INSERT INTO settings(key, value) VALUES(?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (_KEY, db.dumps(merged)),
        )
        return merged


def replace_settings(value: dict[str, Any]) -> dict[str, Any]:
    """Used by backup import."""
    with _lock:
        merged = _validate(_deep_merge(DEFAULT_SETTINGS, value or {}))
        db.execute(
            "INSERT INTO settings(key, value) VALUES(?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (_KEY, db.dumps(merged)),
        )
        return merged


def half_life_days(settings: dict[str, Any]) -> float:
    return TIME_PREFERENCE_HALF_LIFE.get(settings.get("time_preference", "balanced"), 7.0)
