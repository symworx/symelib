"""
Library browser screen: search, table, open detail / PDF, add to list.

Aesthetic + quit model follow symworx SymView (cyan chrome, Esc Esc / Ctrl+Q).
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

from textual import events
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen, Screen
from textual.widgets import DataTable, Input, Label, Static

from symworx_elibrary.models.metadata import (
    DocumentMetadata,
    ImportWindow,
    SearchField,
    SearchQuery,
    SortBy,
    SortOrder,
    import_window_bounds,
)
from symworx_elibrary.tui.keys import (
    ALT_ADD_TO_LIST,
    ALT_FIELD,
    ALT_IMPORT,
    ALT_LISTS,
    ALT_NEW_LIST,
    ALT_SORT,
    ALT_SORT_AUTHOR,
    ALT_SORT_ORDER,
    ALT_SORT_YEAR,
    EDIT,
    EDIT_ALT,
    OPEN_PDF,
    QUIT_SCREEN,
    VIM_MOTION,
    VimMotionMixin,
)

if TYPE_CHECKING:
    from symworx_elibrary.tui.app import ElibApp

_FIELD_CYCLE = (
    SearchField.all,
    SearchField.title,
    SearchField.author,
    SearchField.keywords,
    SearchField.abstract,
)

_FIELD_LABEL = {
    SearchField.all: "all",
    SearchField.title: "title",
    SearchField.author: "author",
    SearchField.keywords: "kw",
    SearchField.abstract: "abs",
}

_FIELD_PLACEHOLDER = {
    SearchField.all: "Search all (title · abstract · keywords · authors)  prefix: cardio→cardiovascular",
    SearchField.title: "Search titles only…",
    SearchField.author: "Search authors only…",
    SearchField.keywords: "Search keywords / MeSH only…",
    SearchField.abstract: "Search abstracts only…",
}

# Browse default: year; with active text search: relevance first in cycle
_SORT_CYCLE = (
    SortBy.year,
    SortBy.author,
    SortBy.title,
    SortBy.added_date,
    SortBy.relevance,
)

_SORT_LABEL = {
    SortBy.year: "year",
    SortBy.author: "author",
    SortBy.title: "title",
    SortBy.added_date: "added",
    SortBy.relevance: "rel",
}

_IMPORT_CYCLE = (
    ImportWindow.all,
    ImportWindow.today,
    ImportWindow.days_7,
    ImportWindow.days_30,
)


def _first_author(authors_json: str) -> str:
    if not authors_json or authors_json in ("[]", "null"):
        return "—"
    try:
        data = json.loads(authors_json)
        if isinstance(data, list) and data:
            a = data[0]
            if isinstance(a, dict):
                return a.get("last_name") or a.get("family") or "—"
            if isinstance(a, str):
                return a.split(",")[0][:30]
    except json.JSONDecodeError:
        pass
    return "—"


def _status_badge(meta: DocumentMetadata) -> str:
    s = meta.metadata_status.value if meta.metadata_status else "?"
    return s[:4]


class LibraryScreen(VimMotionMixin, Screen):
    """Main library table + scoped search."""

    BINDINGS = [
        *VIM_MOTION,
        Binding("/", "focus_search", "Search", show=True),
        *ALT_FIELD,
        # Priority so Esc leaves search even when the Input has focus
        Binding("escape", "escape", "Esc", show=False, priority=True),
        Binding("enter", "open_detail", "Open", show=True),
        *OPEN_PDF,
        *EDIT,
        *EDIT_ALT,
        *ALT_ADD_TO_LIST,
        *ALT_LISTS,
        *ALT_SORT,
        *ALT_SORT_ORDER,
        *ALT_IMPORT,
        *ALT_SORT_YEAR,
        *ALT_SORT_AUTHOR,
        *QUIT_SCREEN,
    ]

    def __init__(self) -> None:
        super().__init__()
        self._docs: list[DocumentMetadata] = []
        self._query_text: str | None = None
        self._search_field: SearchField = SearchField.all
        self._sort_by: SortBy = SortBy.year
        self._sort_order: SortOrder = SortOrder.desc
        self._import_window: ImportWindow = ImportWindow.all
        # Persist highlight across table rebuilds (refresh, sort, return from detail/PDF).
        self._selected_doc_id: int | None = None

    @property
    def app(self) -> ElibApp:  # type: ignore[override]
        return super().app  # type: ignore[return-value]

    def compose(self) -> ComposeResult:
        yield Static(
            "[bold]elib[/]  [cyan]library[/]                    [dim]Esc Esc · Ctrl+Q[/]",
            id="app-header",
        )
        yield Static(
            "  j/k move · / search · o PDF · e edit · Alt+i imported · Alt+l lists",
            id="action-bar",
        )
        with Horizontal(id="search-row"):
            yield Static("all", id="search-field-badge")
            yield Input(
                placeholder=_FIELD_PLACEHOLDER[SearchField.all],
                id="search-input",
            )
        yield DataTable(id="docs-table", cursor_type="row", zebra_stripes=True)
        yield Static("", id="status-bar")

    def on_mount(self) -> None:
        table = self.query_one("#docs-table", DataTable)
        table.add_columns("ID", "Year", "Author", "Status", "Abs", "Title")
        table.focus()
        self._update_field_chrome()
        self.refresh_docs()
        self.app.set_action_bar(
            "j/k move · / search · o PDF · e edit · Alt+i imported · Alt+l lists"
        )

    def _search_input(self) -> Input:
        return self.query_one("#search-input", Input)

    def _docs_table(self) -> DataTable:
        return self.query_one("#docs-table", DataTable)

    def _search_focused(self) -> bool:
        """True when the search box (or a child) has keyboard focus."""
        focused = self.focused
        if focused is None:
            return False
        if getattr(focused, "id", None) == "search-input":
            return True
        try:
            return self._search_input() in focused.ancestors_with_self
        except Exception:
            return isinstance(focused, Input)

    def _focus_table(self) -> None:
        table = self._docs_table()
        table.focus()
        self._restore_selection(table)

    def focus_results(self) -> None:
        """Public: put the keyboard back on the results table."""
        self._focus_table()

    def _update_field_chrome(self) -> None:
        badge = self.query_one("#search-field-badge", Static)
        badge.update(_FIELD_LABEL[self._search_field])
        inp = self._search_input()
        inp.placeholder = _FIELD_PLACEHOLDER[self._search_field]

    def _sort_label(self) -> str:
        arrow = "↓" if self._sort_order == SortOrder.desc else "↑"
        return f"{_SORT_LABEL[self._sort_by]}{arrow}"

    def _capture_selection(self) -> None:
        """Remember the currently highlighted document id (if any)."""
        try:
            table = self.query_one("#docs-table", DataTable)
            if table.row_count == 0:
                return
            row_key = table.coordinate_to_cell_key(table.cursor_coordinate).row_key
            if row_key is not None and row_key.value is not None:
                self._selected_doc_id = int(row_key.value)
        except Exception:
            pass

    def _restore_selection(self, table: DataTable) -> None:
        """Move cursor back to the remembered document after a table rebuild."""
        if self._selected_doc_id is None or table.row_count == 0:
            return
        key = str(self._selected_doc_id)
        try:
            idx = table.get_row_index(key)
        except Exception:
            return
        table.move_cursor(row=idx, animate=False, scroll=True)

    def on_data_table_row_highlighted(self, event: DataTable.RowHighlighted) -> None:
        """Track highlight as the user moves the cursor."""
        if event.row_key is not None and event.row_key.value is not None:
            try:
                self._selected_doc_id = int(event.row_key.value)
            except (TypeError, ValueError):
                pass

    def refresh_docs(self, text: str | None = None) -> None:
        # Keep highlight across clear/rebuild (and after returning from detail).
        self._capture_selection()
        self._query_text = text if text else None
        db = self.app.db
        added_from, added_to = import_window_bounds(self._import_window)
        # When searching with relevance preferred and sort is still default year,
        # auto-use relevance for text queries if user hasn't locked another mode
        sort_by = self._sort_by
        if text and sort_by == SortBy.relevance:
            pass  # ok
        if text:
            results = db.search(
                SearchQuery(
                    text=text,
                    search_field=self._search_field,
                    sort_by=sort_by,
                    sort_order=self._sort_order,
                    added_from=added_from,
                    added_to=added_to,
                    limit=200,
                )
            )
            self._docs = [r.metadata for r in results]
        else:
            # relevance without query → added_date
            effective = sort_by if sort_by != SortBy.relevance else SortBy.added_date
            self._docs = db.list_documents(
                limit=500,
                sort_by=effective,
                sort_order=self._sort_order,
                added_from=added_from,
                added_to=added_to,
            )

        table = self.query_one("#docs-table", DataTable)
        table.clear()
        for d in self._docs:
            year = str(d.publication_year) if d.publication_year else "—"
            abs_flag = "Y" if d.abstract and d.abstract.strip() else "·"
            title = (d.title or "")[:90]
            table.add_row(
                str(d.id or ""),
                year,
                _first_author(d.authors_json)[:20],
                _status_badge(d),
                abs_flag,
                title,
                key=str(d.id),
            )
        self._restore_selection(table)

        status = self.query_one("#status-bar", Static)
        field = _FIELD_LABEL[self._search_field]
        q = f'[{field}] "{text}" · ' if text else f"[{field}] · "
        imported = (
            ""
            if self._import_window == ImportWindow.all
            else f"imported={self._import_window.value} · "
        )
        counts = db.count_by_status()
        status.update(
            f"{q}{imported}sort={self._sort_label()} · {len(self._docs)} shown · "
            f"library={db.count_documents()} · "
            f"complete={counts.get('complete', 0)} "
            f"partial={counts.get('partial', 0)} "
            f"fallback={counts.get('fallback', 0)}"
        )

    def on_input_submitted(self, event: Input.Submitted) -> None:
        if event.input.id == "search-input":
            self.app.clear_esc_quit()
            q = event.value.strip()
            self.refresh_docs(q if q else None)
            self._focus_table()

    def on_input_changed(self, event: Input.Changed) -> None:
        # Typing cancels pending double-Esc quit
        if event.input.id == "search-input":
            self.app.clear_esc_quit()

    def on_key(self, event: events.Key) -> None:
        """While typing in search: ↓ / Tab leave the box so you can browse results."""
        if not self._search_focused():
            return
        if event.key in ("down", "tab"):
            event.stop()
            event.prevent_default()
            self.app.clear_esc_quit()
            self._focus_table()

    def on_click(self, event: events.Click) -> None:
        """Click the field badge (all/title/…) to cycle search scope."""
        widget = event.widget
        if widget is not None and getattr(widget, "id", None) == "search-field-badge":
            event.stop()
            self.action_cycle_field()

    def action_focus_search(self) -> None:
        self.app.clear_esc_quit()
        inp = self._search_input()
        inp.focus()
        # Select all so a new query can replace quickly; Esc still just leaves focus
        if inp.value:
            inp.action_select_all()

    def action_cycle_field(self) -> None:
        self.app.clear_esc_quit()
        idx = _FIELD_CYCLE.index(self._search_field)
        self._search_field = _FIELD_CYCLE[(idx + 1) % len(_FIELD_CYCLE)]
        self._update_field_chrome()
        # Prefer draft text in the box, else last submitted query
        draft = self._search_input().value.strip()
        q = draft or self._query_text
        self.refresh_docs(q if q else None)
        self.notify(
            f"Search field: {_FIELD_LABEL[self._search_field]}  (Alt+f / Ctrl+f while typing)",
            timeout=2,
        )

    def action_cycle_sort(self) -> None:
        self.app.clear_esc_quit()
        idx = _SORT_CYCLE.index(self._sort_by)
        self._sort_by = _SORT_CYCLE[(idx + 1) % len(_SORT_CYCLE)]
        self.refresh_docs(self._query_text)
        self.notify(f"Sort: {self._sort_label()}", timeout=2)

    def action_toggle_sort_order(self) -> None:
        self.app.clear_esc_quit()
        self._sort_order = SortOrder.asc if self._sort_order == SortOrder.desc else SortOrder.desc
        self.refresh_docs(self._query_text)
        self.notify(f"Sort: {self._sort_label()}", timeout=2)

    def action_cycle_import_window(self) -> None:
        self.app.clear_esc_quit()
        idx = _IMPORT_CYCLE.index(self._import_window)
        self._import_window = _IMPORT_CYCLE[(idx + 1) % len(_IMPORT_CYCLE)]
        self.refresh_docs(self._query_text)
        label = self._import_window.value
        self.notify(f"Imported: {label}", timeout=2)

    def action_sort_year(self) -> None:
        self.app.clear_esc_quit()
        if self._sort_by == SortBy.year:
            self._sort_order = (
                SortOrder.asc if self._sort_order == SortOrder.desc else SortOrder.desc
            )
        else:
            self._sort_by = SortBy.year
            self._sort_order = SortOrder.desc
        self.refresh_docs(self._query_text)
        self.notify(f"Sort: {self._sort_label()}", timeout=2)

    def action_sort_author(self) -> None:
        self.app.clear_esc_quit()
        if self._sort_by == SortBy.author:
            self._sort_order = (
                SortOrder.asc if self._sort_order == SortOrder.desc else SortOrder.desc
            )
        else:
            self._sort_by = SortBy.author
            self._sort_order = SortOrder.asc
        self.refresh_docs(self._query_text)
        self.notify(f"Sort: {self._sort_label()}", timeout=2)

    def action_escape(self) -> None:
        """
        Esc ladder (SymView-style, search-friendly):

        1. Search box focused → leave box, focus results table (keep text/results)
        2. Table focused + active/draft search → clear search, show full library
        3. Import-date window active → reset to all
        4. Otherwise → double-Esc quit at root
        """
        inp = self._search_input()

        # 1) Get out of the search box without wiping the query
        if self._search_focused():
            self.app.clear_esc_quit()
            self._focus_table()
            return

        # 2) Clear active or draft search from the table
        if self._query_text or inp.value.strip():
            self.app.clear_esc_quit()
            inp.value = ""
            self.refresh_docs(None)
            self._focus_table()
            return

        # 3) Clear import-date window
        if self._import_window != ImportWindow.all:
            self.app.clear_esc_quit()
            self._import_window = ImportWindow.all
            self.refresh_docs(None)
            self._focus_table()
            self.notify("Imported: all", timeout=2)
            return

        # 4) Root: Esc Esc quit
        self.app.handle_root_escape()

    def action_refresh(self) -> None:
        """Reload library from SQLite (e.g. after `elib process` in another terminal)."""
        self.app.clear_esc_quit()
        self.app.reload_db()
        self.refresh_docs(self._query_text)
        self.notify(
            f"Refreshed — {self.app.db.count_documents()} documents in library",
            timeout=3,
        )

    def on_screen_resume(self) -> None:
        """When returning from detail/lists, pull latest rows (cheap)."""
        # Soft reload data without tearing down sort/search/selection state
        try:
            self.refresh_docs(self._query_text)
        except Exception:
            pass
        try:
            table = self.query_one("#docs-table", DataTable)
            table.focus()
            self._restore_selection(table)
        except Exception:
            pass

    def _selected_doc(self) -> DocumentMetadata | None:
        table = self.query_one("#docs-table", DataTable)
        if table.row_count == 0:
            return None
        self._capture_selection()
        doc_id = self._selected_doc_id
        if doc_id is None:
            row_key = table.coordinate_to_cell_key(table.cursor_coordinate).row_key
            if row_key is None or row_key.value is None:
                return None
            doc_id = int(row_key.value)
            self._selected_doc_id = doc_id
        for d in self._docs:
            if d.id == doc_id:
                return d
        return self.app.db.get_by_id(doc_id)

    def action_open_detail(self) -> None:
        self.app.clear_esc_quit()
        doc = self._selected_doc()
        if doc is None:
            self.notify("No document selected", severity="warning")
            return
        if doc.id is not None:
            self._selected_doc_id = doc.id
        from symworx_elibrary.tui.screens.detail import DetailScreen

        self.app.push_screen(DetailScreen(doc.id))  # type: ignore[arg-type]

    def action_open_pdf(self) -> None:
        self.app.clear_esc_quit()
        doc = self._selected_doc()
        if doc is None:
            self.notify("No document selected", severity="warning")
            return
        if doc.id is not None:
            self._selected_doc_id = doc.id
        ok, msg = self.app.open_pdf(doc.file_path)
        first = msg.split("\n", 1)[0]
        self.notify(
            first[:180], severity="information" if ok else "error", timeout=8 if not ok else 3
        )
        # External viewer steals focus; put cursor back on the same row.
        try:
            table = self.query_one("#docs-table", DataTable)
            table.focus()
            self._restore_selection(table)
        except Exception:
            pass

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        _ = event
        self.action_open_detail()

    def action_edit_metadata(self) -> None:
        self.app.clear_esc_quit()
        doc = self._selected_doc()
        if doc is None or doc.id is None:
            self.notify("No document selected", severity="warning")
            return
        from symworx_elibrary.tui.screens.detail import EditMetadataModal

        self.app.push_screen(EditMetadataModal(doc.id), self._after_edit)

    def _after_edit(self, changed: bool | None) -> None:
        if changed:
            self.refresh_docs(self._query_text)

    def action_add_to_list(self) -> None:
        self.app.clear_esc_quit()
        doc = self._selected_doc()
        if doc is None or doc.id is None:
            self.notify("No document selected", severity="warning")
            return
        self.app.push_screen(AddToListModal(doc.id, doc.title))

    def action_open_lists(self) -> None:
        self.app.clear_esc_quit()
        from symworx_elibrary.tui.screens.lists import ListsScreen

        self.app.push_screen(ListsScreen())


class AddToListModal(VimMotionMixin, ModalScreen[None]):
    """Pick a list (or create one) and add the current document."""

    BINDINGS = [
        *VIM_MOTION,
        Binding("escape", "dismiss", "Cancel", show=True),
        *ALT_NEW_LIST,
        Binding("enter", "confirm", "Add", show=True),
    ]

    def __init__(self, document_id: int, title: str) -> None:
        super().__init__()
        self.document_id = document_id
        self.doc_title = title

    @property
    def app(self) -> ElibApp:  # type: ignore[override]
        return super().app  # type: ignore[return-value]

    def compose(self) -> ComposeResult:
        with Vertical(id="add-list-dialog"):
            yield Label("Add to list", id="dialog-title")
            yield Static(self.doc_title[:80], id="dialog-doc")
            yield DataTable(id="pick-list-table", cursor_type="row")
            yield Static("enter add · Alt+n new list · esc cancel", id="dialog-help")

    def on_mount(self) -> None:
        table = self.query_one("#pick-list-table", DataTable)
        table.add_columns("Name", "Papers", "Description")
        self._reload()

    def _reload(self) -> None:
        table = self.query_one("#pick-list-table", DataTable)
        table.clear()
        for pl in self.app.db.list_paper_lists():
            table.add_row(
                pl.name,
                str(pl.item_count),
                (pl.description or "")[:40],
                key=pl.name,
            )
        table.focus()

    def action_new_list(self) -> None:
        self.app.push_screen(CreateListModal(), self._after_create)

    def _after_create(self, name: str | None) -> None:
        if name:
            self._reload()

    def action_confirm(self) -> None:
        table = self.query_one("#pick-list-table", DataTable)
        if table.row_count == 0:
            self.notify("Create a list first (Alt+n)", severity="warning")
            return
        row_key = table.coordinate_to_cell_key(table.cursor_coordinate).row_key
        if row_key is None or row_key.value is None:
            return
        list_name = str(row_key.value)
        item = self.app.db.add_to_list(list_name=list_name, document_id=self.document_id)
        if item:
            self.notify(f"Added to “{list_name}”", severity="information")
            self.dismiss()
        else:
            self.notify("Failed to add", severity="error")

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        _ = event
        self.action_confirm()


class CreateListModal(ModalScreen[str | None]):
    """Create a new named list; returns the name."""

    BINDINGS = [
        Binding("escape", "cancel", "Cancel", show=True),
    ]

    @property
    def app(self) -> ElibApp:  # type: ignore[override]
        return super().app  # type: ignore[return-value]

    def compose(self) -> ComposeResult:
        with Vertical(id="create-list-dialog"):
            yield Label("New paper list", id="dialog-title")
            yield Input(placeholder="Name (e.g. R01-2026)", id="list-name-input")
            yield Input(placeholder="Description (optional)", id="list-desc-input")
            yield Static("enter to create · esc cancel", id="dialog-help")

    def on_mount(self) -> None:
        self.query_one("#list-name-input", Input).focus()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        if event.input.id in ("list-name-input", "list-desc-input"):
            self._create()

    def _create(self) -> None:
        name = self.query_one("#list-name-input", Input).value.strip()
        desc = self.query_one("#list-desc-input", Input).value.strip() or None
        if not name:
            self.notify("Name required", severity="warning")
            return
        try:
            self.app.db.create_paper_list(name, description=desc)
        except Exception as e:
            self.notify(f"Could not create: {e}", severity="error")
            return
        self.dismiss(name)

    def action_cancel(self) -> None:
        self.dismiss(None)
