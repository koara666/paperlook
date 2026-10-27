import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# Never touch the user's real credential store or data directory from tests.
os.environ["PAPERLOOK_DISABLE_KEYRING"] = "1"


@pytest.fixture()
def tmp_db(tmp_path, monkeypatch):
    from paperlook import config, db, secrets_store

    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    secrets_store._mem.clear()
    db.configure(tmp_path / "test.db")
    yield tmp_path
    secrets_store._mem.clear()


@pytest.fixture()
def client(tmp_db):
    from fastapi.testclient import TestClient

    from paperlook.main import create_app

    return TestClient(create_app())
