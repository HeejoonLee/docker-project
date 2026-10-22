# --- Web UI build ---
FROM node:22-slim AS web
WORKDIR /web
COPY web/package.json web/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY web/ ./
RUN npm run build

# --- Claude Code CLI (native binary, no Node needed at runtime) ---
FROM node:22-slim AS claude
ARG CLAUDE_CODE_VERSION=2.1.304
RUN npm install -g --no-audit --no-fund @anthropic-ai/claude-code@${CLAUDE_CODE_VERSION} \
 && cp -L "$(npm root -g)/@anthropic-ai/claude-code/bin/claude.exe" /claude \
 && /claude --version

# --- Python app (web API + Temporal worker) ---
FROM python:3.13-slim
RUN apt-get update \
 && apt-get install -y --no-install-recommends git ca-certificates \
 && rm -rf /var/lib/apt/lists/*
COPY --from=ghcr.io/astral-sh/uv:0.12.5 /uv /usr/local/bin/uv
COPY --from=claude /claude /usr/local/bin/claude
RUN useradd --create-home --uid 1000 stonepedia \
 && mkdir /home/stonepedia/.claude && chown stonepedia:stonepedia /home/stonepedia/.claude
WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PROJECT_ENVIRONMENT=/app/.venv PATH=/app/.venv/bin:$PATH
COPY pyproject.toml uv.lock README.md ./
RUN uv sync --frozen --no-dev --no-install-project
COPY src ./src
RUN uv sync --frozen --no-dev
COPY --from=web /web/dist ./web/dist
COPY docker-compose.yml /app/deploy/docker-compose.yml
COPY deploy/temporal /app/deploy/temporal
ENV STONEPEDIA_DATA_DIR=/data \
    DISABLE_AUTOUPDATER=1 \
    CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC=1
RUN mkdir /data && chown stonepedia:stonepedia /data
USER stonepedia
EXPOSE 8000
CMD ["uvicorn", "stonepedia.web:app", "--host", "0.0.0.0", "--port", "8000"]
