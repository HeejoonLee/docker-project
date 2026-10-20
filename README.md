# Stonepedia

Turns documents into reviewed, git-versioned knowledge for AI agents.
Submit a Source → an agent proposes Article changes → a human accepts, revises, edits or discards → accepted changes are committed to the Bundle's git repo.

Vocabulary: [CONTEXT.md](CONTEXT.md) · Decisions: [docs/adr](docs/adr) · Plan: [docs/plan.md](docs/plan.md)

> Status: phase 5 of 6. Claude Code writes Proposals from text, files (PDF, Word, PowerPoint, Excel, HTML, images), intranet links and Requests; Bundles are git repos (new or cloned, optionally a subfolder) that push to a remote, with an editable Template; scheduled integrity checks, link refresh and AI audits keep them healthy. Offline packaging comes next ([plan](docs/plan.md)).

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

Create a Bundle under **Bundles**: start empty (optionally with a git URL to push to, e.g. an empty GitLab project) or use an existing repository and the folder its Articles live in. If pushing needs a token, put it in the URL (`http://user:token@gitlab.intra/group/repo.git`); it is never shown back in the UI.

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
