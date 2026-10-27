"""Gemini provider: API configuration, error mapping, fallbacks, rate limiting and translation,
against the local mock server (backend/tests/mock_deepseek.py) - no real key or quota needed."""
import socket
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import mock_deepseek  # noqa: E402


@pytest.fixture(scope="module")
def mock_url():
    import uvicorn

    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    server = uvicorn.Server(uvicorn.Config(mock_deepseek.app, host="127.0.0.1", port=port, log_level="warning"))
    t = threading.Thread(target=server.run, daemon=True)
    t.start()
    for _ in range(100):
        if server.started:
            break
        time.sleep(0.05)
    yield f"http://127.0.0.1:{port}"
    server.should_exit = True
    t.join(5)


@pytest.fixture()
def gemini(client, mock_url):
    """App configured to use Gemini (free tier off, so tests do not wait on the rate limiter)."""
    from paperlook.ai import client as ai_client

    ai_client._gemini_compat.clear()
    r = client.patch("/api/ai/config", json={"provider": "gemini", "gemini_base_url": mock_url, "gemini_free_tier": False})
    assert r.status_code == 200
    return client


def _set_key(c, key):
    r = c.put("/api/ai/key", json={"api_key": key, "provider": "gemini"})
    assert r.status_code == 200, r.text
    return r.json()


def test_config_shape_and_key_never_returned(gemini):
    key = "AIza-mock-ok-0123456789abcdef"
    cfg = _set_key(gemini, key)
    assert cfg["provider"] == "gemini" and cfg["label"] == "Gemini"
    assert cfg["configured"] and cfg["providers"]["gemini"]["configured"]
    assert not cfg["providers"]["deepseek"]["configured"]
    assert cfg["model"] == "gemini-3.5-flash-lite"
    for path in ("/api/ai/config", "/api/settings", "/api/status", "/api/data/export"):
        assert key not in gemini.get(path).text
    assert gemini.get("/api/ai/available").json() == {"configured": True}


def test_connection_test_ok(gemini):
    _set_key(gemini, "AIza-mock-ok-0123456789abcdef")
    r = gemini.post("/api/ai/test", json={}).json()
    assert r["ok"], r
    assert r["models"] == ["gemini-3.5-flash-lite", "gemini-3.8-flash"]  # embeddings / TTS filtered out
    assert [s["name"] for s in r["steps"]] == ["身份验证", "模型调用（gemini-3.5-flash-lite）"]
    assert gemini.get("/api/ai/config").json()["last_test"]["ok"]
    req = mock_deepseek.gemini_requests[-1]
    assert req["body"]["generationConfig"]["thinkingConfig"] == {"thinkingLevel": "minimal"}
    # usage is recorded per model and counted towards today's (Pacific-time) quota
    assert gemini.get("/api/ai/config").json()["providers"]["gemini"]["requests_today"]["gemini-3.5-flash-lite"] >= 1


@pytest.mark.parametrize("key,code,text", [
    ("AIza-mock-invalid-123456", "auth", "无效"),
    ("AIza-mock-region-123456", "region", "地区"),
    ("AIza-mock-daily-1234567", "quota_daily", "每天 20 次"),
    ("AIza-mock-zero-12345678", "quota_daily", "不在你的免费额度内"),
])
def test_connection_errors_are_explained(gemini, key, code, text):
    _set_key(gemini, key)
    r = gemini.post("/api/ai/test", json={}).json()
    assert not r["ok"] and r["error_code"] == code, r
    assert text in r["error"]


def test_unknown_model(gemini):
    _set_key(gemini, "AIza-mock-ok-0123456789abcdef")
    gemini.patch("/api/ai/config", json={"gemini_model": "gemini-0-nonexistent"})
    r = gemini.post("/api/ai/test", json={}).json()
    assert r["error_code"] == "model"


def test_proxy_validation(gemini):
    assert gemini.patch("/api/ai/config", json={"gemini_proxy": "127.0.0.1:7890"}).status_code == 400
    r = gemini.patch("/api/ai/config", json={"gemini_proxy": " http://127.0.0.1:7890 "})
    assert r.status_code == 200 and r.json()["providers"]["gemini"]["proxy"] == "http://127.0.0.1:7890"
    assert gemini.patch("/api/ai/config", json={"gemini_proxy": "socks5://127.0.0.1:7891"}).status_code == 200
    assert gemini.patch("/api/ai/config", json={"provider": "openai"}).status_code == 400


def test_per_minute_429_is_retried(gemini, mock_url):
    from paperlook.ai.client import GeminiClient

    c = GeminiClient("AIza-mock-rpm-retry-1", "gemini-3.5-flash-lite", base_url=mock_url, free_tier=False)
    waits = []
    c.on_wait = waits.append
    try:
        res = c.chat([{"role": "user", "content": "Reply with the single word: OK"}], kind="t")
    finally:
        c.close()
    assert res.content == "OK"
    assert waits and 1 <= waits[0] <= 3  # honoured retryDelay "1s"


def test_feature_fallbacks(gemini, mock_url):
    """Models without system instructions / without the 'minimal' level still work."""
    from paperlook.ai import client as ai_client

    c = ai_client.GeminiClient("AIza-mock-strict-1", "gemini-3.8-flash", base_url=mock_url, free_tier=False)
    try:
        data, res = c.chat_json([{"role": "system", "content": "返回 JSON，字段 abstract_zh"},
                                 {"role": "user", "content": "标题：X\n\n摘要：Y"}], kind="t")
    finally:
        c.close()
    assert data["abstract_zh"]
    assert res.usage["completion_tokens"] > 7  # thought tokens are counted as output
    last = mock_deepseek.gemini_requests[-1]["body"]
    assert "systemInstruction" not in last
    assert last["generationConfig"]["thinkingConfig"] == {"thinkingLevel": "low"}
    assert last["generationConfig"]["responseMimeType"] == "application/json"
    assert ai_client._gemini_compat["gemini-3.8-flash"]["system"] is False


def test_translation_uses_larger_chunks(gemini, mock_url):
    from paperlook.ai import client as ai_client
    from paperlook.ai.translate import Unit, chunk_units, translate_chunk

    units = [Unit(f"p{i}", "s1", "paragraph", f"Paragraph {i} with math $x_{i}$. " + "word " * 300) for i in range(12)]
    free = ai_client.GeminiClient("AIza-mock-ok-0123456789abcdef", "gemini-3.5-flash-lite", base_url=mock_url)
    assert free.chunk_chars > 4500 and free.chunk_units > 40 and free.max_concurrency == 2
    assert len(chunk_units(units, free.chunk_chars, free.chunk_units)) < len(chunk_units(units))
    free.free_tier = False
    try:
        out = translate_chunk(free, {"id": "p1", "title": "T"}, units[:3], "", "1 Intro", "（无）",
                              "你是学术论文翻译专家")
    finally:
        free.close()
    assert set(out) == {"p0", "p1", "p2"}
    assert out["p1"][0].startswith("【译】Paragraph 1 with math $x_1$")  # placeholders restored


def test_rate_limiter_window():
    from paperlook.ai.client import _RateLimiter

    now = [100.0]
    lim = _RateLimiter(clock=lambda: now[0])
    assert [lim.reserve("m", 2) for _ in range(2)] == [0, 0]
    assert lim.reserve("m", 2) == pytest.approx(60)    # third request waits for the window
    assert lim.reserve("m", 2) == pytest.approx(60)
    assert lim.reserve("m", 2) == pytest.approx(120)
    assert lim.reserve("other", 2) == 0                # per model
    now[0] = 400.0
    assert lim.reserve("m", 2) == 0


def test_pacific_quota_day():
    from paperlook.ai.client import gemini_quota_day_start, gemini_reset_hour_beijing

    summer = datetime(2026, 7, 1, 3, 0, tzinfo=timezone.utc)       # 20:00 PDT on June 30
    assert gemini_quota_day_start(summer) == datetime(2026, 6, 30, 7, 0, tzinfo=timezone.utc)
    assert gemini_reset_hour_beijing(summer) == 15
    winter = datetime(2026, 12, 1, 9, 0, tzinfo=timezone.utc)      # 01:00 PST on Dec 1
    assert gemini_quota_day_start(winter) == datetime(2026, 12, 1, 8, 0, tzinfo=timezone.utc)
    assert gemini_reset_hour_beijing(winter) == 16
    # DST boundaries 2026: starts Mar 8, ends Nov 1
    assert gemini_reset_hour_beijing(datetime(2026, 3, 8, 9, 59, tzinfo=timezone.utc)) == 16
    assert gemini_reset_hour_beijing(datetime(2026, 3, 8, 10, 0, tzinfo=timezone.utc)) == 15
    assert gemini_reset_hour_beijing(datetime(2026, 11, 1, 9, 0, tzinfo=timezone.utc)) == 16


def test_deepseek_still_default(client):
    cfg = client.get("/api/ai/config").json()
    assert cfg["provider"] == "deepseek" and cfg["label"] == "DeepSeek" and not cfg["configured"]
    r = client.post("/api/papers/x/ai/summary", json={})
    assert r.status_code in (400, 404)
