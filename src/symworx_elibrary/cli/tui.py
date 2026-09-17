"""
The elib <tui> command: interactive Textual browser for the library.
"""

from __future__ import annotations

import typer


def tui(ctx: typer.Context) -> None:
    """
    Open the interactive TUI to browse, search, read abstracts, and manage lists.

    Keys: j/k move · / search · o PDF · e edit · Alt+l lists · Ctrl+H home · Ctrl+R refresh
    Help: Alt+?   Quit: Esc Esc (at library root) or Ctrl+Q
    """
    config = ctx.obj["config"]
    try:
        from symworx_elibrary.tui.app import run_tui
    except ImportError as e:
        typer.echo(
            f"Textual is required for the TUI. Install with: uv sync\nImport error: {e}",
            err=True,
        )
        raise typer.Exit(code=1) from e

    run_tui(config.database_path, config=config)
