```bash
docker login
```

Run this on your **build machine**, from the Stonepedia project directory, and sign
in to Docker Hub. This guide publishes the image there, then downloads and runs
it on the target server.

Both machines need Docker Engine. The target needs Docker Compose **2.23.1+**
(`docker compose version`) for [embedded configuration files](https://docs.docker.com/reference/compose-file/configs/).
These steps assume Linux images and matching CPU architectures, such as x86-64.
The build machine needs internet access; the target needs access to Docker Hub,
your LLM gateway, and GitLab if used.

**1. Build and upload the image — build machine**

On [Docker Hub](https://hub.docker.com/), create a repository named `stonepedia`
under your account. Choose private visibility if access should be restricted.
Replace `YOUR_USERNAME` in all commands and configuration below with your Docker
Hub username. Use the same version tag throughout.

```bash
docker build -t YOUR_USERNAME/stonepedia:0.1.0 .
docker push YOUR_USERNAME/stonepedia:0.1.0
```

The image includes the web UI, API, worker, and deployment configuration.
Both application services use it. Rebuild and push after changing these files;
older images do not include the configuration generator.
See Docker's [build and push guide](https://docs.docker.com/get-started/tutorials/run-an-app/).

**2. Download and prepare — target server**

Connect to the target server and run the following. Sign in with an account that
can read the repository (login is optional for public images). Replace
`YOUR_USERNAME` with the same Docker Hub username used above.

```bash
docker login
mkdir -p ~/stonepedia
cd ~/stonepedia
IMAGE=YOUR_USERNAME/stonepedia:0.1.0
docker pull "$IMAGE"
docker run --rm "$IMAGE" python -m stonepedia.deploy --image "$IMAGE" > compose.yaml
```

Use a fresh directory for the first installation. The last command generates a
self-contained `compose.yaml`, including the Temporal setup scripts, with the
correct image name and port **8081**. No source checkout or separate file transfer
is needed. It does not start the application yet.

Optional: create `.env` if you need a different available port or time zone:

```dotenv
STONEPEDIA_PORT=9080
TIMEZONE=Asia/Seoul
```

This deployment runs its own Temporal and Postgres on a private Docker network.
Their ports are not published to the host, so an existing Temporal installation
can keep running. Only Stonepedia's web port (`8081` here) must be available.
Keep the Compose project name `stonepedia` distinct from other deployments on
the server; its network and volumes use that name.

**3. Start — target server**

From `~/stonepedia`, run:

```bash
docker compose config --quiet
docker compose pull
docker compose up -d --no-build
docker compose ps -a
```

Compose downloads Stonepedia and the supporting Postgres and Temporal images.
Allow about a minute for initialization. The `web` service should become
`healthy`; `temporal-schema` and `temporal-init` should finish with exit code `0`.
Docker documents the startup options in [Compose up](https://docs.docker.com/reference/cli/docker/compose/up/).

**4. Open and configure Stonepedia**

Open `http://SERVER_IP:8081`. Permit TCP port `8081` from your client network if
the server firewall requires it. Stonepedia has no built-in authentication;
this deployment is intended for a trusted intranet.

1. Enter your reviewer name.
2. Open **Settings**, configure the Claude settings file with your LLM gateway
   URL, token, and model, then save and click **Test agent**. For example:

   ```json
   {
     "env": {
       "ANTHROPIC_BASE_URL": "http://llm-gateway.intra:4000",
       "ANTHROPIC_AUTH_TOKEN": "<gateway token>"
     },
     "model": "<model name on the gateway>"
   }
   ```

3. Open **Bundles** and create a bundle or connect an existing repository.
4. Open **New** to submit your first source or request.

Stonepedia's own Temporal UI is at `http://SERVER_IP:8081/temporal/`.

**5. Logs, restarts, and updates**

Run these from `~/stonepedia` on the server:

```bash
docker compose logs --tail=100 web worker temporal
docker compose restart web worker
```

To stop and later restart the stack while retaining data:

```bash
docker compose stop
docker compose start
```

For an update, build and push a new image tag on the build machine. On the server,
generate the updated configuration, validate it, then replace the old file:

```bash
IMAGE=YOUR_USERNAME/stonepedia:0.1.1
docker pull "$IMAGE"
docker run --rm "$IMAGE" python -m stonepedia.deploy --image "$IMAGE" > compose.next.yaml
docker compose -f compose.next.yaml config --quiet
mv compose.next.yaml compose.yaml
docker compose pull
docker compose up -d --no-build
```

Continue past validation only if it succeeds. Keep local port and time zone
settings in `.env` so they survive regeneration. Follow release notes for workflow
compatibility and finish or discard open proposals when required.

Data persists in `stonepedia_data` and `stonepedia_pgdata`. Keep the project name
the same on updates. `docker compose down -v` deletes those volumes.
This is a fresh installation; to migrate existing data, follow the
[backup and restore instructions](install.md#backup-and-restore).
