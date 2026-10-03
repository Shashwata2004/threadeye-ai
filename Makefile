# ThreadEye AI: developer commands. Run `make help`.
SHELL := /bin/bash
UV ?= uv
PNPM ?= pnpm
TEST_DB_PORT ?= 55432
TEST_DATABASE_URL ?= postgresql+psycopg://threadeye:threadeye@localhost:$(TEST_DB_PORT)/threadeye_test

.PHONY: help env up down logs ps build test test-db test-db-stop test-backend test-frontend lint check \
        openapi openapi-check verify-offline spike-pdf validate-sample micro-fixture save-images \
        cloud-env cloud-migrate cloud-seed cloud-check cloud-setup cloud-sql

help: ## list commands
	@grep -E '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) | awk -F ':.*?## ' '{printf "  \033[36m%-16s\033[0m %s\n", $$1, $$2}'

env: ## create .env from .env.example (keeps an existing .env)
	@test -f .env && echo ".env already exists" || (cp .env.example .env && echo "created .env; review the passwords")

build: ## build all images (needs internet once)
	GIT_SHA=$$(git rev-parse --short HEAD 2>/dev/null || echo dev) docker compose build

up: ## start the edge stack and wait until healthy → http://localhost:8080
	GIT_SHA=$$(git rev-parse --short HEAD 2>/dev/null || echo dev) docker compose up -d --build --wait
	@echo "ThreadEye is up: http://localhost:$${THREADEYE_HTTP_PORT:-8080}"

down: ## stop the stack (data volumes are kept)
	docker compose down

logs: ## follow logs
	docker compose logs -f --tail=100

ps: ## service status
	docker compose ps

verify-offline: ## M0 acceptance: prove the app containers have no internet and still work
	./scripts/verify_offline.sh

test-db: ## start a throwaway Postgres for integration tests (port 55432, RAM-backed)
	@docker inspect threadeye-testdb >/dev/null 2>&1 || docker run -d --name threadeye-testdb \
	  -e POSTGRES_USER=threadeye -e POSTGRES_PASSWORD=threadeye -e POSTGRES_DB=threadeye_test \
	  -p 127.0.0.1:$(TEST_DB_PORT):5432 --tmpfs /var/lib/postgresql/data postgres:16.4-alpine >/dev/null
	@for i in $$(seq 1 30); do docker exec threadeye-testdb pg_isready -U threadeye -d threadeye_test >/dev/null 2>&1 && exit 0; sleep 1; done; echo "test db not ready"; exit 1

test-db-stop: ## remove the throwaway test database
	-docker rm -f threadeye-testdb

test-backend: test-db ## backend unit + integration tests
	cd backend && TEST_DATABASE_URL=$(TEST_DATABASE_URL) $(UV) run pytest

test-frontend: ## frontend checks (i18n parity, lint, typecheck)
	cd frontend && $(PNPM) check

test: test-backend test-frontend ## all tests

lint: ## static checks (ruff, mypy strict, import contracts, eslint, tsc, i18n)
	cd backend && $(UV) run ruff check . && $(UV) run ruff format --check . && $(UV) run mypy threadeye && $(UV) run lint-imports
	cd frontend && $(PNPM) check

openapi: ## regenerate docs/api/openapi.json and the frontend TS types from the backend
	cd backend && $(UV) run threadeye export-openapi ../docs/api/openapi.json
	cd frontend && $(PNPM) gen:api

openapi-check: openapi ## fail if the committed contract is stale
	git diff --exit-code -- docs/api/openapi.json frontend/src/lib/api/schema.d.ts

check: lint test openapi-check ## everything CI runs (except the compose job)

spike-pdf: ## render the Bangla PDF spike to backend/out/spike_bangla.pdf
	cd backend && $(UV) run threadeye spike-pdf out/spike_bangla.pdf

validate-sample: ## validate data/sample_roll against the simulator data contracts
	cd backend && $(UV) run threadeye validate-dataset ../data/sample_roll

micro-fixture: ## regenerate the synthetic test fixture
	python3 scripts/make_micro_fixture.py backend/tests/fixtures/micro_roll

save-images: ## export images for an offline install on another laptop
	docker save threadeye-backend:latest threadeye-web:latest postgres:16.4-alpine caddy:2-alpine -o threadeye-images.tar
	@echo "copy threadeye-images.tar, then: docker load -i threadeye-images.tar && make up"

# --- cloud_demo profile (Supabase). Secrets live in .env.cloud, which is gitignored. -----------
CLOUD_ENV ?= .env.cloud
cloud_run = cd backend && set -a && . ../$(CLOUD_ENV) && set +a &&

cloud-env: ## write .env.cloud from a pasted Supabase connection string (input stays hidden)
	python3 scripts/setup_cloud_env.py

cloud-migrate: ## create the threadeye schema and tables in Supabase (session pooler)
	@test -f $(CLOUD_ENV) || { echo "$(CLOUD_ENV) missing: run 'make cloud-env' first"; exit 1; }
	$(cloud_run) $(UV) run threadeye migrate

cloud-seed: ## create the demo accounts in Supabase
	@test -f $(CLOUD_ENV) || { echo "$(CLOUD_ENV) missing: run 'make cloud-env' first"; exit 1; }
	$(cloud_run) $(UV) run threadeye seed-demo-users

cloud-check: ## verify the Supabase connection, schema isolation and audit chain
	@test -f $(CLOUD_ENV) || { echo "$(CLOUD_ENV) missing: run 'make cloud-env' first"; exit 1; }
	$(cloud_run) $(UV) run threadeye cloud-check

cloud-setup: cloud-migrate cloud-seed cloud-check ## migrate + seed + verify in one go

cloud-sql: ## print the setup SQL to paste into the Supabase SQL editor (no password needed)
	@test -f $(CLOUD_ENV) || { echo "$(CLOUD_ENV) missing: run 'make cloud-env' first"; exit 1; }
	@$(cloud_run) $(UV) run threadeye migrate --sql && $(cloud_run) $(UV) run threadeye seed-demo-users --sql
