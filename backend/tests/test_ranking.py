from datetime import date

from paperlook.recommend import ranker
from paperlook.recommend.freshness import FLOOR, freshness
from paperlook.recommend.quality import assess
from paperlook.recommend.relevance import compile_direction, score_paper
from paperlook.recommend.venues import venue_from_comment, venue_from_name

TODAY = date(2026, 10, 26)


def direction(**kw):
    base = {"id": 1, "name": "多模态", "keywords": ["vision-language model", "multimodal", "VLM"], "exclude": [],
            "categories": ["cs.CV"], "weight": 3}
    base.update(kw)
    return compile_direction(base)


# ---------------- relevance ----------------

def test_title_beats_abstract_and_plural_hyphen_tolerance():
    d = direction()
    t = score_paper(d, "Vision Language Models for Robots", "", ["cs.RO"])
    a = score_paper(d, "A robot paper", "We use vision-language models.", ["cs.RO"])
    assert t.title_hits == ["vision-language model"]
    assert a.abstract_hits == ["vision-language model"]
    assert t.score > a.score > 0


def test_acronym_is_case_sensitive():
    d = direction(keywords=["CLIP"])
    assert score_paper(d, "Improving CLIP", "", []).score > 0
    assert score_paper(d, "Video clip retrieval", "", []).score == 0


def test_multiple_hits_saturate_below_one():
    d = direction()
    r = score_paper(d, "Multimodal VLM: a vision-language model", "multimodal multimodal", ["cs.CV"])
    assert 0.9 < r.score <= 1.0


def test_exclusion_is_per_direction():
    d1 = direction(id=1, exclude=["medical"])
    d2 = direction(id=2, name="other", keywords=["benchmark"])
    paper = {"title": "A medical multimodal benchmark", "abstract": "", "categories": ["cs.CV"], "published": "2026-10-25"}
    scored, stats = ranker.score_candidates([paper], [d1, d2], {"relevance": .55, "quality": .25, "freshness": .2}, TODAY, 7, {})
    assert len(scored) == 1 and scored[0].direction.id == 2


def test_low_relevance_papers_are_never_candidates():
    d = direction()
    paper = {"title": "Unrelated topic", "abstract": "nothing here", "categories": ["cs.CV"], "published": "2026-10-26",
             "comment": "Accepted at CVPR 2026", "signals": {"hf_upvotes": 500}}
    scored, stats = ranker.score_candidates([paper], [d], {"relevance": .2, "quality": .4, "freshness": .4}, TODAY, 7, {})
    assert scored == [] and stats["low_relevance"] == 1


# ---------------- venues / quality ----------------

def test_venue_claims():
    assert venue_from_comment("Accepted at CVPR 2026").display == "CVPR 2026"
    assert venue_from_comment("Submitted to NeurIPS 2026") is None
    assert venue_from_comment("ACL Rolling Review recommends acceptance at an *ACL venue") is None
    assert venue_from_comment("CVPRW 2026").kind == "workshop"
    assert venue_from_comment("Findings of EMNLP 2026").tier == "findings"
    assert venue_from_comment("We use NAACL data and CLIP") is None
    assert venue_from_name("IEEE Transactions on Pattern Analysis and Machine Intelligence").venue == "IEEE TPAMI"
    assert venue_from_name("Pattern Recognition Letters") is None


def test_quality_without_evidence_is_neutral():
    q = assess({"title": "x", "published": "2026-10-25", "signals": {}}, TODAY)
    assert q["score"] == 0.5 and q["insufficient"]


def test_quality_new_paper_citations_ignored():
    q = assess({"title": "x", "published": "2026-10-20", "signals": {"citations": 0}}, TODAY)
    assert all(s["key"] != "citations" for s in q["signals"])


def test_quality_signals_raise_score():
    q = assess({"title": "x", "published": "2026-10-20", "comment": "Accepted to ICLR 2026. Code: https://github.com/a/b",
                "signals": {"code_url": "https://github.com/a/b", "hf_upvotes": 80}}, TODAY)
    assert q["score"] > 0.75 and not q["insufficient"]


def test_low_impact_venue_slightly_below_neutral():
    q = assess({"title": "x", "published": "2026-10-20", "venue": "Some Journal", "signals": {"openalex_source_id": "S1"}},
               TODAY, {"S1": {"name": "Some Journal", "type": "journal", "two_year_mean_citedness": 0.3}})
    assert 0.3 < q["score"] < 0.5


# ---------------- freshness ----------------

def test_freshness_decay_and_floor():
    assert freshness("2026-10-26", "exact", TODAY, 7) == 1.0
    assert abs(freshness("2026-10-19", "exact", TODAY, 7) - 0.6) < 1e-6
    assert freshness("2025-01-01", "exact", TODAY, 7) >= FLOOR
    assert freshness("2026-10-26", "approx", TODAY, 7) < 1.0
    assert freshness(None, "unknown", TODAY, 7) == FLOOR


# ---------------- selection ----------------

def test_quotas_follow_attention_weights():
    d1, d2 = direction(id=1, weight=5), direction(id=2, weight=1)
    q = ranker.allocate_quotas(6, [d1, d2], {1: 10, 2: 10})
    assert q == {1: 5, 2: 1}
    # unused quota is not lost: direction 2 has only 0 candidates
    q = ranker.allocate_quotas(6, [d1, d2], {1: 10})
    assert q == {1: 6}


def test_select_fills_remaining_slots():
    d1, d2 = direction(id=1, weight=3), direction(id=2, name="b", keywords=["retrieval"], weight=3)
    papers = [{"title": f"multimodal paper {i}", "abstract": "", "categories": [], "published": "2026-10-25"} for i in range(5)]
    papers.append({"title": "dense retrieval", "abstract": "", "categories": [], "published": "2026-10-25"})
    scored, _ = ranker.score_candidates(papers, [d1, d2], {"relevance": .55, "quality": .25, "freshness": .2}, TODAY, 7, {})
    chosen = ranker.select(scored, [d1, d2], 4)
    assert len(chosen) == 4
    assert sum(1 for s in chosen if s.direction.id == 2) == 1
    assert [s.score for s in chosen] == sorted([s.score for s in chosen], reverse=True)
