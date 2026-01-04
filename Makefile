.PHONY: help dev-up dev-down dev-logs test test-cov lint typecheck format clean demo-reconcile mock-server docs docs-serve demo-gifs lock lock-upgrade

help: ## Show this help message
	@echo 'Usage: make [target]'
	@echo ''
	@echo 'Available targets:'
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-20s\033[0m %s\n", $$1, $$2}'

# Development environment
dev-up: ## Start Postgres + Redis in Docker
	docker-compose up -d
	@echo "Waiting for services to be healthy..."
	@sleep 3
	@echo "✅ Postgres running on localhost:5432"
	@echo "✅ Redis running on localhost:6379"
	@echo ""
	@echo "Next steps:"
	@echo "  1. Run migrations: make migrate"
	@echo "  2. Start mock server: make mock-server"
	@echo "  3. Run tests: make test"

dev-down: ## Stop Docker services
	docker-compose down

dev-logs: ## Show Docker logs
	docker-compose logs -f

dev-clean: ## Stop and remove volumes
	docker-compose down -v

# Database
migrate: ## Run database migrations
	uv run alembic upgrade head

migrate-down: ## Rollback last migration
	uv run alembic downgrade -1

migrate-create: ## Create new migration (use: make migrate-create MSG="description")
	uv run alembic revision --autogenerate -m "$(MSG)"

# Testing
test: ## Run tests
	uv run pytest tests/ -v

test-cov: ## Run tests with coverage report
	uv run pytest tests/ -v --cov=src/nthlayer --cov-report=html --cov-report=term

test-integration: ## Run integration tests (requires mock server)
	uv run pytest tests/integration/ -v

test-watch: ## Run tests in watch mode (requires pytest-watch)
	uv run ptw tests/ -- -v

# Code quality
lint: ## Run linting
	uv run ruff check src/ tests/

lint-fix: ## Run linting with auto-fix
	uv run ruff check --fix src/ tests/

format: ## Format code
	uv run ruff format src/ tests/

typecheck: ## Run type checking
	uv run mypy src/

pre-commit-install: ## Install pre-commit hooks
	uv pip install pre-commit
	uv run pre-commit install
	@echo "✅ Pre-commit hooks installed. Linting will run automatically on commit."

pre-commit-run: ## Run pre-commit on all files
	uv run pre-commit run --all-files

# Mock server for testing
mock-server: ## Start mock API server (simulates PagerDuty, Grafana, etc.)
	@echo "Starting mock server on http://localhost:8001"
	uv run python -m tests.mock_server

# Demo mode
demo-reconcile: ## Run demo reconciliation workflow
	nthlayer reconcile-team team-platform

demo-service: ## Run demo service reconciliation
	nthlayer reconcile-service search-api

demo-list: ## List available demo commands
	nthlayer --help

# API server
api: ## Start API server locally
	uv run uvicorn nthlayer.api.main:app --reload --host 0.0.0.0 --port 8000

# Installation
install: ## Install package in editable mode
	uv sync

install-dev: ## Install package with dev dependencies
	uv sync --extra dev

# Lock file management
lock: ## Update uv.lock file
	uv lock

lock-upgrade: ## Upgrade all dependencies and update lock
	uv lock --upgrade

# Cleanup
clean: ## Clean up Python cache files
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete
	find . -type d -name "*.egg-info" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".pytest_cache" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".ruff_cache" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name "htmlcov" -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name ".coverage" -delete

# Full setup
setup: dev-up install-dev migrate ## Complete setup: start services, install deps, run migrations
	@echo ""
	@echo "🎉 Setup complete!"
	@echo ""
	@echo "Try these commands:"
	@echo "  make test          # Run tests"
	@echo "  make mock-server   # Start mock APIs"
	@echo "  make demo-reconcile # See demo workflow"
	@echo "  make api           # Start NthLayer API"

# Documentation
docs: ## Build documentation site
	uv run --extra docs mkdocs build
	@echo "✅ Documentation built to docs/"

docs-serve: ## Serve documentation locally
	uv run --extra docs mkdocs serve

# Demo GIFs (requires VHS: https://github.com/charmbracelet/vhs)
demo-gifs: ## Generate CLI demo GIFs using VHS
	@echo "Generating CLI demo GIFs..."
	vhs demo/vhs/apply-demo.tape
	vhs demo/vhs/portfolio-demo.tape
	vhs demo/vhs/plan-demo.tape
	vhs demo/vhs/slo-demo.tape
	@echo "✅ Demo GIFs generated in demo/vhs/"

AUDIT_DIR := docs/audits/chunkhound
RUN_DATE  := $(shell date +%F)
OUT_DIR   := $(AUDIT_DIR)/runs/$(RUN_DATE)

.PHONY: audit audit-weekly audit-init

audit-init:
	mkdir -p $(OUT_DIR)

audit: audit-init
	@echo "Running full ChunkHound audit → $(OUT_DIR)"
	chunkhound research "Map the full execution path of nthlayer plan and nthlayer apply end-to-end. Identify key modules, state/data structures passed between layers, and the top 5 failure points (with citations). Recommend a small refactor to make the flow more testable." \
		| tee $(OUT_DIR)/01-plan-apply.md

	chunkhound research "Where is tier defined, validated, and used to affect generated artifacts? List all tier decision points and any inconsistencies. Propose a single source-of-truth approach." \
		| tee $(OUT_DIR)/02-tier.md

	chunkhound research "Explain the secret backend system end-to-end: configuration → resolution → runtime usage. Identify extension points and any security footguns (logging, error messages, default fallbacks). Recommend hardening steps." \
		| tee $(OUT_DIR)/03-secret-backends.md

	chunkhound research "How are technology templates discovered/selected/applied? Find duplicate or near-duplicate logic across templates or selection code. Propose a consolidation plan that reduces touch points when adding a new template." \
		| tee $(OUT_DIR)/04-templates.md

	chunkhound research "Document config precedence (env/file/flags/defaults/etc.) and where it’s implemented. Identify missing validation and places where invalid config can pass too far. Recommend where validation should live and how to reuse it across CLI + future integrations." \
		| tee $(OUT_DIR)/05-config.md

	chunkhound research "Trace how dashboards, alerts, and recording rules are generated and written. Identify any non-determinism, ordering issues, or formatting drift. Recommend steps to ensure reproducible output (and how to test it)." \
		| tee $(OUT_DIR)/06-determinism.md

	chunkhound research "Audit error handling across the CLI and core modules: patterns used, exit codes, user messaging, and logging. Identify inconsistencies and recommend a standard (including a small shared helper/module)." \
		| tee $(OUT_DIR)/07-errors-ux.md

	chunkhound research "Identify the likely performance bottlenecks in plan/apply and generation. Point to the functions/loops that scale with repo size / number of services / templates. Recommend 3 optimizations with best ROI and minimal complexity." \
		| tee $(OUT_DIR)/08-performance.md

audit-weekly: audit-init
	@echo "Running weekly ChunkHound audit → $(OUT_DIR)"
	chunkhound research "Map the full execution path of nthlayer plan and nthlayer apply end-to-end. Identify key modules and failure points." \
		| tee $(OUT_DIR)/01-plan-apply.md

	chunkhound research "Document config precedence and identify missing or inconsistent validation." \
		| tee $(OUT_DIR)/05-config.md

	chunkhound research "Audit error handling across the CLI and core modules and recommend a consistent standard." \
		| tee $(OUT_DIR)/07-errors-ux.md

	chunkhound research "List the main entrypoints for nthlayer plan/apply and the functions they call (with file:line citations)." \
		| tee $(OUT_DIR)/08-performance.md
	chunkhound research "Weekly performance check: Starting from src/nthlayer/cli/plan.py:119-143 and src/nthlayer/cli/apply.py:1-35, trace into ServiceOrchestrator.plan()/apply(). Identify any NEW or CHANGED potential performance issues introduced by recent changes: repeated parsing, repeated template resolution, repeated file I/O, repeated network calls (Grafana/Prometheus), N^2 loops. Output a short report with (1) top 5 hotspots with file:line citations, (2) what changed since the previous run (if inferable), and (3) 1-2 low-risk optimizations or guardrails/tests to prevent regressions." \
		| tee "$OUT_DIR/08-performance-weekly.md"
