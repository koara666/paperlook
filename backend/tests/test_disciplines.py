"""Recommendations for every discipline and language: CJK matching, language detection, field-normalised venue
quality, curated flagship venues (incl. CJK journals), per-direction window / languages / fields, CiNii parsing."""
import sqlite3
from datetime import date

import pytest

from paperlook import i18n
from paperlook.recommend import ranker
from paperlook.recommend.quality import NON_CORE_CAP, assess, is_review, venue_stats_score
from paperlook.recommend.relevance import compile_direction, score_paper
from paperlook.recommend.venues import venue_from_name
from paperlook.textutil import detect_language, normalize, title_key

TODAY = date(2026, 11, 8)


def direction(**kw):
    base = {"id": 1, "name": "D", "keywords": ["宋代", "Song dynasty"], "exclude": [], "categories": [], "weight": 3}
    base.update(kw)
    return compile_direction(base)


# ---------------- text ----------------

def test_normalize_keeps_every_script_and_folds_width():
    assert normalize("データ駆動型の江戸時代研究") == "データ駆動型の江戸時代研究"  # no が -> か + ゛ splitting
    assert normalize("조선 후기 사회사") == "조선 후기 사회사"
    assert normalize("Ｆｕｌｌ－width Café") == "full width cafe"
    assert title_key("宋代 财政史：研究") == "宋代财政史研究"


@pytest.mark.parametrize("text, hint, title, expected", [
    ("宋代财政研究", None, "宋代财政研究", "zh"),
    ("江戸時代の将棋小説（上）", None, "江戸時代の将棋小説（上）", "ja"),  # a single kana decides
    ("조선 후기 사회사 연구", None, None, "ko"),
    ("江戸時代の被差別民衆 Abstract: This paper examines the people of the Edo period in detail.", "en",
     "江戸時代の被差別民衆", "ja"),  # CJK title wins over an English abstract
    ("Diese Arbeit untersucht die Wirkung der Geldpolitik auf die Inflation und den Arbeitsmarkt in der Eurozone.",
     None, None, "de"),
    ("This paper studies the effect of monetary policy on inflation in the euro area.", None, None, "en"),
])
def test_detect_language(text, hint, title, expected):
    assert detect_language(text, hint, title=title) == expected


# ---------------- relevance ----------------

def test_cjk_keywords_match_without_spaces():
    d = direction()
    assert score_paper(d, "论宋代的财政制度", "", []).title_hits == ["宋代"]
    ko = direction(keywords=["조선시대"])
    assert score_paper(ko, "조선시대의 향촌 사회", "", []).title_hits == ["조선시대"]  # particle attached


def test_latin_keyword_inside_chinese_text():
    d = direction(keywords=["transformer"])
    assert score_paper(d, "基于transformer的图像分割方法", "", []).title_hits == ["transformer"]
    assert score_paper(d, "Transformers for vision", "", []).title_hits == ["transformer"]


def test_single_incidental_abstract_mention_is_not_enough():
    d = direction(keywords=["Tang poetry"])
    once = score_paper(d, "A quantum language model", "We test on Tang poetry generation.", [])
    assert once.score < ranker.MIN_RELEVANCE
    twice = score_paper(d, "A quantum language model", "Tang poetry … more Tang poetry.", [])
    assert twice.score >= ranker.MIN_RELEVANCE


# ---------------- venues ----------------

@pytest.mark.parametrize("venue, canonical, tier", [
    ("史學雜誌 / 史学会 編", "史學雜誌", "A"),
    ("中国科学：信息科学", "中国科学:信息科学", "A"),
    ("管理世界", "管理世界", "A"),
    ("역사학보", "역사학보", "A"),
    ("Social Sciences in China", "Social Sciences in China", "A"),
    ("Physical review. B./Physical review. B", "Physical review. B", "B"),
    ("Nature Medicine", "Nature Medicine", "A"),
    ("The Lancet Oncology", "The Lancet Oncology", "A"),
    ("American Economic Review Insights", "AER: Insights", "B"),
    ("The Journal of Finance", "Journal of Finance", "A"),
    ("National Bureau of Economic Research", "NBER Working Papers", "B"),
    ("Late Imperial China", "Late Imperial China", "B"),
    ("Sahak Yonku The Review of Korean History", "Sahak Yonku The Review of Korean History", "B"),  # own spelling
    ("Yŏksa hakpo", "Yŏksa hakpo", "A"),
])
def test_flagship_venues(venue, canonical, tier):
    m = venue_from_name(venue)
    assert m and (m.venue, m.tier) == (canonical, tier)


@pytest.mark.parametrize("venue", [
    "Journal of Linguistics & Cultural Studies", "International Journal of Finance & Economics", "Journal of Management World",
    "中国科学院院刊", "Scientific Reports", "Buildings", "Advanced Materials Interfaces",
])
def test_lookalike_venues_are_not_flagships(venue):
    assert venue_from_name(venue) is None


# ---------------- quality ----------------

def _paper(**kw):
    p = {"title": "t", "published": "2026-11-01", "language": "en", "signals": {"openalex_source_id": "S1"}}
    p.update(kw)
    return p


def test_venue_citedness_is_compared_within_the_field():
    st = {"type": "journal", "two_year_mean_citedness": 2.0, "h_index": 80, "is_core": True}
    humanities = venue_stats_score({**st, "field": "12"})
    cs = venue_stats_score({**st, "field": "17"})
    assert humanities["score"] > 0.7 > 0.5 > cs["score"]


def test_unscreened_venue_cannot_score_above_neutral():
    st = {"type": "journal", "two_year_mean_citedness": 21.3, "h_index": 36, "is_core": False, "field": "20"}
    assert venue_stats_score(st)["score"] <= NON_CORE_CAP


def test_unscreened_rarely_cited_venue_is_not_shrunk_to_neutral():
    weak = {"type": "journal", "two_year_mean_citedness": 0.6, "h_index": 9, "is_core": False, "field": "20", "name": "X"}
    core = {**weak, "is_core": True}
    q_weak = assess(_paper(), TODAY, {"S1": weak})
    q_core = assess(_paper(), TODAY, {"S1": core})
    assert q_weak["score"] < 0.35 and q_weak["score"] < q_core["score"] < 0.5


def test_no_citation_data_is_no_evidence():
    st = {"type": "journal", "two_year_mean_citedness": 0.0, "h_index": 3, "is_core": False, "field": "33"}
    assert venue_stats_score(st) is None
    q = assess(_paper(), TODAY, {"S1": {**st, "name": "X"}})
    assert q["score"] == 0.5 and not q["signals"]


def test_low_stats_of_cjk_papers_are_not_held_against_them():
    weak = {"type": "journal", "two_year_mean_citedness": 0.2, "h_index": 12, "is_core": True, "field": "17", "name": "某学报"}
    assert assess(_paper(language="en"), TODAY, {"S1": weak})["score"] < 0.5
    assert assess(_paper(language="zh"), TODAY, {"S1": weak})["score"] == 0.5


def test_flagship_cjk_journal_counts_as_strong_evidence():
    q = assess(_paper(venue="管理世界", language="zh"), TODAY, {})
    assert q["score"] > 0.75 and i18n.render(q["signals"][0]["label"], "zh") == "发表于 管理世界"


def test_review_detection():
    assert is_review({"title": "A Survey of Vision-Language Models"})
    assert is_review({"title": "宋代财政史研究综述"})
    assert is_review({"title": "x", "signals": {"work_type": "review"}})
    assert not is_review({"title": "Reviewing the past: a novel method"})


# ---------------- ranking: per-direction window, languages, fields ----------------

def _cand(title, published="2026-11-05", language="en", field=None, **kw):
    p = {"title": title, "abstract": "", "published": published, "date_quality": "exact", "language": language,
         "categories": [], "signals": {"field": field} if field else {}}
    p.update(kw)
    return p


def test_direction_window_and_languages_decide_candidacy():
    d = direction(keywords=["Song dynasty"], window_days=30, languages=["en", "zh"])
    papers = [_cand("Song dynasty taxes"), _cand("Song dynasty salt", published="2026-08-01"),
              _cand("Song dynasty ceramics", language="de")]
    scored, stats = ranker.score_candidates(papers, [d], {"relevance": 0.55, "quality": 0.25, "freshness": 0.2},
                                            TODAY, 7.0, {})
    assert [s.paper["title"] for s in scored] == ["Song dynasty taxes"]
    assert stats["other_language"] == 1


def test_field_mismatch_and_minor_pieces_rank_lower_but_stay_candidates():
    d = direction(keywords=["Qing dynasty"], fields=["12", "33"])
    papers = [_cand("Qing dynasty salt administration", field="33"),
              _cand("Qing dynasty building energy simulation", field="22"),
              _cand("Book review: Qing dynasty courts", field="33"),
              _cand("Corrigendum to Qing dynasty courts", field="33")]
    w = {"relevance": 0.55, "quality": 0.25, "freshness": 0.2}
    scored, stats = ranker.score_candidates(papers, [d], w, TODAY, 7.0, {})
    by = {s.paper["title"]: s for s in scored}
    assert stats["notices"] == 1 and len(scored) == 3
    assert by["Qing dynasty building energy simulation"].field_mismatch == "22"
    assert by["Book review: Qing dynasty courts"].minor
    top = by["Qing dynasty salt administration"]
    assert top.score > by["Qing dynasty building energy simulation"].score
    assert top.score > by["Book review: Qing dynasty courts"].score
    reasons = i18n.render(ranker.build_reasons(by["Qing dynasty building energy simulation"], TODAY), "en")
    assert any("engineering" in r for r in reasons)


def test_long_window_slows_the_recency_decay():
    w = {"relevance": 0.55, "quality": 0.25, "freshness": 0.2}
    old = _cand("Song dynasty taxes", published="2026-09-01")
    short, _ = ranker.score_candidates([old], [direction(keywords=["Song dynasty"], window_days=365)], w, TODAY, 7.0, {})
    assert short[0].freshness > 0.3  # half-life grows to 60 days


def test_prefer_reviews_moves_surveys_up():
    w = {"relevance": 0.55, "quality": 0.25, "freshness": 0.2}
    papers = [_cand("A survey of Song dynasty studies"), _cand("Song dynasty taxes")]
    d = direction(keywords=["Song dynasty"])
    off, _ = ranker.score_candidates(papers, [d], w, TODAY, 7.0, {})
    on, _ = ranker.score_candidates(papers, [d], w, TODAY, 7.0, {}, prefer_reviews=True)
    assert off[0].score == off[1].score and on[0].score > on[1].score and on[0].review


# ---------------- sources ----------------

def test_openalex_quotes_cjk_terms_and_joins_cjk_abstracts():
    from paperlook.sources.openalex import _search_expr, rebuild_abstract

    assert _search_expr(["宋代", "Tang poetry", "RAG"]) == '"宋代" OR "Tang poetry" OR RAG'
    assert rebuild_abstract({"江戸時代の": [0], "画絹。": [1], "Edo": [2]}) == "江戸時代の画絹。 Edo"


def test_cinii_keeps_academic_records_and_drops_magazines():
    from paperlook.sources.cinii import parse_item, wanted
    from paperlook.sources.base import SourceQuery

    journal = {"@id": "https://cir.nii.ac.jp/crid/1", "title": "江戸時代の綿作と金肥干鰯の廻船流通",
               "dc:creator": ["山田 太郎"], "prism:publicationName": "關西大學文學論集", "prism:publicationDate": "2026-09-18",
               "description": "<p>近世の綿作について。</p>", "dc:identifier": [{"@type": "cir:DOI", "@value": "10.1/abc"}]}
    magazine = {"@id": "https://cir.nii.ac.jp/crid/2", "title": "歌舞伎町 春画展", "prism:publicationName": "東京人",
                "prism:publicationDate": "2026-11",
                "dc:identifier": [{"@type": "cir:NDL_BIB_ID", "@value": "1"}, {"@type": "cir:URI", "@value": "http://id.ndl.go.jp/bib/1"}]}
    flagship = {**magazine, "@id": "https://cir.nii.ac.jp/crid/3", "title": "書評", "prism:publicationName": "日本歴史 / 日本歴史学会 編"}
    p = parse_item(journal, TODAY)
    assert p and p.doi == "10.1/abc" and p.date_quality == "exact" and p.abstract == "近世の綿作について。"
    assert parse_item(magazine, TODAY) is None
    f = parse_item(flagship, TODAY)
    assert f and f.date_quality == "approx"
    q = lambda **kw: SourceQuery(keywords=kw.get("k", ["deep learning"]), exclude=[], categories=[], date_from=TODAY,
                                 date_to=TODAY, languages=kw.get("l", []))
    assert not wanted(q()) and wanted(q(k=["江戸時代"])) and wanted(q(l=["ja"])) and not wanted(q(k=["宋代"], l=["en"]))


# ---------------- directions and presets ----------------

def test_direction_languages_fields_and_window(tmp_db):
    from paperlook import directions

    d = directions.create_direction({"name": "宋代财政", "keywords": [], "languages": ["zh", "en", "xxx"],
                                     "fields": ["12", "99"], "window_days": 180})
    assert d["keywords"] == ["宋代财政"]  # CJK names work as keywords too
    assert d["languages"] == ["zh", "en"] and d["fields"] == ["12"] and d["window_days"] == 180
    d = directions.update_direction(d["id"], {"window_days": None, "languages": []})
    assert d["window_days"] is None and d["languages"] == []


def test_presets_cover_every_discipline_in_every_language():
    from paperlook import directions

    groups = {p["group"] for p in directions.PRESETS}
    assert groups == set(directions.PRESET_GROUPS)
    for lang in i18n.LANGS:
        with i18n.use(lang):
            names = [p["name"] for p in directions.presets()]
            assert all(n and not n.startswith("preset.") for n in names)
    humanities = [p for p in directions.presets() if p["group"] == "humanities"]
    assert all((p["window_days"] or 0) >= 90 and p["fields"] for p in humanities)


# ---------------- storage per language ----------------

def test_migration_keeps_1x_translations_and_results_as_chinese(tmp_path):
    from paperlook import db

    path = tmp_path / "old.db"
    conn = sqlite3.connect(path)
    conn.executescript(db.MIGRATIONS[0])
    conn.execute("INSERT INTO papers(id, title, title_norm) VALUES('p1', 'T', 't')")
    conn.execute("INSERT INTO translations(paper_id, unit_id, text) VALUES('p1', 's1.b1', '译文')")
    conn.execute("INSERT INTO ai_results(paper_id, kind, content) VALUES('p1', 'summary', '{\"tldr\": \"x\"}')")
    conn.execute("PRAGMA user_version = 1")
    conn.commit()
    conn.close()
    db.configure(path)
    assert db.query("SELECT lang, text FROM translations") == [{"lang": "zh", "text": "译文"}]
    assert db.query("SELECT lang FROM ai_results") == [{"lang": "zh"}]
    db.configure(tmp_path / "other.db")


def test_results_are_kept_per_language(tmp_db):
    from paperlook import db, settings_store
    from paperlook.ai import analyze, translate

    db.execute("INSERT INTO papers(id, title, title_norm) VALUES('p1', 'T', 't')")
    analyze.save_result("p1", "summary", "zh", {"tldr": "中文"}, None, "m", {})
    settings_store.update_settings({"language": "ja"})
    r = analyze.get_result("p1", "summary")
    assert r["lang"] == "zh" and r["content"]["tldr"] == "中文"  # shown, marked as another language
    assert analyze.get_result("p1", "summary", exact=True) is None  # so "generate" really generates
    analyze.save_result("p1", "summary", "ja", {"tldr": "日本語"}, None, "m", {})
    assert analyze.get_result("p1", "summary")["content"]["tldr"] == "日本語"
    db.execute("INSERT INTO translations(paper_id, unit_id, lang, text) VALUES('p1', 'u1', 'zh', '译文')")
    assert translate.translated_map("p1") == {} and translate.translated_map("p1", "zh")["u1"]["text"] == "译文"
    analyze.save_result("p1", "abstract_translation", "ja", {"title_zh": "旧", "abstract_zh": "旧訳"}, None, "m", {})
    assert analyze.get_result("p1", "abstract_translation")["content"] == {"title": "旧", "abstract": "旧訳"}


def test_paper_already_in_the_output_language_is_not_translated(client):
    from paperlook import db, secrets_store

    secrets_store.set_secret(secrets_store.DEEPSEEK, "sk-mock-ok-123456")
    client.patch("/api/settings", json={"language": "zh"})
    db.execute("INSERT INTO papers(id, title, title_norm, abstract) VALUES('p1', '宋代财政研究', 'x', '本文讨论宋代的财政制度。')")
    doc = {"version": 1, "source": "pdf", "source_label": {"$t": "doc.src.pdf_oa"}, "source_url": "u", "title": "",
           "warnings": [], "stats": {}, "sections": [{"id": "s1", "level": 1, "number": None, "title": "引言", "kind": "body",
                                                     "blocks": [{"id": "s1.b1", "type": "paragraph",
                                                                 "text": "宋代的财政制度在中国历史上具有重要地位，本文从多个角度加以讨论。"}]}]}
    db.execute("INSERT INTO fulltext(paper_id, source, source_url, doc) VALUES('p1', 'pdf', 'u', ?)", (db.dumps(doc),))
    detail = client.get("/api/papers/p1").json()
    assert detail["language"]["fulltext"] == "zh" and not detail["language"]["translate_needed"]
    r = client.post("/api/papers/p1/translate", json={})
    assert r.status_code == 400 and r.json()["code"] == "same_language"
    client.patch("/api/settings", json={"language": "en"})  # an English reader does need it
    assert client.get("/api/papers/p1").json()["language"]["translate_needed"]
    assert client.get("/api/papers/p1/fulltext").json()["doc"]["source_label"] == "PDF (open access)"


def test_cjk_quotes_are_verified_by_characters():
    from paperlook.ai.analyze import verify_quotes

    src = "宋代的财政制度在中国历史上具有重要地位，本文从多个角度加以讨论。"
    items = [{"quote": "宋代的财政制度在中国历史上具有重要地位"}, {"quote": "明代的军事制度完全不同于以往任何朝代"}]
    verify_quotes(items, src)
    assert [i["verified"] for i in items] == ["exact", "not_found"]


def test_ordinary_korean_study_is_not_a_survey():
    assert not is_review({"title": "조선 후기 향촌사회에 대한 고찰"})
    assert is_review({"title": "한국 고대사 연구 동향"})
