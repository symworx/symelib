"""
The elib <add> command: add a citation-only record (DOI/URL lookup or manual).
"""

from __future__ import annotations

import typer

from symworx_elibrary.services.citation_add import (
    CitationDraft,
    CitationLookupError,
    DuplicateCitationError,
    add_citation,
)
from symworx_elibrary.services.crossref_client import CrossrefClient
from symworx_elibrary.services.db_manager import DatabaseManager
from symworx_elibrary.services.metadata_enricher import MetadataEnricher
from symworx_elibrary.services.ncbi_client import NCBIClient
from symworx_elibrary.utils.authors import (
    format_authors_editable,
    parse_authors_editable,
    validate_publication_year,
)

# ========================================================= #
# elib <add> command                                        #
# ========================================================= #


def add(
    ctx: typer.Context,
    identifier: str | None = typer.Argument(
        None,
        help="DOI, publisher URL, doi.org URL, or PMID",
    ),
    title: str | None = typer.Option(None, "--title", help="Document title"),
    author: str | None = typer.Option(
        None,
        "--author",
        help='Authors as "Last, First; Last2, First2"',
    ),
    year: int | None = typer.Option(None, "--year", help="Publication year (YYYY)"),
    journal: str | None = typer.Option(None, "--journal", help="Journal title"),
    doi: str | None = typer.Option(None, "--doi", help="DOI (if not in identifier)"),
    pmid: str | None = typer.Option(None, "--pmid", help="PubMed ID"),
):
    """
    Add a citation-only library record (no PDF).

    Paste a DOI or article URL to populate from PubMed then Crossref, or
    pass ``--title`` / ``--author`` / ``--year`` to enter the citation by hand.

    Examples:

        elib add 10.1080/10447318.2024.2383033
        elib add https://www.tandfonline.com/doi/full/10.1080/10447318.2024.2383033
        elib add --title "Paper title" --author "Smith, Ada" --year 2024
    """
    if not (identifier or doi or pmid or title):
        typer.echo("Provide a DOI/URL/PMID or --title", err=True)
        raise typer.Exit(code=1)

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

    config = ctx.obj["config"]
    db = DatabaseManager(config.database_path)
    ncbi = NCBIClient(email=config.ncbi_email, api_key=config.ncbi_api_key)
    crossref = CrossrefClient(mailto=config.ncbi_email)
    enricher = MetadataEnricher(ncbi_client=ncbi, crossref_client=crossref, db_manager=db)

    draft = CitationDraft(
        identifier=identifier,
        title=title,
        authors=authors,
        year=pub_year,
        journal=journal,
        doi=doi,
        pmid=pmid,
    )
    try:
        meta = add_citation(db, draft, enricher=enricher)
    except DuplicateCitationError as e:
        typer.echo(str(e), err=True)
        raise typer.Exit(code=1) from e
    except CitationLookupError as e:
        typer.echo(str(e), err=True)
        raise typer.Exit(code=1) from e
    except ValueError as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(code=1) from e

    source = meta.metadata_source.value if meta.metadata_source else "—"
    typer.echo(f"[{meta.id}] {meta.title[:80]}")
    typer.echo(f"  authors: {format_authors_editable(meta.authors_json) or '—'}")
    typer.echo(f"  year:    {meta.publication_year or '—'}")
    typer.echo(f"  journal: {meta.journal or '—'}")
    typer.echo(f"  doi:     {meta.doi or '—'}")
    typer.echo(f"  source:  {source}  status={meta.metadata_status.value}")
    typer.echo("  (citation only — no PDF)")
