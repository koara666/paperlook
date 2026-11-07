"""Interface languages: every message exists in zh/en/ja/ko with the same placeholders (backend catalog and
frontend dictionaries), stored messages follow the language, and text stored by 1.x is still translated."""
import re
from pathlib import Path

import pytest

from paperlook import i18n
from paperlook.i18n_catalog import M, PERSISTED

FRONTEND = Path(__file__).resolve().parents[2] / "frontend" / "src" / "i18n"
PLACEHOLDER = re.compile(r"\{(\w+)\}")
TAG = re.compile(r"<(\w+)>")
# Placeholders a translation may use although the Chinese text does not (Japan / Korea reset hour).
FRONTEND_EXTRA = {"gm.free_desc": {"hour_next"}, "gm.used_today": {"hour_next"}}


def test_backend_catalog_complete_and_consistent():
    for key, texts in M.items():
        assert set(texts) == set(i18n.LANGS), key
        zh = set(PLACEHOLDER.findall(texts["zh"]))
        for lang in ("en", "ja", "ko"):
            other = set(PLACEHOLDER.findall(texts[lang]))
            assert other <= zh | i18n.EXTRA_PARAMS.get(key, set()), (key, lang, other - zh)
            assert zh <= other, (key, lang, zh - other)
            assert texts[lang].strip(), (key, lang)
    for key in PERSISTED:
        assert key in M


def _dictionary(lang: str) -> dict[str, str]:
    text = (FRONTEND / f"{lang}.ts").read_text(encoding="utf-8")
    return {m.group(1): m.group(2) for m in re.finditer(r'^  "([^"]+)": "((?:[^"\\]|\\.)*)",?\s*$', text, re.M)}


def test_frontend_dictionaries_complete_and_consistent():
    zh = _dictionary("zh")
    assert len(zh) > 700
    for lang in ("en", "ja", "ko"):
        d = _dictionary(lang)
        assert set(d) == set(zh), (lang, set(zh) ^ set(d))
        for key, text in zh.items():
            a, b = set(PLACEHOLDER.findall(text)), set(PLACEHOLDER.findall(d[key]))
            extra = FRONTEND_EXTRA.get(key, set())
            assert b <= a | extra, (lang, key, b - a)
            assert a - {"hour"} <= b if extra else a <= b, (lang, key, a - b)
            assert sorted(TAG.findall(text)) == sorted(TAG.findall(d[key])), (lang, key)
            assert d[key].strip(), (lang, key)


def test_stored_messages_follow_the_language():
    m = i18n.msg("q.accepted", venue="CVPR 2026")
    assert i18n.render(m, "zh") == "作者注明：已被 CVPR 2026 接收"
    assert i18n.render(m, "en") == "Authors state: accepted at CVPR 2026"
    assert "CVPR 2026" in i18n.render(m, "ja") and "CVPR 2026" in i18n.render(m, "ko")
    nested = i18n.msg("fb.similar", kind=i18n.msg("fb.kind.starred"), title="T")
    assert i18n.render(nested, "en") == "Similar to “T”, which you starred"
    assert i18n.t("rec.sources_failed", "zh", sources=["arXiv", "OpenAlex"]) == "以下来源本次请求失败：arXiv、OpenAlex。"
    assert i18n.t("rec.sources_failed", "en", sources=["arXiv", "OpenAlex"]) == "These sources failed this time: arXiv, OpenAlex."


def test_english_plural():
    assert i18n.t("q.citations", "en", n=1) == "Cited 1 time"
    assert i18n.t("q.citations", "en", n=3) == "Cited 3 times"
    assert i18n.t("rec.none_found", "en", window=1).endswith("last day.")
    assert i18n.t("rec.none_found", "en", window=7).endswith("last 7 days.")


@pytest.mark.parametrize("old, lang, expected", [
    ("作者注明：已被 NeurIPS 2026 接收", "en", "Authors state: accepted at NeurIPS 2026"),
    ("提供开源代码 · 15 页", "en", "Open-source code · 15 pages"),
    ("arXiv 首个版本 (v1) 提交日期", "ja", "arXiv 初版（v1）の投稿日"),
    ("与你收藏的《Graph networks》相近", "en", "Similar to “Graph networks”, which you starred"),
    ("Scientific Reports（2 年平均被引 5.3）", "ko", "Scientific Reports(2년 평균 피인용 5.3)"),
    ("Not Chinese at all", "en", "Not Chinese at all"),
    ("一篇中文论文的标题", "en", "一篇中文论文的标题"),
])
def test_text_stored_by_1x_is_translated(old, lang, expected):
    assert i18n.render(old, lang) == expected
    assert i18n.render(old, "zh") == old


def test_legacy_batch_message_is_translated_sentence_by_sentence(tmp_db):
    from paperlook.recommend.engine import render_message

    old = "最近 3 天内只找到 2 篇新的相关论文（目标 5 篇）。 arXiv 周末不发布新论文，可以把时间范围扩大到 7 天。"
    with i18n.use("en"):
        out = render_message(old)
    assert out.startswith("Only 2 of 5 papers found in the last 3 days.") and "weekends" in out


def test_language_setting_and_system_fallback(tmp_db):
    from paperlook import settings_store

    assert settings_store.get_settings()["language"] == ""
    assert i18n.current() in i18n.LANGS  # follows the system until chosen
    settings_store.update_settings({"language": "ko"})
    assert i18n.current() == "ko"
    settings_store.update_settings({"language": "xx"})
    assert settings_store.get_settings()["language"] == ""
    assert i18n.normalize_lang("zh-Hant-TW") == "zh" and i18n.normalize_lang("ja_JP") == "ja"
    assert i18n.normalize_lang("fr") is None


def test_api_messages_follow_the_language(client):
    client.patch("/api/settings", json={"language": "en"})
    r = client.get("/api/papers/nope")
    assert r.status_code == 404 and r.json()["detail"] == "Paper not found"
    meta = client.get("/api/meta").json()
    assert meta["language"] == "en"
    assert any(p["key"] == "history_china" and p["name"] == "Chinese History" for p in meta["direction_presets"])
    assert {g["id"] for g in meta["preset_groups"]} == {"cs", "science", "life", "engineering", "social", "humanities"}
    client.patch("/api/settings", json={"language": "ja"})
    assert client.get("/api/papers/nope").json()["detail"] == "論文が見つかりません"
    sources = client.get("/api/sources").json()["sources"]
    assert any(s["id"] == "cinii" and "日本語" in s["description"] for s in sources)
