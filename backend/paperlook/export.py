"""Export a paper (metadata, translation, AI analyses) as Markdown."""
from __future__ import annotations

from typing import Any

from .ai import analyze, translate


def _cell(t: str) -> str:
    return (t or "").replace("|", "\\|").replace("\n", " ")


def _table_md(block: dict[str, Any]) -> str:
    out = []
    for rows in block.get("tables", []):
        if not rows:
            continue
        width = max(sum(c.get("cs", 1) for c in r) for r in rows)
        lines = []
        for i, r in enumerate(rows):
            cells = []
            for c in r:
                cells.append(_cell(c.get("t", "")))
                cells.extend([""] * (c.get("cs", 1) - 1))
            cells += [""] * (width - len(cells))
            lines.append("| " + " | ".join(cells) + " |")
            if i == 0:
                lines.append("|" + "---|" * width)
        out.append("\n".join(lines))
    if block.get("text"):
        out.append(block["text"])
    return "\n\n".join(out)


def translation_markdown(paper: dict[str, Any], doc: dict[str, Any], mode: str = "bilingual") -> str:
    """mode: 'zh' (translation only, original where missing) or 'bilingual'."""
    tmap = translate.translated_map(paper["id"])

    def tr(uid: str, original: str) -> str:
        t = tmap.get(uid, {}).get("text")
        if mode == "zh":
            return t or original
        return f"{original}\n\n> {t}" if t else original

    lines = [f"# {paper['title']}", ""]
    if paper.get("authors"):
        lines.append("**作者**：" + ", ".join(paper["authors"][:30]))
    meta = [x for x in [paper.get("published"), paper.get("venue"), paper.get("url")] if x]
    if meta:
        lines.append("**信息**：" + " · ".join(meta))
    lines += [f"**全文来源**：{doc.get('source_label')}（{doc.get('source_url')}）", ""]
    done = sum(1 for _ in tmap)
    if done == 0:
        lines += ["> 注意：本文尚未翻译，以下为原文。", ""]
    for s in doc["sections"]:
        hashes = "#" * min(4, s["level"] + 1)
        title_t = tmap.get(f"{s['id']}::title", {}).get("text")
        num = (s.get("number") or "") + " " if s.get("number") else ""
        if title_t and mode == "bilingual":
            title = f"{num}{title_t}（{s['title']}）"
        else:
            title = f"{num}{title_t or s['title']}"
        lines += [f"{hashes} {title}", ""]
        for b in s["blocks"]:
            t = b["type"]
            if t in ("paragraph", "heading"):
                txt = tr(b["id"], b["text"])
                lines += [f"**{txt}**" if t == "heading" and mode == "zh" else txt, ""]
            elif t == "equation":
                lines += [f"$$\n{b['latex']}\n$$" + (f"  {b['tag']}" if b.get("tag") else ""), ""]
            elif t == "list":
                for i, item in enumerate(b.get("items", [])):
                    prefix = f"{i + 1}." if b.get("ordered") else "-"
                    lines.append(f"{prefix} {tr(b['id'] + '::' + str(i), item)}".replace("\n\n> ", "\n   > "))
                lines.append("")
            elif t in ("figure", "table", "code"):
                cap = tr(b["id"] + "::caption", b.get("caption") or "") if b.get("caption") else ""
                label = b.get("label") or ""
                if t == "figure":
                    for img in b.get("images", []):
                        lines.append(f"![{label}]({img})")
                elif t == "table":
                    md = _table_md(b)
                    if md:
                        lines += ["", md]
                else:
                    lines += ["```", b.get("text", ""), "```"]
                if label or cap:
                    lines.append(f"*{label}{': ' if label and cap else ''}{cap}*")
                lines.append("")
            elif t == "reference":
                lines += [f"- {b.get('label') or ''} {b['text']}".strip(), ""]
            elif t == "unparsed":
                lines += [f"`{b['text']}`", ""]
    return "\n".join(lines)


def _s(v: Any) -> str:
    if v is None:
        return ""
    if isinstance(v, dict):
        return "；".join(_s(x) for x in v.values() if x)
    return str(v).strip()


def _lst(v: Any) -> list[Any]:
    return v if isinstance(v, list) else ([] if v in (None, "") else [v])


def _bullets(items: Any, fmt=lambda x: _s(x)) -> list[str]:
    out = [f"- {fmt(x)}" for x in _lst(items) if fmt(x)]
    return out or ["- 论文未明确说明"]


def _summary_md(c: dict[str, Any]) -> list[str]:
    p, m, e, a = c.get("problem") or {}, c.get("method") or {}, c.get("experiments") or {}, c.get("reading_advice") or {}
    out = [f"> **一句话总结**：{_s(c.get('tldr'))}", ""]
    if c.get("paper_type"):
        out += [f"**论文类型**：{_s(c['paper_type'])}", ""]
    out += ["### 研究问题", f"- **问题**：{_s(p.get('question'))}", f"- **意义**：{_s(p.get('importance'))}", "",
            "### 研究方法", f"- **技术路线**：{_s(m.get('overview'))}", f"- **核心思想**：{_s(m.get('core_idea'))}"]
    if m.get("relation_to_prior"):
        out.append(f"- **与已有方法的关系**：{_s(m['relation_to_prior'])}")
    out += ["", "### 实验与结果",
            f"- **数据集**：{'、'.join(_s(x) for x in _lst(e.get('datasets'))) or '论文未明确说明'}",
            f"- **评价指标**：{'、'.join(_s(x) for x in _lst(e.get('metrics'))) or '论文未明确说明'}", "- **主要结果**："]
    out += ["  " + b for b in _bullets(e.get("main_results"))]
    if e.get("evidence_assessment"):
        out.append(f"- **实验是否充分（AI 评估）**：{_s(e['evidence_assessment'])}")
    out += ["", "### 主要结论", *_bullets(c.get("conclusions")), "", "### 值得关注", *_bullets(c.get("highlights")), "",
            "### 局限性"]
    out += _bullets(c.get("limitations"), lambda x: (f"[{'作者承认' if x.get('source') == 'author' else 'AI 评估'}] {_s(x.get('point'))}"
                                                    if isinstance(x, dict) else _s(x)))
    out += ["", "### 阅读建议"]
    if _lst(a.get("audience")):
        out.append(f"- **适合方向**：{'、'.join(_s(x) for x in _lst(a['audience']))}")
    for ps in _lst(a.get("priority_sections")):
        out.append(f"- **优先阅读**：{_s(ps.get('section'))} — {_s(ps.get('reason'))}" if isinstance(ps, dict) else f"- **优先阅读**：{_s(ps)}")
    if a.get("quick_path"):
        out.append(f"- **快速理解路径**：{_s(a['quick_path'])}")
    return out


def _modules_md(c: dict[str, Any]) -> list[str]:
    if c.get("applicable") is False:
        return [f"> 本文不包含可拆分的技术模块：{_s(c.get('reason'))}", "", "### 核心论证结构",
                *[f"{i + 1}. {_s(x)}" for i, x in enumerate(_lst(c.get("structure")))]]
    novelty = {"new": "本文提出", "adapted": "改进已有方法", "existing": "沿用已有方法"}
    out = ["### 整体架构", _s(c.get("overview")), ""]
    if _lst(c.get("flow")):
        out += ["### 模块协作流程", *[f"- {_s(f.get('from'))} → {_s(f.get('to'))}：{_s(f.get('description'))}"
                                     for f in _lst(c["flow"]) if isinstance(f, dict)], ""]
    for mod in _lst(c.get("modules")):
        if not isinstance(mod, dict):
            continue
        name = _s(mod.get("name")) + (f"（{_s(mod['name_en'])}）" if mod.get("name_en") else "")
        tags = " · ".join(x for x in [_s(mod.get("category")), novelty.get(_s(mod.get("novelty")), ""),
                                      f"§{_s(mod['section'])}" if mod.get("section") else ""] if x)
        out += [f"### {name}", f"_{tags}_", "", f"- **作用**：{_s(mod.get('role'))}",
                f"- **输入 → 输出**：{_s(mod.get('inputs'))} → {_s(mod.get('outputs'))}", f"- **原理**：{_s(mod.get('mechanism'))}"]
        if _s(mod.get("key_formula")):
            out += ["", f"$$\n{_s(mod['key_formula']).strip('$')}\n$$"]
        out.append("")
    if _lst(c.get("design_insights")):
        out += ["### 关键设计选择", *_bullets(c["design_insights"])]
    return out


def _contributions_md(c: dict[str, Any]) -> list[str]:
    verify = {"exact": "✓ 原文已核验", "close": "✓ 与原文基本一致", "partial": "⚠ 仅部分匹配原文",
              "not_found": "✗ 未能在原文中找到", "missing": "缺少原文引用"}
    out = [f"> **解决的核心问题**：{_s(c.get('problem_solved'))}", "", "### ① 作者明确声明的贡献"]
    for e in _lst(c.get("explicit")):
        if isinstance(e, dict):
            out += [f"- **{_s(e.get('claim'))}**（{verify.get(e.get('verified'), '未核验')}{'，§' + _s(e['section']) if e.get('section') else ''}）",
                    f"  > {_s(e.get('quote'))}"]
    out += ["", "### ② 基于论文内容归纳的贡献"]
    out += _bullets(c.get("derived"), lambda x: f"{_s(x.get('point'))}（依据：{_s(x.get('basis'))}）" if isinstance(x, dict) else _s(x))
    if _lst(c.get("improvements")):
        out += ["", "### 相比已有方法的改进"]
        out += _bullets(c["improvements"], lambda x: f"**{_s(x.get('aspect'))}**：{_s(x.get('detail'))}（证据：{_s(x.get('evidence'))}）"
                        if isinstance(x, dict) else _s(x))
    if _lst(c.get("new_methods")):
        out += ["", "### 新提出的方法 / 模型 / 数据集"]
        out += _bullets(c["new_methods"], lambda x: f"**{_s(x.get('name'))}**：{_s(x.get('description'))}" if isinstance(x, dict) else _s(x))
    if _lst(c.get("experimental_support")):
        strength = {"strong": "强", "moderate": "中", "weak": "弱"}
        out += ["", "### 实验支撑的结论"]
        out += _bullets(c["experimental_support"], lambda x: f"{_s(x.get('claim'))}（支撑：{strength.get(_s(x.get('strength')), '?')}；{_s(x.get('evidence'))}）"
                        if isinstance(x, dict) else _s(x))
    out += ["", "### ③ AI 推断的潜在价值（推测，非论文观点）"]
    out += _bullets(c.get("inferred"), lambda x: f"{_s(x.get('point'))}（理由：{_s(x.get('rationale'))}）" if isinstance(x, dict) else _s(x))
    return out


def analysis_markdown(paper: dict[str, Any]) -> str:
    out = [f"# {paper['title']}", ""]
    meta = [x for x in [", ".join(paper.get("authors", [])[:10]), paper.get("published"), paper.get("venue"), paper.get("url")] if x]
    out += [" · ".join(meta), ""]
    renderers = {"summary": ("论文总结", _summary_md), "modules": ("关键模块分析", _modules_md),
                 "contributions": ("创新点与贡献", _contributions_md)}
    found = False
    for kind, (title, render) in renderers.items():
        r = analyze.get_result(paper["id"], kind)
        if not r or not isinstance(r.get("content"), dict):
            continue
        found = True
        basis = (r.get("basis") or {}).get("type")
        out += [f"## {title}", f"_基于{'全文' if basis == 'fulltext' else '摘要'}生成 · {r.get('model')} · {r.get('created_at')} · 内容由 AI 生成，请以原文为准_", ""]
        out += render(r["content"])
        out.append("")
    if not found:
        out.append("> 这篇论文还没有生成任何 AI 分析。")
    return "\n".join(out)
