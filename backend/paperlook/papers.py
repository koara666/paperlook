"""Paper repository: persistence of merged paper records and per-paper user state."""
from __future__ import annotations

import hashlib
from typing import Any

from . import db
from .recommend.dedupe import identity_keys
from .textutil import title_key

JSON_FIELDS = {"authors": [], "categories": [], "sources": [], "signals": {}}
COLUMNS = ["title", "title_norm", "abstract", "authors", "published", "date_quality", "date_note", "updated", "venue",
           "doi", "arxiv_id", "openalex_id", "s2_id", "pmid", "url", "pdf_url", "html_url", "categories", "comment",
           "journal_ref", "sources", "signals"]


def make_id(p: dict[str, Any]) -> str:
    keys = identity_keys(p)
    basis = keys[0] if keys else "title:" + title_key(p.get("title"))
    return "p" + hashlib.sha1(basis.encode("utf-8")).hexdigest()[:15]


def _decode(row: dict[str, Any]) -> dict[str, Any]:
    out = dict(row)
    for f, default in JSON_FIELDS.items():
        out[f] = db.loads(out.get(f), default)
    return out


def find_existing(p: dict[str, Any]) -> str | None:
    checks = [("arxiv_id", p.get("arxiv_id")), ("doi", p.get("doi")), ("pmid", p.get("pmid")),
              ("openalex_id", p.get("openalex_id")), ("title_norm", title_key(p.get("title")) or None)]
    for col, val in checks:
        if not val:
            continue
        if col == "title_norm" and len(val) < 24:
            continue
        r = db.query_one(f"SELECT id FROM papers WHERE {col} = ? LIMIT 1", (val,))
        if r:
            return r["id"]
    return None


def upsert(p: dict[str, Any]) -> str:
    """Insert or merge a paper; returns its id."""
    now = db.now_iso()
    existing_id = find_existing(p)
    record = {k: p.get(k) for k in COLUMNS}
    record["title_norm"] = title_key(p.get("title"))
    if existing_id:
        cur = get_paper(existing_id) or {}
        merged: dict[str, Any] = {}
        for k in COLUMNS:
            new, old = record.get(k), cur.get(k)
            if k == "signals":
                merged[k] = {**(old or {}), **(new or {})}
            elif k == "sources":
                seen = {(s["source"], s["id"]) for s in (old or [])}
                merged[k] = list(old or []) + [s for s in (new or []) if (s["source"], s["id"]) not in seen]
            else:
                merged[k] = new if new not in (None, "", []) else old
        sets = ", ".join(f"{k} = ?" for k in COLUMNS)
        vals = [db.dumps(merged[k]) if k in JSON_FIELDS else merged[k] for k in COLUMNS]
        db.execute(f"UPDATE papers SET {sets}, updated_at = ? WHERE id = ?", (*vals, now, existing_id))
        return existing_id
    pid = make_id(p)
    vals = [db.dumps(record[k] if record[k] is not None else JSON_FIELDS[k]) if k in JSON_FIELDS else record[k] for k in COLUMNS]
    db.execute(
        f"INSERT INTO papers(id, {', '.join(COLUMNS)}, created_at, updated_at) VALUES(?, {', '.join('?' for _ in COLUMNS)}, ?, ?) "
        "ON CONFLICT(id) DO NOTHING",
        (pid, *vals, now, now),
    )
    return pid


def get_paper(paper_id: str) -> dict[str, Any] | None:
    r = db.query_one("SELECT * FROM papers WHERE id = ?", (paper_id,))
    return _decode(r) if r else None


def get_state(paper_id: str) -> dict[str, Any]:
    r = db.query_one("SELECT * FROM paper_state WHERE paper_id = ?", (paper_id,))
    if not r:
        return {"read": False, "starred": False, "dismissed": False, "read_at": None, "opened_at": None, "note": None}
    return {"read": bool(r["read_at"]), "read_at": r["read_at"], "starred": bool(r["starred"]),
            "dismissed": bool(r["dismissed"]), "opened_at": r["opened_at"], "note": r["note"]}


def set_state(paper_id: str, **fields: Any) -> dict[str, Any]:
    db.execute("INSERT OR IGNORE INTO paper_state(paper_id) VALUES(?)", (paper_id,))
    now = db.now_iso()
    if "read" in fields:
        db.execute("UPDATE paper_state SET read_at = ? WHERE paper_id = ?", (now if fields["read"] else None, paper_id))
    if "starred" in fields:
        db.execute("UPDATE paper_state SET starred = ? WHERE paper_id = ?", (1 if fields["starred"] else 0, paper_id))
    if "dismissed" in fields:
        db.execute("UPDATE paper_state SET dismissed = ? WHERE paper_id = ?", (1 if fields["dismissed"] else 0, paper_id))
    if fields.get("opened"):
        db.execute("UPDATE paper_state SET opened_at = ? WHERE paper_id = ?", (now, paper_id))
    if "note" in fields:
        db.execute("UPDATE paper_state SET note = ? WHERE paper_id = ?", ((fields["note"] or "")[:20000], paper_id))
    return get_state(paper_id)


def seen_identity_keys() -> set[str]:
    """Identity keys of papers already recommended or dismissed - never recommend them again."""
    rows = db.query(
        "SELECT p.arxiv_id, p.doi, p.pmid, p.title FROM papers p "
        "WHERE p.id IN (SELECT paper_id FROM recommendations) "
        "OR p.id IN (SELECT paper_id FROM paper_state WHERE dismissed = 1)"
    )
    keys: set[str] = set()
    for r in rows:
        keys.update(identity_keys(r))
    return keys


def ai_status_summary(paper_ids: list[str]) -> dict[str, dict[str, Any]]:
    """Which AI outputs exist per paper (for list badges)."""
    out: dict[str, dict[str, Any]] = {pid: {} for pid in paper_ids}
    if not paper_ids:
        return out
    marks = ",".join("?" for _ in paper_ids)
    for r in db.query(f"SELECT paper_id, kind FROM ai_results WHERE paper_id IN ({marks})", paper_ids):
        out[r["paper_id"]][r["kind"]] = True
    for r in db.query(f"SELECT paper_id, COUNT(*) AS n FROM translations WHERE paper_id IN ({marks}) GROUP BY paper_id", paper_ids):
        out[r["paper_id"]]["translation_units"] = r["n"]
    return out


def card(p: dict[str, Any], state: dict[str, Any] | None = None) -> dict[str, Any]:
    """Compact representation for lists."""
    return {
        "id": p["id"], "title": p["title"], "authors": p["authors"][:8], "author_count": len(p["authors"]),
        "abstract": p.get("abstract"), "published": p.get("published"), "date_quality": p.get("date_quality"),
        "venue": p.get("venue"), "arxiv_id": p.get("arxiv_id"), "doi": p.get("doi"), "url": p.get("url"),
        "pdf_url": p.get("pdf_url"), "categories": p.get("categories")[:4],
        "sources": [s["source"] for s in p.get("sources", [])],
        "state": state if state is not None else get_state(p["id"]),
    }
