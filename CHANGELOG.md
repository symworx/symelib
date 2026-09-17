# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Changed
- Copyright holder set to Nathaniel T. Berry
- TUI keys layered like SymView: vim motion (`h/j/k/l`, `gg`/`G`); local verbs `o` PDF and `e` edit; Ctrl globals (`Ctrl+Q` quit, `Ctrl+H` home to library, `Ctrl+R` / `F5` refresh); Alt mnemonics (`Alt+L` lists, `Alt+I` imported, `Alt+A` add-to-list, `Alt+S` sort, `Alt+T` theme, `Alt+?` help). `/` search, `x`/`d` delete-ish, `Esc Esc` quit unchanged. `Alt+O` / `Alt+E` remain aliases while typing in search.

### Removed
- TUI `Ctrl+I` alias for the import-date window (it is Tab on many terminals). Use `Alt+I`.

## [0.2.0] - 2026-08-29

### Added
- `elib process` default inbox sequence: `~/elibrary/tmp` then `~/elibrary/cart` (`--from tmp|cart|all`).
- Filter by import date: `elib search --added-from/--added-to/--added-since`; TUI `i` cycles all/today/7d/30d.
- Manual author/year edits: `elib edit --id/--doi --author --year`; TUI `e` (marks `metadata_source=manual`).

### Changed
- CI matches the family cadence: `ci.yml` on `develop` only; `release.yml` on PRs to `main`, `release/**`, and tags `v*` (GitHub Release on tags; PyPI paused).

## [0.1.0] - 2026-07-30

### Added
- Initial public-oriented release of elib (local-first PDF library + PubMed integration + TUI).
- Textual TUI: library search, detail, named paper lists, PDF open (Papers / configurable viewer).
- Metadata pipeline: PubMed primary → Crossref fallback → honest local status tracking.
- Paper lists: create, rename, soft-delete/restore, BibTeX export (`elib list`, TUI `l` / `m`).
- `elib setup` + `config.example.yaml`; library layout under `$ELIB_HOME` (cart, library, data, exports, tmp).
- Rate limiting / 429 backoff for NCBI and Crossref; optional API key via env.
- Pre-commit hooks (ruff format + import sort); CONTRIBUTING.md.
- Optional agents/RAG path (Postgres + pgvector via `compose.yaml`) — not required for core use.

### Changed
- Config defaults scrubbed for public use (no personal email/bucket in repo template).
- Compose file renamed to `compose.yaml`; Postgres bound to `127.0.0.1`.

### Security
- Prefer NCBI API key in `~/.config/elib/env` (mode 600), not in bisynced `config.yaml`.
- Tracked secrets removed from example config; `config.yaml` gitignored.

---

## Version Links

[Unreleased]: https://github.com/csymd/symelib/compare/v0.2.0...HEAD
[0.2.0]: https://github.com/csymd/symelib/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/csymd/symelib/releases/tag/v0.1.0
