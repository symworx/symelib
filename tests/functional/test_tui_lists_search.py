"""
Functional (Textual pilot) tests for library search + lists navigation.

Regression: ListsScreen/ListDetailScreen must not define a method named
``refresh`` — that overrides Textual's Widget.refresh and crashes on push.
"""

from __future__ import annotations

import asyncio
from datetime import date
from pathlib import Path

import pytest
from textual.widgets import DataTable, Input

from symworx_elibrary.models.metadata import MetadataSource, MetadataStatus
from symworx_elibrary.models.reference import Author, Journal, Reference
from symworx_elibrary.services.db_manager import DatabaseManager
from symworx_elibrary.tui.app import ElibApp
from symworx_elibrary.tui.screens.detail import DetailScreen, EditMetadataModal
from symworx_elibrary.tui.screens.library import LibraryScreen
from symworx_elibrary.tui.screens.lists import ListDetailScreen, ListsScreen
from symworx_elibrary.utils.config import Config


@pytest.fixture
def tui_env(tmp_path: Path):
    db_path = tmp_path / "elib.db"
    db = DatabaseManager(db_path)
    pdf = tmp_path / "paper.pdf"
    pdf.write_bytes(b"%PDF-1.4")
    ref = Reference(
        pmid="12345678",
        doi="10.1234/test.cardiovascular",
        title="Cardiovascular risk assessment study",
        authors=[Author(last_name="Smith", first_name="Ada", initials="A")],
        journal=Journal(title="Nature"),
        publication_date=date(2020, 6, 1),
        abstract="An abstract about cardiovascular outcomes.",
        keywords=["cardio"],
        mesh_terms=[],
    )
    doc_id = db.add_document(
        ref,
        file_path=pdf,
        filename=pdf.name,
        file_size=pdf.stat().st_size,
        metadata_status=MetadataStatus.complete,
        metadata_source=MetadataSource.pubmed,
    )
    db.create_paper_list("grant-1", description="Grant literature")
    db.add_to_list(list_name="grant-1", document_id=doc_id)

    cfg = Config(
        ncbi_email="test@example.com",
        database_path=db_path,
        target_directory=tmp_path / "library",
        cart_directory=tmp_path / "cart",
        exports_directory=tmp_path / "exports",
        pdf_viewer="true",
    )
    cfg.ensure_dirs()
    return {"db_path": db_path, "config": cfg, "db": db, "doc_id": doc_id, "pdf": pdf}


def _run(coro):
    return asyncio.run(coro)


def test_lists_screen_does_not_shadow_textual_refresh():
    """Guard against reintroducing the crash: Widget.refresh must stay intact."""
    assert "refresh" not in ListsScreen.__dict__
    assert "refresh" not in ListDetailScreen.__dict__
    assert hasattr(ListsScreen, "reload_table")
    assert hasattr(ListDetailScreen, "reload_table")


def test_open_lists_screen_does_not_crash(tui_env):
    async def body():
        app = ElibApp(db_path=tui_env["db_path"], config=tui_env["config"])
        async with app.run_test(size=(120, 40)) as pilot:
            assert isinstance(app.screen, LibraryScreen)
            await pilot.press("alt+l")
            await pilot.pause()
            assert isinstance(app.screen, ListsScreen)
            table = app.screen.query_one("#lists-table")
            assert table.row_count >= 1

    _run(body())


def test_view_list_papers_and_remove(tui_env):
    async def body():
        app = ElibApp(db_path=tui_env["db_path"], config=tui_env["config"])
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.press("alt+l")
            await pilot.pause()
            assert isinstance(app.screen, ListsScreen)
            await pilot.press("enter")
            await pilot.pause()
            assert isinstance(app.screen, ListDetailScreen)
            assert app.screen.list_name == "grant-1"
            table = app.screen.query_one("#list-items-table")
            assert table.row_count == 1

            await pilot.press("x")
            await pilot.pause()
            assert table.row_count == 0
            assert tui_env["db"].get_by_id(tui_env["doc_id"]) is not None
            assert tui_env["db"].get_list_items(list_name="grant-1") == []

    _run(body())


def test_soft_delete_list_hides_from_browser(tui_env):
    async def body():
        app = ElibApp(db_path=tui_env["db_path"], config=tui_env["config"])
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.press("alt+l")
            await pilot.pause()
            await pilot.press("d")
            await pilot.pause()
            table = app.screen.query_one("#lists-table")
            assert table.row_count == 0
            assert tui_env["db"].get_paper_list(name="grant-1", include_deleted=True) is not None
            assert tui_env["db"].restore_paper_list(name="grant-1")

    _run(body())


def test_search_prefix_in_library_tui(tui_env):
    """Search 'cardio' should match 'Cardiovascular' without crashing."""

    async def body():
        app = ElibApp(db_path=tui_env["db_path"], config=tui_env["config"])
        async with app.run_test(size=(120, 40)) as pilot:
            assert isinstance(app.screen, LibraryScreen)
            await pilot.press("/")
            await pilot.pause()
            for ch in "cardio":
                await pilot.press(ch)
            await pilot.press("enter")
            await pilot.pause()
            table = app.screen.query_one("#docs-table")
            assert table.row_count >= 1
            await pilot.press("enter")
            await pilot.pause()
            assert isinstance(app.screen, DetailScreen)
            title_widget = app.screen.query_one("#detail-title")
            # Static content may be str or Visual
            content = getattr(title_widget, "_content", None) or str(title_widget.render())
            assert "Cardiovascular" in str(content)

    _run(body())


def test_tui_import_window_filters_by_added_date(tui_env):
    """Alt+i cycles import windows; today/7d/30d hide older rows."""
    db = tui_env["db"]
    pdf = tui_env["pdf"].parent / "old.pdf"
    pdf.write_bytes(b"%PDF-1.4")
    old_id = db.add_document(
        Reference(
            pmid="11111111",
            doi="10.1234/old.paper",
            title="An old imported paper",
            authors=[Author(last_name="Old", first_name="Pat", initials="P")],
            journal=Journal(title="Nature"),
            publication_date=date(2018, 1, 1),
            abstract="Old abstract.",
            keywords=[],
            mesh_terms=[],
        ),
        file_path=pdf,
        filename=pdf.name,
        file_size=pdf.stat().st_size,
        metadata_status=MetadataStatus.complete,
        metadata_source=MetadataSource.pubmed,
    )
    with db.get_connection() as conn:
        conn.execute(
            "UPDATE documents SET added_date = ? WHERE id = ?",
            ("2020-01-15 12:00:00", old_id),
        )
        conn.commit()

    async def body():
        app = ElibApp(db_path=tui_env["db_path"], config=tui_env["config"])
        async with app.run_test(size=(120, 40)) as pilot:
            assert isinstance(app.screen, LibraryScreen)
            table = app.screen.query_one("#docs-table")
            assert table.row_count == 2
            assert app.screen._import_window.value == "all"

            await pilot.press("i")  # bare i is reserved (vim); must not cycle
            await pilot.pause()
            assert app.screen._import_window.value == "all"
            assert table.row_count == 2

            await pilot.press("alt+i")  # today
            await pilot.pause()
            assert app.screen._import_window.value == "today"
            assert table.row_count == 1

            await pilot.press("alt+i")  # 7d
            await pilot.pause()
            assert app.screen._import_window.value == "7d"
            assert table.row_count == 1

            await pilot.press("escape")  # clear import window
            await pilot.pause()
            assert app.screen._import_window.value == "all"
            assert table.row_count == 2

    _run(body())


def test_tui_edit_authors_and_year(tui_env):
    """e (or Alt+e) opens the edit modal; saving updates authors and year on the record."""

    async def body():
        app = ElibApp(db_path=tui_env["db_path"], config=tui_env["config"])
        async with app.run_test(size=(120, 40)) as pilot:
            assert isinstance(app.screen, LibraryScreen)
            await pilot.press("e")
            await pilot.pause()
            assert isinstance(app.screen, EditMetadataModal)
            authors_in = app.screen.query_one("#edit-authors-input", Input)
            year_in = app.screen.query_one("#edit-year-input", Input)
            authors_in.value = "Curie, Marie"
            year_in.value = "1898"
            app.screen._save()
            await pilot.pause()
            assert isinstance(app.screen, LibraryScreen)
            meta = tui_env["db"].get_by_id(tui_env["doc_id"])
            assert meta is not None
            assert meta.publication_year == 1898
            assert "Curie" in meta.authors_json
            assert meta.metadata_source.value == "manual"
            table = app.screen.query_one("#docs-table")
            assert table.row_count >= 1

    _run(body())


def test_tui_sort_year_and_author(tui_env):
    """Alt+s / Alt+y / Alt+u sort bindings should not crash and should re-query."""

    async def body():
        app = ElibApp(db_path=tui_env["db_path"], config=tui_env["config"])
        async with app.run_test(size=(120, 40)) as pilot:
            assert isinstance(app.screen, LibraryScreen)
            await pilot.press("alt+y")  # sort by year
            await pilot.pause()
            assert app.screen._sort_by.value == "year"
            await pilot.press("alt+u")  # sort by author
            await pilot.pause()
            assert app.screen._sort_by.value == "author"
            await pilot.press("alt+s")  # cycle sort
            await pilot.pause()
            await pilot.press("alt+shift+s")  # toggle order
            await pilot.pause()
            # open lists with sort still works
            await pilot.press("alt+l")
            await pilot.pause()
            assert isinstance(app.screen, ListsScreen)
            await pilot.press("enter")
            await pilot.pause()
            assert isinstance(app.screen, ListDetailScreen)
            await pilot.press("alt+y")
            await pilot.pause()
            assert app.screen._sort_by.value == "year"

    _run(body())


def _add_paper(tui_env, *, pmid: str, title: str, year: int, last: str = "Lee") -> int:
    db = tui_env["db"]
    pdf = tui_env["pdf"].parent / f"{pmid}.pdf"
    pdf.write_bytes(b"%PDF-1.4")
    return db.add_document(
        Reference(
            pmid=pmid,
            doi=f"10.1234/{pmid}",
            title=title,
            authors=[Author(last_name=last, first_name="A", initials="A")],
            journal=Journal(title="Nature"),
            publication_date=date(year, 1, 1),
            abstract="Abstract.",
            keywords=[],
            mesh_terms=[],
        ),
        file_path=pdf,
        filename=pdf.name,
        file_size=pdf.stat().st_size,
        metadata_status=MetadataStatus.complete,
        metadata_source=MetadataSource.pubmed,
    )


def test_vim_jk_gg_on_library_table(tui_env):
    """j/k move the row cursor; G last row; gg first row. Bare l does not open lists."""
    _add_paper(tui_env, pmid="20000001", title="Paper 2019", year=2019)
    _add_paper(tui_env, pmid="20000002", title="Paper 2018", year=2018)

    async def body():
        app = ElibApp(db_path=tui_env["db_path"], config=tui_env["config"])
        async with app.run_test(size=(120, 40)) as pilot:
            assert isinstance(app.screen, LibraryScreen)
            table = app.screen.query_one("#docs-table", DataTable)
            assert table.row_count == 3
            assert table.cursor_row == 0

            await pilot.press("j")
            await pilot.pause()
            assert table.cursor_row == 1

            await pilot.press("j")
            await pilot.pause()
            assert table.cursor_row == 2

            await pilot.press("k")
            await pilot.pause()
            assert table.cursor_row == 1

            await pilot.press("G")
            await pilot.pause()
            assert table.cursor_row == 2

            await pilot.press("g")
            await pilot.press("g")
            await pilot.pause()
            assert table.cursor_row == 0

            await pilot.press("l")
            await pilot.pause()
            assert isinstance(app.screen, LibraryScreen)

    _run(body())


def test_vim_j_types_in_search(tui_env):
    """While the search box is focused, j inserts text and does not move the table."""

    async def body():
        app = ElibApp(db_path=tui_env["db_path"], config=tui_env["config"])
        async with app.run_test(size=(120, 40)) as pilot:
            assert isinstance(app.screen, LibraryScreen)
            table = app.screen.query_one("#docs-table", DataTable)
            start_row = table.cursor_row
            await pilot.press("/")
            await pilot.pause()
            await pilot.press("j")
            await pilot.pause()
            inp = app.screen.query_one("#search-input", Input)
            assert inp.value == "j"
            assert table.cursor_row == start_row
            assert isinstance(app.screen, LibraryScreen)

    _run(body())


def test_vim_jk_on_list_detail(tui_env):
    """j/k move the list-detail cursor; x still removes the selected paper."""
    extra_id = _add_paper(tui_env, pmid="30000001", title="Second list paper", year=2019)
    tui_env["db"].add_to_list(list_name="grant-1", document_id=extra_id)

    async def body():
        app = ElibApp(db_path=tui_env["db_path"], config=tui_env["config"])
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.press("alt+l")
            await pilot.pause()
            await pilot.press("enter")
            await pilot.pause()
            assert isinstance(app.screen, ListDetailScreen)
            table = app.screen.query_one("#list-items-table", DataTable)
            assert table.row_count == 2
            assert table.cursor_row == 0

            await pilot.press("j")
            await pilot.pause()
            assert table.cursor_row == 1

            await pilot.press("k")
            await pilot.pause()
            assert table.cursor_row == 0

            await pilot.press("x")
            await pilot.pause()
            assert table.row_count == 1
            assert tui_env["db"].get_by_id(tui_env["doc_id"]) is not None

    _run(body())


def test_ctrl_h_returns_home_from_lists(tui_env):
    """Ctrl+H pops nested screens back to the library table."""

    async def body():
        app = ElibApp(db_path=tui_env["db_path"], config=tui_env["config"])
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.press("alt+l")
            await pilot.pause()
            assert isinstance(app.screen, ListsScreen)
            await pilot.press("enter")
            await pilot.pause()
            assert isinstance(app.screen, ListDetailScreen)
            await pilot.press("ctrl+h")
            await pilot.pause()
            assert isinstance(app.screen, LibraryScreen)

    _run(body())


def test_ctrl_h_does_not_leave_search(tui_env):
    """Ctrl+H is ignored while the search box is focused (Backspace-safe)."""

    async def body():
        app = ElibApp(db_path=tui_env["db_path"], config=tui_env["config"])
        async with app.run_test(size=(120, 40)) as pilot:
            assert isinstance(app.screen, LibraryScreen)
            await pilot.press("/")
            await pilot.pause()
            await pilot.press("ctrl+h")
            await pilot.pause()
            assert isinstance(app.screen, LibraryScreen)
            inp = app.screen.query_one("#search-input", Input)
            assert inp.has_focus

    _run(body())


def test_ctrl_r_refreshes_library(tui_env):
    """Ctrl+R reloads the library without leaving the screen."""

    async def body():
        app = ElibApp(db_path=tui_env["db_path"], config=tui_env["config"])
        async with app.run_test(size=(120, 40)) as pilot:
            assert isinstance(app.screen, LibraryScreen)
            await pilot.press("ctrl+r")
            await pilot.pause()
            assert isinstance(app.screen, LibraryScreen)
            table = app.screen.query_one("#docs-table", DataTable)
            assert table.row_count >= 1

    _run(body())
