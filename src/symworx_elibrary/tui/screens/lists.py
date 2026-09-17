"""
Paper lists browser + list detail + BibTeX export.

- Enter a list → view *only* papers on that list
- x → remove selected paper from the list (not from library)
- d → soft-delete the list (hidden; membership kept; restore via CLI)
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.screen import ModalScreen, Screen
from textual.widgets import DataTable, Input, Label, Static

from symworx_elibrary.models.metadata import SortBy, SortOrder
from symworx_elibrary.services.bibtex import documents_to_bibtex
from symworx_elibrary.tui.keys import (
    ALT_EXPORT,
    ALT_EXPORT_DETAIL,
    ALT_NEW_LIST,
    ALT_RENAME_LIST,
    ALT_SORT,
    ALT_SORT_AUTHOR,
    ALT_SORT_ORDER,
    ALT_SORT_YEAR,
    EDIT,
    OPEN_PDF,
    QUIT_SCREEN,
    VIM_MOTION,
    VimMotionMixin,
)

if TYPE_CHECKING:
    from symworx_elibrary.tui.app import ElibApp

_SORT_CYCLE = (SortBy.year, SortBy.author, SortBy.title, SortBy.added_date)
_SORT_LABEL = {
    SortBy.year: "year",
    SortBy.author: "author",
    SortBy.title: "title",
    SortBy.added_date: "added",
}


class ListsScreen(VimMotionMixin, Screen):
    """Browse named paper lists (active only; soft-deleted hidden)."""

    BINDINGS = [
        *VIM_MOTION,
        Binding("escape", "go_back", "Back", show=True),
        Binding("enter", "open_list", "View", show=True),
        *ALT_NEW_LIST,
        *ALT_RENAME_LIST,
        *ALT_EXPORT,
        Binding("d", "delete_list", "Soft-del", show=True),
        *QUIT_SCREEN,
    ]

    def __init__(self) -> None:
        super().__init__()
        self._selected_name_key: str | None = None

    @property
    def app(self) -> ElibApp:  # type: ignore[override]
        return super().app  # type: ignore[return-value]

    def compose(self) -> ComposeResult:
        yield Static(
            "[bold]elib[/]  [cyan]lists[/]                      [dim]Esc back · Ctrl+Q quit[/]",
            id="app-header",
        )
        yield Static(
            "  j/k move · enter view · Alt+n new · Alt+m rename · Alt+e export · d del · Esc",
            id="action-bar",
        )
        yield Static("Paper lists — enter to view only that list’s papers", id="status-bar")
        yield DataTable(id="lists-table", cursor_type="row", zebra_stripes=True)

    def on_mount(self) -> None:
        self.app.clear_esc_quit()
        self.app.set_action_bar(
            "j/k move  ·  enter view  ·  Alt+n new  ·  Alt+m rename  ·  Alt+e export  ·  Esc"
        )
        table = self.query_one("#lists-table", DataTable)
        table.add_columns("Name", "Papers", "Description")
        self.reload_table()
        table.focus()

    def action_go_back(self) -> None:
        self.app.clear_esc_quit()
        self.app.pop_screen()

    def action_refresh(self) -> None:
        self.app.reload_db()
        self.reload_table()
        self.notify("Lists refreshed", timeout=2)

    def on_screen_resume(self) -> None:
        try:
            self.reload_table()
        except Exception:
            pass
        try:
            table = self.query_one("#lists-table", DataTable)
            table.focus()
            self._restore_selection(table)
        except Exception:
            pass

    def _capture_selection(self) -> None:
        try:
            table = self.query_one("#lists-table", DataTable)
            if table.row_count == 0:
                return
            row_key = table.coordinate_to_cell_key(table.cursor_coordinate).row_key
            if row_key is not None and row_key.value is not None:
                self._selected_name_key = str(row_key.value)
        except Exception:
            pass

    def _restore_selection(self, table: DataTable) -> None:
        if not self._selected_name_key or table.row_count == 0:
            return
        try:
            idx = table.get_row_index(self._selected_name_key)
            table.move_cursor(row=idx, animate=False, scroll=True)
        except Exception:
            pass

    def on_data_table_row_highlighted(self, event: DataTable.RowHighlighted) -> None:
        if event.row_key is not None and event.row_key.value is not None:
            self._selected_name_key = str(event.row_key.value)

    def reload_table(self) -> None:
        """Reload list rows from the DB (do not name this ``refresh`` — that is Textual's)."""
        self._capture_selection()
        table = self.query_one("#lists-table", DataTable)
        table.clear()
        for pl in self.app.db.list_paper_lists(include_deleted=False):
            table.add_row(
                pl.name,
                str(pl.item_count),
                (pl.description or "")[:50],
                key=pl.name,
            )
        self._restore_selection(table)
        bar = self.query_one("#status-bar", Static)
        n = table.row_count
        bar.update(
            f"{n} active list(s) · enter view · Alt+m rename · d soft-delete "
            f"(restore: elib list restore NAME)"
        )

    def _selected_name(self) -> str | None:
        self._capture_selection()
        if self._selected_name_key:
            return self._selected_name_key
        table = self.query_one("#lists-table", DataTable)
        if table.row_count == 0:
            return None
        row_key = table.coordinate_to_cell_key(table.cursor_coordinate).row_key
        if row_key is None or row_key.value is None:
            return None
        return str(row_key.value)

    def action_open_list(self) -> None:
        name = self._selected_name()
        if not name:
            self.notify("No list selected", severity="warning")
            return
        self._selected_name_key = name
        self.app.push_screen(ListDetailScreen(name))

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        _ = event
        self.action_open_list()

    def action_new_list(self) -> None:
        from symworx_elibrary.tui.screens.library import CreateListModal

        self.app.push_screen(CreateListModal(), self._after_create)

    def _after_create(self, name: str | None) -> None:
        self.reload_table()
        if name:
            self._selected_name_key = name
            self.notify(f"Created “{name}” — enter to view its papers")

    def action_rename_list(self) -> None:
        """Edit selected list name and/or description."""
        name = self._selected_name()
        if not name:
            self.notify("No list selected", severity="warning")
            return
        pl = self.app.db.get_paper_list(name=name)
        if pl is None:
            self.notify(f"List not found: {name}", severity="error")
            return
        self.app.push_screen(
            RenameListModal(current_name=pl.name, description=pl.description or ""),
            self._after_rename,
        )

    def _after_rename(self, result: tuple[str, str] | None) -> None:
        """Callback: (old_name, new_name) or None if cancelled."""
        if not result:
            return
        old_name, new_name = result
        self._selected_name_key = new_name
        self.reload_table()
        if old_name != new_name:
            self.notify(f"Renamed “{old_name}” → “{new_name}”", timeout=4)
        else:
            self.notify(f"Updated “{new_name}”", timeout=3)

    def action_export_list(self) -> None:
        name = self._selected_name()
        if not name:
            self.notify("No list selected", severity="warning")
            return
        items = self.app.db.get_list_items(list_name=name)
        docs = [i.document for i in items if i.document is not None]
        if not docs:
            self.notify("List is empty", severity="warning")
            return
        bib = documents_to_bibtex(docs)
        safe = "".join(c if c.isalnum() or c in "-_." else "_" for c in name)
        out_dir = Path(self.app.config.exports_directory).expanduser()
        out_dir.mkdir(parents=True, exist_ok=True)
        out = out_dir / f"{safe}.bib"
        out.write_text(bib, encoding="utf-8")
        self.notify(f"Wrote {len(docs)} entries → {out}", timeout=5)

    def action_delete_list(self) -> None:
        """Soft-delete: hide list; membership + papers kept."""
        name = self._selected_name()
        if not name:
            return
        if self.app.db.soft_delete_paper_list(name=name):
            self.notify(
                f"Soft-deleted “{name}” (hidden). Restore: elib list restore {name!r}",
                timeout=6,
            )
            self.reload_table()
        else:
            self.notify("Delete failed", severity="error")


class RenameListModal(ModalScreen[tuple[str, str] | None]):
    """Edit list name and description. Dismisses with (old_name, new_name) or None."""

    BINDINGS = [
        Binding("escape", "cancel", "Cancel", show=True, priority=True),
    ]

    def __init__(self, current_name: str, description: str = "") -> None:
        super().__init__()
        self.current_name = current_name
        self.initial_description = description

    @property
    def app(self) -> ElibApp:  # type: ignore[override]
        return super().app  # type: ignore[return-value]

    def compose(self) -> ComposeResult:
        with Vertical(id="create-list-dialog"):
            yield Label(f"Rename list “{self.current_name}”", id="dialog-title")
            yield Input(
                value=self.current_name,
                placeholder="List name",
                id="list-name-input",
            )
            yield Input(
                value=self.initial_description,
                placeholder="Description (optional)",
                id="list-desc-input",
            )
            yield Static("enter save · esc cancel", id="dialog-help")

    def on_mount(self) -> None:
        inp = self.query_one("#list-name-input", Input)
        inp.focus()
        if inp.value:
            inp.action_select_all()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        if event.input.id in ("list-name-input", "list-desc-input"):
            self._save()

    def _save(self) -> None:
        new_name = self.query_one("#list-name-input", Input).value.strip()
        desc = self.query_one("#list-desc-input", Input).value.strip()
        if not new_name:
            self.notify("Name required", severity="warning")
            return
        try:
            pl = self.app.db.rename_paper_list(
                name=self.current_name,
                new_name=new_name,
                description=desc,
            )
        except Exception as e:
            self.notify(f"Could not rename: {e}", severity="error")
            return
        if pl is None:
            self.notify("List not found", severity="error")
            return
        self.dismiss((self.current_name, pl.name))

    def action_cancel(self) -> None:
        self.dismiss(None)


class ListDetailScreen(VimMotionMixin, Screen):
    """Papers belonging to one named list only."""

    BINDINGS = [
        *VIM_MOTION,
        Binding("escape", "go_back", "Back", show=True),
        Binding("enter", "open_detail", "Detail", show=True),
        *OPEN_PDF,
        *EDIT,
        *ALT_RENAME_LIST,
        *ALT_EXPORT_DETAIL,
        Binding("x", "remove", "Remove", show=True),
        Binding("delete", "remove", "Remove", show=False),
        *ALT_SORT,
        *ALT_SORT_ORDER,
        *ALT_SORT_YEAR,
        *ALT_SORT_AUTHOR,
        *QUIT_SCREEN,
    ]

    def __init__(self, list_name: str) -> None:
        super().__init__()
        self.list_name = list_name
        self._sort_by: SortBy = SortBy.year
        self._sort_order: SortOrder = SortOrder.desc
        self._selected_doc_id: int | None = None

    @property
    def app(self) -> ElibApp:  # type: ignore[override]
        return super().app  # type: ignore[return-value]

    def compose(self) -> ComposeResult:
        yield Static(
            f"[bold]elib[/]  [cyan]list[/]  {self.list_name}            [dim]Esc back · Ctrl+Q[/]",
            id="app-header",
        )
        yield Static(
            "  j/k move · enter detail · o PDF · e edit · Alt+e export · x remove",
            id="action-bar",
        )
        yield Static("", id="status-bar")
        yield DataTable(id="list-items-table", cursor_type="row", zebra_stripes=True)

    def on_mount(self) -> None:
        self.app.clear_esc_quit()
        self.app.set_action_bar(f"list “{self.list_name}” · j/k move · o PDF · e edit · x remove")
        table = self.query_one("#list-items-table", DataTable)
        table.add_columns("ID", "Year", "Title")
        self.reload_table()
        table.focus()
        self.sub_title = self.list_name

    def action_go_back(self) -> None:
        self.app.clear_esc_quit()
        self.app.pop_screen()

    def action_rename_list(self) -> None:
        pl = self.app.db.get_paper_list(name=self.list_name)
        if pl is None:
            self.notify("List not found", severity="error")
            return
        self.app.push_screen(
            RenameListModal(current_name=pl.name, description=pl.description or ""),
            self._after_rename,
        )

    def _after_rename(self, result: tuple[str, str] | None) -> None:
        if not result:
            return
        _old, new_name = result
        self.list_name = new_name
        self.sub_title = new_name
        try:
            header = self.query_one("#app-header", Static)
            header.update(
                f"[bold]elib[/]  [cyan]list[/]  {self.list_name}            "
                f"[dim]Esc back · Ctrl+Q[/]"
            )
            self.app.set_action_bar(
                f"list “{self.list_name}” · j/k move · o PDF · e edit · x remove"
            )
        except Exception:
            pass
        self.reload_table()
        self.notify(f"List is now “{new_name}”", timeout=3)

    def action_open_pdf(self) -> None:
        doc_id = self._selected_id()
        if doc_id is None:
            self.notify("No paper selected", severity="warning")
            return
        self._selected_doc_id = doc_id
        doc = self.app.db.get_by_id(doc_id)
        if not doc:
            return
        ok, msg = self.app.open_pdf(doc.file_path)
        first = msg.split("\n", 1)[0]
        self.notify(
            first[:180], severity="information" if ok else "error", timeout=8 if not ok else 3
        )
        try:
            table = self.query_one("#list-items-table", DataTable)
            table.focus()
            self._restore_selection(table)
        except Exception:
            pass

    def _sort_label(self) -> str:
        arrow = "↓" if self._sort_order == SortOrder.desc else "↑"
        return f"{_SORT_LABEL[self._sort_by]}{arrow}"

    def _capture_selection(self) -> None:
        try:
            table = self.query_one("#list-items-table", DataTable)
            if table.row_count == 0:
                return
            row_key = table.coordinate_to_cell_key(table.cursor_coordinate).row_key
            if row_key is not None and row_key.value is not None:
                self._selected_doc_id = int(row_key.value)
        except Exception:
            pass

    def _restore_selection(self, table: DataTable) -> None:
        if self._selected_doc_id is None or table.row_count == 0:
            return
        try:
            idx = table.get_row_index(str(self._selected_doc_id))
            table.move_cursor(row=idx, animate=False, scroll=True)
        except Exception:
            pass

    def on_data_table_row_highlighted(self, event: DataTable.RowHighlighted) -> None:
        if event.row_key is not None and event.row_key.value is not None:
            try:
                self._selected_doc_id = int(event.row_key.value)
            except (TypeError, ValueError):
                pass

    def on_screen_resume(self) -> None:
        try:
            self.reload_table()
        except Exception:
            pass
        try:
            table = self.query_one("#list-items-table", DataTable)
            table.focus()
            self._restore_selection(table)
        except Exception:
            pass

    def reload_table(self) -> None:
        """Reload papers for this list (do not name this ``refresh`` — Textual owns that)."""
        self._capture_selection()
        table = self.query_one("#list-items-table", DataTable)
        table.clear()
        items = self.app.db.get_list_items(
            list_name=self.list_name,
            sort_by=self._sort_by,
            sort_order=self._sort_order,
        )
        for item in items:
            d = item.document
            if d is None:
                continue
            year = str(d.publication_year) if d.publication_year else "—"
            table.add_row(str(d.id), year, (d.title or "")[:90], key=str(d.id))
        self._restore_selection(table)
        bar = self.query_one("#status-bar", Static)
        bar.update(
            f"“{self.list_name}” — {table.row_count} paper(s) · sort={self._sort_label()}  ·  "
            f"x = remove from list (keeps file in library)"
        )

    def action_cycle_sort(self) -> None:
        idx = _SORT_CYCLE.index(self._sort_by)
        self._sort_by = _SORT_CYCLE[(idx + 1) % len(_SORT_CYCLE)]
        self.reload_table()
        self.notify(f"Sort: {self._sort_label()}", timeout=2)

    def action_toggle_sort_order(self) -> None:
        self._sort_order = SortOrder.asc if self._sort_order == SortOrder.desc else SortOrder.desc
        self.reload_table()
        self.notify(f"Sort: {self._sort_label()}", timeout=2)

    def action_sort_year(self) -> None:
        if self._sort_by == SortBy.year:
            self._sort_order = (
                SortOrder.asc if self._sort_order == SortOrder.desc else SortOrder.desc
            )
        else:
            self._sort_by = SortBy.year
            self._sort_order = SortOrder.desc
        self.reload_table()
        self.notify(f"Sort: {self._sort_label()}", timeout=2)

    def action_sort_author(self) -> None:
        if self._sort_by == SortBy.author:
            self._sort_order = (
                SortOrder.asc if self._sort_order == SortOrder.desc else SortOrder.desc
            )
        else:
            self._sort_by = SortBy.author
            self._sort_order = SortOrder.asc
        self.reload_table()
        self.notify(f"Sort: {self._sort_label()}", timeout=2)

    def _selected_id(self) -> int | None:
        self._capture_selection()
        if self._selected_doc_id is not None:
            return self._selected_doc_id
        table = self.query_one("#list-items-table", DataTable)
        if table.row_count == 0:
            return None
        row_key = table.coordinate_to_cell_key(table.cursor_coordinate).row_key
        if row_key is None or row_key.value is None:
            return None
        return int(row_key.value)

    def action_open_detail(self) -> None:
        doc_id = self._selected_id()
        if doc_id is None:
            return
        self._selected_doc_id = doc_id
        from symworx_elibrary.tui.screens.detail import DetailScreen

        self.app.push_screen(DetailScreen(doc_id))

    def action_edit_metadata(self) -> None:
        doc_id = self._selected_id()
        if doc_id is None:
            self.notify("No paper selected", severity="warning")
            return
        self._selected_doc_id = doc_id
        from symworx_elibrary.tui.screens.detail import EditMetadataModal

        self.app.push_screen(EditMetadataModal(doc_id), self._after_edit)

    def _after_edit(self, changed: bool | None) -> None:
        if changed:
            self.reload_table()

    def action_refresh(self) -> None:
        self.app.reload_db()
        self.reload_table()
        self.notify("List refreshed", timeout=2)

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        _ = event
        self.action_open_detail()

    def action_export(self) -> None:
        items = self.app.db.get_list_items(list_name=self.list_name)
        docs = [i.document for i in items if i.document is not None]
        if not docs:
            self.notify("List is empty", severity="warning")
            return
        bib = documents_to_bibtex(docs)
        safe = "".join(c if c.isalnum() or c in "-_." else "_" for c in self.list_name)
        out_dir = Path(self.app.config.exports_directory).expanduser()
        out_dir.mkdir(parents=True, exist_ok=True)
        out = out_dir / f"{safe}.bib"
        out.write_text(bib, encoding="utf-8")
        self.notify(f"Wrote {len(docs)} entries → {out}", timeout=5)

    def action_remove(self) -> None:
        """Remove paper from this list only — does not delete the library file."""
        doc_id = self._selected_id()
        if doc_id is None:
            self.notify("No paper selected", severity="warning")
            return
        if self.app.db.remove_from_list(list_name=self.list_name, document_id=doc_id):
            self.notify(f"Removed id={doc_id} from “{self.list_name}” (file kept in library)")
            self.reload_table()
        else:
            self.notify("Remove failed", severity="error")
