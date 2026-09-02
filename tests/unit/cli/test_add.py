"""tests/unit/cli/test_add.py — argument gates for elib add"""

from pathlib import Path
from types import SimpleNamespace

import pytest
from typer.testing import CliRunner

from symworx_elibrary.main import app
from symworx_elibrary.utils.config import Config

runner = CliRunner()


def _cfg(tmp_path: Path) -> Config:
    return Config(
        ncbi_email="test@example.com",
        database_path=tmp_path / "data" / "elib.db",
        target_directory=tmp_path / "library",
        cart_directory=tmp_path / "cart",
        temp_directory=tmp_path / "tmp",
        exports_directory=tmp_path / "exports",
    )


def test_add_requires_identifier_or_title():
    result = runner.invoke(app, ["add"])
    assert result.exit_code == 1
    assert "DOI/URL/PMID or --title" in (result.output or "") + (result.stderr or "")


def test_add_manual_inserts(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    cfg = _cfg(tmp_path)
    cfg.database_path.parent.mkdir(parents=True, exist_ok=True)

    def fake_init(verbose=0, quiet=True, log_level=None):
        return cfg, SimpleNamespace()

    monkeypatch.setattr("symworx_elibrary.main.initialize_logger", fake_init)

    result = runner.invoke(
        app,
        [
            "add",
            "--title",
            "Manual Paper",
            "--author",
            "Smith, Ada",
            "--year",
            "2024",
            "--journal",
            "Test Journal",
        ],
    )
    assert result.exit_code == 0, result.output
    assert "Manual Paper" in result.output
    assert "citation only" in result.output.lower()
