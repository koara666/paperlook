"""Registry of the fixed, trusted paper sources. Add new sources here."""
from __future__ import annotations

from .arxiv import ArxivSource
from .base import RawPaper, Source, SourceError, SourceQuery
from .openalex import OpenAlexSource
from .pubmed import PubMedSource
from .semantic_scholar import SemanticScholarSource

REGISTRY: dict[str, Source] = {s.id: s for s in (ArxivSource(), OpenAlexSource(), SemanticScholarSource(), PubMedSource())}

# Priority when merging duplicate records (lower = preferred for title/abstract).
PRIORITY = {"arxiv": 0, "openalex": 1, "semantic_scholar": 2, "pubmed": 3}

__all__ = ["REGISTRY", "PRIORITY", "RawPaper", "Source", "SourceError", "SourceQuery"]
