"""Curated list of well-established venues, used as ONE quality signal.

A venue match is reported as a verifiable fact ("authors state: accepted at CVPR 2026"), never as a
rating of the individual paper. Tiers loosely follow CCF-A / CORE A* conventions:
  A -> 1.0   B -> 0.75   Findings -> 0.7   Workshop -> 0.4
Extend VENUES freely; each entry: (canonical, tier, acronym regex (case-sensitive) | None,
full-name regex (case-insensitive) | None, anchored full-name (whole venue string) bool).
"""
from __future__ import annotations

import re
from dataclasses import dataclass

TIER_SCORE = {"A": 1.0, "B": 0.75, "findings": 0.7, "workshop": 0.4}

VENUES: list[tuple[str, str, str | None, str | None, bool]] = [
    # Computer vision
    ("CVPR", "A", r"CVPR", r"computer vision and pattern recognition", False),
    ("ICCV", "A", r"ICCV", r"international conference on computer vision", False),
    ("ECCV", "A", r"ECCV", r"european conference on computer vision", False),
    ("IEEE TPAMI", "A", r"T-?PAMI", r"transactions on pattern analysis and machine intelligence", False),
    ("IJCV", "A", r"IJCV", r"international journal of computer vision", False),
    ("IEEE TIP", "A", None, r"transactions on image processing", False),
    ("WACV", "B", r"WACV", r"winter conference on applications of computer vision", False),
    ("BMVC", "B", r"BMVC", r"british machine vision conference", False),
    ("IEEE TCSVT", "B", r"TCSVT", r"transactions on circuits and systems for video technology", False),
    ("Pattern Recognition", "B", None, r"pattern recognition", True),
    # Machine learning / AI
    ("NeurIPS", "A", r"NeurIPS|NIPS", r"neural information processing systems", False),
    ("ICML", "A", r"ICML", r"international conference on machine learning", False),
    ("ICLR", "A", r"ICLR", r"international conference on learning representations", False),
    ("JMLR", "A", r"JMLR", r"journal of machine learning research", False),
    ("COLT", "A", r"COLT", r"conference on learning theory", False),
    ("TMLR", "B", r"TMLR", r"transactions on machine learning research", False),
    ("AISTATS", "B", r"AISTATS", r"artificial intelligence and statistics", False),
    ("UAI", "B", r"UAI", r"uncertainty in artificial intelligence", False),
    ("IEEE TNNLS", "B", r"TNNLS", r"transactions on neural networks and learning systems", False),
    ("AAAI", "A", r"AAAI", r"aaai conference on artificial intelligence", False),
    ("IJCAI", "A", r"IJCAI", r"international joint conference on artificial intelligence", False),
    ("Artificial Intelligence", "A", None, r"artificial intelligence", True),
    ("Nature Machine Intelligence", "A", None, r"nature machine intelligence", False),
    # NLP
    ("ACL", "A", r"ACL", r"annual meeting of the association for computational linguistics", False),
    ("EMNLP", "A", r"EMNLP", r"empirical methods in natural language processing", False),
    ("NAACL", "A", r"NAACL", r"north american chapter of the association for computational linguistics", False),
    ("TACL", "A", r"TACL", r"transactions of the association for computational linguistics", False),
    ("COLING", "B", r"COLING", r"international conference on computational linguistics", False),
    ("EACL", "B", r"EACL", r"european chapter of the association for computational linguistics", False),
    # IR / data mining / web / databases
    ("SIGIR", "A", r"SIGIR", r"research and development in information retrieval", False),
    ("KDD", "A", r"(?:SIG)?KDD", r"knowledge discovery and data mining", False),
    ("WWW", "A", r"WWW|TheWebConf", r"the web conference|world wide web conference", False),
    ("WSDM", "B", r"WSDM", r"web search and data mining", False),
    ("CIKM", "B", r"CIKM", r"information and knowledge management", False),
    ("RecSys", "B", r"RecSys", r"conference on recommender systems", False),
    ("ECIR", "B", r"ECIR", r"european conference on information retrieval", False),
    ("ACM TOIS", "A", r"TOIS", r"transactions on information systems", False),
    ("IEEE TKDE", "A", r"TKDE", r"transactions on knowledge and data engineering", False),
    ("ICDE", "A", r"ICDE", r"international conference on data engineering", False),
    ("VLDB", "A", r"P?VLDB", r"very large data bases", False),
    ("SIGMOD", "A", r"SIGMOD", r"management of data", False),
    ("ICDM", "B", r"ICDM", r"international conference on data mining", False),
    # Multimedia
    ("ACM MM", "A", r"ACM ?MM|ACM Multimedia", r"acm international conference on multimedia", False),
    ("IEEE TMM", "B", None, r"transactions on multimedia", False),
    ("ICME", "B", r"ICME", r"international conference on multimedia and expo", False),
    # Networking & systems
    ("SIGCOMM", "A", r"SIGCOMM", None, False),
    ("NSDI", "A", r"NSDI", r"networked systems design and implementation", False),
    ("MobiCom", "A", r"MobiCom|MOBICOM", r"mobile computing and networking", False),
    ("INFOCOM", "A", r"INFOCOM", None, False),
    ("IEEE/ACM ToN", "A", r"ToN", r"transactions on networking", False),
    ("IEEE JSAC", "A", r"JSAC", r"journal on selected areas in communications", False),
    ("IEEE TMC", "A", None, r"transactions on mobile computing", False),
    ("MobiSys", "A", r"MobiSys", None, False),
    ("SenSys", "B", r"SenSys", None, False),
    ("IMC", "B", r"IMC", r"internet measurement conference", False),
    ("CoNEXT", "B", r"CoNEXT", None, False),
    ("ICNP", "B", r"ICNP", None, False),
    ("OSDI", "A", r"OSDI", r"operating systems design and implementation", False),
    ("SOSP", "A", r"SOSP", r"symposium on operating systems principles", False),
    ("EuroSys", "A", r"EuroSys", None, False),
    ("USENIX ATC", "A", r"USENIX ATC", r"usenix annual technical conference", False),
    ("ASPLOS", "A", r"ASPLOS", None, False),
    ("ISCA", "A", r"ISCA", r"international symposium on computer architecture", False),
    ("MICRO", "A", r"MICRO", None, False),
    ("HPCA", "A", r"HPCA", None, False),
    ("MLSys", "B", r"MLSys", None, False),
    # Robotics
    ("RSS", "A", r"RSS", r"robotics: science and systems", False),
    ("CoRL", "A", r"CoRL", r"conference on robot learning", False),
    ("ICRA", "B", r"ICRA", r"international conference on robotics and automation", False),
    ("IROS", "B", r"IROS", r"intelligent robots and systems", False),
    ("IEEE T-RO", "A", r"T-RO", r"ieee transactions on robotics", False),
    ("IEEE RA-L", "B", r"RA-L|RAL", r"robotics and automation letters", False),
    # Graphics, security, HCI, SE, theory, speech, medical
    ("SIGGRAPH", "A", r"SIGGRAPH", None, False),
    ("ACM TOG", "A", r"TOG", r"transactions on graphics", False),
    ("ACM CCS", "A", r"CCS", r"computer and communications security", False),
    ("IEEE S&P", "A", r"S&P|Oakland", r"symposium on security and privacy", False),
    ("USENIX Security", "A", r"USENIX Security", None, False),
    ("NDSS", "A", r"NDSS", None, False),
    ("CHI", "A", r"CHI", r"conference on human factors in computing systems", False),
    ("UIST", "A", r"UIST", None, False),
    ("ICSE", "A", r"ICSE", r"international conference on software engineering", False),
    ("FSE", "A", r"(?:ESEC/)?FSE", r"foundations of software engineering", False),
    ("STOC", "A", r"STOC", r"symposium on theory of computing", False),
    ("FOCS", "A", r"FOCS", r"foundations of computer science", False),
    ("SODA", "A", r"SODA", r"symposium on discrete algorithms", False),
    ("ICASSP", "B", r"ICASSP", r"acoustics, speech,? and signal processing", False),
    ("Interspeech", "B", r"INTERSPEECH|Interspeech", None, False),
    ("IEEE/ACM TASLP", "B", r"TASLP", r"transactions on audio, speech,? and language processing", False),
    ("MICCAI", "B", r"MICCAI", r"medical image computing and computer.assisted intervention", False),
    ("Medical Image Analysis", "B", r"MedIA", r"medical image analysis", True),
    ("IEEE TMI", "B", None, r"transactions on medical imaging", False),
    # General science
    ("Nature", "A", None, r"nature", True),
    ("Science", "A", None, r"science", True),
    ("PNAS", "A", r"PNAS", r"proceedings of the national academy of sciences", False),
    ("Nature Communications", "B", None, r"nature communications", False),
    ("Science Advances", "B", None, r"science advances", False),
]


@dataclass
class VenueMatch:
    venue: str
    tier: str
    score: float
    kind: str  # accepted | published | workshop | findings
    evidence: str
    year: str | None = None

    @property
    def display(self) -> str:
        return f"{self.venue} {self.year}" if self.year else self.venue


def _compile():
    out = []
    for canonical, tier, acr, full, anchored in VENUES:
        # "CVPRW"/"ICCVW" style workshop acronyms are captured by the optional W group.
        w_suffix = "" if canonical == "WWW" else "(?P<w>W)?"
        acr_re = re.compile(rf"(?<![A-Za-z])(?:{acr}){w_suffix}(?![A-Za-z])") if acr else None
        if full:
            full_re = re.compile(rf"^\s*(?:the\s+)?{full}\s*$" if anchored else full, re.I)
        else:
            full_re = None
        out.append((canonical, tier, acr_re, full_re, anchored))
    return out


_COMPILED = _compile()

_NEG = re.compile(r"\b(submitted|submitting|under review|in submission|submission to|rejected|preprint of a paper under|"
                  r"for review|rolling review|ARR|recommends?|recommended|considered for|invited to)\b", re.I)
_POS = re.compile(r"\b(accepted|accept|to appear|appear(?:s|ed)? (?:in|at)|published|camera[- ]ready|proceedings|oral|spotlight|poster|presented)\b", re.I)
_YEAR = re.compile(r"(?:'|’)?\s?(?:20\d\d|\d\d)\b")
_WORKSHOP = re.compile(r"\bworkshops?\b", re.I)
_FINDINGS = re.compile(r"\bfindings\b", re.I)
_HONOR = re.compile(r"\b(oral|spotlight|best paper|highlight)\b", re.I)


def _match_any(text: str, use_full_anchored: bool = False):
    for canonical, tier, acr_re, full_re, anchored in _COMPILED:
        if acr_re is not None:
            m = acr_re.search(text)
            if m:
                if m.groupdict().get("w"):
                    tier = "workshop"
                return canonical, tier, acr_re
        if full_re is not None and (not anchored or use_full_anchored) and full_re.search(text):
            return canonical, tier, full_re
    return None


def venue_from_comment(comment: str | None, journal_ref: str | None = None) -> VenueMatch | None:
    """Detect an acceptance/publication claim in arXiv author comments or journal_ref."""
    if journal_ref:
        m = _match_any(journal_ref)
        if m:
            return _make(m[0], m[1], journal_ref, "published")
    if not comment:
        return None
    for clause in re.split(r"[.;|\n]|\s-\s", comment):
        clause = clause.strip()
        if not clause or _NEG.search(clause):
            continue
        m = _match_any(clause)
        if not m:
            continue
        canonical, tier, rx = m
        hit = rx.search(clause)
        after = clause[hit.end(): hit.end() + 8] if hit else ""
        has_year = bool(_YEAR.match(after.strip() or "x")) or bool(re.search(r"20\d\d", clause))
        if _POS.search(clause) or has_year:
            return _make(canonical, tier, clause, "accepted")
    return None


def venue_from_name(venue: str | None) -> VenueMatch | None:
    """Match a venue string from OpenAlex / Semantic Scholar / PubMed metadata."""
    if not venue:
        return None
    m = _match_any(venue, use_full_anchored=True)
    if not m:
        return None
    return _make(m[0], m[1], venue, "published")


def _make(canonical: str, tier: str, evidence: str, kind: str) -> VenueMatch:
    if tier == "workshop" or _WORKSHOP.search(evidence):
        tier_used, kind = "workshop", "workshop"
    elif _FINDINGS.search(evidence):
        tier_used, kind = "findings", "findings"
    else:
        tier_used = tier
    score = TIER_SCORE[tier_used]
    if kind == "accepted" and _HONOR.search(evidence) and tier_used in ("A", "B"):
        score = min(1.0, score + 0.05)
    ym = re.search(r"\b(20\d\d)\b", evidence)
    return VenueMatch(venue=canonical, tier=tier_used, score=score, kind=kind, evidence=evidence.strip()[:160],
                      year=ym.group(1) if ym else None)
