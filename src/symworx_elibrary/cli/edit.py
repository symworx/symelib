"""
The elib <edit> command: manually correct title, authors, and publication year.
"""

from __future__ import annotations

import typer

from symworx_elibrary.services.db_manager import DatabaseManager
from symworx_elibrary.utils.authors import (
    format_authors_editable,
    parse_authors_editable,
    validate_publication_year,
)

# ========================================================= #
# elib <edit> command                                       #
# ========================================================= #


def edit(
    ctx: typer.Context,
    doc_id: int | None = typer.Option(None, "--id", help="Document id"),
    doi: str | None = typer.Option(None, help="Document DOI"),
    author: str | None = typer.Option(
        None,
        "--author",
        help='Authors as "Last, First; Last2, First2"',
    ),
    year: int | None = typer.Option(None, "--year", help="Publication year (YYYY)"),
    title: str | None = typer.Option(None, "--title", help="Document title"),
    clear_year: bool = typer.Option(False, "--clear-year", help="Clear publication year"),
):
    """
    Manually edit title, authors, and/or publication year on a library record.

    Does not rename the PDF on disk. Marks metadata_source as ``manual``.

    Examples:

        elib edit --id 42
        elib edit --id 42 --title "Corrected title" --year 2021
        elib edit --id 42 --author "Smith, Ada; Jones, Bob" --year 2021
        elib edit --doi 10.1038/nature12373 --year 2012
        elib edit --id 42 --clear-year
    """
    if doc_id is None and not doi:
        typer.echo("Provide --id or --doi", err=True)
        raise typer.Exit(code=1)
    if year is not None and clear_year:
        typer.echo("Use --year or --clear-year, not both", err=True)
        raise typer.Exit(code=1)

    db = DatabaseManager(ctx.obj["config"].database_path)
    if doc_id is not None:
        doc = db.get_by_id(doc_id)
    else:
        doc = db.get_by_doi(doi)  # type: ignore[arg-type]
    if doc is None or doc.id is None:
        typer.echo("Document not found.", err=True)
        raise typer.Exit(code=1)

    typer.echo(f"[{doc.id}] {doc.title[:80]}")
    typer.echo(f"  authors: {format_authors_editable(doc.authors_json) or '—'}")
    typer.echo(f"  year:    {doc.publication_year or '—'}")
    typer.echo(
        f"  source:  {doc.metadata_source.value if doc.metadata_source else '—'}  "
        f"status={doc.metadata_status.value}"
    )

    mutating = author is not None or year is not None or clear_year or title is not None
    if not mutating:
        typer.echo("")
        typer.echo('Pass --title, --author "Last, First", and/or --year YYYY to update.')
        return

    authors = None
    if author is not None:
        try:
            authors = parse_authors_editable(author)
        except ValueError as e:
            typer.echo(f"Error: {e}", err=True)
            raise typer.Exit(code=1) from e

    pub_year = None
    if year is not None:
        try:
            pub_year = validate_publication_year(year)
        except ValueError as e:
            typer.echo(f"Error: {e}", err=True)
            raise typer.Exit(code=1) from e

    try:
        updated = db.update_document_fields(
            doc.id,
            authors=authors,
            publication_year=pub_year,
            clear_year=clear_year,
            title=title,
        )
    except ValueError as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(code=1) from e

    if updated is None:
        typer.echo("Update failed.", err=True)
        raise typer.Exit(code=1)

    typer.echo("")
    typer.echo("Updated:")
    typer.echo(f"  title:   {updated.title[:80]}")
    typer.echo(f"  authors: {format_authors_editable(updated.authors_json) or '—'}")
    typer.echo(f"  year:    {updated.publication_year or '—'}")
    typer.echo(f"  source:  {updated.metadata_source.value if updated.metadata_source else '—'}")
