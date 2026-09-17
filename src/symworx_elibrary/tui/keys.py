"""Shared TUI key bindings and vim-style motion.

Layering (aligned with SymView):
- Bare letters: vim motion plus a few high-frequency local verbs (``o`` PDF, ``e`` edit).
- Ctrl: globals that must work in any pane (quit, home, refresh).
- Alt: remaining mnemonics, plus ``Alt+?`` help.
- No ``priority`` on vim letters or ``o``/``e`` — an ``Input`` still types them.
"""

from __future__ import annotations

from textual.binding import Binding
from textual.widgets import DataTable, Input

GG_TIMEOUT_S = 0.8

# --- fragments screens compose into BINDINGS ---

VIM_MOTION = (
    Binding("j", "vim_down", "Down", show=False),
    Binding("k", "vim_up", "Up", show=False),
    Binding("h", "vim_left", "Left", show=False),
    Binding("l", "vim_right", "Right", show=False),
    Binding("g", "vim_g", "Top", show=False),
    Binding("G", "vim_bottom", "Bottom", show=False),
)

QUIT = (Binding("ctrl+q", "quit", "Quit", show=True, priority=True, key_display="Ctrl+Q"),)

QUIT_SCREEN = (
    Binding("ctrl+q", "app.quit", "Quit", show=True, priority=True, key_display="Ctrl+Q"),
)

# No priority: Ctrl+H is Backspace on many PTYs; Input must keep delete-left.
HOME = (Binding("ctrl+h", "go_home", "Home", show=True, key_display="Ctrl+H"),)

REFRESH = (
    Binding("ctrl+r", "refresh_view", "Refresh", show=True, priority=True, key_display="Ctrl+R"),
    Binding("f5", "refresh_view", "Refresh", show=False),
)

HELP = (
    Binding("alt+question_mark", "help", "Help", show=True, priority=True, key_display="Alt+?"),
    Binding("question_mark", "help", "Help", show=False),
)

THEME = (Binding("alt+t", "toggle_theme", "Theme", show=True, key_display="Alt+T"),)

ALT_LISTS = (
    Binding("alt+l", "open_lists", "Lists", show=True, priority=True, key_display="Alt+L"),
)

OPEN_PDF = (
    Binding("o", "open_pdf", "PDF", show=True),
    Binding("alt+o", "open_pdf", "PDF", show=False, priority=True, key_display="Alt+O"),
)

EDIT = (Binding("e", "edit_metadata", "Edit", show=True),)

# Library/detail only — list-detail uses Alt+E for BibTeX export.
EDIT_ALT = (
    Binding("alt+e", "edit_metadata", "Edit", show=False, priority=True, key_display="Alt+E"),
)

ALT_ADD_TO_LIST = (
    Binding("alt+a", "add_to_list", "List+", show=True, priority=True, key_display="Alt+A"),
)

ALT_FIELD = (
    Binding("alt+f", "cycle_field", "Field", show=True, priority=True, key_display="Alt+F"),
    Binding("ctrl+f", "cycle_field", "Field", show=False, priority=True, key_display="Ctrl+F"),
)

ALT_IMPORT = (
    Binding(
        "alt+i",
        "cycle_import_window",
        "Imported",
        show=True,
        priority=True,
        key_display="Alt+I",
    ),
)

ALT_SORT = (Binding("alt+s", "cycle_sort", "Sort", show=True, priority=True, key_display="Alt+S"),)

ALT_SORT_ORDER = (
    Binding(
        "alt+shift+s",
        "toggle_sort_order",
        "Order",
        show=True,
        priority=True,
        key_display="Alt+Shift+S",
    ),
)

ALT_SORT_YEAR = (Binding("alt+y", "sort_year", "Year", show=False, priority=True),)

ALT_SORT_AUTHOR = (Binding("alt+u", "sort_author", "Author", show=False, priority=True),)

ALT_NEW_LIST = (Binding("alt+n", "new_list", "New", show=True, priority=True, key_display="Alt+N"),)

ALT_RENAME_LIST = (
    Binding("alt+m", "rename_list", "Rename", show=True, priority=True, key_display="Alt+M"),
)

ALT_EXPORT = (
    Binding("alt+e", "export_list", "Export", show=True, priority=True, key_display="Alt+E"),
)

ALT_EXPORT_DETAIL = (
    Binding("alt+e", "export", "Export", show=True, priority=True, key_display="Alt+E"),
)


class VimMotionMixin:
    """Dispatch h/j/k/l and gg/G to the focused table or scrollable."""

    def _motion_widget(self) -> object | None:
        focused = getattr(self, "focused", None)
        if isinstance(focused, Input):
            return None
        if isinstance(focused, DataTable):
            return focused
        if focused is not None and hasattr(focused, "action_scroll_down"):
            return focused
        query_one = getattr(self, "query_one", None)
        if query_one is None:
            return None
        try:
            return query_one(DataTable)
        except Exception:
            return None

    def _clear_gg(self) -> None:
        app = getattr(self, "app", None)
        clear = getattr(app, "clear_gg", None)
        if callable(clear):
            clear()

    def action_vim_down(self) -> None:
        self._clear_gg()
        widget = self._motion_widget()
        if widget is None:
            return
        if isinstance(widget, DataTable):
            widget.action_cursor_down()
        else:
            widget.action_scroll_down()

    def action_vim_up(self) -> None:
        self._clear_gg()
        widget = self._motion_widget()
        if widget is None:
            return
        if isinstance(widget, DataTable):
            widget.action_cursor_up()
        else:
            widget.action_scroll_up()

    def action_vim_left(self) -> None:
        self._clear_gg()
        widget = self._motion_widget()
        if widget is None:
            return
        if isinstance(widget, DataTable):
            widget.action_cursor_left()
        else:
            widget.action_scroll_left()

    def action_vim_right(self) -> None:
        self._clear_gg()
        widget = self._motion_widget()
        if widget is None:
            return
        if isinstance(widget, DataTable):
            widget.action_cursor_right()
        else:
            widget.action_scroll_right()

    def action_vim_g(self) -> None:
        app = getattr(self, "app", None)
        if app is not None and getattr(app, "gg_pending", False):
            app.clear_gg()
            self._go_top()
            return
        if app is not None and hasattr(app, "arm_gg"):
            app.arm_gg()

    def action_vim_bottom(self) -> None:
        self._clear_gg()
        self._go_bottom()

    def _go_top(self) -> None:
        widget = self._motion_widget()
        if widget is None:
            return
        if isinstance(widget, DataTable):
            widget.action_scroll_top()
        elif hasattr(widget, "action_scroll_home"):
            widget.action_scroll_home()

    def _go_bottom(self) -> None:
        widget = self._motion_widget()
        if widget is None:
            return
        if isinstance(widget, DataTable):
            if widget.row_count == 0:
                return
            widget.action_scroll_bottom()
        elif hasattr(widget, "action_scroll_end"):
            widget.action_scroll_end()
