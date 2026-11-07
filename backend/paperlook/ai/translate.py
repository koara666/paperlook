"""Full-text translation.

Pipeline:
 1. Structured document (fulltext/) -> translatable units (section titles, paragraphs, list items,
    figure/table captions). Equations, code, table bodies and references are never sent.
 2. Inline math `$...$` is replaced by placeholders ⟦M1⟧... before sending and restored after,
    so formulas can never be "translated" or mangled.
 3. A glossary of key terms is generated once per paper and included in every request
    -> consistent terminology across chunks.
 4. Units are grouped into chunks per section (~CHUNK_CHARS), translated concurrently with the
    previous paragraph passed as read-only context.
 5. Each unit is saved as soon as its chunk succeeds -> failures/cancellation lose nothing and
    "continue" only translates what is missing. Sections can be re-translated individually.

The target is the AI output language (zh/en/ja/ko); the source language is detected from the document,
so papers in any language can be translated. A paper already written in the target language is not.
Translations and glossaries are stored per target language.
"""
from __future__ import annotations

import logging
import re
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from typing import Any

from .. import db, papers as papers_repo, settings_store
from ..errors import AppError
from ..fulltext import fetcher
from ..fulltext.model import plain_text, units as doc_units
from ..i18n import t
from ..jobs import Job, JobCancelled
from ..textutil import detect_language
from . import prompts
from .client import AIError, BaseClient, get_client

log = logging.getLogger(__name__)

CHUNK_CHARS = 4500
FATAL_CODES = {"auth", "balance", "not_configured", "endpoint", "model", "region", "quota_daily", "proxy"}
_INLINE_MATH = re.compile(r"(?<!\\)\$\$(.+?)(?<!\\)\$\$|(?<!\\)\$(.+?)(?<!\\)\$", re.S)
_PLACEHOLDER = re.compile(r"⟦M(\d+)⟧")


@dataclass
class Unit:
    id: str
    section_id: str
    kind: str
    text: str


def unit_kind(unit_id: str) -> str:
    if unit_id.endswith("::title"):
        return "title"
    if unit_id.endswith("::caption"):
        return "caption"
    if "::" in unit_id:
        return "list_item"
    return "paragraph"


def mask_math(text: str) -> tuple[str, dict[str, str]]:
    mapping: dict[str, str] = {}

    def repl(m: re.Match[str]) -> str:
        key = f"⟦M{len(mapping) + 1}⟧"
        mapping[key] = m.group(0)
        return key

    return _INLINE_MATH.sub(repl, text), mapping


def unmask(text: str, mapping: dict[str, str]) -> tuple[str, int]:
    """Restore placeholders; returns (text, number_of_missing_placeholders)."""
    found = set()

    def repl(m: re.Match[str]) -> str:
        key = m.group(0)
        found.add(key)
        return mapping.get(key, key)

    out = _PLACEHOLDER.sub(repl, text)
    return out, len(set(mapping) - found)


def collect_units(doc: dict[str, Any], include_appendix: bool) -> list[Unit]:
    return [Unit(uid, sid, unit_kind(uid), text) for uid, sid, text in
            doc_units(doc, include_references=False, include_appendix=include_appendix)]


MAX_UNITS_PER_CHUNK = 40


def chunk_units(units: list[Unit], max_chars: int = CHUNK_CHARS, max_units: int = MAX_UNITS_PER_CHUNK) -> list[list[Unit]]:
    """Group consecutive units into requests of ~max_chars. Small neighbouring sections share a
    request (fewer calls, less repeated prompt overhead); a new section starts a new chunk only
    when the current one is already more than half full, so section context stays coherent."""
    chunks: list[list[Unit]] = []
    cur: list[Unit] = []
    size = 0
    for u in units:
        new_section = bool(cur) and u.section_id != cur[-1].section_id
        if cur and (size + len(u.text) > max_chars or len(cur) >= max_units
                    or (new_section and size > max_chars * 0.5)):
            chunks.append(cur)
            cur, size = [], 0
        cur.append(u)
        size += len(u.text)
    if cur:
        chunks.append(cur)
    return chunks


def doc_language(doc: dict[str, Any], paper: dict[str, Any] | None = None) -> str | None:
    """Language the full text is written in (the metadata language can differ: CJK journals often
    publish English titles and abstracts for papers written in Chinese, Japanese or Korean)."""
    sample = plain_text(doc, max_chars=6000, include_appendix=False)
    return detect_language(sample, (paper or {}).get("language")) or (paper or {}).get("language")


def translated_map(paper_id: str, lang: str | None = None) -> dict[str, dict[str, Any]]:
    lang = lang or prompts.output_language()
    rows = db.query("SELECT unit_id, text, flags FROM translations WHERE paper_id = ? AND lang = ?", (paper_id, lang))
    return {r["unit_id"]: {"text": r["text"], "flags": db.loads(r["flags"], [])} for r in rows}


def translated_languages(paper_id: str) -> list[str]:
    return [r["lang"] for r in db.query("SELECT DISTINCT lang FROM translations WHERE paper_id = ?", (paper_id,))]


def get_glossary(paper_id: str, lang: str | None = None) -> list[dict[str, Any]]:
    lang = lang or prompts.output_language()
    r = db.query_one("SELECT content FROM ai_results WHERE paper_id = ? AND kind = 'glossary' AND lang = ?",
                     (paper_id, lang))
    terms = (db.loads(r["content"], {}) or {}).get("terms", []) if r else []
    # Glossaries before 1.3 used {"en", "zh"}.
    return [{"src": x.get("src") or x.get("en") or "", "tgt": x.get("tgt") or x.get("zh") or "", "keep": bool(x.get("keep"))}
            for x in terms if isinstance(x, dict)]


def _section_path(doc: dict[str, Any]) -> dict[str, str]:
    path: dict[str, str] = {}
    stack: list[tuple[int, str]] = []
    for s in doc["sections"]:
        label = " ".join(x for x in [s.get("number"), s.get("title")] if x)
        while stack and stack[-1][0] >= s["level"]:
            stack.pop()
        stack.append((s["level"], label))
        path[s["id"]] = " > ".join(x[1] for x in stack)
    return path


def ensure_glossary(client: BaseClient, paper: dict[str, Any], doc: dict[str, Any], source: str | None,
                    lang: str) -> list[dict[str, Any]]:
    existing = get_glossary(paper["id"], lang)
    if existing:
        return existing
    headings = [" ".join(x for x in [s.get("number"), s.get("title")] if x) for s in doc["sections"]
                if s["kind"] in ("body", "appendix")]
    intro = ""
    for s in doc["sections"]:
        if s["kind"] == "body":
            intro = " ".join(b.get("text", "") for b in s["blocks"] if b["type"] == "paragraph")[:3000]
            break
    user = (f"{prompts.glossary_task(source, lang)}\n\nTitle: {paper['title']}\n\nAbstract: {paper.get('abstract') or ''}\n\n"
            f"Section headings:\n" + "\n".join(headings[:60]) + f"\n\nFrom the introduction:\n{intro}")
    data, res = client.chat_json([{"role": "system", "content": prompts.glossary_system(lang)}, {"role": "user", "content": user}],
                                 thinking=False, max_tokens=4000, temperature=0.2, kind="glossary", paper_id=paper["id"])
    terms = []
    for x in data.get("terms", []) if isinstance(data.get("terms"), list) else []:
        src, tgt = (x.get("src") or x.get("en"), x.get("tgt") or x.get("zh")) if isinstance(x, dict) else (None, None)
        if src and tgt:
            terms.append({"src": str(src)[:80], "tgt": str(tgt)[:80], "keep": bool(x.get("keep"))})
    from .analyze import save_result
    save_result(paper["id"], "glossary", lang, {"terms": terms}, None, res.model, res.usage)
    return terms


def _glossary_text(terms: list[dict[str, Any]]) -> str:
    if not terms:
        return "(none)"
    return "\n".join(f"- {x['src']} → {x['tgt']}" + (" (keep as is)" if x.get("keep") else "") for x in terms[:60])


def translate_chunk(client: BaseClient, paper: dict[str, Any], chunk: list[Unit], context: str, section_path: str,
                    glossary: str, system: str) -> dict[str, tuple[str, list[str]]]:
    """Translate one chunk. Returns {unit_id: (text, flags)}. Retries once for missing ids/placeholders."""
    masked = {u.id: mask_math(u.text) for u in chunk}
    pending = list(chunk)
    results: dict[str, tuple[str, list[str]]] = {}
    for attempt in range(2):
        items = [{"id": u.id, "kind": u.kind, "text": masked[u.id][0]} for u in pending]
        # Constant per-paper prefix first (title + glossary) so the provider's prompt cache can hit.
        user = (f"Paper title: {paper['title']}\n\nGlossary (original → translation):\n{glossary}\n\n"
                f"Current section: {section_path}\n\n"
                + (f"Preceding text (context only - do not translate): {context}\n\n" if context else "")
                + "Items to translate:\n" + db.dumps({"items": items}))
        data, _ = client.chat_json([{"role": "system", "content": system}, {"role": "user", "content": user}],
                                   thinking=False, max_tokens=8192, temperature=0.3, kind="translate", paper_id=paper["id"])
        got: dict[str, str] = {}
        for x in data.get("translations", []) if isinstance(data.get("translations"), list) else []:
            if isinstance(x, dict) and x.get("id") in masked and isinstance(x.get("text"), str) and x["text"].strip():
                got[x["id"]] = x["text"].strip()
        retry: list[Unit] = []
        for u in pending:
            if u.id not in got:
                retry.append(u)
                continue
            text, missing = unmask(got[u.id], masked[u.id][1])
            if missing and attempt == 0:
                retry.append(u)
                continue
            flags = ["math_missing"] if missing else []
            results[u.id] = (text, flags)
        pending = retry
        if not pending:
            break
    return results


def _save(paper_id: str, lang: str, unit: Unit, text: str, flags: list[str], model: str) -> None:
    db.execute(
        "INSERT INTO translations(paper_id, unit_id, lang, section_id, text, flags, model, created_at) VALUES(?,?,?,?,?,?,?,?) "
        "ON CONFLICT(paper_id, unit_id, lang) DO UPDATE SET text=excluded.text, flags=excluded.flags, model=excluded.model, "
        "created_at=excluded.created_at",
        (paper_id, unit.id, lang, unit.section_id, text, db.dumps(flags) if flags else None, model, db.now_iso()),
    )


def run(job: Job, paper_id: str, section_ids: list[str] | None = None, force: bool = False) -> dict[str, Any]:
    settings = settings_store.get_settings()
    if not settings["ai"]["features"].get("translate", True):
        raise AppError(t("err.feature_disabled", feature=t("ai.label.translate")), code="feature_disabled")
    paper = papers_repo.get_paper(paper_id)
    if not paper:
        raise AppError(t("err.paper_not_found"), status_code=404)
    lang = prompts.output_language()
    client = get_client()
    client.on_wait = lambda sec: job.update(message=t("job.tr.wait", provider=client.label, n=int(sec + 0.5)), force=True)
    try:
        job.update(message=t("job.tr.prepare"), force=True)
        doc = fetcher.ensure(paper, job)
        job.check_cancelled()
        source = doc_language(doc, paper)
        if source == lang:
            raise AppError(t("err.translate_same_language", language=t(f"lang.{lang}")), code="same_language")

        all_units = collect_units(doc, settings["ai"]["translate_appendix"])
        if section_ids:
            wanted = set(section_ids)
            all_units = [u for u in all_units if u.section_id in wanted]
            if force:
                marks = ",".join("?" for _ in wanted)
                db.execute(f"DELETE FROM translations WHERE paper_id = ? AND lang = ? AND section_id IN ({marks})",
                           (paper_id, lang, *wanted))
        elif force:
            db.execute("DELETE FROM translations WHERE paper_id = ? AND lang = ?", (paper_id, lang))
        done = translated_map(paper_id, lang)
        todo = [u for u in all_units if u.id not in done]
        if not todo:
            job.update(progress=len(all_units), total=len(all_units), force=True)
            job.finish(t("job.tr.already_done"))
            return {"translated": 0, "failed": 0, "total": len(all_units)}

        job.update(message=t("job.tr.glossary"), progress=len(all_units) - len(todo), total=len(all_units), force=True)
        try:
            glossary = ensure_glossary(client, paper, doc, source, lang)
        except AIError as e:
            if e.code in FATAL_CODES:
                raise
            log.warning("glossary failed: %s", e.message)
            glossary = []
        gtext = _glossary_text(glossary)
        system = prompts.translation_system(settings["ai"]["keep_english_terms"], source, lang)
        paths = _section_path(doc)
        titles = {s["id"]: " ".join(x for x in [s.get("number"), s.get("title")] if x) for s in doc["sections"]}

        # previous unit text (original) as read-only context for each chunk
        index = {u.id: i for i, u in enumerate(collect_units(doc, True))}
        flat = collect_units(doc, True)
        chunks = chunk_units(todo, client.chunk_chars, client.chunk_units)
        failed: list[str] = []
        errors: list[str] = []
        fatal: list[AIError] = []
        lock = threading.Lock()

        def work(chunk: list[Unit]) -> None:
            if job.cancelled or fatal:
                return
            first = index.get(chunk[0].id, 0)
            ctx = flat[first - 1].text[-400:] if first > 0 else ""
            sec_title = titles.get(chunk[0].section_id, "")
            sec_ids = list(dict.fromkeys(u.section_id for u in chunk))
            path = "; ".join(paths.get(sid, "") for sid in sec_ids[:4])
            job.update(message=t("job.tr.section", section=sec_title[:40]))
            try:
                res = translate_chunk(client, paper, chunk, ctx, path, gtext, system)
            except AIError as e:
                with lock:
                    if e.code in FATAL_CODES:
                        fatal.append(e)
                    errors.append(e.message)
                    failed.extend(u.id for u in chunk)
                return
            for u in chunk:
                if u.id in res:
                    text, flags = res[u.id]
                    _save(paper_id, lang, u, text, flags, client.model)
                else:
                    with lock:
                        failed.append(u.id)
            job.advance(len(chunk))

        workers = min(settings["ai"]["concurrency"], client.max_concurrency or 99)
        with ThreadPoolExecutor(max_workers=workers) as ex:
            futures = [ex.submit(work, c) for c in chunks]
            for f in as_completed(futures):
                f.result()
        if fatal:
            raise fatal[0]
        if job.cancelled:
            raise JobCancelled()
        if failed:
            why = errors[0] if errors else t("job.tr.some_failed")
            job.finish(t("job.tr.partial", n=len(failed), reason=why), status="partial")
        else:
            job.finish(t("job.tr.done"))
        return {"translated": len(todo) - len(failed), "failed": len(failed), "total": len(all_units),
                "errors": list(dict.fromkeys(errors))[:3]}
    finally:
        client.close()


def status(paper_id: str, doc: dict[str, Any] | None, lang: str | None = None) -> dict[str, Any]:
    settings = settings_store.get_settings()
    tmap = translated_map(paper_id, lang)
    if not doc:
        return {"total": 0, "done": len(tmap), "sections": {}}
    units = collect_units(doc, settings["ai"]["translate_appendix"])
    sections: dict[str, dict[str, int]] = {}
    for u in units:
        s = sections.setdefault(u.section_id, {"total": 0, "done": 0})
        s["total"] += 1
        if u.id in tmap:
            s["done"] += 1
    return {"total": len(units), "done": sum(1 for u in units if u.id in tmap), "sections": sections}
