"""
SQLite persistence for elib (split package).
"""

from __future__ import annotations

from datetime import date, datetime
import json
from pathlib import Path
import sqlite3

from symworx_elibrary.models.metadata import (
    DocumentMetadata,
    MetadataIssue,
    MetadataSource,
    MetadataStatus,
    SearchField,
    SearchQuery,
    SearchResult,
    SortBy,
    SortOrder,
    added_date_sql_filter,
    classify_metadata_status,
    is_synthetic_doi,
    is_synthetic_pmid,
    sort_sql_clause,
)
from symworx_elibrary.models.reference import Author, Reference
from symworx_elibrary.utils.authors import validate_publication_year
from symworx_elibrary.utils.logging import LoggerConfig, get_shared_logger
from symworx_elibrary.utils.search_query import build_fts_match

logger = get_shared_logger(LoggerConfig(name="db_manager"))

_DOCUMENTS_EXTRA_COLUMNS: list[tuple[str, str]] = [
    ("metadata_status", "TEXT NOT NULL DEFAULT 'pending'"),
    ("metadata_source", "TEXT"),
    ("metadata_checked_at", "TIMESTAMP"),
    ("metadata_issue", "TEXT DEFAULT 'unknown'"),
    ("metadata_detail", "TEXT"),
    ("text_extract_chars", "INTEGER"),
    ("source_path", "TEXT"),
    ("original_filename", "TEXT"),
]


class DocumentsMixin:
    """Document CRUD, search, diagnostics queries."""

    def add_document(  # noqa: PLR0913
        self,
        reference: Reference,
        file_path: Path,
        filename: str,
        file_size: int,
        *,
        metadata_status: MetadataStatus | None = None,
        metadata_source: MetadataSource | None = None,
        metadata_checked_at: datetime | None = None,
        metadata_issue: MetadataIssue | None = None,
        metadata_detail: str | None = None,
        text_extract_chars: int | None = None,
        source_path: str | None = None,
        original_filename: str | None = None,
    ) -> int:
        """Add document to database"""
        authors_json = json.dumps([a.model_dump() for a in reference.authors])
        keywords_json = json.dumps(reference.keywords + reference.mesh_terms)

        # Normalize identifiers: never store synthetic placeholders as "real" IDs
        doi = reference.doi or ""
        if is_synthetic_doi(doi):
            doi = ""
        pmid = reference.pmid
        if is_synthetic_pmid(pmid):
            pmid = None

        if metadata_status is None:
            metadata_status = classify_metadata_status(
                doi=doi,
                pmid=pmid,
                title=reference.title,
                authors_json=authors_json,
                abstract=reference.abstract,
            )
        if metadata_source is None:
            if doi or pmid:
                metadata_source = MetadataSource.pubmed
            else:
                metadata_source = MetadataSource.local

        if metadata_issue is None:
            metadata_issue = (
                MetadataIssue.none
                if metadata_status in (MetadataStatus.complete, MetadataStatus.partial)
                else MetadataIssue.unknown
            )

        checked_at = metadata_checked_at or datetime.now()

        metadata = DocumentMetadata(
            file_path=str(file_path),
            filename=filename,
            doi=doi,
            pmid=pmid,
            title=reference.title,
            authors_json=authors_json,
            journal=reference.journal.title,
            publication_year=reference.publication_date.year
            if reference.publication_date
            else None,
            abstract=reference.abstract,
            keywords_json=keywords_json,
            file_size=file_size,
            metadata_status=metadata_status,
            metadata_source=metadata_source,
            metadata_checked_at=checked_at,
            metadata_issue=metadata_issue,
            metadata_detail=metadata_detail,
            text_extract_chars=text_extract_chars,
            source_path=source_path,
            original_filename=original_filename,
        )

        with self.get_connection() as conn:
            cursor = conn.execute(
                """
                INSERT INTO documents (
                    file_path, filename, doi, pmid, title, authors_json,
                    journal, publication_year, abstract, keywords_json, file_size,
                    metadata_status, metadata_source, metadata_checked_at,
                    metadata_issue, metadata_detail, text_extract_chars,
                    source_path, original_filename
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
                (
                    metadata.file_path,
                    metadata.filename,
                    metadata.doi,
                    metadata.pmid,
                    metadata.title,
                    metadata.authors_json,
                    metadata.journal,
                    metadata.publication_year,
                    metadata.abstract,
                    metadata.keywords_json,
                    metadata.file_size,
                    metadata.metadata_status.value,
                    metadata.metadata_source.value if metadata.metadata_source else None,
                    metadata.metadata_checked_at.isoformat()
                    if metadata.metadata_checked_at
                    else None,
                    metadata.metadata_issue.value,
                    metadata.metadata_detail,
                    metadata.text_extract_chars,
                    metadata.source_path,
                    metadata.original_filename,
                ),
            )
            conn.commit()
            return cursor.lastrowid

    def update_document_metadata(
        self,
        doc_id: int,
        reference: Reference,
        *,
        metadata_status: MetadataStatus | None = None,
        metadata_source: MetadataSource | None = None,
        metadata_checked_at: datetime | None = None,
        metadata_issue: MetadataIssue | None = None,
        metadata_detail: str | None = None,
        text_extract_chars: int | None = None,
    ) -> DocumentMetadata | None:
        """Update an existing document's bibliographic fields and metadata quality."""
        authors_json = json.dumps([a.model_dump() for a in reference.authors])
        keywords_json = json.dumps(reference.keywords + reference.mesh_terms)

        doi = reference.doi or ""
        if is_synthetic_doi(doi):
            doi = ""
        pmid = reference.pmid
        if is_synthetic_pmid(pmid):
            pmid = None

        if metadata_status is None:
            metadata_status = classify_metadata_status(
                doi=doi,
                pmid=pmid,
                title=reference.title,
                authors_json=authors_json,
                abstract=reference.abstract,
            )
        if metadata_source is None:
            metadata_source = MetadataSource.pubmed if (doi or pmid) else MetadataSource.local

        if metadata_issue is None:
            metadata_issue = (
                MetadataIssue.none
                if metadata_status in (MetadataStatus.complete, MetadataStatus.partial)
                else MetadataIssue.unknown
            )

        checked_at = metadata_checked_at or datetime.now()
        pub_year = reference.publication_date.year if reference.publication_date else None

        params = (
            doi,
            pmid,
            reference.title,
            authors_json,
            reference.journal.title,
            pub_year,
            reference.abstract,
            keywords_json,
            metadata_status.value,
            metadata_source.value,
            checked_at.isoformat(),
            metadata_issue.value,
            metadata_detail,
            text_extract_chars,
            doc_id,
        )
        sql = """
            UPDATE documents SET
                doi = ?,
                pmid = ?,
                title = ?,
                authors_json = ?,
                journal = ?,
                publication_year = ?,
                abstract = ?,
                keywords_json = ?,
                metadata_status = ?,
                metadata_source = ?,
                metadata_checked_at = ?,
                metadata_issue = ?,
                metadata_detail = ?,
                text_extract_chars = COALESCE(?, text_extract_chars)
            WHERE id = ?
        """

        with self.get_connection() as conn:
            try:
                conn.execute(sql, params)
                conn.commit()
            except sqlite3.IntegrityError:
                # Another row already owns this DOI (duplicate import). Keep existing DOI.
                logger.warning(
                    "DOI unique conflict on update; preserving prior DOI",
                    doc_id=doc_id,
                    doi=doi,
                )
                detail2 = (metadata_detail or "") + f" | doi_conflict={doi}"
                conn.execute(
                    """
                    UPDATE documents SET
                        pmid = ?,
                        title = ?,
                        authors_json = ?,
                        journal = ?,
                        publication_year = ?,
                        abstract = ?,
                        keywords_json = ?,
                        metadata_status = ?,
                        metadata_source = ?,
                        metadata_checked_at = ?,
                        metadata_issue = ?,
                        metadata_detail = ?,
                        text_extract_chars = COALESCE(?, text_extract_chars)
                    WHERE id = ?
                    """,
                    (
                        pmid,
                        reference.title,
                        authors_json,
                        reference.journal.title,
                        pub_year,
                        reference.abstract,
                        keywords_json,
                        metadata_status.value,
                        metadata_source.value,
                        checked_at.isoformat(),
                        metadata_issue.value,
                        detail2[:2000],
                        text_extract_chars,
                        doc_id,
                    ),
                )
                conn.commit()

        return self.get_by_id(doc_id)

    def update_document_fields(
        self,
        doc_id: int,
        *,
        authors: list[Author] | None = None,
        publication_year: int | None = None,
        clear_year: bool = False,
        title: str | None = None,
    ) -> DocumentMetadata | None:
        """Patch title, author list, and/or publication year; mark source as manual.

        Omitting a field leaves it unchanged. ``clear_year`` sets publication_year
        to NULL. Does not rename the PDF on disk.
        """
        if authors is None and publication_year is None and not clear_year and title is None:
            return self.get_by_id(doc_id)

        if publication_year is not None and clear_year:
            raise ValueError("Pass publication_year or clear_year, not both")
        if publication_year is not None:
            publication_year = validate_publication_year(publication_year)

        current = self.get_by_id(doc_id)
        if current is None:
            return None

        if title is not None:
            title = title.strip()
            if not title:
                raise ValueError("Title is required")
        else:
            title = current.title

        if authors is not None:
            authors_json = json.dumps([a.model_dump() for a in authors])
        else:
            authors_json = current.authors_json

        if clear_year:
            year: int | None = None
        elif publication_year is not None:
            year = publication_year
        else:
            year = current.publication_year

        status = classify_metadata_status(
            doi=current.doi,
            pmid=current.pmid,
            title=title,
            authors_json=authors_json,
            abstract=current.abstract,
        )
        checked_at = datetime.now()

        with self.get_connection() as conn:
            conn.execute(
                """
                UPDATE documents SET
                    title = ?,
                    authors_json = ?,
                    publication_year = ?,
                    metadata_status = ?,
                    metadata_source = ?,
                    metadata_checked_at = ?
                WHERE id = ?
                """,
                (
                    title,
                    authors_json,
                    year,
                    status.value,
                    MetadataSource.manual.value,
                    checked_at.isoformat(),
                    doc_id,
                ),
            )
            conn.commit()

        logger.info(
            "Manual metadata edit",
            doc_id=doc_id,
            title_changed=title != current.title,
            authors_changed=authors is not None,
            year=year,
        )
        return self.get_by_id(doc_id)

    def get_by_source_path(self, source_path: str) -> DocumentMetadata | None:
        """Lookup by original source/inbox path (for skip-on-reprocess)."""
        if not source_path:
            return None
        with self.get_connection() as conn:
            row = conn.execute(
                "SELECT * FROM documents WHERE source_path = ?",
                (str(source_path),),
            ).fetchone()
            if row:
                return self._row_to_metadata(row)
        return None

    def count_by_issue(self) -> dict[str, int]:
        with self.get_connection() as conn:
            rows = conn.execute(
                """
                SELECT COALESCE(metadata_issue, 'unknown') AS issue, COUNT(*) AS n
                FROM documents
                GROUP BY COALESCE(metadata_issue, 'unknown')
                """
            ).fetchall()
            return {row["issue"]: row["n"] for row in rows}

    def list_by_issue(
        self,
        issue: MetadataIssue | str | list[MetadataIssue | str],
        limit: int | None = None,
    ) -> list[DocumentMetadata]:
        if isinstance(issue, (list, tuple, set)):
            issues = [i.value if isinstance(i, MetadataIssue) else str(i) for i in issue]
        else:
            issues = [issue.value if isinstance(issue, MetadataIssue) else str(issue)]
        placeholders = ", ".join("?" for _ in issues)
        sql = (
            f"SELECT * FROM documents WHERE metadata_issue IN ({placeholders}) "
            "ORDER BY added_date DESC"
        )
        params: list = list(issues)
        if limit is not None:
            sql += " LIMIT ?"
            params.append(limit)
        with self.get_connection() as conn:
            rows = conn.execute(sql, params).fetchall()
            return [self._row_to_metadata(r) for r in rows]

    def get_by_doi(self, doi: str) -> DocumentMetadata | None:
        """Get document metadata by DOI"""
        if not doi or is_synthetic_doi(doi):
            return None
        with self.get_connection() as conn:
            row = conn.execute("SELECT * FROM documents WHERE doi = ?", (doi,)).fetchone()
            if row:
                return self._row_to_metadata(row)
        return None

    def get_by_id(self, doc_id: int) -> DocumentMetadata | None:
        """Get document metadata by primary key."""
        with self.get_connection() as conn:
            row = conn.execute("SELECT * FROM documents WHERE id = ?", (doc_id,)).fetchone()
            if row:
                return self._row_to_metadata(row)
        return None

    def list_documents(
        self,
        limit: int | None = None,
        *,
        sort_by: SortBy = SortBy.added_date,
        sort_order: SortOrder = SortOrder.desc,
        added_from: date | None = None,
        added_to: date | None = None,
    ) -> list[DocumentMetadata]:
        """Return documents with optional sort and import-date filter.

        Default sort is most recently added first. ``added_from`` / ``added_to``
        are inclusive calendar days on ``documents.added_date``.
        """
        # Alias table as d for shared sort_sql_clause / added_date_sql_filter
        sql = "SELECT d.* FROM documents d WHERE 1=1"
        params: list = []
        clause, extra = added_date_sql_filter(added_from, added_to)
        sql += clause
        params.extend(extra)
        sql += sort_sql_clause(sort_by, sort_order, use_fts=False)
        if limit is not None:
            sql += " LIMIT ?"
            params.append(limit)

        with self.get_connection() as conn:
            rows = conn.execute(sql, params).fetchall()
            return [self._row_to_metadata(row) for row in rows]

    def list_by_status(
        self,
        status: MetadataStatus | str | list[MetadataStatus | str],
        limit: int | None = None,
    ) -> list[DocumentMetadata]:
        """Return documents matching one or more metadata_status values."""
        if isinstance(status, (list, tuple, set)):
            statuses = [s.value if isinstance(s, MetadataStatus) else str(s) for s in status]
        else:
            statuses = [status.value if isinstance(status, MetadataStatus) else str(status)]

        placeholders = ", ".join("?" for _ in statuses)
        sql = f"SELECT * FROM documents WHERE metadata_status IN ({placeholders}) ORDER BY added_date DESC"
        params: list = list(statuses)
        if limit is not None:
            sql += " LIMIT ?"
            params.append(limit)

        with self.get_connection() as conn:
            rows = conn.execute(sql, params).fetchall()
            return [self._row_to_metadata(row) for row in rows]

    def count_by_status(self) -> dict[str, int]:
        """Return {status: count} for all metadata_status values present."""
        with self.get_connection() as conn:
            rows = conn.execute(
                """
                SELECT COALESCE(metadata_status, 'pending') AS status, COUNT(*) AS n
                FROM documents
                GROUP BY COALESCE(metadata_status, 'pending')
                """
            ).fetchall()
            return {row["status"]: row["n"] for row in rows}

    def count_documents(self) -> int:
        with self.get_connection() as conn:
            return conn.execute("SELECT COUNT(*) FROM documents").fetchone()[0]

    def count_fts(self) -> int:
        with self.get_connection() as conn:
            try:
                return conn.execute("SELECT COUNT(*) FROM documents_fts").fetchone()[0]
            except sqlite3.Error:
                return 0

    def search(self, query: SearchQuery) -> list[SearchResult]:
        """Search documents with filters and FTS ranking.

        Free-text uses prefix FTS by default (``cardio`` → ``cardiovascular``).
        ``search_field`` scopes to title / keywords / author / abstract / all.
        """

        params: list = []
        field = query.search_field or SearchField.all
        use_fts = False
        fts_query: str | None = None

        if query.text and field == SearchField.author:
            # Author isolation: substring match on authors_json (not FTS)
            sql = """
                SELECT d.*,
                    0.0 AS relevance
                FROM documents d
                WHERE d.authors_json LIKE ?
            """
            params.append(f"%{query.text.strip()}%")
        elif query.text:
            fts_query = build_fts_match(query.text, field)
            if fts_query:
                use_fts = True
                sql = """
                    SELECT d.*,
                        bm25(documents_fts) AS relevance
                    FROM documents d
                    JOIN documents_fts ON documents_fts.rowid = d.id
                    WHERE documents_fts MATCH ?
                """
                params.append(fts_query)
                logger.debug(
                    "FTS query prepared",
                    original=query.text,
                    field=field.value,
                    match=fts_query,
                )
            else:
                sql = """
                    SELECT d.*,
                        0.0 AS relevance
                    FROM documents d
                    WHERE 1=1
                """
        else:
            # No text search - just filter on metadata
            sql = """
                SELECT d.*,
                    0.0 AS relevance
                FROM documents d
                WHERE 1=1
            """

        # Author filter (additional to free-text)
        if query.author:
            sql += " AND d.authors_json LIKE ?"
            params.append(f"%{query.author}%")

        # Year range filters
        if query.year_from:
            sql += " AND d.publication_year >= ?"
            params.append(query.year_from)

        if query.year_to:
            sql += " AND d.publication_year <= ?"
            params.append(query.year_to)

        # Journal filter
        if query.journal:
            sql += " AND d.journal LIKE ?"
            params.append(f"%{query.journal}%")

        # DOI exact match
        if query.doi:
            sql += " AND d.doi = ?"
            params.append(query.doi)

        # PMID exact match
        if query.pmid:
            sql += " AND d.pmid = ?"
            params.append(query.pmid)

        # Metadata status filter
        if query.metadata_status:
            sql += " AND d.metadata_status = ?"
            params.append(
                query.metadata_status.value
                if isinstance(query.metadata_status, MetadataStatus)
                else query.metadata_status
            )

        # Keyword filters (all must match)
        for kw in query.keywords:
            sql += " AND d.keywords_json LIKE ?"
            params.append(f"%{kw}%")

        # Import-date range (inclusive calendar days on documents.added_date)
        added_clause, added_params = added_date_sql_filter(query.added_from, query.added_to)
        sql += added_clause
        params.extend(added_params)

        # Sorting (enum-driven only)
        sort_by = query.sort_by or SortBy.added_date
        sort_order = query.sort_order or SortOrder.desc
        if sort_by == SortBy.relevance and not use_fts:
            # No FTS rank available — fall back to added_date
            sort_by = SortBy.added_date
        sql += sort_sql_clause(sort_by, sort_order, use_fts=use_fts)

        # Pagination
        sql += " LIMIT ? OFFSET ?"
        params.extend([query.limit, query.offset])

        logger.debug("Executing search query", sql_preview=sql[:300], param_count=len(params))

        # Execute query and build results
        results = []
        try:
            with self.get_connection() as conn:
                rows = conn.execute(sql, params).fetchall()

                for row in rows:
                    meta = self._row_to_metadata(row)
                    # Note: BM25 returns negative scores (lower = more relevant)
                    # Convert to positive for display
                    relevance = abs(row["relevance"]) if row["relevance"] else 0.0
                    results.append(SearchResult(metadata=meta, relevance_score=relevance))

            logger.info(
                "Search completed successfully", result_count=len(results), query_text=query.text
            )

        except Exception as e:
            logger.error(
                "Search query failed",
                error=str(e),
                error_type=type(e).__name__,
                sql_preview=sql[:200],
            )
            raise

        return results

    # ------------------------------------------------------------------
    # Named paper lists
    # ------------------------------------------------------------------
