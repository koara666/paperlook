"""When the arXiv API refuses us (HTTP 429), arXiv papers are fetched through OpenAlex instead."""
from datetime import date

from paperlook.sources.base import RawPaper, SourceError
from paperlook.sources.openalex import ARXIV_SOURCE, parse_work

WORK = {
    "id": "https://openalex.org/W1", "doi": "https://doi.org/10.48550/arxiv.2610.35374",
    "title": "GIFT: Representation Geometry Matters", "publication_date": "2026-10-26",
    "primary_location": {"source": {"id": f"https://openalex.org/{ARXIV_SOURCE}", "display_name": "arXiv (Cornell University)",
                                    "type": "repository"}, "landing_page_url": "https://arxiv.org/abs/2610.35374"},
    "authorships": [{"author": {"display_name": "Yin Zhang"}}], "abstract_inverted_index": {"Geometry": [0], "matters": [1]},
    "cited_by_count": 0,
}


def test_openalex_arxiv_work_is_an_arxiv_preprint_not_a_venue():
    p = parse_work(WORK, date(2026, 10, 28))
    assert p.arxiv_id == "2610.35374" and p.venue is None
    assert "openalex_source_id" not in p.signals  # arXiv's "venue statistics" must not count as quality
    assert p.url == "https://arxiv.org/abs/2610.35374" and p.pdf_url == "https://arxiv.org/pdf/2610.35374"
    assert p.date_quality == "exact" and p.published.isoformat() == "2026-10-26" and "arXiv" in p.date_note


def test_engine_falls_back_to_openalex_when_arxiv_refuses(tmp_db, monkeypatch):
    from paperlook import directions
    from paperlook.jobs import Job
    from paperlook.recommend import engine
    from paperlook.sources import REGISTRY

    d = directions.create_direction({"name": "CV", "keywords": ["object detection"], "exclude": [], "categories": ["cs.CV"],
                                     "weight": 3})
    calls = []

    def arxiv_search(q):
        raise SourceError("arXiv 暂时限制了访问频率（HTTP 429），稍后获取推荐时会自动重试")

    def openalex_search(q, arxiv_only=False):
        calls.append(arxiv_only)
        p = parse_work(WORK, date(2026, 10, 28)) if arxiv_only else None
        return [p] if p else [RawPaper(source="openalex", source_id="W2", title="A journal paper on object detection",
                                       abstract="x", authors=["A"], published=date(2026, 10, 25), date_quality="exact")]

    monkeypatch.setattr(REGISTRY["arxiv"], "search", arxiv_search)
    monkeypatch.setattr(REGISTRY["openalex"], "search", openalex_search)
    merged, stats = engine._fetch_pool(Job("recommend", None), [d], ["arxiv", "openalex"], date(2026, 10, 21), date(2026, 10, 28))
    assert calls == [False, True]
    assert stats["arxiv"]["fallback"] == {"via": "OpenAlex", "fetched": 1}
    assert {p.get("arxiv_id") for p in merged} == {"2610.35374", None}

    # No fallback when arXiv worked, or when OpenAlex is disabled.
    calls.clear()
    monkeypatch.setattr(REGISTRY["arxiv"], "search", lambda q: [])
    _, stats = engine._fetch_pool(Job("recommend", None), [d], ["arxiv", "openalex"], date(2026, 10, 21), date(2026, 10, 28))
    assert calls == [False] and "fallback" not in stats["arxiv"]
    monkeypatch.setattr(REGISTRY["arxiv"], "search", arxiv_search)
    _, stats = engine._fetch_pool(Job("recommend", None), [d], ["arxiv"], date(2026, 10, 21), date(2026, 10, 28))
    assert "fallback" not in stats["arxiv"]
