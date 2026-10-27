"""API key storage.

Order of preference:
1. OS credential store via `keyring` (Windows Credential Manager, macOS Keychain, Secret Service).
2. Windows DPAPI-encrypted file in the data directory (if keyring is unusable on Windows).
3. Plain file with owner-only permissions (last resort on other platforms; documented limitation).

Keys never leave the backend: the API only ever returns a masked form.
"""
from __future__ import annotations

import base64
import json
import logging
import os
import sys
import threading

from . import config

log = logging.getLogger(__name__)
_lock = threading.Lock()
_mem: dict[str, str] = {}  # in-process cache, avoids hitting the credential store on every request

# Known secret names.
DEEPSEEK = "deepseek_api_key"
GEMINI = "gemini_api_key"
OPENALEX = "openalex_api_key"
SEMANTIC_SCHOLAR = "semantic_scholar_api_key"
PUBMED = "pubmed_api_key"
ALL_NAMES = (DEEPSEEK, GEMINI, OPENALEX, SEMANTIC_SCHOLAR, PUBMED)


def _fallback_path():
    return config.DATA_DIR / "secrets.bin"


def _keyring():
    if os.environ.get("PAPERLOOK_DISABLE_KEYRING") == "1":
        return None
    try:
        import keyring  # type: ignore
        from keyring.backends import fail  # type: ignore

        kr = keyring.get_keyring()
        if isinstance(kr, fail.Keyring):
            return None
        return keyring
    except Exception:  # pragma: no cover - environment dependent
        return None


# ---- Windows DPAPI helpers (ctypes, no extra dependency) ----

def _dpapi(data: bytes, protect: bool) -> bytes:
    import ctypes
    from ctypes import wintypes

    class BLOB(ctypes.Structure):
        _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_char))]

    buf = ctypes.create_string_buffer(data, len(data))
    blob_in = BLOB(len(data), ctypes.cast(buf, ctypes.POINTER(ctypes.c_char)))
    blob_out = BLOB()
    crypt32 = ctypes.windll.crypt32
    fn = crypt32.CryptProtectData if protect else crypt32.CryptUnprotectData
    ok = fn(ctypes.byref(blob_in), None, None, None, None, 0, ctypes.byref(blob_out))
    if not ok:
        raise OSError("DPAPI operation failed")
    try:
        return ctypes.string_at(blob_out.pbData, blob_out.cbData)
    finally:
        ctypes.windll.kernel32.LocalFree(blob_out.pbData)


def _read_fallback() -> dict[str, str]:
    p = _fallback_path()
    if not p.exists():
        return {}
    raw = p.read_bytes()
    try:
        if sys.platform == "win32":
            raw = _dpapi(raw, protect=False)
        else:
            raw = base64.b64decode(raw)
        return json.loads(raw.decode("utf-8"))
    except Exception:
        log.warning("Could not read fallback secret file; ignoring it")
        return {}


def _write_fallback(data: dict[str, str]) -> None:
    p = _fallback_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    raw = json.dumps(data).encode("utf-8")
    raw = _dpapi(raw, protect=True) if sys.platform == "win32" else base64.b64encode(raw)
    p.write_bytes(raw)
    try:
        os.chmod(p, 0o600)
    except OSError:
        pass


def backend_name() -> str:
    kr = _keyring()
    if kr is not None:
        return "系统凭据管理器"
    return "本地加密文件 (Windows DPAPI)" if sys.platform == "win32" else "本地文件（仅限当前用户读取）"


def get_secret(name: str) -> str | None:
    with _lock:
        if name in _mem:
            return _mem[name] or None
        value: str | None = None
        kr = _keyring()
        if kr is not None:
            try:
                value = kr.get_password(config.KEYRING_SERVICE, name)
            except Exception:
                value = None
        if value is None:
            value = _read_fallback().get(name)
        _mem[name] = value or ""
        return value or None


def set_secret(name: str, value: str) -> None:
    value = value.strip()
    with _lock:
        kr = _keyring()
        stored = False
        if kr is not None:
            try:
                kr.set_password(config.KEYRING_SERVICE, name, value)
                stored = True
            except Exception:
                log.warning("keyring unavailable, using fallback secret file")
        if not stored:
            data = _read_fallback()
            data[name] = value
            _write_fallback(data)
        _mem[name] = value


def delete_secret(name: str) -> None:
    with _lock:
        kr = _keyring()
        if kr is not None:
            try:
                kr.delete_password(config.KEYRING_SERVICE, name)
            except Exception:
                pass
        data = _read_fallback()
        if name in data:
            data.pop(name)
            _write_fallback(data)
        _mem[name] = ""


def mask(value: str | None) -> str | None:
    if not value:
        return None
    v = value.strip()
    if len(v) <= 8:
        return "•" * len(v)
    return f"{v[:3]}…{v[-4:]}"
