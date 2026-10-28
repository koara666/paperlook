"""Source request retries (HTTP 429) and the short cache for pools where a source failed."""
import httpx
import pytest

from paperlook.sources import base
from paperlook.sources.base import SourceError, get_with_retry


class FakeClient:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = 0

    def get(self, url, **kwargs):
        self.calls += 1
        return self.responses.pop(0)


def _resp(code, headers=None):
    return httpx.Response(code, headers=headers or {}, text="ok", request=httpx.Request("GET", "https://x"))


def test_429_waits_retry_after_then_succeeds(monkeypatch):
    sleeps = []
    monkeypatch.setattr(base.time, "sleep", sleeps.append)
    client = FakeClient([_resp(429, {"Retry-After": "7"}), _resp(429), _resp(200)])
    monkeypatch.setattr(base, "http", lambda: client)
    r = get_with_retry("https://x", source_name="arXiv", backoff_429=10.0)
    assert r.status_code == 200 and client.calls == 3
    assert sleeps == [7.0, 20.0]  # server's Retry-After first, then backoff_429 × attempt


def test_429_gives_up_with_clear_message(monkeypatch):
    monkeypatch.setattr(base.time, "sleep", lambda s: None)
    monkeypatch.setattr(base, "http", lambda: FakeClient([_resp(429, {"Retry-After": "999"})] * 3))
    with pytest.raises(SourceError) as e:
        get_with_retry("https://x", source_name="OpenAlex")
    assert "429" in e.value.message and "每日" not in e.value.message


def test_arxiv_429_message_and_single_request_per_direction(monkeypatch):
    from datetime import date

    from paperlook.sources.arxiv import ArxivSource
    from paperlook.sources.base import SourceQuery

    seen = []

    def fake_get(url, *, params=None, **kw):
        seen.append(params)
        raise SourceError("arXiv 限制了访问频率（HTTP 429）")

    monkeypatch.setattr("paperlook.sources.arxiv.get_with_retry", fake_get)
    q = SourceQuery(keywords=["graph neural network"], exclude=[], categories=["cs.LG"],
                    date_from=date(2026, 10, 21), date_to=date(2026, 10, 28), max_results=200)
    with pytest.raises(SourceError) as e:
        ArxivSource().search(q)
    assert seen[0]["max_results"] == 200 and len(seen) == 1
    assert "自动重试" in e.value.message and "429" in e.value.message


def test_partial_pool_is_reused_only_briefly(tmp_db, monkeypatch):
    from datetime import datetime, timedelta, timezone

    from paperlook import db, directions
    from paperlook.jobs import Job
    from paperlook.recommend import engine

    directions.create_direction({"name": "CV", "keywords": ["object detection"], "exclude": [], "categories": [], "weight": 3})
    calls = []

    def fake_fetch(job, dirs, sources, date_from, today):
        calls.append(1)
        return [], {"arxiv": {"name": "arXiv", "fetched": 101, "errors": ["arXiv 暂时限制了访问频率（HTTP 429）"]},
                    "openalex": {"name": "OpenAlex", "fetched": 0, "errors": []}}

    monkeypatch.setattr(engine, "_fetch_pool", fake_fetch)
    engine.run(Job("recommend", None), "more")
    engine.run(Job("recommend", None), "more")
    assert len(calls) == 1  # reused right away
    old = (datetime.now(timezone.utc) - timedelta(minutes=11)).isoformat(timespec="seconds")
    db.execute("UPDATE kv_cache SET fetched_at = ? WHERE key LIKE 'pool:%'", (old,))
    engine.run(Job("recommend", None), "more")
    assert len(calls) == 2  # partial pool older than 10 minutes: the failed source is tried again
