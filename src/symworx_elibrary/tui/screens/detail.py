"""
Document detail screen: metadata + abstract + open PDF.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical, VerticalScroll
from textual.screen import ModalScreen, Screen
from textual.widgets import Input, Label, Static

from symworx_elibrary.tui.keys import (
    ALT_ADD_TO_LIST,
    EDIT,
    EDIT_ALT,
    OPEN_PDF,
    QUIT_SCREEN,
    VIM_MOTION,
    VimMotionMixin,
)
from symworx_elibrary.utils.authors import (
    format_authors_editable,
    parse_authors_editable,
    validate_publication_year,
)

if TYPE_CHECKING:
    from symworx_elibrary.tui.app import ElibApp


def _escape_markup(text: str) -> str:
    """Escape Rich/Textual markup special characters in free text."""
    return (text or "").replace("[", "\\[").replace("]", "\\]")


class DetailScreen(VimMotionMixin, Screen):
    """Full metadata + abstract for one document."""

    BINDINGS = [
        *VIM_MOTION,
        Binding("escape", "go_back", "Back", show=True),
        *OPEN_PDF,
        *EDIT,
        *EDIT_ALT,
        *ALT_ADD_TO_LIST,
        Binding("enter", "open_pdf", "PDF", show=False),
        *QUIT_SCREEN,
    ]

    def __init__(self, document_id: int) -> None:
        super().__init__()
        self.document_id = document_id
        self._file_path: str | None = None

    @property
    def app(self) -> ElibApp:  # type: ignore[override]
        return super().app  # type: ignore[return-value]

    def compose(self) -> ComposeResult:
        yield Static(
            "[bold]elib[/]  [cyan]detail[/]                     [dim]Esc back · Ctrl+Q quit[/]",
            id="app-header",
        )
        yield Static(
            "  j/k scroll  ·  e edit  ·  o PDF  ·  Alt+a list  ·  Esc back",
            id="action-bar",
        )
        with VerticalScroll(id="detail-scroll"):
            yield Static("", id="detail-title")
            yield Static("", id="detail-meta")
            yield Static("Abstract", classes="section-label")
            yield Static("", id="detail-abstract")
            yield Static("File  ·  o open PDF", classes="section-label")
            yield Static("", id="detail-file")
            yield Static("Lists", classes="section-label")
            yield Static("", id="detail-lists")

    def on_mount(self) -> None:
        self.app.clear_esc_quit()
        self.app.set_action_bar("j/k scroll  ·  e edit  ·  o PDF  ·  Alt+a list  ·  Esc back")
        self.query_one("#detail-scroll", VerticalScroll).focus()
        self._load()

    def _load(self) -> None:
        doc = self.app.db.get_by_id(self.document_id)
        if doc is None:
            self.query_one("#detail-title", Static).update("Document not found")
            return

        self._file_path = doc.file_path
        # Titles/authors may contain [brackets] that break markup
        self.query_one("#detail-title", Static).update(_escape_markup(doc.title))

        authors = _escape_markup(self._format_authors(doc.authors_json))
        status = doc.metadata_status.value if doc.metadata_status else "?"
        source = doc.metadata_source.value if doc.metadata_source else "—"
        year = doc.publication_year or "—"
        journal = _escape_markup(doc.journal or "")
        doi = _escape_markup(doc.doi or "—")
        pmid = _escape_markup(doc.pmid or "—")
        lines = [
            f"[b]Authors[/b]  {authors}",
            f"[b]Journal[/b]  {journal} ({year})",
            f"[b]DOI[/b]      {doi}",
            f"[b]PMID[/b]     {pmid}",
            f"[b]Status[/b]   {status}  via {source}",
        ]
        self.query_one("#detail-meta", Static).update("\n".join(lines))

        abstract = (doc.abstract or "").strip()
        if abstract:
            # Abstracts as plain markup-escaped text (no tags from PubMed labels)
            self.query_one("#detail-abstract", Static).update(_escape_markup(abstract))
        else:
            self.query_one("#detail-abstract", Static).update(
                f"[dim]No abstract available for this record. Try: elib enrich --id {doc.id}[/dim]"
            )

        # Do not use [link=/abs/path] — Rich markup treats "/" after "=" as invalid.
        safe_name = _escape_markup(doc.filename)
        safe_path = _escape_markup(doc.file_path)
        self.query_one("#detail-file", Static).update(
            f"[bold]{safe_name}[/bold]\n"
            f"[dim]{safe_path}[/dim]\n"
            "[cyan]Press o to open in your PDF viewer[/]"
        )

        lists = self.app.db.lists_for_document(self.document_id)
        if lists:
            self.query_one("#detail-lists", Static).update(
                _escape_markup(", ".join(pl.name for pl in lists))
            )
        else:
            self.query_one("#detail-lists", Static).update(
                "[dim]Not on any list — press Alt+a to add[/dim]"
            )

        self.sub_title = f"id={doc.id}"

    @staticmethod
    def _format_authors(authors_json: str) -> str:
        if not authors_json or authors_json in ("[]", "null"):
            return "—"
        try:
            data = json.loads(authors_json)
        except json.JSONDecodeError:
            return authors_json[:200]
        if not isinstance(data, list):
            return str(data)[:200]
        names = []
        for a in data[:12]:
            if isinstance(a, dict):
                last = a.get("last_name") or ""
                first = a.get("first_name") or a.get("initials") or ""
                names.append(f"{last} {first}".strip())
            elif isinstance(a, str):
                names.append(a)
        extra = f" (+{len(data) - 12})" if len(data) > 12 else ""
        return ", ".join(names) + extra if names else "—"

    def action_go_back(self) -> None:
        self.app.clear_esc_quit()
        self.app.pop_screen()

    def action_open_pdf(self) -> None:
        path = self._file_path
        if not path:
            doc = self.app.db.get_by_id(self.document_id)
            path = doc.file_path if doc else None
        if not path:
            self.notify("No file path on this record", severity="warning")
            return
        ok, msg = self.app.open_pdf(path)
        # Multi-line errors: show first line as toast, rest if short
        first = msg.split("\n", 1)[0]
        self.notify(
            first[:180], severity="information" if ok else "error", timeout=8 if not ok else 3
        )

    def action_edit_metadata(self) -> None:
        self.app.clear_esc_quit()
        self.app.push_screen(EditMetadataModal(self.document_id), self._after_edit)

    def _after_edit(self, changed: bool | None) -> None:
        if changed:
            self._load()

    def action_add_to_list(self) -> None:
        from symworx_elibrary.tui.screens.library import AddToListModal

        doc = self.app.db.get_by_id(self.document_id)
        title = doc.title if doc else str(self.document_id)
        self.app.push_screen(AddToListModal(self.document_id, title))

    def on_click(self, event) -> None:
        try:
            if getattr(event.widget, "id", None) == "detail-file":
                self.action_open_pdf()
        except Exception:
            pass


class EditMetadataModal(ModalScreen[bool | None]):
    """Edit authors and publication year; returns True if saved."""

    BINDINGS = [
        Binding("escape", "cancel", "Cancel", show=True),
    ]

    def __init__(self, document_id: int) -> None:
        super().__init__()
        self.document_id = document_id

    @property
    def app(self) -> ElibApp:  # type: ignore[override]
        return super().app  # type: ignore[return-value]

    def compose(self) -> ComposeResult:
        with Vertical(id="edit-meta-dialog"):
            yield Label("Edit authors and year", id="dialog-title")
            yield Static("", id="edit-doc-title")
            yield Input(placeholder="Last, First; Last2, First2", id="edit-authors-input")
            yield Input(placeholder="Year (YYYY, empty to clear)", id="edit-year-input")
            yield Static(
                "Last, First; …  ·  enter save  ·  esc cancel",
                id="dialog-help",
            )

    def on_mount(self) -> None:
        doc = self.app.db.get_by_id(self.document_id)
        if doc is None:
            self.notify("Document not found", severity="error")
            self.dismiss(None)
            return
        self.query_one("#edit-doc-title", Static).update((doc.title or "")[:80])
        authors_inp = self.query_one("#edit-authors-input", Input)
        authors_inp.value = format_authors_editable(doc.authors_json)
        year_inp = self.query_one("#edit-year-input", Input)
        year_inp.value = str(doc.publication_year) if doc.publication_year else ""
        authors_inp.focus()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        if event.input.id in ("edit-authors-input", "edit-year-input"):
            self._save()

    def _save(self) -> None:
        raw_authors = self.query_one("#edit-authors-input", Input).value
        raw_year = self.query_one("#edit-year-input", Input).value.strip()
        try:
            authors = parse_authors_editable(raw_authors)
        except ValueError as e:
            self.notify(str(e), severity="warning")
            return

        clear_year = raw_year == ""
        year: int | None = None
        if not clear_year:
            if not raw_year.isdigit():
                self.notify("Year must be a 4-digit number (YYYY)", severity="warning")
                return
            try:
                year = validate_publication_year(int(raw_year))
            except ValueError as e:
                self.notify(str(e), severity="warning")
                return

        try:
            updated = self.app.db.update_document_fields(
                self.document_id,
                authors=authors,
                publication_year=year,
                clear_year=clear_year,
            )
        except ValueError as e:
            self.notify(str(e), severity="error")
            return
        if updated is None:
            self.notify("Update failed", severity="error")
            return
        self.notify("Saved authors and year", severity="information")
        self.dismiss(True)

    def action_cancel(self) -> None:
        self.dismiss(None)
