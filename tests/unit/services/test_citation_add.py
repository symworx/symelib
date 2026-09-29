"""tests/unit/services/test_citation_add.py"""

from datetime import date, datetime
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from symworx_elibrary.models.metadata import MetadataIssue, MetadataSource, MetadataStatus
from symworx_elibrary.models.reference import Author, Journal, Reference
from symworx_elibrary.services.citation_add import (
    CitationDraft,
    CitationLookupError,
    DuplicateCitationError,
    add_citation,
    insert_citation,
)
from symworx_elibrary.services.db_manager import DatabaseManager
from symworx_elibrary.services.metadata_enricher import EnrichmentResult
from symworx_elibrary.utils.citation import has_local_pdf, is_citation_path


@pytest.fixture
def db(tmp_path: Path) -> DatabaseManager:
    return DatabaseManager(tmp_path / "test.db")


def _ref(**kw) -> Reference:
    base = dict(
        pmid="",
        doi="10.1080/10447318.2024.2383033",
        title="Remote HCI Title",
        authors=[Author(last_name="Lee", first_name="Sam", initials="S")],
        journal=Journal(title="Int J Hum Comput Interact"),
        publication_date=date(2024, 7, 1),
        abstract="An abstract from Crossref.",
        keywords=["HCI"],
        mesh_terms=[],
    )
    base.update(kw)
    return Reference(**base)


def test_add_citation_lookup_insert(db: DatabaseManager):
    enricher = MagicMock()
    result = EnrichmentResult(
        reference=_ref(),
        status=MetadataStatus.complete,
        source=MetadataSource.crossref,
        checked_at=datetime.now(),
        issue=MetadataIssue.none,
    )
    enricher.enrich.return_value = result

    meta = add_citation(
        db,
        CitationDraft(
            identifier="https://www.tandfonline.com/doi/full/10.1080/10447318.2024.2383033"
        ),
        enricher=enricher,
    )
    assert meta.id is not None
    assert meta.title == "Remote HCI Title"
    assert meta.doi == "10.1080/10447318.2024.2383033"
    assert meta.metadata_source == MetadataSource.crossref
    assert is_citation_path(meta.file_path)
    assert meta.file_size == 0
    assert not has_local_pdf(meta.file_path)
    assert not meta.filename.endswith(".pdf")
    enricher.enrich.assert_called_once()


def test_add_citation_manual_insert(db: DatabaseManager):
    meta = add_citation(
        db,
        CitationDraft(
            title="Hand-entered paper",
            authors=[Author(last_name="Curie", first_name="Marie")],
            year=1898,
            journal="Nature",
        ),
    )
    assert meta.title == "Hand-entered paper"
    assert meta.publication_year == 1898
    assert meta.journal == "Nature"
    assert meta.doi == ""
    assert meta.metadata_source == MetadataSource.manual
    assert is_citation_path(meta.file_path)
    assert "local:" in meta.file_path


def test_add_citation_two_manuals_unique_paths(db: DatabaseManager):
    a = add_citation(db, CitationDraft(title="One", authors=[Author(last_name="A")]))
    b = add_citation(db, CitationDraft(title="Two", authors=[Author(last_name="B")]))
    assert a.file_path != b.file_path
    assert a.id != b.id


def test_add_citation_duplicate_doi(db: DatabaseManager):
    enricher = MagicMock()
    enricher.enrich.return_value = EnrichmentResult(
        reference=_ref(),
        status=MetadataStatus.partial,
        source=MetadataSource.crossref,
        checked_at=datetime.now(),
        issue=MetadataIssue.none,
    )
    first = add_citation(db, CitationDraft(doi="10.1080/10447318.2024.2383033"), enricher=enricher)
    with pytest.raises(DuplicateCitationError) as exc:
        add_citation(db, CitationDraft(doi="10.1080/10447318.2024.2383033"), enricher=enricher)
    assert exc.value.existing.id == first.id


def test_add_citation_lookup_miss_without_title(db: DatabaseManager):
    enricher = MagicMock()
    enricher.enrich.return_value = EnrichmentResult(
        reference=_ref(title="Untitled document", authors=[], doi="10.1234/missing"),
        status=MetadataStatus.fallback,
        source=MetadataSource.local,
        checked_at=datetime.now(),
        issue=MetadataIssue.crossref_miss,
    )
    with pytest.raises(CitationLookupError, match="not found"):
        add_citation(db, CitationDraft(doi="10.1234/missing"), enricher=enricher)


def test_add_citation_lookup_miss_with_title(db: DatabaseManager):
    enricher = MagicMock()
    enricher.enrich.return_value = EnrichmentResult(
        reference=_ref(title="My title", authors=[], doi="10.1234/missing"),
        status=MetadataStatus.fallback,
        source=MetadataSource.local,
        checked_at=datetime.now(),
        issue=MetadataIssue.crossref_miss,
    )
    meta = add_citation(
        db,
        CitationDraft(doi="10.1234/missing", title="My title", authors=[Author(last_name="X")]),
        enricher=enricher,
    )
    assert meta.title == "My title"
    assert meta.metadata_source == MetadataSource.manual
    assert meta.doi == "10.1234/missing"


def test_add_citation_requires_something(db: DatabaseManager):
    with pytest.raises(ValueError, match="DOI, URL, PMID, or title"):
        add_citation(db, CitationDraft())


def test_insert_citation_duplicate(db: DatabaseManager):
    ref = _ref()
    insert_citation(db, ref, metadata_source=MetadataSource.crossref)
    with pytest.raises(DuplicateCitationError):
        insert_citation(db, ref, metadata_source=MetadataSource.manual)


def test_add_citation_title_override_marks_manual(db: DatabaseManager):
    enricher = MagicMock()
    enricher.enrich.return_value = EnrichmentResult(
        reference=_ref(),
        status=MetadataStatus.complete,
        source=MetadataSource.crossref,
        checked_at=datetime.now(),
        issue=MetadataIssue.none,
    )
    meta = add_citation(
        db,
        CitationDraft(
            doi="10.1080/10447318.2024.2383033",
            title="User-corrected title",
        ),
        enricher=enricher,
    )
    assert meta.title == "User-corrected title"
    assert meta.metadata_source == MetadataSource.manual
    assert meta.abstract == "An abstract from Crossref."
