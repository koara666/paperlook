"""Parser for arXiv's HTML full text (LaTeXML output, https://arxiv.org/html/<id>).

LaTeXML preserves the paper structure: nested <section>s, math as <math alttext="LaTeX">,
<figure> with <figcaption>, real <table class="ltx_tabular">, algorithms, and the bibliography.
"""
from __future__ import annotations

import re
from typing import Any
from urllib.parse import urljoin

from bs4 import BeautifulSoup, Comment, NavigableString, Tag

from .model import DocBuilder

SECTION_LEVEL = {"ltx_part": 1, "ltx_chapter": 1, "ltx_section": 1, "ltx_appendix": 1,
                 "ltx_subsection": 2, "ltx_subsubsection": 3}
_WS = re.compile(r"\s+")


class HtmlNotAvailable(Exception):
    pass


def _cls(el: Tag) -> list[str]:
    return el.get("class") or []


def _clean_tex(tex: str) -> str:
    tex = _WS.sub(" ", tex).strip()
    return tex.replace("$", r"\$")


class _Parser:
    def __init__(self, html: str, page_url: str):
        self.soup = BeautifulSoup(html, "lxml")
        self.page_url = page_url
        self.b = DocBuilder("arxiv_html", "arXiv HTML（结构化全文）", page_url)
        self.errors = 0
        self.svg_figures = 0

    # ---------- inline text ----------
    def inline(self, el: Tag | None, skip_tag: bool = False) -> str:
        if el is None:
            return ""
        parts: list[str] = []

        def rec(n: Any) -> None:
            if isinstance(n, Comment):
                return
            if isinstance(n, NavigableString):
                parts.append(str(n).replace("$", r"\$"))
                return
            if not isinstance(n, Tag):
                return
            name, cls = n.name, _cls(n)
            if name == "math":
                tex = _clean_tex(n.get("alttext") or n.get_text(" "))
                if n.get("display") == "block":
                    parts.append(f" $${tex}$$ ")
                else:
                    parts.append(f"${tex}$")
                return
            if name in ("script", "style", "button", "img", "svg", "nav"):
                return
            if "ltx_note" in cls or "ltx_role_footnote" in cls:
                return  # footnotes would break the sentence flow
            if "ltx_ERROR" in cls:
                self.errors += 1
                return
            if skip_tag and "ltx_tag" in cls:
                return
            if name == "br":
                parts.append(" ")
                return
            for c in n.children:
                rec(c)

        rec(el)
        return _WS.sub(" ", "".join(parts)).strip()

    # ---------- blocks ----------
    def equation(self, el: Tag) -> dict[str, Any] | None:
        rows = []
        tags = []
        for tr in el.find_all("tr"):
            if "ltx_eqn_row" not in _cls(tr) and "ltx_equation" not in _cls(tr):
                continue
            cells = []
            for td in tr.find_all("td", recursive=False):
                maths = td.find_all("math")
                if maths:
                    cells.append(" ".join(_clean_tex(m.get("alttext") or "") for m in maths))
            tag = tr.find(class_="ltx_tag_equation")
            if tag:
                tags.append(tag.get_text(strip=True))
            if cells:
                rows.append(" & ".join(cells) if len(cells) == 2 else " ".join(cells))
        if not rows:
            maths = el.find_all("math")
            if not maths:
                return None
            rows = [" ".join(_clean_tex(m.get("alttext") or "") for m in maths)]
        if len(rows) == 1 and "&" not in rows[0]:
            latex = rows[0]
        else:
            latex = "\\begin{aligned}" + " \\\\ ".join(rows) + "\\end{aligned}"
        latex = latex.replace(r"\$", "$")  # display math is stored raw (not inside $..$ text)
        return {"type": "equation", "latex": latex, "tag": ", ".join(tags) or None}

    def table_rows(self, tabular: Tag) -> list[list[dict[str, Any]]]:
        rows = []
        for tr in tabular.find_all("tr"):
            if tr.find_parent("table") is not tabular:
                continue
            row = []
            for td in tr.find_all(["td", "th"], recursive=False):
                cell: dict[str, Any] = {"t": self.inline(td)}
                cs, rs = td.get("colspan"), td.get("rowspan")
                if cs and str(cs).isdigit() and int(cs) > 1:
                    cell["cs"] = int(cs)
                if rs and str(rs).isdigit() and int(rs) > 1:
                    cell["rs"] = int(rs)
                if td.name == "th" or "ltx_th" in _cls(td):
                    cell["h"] = True
                if td.find(class_="ltx_font_bold") is not None or "ltx_font_bold" in _cls(td):
                    cell["b"] = True
                row.append(cell)
            if row:
                rows.append(row)
            if len(rows) >= 300:
                break
        return rows

    def caption_of(self, fig: Tag) -> tuple[str | None, str]:
        caps = [fc for fc in fig.find_all("figcaption") if fc.find_parent("figure") is fig]
        if not caps:
            return None, ""
        cap = caps[0]
        tag = cap.find(class_="ltx_tag")
        label = tag.get_text(" ", strip=True).rstrip(":：. ").strip() if tag else None
        return label or None, self.inline(cap, skip_tag=True).lstrip(":： ").strip()

    def figure(self, fig: Tag) -> dict[str, Any] | None:
        cls = _cls(fig)
        label, caption = self.caption_of(fig)
        is_algo = any(c in cls for c in ("ltx_float_algorithm", "ltx_algorithm")) or (
            fig.find(class_="ltx_listing") is not None and fig.find("img") is None)
        if is_algo:
            return self.code_block(fig, label, caption)
        tabulars = [t for t in fig.find_all("table", class_="ltx_tabular")]
        imgs = fig.find_all("img")
        if ("ltx_table" in cls and tabulars) or (tabulars and not imgs):
            top = [t for t in tabulars if t.find_parent("table", class_="ltx_tabular") is None]
            tables = [r for r in (self.table_rows(t) for t in top) if r]
            if tables:
                return {"type": "table", "label": label, "caption": caption, "tables": tables}
        images = []
        for img in imgs:
            src = img.get("src")
            if src and not src.startswith("data:"):
                images.append(urljoin(self.page_url, src))
        subcaps = []
        for sub in fig.find_all("figure"):
            if sub is fig:
                continue
            sl, sc = self.caption_of(sub)
            if sc:
                subcaps.append(f"{sl + ' ' if sl else ''}{sc}")
        if not images:
            if fig.find("svg") is not None or fig.find(class_="ltx_picture") is not None:
                self.svg_figures += 1
            if not caption:
                return None
        return {"type": "figure", "label": label or ("Table" if "ltx_table" in cls else None), "caption": caption,
                "images": images[:12], "subcaptions": subcaps[:12]}

    def code_block(self, el: Tag, label: str | None = None, caption: str = "") -> dict[str, Any] | None:
        lines = el.find_all(class_="ltx_listingline")
        if lines:
            text = "\n".join(self.inline(ln) for ln in lines)
        else:
            # algorithmic environments: one ltx_p / div per line
            items = [self.inline(p) for p in el.find_all(["p", "div"], class_=re.compile("ltx_p|ltx_listing_line"))]
            items = [i for i in items if i]
            text = "\n".join(items) if items else self.inline(el, skip_tag=True)
        if caption and text.startswith(caption):
            text = text[len(caption):].lstrip()
        if not text and not caption:
            return None
        return {"type": "code", "label": label, "caption": caption, "text": text}

    def list_block(self, el: Tag) -> dict[str, Any] | None:
        items = []
        for li in el.find_all("li", recursive=False):
            # drop the item marker ("•", "1.") rendered as ltx_tag
            txt = self.inline(li, skip_tag=True)
            if txt:
                items.append(txt)
        if not items:
            return None
        return {"type": "list", "ordered": el.name == "ol", "items": items}

    # ---------- traversal ----------
    def handle(self, node: Any, sec: dict[str, Any], level: int) -> None:
        if isinstance(node, Comment):
            return
        if isinstance(node, NavigableString):
            t = _WS.sub(" ", str(node)).strip()
            if len(t) > 1:
                DocBuilder.add(sec, {"type": "paragraph", "text": t.replace("$", r"\$")})
            return
        if not isinstance(node, Tag):
            return
        name, cls = node.name, _cls(node)
        if name == "section":
            if "ltx_paragraph" in cls or "ltx_subparagraph" in cls:
                title = node.find(class_="ltx_title", recursive=False)
                if title:
                    t = self.inline(title)
                    if t:
                        DocBuilder.add(sec, {"type": "heading", "text": t})
                for c in node.children:
                    if c is not title:
                        self.handle(c, sec, level)
            elif "ltx_bibliography" in cls:
                self.bibliography(node)
            else:
                self.section(node, level + 1, "appendix" if sec["kind"] == "appendix" else "body")
            return
        if name in ("h1", "h2", "h3", "h4", "h5", "h6"):
            t = self.inline(node)
            if t:
                DocBuilder.add(sec, {"type": "heading", "text": t})
            return
        if name == "p":
            t = self.inline(node)
            if t:
                DocBuilder.add(sec, {"type": "paragraph", "text": t})
            return
        if name == "table" and ("ltx_equation" in cls or "ltx_equationgroup" in cls):
            eq = self.equation(node)
            if eq:
                DocBuilder.add(sec, eq)
            return
        if name == "table" and "ltx_tabular" in cls:
            rows = self.table_rows(node)
            if rows:
                DocBuilder.add(sec, {"type": "table", "label": None, "caption": "", "tables": [rows]})
            return
        if name in ("ul", "ol"):
            lb = self.list_block(node)
            if lb:
                DocBuilder.add(sec, lb)
            return
        if name == "figure":
            fb = self.figure(node)
            if fb:
                DocBuilder.add(sec, fb)
            return
        if name == "div" and "ltx_listing" in cls:
            cb = self.code_block(node)
            if cb:
                DocBuilder.add(sec, cb)
            return
        if name == "pre":
            DocBuilder.add(sec, {"type": "code", "label": None, "caption": "", "text": node.get_text()})
            return
        if name == "div" and any(c.startswith("ltx_theorem") or c == "ltx_proof" for c in cls):
            title = node.find(class_="ltx_title")
            if title:
                t = self.inline(title)
                if t:
                    DocBuilder.add(sec, {"type": "heading", "text": t})
            for c in node.children:
                if c is not title:
                    self.handle(c, sec, level)
            return
        if name in ("div", "blockquote", "span") and node.find(["p", "table", "figure", "ul", "ol", "div", "section"]):
            for c in node.children:
                self.handle(c, sec, level)
            return
        if name in ("script", "style", "nav", "footer", "header", "button"):
            return
        t = self.inline(node)
        if t:
            DocBuilder.add(sec, {"type": "paragraph", "text": t})

    def section(self, el: Tag, level: int, kind: str) -> None:
        cls = _cls(el)
        if "ltx_appendix" in cls:
            kind = "appendix"
        title_el = None
        for c in el.children:
            if isinstance(c, Tag) and c.name in ("h1", "h2", "h3", "h4", "h5", "h6"):
                title_el = c
                break
        number = None
        title = ""
        if title_el is not None:
            tag = title_el.find(class_="ltx_tag")
            if tag:
                number = tag.get_text(" ", strip=True).rstrip(".") or None
            title = self.inline(title_el, skip_tag=True)
        sec = self.b.section(title or "（无标题章节）", level=min(level, 3), number=number, kind=kind)
        for c in el.children:
            if c is title_el:
                continue
            self.handle(c, sec, level)

    def bibliography(self, el: Tag) -> None:
        sec = self.b.section("References", level=1, kind="references")
        for li in el.find_all("li", class_="ltx_bibitem"):
            tag = li.find(class_="ltx_tag")
            label = tag.get_text(" ", strip=True) if tag else None
            blocks = li.find_all(class_="ltx_bibblock")
            text = " ".join(self.inline(b) for b in blocks) if blocks else self.inline(li, skip_tag=True)
            if text:
                DocBuilder.add(sec, {"type": "reference", "label": label, "text": text})

    def parse(self) -> dict[str, Any]:
        article = self.soup.find("article", class_="ltx_document")
        if article is None:
            raise HtmlNotAvailable("页面不包含 LaTeXML 文档")
        title_el = article.find(class_="ltx_title_document")
        self.b.doc["title"] = self.inline(title_el) if title_el else ""

        abstract = article.find("div", class_="ltx_abstract")
        if abstract is not None:
            sec = self.b.section("Abstract", level=1, kind="abstract")
            for p in abstract.find_all("p"):
                t = self.inline(p)
                if t:
                    DocBuilder.add(sec, {"type": "paragraph", "text": t})

        front = None
        for child in article.children:
            if not isinstance(child, Tag):
                continue
            cls = _cls(child)
            if child.name == "section":
                if "ltx_bibliography" in cls:
                    self.bibliography(child)
                else:
                    lvl = next((v for k, v in SECTION_LEVEL.items() if k in cls), 1)
                    self.section(child, lvl, "appendix" if "ltx_appendix" in cls else "body")
                continue
            if child is title_el or any(c in cls for c in ("ltx_authors", "ltx_abstract", "ltx_dates", "ltx_classification",
                                                            "ltx_keywords", "ltx_acknowledgements", "ltx_pagination")):
                if "ltx_keywords" in cls or "ltx_acknowledgements" in cls:
                    pass
                continue
            if child.name in ("h1",):
                continue
            if child.name in ("figure", "div", "p", "table", "ul", "ol"):
                if front is None:
                    front = self.b.section("正文前内容", level=1, kind="front")
                self.handle(child, front, 1)

        body_paragraphs = sum(1 for s in self.b.doc["sections"] if s["kind"] in ("body", "appendix")
                              for blk in s["blocks"] if blk["type"] == "paragraph")
        if body_paragraphs < 3:
            raise HtmlNotAvailable("HTML 版本内容过少，可能转换失败")
        if self.errors:
            self.b.warn(f"有 {self.errors} 处 LaTeX 命令未能被 arXiv 转换，已在文中省略。")
        if self.svg_figures:
            self.b.warn(f"有 {self.svg_figures} 张矢量图无法在此显示，请查看原文 PDF。")
        # Move the front-matter section (teaser figures) right after the abstract.
        secs = self.b.doc["sections"]
        if front is not None and front in secs:
            secs.remove(front)
            idx = 1 if secs and secs[0]["kind"] == "abstract" else 0
            secs.insert(idx, front)
        return self.b.finish()


def parse_arxiv_html(html: str, page_url: str) -> dict[str, Any]:
    return _Parser(html, page_url).parse()
