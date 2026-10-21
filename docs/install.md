# Installing Stonepedia

Stonepedia runs as one Docker Compose stack: the web app, a worker that runs the
agent and git, Temporal (workflow engine), the Temporal UI and Postgres.
It needs no internet access. It does need to reach your LLM gateway and, if you
use one, your GitLab.

## Requirements

- A Linux server with Docker Engine 24+ and the Docker Compose plugin (`docker compose version`).
- About 3 GB of disk for images, plus space for your knowledge.
- Network access from the server to the LLM endpoint and to GitLab (if used).

## Install

```sh
tar -xf stonepedia-<version>.tar
cd stonepedia-<version>
docker load -i images.tar.gz          # loads all images; no internet needed
cp .env.example .env                  # change ports or time zone here if needed
docker compose up -d
```

Open `http://<server>:8080` (the Temporal UI is at `/temporal/` on the same port). The first start takes about a minute while Temporal
sets up its database. `docker compose ps` shows `web` as `healthy` when ready.

## First-time setup (in the browser)

1. Enter your name. It is recorded on your reviews and commits.
2. **Settings** → *Claude settings file*: point Claude Code at the company LLM, e.g.

   ```json
   {
     "env": {
       "ANTHROPIC_BASE_URL": "http://llm-gateway.intra:4000",
       "ANTHROPIC_AUTH_TOKEN": "<gateway token>"
     },
     "model": "<model name on the gateway>"
   }
   ```

   Save, then **Test agent**. It should answer "OK" within a few seconds.
3. **Bundles** → *New Bundle*. Start empty (optionally give an empty GitLab
   project's URL to push to), or use an existing repository and the folder its
   Articles live in. If GitLab needs a token for pushing, put it in the URL:
   `http://user:token@gitlab.intra/group/repo.git`.
4. Optionally, under **Maintenance**, schedule the integrity check and link refresh.

## Everyday use

1. **New** → pick the Bundle, then paste text, upload a file (PDF, Word,
   PowerPoint, Excel, image of a note...), give a link, or write a Request.
2. The agent drafts Article changes (usually under a minute).
3. Review each change: **Accept**, **Revise** (tell the agent what to change),
   **Edit** by hand, or **Discard**. Feedback on the whole Proposal goes in the box
   at the bottom.
4. **Submit review**. Accepted changes become one git commit, pushed to the Bundle's remote.

## Upgrade

```sh
tar -xf stonepedia-<new version>.tar
cd stonepedia-<new version>
cp ../stonepedia-<old version>/.env .
docker load -i images.tar.gz
docker compose up -d
```

Data lives in Docker volumes (`stonepedia_data`, `stonepedia_pgdata`) and is kept.
Finish or discard open Proposals before upgrading, unless the release notes say
the upgrade keeps them.

## Backup and restore

Accepted knowledge is in each Bundle's git remote. To back up everything else
(settings, Bundles without a remote, open Proposals), stop the stack and copy the volumes:

```sh
docker compose stop
for v in data pgdata; do
  docker run --rm --user root --entrypoint tar -v stonepedia_$v:/v -v "$PWD":/backup \
    stonepedia:$(cat VERSION) czf /backup/stonepedia-$v.tgz -C /v .
done
docker compose start
```

To restore on a new server, install as above, then:

```sh
docker compose stop
for v in data pgdata; do
  docker run --rm --user root --entrypoint tar -v stonepedia_$v:/v -v "$PWD":/backup \
    stonepedia:$(cat VERSION) xzf /backup/stonepedia-$v.tgz -C /v
done
docker compose start
```

## Troubleshooting

| Symptom | What to do |
| --- | --- |
| Page does not load | `docker compose ps`; `docker compose logs web temporal` |
| "Test agent" fails | The message shows Claude's error. Check the gateway URL, token and model in Settings. |
| Proposal fails | Open it: the error is shown at the top. **Open in Temporal** shows every step. |
| "Push failed" on a Bundle | The message is from git. Fix the URL or token in the Bundle's Settings, then **Retry push**. |
| Port already in use | Change `STONEPEDIA_PORT` in `.env`, then `docker compose up -d`. |

Logs: `docker compose logs -f web worker`.
