.PHONY: help dev-up dev-down dev-logs test test-cov lint typecheck format clean demo-reconcile mock-server

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
	alembic upgrade head

migrate-down: ## Rollback last migration
	alembic downgrade -1

migrate-create: ## Create new migration (use: make migrate-create MSG="description")
	alembic revision --autogenerate -m "$(MSG)"

# Testing
test: ## Run tests
	.venv/bin/python -m pytest tests/ -v

test-cov: ## Run tests with coverage report
	.venv/bin/python -m pytest tests/ -v --cov=src/nthlayer --cov-report=html --cov-report=term

test-integration: ## Run integration tests (requires mock server)
	.venv/bin/python -m pytest tests/integration/ -v

test-watch: ## Run tests in watch mode (requires pytest-watch)
	.venv/bin/python -m ptw tests/ -- -v

# Code quality
lint: ## Run linting
	ruff check src/ tests/

lint-fix: ## Run linting with auto-fix
	ruff check --fix src/ tests/

format: ## Format code
	ruff format src/ tests/

typecheck: ## Run type checking
	mypy src/

pre-commit-install: ## Install pre-commit hooks
	pip install pre-commit
	pre-commit install
	@echo "✅ Pre-commit hooks installed. Linting will run automatically on commit."

pre-commit-run: ## Run pre-commit on all files
	pre-commit run --all-files

# Mock server for testing
mock-server: ## Start mock API server (simulates PagerDuty, Grafana, etc.)
	@echo "Starting mock server on http://localhost:8001"
	python -m tests.mock_server

# Demo mode
demo-reconcile: ## Run demo reconciliation workflow
	nthlayer reconcile-team team-platform

demo-service: ## Run demo service reconciliation
	nthlayer reconcile-service search-api

demo-list: ## List available demo commands
	nthlayer --help

# API server
api: ## Start API server locally
	uvicorn nthlayer.api.main:app --reload --host 0.0.0.0 --port 8000

# Installation
install: ## Install package in editable mode
	pip install -e .

install-dev: ## Install package with dev dependencies
	pip install -e ".[dev]"

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
