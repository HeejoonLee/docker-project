# Stonepedia

Stonepedia turns documents into reviewed, git-versioned knowledge for AI agents.

You give it a **Source**: pasted text, a PDF/Word/PowerPoint/Excel file, a photo of a handwritten note, an intranet link, or a typed **Request**. Claude Code drafts a **Proposal**, a set of changes to the **Articles** (OKF v0.2 Markdown) of a **Bundle**. A person reviews each change (Accept, Revise, Edit or Discard), and the accepted changes become one git commit, pushed to GitLab. Scheduled **maintenance** checks links and structure, re-reads linked pages, and can audit a Bundle for duplicates and contradictions. Its output is always another Proposal, never a direct change.

Everything is configured in the browser. Under the hood, every step is a [Temporal](https://temporal.io) workflow; the Temporal UI ships alongside for debugging.

Vocabulary: [CONTEXT.md](CONTEXT.md) · Decisions: [docs/adr](docs/adr) · Plan: [docs/plan.md](docs/plan.md)

## Deploy on a server (offline)

On a machine with Docker and this repository:

```sh
make bundle            # -> dist/stonepedia-<version>.tar (all images, ~720 MB)
```

Copy the tar to the server and follow the **INSTALL.md** inside ([docs/install.md](docs/install.md)). In short:

```sh
tar -xf stonepedia-<version>.tar && cd stonepedia-<version>
docker load -i images.tar.gz
cp .env.example .env
docker compose up -d     # then open http://<server>:8080
```

Then, in the browser: **Settings** (point Claude at your LLM gateway, press *Test agent*) → **Bundles** (new or from an existing repo) → **New**.

## Run from source

Requires Docker with Compose.

```sh
cp .env.example .env
docker compose up -d --build
```

Stonepedia: http://localhost:8080 · Temporal UI: http://localhost:8080/temporal/

To let the Docker worker use your own Claude login on a development machine, create a git-ignored `docker-compose.override.yml`:

```yaml
services:
  worker:
    volumes:
      - ${HOME}/.claude/.credentials.json:/home/stonepedia/.claude/.credentials.json:ro
```

## Develop

Requires [uv](https://docs.astral.sh/uv/), Node 22, the [Temporal CLI](https://docs.temporal.io/cli) and Claude Code.

```sh
uv sync && (cd web && npm install)
make dev     # Temporal dev server + worker + API + Vite: http://localhost:5173
make test
```

Read [docs/development.md](docs/development.md) before changing workflow code.
