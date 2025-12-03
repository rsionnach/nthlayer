"""
Integration tests using the mock server.

These tests demonstrate how to test against the mock server
without requiring real external services.

To run:
    1. Start mock server: python -m tests.mock_server
    2. Run tests: pytest tests/integration/ -v
"""

import httpx
import pytest

MOCK_SERVER_URL = "http://localhost:8001"


@pytest.fixture
def mock_server_available():
    """Check if mock server is running"""
    try:
        response = httpx.get(f"{MOCK_SERVER_URL}/health", timeout=2)
        if response.status_code == 200:
            return True
    except Exception:
        pass
    pytest.skip("Mock server not running. Start with: make mock-server")


@pytest.mark.integration
def test_mock_pagerduty_team(mock_server_available):
    """Test PagerDuty team endpoint via mock server"""
    response = httpx.get(f"{MOCK_SERVER_URL}/pagerduty/teams/team-123")
    
    assert response.status_code == 200
    data = response.json()
    assert data["team"]["id"] == "team-123"


@pytest.mark.integration
def test_mock_pagerduty_set_members(mock_server_available):
    """Test setting PagerDuty team members (idempotent)"""
    payload = {
        "members": [
            {"user": {"id": "user-1"}, "role": "manager"},
            {"user": {"id": "user-2"}, "role": "responder"},
        ]
    }
    
    response = httpx.post(
        f"{MOCK_SERVER_URL}/pagerduty/teams/team-123/users",
        json=payload,
        headers={"Idempotency-Key": "test-key-123"},
    )
    
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    assert data["team_id"] == "team-123"


@pytest.mark.integration
def test_mock_grafana_create_dashboard(mock_server_available):
    """Test creating Grafana dashboard via mock server"""
    payload = {
        "dashboard": {
            "title": "Test Dashboard",
            "uid": "test-dash-1",
            "panels": [],
        }
    }
    
    response = httpx.post(
        f"{MOCK_SERVER_URL}/grafana/api/dashboards/db",
        json=payload,
    )
    
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    assert data["uid"] == "test-dash-1"


@pytest.mark.integration
def test_mock_datadog_create_monitor(mock_server_available):
    """Test creating Datadog monitor via mock server"""
    payload = {
        "name": "High latency alert",
        "type": "metric alert",
        "query": "avg(last_5m):avg:api.latency{service:search} > 500",
        "message": "Latency is too high!",
        "tags": ["service:search", "tier:1"],
    }
    
    response = httpx.post(
        f"{MOCK_SERVER_URL}/datadog/api/v1/monitor",
        json=payload,
    )
    
    assert response.status_code == 200
    data = response.json()
    assert data["name"] == "High latency alert"
    assert "id" in data


@pytest.mark.integration
def test_mock_cortex_get_team(mock_server_available):
    """Test getting Cortex team via mock server"""
    response = httpx.get(f"{MOCK_SERVER_URL}/cortex/api/teams/team-platform")
    
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == "team-platform"
    assert "members" in data


@pytest.mark.integration
def test_mock_slack_post_message(mock_server_available):
    """Test posting Slack message via mock server"""
    payload = {
        "channel": "#team-platform",
        "text": "Reconciliation completed: 2 changes applied",
    }
    
    response = httpx.post(
        f"{MOCK_SERVER_URL}/slack/chat.postMessage",
        json=payload,
    )
    
    assert response.status_code == 200
    data = response.json()
    assert data["ok"] is True
    assert data["channel"] == "#team-platform"


@pytest.mark.integration
def test_mock_server_state(mock_server_available):
    """Test viewing mock server state"""
    response = httpx.get(f"{MOCK_SERVER_URL}/state")
    
    assert response.status_code == 200
    data = response.json()
    assert "pagerduty_teams" in data
    assert "grafana_dashboards" in data
    assert "datadog_monitors" in data
    assert "cortex_teams" in data
    assert "slack_messages" in data


@pytest.mark.integration
def test_mock_server_reset(mock_server_available):
    """Test resetting mock server state"""
    # Create some data
    httpx.post(
        f"{MOCK_SERVER_URL}/pagerduty/teams/test-team/users",
        json={"members": []},
    )
    
    # Reset
    response = httpx.post(f"{MOCK_SERVER_URL}/reset")
    assert response.status_code == 200
    
    # Verify state is empty
    state = httpx.get(f"{MOCK_SERVER_URL}/state").json()
    assert state["pagerduty_teams"] == 0
