"""SQLite storage: one connection per thread, WAL mode, versioned migrations.

Kept deliberately small - plain SQL with JSON-encoded columns for flexible fields.
"""
from __future__ import annotations

import json
import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Iterator

from . import config

_local = threading.local()
_db_path: Path | None = None
_init_lock = threading.Lock()


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def loads(value: str | None, default: Any = None) -> Any:
    if value is None or value == "":
        return default
    try:
        return json.loads(value)
    except (ValueError, TypeError):
        return default


# Each entry is one migration step; append only, never edit an applied step.
MIGRATIONS: list[str] = [
    # 1: initial schema
    """
    CREATE TABLE IF NOT EXISTS settings (
        key TEXT PRIMARY KEY,
        value TEXT NOT NULL
    );

    CREATE TABLE IF NOT EXISTS directions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        keywords TEXT NOT NULL DEFAULT '[]',
        exclude TEXT NOT NULL DEFAULT '[]',
        categories TEXT NOT NULL DEFAULT '[]',
        weight INTEGER NOT NULL DEFAULT 3,
        enabled INTEGER NOT NULL DEFAULT 1,
        sort_order INTEGER NOT NULL DEFAULT 0,
        created_at TEXT,
        updated_at TEXT
    );

    CREATE TABLE IF NOT EXISTS papers (
        id TEXT PRIMARY KEY,
        title TEXT NOT NULL,
        title_norm TEXT NOT NULL,
        abstract TEXT,
        authors TEXT NOT NULL DEFAULT '[]',
        published TEXT,
        date_quality TEXT,
        date_note TEXT,
        updated TEXT,
        venue TEXT,
        doi TEXT,
        arxiv_id TEXT,
        openalex_id TEXT,
        s2_id TEXT,
        pmid TEXT,
        url TEXT,
        pdf_url TEXT,
        html_url TEXT,
        categories TEXT NOT NULL DEFAULT '[]',
        comment TEXT,
        journal_ref TEXT,
        sources TEXT NOT NULL DEFAULT '[]',
        signals TEXT NOT NULL DEFAULT '{}',
        created_at TEXT,
        updated_at TEXT
    );
    CREATE INDEX IF NOT EXISTS idx_papers_doi ON papers(doi);
    CREATE INDEX IF NOT EXISTS idx_papers_arxiv ON papers(arxiv_id);
    CREATE INDEX IF NOT EXISTS idx_papers_title_norm ON papers(title_norm);

    CREATE TABLE IF NOT EXISTS paper_state (
        paper_id TEXT PRIMARY KEY REFERENCES papers(id) ON DELETE CASCADE,
        read_at TEXT,
        starred INTEGER NOT NULL DEFAULT 0,
        dismissed INTEGER NOT NULL DEFAULT 0,
        opened_at TEXT,
        note TEXT
    );

    CREATE TABLE IF NOT EXISTS rec_batches (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        created_at TEXT NOT NULL,
        day TEXT NOT NULL,
        params TEXT NOT NULL DEFAULT '{}',
        stats TEXT NOT NULL DEFAULT '{}',
        message TEXT
    );
    CREATE INDEX IF NOT EXISTS idx_batches_day ON rec_batches(day);

    CREATE TABLE IF NOT EXISTS recommendations (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        batch_id INTEGER NOT NULL REFERENCES rec_batches(id) ON DELETE CASCADE,
        paper_id TEXT NOT NULL REFERENCES papers(id) ON DELETE CASCADE,
        rank INTEGER,
        score REAL,
        breakdown TEXT NOT NULL DEFAULT '{}',
        reasons TEXT NOT NULL DEFAULT '[]',
        direction_id INTEGER,
        direction_name TEXT,
        ai TEXT,
        created_at TEXT
    );
    CREATE INDEX IF NOT EXISTS idx_rec_paper ON recommendations(paper_id);
    CREATE INDEX IF NOT EXISTS idx_rec_batch ON recommendations(batch_id);

    CREATE TABLE IF NOT EXISTS fulltext (
        paper_id TEXT PRIMARY KEY REFERENCES papers(id) ON DELETE CASCADE,
        source TEXT,
        source_url TEXT,
        doc TEXT,
        fetched_at TEXT
    );

    CREATE TABLE IF NOT EXISTS ai_results (
        paper_id TEXT NOT NULL REFERENCES papers(id) ON DELETE CASCADE,
        kind TEXT NOT NULL,
        content TEXT,
        basis TEXT,
        model TEXT,
        usage TEXT,
        created_at TEXT,
        PRIMARY KEY (paper_id, kind)
    );

    CREATE TABLE IF NOT EXISTS translations (
        paper_id TEXT NOT NULL REFERENCES papers(id) ON DELETE CASCADE,
        unit_id TEXT NOT NULL,
        section_id TEXT,
        text TEXT,
        flags TEXT,
        model TEXT,
        created_at TEXT,
        PRIMARY KEY (paper_id, unit_id)
    );

    CREATE TABLE IF NOT EXISTS jobs (
        id TEXT PRIMARY KEY,
        kind TEXT NOT NULL,
        paper_id TEXT,
        status TEXT NOT NULL,
        progress INTEGER NOT NULL DEFAULT 0,
        total INTEGER NOT NULL DEFAULT 0,
        message TEXT,
        error TEXT,
        result TEXT,
        created_at TEXT,
        updated_at TEXT
    );
    CREATE INDEX IF NOT EXISTS idx_jobs_paper ON jobs(paper_id, kind);

    CREATE TABLE IF NOT EXISTS api_usage (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        at TEXT NOT NULL,
        kind TEXT,
        model TEXT,
        paper_id TEXT,
        prompt_tokens INTEGER NOT NULL DEFAULT 0,
        completion_tokens INTEGER NOT NULL DEFAULT 0,
        cache_hit_tokens INTEGER NOT NULL DEFAULT 0,
        ok INTEGER NOT NULL DEFAULT 1
    );

    CREATE TABLE IF NOT EXISTS kv_cache (
        key TEXT PRIMARY KEY,
        value TEXT,
        fetched_at TEXT
    );
    """,
]


def configure(path: Path | None = None) -> None:
    """Point the module at a database file (tests use a temp file) and run migrations."""
    global _db_path
    with _init_lock:
        _db_path = Path(path) if path else config.db_path()
        _db_path.parent.mkdir(parents=True, exist_ok=True)
        # Drop this thread's cached connection if it points elsewhere.
        conn = getattr(_local, "conn", None)
        if conn is not None and getattr(_local, "path", None) != _db_path:
            conn.close()
            _local.conn = None
        _migrate()


def _connect() -> sqlite3.Connection:
    if _db_path is None:
        configure()
    conn = getattr(_local, "conn", None)
    if conn is None or getattr(_local, "path", None) != _db_path:
        conn = sqlite3.connect(_db_path, timeout=30, check_same_thread=False, isolation_level=None)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute("PRAGMA busy_timeout=30000")
        conn.execute("PRAGMA synchronous=NORMAL")
        _local.conn = conn
        _local.path = _db_path
    return conn


def _migrate() -> None:
    conn = sqlite3.connect(_db_path, timeout=30, isolation_level=None)
    try:
        conn.execute("PRAGMA journal_mode=WAL")
        version = conn.execute("PRAGMA user_version").fetchone()[0]
        for i, script in enumerate(MIGRATIONS, start=1):
            if i <= version:
                continue
            conn.execute("BEGIN")
            try:
                for stmt in _split_sql(script):
                    conn.execute(stmt)
                conn.execute(f"PRAGMA user_version = {i}")
                conn.execute("COMMIT")
            except Exception:
                conn.execute("ROLLBACK")
                raise
    finally:
        conn.close()


def _split_sql(script: str) -> list[str]:
    return [s.strip() for s in script.split(";") if s.strip()]


def query(sql: str, params: Iterable[Any] = ()) -> list[dict[str, Any]]:
    cur = _connect().execute(sql, tuple(params))
    return [dict(r) for r in cur.fetchall()]


def query_one(sql: str, params: Iterable[Any] = ()) -> dict[str, Any] | None:
    cur = _connect().execute(sql, tuple(params))
    row = cur.fetchone()
    return dict(row) if row else None


def execute(sql: str, params: Iterable[Any] = ()) -> int:
    """Execute a statement; returns lastrowid."""
    cur = _connect().execute(sql, tuple(params))
    return cur.lastrowid or 0


def executemany(sql: str, rows: Iterable[Iterable[Any]]) -> None:
    _connect().executemany(sql, [tuple(r) for r in rows])


@contextmanager
def transaction() -> Iterator[sqlite3.Connection]:
    conn = _connect()
    conn.execute("BEGIN IMMEDIATE")
    try:
        yield conn
        conn.execute("COMMIT")
    except Exception:
        conn.execute("ROLLBACK")
        raise


# ---- tiny key/value cache (HF daily lists, venue statistics, candidate pools) ----

def cache_get(key: str, max_age_seconds: float | None = None) -> Any:
    row = query_one("SELECT value, fetched_at FROM kv_cache WHERE key = ?", (key,))
    if not row:
        return None
    if max_age_seconds is not None:
        try:
            fetched = datetime.fromisoformat(row["fetched_at"])
            if (datetime.now(timezone.utc) - fetched).total_seconds() > max_age_seconds:
                return None
        except (TypeError, ValueError):
            return None
    return loads(row["value"])


def cache_set(key: str, value: Any) -> None:
    execute(
        "INSERT INTO kv_cache(key, value, fetched_at) VALUES(?,?,?) "
        "ON CONFLICT(key) DO UPDATE SET value=excluded.value, fetched_at=excluded.fetched_at",
        (key, dumps(value), now_iso()),
    )


def file_size_bytes() -> int:
    if _db_path is None:
        return 0
    total = 0
    for suffix in ("", "-wal", "-shm"):
        p = Path(str(_db_path) + suffix)
        if p.exists():
            total += p.stat().st_size
    return total
