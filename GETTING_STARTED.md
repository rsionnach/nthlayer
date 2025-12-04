# Getting Started with NthLayer Development

**Zero external services required!** This guide will get you up and running in 10 minutes.

---

## Prerequisites

- **Python 3.11+** (required - check with `python3 --version`)
- Docker Desktop (for Postgres + Redis)
- Git
- Text editor (VS Code, PyCharm, etc.)

**That's it!** No PagerDuty, Grafana, AWS, or other accounts needed.

> **Note:** If your system Python is older, use `brew install python@3.11` or [pyenv](https://github.com/pyenv/pyenv) to install Python 3.11+.

---

## Step 1: Clone and Setup (2 minutes)

```bash
# Clone repository
git clone <repo-url>
cd nthlayer

# Create virtual environment
python3 -m venv .venv

# Activate it
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# Install dependencies
pip install -e ".[dev]"
```

---

## Step 2: Start Infrastructure (1 minute)

```bash
# Start Postgres + Redis in Docker
make dev-up

# This will:
# ✅ Start Postgres on localhost:5432
# ✅ Start Redis on localhost:6379
# ✅ Create persistent volumes
```

Wait about 5 seconds for services to start, then:

```bash
# Run database migrations
make migrate
```

---

## Step 3: Verify Installation (30 seconds)

```bash
# Run tests
make test

# You should see:
# ====== test session starts ======
# tests/test_clients.py ........... PASSED
# tests/test_repository.py ....... PASSED
# ====== X passed in 2.34s ======
```

✅ **If tests pass, you're ready to develop!**

---

## Step 4: Try the Mock Server (2 minutes)

The mock server simulates PagerDuty, Grafana, Datadog, Cortex, and Slack APIs.

**Terminal 1: Start mock server**
```bash
make mock-server

# You should see:
# ======================================================================
# 🚀 NthLayer Mock API Server
# ======================================================================
# Running on: http://localhost:8001
# ...
```

**Terminal 2: Test it**
```bash
# Check health
curl http://localhost:8001/health

# Get mock PagerDuty team
curl http://localhost:8001/pagerduty/teams/team-123

# View all state
curl http://localhost:8001/state | jq
```

---

## Step 5: Run a Demo Workflow (1 minute)

See what NthLayer does without making real API calls:

```bash
# List available services
python -m nthlayer.demo list-services

# Run team reconciliation demo
python -m nthlayer.demo reconcile-team team-platform

# Run service reconciliation demo
python -m nthlayer.demo reconcile-service search-api
```

You'll see a step-by-step visualization of:
- What data NthLayer reads
- What changes it computes
- What API calls it makes
- What gets stored in the database

---

## Step 6: Start the API (Optional)

If you want to test the API endpoints:

```bash
# Use mock server configuration
cp .env.mock .env

# Start API server
make api

# Open interactive docs
open http://localhost:8000/v1/docs

# Or test with curl
curl http://localhost:8000/health
```

---

## Understanding the Components

### What You Just Set Up:

```
┌─────────────────────────────────────────┐
│  Your Development Environment          │
├─────────────────────────────────────────┤
│                                         │
│  Postgres (Docker)                      │
│  └── Port 5432                          │
│      Database for runs, findings        │
│                                         │
│  Redis (Docker)                         │
│  └── Port 6379                          │
│      Cache & rate limiting              │
│                                         │
│  Mock API Server (Python)               │
│  └── Port 8001                          │
│      Simulates:                         │
│      • PagerDuty                        │
│      • Grafana                          │
│      • Datadog                          │
│      • Cortex                           │
│      • Slack                            │
│                                         │
│  NthLayer API (Optional)                 │
│  └── Port 8000                          │
│      FastAPI application                │
│                                         │
└─────────────────────────────────────────┘
```

### What You DON'T Need (Yet):

- ❌ Real PagerDuty account
- ❌ Real Grafana instance
- ❌ Real Datadog account
- ❌ AWS account
- ❌ Any paid services

---

## Your Daily Development Workflow

### Morning: Start services

```bash
make dev-up
```

### While coding: Run tests

```bash
# Quick test
make test

# With coverage
make test-cov

# Specific test
pytest tests/test_clients.py::test_name -v
```

### Testing integration: Use mock server

```bash
# Terminal 1
make mock-server

# Terminal 2
make api  # or run your code

# Terminal 3
curl http://localhost:8000/v1/teams/reconcile -X POST \
  -H "Content-Type: application/json" \
  -d '{"team_id": "team-123"}'
```

### Evening: Clean up

```bash
make dev-down
```

---

## Common Tasks

### Add a new test

```python
# tests/test_my_feature.py
import pytest
import respx
from httpx import Response

@pytest.mark.asyncio
async def test_my_feature():
    client = MyClient("token")

    with respx.mock:
        respx.get("https://api.example.com/data").mock(
            return_value=Response(200, json={"result": "success"})
        )

        result = await client.get_data()
        assert result["result"] == "success"
```

Run it:
```bash
pytest tests/test_my_feature.py -v
```

---

### Add a new mock endpoint

```python
# tests/mock_server.py

@app.get("/myservice/data")
async def myservice_get_data(authorization: str = Header(None)):
    logger.info("[MyService] GET /data")
    return {"result": "success"}
```

Restart mock server:
```bash
# Ctrl+C to stop, then
make mock-server
```

---

### View database contents

```bash
# Connect to Postgres
docker exec -it nthlayer-postgres psql -U postgres -d nthlayer

# List tables
\dt

# Query runs
SELECT * FROM runs;

# Exit
\q
```

---

### View Redis cache

```bash
# Connect to Redis
docker exec -it nthlayer-redis redis-cli

# List keys
KEYS *

# Get a value
GET some-key

# Exit
exit
```

---

### Check logs

```bash
# Docker logs
make dev-logs

# Mock server logs
# (printed to console where you ran 'make mock-server')

# API logs
# (printed to console where you ran 'make api')
```

---

## Next Steps

### 1. Explore the Codebase

**Start here:**
- `src/nthlayer/clients/` - How clients work
- `tests/test_clients.py` - How to test them
- `src/nthlayer/workflows/` - Reconciliation logic
- `tests/mock_server.py` - Mock API implementation

**Key patterns to understand:**
- HTTP clients inherit from `BaseHTTPClient` (retry, circuit breaker)
- All HTTP calls are mocked in tests with `respx`
- LangGraph defines workflows as state machines
- Idempotency keys prevent duplicate operations

---

### 2. Try Adding a Feature

**Example: Add Opsgenie support**

1. **Create client:**
```python
# src/nthlayer/clients/opsgenie.py
from .base import BaseHTTPClient

class OpsgenieClient(BaseHTTPClient):
    async def get_team(self, team_id: str):
        return await self._request("GET", f"/v2/teams/{team_id}")
```

2. **Add test:**
```python
# tests/test_opsgenie.py
@pytest.mark.asyncio
async def test_opsgenie_get_team():
    client = OpsgenieClient("key")
    with respx.mock:
        respx.get("https://api.opsgenie.com/v2/teams/t1").mock(
            return_value=Response(200, json={"id": "t1"})
        )
        team = await client.get_team("t1")
        assert team["id"] == "t1"
```

3. **Add to mock server:**
```python
# tests/mock_server.py
@app.get("/opsgenie/v2/teams/{team_id}")
async def opsgenie_get_team(team_id: str):
    return {"id": team_id, "name": f"Team {team_id}"}
```

4. **Test it:**
```bash
make test
```

---

### 3. Read the Full Guide

For deeper understanding, see:
- **[docs/DEVELOPMENT.md](docs/DEVELOPMENT.md)** - Complete development guide
- **[docs/QUICK_START.md](QUICK_START.md)** - Production deployment guide
- **[docs/IMPROVEMENTS.md](IMPROVEMENTS.md)** - Feature documentation
- **[nthlayer_architecture.md](nthlayer_architecture.md)** - System architecture

---

## Troubleshooting

### "Can't connect to database"

```bash
# Check if Postgres is running
docker ps | grep nthlayer-postgres

# If not running
make dev-up

# Wait 5 seconds, then
make migrate
```

---

### "Module not found"

```bash
# Make sure you installed in editable mode
pip install -e ".[dev]"

# And virtual environment is activated
source .venv/bin/activate
```

---

### "Tests are failing"

```bash
# Make sure dependencies are installed
pip install -e ".[dev]"

# Try running one test at a time
pytest tests/test_clients.py::test_cortex_client_success -v

# Check if respx mock is set up correctly
# (All HTTP calls must be inside 'with respx.mock:' block)
```

---

### "Mock server won't start"

```bash
# Check if port 8001 is already in use
lsof -i :8001

# Kill the process or use a different port
python -m tests.mock_server  # manually
```

---

### "Docker won't start"

```bash
# Make sure Docker Desktop is running
docker ps

# If not installed, download from:
# https://www.docker.com/products/docker-desktop
```

---

## Quick Reference

### Makefile Commands

```bash
make help              # Show all commands
make setup             # Complete setup (first time)
make dev-up            # Start Postgres + Redis
make dev-down          # Stop services
make migrate           # Run database migrations
make test              # Run tests
make test-cov          # Run tests with coverage
make mock-server       # Start mock API server
make api               # Start NthLayer API
make demo-reconcile    # Run demo workflow
make lint              # Check code style
make format            # Format code
make clean             # Clean cache files
```

### Demo Commands

```bash
python -m nthlayer.demo list-services           # List demo services
python -m nthlayer.demo list-teams              # List demo teams
python -m nthlayer.demo reconcile-team <id>     # Demo team reconciliation
python -m nthlayer.demo reconcile-service <id>  # Demo service reconciliation
python -m nthlayer.demo help                    # Show help
```

### URLs

- Mock Server: http://localhost:8001
- Mock Server Docs: http://localhost:8001 (shows all endpoints)
- Mock Server State: http://localhost:8001/state
- API Server: http://localhost:8000
- API Docs: http://localhost:8000/v1/docs
- Redis Commander: http://localhost:8081 (if running with `--profile tools`)

---

## Summary

✅ **You now have:**
- Local Postgres + Redis running in Docker
- Mock API server simulating all external services
- Tests running and passing
- Demo mode to visualize workflows

✅ **You can:**
- Develop without external service accounts
- Test everything locally
- Run demos for stakeholders
- Add new features with confidence

✅ **Next:**
- Explore the codebase
- Try adding a simple feature
- Read the full development guide
- When ready, get trial accounts for real testing

**Questions?** Check [docs/DEVELOPMENT.md](docs/DEVELOPMENT.md) for detailed answers.

---

**Happy coding!** 🚀

**Remember:** You're building infrastructure-as-code for operations. Every service definition becomes automated operational excellence. That's powerful stuff! 🌿
