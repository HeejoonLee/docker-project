# --- Web UI build ---
FROM node:22-slim AS web
WORKDIR /web
COPY web/package.json web/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY web/ ./
RUN npm run build

# --- Python app (web API + Temporal worker) ---
FROM python:3.13-slim
RUN apt-get update \
 && apt-get install -y --no-install-recommends git ca-certificates \
 && rm -rf /var/lib/apt/lists/*
COPY --from=ghcr.io/astral-sh/uv:0.12.5 /uv /usr/local/bin/uv
RUN useradd --create-home --uid 1000 stonepedia
WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PROJECT_ENVIRONMENT=/app/.venv PATH=/app/.venv/bin:$PATH
COPY pyproject.toml uv.lock README.md ./
RUN uv sync --frozen --no-dev --no-install-project
COPY src ./src
RUN uv sync --frozen --no-dev
COPY --from=web /web/dist ./web/dist
ENV STONEPEDIA_DATA_DIR=/data
RUN mkdir /data && chown stonepedia:stonepedia /data
USER stonepedia
EXPOSE 8000
CMD ["uvicorn", "stonepedia.web:app", "--host", "0.0.0.0", "--port", "8000"]
