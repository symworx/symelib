"""
elib Textual application entry.

Design notes (mirrors symworx SymView chrome):
  - Cyan accents on dark surface (see elib.tcss)
  - Light beige theme toggle with Alt+T
  - Esc Esc at root to quit; Ctrl+Q anytime
  - Vim motion (hjkl, gg/G) when not typing in an Input
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import TYPE_CHECKING

from textual.app import App
from textual.widgets import Input

from symworx_elibrary.services.db_manager import DatabaseManager
from symworx_elibrary.tui.keys import GG_TIMEOUT_S, HELP, HOME, QUIT, REFRESH, THEME
from symworx_elibrary.tui.screens.library import LibraryScreen
from symworx_elibrary.utils.config import Config
from symworx_elibrary.utils.open_file import open_path

if TYPE_CHECKING:
    from textual.timer import Timer


class ElibApp(App[None]):
    """Interactive browser for the local paper library."""

    TITLE = "elib"
    SUB_TITLE = "paper library"
    CSS_PATH = "elib.tcss"

    BINDINGS = [
        *QUIT,
        *HOME,
        *REFRESH,
        *HELP,
        *THEME,
    ]

    def __init__(self, db_path: Path, config: Config | None = None, **kwargs):
        super().__init__(**kwargs)
        self.db_path = Path(db_path)
        self.db = DatabaseManager(self.db_path)
        self.config = config or Config.load()
        self.esc_quit_pending: bool = False
        self.gg_pending: bool = False
        self._gg_timer: Timer | None = None
        self.light_theme: bool = False

    def on_mount(self) -> None:
        self.push_screen(LibraryScreen())

    def clear_gg(self) -> None:
        self.gg_pending = False
        if self._gg_timer is not None:
            self._gg_timer.stop()
            self._gg_timer = None

    def arm_gg(self) -> None:
        """First ``g``: wait for a second ``g`` to jump to top."""
        self.esc_quit_pending = False
        self.clear_gg()
        self.gg_pending = True
        self._gg_timer = self.set_timer(GG_TIMEOUT_S, self.clear_gg)

    def clear_esc_quit(self) -> None:
        self.esc_quit_pending = False
        self.clear_gg()

    def arm_esc_quit(self) -> None:
        self.clear_gg()
        self.esc_quit_pending = True
        self.notify("Esc again to quit  ·  Ctrl+Q anytime", timeout=3)

    def handle_root_escape(self) -> bool:
        if self.esc_quit_pending:
            self.exit()
            return True
        self.arm_esc_quit()
        return True

    def set_action_bar(self, text: str) -> None:
        try:
            screen = self.screen
            bar = screen.query_one("#action-bar")
            bar.update(f"  {text}")  # type: ignore[union-attr]
        except Exception:
            pass

    def action_go_home(self) -> None:
        """Pop back to the library table (SymView Ctrl+H). No-op while typing."""
        if isinstance(self.focused, Input):
            return
        self.clear_esc_quit()
        while not isinstance(self.screen, LibraryScreen) and len(self.screen_stack) > 1:
            self.pop_screen()
        if isinstance(self.screen, LibraryScreen):
            try:
                self.screen.focus_results()
            except Exception:
                pass

    def action_refresh_view(self) -> None:
        """Reload the current pane from SQLite (Ctrl+R / F5)."""
        self.clear_esc_quit()
        screen = self.screen
        refresh = getattr(screen, "action_refresh", None)
        if callable(refresh):
            refresh()
            return
        self.reload_db()
        load = getattr(screen, "_load", None)
        if callable(load):
            load()
        self.notify("Refreshed", timeout=2)

    def action_toggle_theme(self) -> None:
        """Switch between dark cyan and light beige themes."""
        self.light_theme = not self.light_theme
        self.set_class(self.light_theme, "theme-light")
        label = "light/beige" if self.light_theme else "dark"
        self.notify(f"Theme: {label}", timeout=2)

    def reload_db(self) -> None:
        """Re-open SQLite connection layer (picks up imports from other processes)."""
        self.db = DatabaseManager(self.db_path)

    def open_pdf(self, file_path: str | Path) -> tuple[bool, str]:
        """Open PDF using current config/env viewer preference (reload config each time)."""
        # Pick up pdf_viewer changes without restarting the TUI
        try:
            self.config = Config.load()
        except Exception:
            pass
        viewer = self.config.pdf_viewer or os.environ.get("ELIB_PDF_VIEWER")
        return open_path(file_path, preferred_viewer=viewer)

    def action_help(self) -> None:
        self.notify(
            "j/k move · h/l · gg/G · / search · o PDF · e edit · "
            "Alt+? help · Ctrl+H home · Ctrl+R refresh · Alt+l lists · "
            "Alt+i imported · Alt+a list · Alt+s sort · Alt+t theme · Esc Esc / Ctrl+Q quit",
            title="Keys",
            timeout=10,
        )


def run_tui(db_path: Path, config: Config | None = None) -> None:
    """Launch the Textual TUI (blocking)."""
    app = ElibApp(db_path=db_path, config=config)
    app.run()
