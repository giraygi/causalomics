# Only Docker (with the compose plugin) is required on the host.
COMPOSE ?= docker compose
APP_URL ?= http://localhost:$${FRONTEND_PORT:-8080}

.PHONY: up import down logs test test-backend test-frontend smoke verify clean clean-all

up:            ## build and start db, backend and frontend
	$(COMPOSE) up --build -d

import:        ## load example data through the API (idempotent)
	$(COMPOSE) --profile import run --rm importer

down:          ## stop the stack, keep the database volume
	$(COMPOSE) down

logs:
	$(COMPOSE) logs -f --tail=100

test: test-backend test-frontend

test-backend:  ## ruff + pytest inside the backend test image (SQLite in-memory)
	docker build --target test -t causalomics-backend-test ./backend
	docker run --rm causalomics-backend-test

test-frontend: ## type-check and build the frontend bundle
	docker build --target build -t causalomics-frontend-build ./frontend

smoke:         ## the UI and the proxied API answer
	curl -fsS $(APP_URL)/ > /dev/null
	curl -fsS $(APP_URL)/api/health

verify: test up
	@echo "waiting for the stack..."; \
	for i in $$(seq 1 30); do curl -fsS $(APP_URL)/api/health >/dev/null 2>&1 && break; sleep 2; done
	$(MAKE) smoke
	@echo "verify: OK"

clean:         ## remove this project's containers, networks and built images (keeps data)
	$(COMPOSE) --profile import down --remove-orphans
	-docker images -q --filter label=com.causalomics.project=$${COMPOSE_PROJECT_NAME:-causalomics} | xargs -r docker rmi -f

clean-all: clean ## additionally delete the database volume
	$(COMPOSE) --profile import down -v
