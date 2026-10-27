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
   Articles live in. Enter an HTTP(S) or SSH repository URL. For a private HTTP(S)
   repository, fill in **Git access token**. **Git username** can be left blank for a GitLab
   personal access token (defaults to `oauth2`). Use a token with
   [`write_repository`](https://docs.gitlab.com/user/profile/personal_access_tokens/)
   access so Stonepedia can clone, fetch and push accepted changes.
   In a Bundle's **Settings**, enter a replacement token to rotate it, leave the
   field blank to keep it, or select **Remove the saved token when saving**.
   Changing the repository URL requires re-entering the token; saved credentials
   are not automatically forwarded to a different repository.
   For SSH remotes, mount a server-managed `.ssh` directory into the worker as
   shown below. A Gerrit remote with a custom port uses a URL such as
   `ssh://user@gerrit.intra:29418/project.git`. The mounted `known_hosts` must
   contain the verified `[gerrit.intra]:29418` host key. SSH failures stop without
   prompting; the web UI's token fields do not apply to SSH.
   Tokens use the existing Git URL authentication storage: they are hidden in
   Bundle API responses and the UI, but stored in the local Git configuration and
   Temporal history. Removing a token stops its use for the remote; it does not
   erase historical copies. Revoke old tokens in GitLab.
4. Optionally, under **Maintenance**, schedule the integrity check and link refresh.

To use SSH and a host source-code directory, place this in a
`docker-compose.override.yml` beside the Compose file, adjusting the host paths:

```yaml
services:
  worker:
    volumes:
      - /srv/stonepedia/ssh:/home/stonepedia/.ssh:ro
      - /srv/code:/references:ro
```

The SSH directory should contain the private key, optional `config`, and verified
`known_hosts`; key files must be readable by the worker user (UID 1000). Mount
only code the agent may read. In Bundle settings, enter a path below
`/references`, such as `project-a`. Reference exclusions guide the agent's
search but do not restrict access to known files. The code stays outside the
Bundle; accepted Articles cite files by path and SHA-256 hash, with a Git commit
when available. A code-only Proposal requires a focus instruction.

## Everyday use

1. **New** → pick the Bundle, then paste text, upload a file (PDF, Word,
   PowerPoint, Excel, image of a note...), give a link, write a Request, or
   select **Code reference** and enter a focus instruction.
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
| Proposal fails | Open it: the error is shown at the top. **Temporal UI** (top right) shows every step of workflow `proposal-<id>`. |
| "Push failed" on a Bundle | The message is from git. Fix the URL or token in the Bundle's Settings, then **Retry push**. |
| Port already in use | Change `STONEPEDIA_PORT` in `.env`, then `docker compose up -d`. |

Logs: `docker compose logs -f web worker`.
