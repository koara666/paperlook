"""Reading notes and citations (BibTeX / GB/T 7714)."""
from datetime import date

from paperlook import cite

GIFT = {
    "title": "GIFT: Representation Geometry Matters for Single-Domain Generalized Object Detection",
    "authors": ["Yin Zhang", "Yaoyue Zheng", "Yongqiang Zhang", "Bogdan Raducanu", "Dan Li"],
    "published": "2026-10-26", "arxiv_id": "2610.35374", "categories": ["cs.CV"], "venue": None, "doi": None,
}


def _insert(title="A Sufficiently Long Paper Title For Testing", arxiv_id="2610.99999", **extra):
    from paperlook import papers

    return papers.upsert({"title": title, "abstract": "abs", "authors": ["Ha-Thanh Nguyen", "Anna Smith"],
                          "published": "2026-10-20", "date_quality": "exact", "arxiv_id": arxiv_id, "categories": ["cs.CL"],
                          "sources": [{"source": "arxiv", "id": arxiv_id, "url": None}], "signals": {}, **extra})


def test_bibtex_for_arxiv_preprint():
    assert cite.bibtex(GIFT) == (
        "@misc{zhang2026gift,\n"
        "  title = {{GIFT: Representation Geometry Matters for Single-Domain Generalized Object Detection}},\n"
        "  author = {Yin Zhang and Yaoyue Zheng and Yongqiang Zhang and Bogdan Raducanu and Dan Li},\n"
        "  year = {2026},\n  eprint = {2610.35374},\n  archivePrefix = {arXiv},\n  primaryClass = {cs.CV},\n"
        "  url = {https://arxiv.org/abs/2610.35374}\n}"
    )


def test_bibtex_escapes_specials_but_keeps_math_and_picks_venue_type():
    p = {"title": "S$^2$-RL: Q&A on 100% of data_sets", "authors": ["Wang, Haoyu"], "published": "2025-01-02",
         "venue": "Proceedings of the IEEE/CVF Conference on Computer Vision and Pattern Recognition", "doi": "10.1/x"}
    b = cite.bibtex(p)
    assert b.startswith("@inproceedings{wang2025srl,")
    assert r"title = {{S$^2$-RL: Q\&A on 100\% of data\_sets}}" in b
    assert "booktitle = {Proceedings of the IEEE/CVF" in b and "doi = {10.1/x}" in b
    assert cite.bibtex({**p, "venue": "Pattern Recognition"}).startswith("@article{")
    assert "journal = {Pattern Recognition}" in cite.bibtex({**p, "venue": "Pattern Recognition"})
    # duplicate keys get suffixes
    many = cite.bibtex_many([GIFT, GIFT, GIFT])
    assert "{zhang2026gift," in many and "{zhang2026gifta," in many and "{zhang2026giftb," in many


def test_gbt7714():
    assert cite.gbt7714(GIFT, accessed=date(2026, 10, 28)) == (
        "ZHANG Y, ZHENG Y, ZHANG Y, et al. GIFT: Representation Geometry Matters for Single-Domain Generalized "
        "Object Detection[EB/OL]. (2026-10-26)[2026-10-28]. https://arxiv.org/abs/2610.35374."
    )
    conf = {"title": "T", "authors": ["Ha-Thanh Nguyen", "张三"], "published": "2025-06-01", "venue": "CVPR 2025"}
    assert cite.gbt7714(conf) == "NGUYEN H T, 张三. T[C]//CVPR 2025. 2025."
    journal = {"title": "T", "authors": ["A B"], "published": "2024-01-01", "venue": "Nature", "doi": "10.1038/x"}
    assert cite.gbt7714(journal) == "B A. T[J]. Nature, 2024. DOI: 10.1038/x."


def test_notes_filter_search_and_export(client):
    pid = _insert()
    other = _insert(title="Another Quite Long Paper Title About Something Else", arxiv_id="2610.88888")
    st = client.patch(f"/api/papers/{pid}/state", json={"note": "可借鉴：门控残差更新"}).json()
    assert st["note"] == "可借鉴：门控残差更新"
    noted = client.get("/api/papers", params={"filter": "noted"}).json()
    assert noted["total"] == 1 and noted["items"][0]["paper"]["state"]["note"] == "可借鉴：门控残差更新"
    assert client.get("/api/papers", params={"q": "门控残差"}).json()["total"] == 1
    md = client.get(f"/api/papers/{pid}/export", params={"type": "analysis"}).text
    assert "## 我的笔记" in md and "可借鉴：门控残差更新" in md
    assert "我的笔记" not in client.get(f"/api/papers/{other}/export", params={"type": "analysis"}).text
    # clearing the note removes it from the filter
    client.patch(f"/api/papers/{pid}/state", json={"note": "  "})
    assert client.get("/api/papers", params={"filter": "noted"}).json()["total"] == 0


def test_cite_endpoints(client):
    pid = _insert()
    _insert(title="Another Quite Long Paper Title About Something Else", arxiv_id="2610.88888")
    c = client.get(f"/api/papers/{pid}/cite").json()
    assert c["bibtex"].startswith("@misc{nguyen2026sufficiently,") and c["gbt7714"].startswith("NGUYEN H T, SMITH A. ")
    client.patch(f"/api/papers/{pid}/state", json={"starred": True})
    r = client.get("/api/library/bibtex", params={"filter": "starred"})
    assert r.status_code == 200 and "attachment" in r.headers["content-disposition"]
    assert r.text.count("@misc{") == 1
    assert client.get("/api/library/bibtex").text.count("@misc{") == 2
    assert client.get("/api/library/bibtex", params={"filter": "noted"}).status_code == 404
