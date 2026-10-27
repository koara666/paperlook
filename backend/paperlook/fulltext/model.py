"""Structured document model shared by the HTML and PDF parsers, the translator and the UI.

doc = {
  "version": 1, "source": "arxiv_html" | "pdf", "source_label": str, "source_url": str,
  "title": str, "warnings": [str], "stats": {...},
  "sections": [{
      "id": "s3", "level": 1|2|3, "number": "3.1" | None, "title": str,
      "kind": "abstract" | "front" | "body" | "appendix" | "references",
      "blocks": [block, ...]
  }]
}

Block types (text fields use plain text with inline math as $...$ and literal dollars as \\$):
  paragraph {text}            heading {text}             equation {latex, tag}
  list {ordered, items[]}     figure {label, caption, images[], subcaptions[]}
  table {label, caption, tables: [[[cell]]], text?}   cell = {t, cs, rs, h, b}
  code {label, caption, text} reference {label, text}  unparsed {text, note}

Translatable units (see units()):
  "<sid>::title", "<bid>" (paragraph/heading), "<bid>::<i>" (list item), "<bid>::caption".
"""
from __future__ import annotations

from typing import Any, Iterator

DOC_VERSION = 1


class DocBuilder:
    def __init__(self, source: str, source_label: str, source_url: str):
        self.doc: dict[str, Any] = {
            "version": DOC_VERSION, "source": source, "source_label": source_label, "source_url": source_url,
            "title": "", "warnings": [], "sections": [], "stats": {},
        }
        self._sec_n = 0

    def section(self, title: str, level: int = 1, number: str | None = None, kind: str = "body") -> dict[str, Any]:
        self._sec_n += 1
        s = {"id": f"s{self._sec_n}", "level": level, "number": number, "title": title, "kind": kind, "blocks": []}
        self.doc["sections"].append(s)
        return s

    @staticmethod
    def add(section: dict[str, Any], block: dict[str, Any]) -> dict[str, Any]:
        block["id"] = f"{section['id']}.b{len(section['blocks']) + 1}"
        section["blocks"].append(block)
        return block

    def warn(self, msg: str) -> None:
        if msg not in self.doc["warnings"]:
            self.doc["warnings"].append(msg)

    def finish(self) -> dict[str, Any]:
        # drop empty sections that have no blocks and no children-like successors
        secs = self.doc["sections"]
        keep = []
        for i, s in enumerate(secs):
            has_child = i + 1 < len(secs) and secs[i + 1]["level"] > s["level"]
            if s["blocks"] or has_child or s["kind"] == "references":
                keep.append(s)
        self.doc["sections"] = keep
        words = 0
        for _, _, text in units(self.doc, include_references=False):
            words += len(text.split())
        self.doc["stats"] = {
            "sections": len(keep),
            "words": words,
            "figures": sum(1 for s in keep for b in s["blocks"] if b["type"] == "figure"),
            "tables": sum(1 for s in keep for b in s["blocks"] if b["type"] == "table"),
            "equations": sum(1 for s in keep for b in s["blocks"] if b["type"] == "equation"),
        }
        return self.doc


def units(doc: dict[str, Any], include_references: bool = False,
          include_appendix: bool = True) -> Iterator[tuple[str, str, str]]:
    """Yield (unit_id, section_id, text) for every translatable piece, in reading order."""
    for s in doc.get("sections", []):
        if s["kind"] == "references" and not include_references:
            continue
        if s["kind"] == "appendix" and not include_appendix:
            continue
        if s.get("title"):
            yield f"{s['id']}::title", s["id"], s["title"]
        for b in s["blocks"]:
            t = b["type"]
            if t in ("paragraph", "heading") and b.get("text"):
                yield b["id"], s["id"], b["text"]
            elif t == "list":
                for i, item in enumerate(b.get("items", [])):
                    if item:
                        yield f"{b['id']}::{i}", s["id"], item
            elif t in ("figure", "table", "code") and b.get("caption"):
                yield f"{b['id']}::caption", s["id"], b["caption"]


def plain_text(doc: dict[str, Any], max_chars: int = 200_000, include_appendix: bool = True) -> str:
    """Readable text rendering for LLM analysis (keeps headings, equations, captions, tables)."""
    out: list[str] = []
    size = 0
    for s in doc.get("sections", []):
        if s["kind"] == "references":
            continue
        if s["kind"] == "appendix" and not include_appendix:
            continue
        head = ("#" * min(3, s["level"] + 1)) + " " + " ".join(x for x in [s.get("number"), s.get("title")] if x)
        out.append(head)
        for b in s["blocks"]:
            t = b["type"]
            if t in ("paragraph", "heading"):
                piece = b["text"]
            elif t == "equation":
                piece = f"$$ {b['latex']} $$ {b.get('tag') or ''}".strip()
            elif t == "list":
                piece = "\n".join(f"- {i}" for i in b.get("items", []))
            elif t == "figure":
                piece = f"[{b.get('label') or 'Figure'}] {b.get('caption') or ''}"
            elif t == "table":
                piece = f"[{b.get('label') or 'Table'}] {b.get('caption') or ''}\n{table_to_text(b)}"
            elif t == "code":
                piece = f"[{b.get('label') or 'Algorithm'}] {b.get('caption') or ''}\n{b.get('text', '')}"
            else:
                piece = b.get("text") or ""
            if not piece:
                continue
            out.append(piece)
            size += len(piece)
            if size > max_chars:
                out.append("…（后文因长度限制省略）")
                return "\n\n".join(out)
    return "\n\n".join(out)


def table_to_text(block: dict[str, Any], max_rows: int = 40) -> str:
    if block.get("text"):
        return block["text"]
    lines = []
    for table in block.get("tables", []):
        for row in table[:max_rows]:
            lines.append(" | ".join(c.get("t", "") for c in row))
    return "\n".join(lines)
