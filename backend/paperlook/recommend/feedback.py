"""Personal preference from the user's own feedback, as an explainable adjustment to relevance.

Positive feedback: starred papers and papers with a note (1.0), papers the user translated or analysed
with AI (0.6), papers they opened (0.25). Negative: papers marked "not interested" (1.0).

Each candidate is compared with those papers by TF-IDF cosine similarity of title (counted twice) and
abstract, computed locally (no AI). For a candidate,

    affinity = mean of its top-3 weighted similarities to positive papers
             - mean of its top-3 similarities to negative papers

and the relevance adjustment is MAX_ADJUST * tanh((affinity - median affinity of all candidates) / SCALE).
Centring on the median keeps it a pure ordering signal (it never lifts every score), and like freshness it
never decides candidacy: eligibility (MIN_RELEVANCE) is still keyword relevance alone. It is off until the
user has given at least MIN_FEEDBACK papers of feedback.
"""
from __future__ import annotations

import math
import re
from collections import Counter
from dataclasses import dataclass
from typing import Any

from .. import db

MAX_ADJUST = 0.15
SCALE = 0.08
MIN_FEEDBACK = 3
MAX_PER_KIND = 300
TOP_K = 3
SHOWN = 0.03  # adjustments smaller than this are not mentioned in the reasons

_WORD = re.compile(r"[a-z][a-z0-9\-]{2,}")
_STOP = set("""
about above across after again against also among an and any are as at based be been before being below
between both but by can could did do does doing down during each either few for from further had has have
having here how however if in into is it its itself just less like may more most much must new no nor not
novel now of off on once only or other our out over own paper per propose proposed provides same
show shows such than that the their them then there these they this those through thus to too toward towards
under until up upon use used uses using various very via was we well were what when where whether which
while who whom why will with within without would yet approach approaches method methods results result work
existing study studies demonstrate demonstrates achieve achieves present presents introduce introduces
furthermore moreover significantly state-of-the-art experiments experimental extensive task tasks
""".split())

KIND_LABEL = {"starred": "收藏", "noted": "写过笔记", "analyzed": "用 AI 分析过", "opened": "读过", "dismissed": "标记为不感兴趣"}


@dataclass
class FeedbackPaper:
    id: str
    title: str
    kind: str
    weight: float
    vec: dict[str, float]


@dataclass
class Preference:
    adjust: float
    affinity: float
    paper_id: str | None = None
    title: str | None = None
    kind: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {"adjust": round(self.adjust, 4), "paper_id": self.paper_id, "title": self.title, "kind": self.kind}


def tokens(title: str | None, abstract: str | None) -> Counter[str]:
    def words(t: str | None) -> list[str]:
        out = []
        for w in _WORD.findall((t or "").lower()):
            w = w.strip("-")
            if len(w) < 3 or w in _STOP:
                continue
            if len(w) > 4 and w.endswith("s") and not w.endswith("ss"):
                w = w[:-1]  # crude plural folding: "networks" ~ "network"
            out.append(w)
        return out

    tw = words(title)
    c = Counter(tw * 2 + words(abstract))
    c.update(f"{a} {b}" for a, b in zip(tw, tw[1:]))  # title bigrams carry topic phrases
    return c


def load_feedback() -> list[dict[str, Any]]:
    """Feedback papers, strongest kind per paper, most recent first."""
    rows = db.query(
        "SELECT p.id, p.title, p.abstract, s.starred, s.dismissed, s.opened_at, TRIM(COALESCE(s.note, '')) <> '' AS noted, "
        "(p.id IN (SELECT paper_id FROM ai_results WHERE kind IN ('summary','modules','contributions')) "
        " OR p.id IN (SELECT DISTINCT paper_id FROM translations)) AS analyzed, "
        "COALESCE(s.opened_at, s.read_at, p.created_at) AS at "
        "FROM papers p JOIN paper_state s ON s.paper_id = p.id "
        "WHERE s.starred = 1 OR s.dismissed = 1 OR s.opened_at IS NOT NULL OR TRIM(COALESCE(s.note, '')) <> '' "
        "ORDER BY at DESC"
    )
    out, counts = [], Counter()
    for r in rows:
        if r["dismissed"]:
            kind, weight = "dismissed", 1.0
        elif r["starred"]:
            kind, weight = "starred", 1.0
        elif r["noted"]:
            kind, weight = "noted", 1.0
        elif r["analyzed"]:
            kind, weight = "analyzed", 0.6
        else:
            kind, weight = "opened", 0.25
        side = "neg" if kind == "dismissed" else "pos"
        if counts[side] >= MAX_PER_KIND:
            continue
        counts[side] += 1
        out.append({"id": r["id"], "title": r["title"], "abstract": r["abstract"], "kind": kind, "weight": weight})
    return out


def _tfidf(docs: list[Counter[str]]) -> list[dict[str, float]]:
    df = Counter(t for d in docs for t in d)
    n = len(docs)
    vecs = []
    for d in docs:
        v = {t: (1 + math.log(c)) * math.log((1 + n) / (1 + df[t])) for t, c in d.items()}
        norm = math.sqrt(sum(x * x for x in v.values())) or 1.0
        vecs.append({t: x / norm for t, x in v.items() if x > 0})
    return vecs


def preferences(candidates: list[dict[str, Any]], feedback: list[dict[str, Any]] | None = None) -> dict[int, Preference]:
    """Preference adjustment per candidate index. Empty when there is too little feedback."""
    feedback = load_feedback() if feedback is None else feedback
    pos_n = sum(1 for f in feedback if f["kind"] != "dismissed" and f["weight"] >= 0.6)
    neg_n = sum(1 for f in feedback if f["kind"] == "dismissed")
    # "Opened" alone is weak evidence: it counts once there is some explicit feedback too.
    if not candidates or (pos_n < MIN_FEEDBACK and neg_n < MIN_FEEDBACK):
        return {}
    cand_ids = {c.get("id") for c in candidates}
    feedback = [f for f in feedback if f["id"] not in cand_ids]
    vecs = _tfidf([tokens(c.get("title"), c.get("abstract")) for c in candidates]
                  + [tokens(f["title"], f["abstract"]) for f in feedback])
    cvecs, fvecs = vecs[:len(candidates)], vecs[len(candidates):]
    fb = [FeedbackPaper(f["id"], f["title"], f["kind"], f["weight"], v) for f, v in zip(feedback, fvecs)]
    index: dict[str, list[tuple[int, float]]] = {}
    for i, f in enumerate(fb):
        for t, x in f.vec.items():
            index.setdefault(t, []).append((i, x))

    raw: list[tuple[float, FeedbackPaper | None, FeedbackPaper | None]] = []
    for cv in cvecs:
        sims: dict[int, float] = {}
        for t, x in cv.items():
            for i, y in index.get(t, ()):
                sims[i] = sims.get(i, 0.0) + x * y
        pos = sorted(((s * fb[i].weight, fb[i]) for i, s in sims.items() if fb[i].kind != "dismissed"), key=lambda z: -z[0])
        neg = sorted(((s, fb[i]) for i, s in sims.items() if fb[i].kind == "dismissed"), key=lambda z: -z[0])
        p = sum(s for s, _ in pos[:TOP_K]) / TOP_K
        n = sum(s for s, _ in neg[:TOP_K]) / TOP_K
        raw.append((p - n, pos[0][1] if pos else None, neg[0][1] if neg else None))

    ordered = sorted(a for a, *_ in raw)
    mid = len(ordered) // 2
    median = ordered[mid] if len(ordered) % 2 else (ordered[mid - 1] + ordered[mid]) / 2
    out: dict[int, Preference] = {}
    for i, (affinity, top_pos, top_neg) in enumerate(raw):
        adj = MAX_ADJUST * math.tanh((affinity - median) / SCALE)
        ref = top_pos if adj > 0 else top_neg
        out[i] = Preference(adjust=adj, affinity=affinity, paper_id=ref.id if ref else None,
                            title=ref.title if ref else None, kind=ref.kind if ref else None)
    return out


def reason(pref: Preference | None) -> str | None:
    if not pref or abs(pref.adjust) < SHOWN or not pref.title:
        return None
    title = pref.title if len(pref.title) <= 60 else pref.title[:58] + "…"
    if pref.adjust > 0:
        return f"与你{KIND_LABEL.get(pref.kind or '', '关注')}的《{title}》相近"
    return f"与你标记为不感兴趣的《{title}》相近，已降低排序"
