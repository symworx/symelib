"""Citation-only library records (no PDF on disk).

``documents.file_path`` is UNIQUE NOT NULL, so metadata-only rows use a
sentinel that is not a filesystem path:

    elib:citation:{doi-with-slash-as-::}
    elib:citation:local:{uuid}
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

from symworx_elibrary.utils.doi_parser import (
    extract_doi_from_text,
    extract_pmid_from_text,
    normalize_doi,
)

CITATION_PATH_PREFIX = "elib:citation:"
NO_PDF_MESSAGE = "Citation only — no PDF on disk"

# DOI slash would split Path() on POSIX; keep a single path segment.
_DOI_SLASH = "/"
_DOI_SLASH_SAFE = "::"


@dataclass(frozen=True)
class ArticleIdentifier:
    """DOI and/or PMID parsed from a DOI, publisher URL, or PMID string."""

    doi: str | None = None
    pmid: str | None = None
    raw: str = ""

    def has_id(self) -> bool:
        return bool(self.doi or self.pmid)


def is_citation_path(path: str | Path | None) -> bool:
    """True when ``path`` is a citation-only sentinel, not a real file."""
    if path is None:
        return False
    return str(path).startswith(CITATION_PATH_PREFIX)


def citation_file_path(doi: str | None = None) -> str:
    """Unique sentinel ``file_path`` for a citation-only row."""
    normalized = normalize_doi(doi) if doi else None
    if normalized:
        safe = normalized.replace(_DOI_SLASH, _DOI_SLASH_SAFE)
        return f"{CITATION_PATH_PREFIX}{safe}"
    return f"{CITATION_PATH_PREFIX}local:{uuid4()}"


def has_local_pdf(file_path: str | Path | None) -> bool:
    """True when the record points at an existing PDF file."""
    if file_path is None:
        return False
    if is_citation_path(file_path):
        return False
    return Path(file_path).is_file()


def parse_article_identifier(text: str | None) -> ArticleIdentifier:
    """Parse a DOI, doi.org/publisher URL, or PMID from free text.

    Bare 5-9 digit strings are treated as PMIDs. Publisher URLs such as
    ``https://www.tandfonline.com/doi/full/10.1080/…`` yield the DOI body.
    """
    raw = (text or "").strip()
    if not raw:
        return ArticleIdentifier()

    doi = normalize_doi(raw) or extract_doi_from_text(raw)
    pmid: str | None = None
    if raw.isdigit() and 5 <= len(raw) <= 9:
        pmid = raw
    else:
        pmid = extract_pmid_from_text(raw)

    return ArticleIdentifier(doi=doi, pmid=pmid, raw=raw)
