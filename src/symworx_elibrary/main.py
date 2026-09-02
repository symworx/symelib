"""
src/symworx_elibrary/main.py

The entry point for the elib CLI application.
"""

from __future__ import annotations

import typer

from symworx_elibrary.cli.add import add
from symworx_elibrary.cli.agent import agent
from symworx_elibrary.cli.check_metadata import check_metadata
from symworx_elibrary.cli.edit import edit
from symworx_elibrary.cli.enrich import enrich
from symworx_elibrary.cli.list_cmd import list_app
from symworx_elibrary.cli.process import process
from symworx_elibrary.cli.rebuild_index import rebuild_index
from symworx_elibrary.cli.search import search
from symworx_elibrary.cli.setup_cmd import setup
from symworx_elibrary.cli.stats import stats
from symworx_elibrary.cli.tui import tui
from symworx_elibrary.utils.logging import LogLevel, initialize_logger

# ========================================================= #
# elib CLI Application                                      #
# ========================================================= #

app = typer.Typer(help="elib - Electronic Library Management System")
app.command(name="setup")(setup)
app.command(name="stats")(stats)
app.command(name="search")(search)
app.command(name="process")(process)
app.command(name="rebuild-index")(rebuild_index)
app.command(name="check-metadata")(check_metadata)
app.command(name="enrich")(enrich)
app.command(name="edit")(edit)
app.command(name="add")(add)
app.add_typer(list_app, name="list")
app.command(name="tui")(tui)
app.command(name="agent")(agent)


# ========================================================= #
# Global CLI Options                                        #
# ========================================================= #
#
@app.callback()
def main(
    ctx: typer.Context,
    verbose: int = typer.Option(0, "--verbose", "-v", help="Increase verbosity"),
    quiet: bool = typer.Option(True, "--quiet", "-q", help="Quiet mode"),
    log_level: LogLevel | None = typer.Option(None, "--log-level", help="Set log level"),
):
    """
    Global CLI options (verbosity, quiet, log level).
    """
    # Default log level
    log_level = log_level or LogLevel.INFO

    # Initialize logger + config
    config, logger = initialize_logger(verbose=verbose, quiet=quiet, log_level=log_level)

    # Attach to context so subcommands can use it
    ctx.obj = {"config": config, "logger": logger}


def runner():
    """
    Entrypoint for pyproject.toml
    """
    app()


if __name__ == "__main__":
    runner()
