# Stonepedia

Turns documents into reviewed, git-versioned knowledge for AI agents.
Submit a Source → an agent proposes Article changes → a human accepts, revises, edits or discards → accepted changes are committed to the Bundle's git repo.

Vocabulary: [CONTEXT.md](CONTEXT.md) · Decisions: [docs/adr](docs/adr) · Plan: [docs/plan.md](docs/plan.md)

> Status: phase 1 (walking skeleton). Proposals come from a stand-in "fake" agent; the real Claude agent arrives in phase 2.

## Run it

Requires Docker with Compose.

```sh
cp .env.example .env      # optional: change ports
docker compose up -d --build
```

- Stonepedia: http://localhost:8080
- Temporal UI (admin/debug): http://localhost:8233

Data lives in Docker volumes (`stonepedia_data` for Bundles, `stonepedia_pgdata` for Temporal). `docker compose down` keeps them.

## Develop

Requires [uv](https://docs.astral.sh/uv/), Node 22 and the [Temporal CLI](https://docs.temporal.io/cli).

```sh
uv sync && (cd web && npm install)
make dev     # Temporal dev server + worker + API + Vite at http://localhost:5173
make test
```
