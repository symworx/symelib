"""Add a citation-only library record (DOI/URL lookup or manual entry)."""

from __future__ import annotations

from datetime import date
from typing import TYPE_CHECKING

from textual import work
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import Input, Label, Static

from symworx_elibrary.models.metadata import MetadataIssue, MetadataSource
from symworx_elibrary.models.reference import Journal, Reference
from symworx_elibrary.services.citation_add import (
    DuplicateCitationError,
    insert_citation,
    lookup_citation,
)
from symworx_elibrary.utils.authors import (
    format_authors_editable,
    parse_authors_editable,
    validate_publication_year,
)
from symworx_elibrary.utils.citation import parse_article_identifier

if TYPE_CHECKING:
    from symworx_elibrary.tui.app import ElibApp


class AddCitationModal(ModalScreen[int | None]):
    """Lookup by DOI/URL/PMID or enter a citation by hand. Returns new document id."""

    BINDINGS = [
        Binding("escape", "cancel", "Cancel", show=True),
    ]

    def __init__(self) -> None:
        super().__init__()
        self._abstract: str | None = None
        self._lookup_source: MetadataSource | None = None
        self._lookup_issue: MetadataIssue | None = None
        self._lookup_detail: str | None = None
        self._snapshot: tuple[str, str, str, str] | None = None

    @property
    def app(self) -> ElibApp:  # type: ignore[override]
        return super().app  # type: ignore[return-value]

    def compose(self) -> ComposeResult:
        with Vertical(id="add-cite-dialog"):
            yield Label("Add citation", id="dialog-title")
            yield Input(placeholder="DOI, URL, or PMID (enter to look up)", id="add-ident-input")
            yield Input(placeholder="Title", id="add-title-input")
            yield Input(placeholder="Last, First; Last2, First2", id="add-authors-input")
            yield Input(placeholder="Year (YYYY)", id="add-year-input")
            yield Input(placeholder="Journal", id="add-journal-input")
            yield Static(
                "enter on DOI looks up  ·  enter on other fields saves  ·  esc cancel",
                id="dialog-help",
            )

    def on_mount(self) -> None:
        self.query_one("#add-ident-input", Input).focus()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        if event.input.id == "add-ident-input":
            self._start_lookup()
            return
        if event.input.id in (
            "add-title-input",
            "add-authors-input",
            "add-year-input",
            "add-journal-input",
        ):
            self._save()

    def _start_lookup(self) -> None:
        raw = self.query_one("#add-ident-input", Input).value.strip()
        if not raw:
            self.notify("Enter a DOI, URL, or PMID — or fill the form below", severity="warning")
            return
        ident = parse_article_identifier(raw)
        if not ident.has_id():
            self.notify("Could not parse a DOI or PMID from that text", severity="warning")
            return
        if ident.doi:
            existing = self.app.db.get_by_doi(ident.doi)
            if existing is not None:
                self.notify(
                    f"Already in library [{existing.id}] {(existing.title or '')[:60]}",
                    severity="warning",
                    timeout=6,
                )
                return
        self.notify("Looking up…", timeout=2)
        self._lookup_worker(ident.doi, ident.pmid)

    @work(thread=True, exclusive=True)
    def _lookup_worker(self, doi: str | None, pmid: str | None) -> None:
        try:
            enricher = self.app.make_enricher()
            result = lookup_citation(enricher, doi=doi, pmid=pmid)
        except Exception as e:
            self.app.call_from_thread(self._on_lookup_error, str(e))
            return
        self.app.call_from_thread(self._on_lookup_done, result)

    def _on_lookup_error(self, message: str) -> None:
        self.notify(message[:180], severity="error")

    def _on_lookup_done(self, result) -> None:
        ref = result.reference
        miss = result.source == MetadataSource.local
        if miss:
            self.notify(
                "Not in PubMed/Crossref — fill the form manually",
                severity="warning",
                timeout=6,
            )
            if ref.doi:
                # Keep the DOI in the identifier box for save.
                ident_inp = self.query_one("#add-ident-input", Input)
                if not ident_inp.value.strip():
                    ident_inp.value = ref.doi
            return

        title_inp = self.query_one("#add-title-input", Input)
        authors_inp = self.query_one("#add-authors-input", Input)
        year_inp = self.query_one("#add-year-input", Input)
        journal_inp = self.query_one("#add-journal-input", Input)
        title_inp.value = ref.title or ""
        authors_inp.value = format_authors_editable(ref.authors)
        year_inp.value = str(ref.publication_date.year) if ref.publication_date else ""
        journal_inp.value = ref.journal.title if ref.journal else ""
        self._abstract = ref.abstract
        self._lookup_source = result.source
        self._lookup_issue = result.issue
        self._lookup_detail = result.detail
        self._snapshot = (
            title_inp.value.strip(),
            authors_inp.value,
            year_inp.value.strip(),
            journal_inp.value.strip(),
        )
        via = result.source.value if result.source else "remote"
        self.notify(f"Populated via {via}", timeout=4)
        title_inp.focus()

    def _save(self) -> None:
        raw_title = self.query_one("#add-title-input", Input).value.strip()
        if not raw_title:
            self.notify("Title is required", severity="warning")
            return
        try:
            authors = parse_authors_editable(self.query_one("#add-authors-input", Input).value)
        except ValueError as e:
            self.notify(str(e), severity="warning")
            return

        raw_year = self.query_one("#add-year-input", Input).value.strip()
        year: int | None = None
        if raw_year:
            if not raw_year.isdigit():
                self.notify("Year must be a 4-digit number (YYYY)", severity="warning")
                return
            try:
                year = validate_publication_year(int(raw_year))
            except ValueError as e:
                self.notify(str(e), severity="warning")
                return

        journal = self.query_one("#add-journal-input", Input).value.strip() or "Unknown"
        ident = parse_article_identifier(self.query_one("#add-ident-input", Input).value)
        doi = ident.doi or ""
        pmid = ident.pmid or ""

        current = (
            raw_title,
            self.query_one("#add-authors-input", Input).value,
            self.query_one("#add-year-input", Input).value.strip(),
            self.query_one("#add-journal-input", Input).value.strip(),
        )
        if self._lookup_source is not None and self._snapshot == current:
            source = self._lookup_source
            issue = self._lookup_issue
            detail = self._lookup_detail
        else:
            source = MetadataSource.manual
            issue = MetadataIssue.none
            detail = "manual citation-only add"

        reference = Reference(
            pmid=pmid,
            doi=doi,
            title=raw_title,
            authors=authors,
            journal=Journal(title=journal),
            publication_date=date(year, 1, 1) if year else None,
            abstract=self._abstract,
            keywords=[],
            mesh_terms=[],
        )
        try:
            meta = insert_citation(
                self.app.db,
                reference,
                metadata_source=source,
                metadata_issue=issue,
                metadata_detail=detail,
            )
        except DuplicateCitationError as e:
            self.notify(str(e), severity="warning", timeout=6)
            return
        except ValueError as e:
            self.notify(str(e), severity="error")
            return

        self.notify(f"Added [{meta.id}] {meta.title[:50]}", timeout=4)
        self.dismiss(meta.id)

    def action_cancel(self) -> None:
        self.dismiss(None)
