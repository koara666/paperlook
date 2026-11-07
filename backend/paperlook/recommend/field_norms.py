"""How venues compare within their field: quantiles of OpenAlex venue statistics per OpenAlex field.

Citation levels differ by an order of magnitude between fields (median 2-year mean citedness of journals:
Arts & Humanities 0.12, Mathematics 1.8, Computer Science 4.8), so a venue is scored by its percentile
within its own field, never on one global scale.

Data: for each field, the 200 journals that published the most 2024 works with that primary field
(OpenAlex group_by, collected 2026-11-08), excluding journals without citation data. Each entry is
(2-year mean citedness quantiles, h-index quantiles) at the percentiles in PERCENTILES.
"""
from __future__ import annotations

PERCENTILES = (0.10, 0.25, 0.50, 0.75, 0.90, 0.97)

FIELD_NORMS: dict[str, tuple[tuple[float, ...], tuple[float, ...]]] = {
    "11": ((0.43, 1.13, 4.03, 6.47, 8.13, 11.92), (22, 46, 135, 232, 352, 476)),  # Agricultural and Biological Sciences
    "12": ((0.00, 0.01, 0.12, 0.48, 1.77, 5.08), (7, 10, 22, 54, 117, 274)),  # Arts and Humanities
    "13": ((1.03, 3.02, 5.41, 8.16, 11.91, 19.11), (112, 164, 238, 391, 542, 854)),  # Biochemistry, Genetics and Molecular Biology
    "14": ((0.05, 0.38, 0.94, 2.15, 8.15, 14.08), (10, 16, 25, 61, 167, 344)),  # Business, Management and Accounting
    "15": ((2.46, 3.42, 5.64, 8.07, 11.75, 17.11), (53, 95, 175, 295, 399, 570)),  # Chemical Engineering
    "16": ((1.35, 3.00, 4.61, 7.22, 10.30, 16.70), (51, 96, 182, 286, 390, 489)),  # Chemistry
    "17": ((0.65, 1.71, 4.81, 7.56, 10.86, 17.25), (25, 55, 119, 200, 286, 397)),  # Computer Science
    "18": ((0.09, 0.54, 2.22, 5.99, 8.92, 12.79), (9, 25, 79, 170, 256, 380)),  # Decision Sciences
    "19": ((0.81, 2.33, 3.65, 5.85, 8.42, 13.77), (41, 85, 170, 251, 381, 620)),  # Earth and Planetary Sciences
    "20": ((0.08, 0.41, 1.61, 5.84, 8.93, 14.26), (9, 17, 59, 141, 288, 440)),  # Economics, Econometrics and Finance
    "21": ((1.41, 4.26, 6.27, 8.95, 13.53, 19.64), (68, 107, 189, 305, 399, 569)),  # Energy
    "22": ((0.66, 3.51, 5.51, 8.09, 11.30, 17.14), (44, 115, 185, 284, 384, 565)),  # Engineering
    "23": ((0.57, 3.26, 5.90, 8.42, 11.26, 14.74), (34, 106, 174, 276, 400, 600)),  # Environmental Science
    "24": ((0.71, 1.57, 3.59, 6.08, 11.03, 19.45), (50, 125, 182, 325, 507, 794)),  # Immunology and Microbiology
    "25": ((2.88, 3.98, 5.88, 8.08, 11.40, 16.24), (93, 124, 198, 298, 422, 609)),  # Materials Science
    "26": ((0.74, 1.24, 1.84, 3.23, 4.81, 7.42), (26, 45, 80, 145, 211, 409)),  # Mathematics
    "27": ((0.24, 0.57, 1.45, 3.42, 5.84, 9.91), (33, 79, 168, 274, 414, 648)),  # Medicine
    "28": ((0.58, 2.31, 4.21, 5.95, 9.71, 16.45), (56, 139, 216, 312, 432, 663)),  # Neuroscience
    "29": ((0.20, 0.61, 2.06, 4.91, 7.30, 10.90), (17, 42, 116, 220, 342, 484)),  # Nursing
    "30": ((0.47, 1.41, 3.48, 6.53, 8.97, 11.27), (23, 53, 144, 233, 355, 475)),  # Pharmacology, Toxicology and Pharmaceutics
    "31": ((0.74, 2.26, 3.83, 6.23, 10.44, 18.35), (45, 88, 153, 272, 437, 751)),  # Physics and Astronomy
    "32": ((0.10, 0.46, 2.29, 4.72, 6.97, 10.45), (17, 30, 114, 198, 318, 412)),  # Psychology
    "33": ((0.02, 0.19, 0.54, 2.02, 5.67, 8.66), (10, 14, 24, 72, 179, 400)),  # Social Sciences
    "34": ((0.12, 0.31, 0.74, 1.52, 2.93, 4.74), (10, 15, 34, 83, 146, 220)),  # Veterinary
    "35": ((0.12, 0.38, 0.99, 3.42, 5.12, 6.98), (9, 18, 52, 118, 206, 268)),  # Dentistry
    "36": ((0.08, 0.40, 1.53, 3.42, 6.29, 10.77), (17, 34, 95, 178, 288, 445)),  # Health Professions
}
GLOBAL_NORMS = ((0.19, 0.78, 3.14, 6.16, 9.24, 14.73), (17, 46, 132, 233, 370, 564))


def percentile(value: float, quantiles: tuple[float, ...]) -> float:
    """Approximate percentile of value given the quantiles at PERCENTILES (piecewise linear, clamped)."""
    pts = list(zip(quantiles, PERCENTILES))
    if value <= pts[0][0]:
        return max(0.01, PERCENTILES[0] * value / pts[0][0]) if pts[0][0] > 0 else PERCENTILES[0]
    for (v0, p0), (v1, p1) in zip(pts, pts[1:]):
        if value <= v1:
            return p0 + (p1 - p0) * ((value - v0) / (v1 - v0) if v1 > v0 else 1.0)
    return min(0.995, PERCENTILES[-1] + 0.02 * (value / pts[-1][0] - 1) if pts[-1][0] > 0 else 0.99)


def norms(field: str | None) -> tuple[tuple[float, ...], tuple[float, ...]]:
    return FIELD_NORMS.get(field or "", GLOBAL_NORMS)
