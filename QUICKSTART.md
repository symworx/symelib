# Quickstart

> **Note:** Core elib features (ingest PDFs, metadata, full-text search) work today with **SQLite** and require no containers.
> Postgres + pgvector is **only** for the optional agentic / RAG features.
>
> You recently performed a full podman + toolbox rebuild — the first `make db-up` will pull images and create a fresh named volume.

## Core (works right now — recommended first steps)

```bash
# 1. Install (core + dev tools)
uv sync

# 2. (For agents/RAG) Install the agents extra (includes Postgres/pgvector runtime deps)
# uv sync --extra agents
# or everything: uv sync --all-extras

# 3. Process some PDFs (uses SQLite + your config.yaml)
# Default: ~/elibrary/tmp then ~/elibrary/cart. Drop files in tmp for ad-hoc ingest.
elib process --from tmp
# or: elib process /path/to/some/pdfs

# 4. Search your local library
elib search "CRISPR oncology"
elib search --added-since 7d          # imported in the last 7 days
# elib search --added-from 2026-08-01 --added-to 2026-08-28
# elib edit --id 42 --author "Smith, Ada" --year 2021

# 5. Metadata quality + re-enrich incomplete rows
elib check-metadata
elib enrich --status fallback --limit 20

# 6. Named lists (grant/manuscript) → BibTeX
elib list create "my-project" -d "Working bibliography"
# elib list add "my-project" --id 1
# elib list export "my-project" -o project.bib

# 7. Interactive TUI
elib tui
# Keys: / search · j/k move · o PDF · e edit · Alt+l lists · Ctrl+H home · Ctrl+R refresh
# Help: Alt+?   Quit: Esc Esc (library root) or Ctrl+Q

# 8. Rebuild the full-text search index after bulk changes
elib rebuild-index
```

See `config.yaml` (edit `ncbi_email` at minimum) and the main README.

## Full agents + RAG path (Postgres + pgvector + Ollama)

This path is still being stabilized on the current refactor branch. The pieces below will get you past the previous "missing compose.yaml" / "make db-up" hard failure.

```bash
# 1. Install everything
uv sync --all-extras
# or incrementally:
# uv sync --extra agents
# (the agents extra now includes the Postgres client + pgvector Python package)

# 2. Have Ollama running with a model you like
# On Silverblue (host/"OS root"): use the `ollama` command on the host (outside toolbox).
# Inside the toolbox for elib, configure the client to reach the host's Ollama:
#   export OLLAMA_HOST=http://host.containers.internal:11434
ollama run llama3.1   # run this on the *host* typically

# 3. Start Postgres + pgvector
make db-up
# (See "Toolbox / Containerized Dev Workflow" section below if you run this from inside a toolbox.)

#    After a full podman reset this will:
#    - pull the pgvector/pgvector image
#    - create the "elib-postgres" container
#    - create a named volume "elib_pgdata" (data survives restarts until you prune volumes)

# 4. Run migrations for the vector store (recommended after first `make db-up`)
make db-migrate
# This enables the pgvector extension and creates the table used by the agents RAG index.
# (Inside toolbox you will have needed to set DATABASE_URL first — see below.)

# 5. (Agents path) After you have processed some papers with the core path, populate embeddings
elib rebuild-index --embeddings
# This extracts real text from the stored PDFs (up to ~40 pages), chunks it (SentenceSplitter),
# and stores chunks with rich metadata (doi, title, etc.) in pgvector.

# 6. Try the agent (now has data in the vector store)
elib agent "Find papers on CRISPR applications in oncology and summarize key findings"
```

Re-running `elib rebuild-index --embeddings` now does a smart update (removes old chunks for the same papers first).
For a full wipe before re-populating: `elib rebuild-index --embeddings --reset`

The agent command reports how many chunks are currently in the index and gives guidance when it's empty.

## Common commands

```bash
make help          # list everything
make db-down       # stop the postgres container
make clean         # nuke caches, venvs, etc.
```

## References

- Full plan for the remaining gaps: [REFACTOR_PLAN.md](./REFACTOR_PLAN.md)
- Project vision for agents: [AGENTS.md](./AGENTS.md)
- Current status is tracked on the `grok/refactor` branch.

## Toolbox / Containerized Dev Workflow (important on atomic hosts like Silverblue)

Because `elib` Python/uv work happens inside a toolbox (or distrobox), but the DB is a separate podman container:

**Recommended sequencing:**

1. **On the host** (outside any toolbox):
   ```bash
   cd /var/home/.../elib
   make db-up
   ```
   This starts the `elib-postgres` container on the host's podman.

2. Enter your toolbox (the one that has your development tools, uv, etc.).

3. Inside the toolbox:
   ```bash
   cd /path/to/elib
   uv sync --all-extras

   # Critical: localhost inside the toolbox does not reach the host.
   export DATABASE_URL="postgresql+psycopg://elib:elib@host.containers.internal:5432/elib"
   export OLLAMA_HOST="http://host.containers.internal:11434"

   make db-migrate
   elib rebuild-index --embeddings
   elib agent "your query"
   ```

You can put the `DATABASE_URL` export in your toolbox shell init or a `.env` file if you prefer.

**Running `make db-up` from inside the toolbox**

It usually works (podman socket is forwarded), but:
- The DB container still runs on the *host*.
- You **still must** use the `host.containers.internal` form of `DATABASE_URL` for any code that connects to Postgres (alembic, the elib agents, etc.).

See the top of `compose.yaml` for more details on the full workflow.

## Troubleshooting (especially after podman rebuild)

- `make db-up` fails inside toolbox → try running it from the host instead. Ensure the toolbox can see the project directory and has podman socket access.
- Connection refused / "localhost" doesn't work → you are almost certainly hitting the toolbox networking issue. Use `host.containers.internal:5432` (see above).
- After `podman system reset` you will need to `make db-up` again; previous DB data is gone (by design of a full reset).
- Agent import errors or "DB not ready" → make sure you did `uv sync --extra agents`, have the correct `DATABASE_URL`, ran `make db-migrate`, and have processed papers + `elib rebuild-index --embeddings`.

Run `make help` anytime.
