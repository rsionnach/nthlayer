# Mock API Server vs Real APIs - Fidelity Assessment

**Last Updated:** January 2025
**Purpose:** Document the differences between our mock server and real external APIs

---

## 🎯 Executive Summary

The mock server (`tests/mock_server.py`) is a **development tool**, not a production simulator. It provides basic functionality to unblock local development without requiring real API accounts.

**Fidelity Level:** ~20% (covers essential happy paths only)

---

## Quick Reference

| Aspect | Mock Server | Real APIs |
|--------|-------------|-----------|
| **Setup** | ✅ Zero config | ❌ Account + tokens required |
| **Speed** | ✅ Instant | ⚠️ Network latency |
| **Offline** | ✅ Works | ❌ Requires internet |
| **Validation** | ❌ None | ✅ Strict |
| **Auth** | ❌ Fake | ✅ Required |
| **Errors** | ❌ Basic | ✅ Detailed |
| **Coverage** | ⚠️ ~5% of API | ✅ 100% |

---

## PagerDuty API Comparison

### ✅ Mock Implements (Happy Path Only)

```python
# These work in mock server:
GET  /pagerduty/teams/{team_id}
GET  /pagerduty/teams/{team_id}/members
POST /pagerduty/teams/{team_id}/users
GET  /pagerduty/escalation_policies
```

### ❌ Mock Does NOT Implement

**Authentication:**
- No token validation (accepts any header)
- No 401 errors for invalid tokens
- No RBAC enforcement

**Request Validation:**
- No JSON schema validation
- No required field enforcement
- No type checking
- Accepts malformed requests

**Response Format:**
```json
// Real PagerDuty API:
{
  "team": {
    "id": "P123ABC",
    "type": "team",
    "summary": "Engineering",
    "self": "https://api.pagerduty.com/teams/P123ABC",
    "html_url": "https://acme.pagerduty.com/teams/P123ABC",
    "name": "Engineering",
    "description": "All engineering staff",
    "parent": { "id": "P456DEF", "type": "team" },
    "default_role": "responder"
  }
}

// Mock server returns:
{
  "team": {
    "id": "team-123",
    "name": "Team team-123",
    "description": "Mock team from NthLayer dev server"
  }
}
```

**Missing Features:**
- Pagination (`limit`, `offset`, `more`, `total`)
- Filtering (`query=`, `include[]`, `sort_by=`)
- Error codes (2100, 2001, etc.)
- Rate limiting
- Webhooks
- Conditional requests (ETags)
- 90%+ of API endpoints

**Missing Endpoints:**
- `/teams/{id}/escalation_policies`
- `/teams/{id}/audit/records`
- `/users` (full CRUD)
- `/schedules`
- `/incidents`
- `/services`
- `/oncalls`
- Most other endpoints

---

## When to Use Mock vs Real APIs

### ✅ Use Mock Server For:

1. **Feature Development**
   ```bash
   make mock-server
   export NTHLAYER_PAGERDUTY_BASE_URL=http://localhost:8001/pagerduty
   # Develop with zero external dependencies
   ```

2. **Unit/Integration Tests**
   - Testing retry logic
   - Circuit breaker behavior
   - Workflow state machines
   - Error handling paths

3. **Demos & Presentations**
   - Customer demos
   - Conference talks
   - Sales presentations
   - Documentation screenshots

4. **Offline Development**
   - Working without internet
   - Airplane coding
   - Unstable network environments

### ⚠️ Use Real APIs For:

1. **Pre-Production Validation**
   ```bash
   export NTHLAYER_PAGERDUTY_BASE_URL=https://api.pagerduty.com
   export NTHLAYER_PAGERDUTY_TOKEN=<real-sandbox-token>
   pytest tests/integration/ --real-services
   ```

2. **Edge Case Testing**
   - Rate limiting behavior
   - Large dataset pagination
   - Concurrent modifications
   - API version changes

3. **Security Validation**
   - Auth/authz flows
   - Token expiration
   - Permission boundaries
   - Audit trail verification

4. **Performance Testing**
   - Real-world latency
   - Connection pooling
   - Timeout tuning
   - Throughput limits

---

## Test Strategy Recommendations

### Hybrid Approach (Best Practice)

```python
# tests/conftest.py
import pytest
import os

@pytest.fixture
def pagerduty_client(request):
    """Provide PagerDuty client based on test marker"""

    if request.node.get_closest_marker("real_api"):
        # Use real API (requires env vars)
        return PagerDutyClient(
            token=os.getenv("NTHLAYER_PAGERDUTY_TOKEN"),
            base_url="https://api.pagerduty.com"
        )
    else:
        # Use mock (default)
        return PagerDutyClient(
            token="mock-token",
            base_url="http://localhost:8001/pagerduty"
        )

# Test with mock (fast, no setup)
@pytest.mark.asyncio
async def test_get_team_basic(pagerduty_client):
    team = await pagerduty_client.get_team("team-123")
    assert team["id"] == "team-123"
    assert "name" in team

# Test with real API (slow, requires setup)
@pytest.mark.real_api
@pytest.mark.asyncio
async def test_get_team_complete(pagerduty_client):
    team = await pagerduty_client.get_team("P123ABC")
    assert team["type"] == "team"  # Real API field
    assert team["self"].startswith("https://")
    assert "html_url" in team
```

### Running Tests

```bash
# Default: Use mock server (fast)
pytest tests/ -v

# Validate against real API (slow, requires credentials)
pytest tests/ -v -m real_api

# Run both
pytest tests/ -v -m "not real_api or real_api"
```

---

## Improving Mock Fidelity

If you need higher fidelity for specific use cases:

### Option 1: Record/Replay (Recommended)

Use VCR.py to record real API responses:

```python
import vcr

@vcr.use_cassette('fixtures/vcr/pagerduty_get_team.yaml')
async def test_with_recorded_response():
    # First run: Records real API response
    # Subsequent runs: Replays from cassette
    client = PagerDutyClient(token=real_token)
    team = await client.get_team("P123ABC")
```

**Pros:**
- Real response format
- One-time recording
- Fast playback
- Offline-capable

**Cons:**
- Requires initial real API access
- Cassettes get stale
- Need to re-record on API changes

### Option 2: OpenAPI-Based Mock

Use Prism with PagerDuty's OpenAPI spec:

```bash
# Install Prism
npm install -g @stoplight/prism-cli

# Mock from OpenAPI spec
prism mock https://raw.githubusercontent.com/PagerDuty/api-schema/main/reference/REST/openapiv3.json

# Point NthLayer at Prism
export NTHLAYER_PAGERDUTY_BASE_URL=http://localhost:4010
```

**Pros:**
- Auto-validates requests/responses
- Stays in sync with API spec
- No code to maintain

**Cons:**
- Setup overhead
- No state persistence
- May not handle all edge cases

### Option 3: Enhance Current Mock

Add validation and complete response formats:

```python
# tests/mock_server.py
from pydantic import BaseModel, Field, HttpUrl

class PagerDutyTeam(BaseModel):
    """Real PagerDuty team response format"""
    id: str
    type: str = "team"
    summary: str
    self_link: HttpUrl = Field(alias="self")
    html_url: HttpUrl
    name: str
    description: str | None = None
    parent: dict | None = None
    default_role: str = "responder"

@app.get("/pagerduty/teams/{team_id}")
async def pd_get_team(team_id: str, authorization: str = Header(None)):
    """Get PagerDuty team (with validation)"""

    # Validate auth token format
    if not authorization or not authorization.startswith("Token token="):
        raise HTTPException(status_code=401, detail="Invalid authorization")

    # Validate team_id format (PagerDuty uses P123ABC format)
    if not team_id.startswith("P") or len(team_id) != 7:
        raise HTTPException(
            status_code=400,
            detail={
                "error": {
                    "message": "Invalid team ID format",
                    "code": 2001
                }
            }
        )

    # Return properly formatted response
    team = PagerDutyTeam(
        id=team_id,
        summary=f"Team {team_id}",
        self_link=f"https://api.pagerduty.com/teams/{team_id}",
        html_url=f"https://acme.pagerduty.com/teams/{team_id}",
        name=STATE["pagerduty_teams"].get(team_id, {}).get("name", f"Team {team_id}"),
        description=STATE["pagerduty_teams"].get(team_id, {}).get("description"),
    )

    return {"team": team.model_dump(by_alias=True)}
```

---

## Coverage by API

### PagerDuty
- **Mock Coverage:** ~5%
- **Endpoints:** 4 of 80+
- **Auth:** ❌ Not validated
- **Fidelity:** Low

### Grafana
- **Mock Coverage:** ~10%
- **Endpoints:** 3 of 30+
- **Auth:** ❌ Not validated
- **Fidelity:** Low

### Datadog
- **Mock Coverage:** ~15%
- **Endpoints:** 3 of 200+
- **Auth:** ❌ Not validated
- **Fidelity:** Low

### Cortex
- **Mock Coverage:** ~10%
- **Endpoints:** 2 of 20+
- **Auth:** ❌ Not validated
- **Fidelity:** Low

### Slack
- **Mock Coverage:** ~5%
- **Endpoints:** 1 of 100+
- **Auth:** ❌ Not validated
- **Fidelity:** Very Low

---

## Common Gotchas

### 1. Auth Always Succeeds in Mock
```python
# This works in mock but fails in production:
client = PagerDutyClient(token="invalid-token")
team = await client.get_team("P123ABC")  # Mock: ✅ | Real: ❌ 401
```

### 2. Invalid Data Accepted
```python
# Mock accepts invalid data:
await client.set_team_members("team-123", members=[
    {"invalid": "structure"}  # Mock: ✅ | Real: ❌ 400
])
```

### 3. Missing Fields in Responses
```python
# Code that works with mock but breaks with real API:
team = await client.get_team("P123ABC")
print(team["html_url"])  # Mock: ❌ KeyError | Real: ✅ Works
```

### 4. No Pagination
```python
# Mock returns all results (could be huge):
teams = await client.list_teams()  # Mock: All | Real: Paginated
```

### 5. No Rate Limiting
```python
# This hammers the mock but gets rate limited on real API:
for i in range(10000):
    await client.get_team(f"team-{i}")  # Mock: ✅ Fast | Real: ❌ 429
```

---

## Monitoring Mock vs Real API Differences

### Add Logging to Catch Discrepancies

```python
# src/nthlayer/clients/base.py
import structlog

logger = structlog.get_logger()

class BaseHTTPClient:
    async def _request(self, method, path, **kwargs):
        response = await self._http_request(method, path, **kwargs)

        # Log when using mock vs real API
        if "localhost:8001" in self.base_url:
            logger.warning(
                "mock_api_used",
                base_url=self.base_url,
                method=method,
                path=path,
                warning="This request used mock API - production behavior may differ"
            )

        return response
```

### Add Integration Test Validation

```python
# tests/integration/test_api_compatibility.py
@pytest.mark.real_api
async def test_response_format_compatibility():
    """Ensure our code handles real API response format"""

    client = PagerDutyClient(token=real_token, base_url="https://api.pagerduty.com")
    team = await client.get_team("P123ABC")

    # Assert fields that MUST exist in real API
    assert "type" in team, "Real API includes 'type' field"
    assert "self" in team, "Real API includes 'self' field"
    assert "html_url" in team, "Real API includes 'html_url' field"
    assert team["type"] == "team", "Type must be 'team'"
```

---

## Decision Tree: Mock or Real API?

```
┌─────────────────────────────────────┐
│  Need to test this feature?         │
└──────────────┬──────────────────────┘
               │
               ▼
        ┌──────────────┐
        │ Does it need │     NO      ┌──────────────┐
        │ auth/authz?  ├────────────►│ Use Mock API │
        └──────┬───────┘             └──────────────┘
               │ YES
               ▼
        ┌──────────────┐
        │ Does it need │     NO      ┌──────────────┐
        │ validation?  ├────────────►│ Use Mock API │
        └──────┬───────┘             └──────────────┘
               │ YES
               ▼
        ┌──────────────┐
        │ Does it need │     NO      ┌──────────────┐
        │ pagination?  ├────────────►│ Use Mock API │
        └──────┬───────┘             └──────────────┘
               │ YES
               ▼
        ┌──────────────┐
        │ Is this pre- │     NO      ┌──────────────┐
        │ production?  ├────────────►│ Use Mock API │
        └──────┬───────┘             └──────────────┘
               │ YES
               ▼
        ┌──────────────┐
        │ Use Real API │
        │ with sandbox │
        └──────────────┘
```

---

## Resources

### Real API Documentation
- **PagerDuty:** https://developer.pagerduty.com/api-reference/
- **Grafana:** https://grafana.com/docs/grafana/latest/developers/http_api/
- **Datadog:** https://docs.datadoghq.com/api/latest/
- **Cortex:** https://docs.getcortexapp.com/api/
- **Slack:** https://api.slack.com/web

### Mock Server
- **Code:** `tests/mock_server.py`
- **Start:** `make mock-server` or `python -m tests.mock_server`
- **State:** http://localhost:8001/state
- **Reset:** `POST http://localhost:8001/reset`

### Testing
- **Mock tests:** `pytest tests/ -v`
- **Real API tests:** `pytest tests/ -v -m real_api`
- **Integration:** `pytest tests/integration/ -v`

---

## Summary

The mock API server is **intentionally simplified** to enable fast local development. It's not meant to be a perfect replica of production APIs.

**Use it for:**
- ✅ Fast iteration
- ✅ Offline work
- ✅ Learning
- ✅ Demos

**Don't use it for:**
- ❌ Production validation
- ❌ Security testing
- ❌ Edge cases
- ❌ Performance testing

**Best practice:** Develop with mock, validate with real API before release.
