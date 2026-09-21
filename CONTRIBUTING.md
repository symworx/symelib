# Contributing to elib

Thank you for your interest in contributing to **elib**!
We welcome contributions of all kinds—whether it's fixing a typo, improving documentation, reporting bugs, or implementing new features.

## Our Philosophy

elib is a **local-first** paper (PDF) library with honest metadata sourcing and optional agentic tooling. Contributions should align with:

- **Local-first & privacy** — library data and keys stay on the user’s machine; no telemetry by default.
- **Honest metadata** — prefer PubMed → Crossref → clear local fallback; track quality (`complete` / `partial` / `fallback` / `pending`) rather than inventing fields.
- **Modular design** — core path is SQLite + CLI/TUI; agents/Postgres/pgvector remain optional extras.
- **Safe defaults** — rate limits, no secret commits, toolbox/host quirks documented when they matter.

See [AGENTS.md](AGENTS.md) for the longer-term agent vision, [docs/PUBLIC_RELEASE.md](docs/PUBLIC_RELEASE.md) for public-repo safety scope, and [docs/RELEASING.md](docs/RELEASING.md) for the SymWorx-style release branch/tag workflow.

## AI-Assisted Contributions

Feel free to use AI tools (such as Grok, Claude, Copilot, etc.) to assist your work. We do not regulate how you use AI, but all contributors must:

1. Be able to clearly explain the changes and reasoning behind them.
2. Ensure the contribution meets elib standards for quality, privacy, and style.
3. Take full ownership of the submitted code.

AI should be treated as a helpful collaborator — **you** remain responsible for the final result.

## Ways to Contribute

- **Submit an Issue** – Report bugs, request features, or suggest improvements.
- **Submit a Pull Request (PR)** – From small documentation fixes to major new functionality.
- **Improve Documentation** – Keep [README.md](README.md), [QUICKSTART.md](QUICKSTART.md), and setup flows accurate.
- **Write Tests** – Strengthen coverage for models, DB, search, enrichers, and TUI behavior.
- **Review Pull Requests** – Provide constructive feedback to help maintain quality.

If you see something that needs fixing, feel free to open a PR directly—no need to wait for an issue to be assigned.

## Getting Started

1. **Fork the repository** and clone your fork.
2. **Create a branch** for your work (`git checkout -b feature/your-feature-name`).
3. **Set up the environment** (Python ≥ 3.13, [uv](https://docs.astral.sh/uv/)):

   ```bash
   cd elib
   make sync                 # or: uv sync --all-extras
   make install-cli          # optional: elib on PATH via uv tool
   # Optional interactive NCBI + paths:
   make setup                # or: elib setup
   source ~/.config/elib/env # if setup wrote env exports
   ```

4. **Install pre-commit hooks** (once per clone):

   ```bash
   make pre-commit-install   # ruff format + lint on each git commit
   ```

5. **Make changes**, following the standards below.
6. **Run checks** before opening a PR:

   ```bash
   make check                # ruff check + format --check + pytest
   make pre-commit-run       # same hooks as commit, on all files
   # Or separately:
   make lint
   make format
   make test
   ```

7. **Commit** with clear, descriptive messages; push and open a Pull Request to **`worx`**.

   GitHub Actions `CI` runs on `worx` and `develop` (jobs `fmt` and `check`).
   Release validation (`release.yml`) runs on pushes to `release/**` and tags
   `v*` (legacy freeze PRs into `main` still run it). See
   [docs/RELEASING.md](docs/RELEASING.md).

   Until GitHub renames the default branch, PRs still target **`develop`**.

   Hooks auto-fix formatting when possible; re-stage and commit again if they modify files.
   Emergency skip (rare): `git commit --no-verify`.

Runtime layout for day-to-day use (tmp then cart → library → SQLite) is documented in [QUICKSTART.md](QUICKSTART.md). Core flows do **not** require Postgres; `make db-up` is only for the optional agents/RAG path.

## Project layout (where to work)

| Area | Path | Notes |
|------|------|--------|
| CLI entrypoints | `src/symworx_elibrary/cli/` | Typer commands wired from `main.py` |
| Models | `src/symworx_elibrary/models/` | Documents, metadata status, paper lists |
| Services | `src/symworx_elibrary/services/` | NCBI, Crossref, PDF process, enrich, BibTeX |
| SQLite layer | `src/symworx_elibrary/services/db/` | Schema, documents, lists; facade via `db_manager` |
| TUI | `src/symworx_elibrary/tui/` | Textual app + screens + `elib.tcss` |
| Config / utils | `src/symworx_elibrary/utils/` | Config, rate limits, open PDF, search query |
| Tests | `tests/unit/`, `tests/functional/` | Prefer unit tests for logic; functional for TUI flows |
| Optional agents | `src/symworx_elibrary/agents/`, `migrations/`, `compose.yaml` | Postgres + pgvector extras |

User data and secrets live **outside** the repo (typically `~/elibrary/` and `~/.config/elib/env`). Never commit PDFs, SQLite DBs, API keys, or personal `config.yaml` with real credentials.

## Coding standards

- **Python 3.13+**, type hints on public APIs, Pydantic models for structured data.
- **Lint/format** with Ruff (`ruff.toml`); keep `make check` green. Prefer `make pre-commit-install` so commits stay formatted.
- **Tests** for new behavior (DB, search, enrich, open-file helpers, list ops). Mock network (NCBI/Crossref) in unit tests.
- **Rate limits** — respect NCBI etiquette (email required; API key optional for higher throughput; backoff on 429). Do not introduce aggressive default polling.
- **TUI** — preserve selection/search state across refresh where practical; avoid naming methods `refresh` on screens (Textual owns that).
- **Secrets** — config examples only; see [docs/PUBLIC_RELEASE.md](docs/PUBLIC_RELEASE.md).

## Submitting Pull Requests

- **Keep PRs focused** — one logical change per PR is strongly preferred; larger refactors should be called out clearly.
- **Include tests** when adding or modifying functionality.
- **Update documentation** when behavior or setup changes (README / QUICKSTART / help text).
- **Follow the Code of Conduct** in all interactions.
- Be prepared to address review feedback and iterate until the PR is ready to merge.

We ask that you stay engaged with your PR—respond to comments and keep the conversation moving so we can merge high-quality contributions quickly.

### Suggested PR checklist

- [ ] `make check` passes
- [ ] No secrets, personal emails, or library PDFs in the diff
- [ ] Docs updated if user-facing behavior changed
- [ ] Network-touching code has tests or clear manual steps

## Code of Conduct

This project follows the [Contributor Covenant Code of Conduct](https://www.contributor-covenant.org/version/2/1/code_of_conduct/).
By participating, you agree to uphold this code in all project spaces.

## Questions or Need Help?

- Open an **Issue** or **Discussion** in the repository.
- For local setup friction (toolbox, PATH, NCBI), start from [QUICKSTART.md](QUICKSTART.md) and `elib setup`.

---

**Thank you for helping make elib better!**
Your contributions support a private, reliable literature workflow for research—and a solid base for optional agentic features later.
