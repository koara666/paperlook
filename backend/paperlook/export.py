"""Export a paper (metadata, translation, AI analyses) as Markdown."""
from __future__ import annotations

from typing import Any

from . import i18n, papers as papers_repo
from .ai import analyze, translate
from .i18n import t


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
    """mode: 'translation' (translation only, original where missing) or 'bilingual'."""
    tmap = translate.translated_map(paper["id"])
    only = mode == "translation"

    def tr(uid: str, original: str) -> str:
        text = tmap.get(uid, {}).get("text")
        if only:
            return text or original
        return f"{original}\n\n> {text}" if text else original

    lines = [f"# {paper['title']}", ""]
    if paper.get("authors"):
        lines.append(f"**{t('ex.authors')}**: " + ", ".join(paper["authors"][:30]))
    meta = [x for x in [paper.get("published"), paper.get("venue"), paper.get("url")] if x]
    if meta:
        lines.append(f"**{t('ex.info')}**: " + " · ".join(meta))
    lines += [f"**{t('ex.fulltext_source')}**: {i18n.render(doc.get('source_label'))} ({doc.get('source_url')})", ""]
    if not tmap:
        lines += [f"> {t('ex.not_translated')}", ""]
    titles = {"doc.front": t("doc.front"), "doc.untitled": t("doc.untitled")}
    for s in doc["sections"]:
        hashes = "#" * min(4, s["level"] + 1)
        original_title = s["title"] or titles.get(s.get("title_key") or "", "")
        title_t = tmap.get(f"{s['id']}::title", {}).get("text")
        num = (s.get("number") or "") + " " if s.get("number") else ""
        if title_t and not only:
            title = f"{num}{title_t} ({original_title})"
        else:
            title = f"{num}{title_t or original_title}"
        lines += [f"{hashes} {title}", ""]
        for b in s["blocks"]:
            kind = b["type"]
            if kind in ("paragraph", "heading"):
                txt = tr(b["id"], b["text"])
                lines += [f"**{txt}**" if kind == "heading" and only else txt, ""]
            elif kind == "equation":
                lines += [f"$$\n{b['latex']}\n$$" + (f"  {b['tag']}" if b.get("tag") else ""), ""]
            elif kind == "list":
                for i, item in enumerate(b.get("items", [])):
                    prefix = f"{i + 1}." if b.get("ordered") else "-"
                    lines.append(f"{prefix} {tr(b['id'] + '::' + str(i), item)}".replace("\n\n> ", "\n   > "))
                lines.append("")
            elif kind in ("figure", "table", "code"):
                cap = tr(b["id"] + "::caption", b.get("caption") or "") if b.get("caption") else ""
                label = b.get("label") or ""
                if kind == "figure":
                    for img in b.get("images", []):
                        lines.append(f"![{label}]({img})")
                elif kind == "table":
                    md = _table_md(b)
                    if md:
                        lines += ["", md]
                else:
                    lines += ["```", b.get("text", ""), "```"]
                if label or cap:
                    lines.append(f"*{label}{': ' if label and cap else ''}{cap}*")
                lines.append("")
            elif kind == "reference":
                lines += [f"- {b.get('label') or ''} {b['text']}".strip(), ""]
            elif kind == "unparsed":
                lines += [f"`{b['text']}`", ""]
    return "\n".join(lines)


def _s(v: Any) -> str:
    if v is None:
        return ""
    if isinstance(v, dict):
        return "; ".join(_s(x) for x in v.values() if x)
    return str(v).strip()


def _lst(v: Any) -> list[Any]:
    return v if isinstance(v, list) else ([] if v in (None, "") else [v])


def _bullets(items: Any, fmt=lambda x: _s(x)) -> list[str]:
    out = [f"- {fmt(x)}" for x in _lst(items) if fmt(x)]
    return out or [f"- {t('ex.not_stated')}"]


def _code(prefix: str, value: Any) -> str:
    """Enumerated values (paper type, module category) are English codes; older results stored text."""
    v = _s(value)
    key = f"{prefix}.{v}"
    return t(key) if key in i18n.M else v


def _join(items: Any) -> str:
    return i18n.join([_s(x) for x in _lst(items) if _s(x)]) or t("ex.not_stated")


def _summary_md(c: dict[str, Any]) -> list[str]:
    p, m, e, a = c.get("problem") or {}, c.get("method") or {}, c.get("experiments") or {}, c.get("reading_advice") or {}
    out = [f"> **{t('ex.tldr')}**: {_s(c.get('tldr'))}", ""]
    if c.get("paper_type"):
        out += [f"**{t('ex.paper_type')}**: {_code('ptype', c['paper_type'])}", ""]
    out += [f"### {t('ex.problem')}", f"- **{t('ex.question')}**: {_s(p.get('question'))}",
            f"- **{t('ex.importance')}**: {_s(p.get('importance'))}", "",
            f"### {t('ex.method')}", f"- **{t('ex.overview')}**: {_s(m.get('overview'))}",
            f"- **{t('ex.core_idea')}**: {_s(m.get('core_idea'))}"]
    if m.get("relation_to_prior"):
        out.append(f"- **{t('ex.relation')}**: {_s(m['relation_to_prior'])}")
    out += ["", f"### {t('ex.experiments')}",
            f"- **{t('ex.datasets')}**: {_join(e.get('datasets'))}",
            f"- **{t('ex.metrics')}**: {_join(e.get('metrics'))}", f"- **{t('ex.main_results')}**:"]
    out += ["  " + b for b in _bullets(e.get("main_results"))]
    if e.get("evidence_assessment"):
        out.append(f"- **{t('ex.evidence')}**: {_s(e['evidence_assessment'])}")
    out += ["", f"### {t('ex.conclusions')}", *_bullets(c.get("conclusions")), "",
            f"### {t('ex.highlights')}", *_bullets(c.get("highlights")), "", f"### {t('ex.limitations')}"]
    out += _bullets(c.get("limitations"), lambda x: (
        f"[{t('ex.by_author') if x.get('source') == 'author' else t('ex.by_ai')}] {_s(x.get('point'))}"
        if isinstance(x, dict) else _s(x)))
    out += ["", f"### {t('ex.reading')}"]
    if _lst(a.get("audience")):
        out.append(f"- **{t('ex.audience')}**: {_join(a['audience'])}")
    for ps in _lst(a.get("priority_sections")):
        out.append(f"- **{t('ex.priority')}**: {_s(ps.get('section'))} — {_s(ps.get('reason'))}" if isinstance(ps, dict)
                   else f"- **{t('ex.priority')}**: {_s(ps)}")
    if a.get("quick_path"):
        out.append(f"- **{t('ex.quick_path')}**: {_s(a['quick_path'])}")
    return out


def _modules_md(c: dict[str, Any]) -> list[str]:
    if c.get("applicable") is False:
        return [f"> {t('ex.no_modules')}: {_s(c.get('reason'))}", "", f"### {t('ex.structure')}",
                *[f"{i + 1}. {_s(x)}" for i, x in enumerate(_lst(c.get("structure")))]]
    out = [f"### {t('ex.architecture')}", _s(c.get("overview")), ""]
    if _lst(c.get("flow")):
        out += [f"### {t('ex.flow')}", *[f"- {_s(f.get('from'))} → {_s(f.get('to'))}: {_s(f.get('description'))}"
                                         for f in _lst(c["flow"]) if isinstance(f, dict)], ""]
    for mod in _lst(c.get("modules")):
        if not isinstance(mod, dict):
            continue
        name = _s(mod.get("name")) + (f" ({_s(mod['name_en'])})" if mod.get("name_en") else "")
        novelty = _s(mod.get("novelty"))
        tags = " · ".join(x for x in [_code("mcat", mod.get("category")),
                                      t(f"novelty.{novelty}") if novelty in ("new", "adapted", "existing") else "",
                                      f"§{_s(mod['section'])}" if mod.get("section") else ""] if x)
        out += [f"### {name}", f"_{tags}_", "", f"- **{t('ex.role')}**: {_s(mod.get('role'))}",
                f"- **{t('ex.io')}**: {_s(mod.get('inputs'))} → {_s(mod.get('outputs'))}",
                f"- **{t('ex.mechanism')}**: {_s(mod.get('mechanism'))}"]
        if _s(mod.get("key_formula")):
            out += ["", f"$$\n{_s(mod['key_formula']).strip('$')}\n$$"]
        out.append("")
    if _lst(c.get("design_insights")):
        out += [f"### {t('ex.design')}", *_bullets(c["design_insights"])]
    return out


def _contributions_md(c: dict[str, Any]) -> list[str]:
    out = [f"> **{t('ex.problem_solved')}**: {_s(c.get('problem_solved'))}", "", f"### ① {t('ex.explicit')}"]
    for e in _lst(c.get("explicit")):
        if isinstance(e, dict):
            v = e.get("verified")
            check = t(f"verify.{v}") if v in ("exact", "close", "partial", "not_found", "missing") else t("verify.none")
            section = f", §{_s(e['section'])}" if e.get("section") else ""
            out += [f"- **{_s(e.get('claim'))}** ({check}{section})", f"  > {_s(e.get('quote'))}"]
    out += ["", f"### ② {t('ex.derived')}"]
    out += _bullets(c.get("derived"), lambda x: f"{_s(x.get('point'))} ({t('ex.basis')}: {_s(x.get('basis'))})"
                    if isinstance(x, dict) else _s(x))
    if _lst(c.get("improvements")):
        out += ["", f"### {t('ex.improvements')}"]
        out += _bullets(c["improvements"], lambda x: f"**{_s(x.get('aspect'))}**: {_s(x.get('detail'))} "
                        f"({t('ex.evidence_short')}: {_s(x.get('evidence'))})" if isinstance(x, dict) else _s(x))
    if _lst(c.get("new_methods")):
        out += ["", f"### {t('ex.new_methods')}"]
        out += _bullets(c["new_methods"], lambda x: f"**{_s(x.get('name'))}**: {_s(x.get('description'))}"
                        if isinstance(x, dict) else _s(x))
    if _lst(c.get("experimental_support")):
        out += ["", f"### {t('ex.support')}"]

        def fmt(x: Any) -> str:
            if not isinstance(x, dict):
                return _s(x)
            st = _s(x.get("strength"))
            strength = t(f"strength.{st}") if st in ("strong", "moderate", "weak") else "?"
            return f"{_s(x.get('claim'))} ({t('ex.support_strength')}: {strength}; {_s(x.get('evidence'))})"
        out += _bullets(c["experimental_support"], fmt)
    out += ["", f"### ③ {t('ex.inferred')}"]
    out += _bullets(c.get("inferred"), lambda x: f"{_s(x.get('point'))} ({t('ex.rationale')}: {_s(x.get('rationale'))})"
                    if isinstance(x, dict) else _s(x))
    return out


def analysis_markdown(paper: dict[str, Any]) -> str:
    out = [f"# {paper['title']}", ""]
    meta = [x for x in [", ".join(paper.get("authors", [])[:10]), paper.get("published"), paper.get("venue"), paper.get("url")] if x]
    out += [" · ".join(meta), ""]
    note = (papers_repo.get_state(paper["id"]).get("note") or "").strip()
    if note:
        out += [f"## {t('ex.my_note')}", "", note, ""]
    renderers = {"summary": ("ai.label.summary", _summary_md), "modules": ("ai.label.modules", _modules_md),
                 "contributions": ("ex.contributions_title", _contributions_md)}
    found = False
    for kind, (title, render) in renderers.items():
        r = analyze.get_result(paper["id"], kind)
        if not r or not isinstance(r.get("content"), dict):
            continue
        found = True
        basis = (r.get("basis") or {}).get("type")
        based = t("ex.based_fulltext" if basis == "fulltext" else "ex.based_abstract")
        out += [f"## {t(title)}", f"_{based} · {r.get('model')} · {r.get('created_at')} · {t('ex.ai_disclaimer')}_", ""]
        out += render(r["content"])
        out.append("")
    if not found:
        out.append(f"> {t('ex.no_analysis')}")
    return "\n".join(out)
