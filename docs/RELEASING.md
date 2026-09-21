# Releasing elib

Release process for elib. **SymWorx org standard** (GitHub Flow:
`feature/*` → `worx` → tag `vX.Y.Z`), adapted for a **single Python
package** (`pyproject.toml` version).

See also: [PUBLIC_RELEASE.md](PUBLIC_RELEASE.md) (security scrub before first public push).

---

## Branch model

| Branch | Purpose |
|--------|---------|
| `worx` | Default. Feature PRs land here. Keep it releasable. |
| `release/vX.Y.Z` | Optional freeze: version bump, changelog, last-minute fixes. |

```text
feature/*  ──PR──►  worx  ──tag──►  vX.Y.Z
```

**Pre-releases** (e.g. `v0.1.0-rc.1`) are tags on `worx` (GitHub pre-release).
**Final releases** are tagged on `worx`.

Until GitHub finishes renaming `develop` → `worx`, open PRs against the GitHub default (`develop`).

---

## Versioning

- **SemVer** in `pyproject.toml` → `[project].version` (single source of truth).
- Git tags: `vX.Y.Z` (must match `pyproject.toml` without the leading `v`).
- Pre-release forms: `0.1.0-beta.1`, `0.1.0-rc.1` ↔ tags `v0.1.0-beta.1`, `v0.1.0-rc.1`.
- Keep a Changelog: root [`CHANGELOG.md`](../CHANGELOG.md).

Release metadata checks (when CI is enabled) should assert:

- Tag / optional `release/vX.Y.Z` branch version **equals** `pyproject.toml` version.
- `CHANGELOG.md` contains a `## [X.Y.Z]` section (not only `[Unreleased]`).

---

## What ships in v0.1.0 (suggested scope)

**In (core library):**

- SQLite FTS library + `elib process` / search / stats
- Metadata enrich (PubMed → Crossref → honest fallback)
- Named paper lists + BibTeX export
- Textual TUI (library, lists, PDF open via Papers/firefox)
- `elib setup`, `config.example.yaml`, local-first paths under `~/elibrary`
- Tests + pre-commit (ruff format) + CONTRIBUTING

**Out of band / clearly optional:**

- Agents / Postgres / pgvector (`compose.yaml`, `[agents]` extra) — documented, not required
- PyPI publish (optional later; start with GitHub tag + release notes)
- Full ruff lint green on entire tree (format-gated is enough for v0.1 if noted)

**Blockers before first public tag:**

- [ ] Security scrub complete ([PUBLIC_RELEASE.md](PUBLIC_RELEASE.md)) — config/example, no keys, no library PDFs
- [ ] All intentional code on `worx` (or an optional release branch), not only a dirty working tree
- [ ] `make check` (or `pytest` + format) green
- [ ] Fresh clone smoke: `uv sync` → `elib setup` → process sample → search → TUI
- [ ] Changelog section for `0.1.0` filled in

---

## Release procedure (final `vX.Y.Z`)

### 0. Preflight (every release)

```bash
# working tree clean; on up-to-date worx (develop until the GitHub rename)
git status
make check                 # ruff format/lint checks + pytest
make pre-commit-run        # optional full-tree hooks
git grep -iE 'api_key\s*[:=].*[a-f0-9]{20}|BEGIN PRIVATE' || true
```

Confirm secrets stay in `~/.config/elib/env` / `~/elibrary/config.yaml` only.

### 1. Freeze version + changelog (on `worx`)

1. Set version in `pyproject.toml`:

   ```toml
   version = "X.Y.Z"
   ```

2. In `CHANGELOG.md`:
   - Move items from `## [Unreleased]` into `## [X.Y.Z] - YYYY-MM-DD`
   - Leave a fresh empty `## [Unreleased]` section
   - Update compare links at the bottom

3. Commit and open a PR into `worx` (or commit on an optional `release/vX.Y.Z` freeze branch and PR that back):

   ```bash
   git add pyproject.toml CHANGELOG.md uv.lock   # lock if needed
   git commit -m "release: vX.Y.Z"
   git push -u origin HEAD
   ```

- Title: `release: vX.Y.Z`
- Description: short summary + checklist (tests, scrub, smoke).
- Merge only when green.

### 2. Tag

From `worx` after merge:

```bash
git checkout worx
git pull
git tag -a vX.Y.Z -m "elib vX.Y.Z"
git push origin vX.Y.Z
```

### 3. GitHub Release

`release.yml` creates the GitHub Release from tag `vX.Y.Z` after validation
succeeds (pre-release if the version contains `-`). PyPI stays paused.

### 4. After release

- Next work continues on `worx`. Version can stay until the next bump (elib keeps a simple SemVer in pyproject).
- Optional: announce, update any personal notes.
- **Do not** auto-publish to PyPI until you explicitly want that (mirror SymWorx: validation first, publish jobs later).

---

## Pre-release procedure (optional)

From `worx`:

```bash
# e.g. 0.1.0-rc.1
# bump pyproject.toml + CHANGELOG [0.1.0-rc.1]
git tag -a v0.1.0-rc.1 -m "elib v0.1.0-rc.1"
git push origin v0.1.0-rc.1
```

GitHub Release → mark **Pre-release**.

---

## CI

Org-standard CI split:

| Workflow | Trigger | Checks |
|----------|---------|--------|
| `ci.yml` | PR / push `worx` and `develop`; `workflow_dispatch` | `fmt` (ruff format), `check` (ruff lint + pytest) |
| `release.yml` | PR → `main` (legacy); push `release/**`; tags `v*`; `workflow_dispatch` | Version ↔ tag/branch match; changelog heading; `fmt`; `check`; `uv build` smoke. GitHub Release on tags only. |

Push to `worx` is not a Release trigger: day-to-day CI already ran.

**PyPI publish stays paused.** GitHub Release runs on tags `v*` after validation.

Local equivalent:

```bash
make check   # ruff check + format --check + pytest
```

Org rulesets still name `develop` / `stage` / `main` until an admin pass after the default-branch rename. Repo helper:

```bash
./scripts/apply-github-rulesets.py
```

---

## First public open-source sequence

Shipped (`v0.1.0` and later). Keep using GitHub Flow on `worx` for the next tag.

---

## PyPI (later, optional)

Not required for GitHub releases. When ready:

- Trusted publishing (OIDC) from `release.yml` on tags `v*`
- `uv build` / `uv publish` or `python -m build`
- Package name `elib` may already be taken — verify on PyPI; rename distribution if needed (`elibrary-cli`, etc.)

---

## Checklist (copy into the release PR)

- [ ] Version in `pyproject.toml` = `X.Y.Z`
- [ ] Branch name `release/vX.Y.Z` (if used) or tag matches
- [ ] `CHANGELOG.md` has `## [X.Y.Z] - YYYY-MM-DD`
- [ ] `make check` green
- [ ] No secrets / personal `config.yaml` / PDFs in the commit
- [ ] Smoke: setup → process → search → TUI open PDF → list export
- [ ] Tag `vX.Y.Z` on `worx` after merge (`release.yml` creates the GitHub Release)

---

## Quick reference (commands)

```bash
# on worx: edit pyproject.toml version + CHANGELOG
git commit -am "release: v0.2.2"
git push
# PR → worx, merge, then:
git checkout worx && git pull
git tag -a v0.2.2 -m "elib v0.2.2"
git push origin v0.2.2
```
