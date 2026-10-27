"""Static paths and constants. Runtime user settings live in the database (see settings_store)."""
from __future__ import annotations

import os
import sys
from pathlib import Path

from . import __version__

APP_NAME = "PaperLook"
VERSION = __version__

PACKAGE_DIR = Path(__file__).resolve().parent
BACKEND_DIR = PACKAGE_DIR.parent
PROJECT_DIR = BACKEND_DIR.parent

# True in the packaged desktop app (PyInstaller).
FROZEN = bool(getattr(sys, "frozen", False))


def _default_data_dir() -> Path:
    if not FROZEN:
        return PROJECT_DIR / "data"  # running from source: next to the code (never committed)
    # Installed app: the per-user data folder, kept when the app is upgraded or uninstalled.
    if sys.platform == "win32":
        base = Path(os.environ.get("LOCALAPPDATA") or Path.home() / "AppData" / "Local")
    elif sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support"
    else:
        base = Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local" / "share")
    return base / APP_NAME


# All user data (database, logs, caches) lives here.
DATA_DIR = Path(os.environ.get("PAPERLOOK_DATA_DIR") or _default_data_dir()).resolve()
STATIC_DIR = PACKAGE_DIR / "static"

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8765

GITHUB_REPO = "koara666/paperlook"
USER_AGENT = f"PaperLook/{VERSION} (personal research reader; +https://github.com/{GITHUB_REPO})"

# Service name used for the OS credential store (Windows Credential Manager / macOS Keychain).
KEYRING_SERVICE = "PaperLook"


def db_path() -> Path:
    return DATA_DIR / "paperlook.db"


def log_dir() -> Path:
    return DATA_DIR / "logs"
