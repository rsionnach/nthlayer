# NthLayer Development Guide

Complete guide for local development and testing without external service dependencies.

---

## Quick Start (5 minutes)

```bash
# 1. Clone and setup
git clone <repo-url>
cd nthlayer
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# 2. Install dependencies
make install-dev

# 3. Start infrastructure (Postgres + Redis)
make dev-up

# 4. Run migrations
make migrate

# 5. Run tests
make test

# 6. Start mock API server (in another terminal)
make mock-server

# 7. Try demo workflow
make demo-reconcile
```

✅ **You're ready to develop!**

---

## What You Need

### Required:
- ✅ Python 3.9+
- ✅ Docker Desktop (for Postgres + Redis)
- ✅ This repository

### NOT Required:
- ❌ PagerDuty account
- ❌ Grafana installation
- ❌ Datadog account
- ❌ AWS account (for initial development)
- ❌ Any paid services

---

## Development Modes

### Mode 1: Unit Tests (Fastest)

**What:** Test individual components with mocked HTTP calls
**When:** During active development, pre-commit
**Speed:** < 5 seconds

```bash
# Run all tests
make test

# Run with coverage
make test-cov

# Run specific test file
pytest tests/test_clients.py -v

# Run specific test
pytest tests/test_clients.py::test_cortex_client_retry_on_503 -v
```

**How it works:**
- Uses `respx` to mock HTTP calls
- No external services needed
- Fast, reliable, deterministic

---

### Mode 2: Mock Server (Integration)

**What:** Test against realistic API server that simulates all external services
**When:** Testing workflows, debugging reconciliation
**Speed:** ~30 seconds

```bash
# Terminal 1: Start infrastructure
make dev-up

# Terminal 2: Start mock server
make mock-server
# Server runs at http://localhost:8001

# Terminal 3: Update .env to point at mock server
cat >> .env << EOF
NTHLAYER_PAGERDUTY_BASE_URL=http://localhost:8001/pagerduty
NTHLAYER_GRAFANA_BASE_URL=http://localhost:8001/grafana
NTHLAYER_CORTEX_BASE_URL=http://localhost:8001/cortex
NTHLAYER_DATADOG_BASE_URL=http://localhost:8001/datadog
EOF

# Run integration tests
pytest tests/integration/ -v

# Or start API and test manually
make api
# Then: curl http://localhost:8000/v1/docs
```

**Mock server features:**
- ✅ Simulates PagerDuty, Grafana, Datadog, Cortex, Slack
- ✅ Returns realistic responses
- ✅ Tracks state (remembers what you create)
- ✅ Logs all requests
- ✅ Can simulate errors (503, 429, etc.)

**View mock server state:**
```bash
curl http://localhost:8001/state | jq
```

**Reset mock server:**
```bash
curl -X POST http://localhost:8001/reset
```

---

### Mode 3: Demo Mode (Visual)

**What:** Simulate full workflows with pretty output
**When:** Learning, demos, presentations
**Speed:** ~5 seconds

```bash
# List available services
python -m nthlayer.demo list-services

# List available teams
python -m nthlayer.demo list-teams

# Run team reconciliation demo
python -m nthlayer.demo reconcile-team team-platform

# Run service reconciliation demo
python -m nthlayer.demo reconcile-service search-api
```

**What you'll see:**
```
======================================================================
  🔄 Team Reconciliation Demo: team-platform
======================================================================

--- 1. Input: Team Definition ---

id: team-platform
name: Platform Engineering
members:
  - email: alice@example.com
    role: manager
  ...

--- 2. Fetching Current State ---

📥 GET Cortex:     /api/teams/team-platform
📥 GET PagerDuty:  /teams/TEAM123
✅ Fetched current state from all sources

--- 3. Computing Differences ---

Changes detected:
  • PagerDuty: Add 1 manager (alice@example.com)
  • Slack: Create user group @platform-oncall

... (continues with all steps)
```

---

### Mode 4: Real Services (Production-like)

**What:** Test against real PagerDuty, Grafana, etc.
**When:** Final validation before production
**Speed:** ~60 seconds (API rate limits)

**Setup:**
1. Get trial accounts:
   - PagerDuty: 14-day free trial
   - Grafana Cloud: Free tier
   - Datadog: 14-day trial (optional)

2. Update `.env` with real tokens:
```bash
NTHLAYER_PAGERDUTY_TOKEN=<your-real-token>
NTHLAYER_PAGERDUTY_BASE_URL=https://api.pagerduty.com
NTHLAYER_GRAFANA_BASE_URL=https://your-org.grafana.net
# ... etc
```

3. Run tests:
```bash
pytest tests/integration/ -v --real-services
```

⚠️ **Warning:** This will create real resources. Use a sandbox account!

---

## Project Structure

```
nthlayer/
├── src/nthlayer/           # Main application code
│   ├── api/               # FastAPI endpoints
│   ├── clients/           # HTTP clients (PagerDuty, Grafana, etc.)
│   ├── workflows/         # LangGraph reconciliation workflows
│   ├── workers/           # Lambda workers
│   ├── db/                # Database models & repositories
│   ├── cache.py           # Redis caching
│   ├── metrics.py         # CloudWatch metrics
│   ├── tracing.py         # X-Ray tracing
│   └── demo.py            # Demo CLI (NEW)
│
├── tests/                 # Tests
│   ├── test_clients.py    # Client tests (with respx mocks)
│   ├── test_repository.py # Database tests
│   ├── integration/       # Integration tests (NEW)
│   ├── fixtures/          # Test data (NEW)
│   │   └── demo_data.yaml # Demo services/teams
│   └── mock_server.py     # Mock API server (NEW)
│
├── alembic/               # Database migrations
├── docs/                  # Documentation
│   ├── DEVELOPMENT.md     # This file (NEW)
│   ├── IMPROVEMENTS.md    # Feature documentation
│   └── QUICK_START.md     # Quick start guide
│
├── docker-compose.yml     # Postgres + Redis (NEW)
├── Makefile               # Development shortcuts (NEW)
├── pyproject.toml         # Python dependencies
├── .env.example           # Environment template
└── README.md              # Overview
```

---

## Common Workflows

### Adding a New Client

Example: Add Opsgenie client

**1. Create client file:**
```python
# src/nthlayer/clients/opsgenie.py
from .base import BaseHTTPClient

class OpsgenieClient(BaseHTTPClient):
    def __init__(self, api_key: str, **kwargs):
        super().__init__(base_url="https://api.opsgenie.com", **kwargs)
        self.api_key = api_key

    async def get_team(self, team_id: str):
        return await self._request("GET", f"/v2/teams/{team_id}")
```

**2. Add tests with mocks:**
```python
# tests/test_opsgenie_client.py
import pytest
import respx
from httpx import Response

@pytest.mark.asyncio
async def test_opsgenie_get_team():
    client = OpsgenieClient("test-key")

    with respx.mock:
        respx.get("https://api.opsgenie.com/v2/teams/team-123").mock(
            return_value=Response(200, json={"id": "team-123"})
        )

        team = await client.get_team("team-123")
        assert team["id"] == "team-123"
```

**3. Add to mock server:**
```python
# tests/mock_server.py
@app.get("/opsgenie/v2/teams/{team_id}")
async def opsgenie_get_team(team_id: str):
    return {"id": team_id, "name": f"Team {team_id}"}
```

**4. Test it:**
```bash
make test
make mock-server  # In another terminal
# Test manually with mock server running
```

---

### Adding a New Workflow

Example: Add "service onboarding" workflow

**1. Create workflow:**
```python
# src/nthlayer/workflows/service_onboard.py
from langgraph.graph import StateGraph

def create_onboard_workflow():
    workflow = StateGraph()
    workflow.add_node("validate", validate_service)
    workflow.add_node("create_alerts", create_alerts)
    workflow.add_node("create_dashboard", create_dashboard)
    # ... etc
    return workflow.compile()
```

**2. Add demo:**
```python
# src/nthlayer/demo.py
async def demo_onboard_service(service_id: str):
    print_header("🚀 Service Onboarding Demo")
    # ... simulate workflow
```

**3. Test:**
```bash
python -m nthlayer.demo onboard-service my-new-service
```

---

### Debugging Tips

**1. See what API calls are being made:**
```bash
# Start mock server with debug logging
LOGLEVEL=DEBUG python -m tests.mock_server
```

**2. Check mock server state:**
```bash
curl http://localhost:8001/state | jq .details
```

**3. Use demo mode to understand flow:**
```bash
python -m nthlayer.demo reconcile-team team-platform
# Shows step-by-step what happens
```

**4. Run specific test with output:**
```bash
pytest tests/test_clients.py::test_name -v -s
```

**5. Check database state:**
```bash
docker exec -it nthlayer-postgres psql -U postgres -d nthlayer
\dt  # List tables
SELECT * FROM runs;
```

**6. Check Redis cache:**
```bash
docker exec -it nthlayer-redis redis-cli
KEYS *
GET some-key
```

---

## Makefile Reference

```bash
# Setup
make setup              # Complete setup (services + install + migrate)
make install-dev        # Install with dev dependencies

# Development services
make dev-up             # Start Postgres + Redis
make dev-down           # Stop services
make dev-logs           # View logs
make dev-clean          # Stop and remove volumes

# Database
make migrate            # Run migrations
make migrate-down       # Rollback last migration
make migrate-create MSG="description"  # Create new migration

# Testing
make test               # Run tests
make test-cov           # Run with coverage report
make test-integration   # Run integration tests
make mock-server        # Start mock API server

# Code quality
make lint               # Run linting
make lint-fix           # Auto-fix linting issues
make format             # Format code
make typecheck          # Run type checking

# Running
make api                # Start API server
make demo-reconcile     # Run demo reconciliation
make demo-service       # Run demo service reconciliation

# Cleanup
make clean              # Remove Python cache files
```

---

## Testing Best Practices

### Unit Tests

✅ **Do:**
- Mock all HTTP calls with `respx`
- Test one component at a time
- Test error cases (404, 503, timeout)
- Test retry logic
- Test idempotency

❌ **Don't:**
- Make real API calls in unit tests
- Test multiple components together
- Require database/Redis (use mocks)

**Example:**
```python
@pytest.mark.asyncio
async def test_client_retries_on_503():
    client = PagerDutyClient("token", max_retries=2)

    with respx.mock:
        route = respx.get("https://api.pagerduty.com/teams/team-1")
        route.side_effect = [
            Response(503),  # First attempt fails
            Response(200, json={"id": "team-1"}),  # Retry succeeds
        ]

        result = await client.get_team("team-1")
        assert route.call_count == 2  # Verify retry happened
```

---

### Integration Tests

✅ **Do:**
- Use mock server for external APIs
- Test full workflows end-to-end
- Test state changes in database
- Test cache behavior

❌ **Don't:**
- Test individual functions (that's unit tests)
- Require real external services
- Skip cleanup between tests

**Example:**
```python
@pytest.mark.integration
async def test_team_reconcile_workflow(db_session, mock_server_url):
    # Setup
    service = ServiceConfig(
        pagerduty_base_url=f"{mock_server_url}/pagerduty",
        cortex_base_url=f"{mock_server_url}/cortex",
    )

    # Execute workflow
    result = await reconcile_team("team-123", service)

    # Verify
    assert result.status == "success"
    assert result.changes == 2

    # Check database
    run = await db_session.get(Run, result.run_id)
    assert run.status == "completed"
```

---

## Troubleshooting

### Problem: `ModuleNotFoundError: No module named 'nthlayer'`

**Solution:**
```bash
pip install -e .
# or
make install-dev
```

### Problem: Database connection refused

**Solution:**
```bash
make dev-up  # Start Postgres
# Wait 5 seconds for startup
make migrate
```

### Problem: Mock server not responding

**Solution:**
```bash
# Check if running
curl http://localhost:8001/health

# If not, start it
make mock-server

# Check logs
# (Server prints all requests to console)
```

### Problem: Tests hang

**Solution:**
- Check if `respx.mock` context manager is used
- Check if async functions have `await`
- Check if tests have `@pytest.mark.asyncio` decorator

### Problem: "Too many open files"

**Solution:**
```bash
# Close httpx clients properly
async with AsyncClient() as client:
    response = await client.get(...)
```

---

## Next Steps

### Learn by Example:
1. ✅ Run `make demo-reconcile` to see workflow
2. ✅ Read `tests/test_clients.py` to see test patterns
3. ✅ Study `src/nthlayer/clients/base.py` for client implementation
4. ✅ Try modifying mock server to return different data

### Add Your First Feature:
1. Pick a small feature (e.g., "Add Opsgenie client")
2. Write tests first (TDD approach)
3. Implement against mock server
4. Validate with demo mode
5. Test against real service (optional)

### Resources:
- FastAPI docs: https://fastapi.tiangolo.com
- Respx docs: https://lundberg.github.io/respx/
- LangGraph docs: https://langchain-ai.github.io/langgraph/
- pytest-asyncio: https://pytest-asyncio.readthedocs.io

---

## Getting Help

**Questions?**
- Check this guide first
- Look at existing tests for patterns
- Run demo mode to understand workflows
- Check mock server logs to see requests

**Found a bug?**
- Check if tests reproduce it
- Add test case that fails
- Fix code
- Verify test passes

**Want to add a feature?**
1. Create issue/design doc
2. Write tests for new behavior
3. Implement feature
4. Run `make test lint typecheck`
5. Submit PR

---

## Summary

✅ **Local development is fully self-contained**
- Postgres + Redis in Docker
- Mock server simulates all external APIs
- Demo mode for visual workflows
- Unit tests for components
- Integration tests for workflows

✅ **No external services needed until production**
- Develop offline
- Fast feedback loops
- Reproducible tests
- Safe to experiment

✅ **Makefile provides shortcuts for everything**
- `make setup` - One command to get started
- `make test` - Run all tests
- `make demo-reconcile` - See it work
- `make help` - See all commands

**Happy coding!** 🚀
