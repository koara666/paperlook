from datetime import date

from paperlook.ai.translate import Unit, chunk_units, collect_units, mask_math, unmask
from paperlook.ai.analyze import verify_quotes
from paperlook.fulltext.arxiv_html import parse_arxiv_html
from paperlook.fulltext.pdf import markdown_to_doc
from paperlook.recommend.dedupe import merge
from paperlook.sources.arxiv import build_query, parse_feed
from paperlook.sources.base import RawPaper, SourceQuery
from paperlook.sources.openalex import rebuild_abstract

ATOM = """<?xml version='1.0' encoding='UTF-8'?>
<feed xmlns:opensearch="http://a9.com/-/spec/opensearch/1.1/" xmlns:arxiv="http://arxiv.org/schemas/atom" xmlns="http://www.w3.org/2005/Atom">
  <opensearch:totalResults>1</opensearch:totalResults>
  <entry>
    <id>http://arxiv.org/abs/2610.12345v2</id>
    <title>A  Test
      Paper</title>
    <updated>2026-10-24T10:00:00Z</updated>
    <published>2026-10-20T17:59:51Z</published>
    <summary>We propose X. Code at https://github.com/foo/bar.</summary>
    <category term="cs.LG" scheme="http://arxiv.org/schemas/atom"/>
    <category term="cs.CV" scheme="http://arxiv.org/schemas/atom"/>
    <arxiv:primary_category term="cs.CV"/>
    <arxiv:comment>Accepted at CVPR 2026, 12 pages</arxiv:comment>
    <author><name>Ada Lovelace</name></author>
  </entry>
</feed>"""

HTML = """<html><body><article class="ltx_document">
<h1 class="ltx_title ltx_title_document">Doc Title</h1>
<div class="ltx_abstract"><h6>Abstract</h6><p class="ltx_p">We study $x$ costs.</p></div>
<section id="S1" class="ltx_section"><h2 class="ltx_title ltx_title_section"><span class="ltx_tag ltx_tag_section">1 </span>Introduction</h2>
 <div class="ltx_para"><p class="ltx_p">First paragraph with <math alttext="a^{2}" display="inline"><mi>a</mi></math> math and a cite <cite>[1]</cite>.</p></div>
 <div class="ltx_para"><p class="ltx_p">Second paragraph.</p>
  <table class="ltx_equation ltx_eqn_table"><tr class="ltx_equation ltx_eqn_row"><td class="ltx_eqn_cell"><math alttext="E=mc^{2}" display="block"></math></td><td class="ltx_eqn_cell ltx_eqn_eqno"><span class="ltx_tag ltx_tag_equation">(1)</span></td></tr></table>
 </div>
 <div class="ltx_para"><p class="ltx_p">Third paragraph costs 5$ only.</p></div>
 <figure class="ltx_figure"><img src="2610.1/x1.png"/><figcaption class="ltx_caption"><span class="ltx_tag ltx_tag_figure">Figure 1: </span>A figure.</figcaption></figure>
 <figure class="ltx_table"><figcaption class="ltx_caption"><span class="ltx_tag ltx_tag_table">Table 1: </span>Results.</figcaption>
   <table class="ltx_tabular"><tr><td class="ltx_td">Model</td><td class="ltx_td">Acc</td></tr><tr><td class="ltx_td">Ours</td><td class="ltx_td"><span class="ltx_font_bold">91.2</span></td></tr></table></figure>
 <section class="ltx_subsection"><h3 class="ltx_title"><span class="ltx_tag">1.1 </span>Sub</h3><div class="ltx_para"><ul class="ltx_itemize"><li><span class="ltx_tag">•</span><div class="ltx_para"><p>item one</p></div></li></ul></div></section>
</section>
<section class="ltx_bibliography"><h2 class="ltx_title">References</h2><ul class="ltx_biblist">
 <li class="ltx_bibitem"><span class="ltx_tag ltx_tag_bibitem">[1]</span><span class="ltx_bibblock">A. Author. A paper. 2024.</span></li></ul></section>
</article></body></html>"""


def test_arxiv_feed_parsing():
    papers, total = parse_feed(ATOM)
    assert total == 1
    p = papers[0]
    assert p.arxiv_id == "2610.12345" and p.title == "A Test Paper"
    assert p.published == date(2026, 10, 20) and p.date_quality == "exact"
    assert p.categories[0] == "cs.CV"  # primary first
    assert p.signals["code_url"] == "https://github.com/foo/bar"


def test_arxiv_query_builder():
    q = build_query(SourceQuery(keywords=['vision "language"', "RAG"], exclude=[], categories=["cs.CV"],
                                date_from=date(2026, 10, 19), date_to=date(2026, 10, 26)))
    assert '(cat:cs.CV)' in q and 'ti:"RAG" OR abs:"RAG"' in q
    assert "submittedDate:[202610190000 TO 202610270000]" in q
    assert '""' not in q


def test_openalex_abstract_rebuild():
    assert rebuild_abstract({"world": [1], "hello": [0]}) == "hello world"


def test_dedupe_merges_and_prefers_earliest_exact_date():
    a = RawPaper(source="arxiv", source_id="2610.1", title="Great Paper On Things And Stuff", arxiv_id="2610.1",
                 published=date(2026, 10, 20), abstract="abs", url="https://arxiv.org/abs/2610.1")
    b = RawPaper(source="openalex", source_id="W1", title="Great paper on things and stuff.", doi="10.1/xyz",
                 published=date(2026, 10, 24), venue="IJCV", openalex_id="W1", signals={"citations": 3})
    c = RawPaper(source="openalex", source_id="W2", title="Different", doi="10.48550/arxiv.2610.1", published=date(2026, 10, 21))
    merged = merge([a, b, c])
    assert len(merged) == 1
    m = merged[0]
    assert m["published"] == "2026-10-20" and m["venue"] == "IJCV" and m["doi"] == "10.1/xyz"
    assert {s["source"] for s in m["sources"]} == {"arxiv", "openalex"}


def test_html_parser_structure():
    doc = parse_arxiv_html(HTML, "https://arxiv.org/html/2610.1v1")
    kinds = [s["kind"] for s in doc["sections"]]
    assert kinds[0] == "abstract" and "references" in kinds
    intro = next(s for s in doc["sections"] if s["title"] == "Introduction")
    assert intro["number"] == "1"
    types = [b["type"] for b in intro["blocks"]]
    assert types.count("paragraph") == 3 and "equation" in types and "figure" in types and "table" in types
    para = intro["blocks"][0]["text"]
    assert "$a^{2}$" in para and "[1]" in para
    eq = next(b for b in intro["blocks"] if b["type"] == "equation")
    assert eq["latex"] == "E=mc^{2}" and eq["tag"] == "(1)"
    fig = next(b for b in intro["blocks"] if b["type"] == "figure")
    assert fig["images"] == ["https://arxiv.org/html/2610.1/x1.png"] and fig["label"] == "Figure 1"
    tab = next(b for b in intro["blocks"] if b["type"] == "table")
    assert tab["tables"][0][1][1] == {"t": "91.2", "b": True}
    third = [b for b in intro["blocks"] if b["type"] == "paragraph"][2]["text"]
    assert r"5\$" in third  # literal dollar escaped
    sub = next(s for s in doc["sections"] if s["title"] == "Sub")
    assert sub["level"] == 2 and sub["blocks"][0]["items"] == ["item one"]
    refs = next(s for s in doc["sections"] if s["kind"] == "references")
    assert refs["blocks"][0]["label"] == "[1]"


def test_units_skip_references_and_equations():
    doc = parse_arxiv_html(HTML, "https://arxiv.org/html/2610.1v1")
    units = collect_units(doc, include_appendix=True)
    ids = [u.id for u in units]
    assert any(i.endswith("::caption") for i in ids)
    assert not any("A paper. 2024" in u.text for u in units)
    assert not any("E=mc" in u.text for u in units)


def test_math_masking_roundtrip():
    text = r"Let $x_i$ and $$\sum_j y_j$$ cost 5\$ and $z$."
    masked, mapping = mask_math(text)
    assert "$" not in masked.replace(r"\$", "") and len(mapping) == 3
    translated = masked.replace("Let", "设").replace("cost", "花费")
    restored, missing = unmask(translated, mapping)
    assert missing == 0 and "$x_i$" in restored and r"$$\sum_j y_j$$" in restored
    _, missing = unmask(translated.replace("⟦M2⟧", ""), mapping)
    assert missing == 1


def test_chunking_packs_small_sections():
    units = [Unit(f"s{s}.b{i}", f"s{s}", "paragraph", "x" * 300) for s in range(10) for i in range(3)]
    chunks = chunk_units(units)
    assert sum(len(c) for c in chunks) == 30 and len(chunks) < 10
    big = [Unit(f"s1.b{i}", "s1", "paragraph", "y" * 2000) for i in range(5)]
    assert all(sum(len(u.text) for u in c) <= 4500 for c in chunk_units(big))


def test_quote_verification():
    src = "Introduction. We propose a novel method for robust alignment of modalities. Results follow."
    items = [{"quote": "We propose a novel method for robust alignment of modalities."},
             {"quote": "We propose a novel method for robust alignment of all modalities."},
             {"quote": "Completely invented sentence that is not there."}, {"quote": ""}]
    verify_quotes(items, src)
    assert [i["verified"] for i in items] == ["exact", "partial", "not_found", "missing"]


def test_pdf_markdown_conversion():
    md = """# **A Paper Title**

## Abstract

We do things.

## 1. Introduction

This is a long para-
graph that continues here.

Figure 1: A caption here.

## 2.1 Details

𝑥 = 𝑦 + 𝑧 (1)

| A | B |
|---|---|
| 1 | 2 |

## References

[1] First ref. [2] Second ref.

## A. Appendix stuff

More text here that is long enough.
"""
    doc = markdown_to_doc(md, "PDF", "u")
    assert doc["title"] == "A Paper Title"
    secs = {s["title"]: s for s in doc["sections"]}
    assert secs["Introduction"]["number"] == "1"
    assert secs["Introduction"]["blocks"][0]["text"] == "This is a long paragraph that continues here."
    assert secs["Introduction"]["blocks"][1]["type"] == "figure"
    assert secs["Details"]["level"] == 2
    assert secs["Details"]["blocks"][0]["type"] == "unparsed"
    assert secs["Details"]["blocks"][1]["type"] == "table"
    assert len(secs["References"]["blocks"]) == 2
    assert secs["Appendix stuff"]["kind"] == "appendix"


def test_latex_typography_outside_math_only():
    from paperlook.textutil import latex_typography

    assert latex_typography("text--image---audio ``quoted'' $a--b$") == "text–image—audio “quoted” $a--b$"
