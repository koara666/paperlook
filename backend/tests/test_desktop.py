"""Desktop (packaged) mode helpers that can be tested without opening a window."""
import sys
from pathlib import Path


def test_data_dir_source_vs_packaged(monkeypatch, tmp_path):
    from paperlook import config

    assert config._default_data_dir() == config.PROJECT_DIR / "data"
    monkeypatch.setattr(config, "FROZEN", True)
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    assert config._default_data_dir() == tmp_path / "PaperLook"


def test_port_selection(client, monkeypatch):
    """A running instance on the same data directory is reused; other PaperLook instances are skipped."""
    from paperlook import config, desktop

    mine = {"app": "PaperLook", "data_dir": str(config.DATA_DIR)}
    other = {"app": "PaperLook", "data_dir": str(Path(config.DATA_DIR) / "elsewhere")}
    monkeypatch.setattr(desktop, "_status", lambda port: {8765: other, 8766: mine}.get(port))
    assert desktop._pick_port(8765) == (8766, True)
    monkeypatch.setattr(desktop, "_status", lambda port: {8765: other}.get(port))
    monkeypatch.setattr("paperlook.__main__._port_free", lambda port: port != 8765)
    assert desktop._pick_port(8765) == (8766, False)


def test_status_reports_packaged(client):
    st = client.get("/api/status").json()
    assert st["packaged"] is False
