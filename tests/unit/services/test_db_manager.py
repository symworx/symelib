"""
tests/unit/services/test_db_manager.py
"""

from datetime import date
import json
from pathlib import Path

import pytest

from symworx_elibrary.models.metadata import (
    MetadataSource,
    MetadataStatus,
    SearchField,
    SearchQuery,
    SortBy,
)
from symworx_elibrary.models.reference import Author, Journal, Reference
from symworx_elibrary.services.db_manager import DatabaseManager


@pytest.fixture
def db(tmp_path: Path) -> DatabaseManager:
    return DatabaseManager(tmp_path / "test.db")


def _ref(**overrides) -> Reference:
    data = dict(
        pmid="12345678",
        doi="10.1234/test.doi",
        title="A Test Paper About CRISPR",
        authors=[Author(last_name="Doe", first_name="Jane", initials="J")],
        journal=Journal(title="Nature Methods"),
        publication_date=date(2020, 6, 1),
        abstract="This is the abstract.",
        keywords=["CRISPR"],
        mesh_terms=["Gene Editing"],
    )
    data.update(overrides)
    return Reference(**data)


def test_add_and_get_by_doi(db: DatabaseManager, tmp_path: Path):
    pdf = tmp_path / "paper.pdf"
    pdf.write_bytes(b"%PDF-1.4")
    doc_id = db.add_document(
        _ref(),
        file_path=pdf,
        filename=pdf.name,
        file_size=8,
        metadata_status=MetadataStatus.complete,
        metadata_source=MetadataSource.pubmed,
    )
    assert doc_id is not None

    meta = db.get_by_doi("10.1234/test.doi")
    assert meta is not None
    assert meta.id == doc_id
    assert meta.title.startswith("A Test Paper")
    assert meta.metadata_status == MetadataStatus.complete
    assert meta.metadata_source == MetadataSource.pubmed
    assert meta.abstract == "This is the abstract."

    by_id = db.get_by_id(doc_id)
    assert by_id is not None
    assert by_id.doi == "10.1234/test.doi"


def test_add_strips_synthetic_doi(db: DatabaseManager, tmp_path: Path):
    pdf = tmp_path / "local.pdf"
    pdf.write_bytes(b"%PDF")
    doc_id = db.add_document(
        _ref(doi="10.9999/elib-local-1", pmid="LOCAL-99", title="Local Doc"),
        file_path=pdf,
        filename=pdf.name,
        file_size=4,
        metadata_status=MetadataStatus.fallback,
        metadata_source=MetadataSource.local,
    )
    meta = db.get_by_id(doc_id)
    assert meta is not None
    assert meta.doi == ""
    assert meta.pmid is None
    assert meta.metadata_status == MetadataStatus.fallback
    assert db.get_by_doi("10.9999/elib-local-1") is None


def test_update_document_fields_authors_and_year(db: DatabaseManager, tmp_path: Path):
    pdf = tmp_path / "paper.pdf"
    pdf.write_bytes(b"%PDF")
    doc_id = db.add_document(
        _ref(),
        file_path=pdf,
        filename=pdf.name,
        file_size=4,
        metadata_status=MetadataStatus.complete,
        metadata_source=MetadataSource.pubmed,
    )
    updated = db.update_document_fields(
        doc_id,
        authors=[Author(last_name="Curie", first_name="Marie", initials="M")],
        publication_year=1898,
    )
    assert updated is not None
    assert updated.publication_year == 1898
    assert json.loads(updated.authors_json)[0]["last_name"] == "Curie"
    assert updated.metadata_source == MetadataSource.manual

    hits = db.search(SearchQuery(text="Curie", search_field=SearchField.author))
    assert len(hits) == 1
    assert hits[0].metadata.id == doc_id

    cleared = db.update_document_fields(doc_id, clear_year=True)
    assert cleared is not None
    assert cleared.publication_year is None
    assert json.loads(cleared.authors_json)[0]["last_name"] == "Curie"


def test_update_document_fields_title(db: DatabaseManager, tmp_path: Path):
    pdf = tmp_path / "paper.pdf"
    pdf.write_bytes(b"%PDF")
    doc_id = db.add_document(_ref(), file_path=pdf, filename=pdf.name, file_size=4)
    updated = db.update_document_fields(doc_id, title="  Corrected Title  ")
    assert updated is not None
    assert updated.title == "Corrected Title"
    assert updated.metadata_source == MetadataSource.manual
    hits = db.search(SearchQuery(text="Corrected", search_field=SearchField.title))
    assert len(hits) == 1
    assert hits[0].metadata.id == doc_id


def test_update_document_fields_rejects_blank_title(db: DatabaseManager, tmp_path: Path):
    pdf = tmp_path / "paper.pdf"
    pdf.write_bytes(b"%PDF")
    doc_id = db.add_document(_ref(), file_path=pdf, filename=pdf.name, file_size=4)
    with pytest.raises(ValueError, match="Title is required"):
        db.update_document_fields(doc_id, title="   ")


def test_update_document_fields_rejects_bad_year(db: DatabaseManager, tmp_path: Path):
    pdf = tmp_path / "paper.pdf"
    pdf.write_bytes(b"%PDF")
    doc_id = db.add_document(_ref(), file_path=pdf, filename=pdf.name, file_size=4)
    with pytest.raises(ValueError, match="Year must be"):
        db.update_document_fields(doc_id, publication_year=99)


def test_update_document_metadata(db: DatabaseManager, tmp_path: Path):
    pdf = tmp_path / "paper.pdf"
    pdf.write_bytes(b"%PDF")
    doc_id = db.add_document(
        _ref(abstract=None, authors=[]),
        file_path=pdf,
        filename=pdf.name,
        file_size=4,
        metadata_status=MetadataStatus.partial,
        metadata_source=MetadataSource.pubmed,
    )
    updated = db.update_document_metadata(
        doc_id,
        _ref(abstract="Now we have an abstract.", title="Updated Title"),
        metadata_status=MetadataStatus.complete,
        metadata_source=MetadataSource.pubmed,
    )
    assert updated is not None
    assert updated.title == "Updated Title"
    assert updated.abstract == "Now we have an abstract."
    assert updated.metadata_status == MetadataStatus.complete


def test_list_by_status_and_counts(db: DatabaseManager, tmp_path: Path):
    for i, (status, source) in enumerate(
        [
            (MetadataStatus.complete, MetadataSource.pubmed),
            (MetadataStatus.partial, MetadataSource.crossref),
            (MetadataStatus.fallback, MetadataSource.local),
            (MetadataStatus.fallback, MetadataSource.local),
        ]
    ):
        pdf = tmp_path / f"p{i}.pdf"
        pdf.write_bytes(b"%PDF")
        doi = f"10.1234/doc.{i}" if status != MetadataStatus.fallback else ""
        pmid = f"{1000 + i}" if status != MetadataStatus.fallback else None
        db.add_document(
            _ref(doi=doi or "10.9999/x", pmid=pmid or "LOCAL-1", title=f"Paper {i}"),
            file_path=pdf,
            filename=pdf.name,
            file_size=4,
            metadata_status=status,
            metadata_source=source,
        )

    counts = db.count_by_status()
    assert counts.get("complete") == 1
    assert counts.get("partial") == 1
    assert counts.get("fallback") == 2

    partials = db.list_by_status(MetadataStatus.partial)
    assert len(partials) == 1
    assert partials[0].metadata_source == MetadataSource.crossref

    multi = db.list_by_status([MetadataStatus.partial, MetadataStatus.fallback])
    assert len(multi) == 3


def test_search_by_status(db: DatabaseManager, tmp_path: Path):
    for i, status in enumerate([MetadataStatus.complete, MetadataStatus.fallback]):
        pdf = tmp_path / f"s{i}.pdf"
        pdf.write_bytes(b"%PDF")
        db.add_document(
            _ref(
                doi=f"10.1/s{i}" if status == MetadataStatus.complete else "10.9999/z",
                pmid=str(i) if status == MetadataStatus.complete else "LOCAL-0",
                title=f"Searchable {status.value}",
            ),
            file_path=pdf,
            filename=pdf.name,
            file_size=4,
            metadata_status=status,
            metadata_source=MetadataSource.pubmed
            if status == MetadataStatus.complete
            else MetadataSource.local,
        )

    results = db.search(SearchQuery(metadata_status=MetadataStatus.complete))
    assert len(results) == 1
    assert results[0].metadata.metadata_status == MetadataStatus.complete


def test_search_prefix_matches_longer_word(db: DatabaseManager, tmp_path: Path):
    """cardio should match cardiovascular (prefix FTS, not exact phrase)."""
    from symworx_elibrary.models.metadata import SearchField

    pdf = tmp_path / "cv.pdf"
    pdf.write_bytes(b"%PDF")
    db.add_document(
        _ref(
            doi="10.1/cv",
            pmid="999",
            title="Cardiovascular risk in athletes",
            abstract="A study of cardiovascular outcomes.",
        ),
        file_path=pdf,
        filename=pdf.name,
        file_size=4,
        metadata_status=MetadataStatus.complete,
        metadata_source=MetadataSource.pubmed,
    )

    hits = db.search(SearchQuery(text="cardio", search_field=SearchField.all))
    assert len(hits) == 1
    assert "Cardiovascular" in hits[0].metadata.title

    title_hits = db.search(SearchQuery(text="cardio", search_field=SearchField.title))
    assert len(title_hits) == 1

    author_hits = db.search(SearchQuery(text="Doe", search_field=SearchField.author))
    assert len(author_hits) == 1


def test_backfill_from_legacy_shape(tmp_path: Path):
    """Simulate a pre-migration DB row and ensure backfill classifies it."""
    import sqlite3

    db_path = tmp_path / "legacy.db"
    conn = sqlite3.connect(db_path)
    conn.execute("""
        CREATE TABLE documents (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            file_path TEXT UNIQUE NOT NULL,
            filename TEXT NOT NULL,
            doi TEXT NOT NULL,
            pmid TEXT,
            title TEXT NOT NULL,
            authors_json TEXT NOT NULL,
            journal TEXT NOT NULL,
            publication_year INTEGER,
            abstract TEXT,
            keywords_json TEXT DEFAULT '[]',
            file_size INTEGER NOT NULL,
            added_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            last_accessed TIMESTAMP,
            s3_synced BOOLEAN DEFAULT 0,
            s3_path TEXT
        )
    """)
    conn.execute(
        """
        INSERT INTO documents (
            file_path, filename, doi, pmid, title, authors_json,
            journal, publication_year, abstract, keywords_json, file_size
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            "/tmp/a.pdf",
            "a.pdf",
            "10.9999/elib-local-1",
            "LOCAL-99",
            "Filename Stem Title",
            "[]",
            "Local / Non-PubMed source",
            None,
            "preview text",
            "[]",
            100,
        ),
    )
    conn.execute(
        """
        INSERT INTO documents (
            file_path, filename, doi, pmid, title, authors_json,
            journal, publication_year, abstract, keywords_json, file_size
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            "/tmp/b.pdf",
            "b.pdf",
            "10.1038/s41586-020-2649-2",
            "32848250",
            "A Real Paper",
            '[{"last_name": "Smith"}]',
            "Nature",
            2020,
            "A full abstract here.",
            '["gene"]',
            200,
        ),
    )
    conn.commit()
    conn.close()

    db = DatabaseManager(db_path)
    # Migration + backfill happen in __init__
    counts = db.count_by_status()
    assert counts.get("fallback") == 1
    assert counts.get("complete") == 1

    local = db.list_by_status(MetadataStatus.fallback)[0]
    assert local.doi == ""  # synthetic cleared
    assert local.pmid is None
    assert local.metadata_source == MetadataSource.local

    complete = db.list_by_status(MetadataStatus.complete)[0]
    assert complete.doi.startswith("10.1038")
    assert complete.metadata_source == MetadataSource.pubmed


def test_unique_doi_constraint(db: DatabaseManager, tmp_path: Path):
    pdf1 = tmp_path / "1.pdf"
    pdf2 = tmp_path / "2.pdf"
    pdf1.write_bytes(b"%PDF")
    pdf2.write_bytes(b"%PDF")
    db.add_document(_ref(), file_path=pdf1, filename="1.pdf", file_size=4)
    with pytest.raises(Exception):
        db.add_document(_ref(), file_path=pdf2, filename="2.pdf", file_size=4)


def _set_added_date(db: DatabaseManager, doc_id: int, when: str) -> None:
    with db.get_connection() as conn:
        conn.execute("UPDATE documents SET added_date = ? WHERE id = ?", (when, doc_id))
        conn.commit()


def test_filter_by_added_date(db: DatabaseManager, tmp_path: Path):
    ids = []
    for i, stamp in enumerate(
        ("2026-01-15 12:00:00", "2026-08-20 09:00:00", "2026-08-28 18:00:00")
    ):
        pdf = tmp_path / f"added{i}.pdf"
        pdf.write_bytes(b"%PDF")
        doc_id = db.add_document(
            _ref(doi=f"10.1/added.{i}", pmid=str(2000 + i), title=f"Imported {i}"),
            file_path=pdf,
            filename=pdf.name,
            file_size=4,
            metadata_status=MetadataStatus.complete,
            metadata_source=MetadataSource.pubmed,
        )
        _set_added_date(db, doc_id, stamp)
        ids.append(doc_id)

    listed = db.list_documents(added_from=date(2026, 8, 1), added_to=date(2026, 8, 31))
    assert {d.id for d in listed} == {ids[1], ids[2]}

    from_only = db.list_documents(added_from=date(2026, 8, 28))
    assert [d.id for d in from_only] == [ids[2]]

    to_only = db.list_documents(added_to=date(2026, 1, 15))
    assert [d.id for d in to_only] == [ids[0]]

    hits = db.search(
        SearchQuery(
            added_from=date(2026, 8, 20),
            added_to=date(2026, 8, 20),
            sort_by=SortBy.added_date,
        )
    )
    assert [r.metadata.id for r in hits] == [ids[1]]

    none = db.list_documents(added_from=date(2025, 1, 1), added_to=date(2025, 12, 31))
    assert none == []


def test_multiple_empty_dois_allowed(db: DatabaseManager, tmp_path: Path):
    for i in range(2):
        pdf = tmp_path / f"e{i}.pdf"
        pdf.write_bytes(b"%PDF")
        db.add_document(
            _ref(doi="10.9999/x", pmid="LOCAL-1", title=f"Empty {i}"),
            file_path=pdf,
            filename=pdf.name,
            file_size=4,
            metadata_status=MetadataStatus.fallback,
            metadata_source=MetadataSource.local,
        )
    assert db.count_documents() == 2
