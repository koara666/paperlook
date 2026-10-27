"""Static paths and constants. Runtime user settings live in the database (see settings_store)."""
from __future__ import annotations

import os
from pathlib import Path

from . import __version__

APP_NAME = "PaperLook"
VERSION = __version__

PACKAGE_DIR = Path(__file__).resolve().parent
BACKEND_DIR = PACKAGE_DIR.parent
PROJECT_DIR = BACKEND_DIR.parent

# All user data (database, logs, caches) lives here. Never committed (see .gitignore).
DATA_DIR = Path(os.environ.get("PAPERLOOK_DATA_DIR", PROJECT_DIR / "data")).resolve()
STATIC_DIR = PACKAGE_DIR / "static"

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8765

USER_AGENT = f"PaperLook/{VERSION} (personal research reader; +https://github.com/)"

# Service name used for the OS credential store (Windows Credential Manager / macOS Keychain).
KEYRING_SERVICE = "PaperLook"


def db_path() -> Path:
    return DATA_DIR / "paperlook.db"


def log_dir() -> Path:
    return DATA_DIR / "logs"
