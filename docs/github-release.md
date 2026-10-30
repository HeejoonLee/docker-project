# Deploying from a GitHub Release

Use this guide when the target server cannot reach Docker Hub. You build one
offline package on a machine with internet access, attach it to a GitHub Release,
then download and run it on the server. The server never pulls from a container
registry: the package contains every image the stack needs (Stonepedia, Postgres,
Temporal server, admin tools and UI).

**Build machine:** Docker Engine, this repository, internet access (including
Docker Hub), and the [GitHub CLI](https://cli.github.com/) signed in with
`gh auth login`.

**Target server:** Docker Engine 24+ with the Compose plugin, a way to download
from GitHub, and network access to your LLM gateway and GitLab (if used).
Both machines must have the same CPU architecture, such as x86-64.

## 1. Build the package — build machine

From the project directory, with the release commit checked out:

```bash
VERSION=0.3.0 make bundle && \
  (cd dist && sha256sum stonepedia-0.3.0.tar > stonepedia-0.3.0.tar.sha256)
```

This writes `dist/stonepedia-0.3.0.tar` (about 750 MB). Without `VERSION`, the
name also contains the commit hash, such as `stonepedia-0.3.0-1d5337c.tar`.

## 2. Publish the Release — build machine

The repository needs a GitHub remote and the commit must be pushed. Then:

```bash
git tag v0.3.0
git push origin v0.3.0
gh release create v0.3.0 \
  dist/stonepedia-0.3.0.tar dist/stonepedia-0.3.0.tar.sha256 \
  --title "Stonepedia 0.3.0" --notes "Install: see INSTALL.md inside the tar."
```

Upload the package as a Release asset, never as a committed file: GitHub rejects
repository files over 100 MB, while Release assets can be up to 2 GiB.
In a private repository, only people with read access can download it.

## 3. Download — target server

Pick whichever works on your network.

- **GitHub CLI** (works for private repositories):

  ```bash
  gh release download v0.3.0 -R OWNER/stonepedia
  ```

- **curl** (public repositories only):

  ```bash
  curl -LO https://github.com/OWNER/stonepedia/releases/download/v0.3.0/stonepedia-0.3.0.tar
  curl -LO https://github.com/OWNER/stonepedia/releases/download/v0.3.0/stonepedia-0.3.0.tar.sha256
  ```

- **Browser, then copy:** if the server cannot reach GitHub, download both
  files on your PC from the Release page and copy them over:

  ```bash
  scp stonepedia-0.3.0.tar stonepedia-0.3.0.tar.sha256 USER@SERVER:~
  ```

Replace `OWNER` with the GitHub user or organization. Then check the download:

```bash
sha256sum -c stonepedia-0.3.0.tar.sha256
```

## 4. Install and start — target server

```bash
tar -xf stonepedia-0.3.0.tar
cd stonepedia-0.3.0
docker load -i images.tar.gz
cp .env.example .env
docker compose up -d
docker compose ps -a
```

The web UI listens on port **8080**. To use another port, such as 8081, change
`STONEPEDIA_PORT` in `.env` before `docker compose up -d`. Allow about a minute
for the first start. The `web` service should become `healthy`, and
`temporal-schema` and `temporal-init` should exit with code `0`.

Temporal and Postgres stay on a private Docker network with no host ports, so an
existing Temporal installation on the server can keep running.

## 5. Configure in the browser

Open `http://SERVER_IP:8080` (or your chosen port) and follow
[First-time setup](install.md#first-time-setup-in-the-browser): enter your name,
point Claude at your LLM gateway in **Settings** and press **Test agent**, then
create a Bundle. The Temporal UI is at `/temporal/` on the same port.

Stonepedia has no built-in authentication; run it only on a trusted intranet.

## Updates

Build and publish a new version as in steps 1–3, then on the server:

```bash
tar -xf stonepedia-0.3.0.tar
cd stonepedia-0.3.0
cp ../stonepedia-0.3.0/.env .
docker load -i images.tar.gz
docker compose up -d
```

Data lives in the `stonepedia_data` and `stonepedia_pgdata` Docker volumes and is
kept across updates. Finish or discard open Proposals before updating, unless the
release notes say they carry over. `docker compose down -v` deletes the data.

For logs, backups and troubleshooting, see [install.md](install.md).
