#!/usr/bin/env bash
# Run Stonepedia on the host for development: Temporal dev server, worker, API and Vite.
# Uses its own ports (Temporal 7243, Temporal UI 8243, API 8000, UI 5173) so it can run
# next to the docker stack or another Temporal dev server.
set -euo pipefail
cd "$(dirname "$0")/.."
mkdir -p .dev
export STONEPEDIA_DATA_DIR="$PWD/.dev/data"
export STONEPEDIA_TEMPORAL_ADDRESS=localhost:7243
export STONEPEDIA_TEMPORAL_UI_URL=http://localhost:8243

# Stop every process started here (the whole process group) on exit.
trap 'trap - EXIT INT TERM; kill 0 2>/dev/null' EXIT INT TERM

if temporal operator cluster health --address "$STONEPEDIA_TEMPORAL_ADDRESS" >/dev/null 2>&1; then
  echo "Something is already listening on $STONEPEDIA_TEMPORAL_ADDRESS; stop it first." >&2
  exit 1
fi

temporal server start-dev --db-filename .dev/temporal.db --port 7243 --ui-port 8243 --log-level warn \
  --search-attribute Bundle=Keyword --search-attribute ProposalState=Keyword &
until temporal operator cluster health --address "$STONEPEDIA_TEMPORAL_ADDRESS" >/dev/null 2>&1; do sleep 1; done

uv run python -m stonepedia.worker &
uv run uvicorn stonepedia.web:app --reload --port 8000 --log-level warning &
(cd web && exec npm run dev -- --port 5173 --strictPort) &

echo
echo "  Stonepedia:  http://localhost:5173"
echo "  Temporal UI: http://localhost:8243"
echo
wait
