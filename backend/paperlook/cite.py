"""Citations for a paper: BibTeX and GB/T 7714-2015 (the format Chinese theses and journals ask for).

Only facts the sources provide are used. An author's "accepted at …" comment is a claim, not a
bibliographic record, so arXiv papers are cited as preprints unless a source reports a venue.
"""
from __future__ import annotations

import re
import unicodedata
from datetime import date
from typing import Any

_CONF = re.compile(r"conference|proceedings|workshop|symposium|\b(?:NeurIPS|NIPS|ICML|ICLR|CVPR|ICCV|ECCV|ACL|EMNLP|NAACL|"
                   r"AAAI|IJCAI|KDD|WWW|SIGIR|SIGGRAPH|MICCAI|COLING|INTERSPEECH|ICASSP|ICRA|IROS|CoRL|RSS)\b", re.I)
_STOP = {"a", "an", "the", "on", "of", "for", "in", "to", "with", "and", "towards", "toward", "via", "is", "are", "from", "by"}


def _ascii(s: str) -> str:
    return unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode("ascii")


def _split_name(name: str) -> tuple[str, list[str]]:
    """(surname, given names). 'Zhang, Yin' and 'Yin Zhang' both give ('Zhang', ['Yin'])."""
    name = " ".join(name.split())
    if "," in name:
        last, _, first = name.partition(",")
        return last.strip(), first.split()
    parts = name.split(" ")
    return parts[-1], parts[:-1]


def _is_cjk(s: str) -> bool:
    return any("一" <= ch <= "鿿" for ch in s)


def _venue(p: dict[str, Any]) -> str | None:
    v = (p.get("venue") or "").strip()
    return v if v and not re.fullmatch(r"(?i)arxiv(\.org)?( \(cornell university\))?", v) else None


def _year(p: dict[str, Any]) -> str:
    return (p.get("published") or "")[:4]


def bibtex_key(p: dict[str, Any]) -> str:
    authors = p.get("authors") or []
    last = re.sub(r"[^a-z]", "", _ascii(_split_name(authors[0])[0]).lower()) if authors else ""
    words = [re.sub(r"[^a-z0-9]", "", w) for w in _ascii(re.sub(r"\$[^$]*\$", "", p.get("title") or "")).lower().split()]
    word = next((w for w in words if w and w not in _STOP), "")
    return f"{last or 'paper'}{_year(p)}{word}"


def _tex(s: str) -> str:
    """Escape BibTeX specials outside $…$ math (titles may contain LaTeX such as S$^2$-RL)."""
    parts = re.split(r"(\$[^$]*\$)", s)
    for i in range(0, len(parts), 2):
        parts[i] = re.sub(r"([&%#_])", r"\\\1", parts[i])
    return "".join(parts)


def bibtex(p: dict[str, Any], key: str | None = None) -> str:
    venue = _venue(p)
    fields: list[tuple[str, str]] = [("title", "{" + _tex(p.get("title") or "") + "}"),
                                     ("author", " and ".join(_tex(a) for a in p.get("authors") or []))]
    if venue:
        kind = "inproceedings" if _CONF.search(venue) else "article"
        fields.append(("booktitle" if kind == "inproceedings" else "journal", _tex(venue)))
    else:
        kind = "misc" if p.get("arxiv_id") else "article"
    if _year(p):
        fields.append(("year", _year(p)))
    if p.get("arxiv_id"):
        cats = p.get("categories") or []
        fields += [("eprint", p["arxiv_id"]), ("archivePrefix", "arXiv")] + ([("primaryClass", cats[0])] if cats else [])
    if p.get("doi"):
        fields.append(("doi", p["doi"]))
    url = f"https://arxiv.org/abs/{p['arxiv_id']}" if p.get("arxiv_id") else p.get("url")
    if url:
        fields.append(("url", url))
    body = ",\n".join(f"  {k} = {{{v}}}" for k, v in fields if v)
    return f"@{kind}{{{key or bibtex_key(p)},\n{body}\n}}"


def bibtex_many(papers: list[dict[str, Any]]) -> str:
    used: dict[str, int] = {}
    out = []
    for p in papers:
        key = bibtex_key(p)
        n = used.get(key, 0)
        used[key] = n + 1
        out.append(bibtex(p, key + (chr(ord("a") + n - 1) if 0 < n <= 26 else (str(n) if n else ""))))
    return "\n\n".join(out) + "\n"


def _gbt_author(name: str) -> str:
    if _is_cjk(name):
        return name.replace(" ", "")
    last, given = _split_name(name)
    initials = " ".join(g[0].upper() for part in given for g in part.split("-") if g)
    return f"{last.upper()} {initials}".strip()


def gbt7714(p: dict[str, Any], accessed: date | None = None) -> str:
    """GB/T 7714-2015 reference: journal [J], conference [C], otherwise an online preprint [EB/OL]."""
    authors = p.get("authors") or []
    names = [_gbt_author(a) for a in authors[:3]]
    who = ", ".join(names) + (", et al" if len(authors) > 3 else "")
    title = re.sub(r"\$([^$]*)\$", r"\1", p.get("title") or "").strip()
    venue, year = _venue(p), _year(p)
    doi = f" DOI: {p['doi']}." if p.get("doi") and not p["doi"].lower().startswith("10.48550") else ""
    head = f"{who}. {title}" if who else title
    if venue and _CONF.search(venue):
        return f"{head}[C]//{venue}. {year}.{doi}".replace(". .", ".")
    if venue:
        return f"{head}[J]. {venue}, {year}.{doi}".replace(", .", ".")
    url = f"https://arxiv.org/abs/{p['arxiv_id']}" if p.get("arxiv_id") else (p.get("url") or "")
    pub = f"({p['published']})" if p.get("published") else ""
    cited = f"[{(accessed or date.today()).isoformat()}]"
    return f"{head}[EB/OL]. {pub}{cited}. {url}".rstrip(". ") + "."
