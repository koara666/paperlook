"""Quality evidence for a paper - built only from verifiable signals, with explicit confidence.

Signals (weight when present):
  venue       0.40  author-stated acceptance (arXiv comment/journal-ref), curated venue list,
                    or OpenAlex venue statistics (2-year mean citedness, ~impact factor)
  citations   0.25  only for papers older than 30 days (age-normalised); new papers get NO signal
  community   0.20  Hugging Face Daily Papers upvotes (ML/AI papers only)
  completeness 0.15 public code link, page count from author comments

Missing signals are *missing*, not zero. The observed score is shrunk toward a neutral 0.5 prior
in proportion to how much evidence exists:
    quality = c * observed + (1 - c) * 0.5,   c = sum of weights of present signals
so a brand-new paper with no evidence sits at 0.5 and is neither boosted nor punished.
"""
from __future__ import annotations

import math
import re
from datetime import date
from typing import Any

from .venues import venue_from_comment, venue_from_name

WEIGHTS = {"venue": 0.40, "citations": 0.25, "community": 0.20, "completeness": 0.15}
PRIOR = 0.5
_PAGES = re.compile(r"(\d{1,3})\s*(?:pages|pp\.?|页)", re.I)


def _log_scale(x: float, full: float) -> float:
    return max(0.0, min(1.0, math.log1p(max(0.0, x)) / math.log1p(full)))


def assess(paper: dict[str, Any], today: date, venue_stats: dict[str, dict[str, Any]] | None = None) -> dict[str, Any]:
    sig = paper.get("signals") or {}
    items: list[dict[str, Any]] = []

    # --- venue ---
    vm = venue_from_comment(paper.get("comment"), paper.get("journal_ref"))
    if vm:
        label = {"accepted": f"作者注明：已被 {vm.display} 接收",
                 "published": f"发表于 {vm.display}",
                 "workshop": f"作者注明：{vm.display} Workshop 论文",
                 "findings": f"作者注明：{vm.display} Findings"}[vm.kind]
        items.append({"key": "venue", "label": label, "score": vm.score, "evidence": vm.evidence})
    else:
        vm2 = venue_from_name(paper.get("venue"))
        if vm2:
            label = f"发表于 {vm2.venue}" if vm2.kind != "workshop" else f"{vm2.venue} Workshop"
            items.append({"key": "venue", "label": label, "score": vm2.score, "evidence": paper.get("venue")})
        else:
            sid = sig.get("openalex_source_id")
            st = (venue_stats or {}).get(sid) if sid else None
            two = (st or {}).get("two_year_mean_citedness")
            if st and two is not None and (st.get("type") in ("journal", "conference", "book series")):
                score = _log_scale(two, 12.0)
                items.append({"key": "venue", "label": f"{st.get('name') or paper.get('venue')}（2 年平均被引 {two:.1f}）",
                              "score": round(score, 3), "evidence": "OpenAlex 期刊/会议统计"})

    # --- citations (age-normalised; meaningless for brand-new papers) ---
    pub = paper.get("published")
    age_days = None
    if pub:
        try:
            age_days = (today - date.fromisoformat(pub)).days
        except ValueError:
            age_days = None
    cites = sig.get("citations")
    if cites is not None and age_days is not None and age_days >= 30:
        pct = sig.get("citation_percentile")
        if pct is not None:
            score = float(pct)
        else:
            per_month = cites / max(1.0, age_days / 30.0)
            score = _log_scale(per_month, 5.0)
        infl = sig.get("influential_citations")
        label = f"被引 {cites} 次" + (f"（高影响力引用 {infl}）" if infl else "")
        items.append({"key": "citations", "label": label, "score": round(score, 3), "evidence": "引用数据"})

    # --- community attention ---
    up = sig.get("hf_upvotes")
    if up is not None and up > 0:
        items.append({"key": "community", "label": f"Hugging Face 社区 {up} 赞", "score": round(_log_scale(up, 150.0), 3),
                      "evidence": "Hugging Face Daily Papers"})

    # --- completeness / reproducibility ---
    comp_scores = []
    comp_labels = []
    if sig.get("code_url") or sig.get("hf_github_repo"):
        comp_scores.append(1.0)
        comp_labels.append("提供开源代码")
    elif sig.get("code_mentioned"):
        comp_scores.append(0.75)
        comp_labels.append("声明将公开代码")
    m = _PAGES.search(paper.get("comment") or "")
    if m:
        pages = int(m.group(1))
        comp_scores.append(0.7 if pages >= 8 else (0.45 if pages >= 4 else 0.3))
        comp_labels.append(f"{pages} 页")
    if comp_scores:
        items.append({"key": "completeness", "label": " · ".join(comp_labels),
                      "score": round(sum(comp_scores) / len(comp_scores), 3), "evidence": "作者备注 / 摘要"})

    present_w = sum(WEIGHTS[i["key"]] for i in items)
    if present_w > 0:
        observed = sum(WEIGHTS[i["key"]] * i["score"] for i in items) / present_w
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
