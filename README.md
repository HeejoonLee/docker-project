# Stonepedia

Turns documents into reviewed, git-versioned knowledge for AI agents.
Submit a Source → an agent proposes Article changes → a human accepts, revises, edits or discards → accepted changes are committed to the Bundle's git repo.

Vocabulary: [CONTEXT.md](CONTEXT.md) · Decisions: [docs/adr](docs/adr) · Plan: [docs/plan.md](docs/plan.md)

> Status: phase 3 of 6. Proposals are written by Claude Code from pasted text, files (PDF, Word, PowerPoint, Excel, HTML, images), intranet links and Requests. Templates, git remotes and maintenance come in later phases ([plan](docs/plan.md)).

## Run it

Requires Docker with Compose.

```sh
cp .env.example .env      # optional: change ports
docker compose up -d --build
```

- Stonepedia: http://localhost:8080
- Temporal UI (admin/debug): http://localhost:8233

Then open **Settings** and put your LLM endpoint into the Claude settings file, for example:

```json
{
  "env": {
    "ANTHROPIC_BASE_URL": "http://llm.company.intra:4000",
    "ANTHROPIC_AUTH_TOKEN": "token-for-the-gateway"
  },
  "model": "model-name-on-the-gateway"
}
```

Press **Test agent** to check it. The file is passed to `claude --settings`; any Claude Code setting works there.

Data lives in Docker volumes (`stonepedia_data` for Bundles, `stonepedia_pgdata` for Temporal). `docker compose down` keeps them.

## Develop

Requires [uv](https://docs.astral.sh/uv/), Node 22 and the [Temporal CLI](https://docs.temporal.io/cli).

```sh
uv sync && (cd web && npm install)
make dev     # Temporal dev server + worker + API + Vite at http://localhost:5173
make test
```

`make dev` uses the `claude` CLI and login on your machine. To let the Docker worker use your login for local testing, create a git-ignored `docker-compose.override.yml`:

```yaml
services:
  worker:
    volumes:
      - ${HOME}/.claude/.credentials.json:/home/stonepedia/.claude/.credentials.json:ro
```
