"""Optional AI re-ranking of the recommendation candidate pool (explicit opt-in in settings).
One request for the whole pool; also yields a Chinese title and one-line summary per paper."""
from __future__ import annotations

from typing import Any

from .. import db
from ..textutil import truncate
from . import prompts
from .client import get_client


def rerank(pool: list[Any], directions: list[Any]) -> tuple[dict[int, dict[str, Any]], dict[str, int]]:
    dir_text = "\n".join(
        f"{i + 1}. {d.name}（关键词：{', '.join(k.display for k in d.keywords[:12]) or '无'}）" for i, d in enumerate(directions))
    cands = [{"i": i, "title": s.paper.get("title"), "abstract": truncate(s.paper.get("abstract") or "", 1100)}
             for i, s in enumerate(pool)]
    user = f"{prompts.RERANK_TASK}\n\n用户的研究方向：\n{dir_text}\n\n候选论文：\n{db.dumps(cands)}"
    client = get_client()
    try:
        data, res = client.chat_json([{"role": "system", "content": prompts.RERANK_SYSTEM}, {"role": "user", "content": user}],
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
            out[i] = {"relevance": round(rel / 10.0, 3), "reason": str(r.get("reason") or "")[:80],
                      "title_zh": str(r.get("title_zh") or "")[:200], "tldr": str(r.get("tldr") or "")[:160]}
    return out, res.usage
