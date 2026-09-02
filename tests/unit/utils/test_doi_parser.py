"""
tests/unit/utils/test_doi_parser.py
"""

from symworx_elibrary.utils.doi_parser import (
    extract_doi_from_text,
    extract_pmid_from_text,
    normalize_doi,
)


def test_normalize_doi_basic():
    assert normalize_doi("10.1038/nature12373") == "10.1038/nature12373"


def test_normalize_doi_url():
    assert normalize_doi("https://doi.org/10.1038/nature12373") == "10.1038/nature12373"
    assert normalize_doi("http://dx.doi.org/10.1038/nature12373") == "10.1038/nature12373"


def test_normalize_doi_publisher_url():
    url = "https://www.tandfonline.com/doi/full/10.1080/10447318.2024.2383033"
    assert normalize_doi(url) == "10.1080/10447318.2024.2383033"
    assert extract_doi_from_text(url) == "10.1080/10447318.2024.2383033"


def test_normalize_doi_prefix_and_punct():
    assert normalize_doi("doi:10.1038/nature12373.") == "10.1038/nature12373"
    assert normalize_doi("DOI: 10.1038/nature12373,") == "10.1038/nature12373"


def test_normalize_doi_invalid():
    assert normalize_doi(None) is None
    assert normalize_doi("") is None
    assert normalize_doi("not-a-doi") is None


def test_extract_doi_from_text():
    text = "See https://doi.org/10.1000/182 for details. Also PMID: 12345678."
    assert extract_doi_from_text(text) == "10.1000/182"


def test_extract_pmid_from_text():
    assert extract_pmid_from_text("PMID: 32848250") == "32848250"
    assert extract_pmid_from_text("PubMed ID: 12345") == "12345"
    assert extract_pmid_from_text("no id here") is None


def test_extract_pmid_from_filename():
    from symworx_elibrary.utils.doi_parser import extract_pmid_from_filename

    assert extract_pmid_from_filename("[15432688 - Journal of Applied Bio.pdf") == "15432688"
    assert (
        extract_pmid_from_filename("%5B15432688%20-%20Journal%20of%20Applied%20Bio.pdf")
        == "15432688"
    )
    assert (
        extract_pmid_from_filename("Unknown_NODATE_5B154326882020Journal20of20Applied2")
        == "15432688"
    )
