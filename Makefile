.PHONY: dev test up down logs web

dev:   ## Run everything on the host (hot reload)
	./scripts/dev.sh

test:  ## Run the test suite
	uv run pytest -q

web:   ## Build the web UI
	cd web && npm run build

up:    ## Build and start the docker stack
	docker compose up -d --build

down:  ## Stop the docker stack (data is kept)
	docker compose down

logs:  ## Follow app logs
	docker compose logs -f web worker
