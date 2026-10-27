"""User-triggered AI analyses: summary, key modules, contributions, abstract translation.

Each analysis uses the full text when it can be obtained, otherwise the abstract - and records
which one was used ("basis") so the UI can say so prominently. Results are cached in ai_results;
re-running requires an explicit "regenerate" action.
"""
from __future__ import annotations

import logging
from typing import Any

from .. import db, papers as papers_repo, settings_store
from ..errors import AppError
from ..fulltext import fetcher
from ..fulltext.model import plain_text
from ..jobs import Job
from ..textutil import normalize
from . import prompts
from .client import get_client

log = logging.getLogger(__name__)

KINDS = {
    "summary": {"feature": "summary", "task": prompts.SUMMARY_TASK, "label": "论文总结"},
    "modules": {"feature": "modules", "task": prompts.MODULES_TASK, "label": "关键模块分析"},
    "contributions": {"feature": "contributions", "task": prompts.CONTRIBUTIONS_TASK, "label": "创新点提取"},
    "abstract_translation": {"feature": None, "task": None, "label": "摘要翻译"},
}
MAX_CONTENT_CHARS = 180_000


def get_result(paper_id: str, kind: str) -> dict[str, Any] | None:
    r = db.query_one("SELECT * FROM ai_results WHERE paper_id = ? AND kind = ?", (paper_id, kind))
    if not r:
        return None
    return {"kind": kind, "content": db.loads(r["content"], {}), "basis": db.loads(r["basis"], None),
            "model": r["model"], "usage": db.loads(r["usage"], {}), "created_at": r["created_at"]}


def _save(paper_id: str, kind: str, content: dict[str, Any], basis: dict[str, Any] | None, model: str,
          usage: dict[str, int]) -> None:
    db.execute(
        "INSERT INTO ai_results(paper_id, kind, content, basis, model, usage, created_at) VALUES(?,?,?,?,?,?,?) "
        "ON CONFLICT(paper_id, kind) DO UPDATE SET content=excluded.content, basis=excluded.basis, model=excluded.model, "
        "usage=excluded.usage, created_at=excluded.created_at",
        (paper_id, kind, db.dumps(content), db.dumps(basis) if basis else None, model, db.dumps(usage), db.now_iso()),
    )


def _paper_header(p: dict[str, Any]) -> str:
    authors = ", ".join(p.get("authors", [])[:12]) + (" 等" if len(p.get("authors", [])) > 12 else "")
    lines = [f"标题：{p['title']}", f"作者：{authors or '未知'}", f"发布日期：{p.get('published') or '未知'}"]
    if p.get("venue"):
        lines.append(f"发表于：{p['venue']}")
    if p.get("comment"):
        lines.append(f"作者备注：{p['comment']}")
    return "\n".join(lines)


def load_content(paper: dict[str, Any], job: Job | None) -> tuple[str, dict[str, Any]]:
    """Full text if obtainable, else abstract. Returns (content, basis)."""
    reason = None
    try:
        if job:
            job.update(message="正在获取论文全文…", force=True)
        doc = fetcher.ensure(paper, job)
        text = plain_text(doc, max_chars=MAX_CONTENT_CHARS)
        return text, {"type": "fulltext", "source_label": doc.get("source_label"), "chars": len(text),
                      "truncated": len(text) >= MAX_CONTENT_CHARS}
    except AppError as e:
        reason = e.message
    if not paper.get("abstract"):
        raise AppError((reason or "无法获取全文") + "，且该论文没有摘要，无法进行分析。", code="no_content")
    return f"摘要：\n{paper['abstract']}", {"type": "abstract", "reason": reason}


def verify_quotes(items: list[dict[str, Any]], source_text: str) -> None:
    """Mark each explicit claim's quote as verified / partial / not found in the paper text."""
    src = normalize(source_text)
    src_words = src.split()
    grams = {" ".join(src_words[i:i + 4]) for i in range(max(0, len(src_words) - 3))}
    for it in items:
        q = normalize(it.get("quote") or "")
        if not q:
            it["verified"] = "missing"
            continue
        if q in src:
            it["verified"] = "exact"
            continue
        qw = q.split()
        qgrams = [" ".join(qw[i:i + 4]) for i in range(max(0, len(qw) - 3))]
        if not qgrams:
            it["verified"] = "exact" if q in src else "not_found"
            continue
        ratio = sum(1 for g in qgrams if g in grams) / len(qgrams)
        it["verified"] = "close" if ratio >= 0.8 else ("partial" if ratio >= 0.4 else "not_found")


def run(job: Job, paper_id: str, kind: str) -> dict[str, Any]:
    if kind not in KINDS:
        raise AppError("未知的分析类型", status_code=400)
    spec = KINDS[kind]
    settings = settings_store.get_settings()
    if spec["feature"] and not settings["ai"]["features"].get(spec["feature"], True):
        raise AppError(f"「{spec['label']}」功能已在设置中关闭。", code="feature_disabled")
    paper = papers_repo.get_paper(paper_id)
    if not paper:
        raise AppError("论文不存在", status_code=404)
    client = get_client()
    try:
        if kind == "abstract_translation":
            if not paper.get("abstract"):
                raise AppError("该论文没有摘要。", code="no_content")
            job.update(message="正在翻译摘要…", force=True)
            data, res = client.chat_json(
                [{"role": "system", "content": prompts.ABSTRACT_TRANSLATION_SYSTEM},
                 {"role": "user", "content": f"标题：{paper['title']}\n\n摘要：{paper['abstract']}"}],
                thinking=False, max_tokens=4000, temperature=0.3, kind=kind, paper_id=paper_id)
            content = {"title_zh": str(data.get("title_zh") or ""), "abstract_zh": str(data.get("abstract_zh") or "")}
            if not content["abstract_zh"]:
                raise AppError("模型没有返回译文，请重试。", code="bad_response")
            _save(paper_id, kind, content, {"type": "abstract"}, res.model, res.usage)
            return {"kind": kind}

        text, basis = load_content(paper, job)
        job.check_cancelled()
        thinking = bool(settings["ai"]["thinking_for_analysis"])
        job.update(message=f"AI 正在{'深度思考并' if thinking else ''}生成{spec['label']}…", force=True)
        system = prompts.ANALYSIS_SYSTEM + ("\n\n" + prompts.ABSTRACT_ONLY_NOTE if basis["type"] == "abstract" else "")
        basis_label = "全文" if basis["type"] == "fulltext" else "仅摘要"
        # Paper first, task last: the long shared prefix (system + paper) hits DeepSeek's context cache
        # when the other analyses of the same paper run later, and instructions after a long document
        # are followed more reliably.
        user = (f"=== 论文信息 ===\n{_paper_header(paper)}\n\n=== 论文内容（{basis_label}）===\n{text}\n\n"
                f"=== 任务 ===\n{spec['task']}")
        data, res = client.chat_json([{"role": "system", "content": system}, {"role": "user", "content": user}],
                                     thinking=thinking, max_tokens=32000 if thinking else 12000, temperature=0.3,
                                     kind=kind, paper_id=paper_id)
        if kind == "contributions" and isinstance(data.get("explicit"), list):
            verify_quotes([x for x in data["explicit"] if isinstance(x, dict)], text)
        basis["thinking"] = thinking
        _save(paper_id, kind, data, basis, res.model, res.usage)
        return {"kind": kind, "basis": basis["type"]}
    finally:
        client.close()
