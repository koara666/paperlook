"""User-triggered AI analyses: summary, key modules, contributions, abstract translation.

Each analysis uses the full text when it can be obtained, otherwise the abstract - and records
which one was used ("basis") so the UI can say so prominently. Results are cached in ai_results per
output language; re-running requires an explicit "regenerate" action. A result in another language is
still shown (with a note) instead of silently spending tokens again.
"""
from __future__ import annotations

import logging
from typing import Any

from .. import db, papers as papers_repo, settings_store
from ..errors import AppError
from ..fulltext import fetcher
from ..fulltext.model import plain_text
from ..i18n import t
from ..jobs import Job
from ..textutil import detect_language, is_cjk_char, normalize
from . import prompts
from .client import get_client

log = logging.getLogger(__name__)

KINDS = {
    "summary": {"feature": "summary", "task": prompts.summary_task, "label": "ai.label.summary"},
    "modules": {"feature": "modules", "task": prompts.modules_task, "label": "ai.label.modules"},
    "contributions": {"feature": "contributions", "task": prompts.contributions_task, "label": "ai.label.contributions"},
    "abstract_translation": {"feature": None, "task": None, "label": "ai.label.abstract_translation"},
}
MAX_CONTENT_CHARS = 180_000


def _normalize_content(kind: str, content: dict[str, Any]) -> dict[str, Any]:
    if kind == "abstract_translation":  # results before 1.3 were always Chinese: title_zh / abstract_zh
        return {"title": content.get("title") or content.get("title_zh") or "",
                "abstract": content.get("abstract") or content.get("abstract_zh") or ""}
    return content


def get_result(paper_id: str, kind: str, lang: str | None = None, exact: bool = False) -> dict[str, Any] | None:
    """The result in `lang` (default: the AI output language); unless exact, a result in another language."""
    lang = lang or prompts.output_language()
    rows = db.query("SELECT * FROM ai_results WHERE paper_id = ? AND kind = ? ORDER BY created_at DESC", (paper_id, kind))
    r = next((x for x in rows if x["lang"] == lang), None) or (None if exact or not rows else rows[0])
    if not r:
        return None
    return {"kind": kind, "lang": r["lang"], "content": _normalize_content(kind, db.loads(r["content"], {})),
            "basis": db.loads(r["basis"], None), "model": r["model"], "usage": db.loads(r["usage"], {}),
            "created_at": r["created_at"]}


def save_result(paper_id: str, kind: str, lang: str, content: dict[str, Any], basis: dict[str, Any] | None,
                model: str, usage: dict[str, int]) -> None:
    db.execute(
        "INSERT INTO ai_results(paper_id, kind, lang, content, basis, model, usage, created_at) VALUES(?,?,?,?,?,?,?,?) "
        "ON CONFLICT(paper_id, kind, lang) DO UPDATE SET content=excluded.content, basis=excluded.basis, "
        "model=excluded.model, usage=excluded.usage, created_at=excluded.created_at",
        (paper_id, kind, lang, db.dumps(content), db.dumps(basis) if basis else None, model, db.dumps(usage), db.now_iso()),
    )


def _paper_header(p: dict[str, Any]) -> str:
    authors = ", ".join(p.get("authors", [])[:12]) + (" et al." if len(p.get("authors", [])) > 12 else "")
    lines = [f"Title: {p['title']}", f"Authors: {authors or 'unknown'}", f"Published: {p.get('published') or 'unknown'}"]
    if p.get("venue"):
        lines.append(f"Venue: {p['venue']}")
    if p.get("comment"):
        lines.append(f"Author comment: {p['comment']}")
    return "\n".join(lines)


def load_content(paper: dict[str, Any], job: Job | None) -> tuple[str, dict[str, Any]]:
    """Full text if obtainable, else abstract. Returns (content, basis)."""
    reason = None
    try:
        if job:
            job.update(message=t("job.ai.fulltext"), force=True)
        doc = fetcher.ensure(paper, job)
        text = plain_text(doc, max_chars=MAX_CONTENT_CHARS)
        return text, {"type": "fulltext", "source": doc.get("source"), "chars": len(text),
                      "truncated": len(text) >= MAX_CONTENT_CHARS}
    except AppError as e:
        reason = e.message
    if not paper.get("abstract"):
        raise AppError(t("err.no_content", reason=reason or t("err.no_fulltext")), code="no_content")
    return f"Abstract:\n{paper['abstract']}", {"type": "abstract", "reason": reason}


def _tokens(text: str) -> list[str]:
    """Words for alphabetic scripts; single characters for CJK (no spaces between words)."""
    out: list[str] = []
    for w in normalize(text).split():
        if any(is_cjk_char(c) for c in w):
            out.extend(c for c in w if not c.isspace())
        else:
            out.append(w)
    return out


def verify_quotes(items: list[dict[str, Any]], source_text: str) -> None:
    """Mark each explicit claim's quote as verified / partial / not found in the paper text.
    Matching uses 4-word n-grams, or 6-character n-grams for CJK text."""
    src_tokens = _tokens(source_text)
    src_join = " ".join(src_tokens)
    grams: dict[int, set[str]] = {}
    for it in items:
        q_tokens = _tokens(it.get("quote") or "")
        if not q_tokens:
            it["verified"] = "missing"
            continue
        if " ".join(q_tokens) in src_join:
            it["verified"] = "exact"
            continue
        n = 6 if sum(1 for x in q_tokens if len(x) == 1 and is_cjk_char(x)) > len(q_tokens) / 2 else 4
        if n not in grams:
            grams[n] = {" ".join(src_tokens[i:i + n]) for i in range(max(0, len(src_tokens) - n + 1))}
        qgrams = [" ".join(q_tokens[i:i + n]) for i in range(max(0, len(q_tokens) - n + 1))]
        if not qgrams:
            it["verified"] = "not_found"
            continue
        ratio = sum(1 for g in qgrams if g in grams[n]) / len(qgrams)
        it["verified"] = "close" if ratio >= 0.8 else ("partial" if ratio >= 0.4 else "not_found")


def run(job: Job, paper_id: str, kind: str) -> dict[str, Any]:
    if kind not in KINDS:
        raise AppError(t("err.unknown_ai_kind"), status_code=400)
    spec = KINDS[kind]
    settings = settings_store.get_settings()
    if spec["feature"] and not settings["ai"]["features"].get(spec["feature"], True):
        raise AppError(t("err.feature_disabled", feature=t(spec["label"])), code="feature_disabled")
    paper = papers_repo.get_paper(paper_id)
    if not paper:
        raise AppError(t("err.paper_not_found"), status_code=404)
    lang = prompts.output_language()
    client = get_client()
    try:
        if kind == "abstract_translation":
            if not paper.get("abstract"):
                raise AppError(t("err.no_abstract"), code="no_content")
            job.update(message=t("job.ai.abstract"), force=True)
            source = detect_language(paper["abstract"], paper.get("language"))
            data, res = client.chat_json(
                [{"role": "system", "content": prompts.abstract_translation_system(source, lang)},
                 {"role": "user", "content": f"Title: {paper['title']}\n\nAbstract: {paper['abstract']}"}],
                thinking=False, max_tokens=4000, temperature=0.3, kind=kind, paper_id=paper_id)
            content = {"title": str(data.get("title") or data.get("title_zh") or ""),
                       "abstract": str(data.get("abstract") or data.get("abstract_zh") or "")}
            if not content["abstract"]:
                raise AppError(t("err.no_translation"), code="bad_response")
            save_result(paper_id, kind, lang, content, {"type": "abstract", "source_language": source}, res.model, res.usage)
            return {"kind": kind}

        text, basis = load_content(paper, job)
        job.check_cancelled()
        thinking = bool(settings["ai"]["thinking_for_analysis"])
        job.update(message=t("job.ai.thinking" if thinking else "job.ai.generating", label=t(spec["label"])), force=True)
        system = prompts.analysis_system(lang) + ("\n\n" + prompts.abstract_only_note(lang) if basis["type"] == "abstract" else "")
        basis_label = "full text" if basis["type"] == "fulltext" else "abstract only"
        basis["source_language"] = detect_language(text[:4000], paper.get("language"))
        # Paper first, task last: the long shared prefix (system + paper) hits DeepSeek's context cache
        # when the other analyses of the same paper run later, and instructions after a long document
        # are followed more reliably.
        user = (f"=== Paper ===\n{_paper_header(paper)}\n\n=== Content ({basis_label}) ===\n{text}\n\n"
                f"=== Task ===\n{spec['task'](lang)}")
        data, res = client.chat_json([{"role": "system", "content": system}, {"role": "user", "content": user}],
                                     thinking=thinking, max_tokens=32000 if thinking else 12000, temperature=0.3,
                                     kind=kind, paper_id=paper_id)
        if kind == "contributions" and isinstance(data.get("explicit"), list):
            verify_quotes([x for x in data["explicit"] if isinstance(x, dict)], text)
        basis["thinking"] = thinking
        save_result(paper_id, kind, lang, data, basis, res.model, res.usage)
        return {"kind": kind, "basis": basis["type"]}
    finally:
        client.close()

