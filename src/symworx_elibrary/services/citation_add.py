"""Add citation-only library rows (DOI/URL lookup or manual entry)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
import json
from pathlib import Path

from symworx_elibrary.models.metadata import (
    DocumentMetadata,
    MetadataIssue,
    MetadataSource,
    MetadataStatus,
    classify_metadata_status,
    is_synthetic_doi,
    is_synthetic_pmid,
)
from symworx_elibrary.models.reference import Author, Journal, Reference
from symworx_elibrary.services.db_manager import DatabaseManager
from symworx_elibrary.services.metadata_enricher import EnrichmentResult, MetadataEnricher
from symworx_elibrary.utils.citation import citation_file_path, parse_article_identifier
from symworx_elibrary.utils.doi_parser import normalize_doi
from symworx_elibrary.utils.logging import LoggerConfig, get_shared_logger

logger = get_shared_logger(LoggerConfig(name="citation_add"))

_MISS_TITLES = frozenset({"", "untitled document", "no title"})


class DuplicateCitationError(ValueError):
    """A library row already owns this DOI."""

    def __init__(self, existing: DocumentMetadata):
        self.existing = existing
        title = (existing.title or "")[:80]
        super().__init__(f"Already in library [{existing.id}] {title}")


class CitationLookupError(ValueError):
    """Remote lookup missed and no manual title was provided."""


@dataclass
class CitationDraft:
    """Fields for adding a citation-only record."""

    identifier: str | None = None
    title: str | None = None
    authors: list[Author] | None = None
    year: int | None = None
    journal: str | None = None
    doi: str | None = None
    pmid: str | None = None
    abstract: str | None = None


def lookup_citation(
    enricher: MetadataEnricher,
    *,
    doi: str | None = None,
    pmid: str | None = None,
    fallback_title: str | None = None,
) -> EnrichmentResult:
    """PubMed → Crossref lookup. Does not write to the database."""
    return enricher.enrich(doi=doi, pmid=pmid, fallback_title=fallback_title)


def insert_citation(
    db: DatabaseManager,
    reference: Reference,
    *,
    metadata_source: MetadataSource,
    metadata_status: MetadataStatus | None = None,
    metadata_issue: MetadataIssue | None = None,
    metadata_detail: str | None = None,
) -> DocumentMetadata:
    """Insert a citation-only row. Raises DuplicateCitationError on DOI clash."""
    doi = reference.doi or ""
    if doi and not is_synthetic_doi(doi):
        existing = db.get_by_doi(doi)
        if existing is not None:
            raise DuplicateCitationError(existing)

    filename = reference.generate_filename()
    if filename.lower().endswith(".pdf"):
        filename = filename[:-4]
    path = citation_file_path(doi if doi and not is_synthetic_doi(doi) else None)

    doc_id = db.add_document(
        reference,
        file_path=Path(path),
        filename=filename,
        file_size=0,
        metadata_status=metadata_status,
        metadata_source=metadata_source,
        metadata_issue=metadata_issue,
        metadata_detail=metadata_detail,
        text_extract_chars=0,
    )
    meta = db.get_by_id(doc_id)
    if meta is None:
        raise RuntimeError("Citation insert failed")
    logger.info(
        "Citation-only record added",
        doc_id=meta.id,
        doi=meta.doi or None,
        source=metadata_source.value,
    )
    return meta


def add_citation(
    db: DatabaseManager,
    draft: CitationDraft,
    *,
    enricher: MetadataEnricher | None = None,
) -> DocumentMetadata:
    """Lookup (optional) + overlay manual fields + insert a citation-only row."""
    parsed = parse_article_identifier(draft.identifier)
    doi = normalize_doi(draft.doi) if draft.doi else None
    doi = doi or parsed.doi
    pmid = (draft.pmid or "").strip() or parsed.pmid
    if pmid and is_synthetic_pmid(pmid):
        pmid = None

    title = (draft.title or "").strip() or None
    journal = (draft.journal or "").strip() or None

    if not (doi or pmid or title):
        raise ValueError("Provide a DOI, URL, PMID, or title")

    if doi:
        existing = db.get_by_doi(doi)
        if existing is not None:
            raise DuplicateCitationError(existing)

    result: EnrichmentResult | None = None
    if doi or pmid:
        if enricher is None:
            raise ValueError("Metadata enricher required to look up a DOI or PMID")
        result = lookup_citation(enricher, doi=doi, pmid=pmid, fallback_title=title)
        if _is_lookup_miss(result) and not title:
            ident = doi or pmid or (draft.identifier or "")
            raise CitationLookupError(
                f"{ident} not found in PubMed or Crossref; pass --title or fill the form"
            )
        reference = result.reference
        source = MetadataSource.manual if _is_lookup_miss(result) else result.source
        issue = result.issue
        detail = result.detail
    else:
        reference = _manual_reference(
            title=title or "Untitled document",
            authors=draft.authors or [],
            year=draft.year,
            journal=journal or "Unknown",
            doi=doi or "",
            pmid=pmid or "",
            abstract=draft.abstract,
        )
        source = MetadataSource.manual
        issue = MetadataIssue.none
        detail = "manual citation-only add"

    reference, changed = _overlay(reference, draft, doi=doi, pmid=pmid)
    if changed and source != MetadataSource.manual:
        source = MetadataSource.manual

    authors_json = _authors_json(reference.authors)
    status = classify_metadata_status(
        doi=reference.doi,
        pmid=reference.pmid or None,
        title=reference.title,
        authors_json=authors_json,
        abstract=reference.abstract,
    )
    if issue is None:
        issue = (
            MetadataIssue.none
            if status in (MetadataStatus.complete, MetadataStatus.partial)
            else MetadataIssue.unknown
        )

    return insert_citation(
        db,
        reference,
        metadata_source=source,
        metadata_status=status,
        metadata_issue=issue,
        metadata_detail=detail,
    )


def _is_lookup_miss(result: EnrichmentResult) -> bool:
    if result.source not in (MetadataSource.local,):
        return False
    title = (result.reference.title or "").strip().lower()
    return title in _MISS_TITLES or result.issue not in (MetadataIssue.none,)


def _overlay(
    reference: Reference,
    draft: CitationDraft,
    *,
    doi: str | None,
    pmid: str | None,
) -> tuple[Reference, bool]:
    """Apply user-supplied fields. Returns (ref, changed_bibliographic)."""
    updates: dict = {}
    changed = False

    title = (draft.title or "").strip()
    if title and title != reference.title:
        updates["title"] = title
        changed = True

    if draft.authors is not None:
        updates["authors"] = draft.authors
        changed = True

    if draft.year is not None:
        current_year = reference.publication_date.year if reference.publication_date else None
        if draft.year != current_year:
            updates["publication_date"] = date(draft.year, 1, 1)
            changed = True

    journal = (draft.journal or "").strip()
    if journal and journal != reference.journal.title:
        updates["journal"] = Journal(
            title=journal,
            abbreviation=reference.journal.abbreviation,
            issn=reference.journal.issn,
            volume=reference.journal.volume,
            issue=reference.journal.issue,
        )
        changed = True

    if doi and doi != (reference.doi or ""):
        updates["doi"] = doi

    if pmid and pmid != (reference.pmid or ""):
        updates["pmid"] = pmid

    abstract = (draft.abstract or "").strip() if draft.abstract else None
    if abstract and not (reference.abstract or "").strip():
        updates["abstract"] = abstract

    if not updates:
        return reference, False
    return reference.model_copy(update=updates), changed


def _manual_reference(
    *,
    title: str,
    authors: list[Author],
    year: int | None,
    journal: str,
    doi: str,
    pmid: str,
    abstract: str | None,
) -> Reference:
    return Reference(
        pmid=pmid or "",
        doi=doi or "",
        title=title,
        authors=authors,
        journal=Journal(title=journal or "Unknown"),
        publication_date=date(year, 1, 1) if year else None,
        abstract=abstract,
        keywords=[],
        mesh_terms=[],
    )


def _authors_json(authors: list[Author]) -> str:
    return json.dumps([a.model_dump() for a in authors])
