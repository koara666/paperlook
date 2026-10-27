"""Time weighting.

The time *window* (settings.window_days) decides which papers are candidates at all.
The freshness *score* only orders candidates inside the window:

    freshness(age) = FLOOR + (1 - FLOOR) * 0.5 ** (age / half_life)

- age 0 -> 1.0; one half-life -> 0.6; never below FLOOR (0.2), so an older but highly relevant,
  high-quality paper can still win.
- half-life comes from the user's "time preference" (latest 3d / balanced 7d / relaxed 21d).
- approximate dates are discounted (x0.85); unknown dates get the floor value.
"""
from __future__ import annotations

from datetime import date

FLOOR = 0.2
APPROX_FACTOR = 0.85


def age_days(published: str | None, today: date) -> int | None:
    if not published:
        return None
    try:
        return max(0, (today - date.fromisoformat(published)).days)
    except ValueError:
        return None


def freshness(published: str | None, date_quality: str | None, today: date, half_life: float) -> float:
    age = age_days(published, today)
    if age is None or date_quality == "unknown":
        return FLOOR
    f = FLOOR + (1 - FLOOR) * 0.5 ** (age / max(0.5, half_life))
    if date_quality == "approx":
        f *= APPROX_FACTOR
    return round(f, 4)
