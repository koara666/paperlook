"""PDF fallback: PyMuPDF4LLM markdown extraction -> structured document.

PDF text extraction cannot recover LaTeX or images; formulas that come out as symbol soup are
kept verbatim and marked (never translated), and the UI shows a clear warning.
"""
from __future__ import annotations

import logging
import re
from typing import Any

from .model import DocBuilder

log = logging.getLogger(__name__)
MAX_PAGES = 60

_PICTURE_TEXT = re.compile(r"<!--\s*Start of picture text\s*-->.*?<!--\s*End of picture text\s*-->", re.S)
_HTML_COMMENT = re.compile(r"<!--.*?-->", re.S)
_HEADING = re.compile(r"^(#{1,6})\s+(.*)$")
_NUM = re.compile(r"^((?:Appendix\s+)?(?:[A-Z]|\d+)(?:\.\d+)*\.?|[IVX]+\.)\s+(.+)$")
_CAPTION = re.compile(r"^(?:\*\*)?((?:Figure|Fig\.|Table|Algorithm)\s*[A-Z]?\d+[a-z]?)(?:\*\*)?\s*[:.|]\s*(.*)$", re.I | re.S)
_REF_START = re.compile(r"^\[\d+\]\s")
_MATH_ALNUM = re.compile(r"[\U0001D400-\U0001D7FF]")
_REF_HEADINGS = {"references", "bibliography", "reference", "参考文献"}


def _clean_inline(text: str) -> str:
    t = text.replace("$", r"\$")
    t = re.sub(r"<sup>(.*?)</sup>", r"^\1", t)
    t = re.sub(r"<sub>(.*?)</sub>", r"_\1", t)
    t = re.sub(r"<br\s*/?>", " ", t)
    t = re.sub(r"</?[a-z][^>]*>", "", t)
    t = t.replace("**", "")
    t = re.sub(r"(?<![\w\\])_([^_\n]{1,80}?)_(?!\w)", r"\1", t)
    t = re.sub(r"`([^`]*)`", r"\1", t)
    return re.sub(r"\s+", " ", t).strip()


def _join_lines(lines: list[str]) -> str:
    out = ""
    for ln in lines:
        ln = ln.strip()
        if not ln:
            continue
        if out.endswith("-") and ln[:1].islower():
            out = out[:-1] + ln
        else:
            out = f"{out} {ln}" if out else ln
    return out


def _looks_like_formula(text: str) -> bool:
    if len(text) > 300:
        return False
    words = [w for w in re.findall(r"[A-Za-z]{4,}", text)]
    return bool(_MATH_ALNUM.search(text)) and len(words) <= 4


def _md_table(lines: list[str]) -> list[list[dict[str, Any]]]:
    rows = []
    for ln in lines:
        ln = ln.strip()
        if re.fullmatch(r"\|?\s*:?-{2,}.*", ln) and set(ln) <= set("|-: "):
            continue
        cells = [c.strip() for c in ln.strip("|").split("|")]
        rows.append([{"t": _clean_inline(c)} for c in cells])
    if rows:
        for c in rows[0]:
            c["h"] = True
    return rows


def markdown_to_doc(md: str, source_label: str, source_url: str) -> dict[str, Any]:
    b = DocBuilder("pdf", source_label, source_url)
    b.warn("该全文来自 PDF 文本提取：公式可能无法完整保留（以原样文本显示且不翻译），图片无法显示，表格可能不完整。")
    md = _PICTURE_TEXT.sub("\n\n", md)
    md = _HTML_COMMENT.sub("", md)

    sec: dict[str, Any] | None = None
    kind = "body"
    title_set = False
    para: list[str] = []
    table: list[str] = []
    code: list[str] | None = None

    def ensure_sec() -> dict[str, Any]:
        nonlocal sec
        if sec is None:
            sec = b.section("正文前内容", level=1, kind="front")
        return sec

    def flush_para() -> None:
        nonlocal para
        if not para:
            return
        raw = _join_lines(para)
        para = []
        if not raw or re.fullmatch(r"\d{1,3}", raw.strip()):
            return  # page numbers
        s = ensure_sec()
        if s["kind"] == "references":
            for piece in re.split(r"(?=\[\d+\]\s)", raw):
                piece = piece.strip()
                if piece:
                    m = re.match(r"^(\[\d+\])\s*(.*)$", piece, re.S)
                    DocBuilder.add(s, {"type": "reference", "label": m.group(1) if m else None,
                                       "text": _clean_inline(m.group(2) if m else piece)})
            return
        m = _CAPTION.match(raw)
        if m:
            label = _clean_inline(m.group(1))
            btype = "table" if label.lower().startswith("table") else ("code" if label.lower().startswith("algorithm") else "figure")
            blk: dict[str, Any] = {"type": btype, "label": label, "caption": _clean_inline(m.group(2))}
            if btype == "figure":
                blk.update(images=[], subcaptions=[])
            elif btype == "table":
                blk["tables"] = []
            else:
                blk["text"] = ""
            DocBuilder.add(s, blk)
            return
        text = _clean_inline(raw)
        if not text:
            return
        if _looks_like_formula(text):
            DocBuilder.add(s, {"type": "unparsed", "text": text, "note": "公式（从 PDF 提取，可能不完整）"})
        else:
            DocBuilder.add(s, {"type": "paragraph", "text": text})

    def flush_table() -> None:
        nonlocal table
        if not table:
            return
        rows = _md_table(table)
        table = []
        if rows:
            s = ensure_sec()
            # attach to a preceding caption-only table block if there is one
            last = s["blocks"][-1] if s["blocks"] else None
            if last and last["type"] == "table" and not last.get("tables"):
                last["tables"] = [rows]
            else:
                DocBuilder.add(s, {"type": "table", "label": None, "caption": "", "tables": [rows]})

    for line in md.splitlines():
        if code is not None:
            if line.strip().startswith("```"):
                DocBuilder.add(ensure_sec(), {"type": "code", "label": None, "caption": "", "text": "\n".join(code)})
                code = None
            else:
                code.append(line)
            continue
        if line.strip().startswith("```"):
            flush_para(); flush_table()
            code = []
            continue
        if line.strip().startswith("|"):
            flush_para()
            table.append(line)
            continue
        elif table:
            flush_table()
        hm = _HEADING.match(line.strip())
        if hm:
            flush_para()
            text = _clean_inline(hm.group(2))
            if not text:
                continue
            if not title_set and sec is None and text.lower() != "abstract":
                b.doc["title"] = text
                title_set = True
                continue
            low = text.lower().strip(" .:")
            number = None
            title = text
            nm = _NUM.match(text)
            if nm:
                number, title = nm.group(1).rstrip("."), nm.group(2)
            if low in _REF_HEADINGS:
                kind = "references"
            elif low == "abstract":
                sec = b.section("Abstract", level=1, kind="abstract")
                continue
            elif low.startswith("appendix") or (kind in ("references", "appendix") and number and number[0].isalpha()):
                kind = "appendix"
            elif kind == "references":
                kind = "appendix"
            level = 1
            if number:
                level = min(3, number.count(".") + 1)
            sec = b.section(title, level=level, number=number,
                            kind="references" if kind == "references" else kind)
            continue
        if not line.strip():
            flush_para()
            continue
        if sec is not None and sec["kind"] == "references" and _REF_START.match(line.strip()) and para:
            flush_para()
        para.append(line)
    flush_para()
    flush_table()
    return b.finish()


def parse_pdf(data: bytes, source_label: str, source_url: str) -> dict[str, Any]:
    import pymupdf  # imported lazily: heavy module
    import pymupdf4llm

    doc = pymupdf.open(stream=data, filetype="pdf")
    try:
        if doc.page_count == 0:
            raise ValueError("PDF 没有页面")
        pages = list(range(min(doc.page_count, MAX_PAGES)))
        try:
            md = pymupdf4llm.to_markdown(doc, pages=pages, use_ocr=False, header=False, footer=False, show_progress=False)
        except Exception as e:  # layout engine problems -> legacy extractor
            log.warning("layout extraction failed (%s); using legacy extractor", e)
            pymupdf4llm.use_layout(False)
            try:
                md = pymupdf4llm.to_markdown(doc, pages=pages, show_progress=False)
            finally:
                pymupdf4llm.use_layout(True)
        result = markdown_to_doc(md, source_label, source_url)
        if doc.page_count > MAX_PAGES:
            result["warnings"].append(f"PDF 共 {doc.page_count} 页，仅解析了前 {MAX_PAGES} 页。")
        if result["stats"]["words"] < 200:
            raise ValueError("几乎没有提取到文字（可能是扫描版 PDF）")
        return result
    finally:
        doc.close()
