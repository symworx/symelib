"""tests/unit/utils/test_citation.py"""

from pathlib import Path

from symworx_elibrary.utils.citation import (
    CITATION_PATH_PREFIX,
    citation_file_path,
    has_local_pdf,
    is_citation_path,
    parse_article_identifier,
)

TF_URL = "https://www.tandfonline.com/doi/full/10.1080/10447318.2024.2383033"
TF_DOI = "10.1080/10447318.2024.2383033"


def test_parse_bare_doi():
    ident = parse_article_identifier(TF_DOI)
    assert ident.doi == TF_DOI
    assert ident.pmid is None
    assert ident.has_id()


def test_parse_doi_org_url():
    ident = parse_article_identifier(f"https://doi.org/{TF_DOI}")
    assert ident.doi == TF_DOI


def test_parse_tandfonline_url():
    ident = parse_article_identifier(TF_URL)
    assert ident.doi == TF_DOI


def test_parse_bare_pmid():
    ident = parse_article_identifier("32848250")
    assert ident.pmid == "32848250"
    assert ident.doi is None


def test_parse_pmid_label():
    ident = parse_article_identifier("PMID: 32848250")
    assert ident.pmid == "32848250"


def test_parse_empty():
    ident = parse_article_identifier("  ")
    assert not ident.has_id()
    assert ident.doi is None
    assert ident.pmid is None


def test_citation_file_path_encodes_doi_slash():
    path = citation_file_path(TF_DOI)
    assert path.startswith(CITATION_PATH_PREFIX)
    assert "/" not in path
    assert "10.1080" in path
    assert is_citation_path(path)
    # POSIX Path must not split the DOI suffix into parents
    assert Path(path).name == path


def test_citation_file_path_local_is_unique():
    a = citation_file_path(None)
    b = citation_file_path("")
    assert a != b
    assert is_citation_path(a) and is_citation_path(b)
    assert "local:" in a


def test_has_local_pdf(tmp_path: Path):
    pdf = tmp_path / "paper.pdf"
    pdf.write_bytes(b"%PDF")
    assert has_local_pdf(pdf)
    assert not has_local_pdf(citation_file_path(TF_DOI))
    assert not has_local_pdf(None)
    assert not has_local_pdf(tmp_path / "missing.pdf")
