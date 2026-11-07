"""Optional AI re-ranking of the recommendation candidate pool (explicit opt-in in settings).
One request for the whole pool; also yields a translated title and one-line summary per paper in the AI output
language."""
from __future__ import annotations

from typing import Any

from .. import db
from ..textutil import truncate
from . import prompts
from .client import get_client


def rerank(pool: list[Any], directions: list[Any]) -> tuple[dict[int, dict[str, Any]], dict[str, int]]:
    lang = prompts.output_language()
    dir_text = "\n".join(
        f"{i + 1}. {d.name} (keywords: {', '.join(k.display for k in d.keywords[:12]) or 'none'})"
        for i, d in enumerate(directions))
    cands = [{"i": i, "title": s.paper.get("title"), "abstract": truncate(s.paper.get("abstract") or "", 1100)}
             for i, s in enumerate(pool)]
    user = f"{prompts.rerank_task(lang)}\n\nThe user's research directions:\n{dir_text}\n\nCandidates:\n{db.dumps(cands)}"
    client = get_client()
    try:
        data, res = client.chat_json([{"role": "system", "content": prompts.rerank_system(lang)},
                                      {"role": "user", "content": user}],
                                     thinking=False, max_tokens=12000, temperature=0.2, kind="rerank")
    finally:
        client.close()
    out: dict[int, dict[str, Any]] = {}
    for r in data.get("results", []) if isinstance(data.get("results"), list) else []:
        if not isinstance(r, dict):
            continue
        try:
            i = int(r.get("i"))
            rel = max(0.0, min(10.0, float(r.get("relevance"))))
        except (TypeError, ValueError):
            continue
        if 0 <= i < len(pool):
            out[i] = {"relevance": round(rel / 10.0, 3), "reason": str(r.get("reason") or "")[:120],
                      "title_tr": str(r.get("title_tr") or r.get("title_zh") or "")[:240],
                      "tldr": str(r.get("tldr") or "")[:240], "lang": lang}
    return out, res.usage
