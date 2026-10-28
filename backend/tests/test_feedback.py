"""Preference from the user's own feedback: explainable, ordering-only, off without enough feedback."""
from datetime import date

from paperlook.recommend import feedback, ranker
from paperlook.recommend.relevance import compile_direction

GNN = "Graph neural networks for molecular property prediction with message passing on molecular graphs"
MED = "Medical image segmentation of tumors in MRI scans with a U-Net encoder decoder"


def _fb(i, kind, title, abstract, weight=1.0):
    return {"id": f"f{i}", "title": title, "abstract": abstract, "kind": kind, "weight": weight}


def _cand(i, title, abstract):
    return {"id": None, "title": title, "abstract": abstract}


FEEDBACK = [
    _fb(1, "starred", "Message passing graph neural networks for molecules", GNN),
    _fb(2, "noted", "Equivariant graph networks for molecular property prediction", GNN + " equivariant"),
    _fb(3, "starred", "Scalable molecular graph transformers", "Graph transformers for molecular graphs and property prediction"),
    _fb(4, "dismissed", "Tumor segmentation in MRI", MED),
    _fb(5, "dismissed", "Brain MRI lesion segmentation", "MRI lesion segmentation with U-Net for medical image analysis"),
    _fb(6, "dismissed", "Cardiac MRI segmentation", "Cardiac MRI segmentation with encoder decoder networks for medical images"),
]
CANDS = [
    _cand(0, "A new message passing graph neural network for molecular property prediction", GNN + " benchmark"),
    _cand(1, "Self-supervised learning for tabular data", "Contrastive pretraining for tabular data with transformers"),
    _cand(2, "Efficient U-Net for MRI tumor segmentation", MED + " efficient"),
    _cand(3, "Reinforcement learning for robot grasping", "Policy learning for grasping objects with a robot arm"),
]


def test_similar_to_favourites_goes_up_and_similar_to_dismissed_goes_down():
    prefs = feedback.preferences(CANDS, FEEDBACK)
    assert prefs[0].adjust > 0.05 and prefs[0].kind in ("starred", "noted")
    assert prefs[2].adjust < -0.05 and prefs[2].kind == "dismissed"
    assert abs(prefs[1].adjust) < abs(prefs[0].adjust) and abs(prefs[3].adjust) < abs(prefs[2].adjust)
    assert all(abs(p.adjust) <= feedback.MAX_ADJUST for p in prefs.values())
    assert feedback.reason(prefs[0]).startswith("与你") and "相近" in feedback.reason(prefs[0])
    assert "不感兴趣" in feedback.reason(prefs[2]) and "降低排序" in feedback.reason(prefs[2])


def test_off_without_enough_feedback():
    assert feedback.preferences(CANDS, FEEDBACK[:2]) == {}
    # merely opened papers are weak evidence and do not switch it on by themselves
    opened = [_fb(i, "opened", "Graph networks", GNN, 0.25) for i in range(10)]
    assert feedback.preferences(CANDS, opened) == {}
    assert feedback.preferences([], FEEDBACK) == {}


def test_preference_reorders_but_never_changes_candidacy():
    d = compile_direction({"id": 1, "name": "ML", "keywords": ["graph neural network", "segmentation"], "exclude": [],
                           "categories": [], "weight": 3})
    papers = [
        {"title": "Graph neural network for molecular property prediction", "abstract": GNN, "published": "2026-10-20",
         "date_quality": "exact", "categories": [], "signals": {}, "sources": []},
        {"title": "U-Net segmentation of MRI tumors", "abstract": MED, "published": "2026-10-20",
         "date_quality": "exact", "categories": [], "signals": {}, "sources": []},
        {"title": "Robot grasping with reinforcement learning", "abstract": "Policy learning for grasping",
         "published": "2026-10-20", "date_quality": "exact", "categories": [], "signals": {}, "sources": []},
    ]
    weights = {"relevance": 0.55, "quality": 0.25, "freshness": 0.20}
    scored, stats = ranker.score_candidates(papers, [d], weights, date(2026, 10, 21), 7, {})
    assert len(scored) == 2 and stats["low_relevance"] == 1  # the off-topic paper is out either way
    before = {s.paper["title"][:5]: s.score for s in scored}
    prefs = feedback.preferences([s.paper for s in scored], FEEDBACK)
    for i, s in enumerate(scored):
        s.pref = prefs.get(i)
        ranker.compute_score(s, weights)
    after = {s.paper["title"][:5]: s.score for s in scored}
    assert after["Graph"] > before["Graph"] and after["U-Net"] < before["U-Net"]
    gnn = next(s for s in scored if s.paper["title"].startswith("Graph"))
    b = ranker.breakdown(gnn, weights)
    assert b["preference"]["adjust"] > 0 and b["keyword_relevance"] == round(gnn.relevance.score, 4)
    assert any("相近" in r for r in ranker.build_reasons(gnn, date(2026, 10, 21)))


def test_feedback_is_read_from_the_library(tmp_db):
    from paperlook import db, papers

    ids = []
    for i, (title, abstract) in enumerate([("Graph networks one", GNN), ("Graph networks two", GNN), ("MRI three", MED),
                                           ("Opened only four", "Something else entirely")]):
        ids.append(papers.upsert({"title": title + " with a long enough title", "abstract": abstract, "authors": ["A"],
                                  "published": "2026-10-20", "date_quality": "exact", "arxiv_id": f"2610.0000{i}",
                                  "categories": [], "sources": [], "signals": {}}))
    papers.set_state(ids[0], starred=True)
    papers.set_state(ids[1], note="很有启发")
    papers.set_state(ids[2], dismissed=True)
    papers.set_state(ids[3], opened=True)
    db.execute("INSERT INTO translations(paper_id, unit_id, section_id, text, created_at) VALUES(?,?,?,?,?)",
               (ids[3], "u1", "s1", "译文", "2026-10-20T00:00:00+00:00"))
    kinds = {f["id"]: f["kind"] for f in feedback.load_feedback()}
    assert kinds == {ids[0]: "starred", ids[1]: "noted", ids[2]: "dismissed", ids[3]: "analyzed"}
