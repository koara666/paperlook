"""Quality evidence for a paper - built only from verifiable signals, with explicit confidence.

Signals (weight when present):
  venue        0.55  author-stated acceptance (arXiv comment/journal-ref) or a curated flagship venue
                     (venues.py, venue_lists.py), else OpenAlex venue statistics compared within the venue's
                     paper's field (field_norms.py) - citation levels differ tenfold between fields. Venues outside
                     the CWTS core list get a lower curve (max 0.5); unscreened *and* rarely cited ones (the profile
                     of low-grade/predatory journals) count with full weight instead of being shrunk to neutral
  citations    0.25  only for papers older than 90 days (field-normalised percentile when OpenAlex has it);
                     zero citations count only after a year - before that they mostly mean "not cited yet"
  community    0.12  Hugging Face Daily Papers upvotes (ML/AI papers only)
  completeness 0.08  public code link, page count from author comments

Missing signals are *missing*, not zero. The observed score is shrunk toward a neutral 0.5 prior
in proportion to how much evidence exists:
    quality = c * observed + (1 - c) * 0.5,   c = sum of weights of present signals
so a brand-new paper with no evidence sits at 0.5 and is neither boosted nor punished.

OpenAlex counts few citations of Chinese/Japanese/Korean-language work (flagship CJK journals show ~0), so for
papers not in English low statistics are treated as missing evidence; only clearly positive evidence counts.
"""
from __future__ import annotations

import math
import re
from datetime import date
from typing import Any

from ..i18n import msg
from .field_norms import norms, percentile
from .venues import venue_from_comment, venue_from_name

WEIGHTS = {"venue": 0.55, "citations": 0.25, "community": 0.12, "completeness": 0.08}
PRIOR = 0.5
_PAGES = re.compile(r"(\d{1,3})\s*(?:pages|pp\.?|页|ページ|쪽)", re.I)
# Venues without usable citation data (CJK-language journals, new journals): 2-year citedness 0 and tiny h-index.
_NO_DATA_H = 5
# Venues outside the CWTS core set (international, peer-reviewed journals citing other work) are capped at the
# neutral value: high citation numbers of an unscreened venue are no evidence of quality (inflated or
# self-cited numbers exist), while low numbers still count against it.
NON_CORE_CAP = 0.5
_SURVEY = re.compile(r"\b(survey|review|overview|tutorial|primer|state of the art|systematic review|meta-analysis)\b|"
                     r"综述|述评|研究进展|研究现状|レビュー|総説|概説|研究動向|개관|연구 동향|리뷰", re.I)  # not 고찰: it titles ordinary studies


def _log_scale(x: float, full: float) -> float:
    return max(0.0, min(1.0, math.log1p(max(0.0, x)) / math.log1p(full)))


def is_review(paper: dict[str, Any]) -> bool:
    """Surveys, reviews and tutorials: good entry points when learning a field."""
    if (paper.get("signals") or {}).get("work_type") == "review":
        return True
    return bool(_SURVEY.search(paper.get("title") or ""))


CITATIONS_MIN_AGE = 90


def venue_stats_score(st: dict[str, Any], field: str | None = None) -> dict[str, Any] | None:
    """Field-normalised venue score from OpenAlex statistics, or None when there is no usable data.
    `field` is the paper's field when known: an economics paper in a broad or multidisciplinary venue is compared
    with economics journals, not with the venue's nominal main field."""
    two = st.get("two_year_mean_citedness")
    h = st.get("h_index")
    two_ok = two is not None and two > 0
    h_ok = h is not None and h > _NO_DATA_H
    if not two_ok and not h_ok:
        return None
    t_q, h_q = norms(field or st.get("field"))
    parts = []
    if two_ok:
        parts.append((0.4, percentile(float(two), t_q)))
    if h_ok:
        parts.append((0.6, percentile(float(h), h_q)))  # long-run standing; harder to inflate
    pct = sum(w * v for w, v in parts) / sum(w for w, _ in parts)
    if st.get("is_core") is False:  # outside the CWTS core list: screened by nobody, so the same numbers are worth less
        score = min(0.1 + 0.6 * pct, NON_CORE_CAP)
    else:
        score = 0.15 + 0.75 * pct
        if not st.get("is_core"):  # unknown
            score = min(score, NON_CORE_CAP)
    return {"score": round(score, 3), "pct": pct, "two": two if two_ok else None, "h": h if h_ok else None}


def assess(paper: dict[str, Any], today: date, venue_stats: dict[str, dict[str, Any]] | None = None) -> dict[str, Any]:
    sig = paper.get("signals") or {}
    items: list[dict[str, Any]] = []
    english = (paper.get("language") or "en") == "en"

    # --- venue ---
    vm = venue_from_comment(paper.get("comment"), paper.get("journal_ref"))
    if vm:
        key = {"accepted": "q.accepted", "published": "q.published", "workshop": "q.workshop", "findings": "q.findings"}[vm.kind]
        short = {"accepted": "q.accepted_short", "published": "q.published", "workshop": "q.workshop",
                 "findings": "q.findings"}[vm.kind]
        items.append({"key": "venue", "label": msg(key, venue=vm.display), "short": msg(short, venue=vm.display),
                      "score": vm.score, "evidence": vm.evidence, "tier": vm.tier})
    else:
        vm2 = venue_from_name(paper.get("venue"))
        if vm2:
            label = msg("q.published", venue=vm2.venue) if vm2.kind != "workshop" else msg("q.workshop", venue=vm2.venue)
            items.append({"key": "venue", "label": label, "short": label, "score": vm2.score,
                          "evidence": paper.get("venue"), "tier": vm2.tier})
        else:
            sid = sig.get("openalex_source_id")
            st = (venue_stats or {}).get(sid) if sid else None
            if st and st.get("type") in ("journal", "conference", "book series"):
                field_id = sig.get("field") or st.get("field")
                vs = venue_stats_score(st, field_id)
                # For non-English papers low numbers mostly mean "not counted", so only positive evidence counts.
                if vs and (english or vs["pct"] >= 0.5):
                    top = max(1, round((1 - vs["pct"]) * 100))
                    name = st.get("name") or paper.get("venue")
                    field = msg(f"field.{field_id}" if field_id else "field.all")
                    if vs["pct"] < 0.5:
                        label = msg("q.venue_stats_low", venue=name, field=field)
                    elif st.get("is_core"):
                        label = msg("q.venue_stats", venue=name, field=field, top=top)
                    else:  # high numbers of an unscreened venue: stated, but not counted as a plus
                        label = msg("q.venue_stats_noncore", venue=name, field=field, top=top)
                    item = {"key": "venue", "label": label, "short": msg("q.venue_short", venue=name),
                            "score": vs["score"], "evidence": "OpenAlex", "stats": {
                                      "two_year_mean_citedness": vs["two"], "h_index": vs["h"],
                                      "is_core": bool(st.get("is_core")), "field": field_id,
                                      "percentile": round(vs["pct"], 3)}}
                    if st.get("is_core") is False and vs["pct"] < 0.5:
                        # unscreened and rarely cited: the typical profile of low-grade and predatory journals -
                        # strong evidence, so it is not shrunk towards the neutral prior
                        item["weight"] = 1.0
                    items.append(item)

    # --- citations (age-normalised; meaningless for brand-new papers) ---
    pub = paper.get("published")
    age_days = None
    if pub:
        try:
            age_days = (today - date.fromisoformat(pub)).days
        except ValueError:
            age_days = None
    cites = sig.get("citations")
    if cites is not None and age_days is not None and age_days >= CITATIONS_MIN_AGE and (cites > 0 or age_days >= 365):
        pct = sig.get("citation_percentile")
        if pct is not None:
            score = float(pct)
        else:
            per_month = cites / max(1.0, age_days / 30.0)
            score = _log_scale(per_month, 5.0)
        if english or (score >= 0.5 and cites > 0):
            infl = sig.get("influential_citations")
            label = msg("q.citations_infl", n=cites, infl=infl) if infl else msg("q.citations", n=cites)
            items.append({"key": "citations", "label": label, "score": round(score, 3), "evidence": "citations"})

    # --- community attention ---
    up = sig.get("hf_upvotes")
    if up is not None and up > 0:
        items.append({"key": "community", "label": msg("q.hf", n=up), "score": round(_log_scale(up, 150.0), 3),
                      "evidence": "Hugging Face Daily Papers"})

    # --- completeness / reproducibility ---
    comp_scores = []
    comp_labels: list[Any] = []
    if sig.get("code_url") or sig.get("hf_github_repo"):
        comp_scores.append(1.0)
        comp_labels.append(msg("q.code"))
    elif sig.get("code_mentioned"):
        comp_scores.append(0.75)
        comp_labels.append(msg("q.code_promised"))
    m = _PAGES.search(paper.get("comment") or "")
    if m:
        pages = int(m.group(1))
        comp_scores.append(0.7 if pages >= 8 else (0.45 if pages >= 4 else 0.3))
        comp_labels.append(msg("q.pages", n=pages))
    if comp_scores:
        items.append({"key": "completeness", "label": msg("q.completeness", items=comp_labels),
                      "score": round(sum(comp_scores) / len(comp_scores), 3), "evidence": "comment"})

    def weight(i: dict[str, Any]) -> float:
        return i.get("weight", WEIGHTS[i["key"]])

    present_w = sum(weight(i) for i in items)
    if present_w > 0:
        observed = sum(weight(i) * i["score"] for i in items) / present_w
    else:
        observed = PRIOR
    confidence = min(1.0, present_w)
    quality = confidence * observed + (1 - confidence) * PRIOR
    return {
        "score": round(quality, 4),
        "observed": round(observed, 4),
        "confidence": round(confidence, 3),
        "signals": items,
        "insufficient": present_w < 0.2,
    }
