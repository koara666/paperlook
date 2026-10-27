"""API-level tests (no network): settings, directions, security, AI gating, state, backups."""


def test_health_and_first_start(client):
    assert client.get("/api/health").json()["app"] == "PaperLook"
    s = client.get("/api/settings").json()
    assert s["daily_count"] == 5 and s["window_days"] == 7 and s["ai_rerank"] is False
    ai = client.get("/api/ai/config").json()
    assert ai["configured"] is False and ai["key_masked"] is None


def test_settings_validation_and_presets(client):
    s = client.patch("/api/settings", json={"daily_count": 999, "window_days": 0}).json()
    assert s["daily_count"] == 50 and s["window_days"] == 1
    s = client.patch("/api/settings", json={"weights": {"relevance": 0.0, "quality": 1, "freshness": 1}}).json()
    assert s["ranking_preset"] == "custom"
    assert abs(sum(s["weights"].values()) - 1) < 1e-3 and s["weights"]["relevance"] >= 0.2
    s = client.patch("/api/settings", json={"ranking_preset": "quality"}).json()
    assert s["weights"] == {"relevance": 0.45, "quality": 0.40, "freshness": 0.15}


def test_directions_crud(client):
    d = client.post("/api/directions", json={"name": "  Graph  Learning ", "keywords": ["GNN", "gnn", "graph, network"]}).json()
    assert d["name"] == "Graph Learning" and d["keywords"] == ["GNN", "graph network"]
    d = client.patch(f"/api/directions/{d['id']}", json={"weight": 9, "enabled": False}).json()
    assert d["weight"] == 5 and d["enabled"] is False
    assert client.post("/api/directions", json={"name": ""}).status_code == 400
    created = client.post("/api/directions/presets", json={"keys": ["cv", "ir", "cv"]}).json()
    assert len(created) == 2
    assert client.get("/api/settings").json()["onboarded"] is True
    client.delete(f"/api/directions/{d['id']}")
    assert len(client.get("/api/directions").json()) == 2


def test_recommend_requires_directions(client):
    import time

    job = client.post("/api/recommend/run", json={}).json()
    for _ in range(50):
        j = client.get(f"/api/jobs/{job['id']}").json()
        if j["status"] not in ("queued", "running"):
            break
        time.sleep(0.05)
    assert j["status"] == "failed" and j["error_code"] == "no_directions"


def test_security_middleware(client):
    assert client.get("/api/health", headers={"host": "evil.com"}).status_code == 403
    r = client.post("/api/settings", headers={"origin": "https://evil.com"})
    assert r.status_code == 403
    assert client.patch("/api/settings", json={}, headers={"origin": "http://127.0.0.1:8765"}).status_code == 200


def test_api_key_never_returned(client):
    r = client.put("/api/ai/key", json={"api_key": "sk-abcdef1234567890"}).json()
    assert r["configured"] and r["key_masked"] == "sk-…7890"
    body = client.get("/api/ai/config").text + client.get("/api/settings").text + client.get("/api/status").text
    assert "abcdef1234567890" not in body
    assert client.put("/api/ai/key", json={"api_key": "bad key"}).status_code == 400
    client.delete("/api/ai/key")
    assert client.get("/api/ai/config").json()["configured"] is False


def _insert_paper():
    from paperlook import papers

    return papers.upsert({"title": "A Sufficiently Long Paper Title For Testing", "abstract": "abs", "authors": ["A"],
                          "published": "2026-10-20", "date_quality": "exact", "arxiv_id": "2610.99999",
                          "categories": [], "sources": [{"source": "arxiv", "id": "2610.99999", "url": None}], "signals": {}})


def test_ai_requires_key_and_is_never_automatic(client):
    pid = _insert_paper()
    d = client.get(f"/api/papers/{pid}").json()
    assert all(d["ai"][k]["status"] in ("idle",) for k in ("summary", "modules", "contributions"))
    assert d["ai"]["translate"]["status"] == "idle"
    r = client.post(f"/api/papers/{pid}/ai/summary", json={})
    assert r.status_code == 400 and r.json()["code"] == "not_configured"
    # opening the paper triggered no jobs
    assert client.get("/api/jobs", params={"paper_id": pid}).json() == []


def test_feature_switch_shows_disabled(client):
    pid = _insert_paper()
    client.patch("/api/settings", json={"ai": {"features": {"modules": False}}})
    d = client.get(f"/api/papers/{pid}").json()
    assert d["ai"]["modules"]["status"] == "disabled" and d["ai"]["summary"]["status"] == "idle"


def test_state_and_library(client):
    pid = _insert_paper()
    st = client.patch(f"/api/papers/{pid}/state", json={"starred": True, "read": True}).json()
    assert st["starred"] and st["read"]
    lib = client.get("/api/papers", params={"filter": "starred"}).json()
    assert lib["total"] == 1
    client.patch(f"/api/papers/{pid}/state", json={"dismissed": True})
    assert client.get("/api/papers", params={"filter": "all"}).json()["total"] == 0
    assert client.get("/api/papers", params={"filter": "dismissed"}).json()["total"] == 1


def test_backup_roundtrip(client):
    pid = _insert_paper()
    client.post("/api/directions", json={"name": "X", "keywords": ["x"]})
    data = client.get("/api/data/export").json()
    assert data["app"] == "PaperLook" and len(data["papers"]) == 1
    assert "api_key" not in str(data).lower() or "sk-" not in str(data)
    client.post("/api/data/clear", json={"target": "history"})
    r = client.post("/api/data/import", json=data).json()
    assert r["ok"] and r["counts"]["papers"] == 1
    assert client.post("/api/data/import", json={"app": "Other"}).status_code == 400
