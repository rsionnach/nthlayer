"""Tests for pagerduty/resources.py.

Comprehensive tests for PagerDuty resource management including:
- PagerDutyResourceManager initialization
- Team, schedule, escalation policy, and service management
- Error handling and API responses
"""

from unittest.mock import MagicMock, patch

import pagerduty
import pytest
from nthlayer.pagerduty.resources import (
    PagerDutyAPIError,
    PagerDutyResourceManager,
    ResourceResult,
    SetupResult,
)


def make_http_error(status_code=400, text="Error"):
    """Create a mock HttpError for testing."""
    mock_response = MagicMock()
    mock_response.status_code = status_code
    mock_response.text = text
    return pagerduty.HttpError("API Error", mock_response)


@pytest.fixture
def mock_client():
    """Create mock PagerDuty client."""
    client = MagicMock()
    return client


@pytest.fixture
def manager(mock_client):
    """Create PagerDutyResourceManager with mocked client."""
    with patch("nthlayer.pagerduty.resources.RestApiV2Client", return_value=mock_client):
        mgr = PagerDutyResourceManager(
            api_key="test-api-key",
            default_from="test@example.com",
        )
        mgr._client = mock_client
    return mgr


class TestPagerDutyAPIError:
    """Tests for PagerDutyAPIError exception."""

    def test_create_error(self):
        """Creates exception."""
        error = PagerDutyAPIError("API failed")
        assert str(error) == "API failed"


class TestResourceResult:
    """Tests for ResourceResult dataclass."""

    def test_successful_result(self):
        """Creates successful result."""
        result = ResourceResult(
            success=True,
            resource_id="PABCD123",
            resource_name="test-team",
            created=True,
        )

        assert result.success is True
        assert result.resource_id == "PABCD123"
        assert result.created is True

    def test_failed_result(self):
        """Creates failed result."""
        result = ResourceResult(
            success=False,
            error="API error: 401 Unauthorized",
        )

        assert result.success is False
        assert result.error == "API error: 401 Unauthorized"

    def test_result_with_warnings(self):
        """Creates result with warnings."""
        result = ResourceResult(
            success=True,
            resource_id="PABCD123",
            warnings=["Using existing team"],
        )

        assert result.warnings == ["Using existing team"]


class TestSetupResult:
    """Tests for SetupResult dataclass."""

    def test_successful_setup(self):
        """Creates successful setup result."""
        result = SetupResult(
            success=True,
            team_id="PTEAM123",
            schedule_ids={"primary": "PSCHED123"},
            escalation_policy_id="PESC123",
            service_id="PSERV123",
            service_url="https://pagerduty.com/services/PSERV123",
            created_resources=["team:test-team", "service:test-service"],
        )

        assert result.success is True
        assert result.team_id == "PTEAM123"
        assert "primary" in result.schedule_ids

    def test_failed_setup(self):
        """Creates failed setup result."""
        result = SetupResult(
            success=False,
            errors=["Failed to create team"],
        )

        assert result.success is False
        assert len(result.errors) == 1


class TestPagerDutyResourceManagerInit:
    """Tests for PagerDutyResourceManager initialization."""

    def test_init_stores_config(self):
        """Stores configuration on init."""
        mgr = PagerDutyResourceManager(
            api_key="test-key",
            default_from="test@example.com",
            timeout=60.0,
        )

        assert mgr.api_key == "test-key"
        assert mgr.default_from == "test@example.com"
        assert mgr.timeout == 60.0
        assert mgr._client is None

    def test_client_lazy_init(self):
        """Client is lazily initialized."""
        with patch("nthlayer.pagerduty.resources.RestApiV2Client") as mock_class:
            mock_client = MagicMock()
            mock_class.return_value = mock_client

            mgr = PagerDutyResourceManager(
                api_key="test-key",
                default_from="test@example.com",
            )

            # Client not created yet
            mock_class.assert_not_called()

            # Access client
            _ = mgr.client

            mock_class.assert_called_once_with(
                "test-key",
                default_from="test@example.com",
            )

    def test_close_client(self, manager, mock_client):
        """Closes client connection."""
        manager.close()

        mock_client.close.assert_called_once()
        assert manager._client is None

    def test_context_manager(self):
        """Works as context manager."""
        with patch("nthlayer.pagerduty.resources.RestApiV2Client") as mock_class:
            mock_client = MagicMock()
            mock_class.return_value = mock_client

            with PagerDutyResourceManager(
                api_key="test-key",
                default_from="test@example.com",
            ) as mgr:
                _ = mgr.client  # Force client creation

            mock_client.close.assert_called_once()


class TestGetDefaultUserId:
    """Tests for get_default_user_id method."""

    def test_returns_cached_id(self, manager):
        """Returns cached user ID."""
        manager._default_user_id = "PUSER123"

        result = manager.get_default_user_id()

        assert result == "PUSER123"
        manager._client.get.assert_not_called()

    def test_fetches_user_from_api(self, manager, mock_client):
        """Fetches first user from API."""
        mock_response = MagicMock()
        mock_response.json.return_value = {"users": [{"id": "PUSER456", "name": "Test User"}]}
        mock_client.get.return_value = mock_response

        result = manager.get_default_user_id()

        assert result == "PUSER456"
        mock_client.get.assert_called_with("/users", params={"limit": 1})

    def test_returns_none_when_no_users(self, manager, mock_client):
        """Returns None when no users."""
        mock_response = MagicMock()
        mock_response.json.return_value = {"users": []}
        mock_client.get.return_value = mock_response

        result = manager.get_default_user_id()

        assert result is None

    def test_handles_api_error(self, manager, mock_client):
        """Handles API error gracefully."""
        mock_client.get.side_effect = make_http_error(500, "Server Error")

        result = manager.get_default_user_id()

        assert result is None


class TestEnsureTeam:
    """Tests for ensure_team method."""

    def test_finds_existing_team(self, manager, mock_client):
        """Finds and returns existing team."""
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "teams": [{"id": "PTEAM123", "name": "platform"}]  # get_team_name returns "platform"
        }
        mock_client.get.return_value = mock_response

        result = manager.ensure_team("platform")

        assert result.success is True
        assert result.resource_id == "PTEAM123"
        assert result.created is False

    def test_creates_new_team(self, manager, mock_client):
        """Creates new team when not found."""
        # First call: search returns no results
        mock_get_response = MagicMock()
        mock_get_response.json.return_value = {"teams": []}
        mock_client.get.return_value = mock_get_response

        # Second call: create succeeds
        mock_post_response = MagicMock()
        mock_post_response.json.return_value = {"team": {"id": "PTEAM456", "name": "platform"}}
        mock_client.post.return_value = mock_post_response

        result = manager.ensure_team("platform")

        assert result.success is True
        assert result.resource_id == "PTEAM456"
        assert result.created is True

    def test_handles_create_error(self, manager, mock_client):
        """Handles team creation error."""
        mock_get_response = MagicMock()
        mock_get_response.json.return_value = {"teams": []}
        mock_client.get.return_value = mock_get_response

        mock_client.post.side_effect = make_http_error(403, "Forbidden")

        result = manager.ensure_team("platform")

        assert result.success is False
        assert "Forbidden" in result.error


class TestAddTeamMember:
    """Tests for add_team_member method."""

    def test_adds_member_successfully(self, manager, mock_client):
        """Adds team member."""
        mock_response = MagicMock()
        mock_client.put.return_value = mock_response

        result = manager.add_team_member(
            team_id="PTEAM123",
            user_id="PUSER456",
            role="manager",
        )

        assert result.success is True
        assert result.created is True

    def test_handles_already_member(self, manager, mock_client):
        """Handles user already being member."""
        mock_client.put.side_effect = make_http_error(409, "Conflict")

        result = manager.add_team_member(
            team_id="PTEAM123",
            user_id="PUSER456",
            role="manager",
        )

        assert result.success is True
        assert result.created is False
        assert "already member" in result.warnings[0]

    def test_handles_api_error(self, manager, mock_client):
        """Handles API error."""
        mock_client.put.side_effect = make_http_error(403, "Forbidden")

        result = manager.add_team_member(
            team_id="PTEAM123",
            user_id="PUSER456",
            role="manager",
        )

        assert result.success is False
        assert "Forbidden" in result.error

    def test_handles_unexpected_error(self, manager, mock_client):
        """Handles unexpected error."""
        mock_client.put.side_effect = RuntimeError("Unexpected")

        result = manager.add_team_member(
            team_id="PTEAM123",
            user_id="PUSER456",
            role="manager",
        )

        assert result.success is False
        assert "Unexpected" in result.error


class TestEnsureSchedule:
    """Tests for ensure_schedule method."""

    def test_finds_existing_schedule(self, manager, mock_client):
        """Finds and returns existing schedule."""
        # get_schedule_name returns "platform-primary"
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "schedules": [{"id": "PSCHED123", "name": "platform-primary"}]
        }
        mock_client.get.return_value = mock_response

        result = manager.ensure_schedule(
            team="platform",
            schedule_type="primary",
            tier="critical",
            support_model="self",
            timezone="America/New_York",
        )

        assert result.success is True
        assert result.resource_id == "PSCHED123"
        assert result.created is False

    def test_creates_new_schedule(self, manager, mock_client):
        """Creates new schedule when not found."""
        # Search returns no results
        mock_get_response = MagicMock()
        mock_get_response.json.return_value = {"schedules": []}
        mock_client.get.return_value = mock_get_response

        # Create succeeds
        mock_post_response = MagicMock()
        mock_post_response.json.return_value = {
            "schedule": {"id": "PSCHED456", "name": "platform-primary"}
        }
        mock_client.post.return_value = mock_post_response

        # Mock user lookup
        manager._default_user_id = "PUSER123"

        result = manager.ensure_schedule(
            team="platform",
            schedule_type="primary",
            tier="critical",
            support_model="self",
            timezone="America/New_York",
        )

        assert result.success is True
        assert result.resource_id == "PSCHED456"
        assert result.created is True

    def test_fails_without_users(self, manager, mock_client):
        """Fails when no users available."""
        mock_get_response = MagicMock()
        mock_get_response.json.return_value = {"schedules": [], "users": []}
        mock_client.get.return_value = mock_get_response

        manager._default_user_id = None

        result = manager.ensure_schedule(
            team="platform",
            schedule_type="primary",
            tier="critical",
            support_model="self",
            timezone="America/New_York",
        )

        assert result.success is False
        assert "No users found" in result.error


class TestEnsureEscalationPolicy:
    """Tests for ensure_escalation_policy method."""

    def test_finds_existing_policy(self, manager, mock_client):
        """Finds and returns existing policy."""
        # get_escalation_policy_name returns "platform-escalation"
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "escalation_policies": [{"id": "PESC123", "name": "platform-escalation"}]
        }
        mock_client.get.return_value = mock_response

        result = manager.ensure_escalation_policy(
            team="platform",
            tier="critical",
            schedule_ids={"primary": "PSCHED123"},
        )

        assert result.success is True
        assert result.resource_id == "PESC123"
        assert result.created is False

    def test_creates_new_policy(self, manager, mock_client):
        """Creates new escalation policy."""
        # Search returns no results
        mock_get_response = MagicMock()
        mock_get_response.json.return_value = {"escalation_policies": []}
        mock_client.get.return_value = mock_get_response

        # Create succeeds
        mock_post_response = MagicMock()
        mock_post_response.json.return_value = {
            "escalation_policy": {"id": "PESC456", "name": "platform-escalation"}
        }
        mock_client.post.return_value = mock_post_response

        result = manager.ensure_escalation_policy(
            team="platform",
            tier="critical",
            schedule_ids={"primary": "PSCHED123"},
        )

        assert result.success is True
        assert result.resource_id == "PESC456"
        assert result.created is True

    def test_fails_without_schedules(self, manager, mock_client):
        """Fails when no schedules provided."""
        mock_get_response = MagicMock()
        mock_get_response.json.return_value = {"escalation_policies": []}
        mock_client.get.return_value = mock_get_response

        result = manager.ensure_escalation_policy(
            team="platform",
            tier="critical",
            schedule_ids={},  # No schedules
        )

        assert result.success is False
        assert "No valid escalation rules" in result.error


class TestEnsureService:
    """Tests for ensure_service method."""

    def test_finds_existing_service(self, manager, mock_client):
        """Finds and returns existing service."""
        mock_response = MagicMock()
        mock_response.json.return_value = {"services": [{"id": "PSERV123", "name": "my-service"}]}
        mock_client.get.return_value = mock_response

        result = manager.ensure_service(
            service_name="my-service",
            escalation_policy_id="PESC123",
            team_id="PTEAM123",
            tier="critical",
        )

        assert result.success is True
        assert result.resource_id == "PSERV123"
        assert result.created is False

    def test_creates_new_service(self, manager, mock_client):
        """Creates new service."""
        # Search returns no results
        mock_get_response = MagicMock()
        mock_get_response.json.return_value = {"services": []}
        mock_client.get.return_value = mock_get_response

        # Create succeeds
        mock_post_response = MagicMock()
        mock_post_response.json.return_value = {"service": {"id": "PSERV456", "name": "my-service"}}
        mock_client.post.return_value = mock_post_response

        result = manager.ensure_service(
            service_name="my-service",
            escalation_policy_id="PESC123",
            team_id="PTEAM123",
            tier="critical",
        )

        assert result.success is True
        assert result.resource_id == "PSERV456"
        assert result.created is True


class TestSetupService:
    """Tests for setup_service method."""

    def test_full_setup_success(self, manager, mock_client):
        """Completes full service setup."""
        # Mock user lookup
        manager._default_user_id = "PUSER123"

        # For the "low" tier, we need fewer schedules
        # Use call tracking to return different values for different endpoints
        call_count = {"get": 0, "post": 0}

        def get_side_effect(url, **kwargs):
            call_count["get"] += 1
            resp = MagicMock()
            resp.json.return_value = {
                "teams": [],
                "schedules": [],
                "escalation_policies": [],
                "services": [],
                "users": [{"id": "PUSER123"}],
            }
            return resp

        def post_side_effect(url, **kwargs):
            call_count["post"] += 1
            resp = MagicMock()
            if "/teams" in url:
                resp.json.return_value = {"team": {"id": "PTEAM123", "name": "platform"}}
            elif "/schedules" in url:
                resp.json.return_value = {"schedule": {"id": "PSCHED123", "name": "schedule"}}
            elif "/escalation_policies" in url:
                resp.json.return_value = {"escalation_policy": {"id": "PESC123", "name": "policy"}}
            elif "/services" in url:
                resp.json.return_value = {"service": {"id": "PSERV123", "name": "my-service"}}
            return resp

        mock_client.get.side_effect = get_side_effect
        mock_client.post.side_effect = post_side_effect
        mock_client.put.return_value = MagicMock()

        result = manager.setup_service(
            service_name="my-service",
            team="platform",
            tier="low",  # Low tier has simpler setup
        )

        assert result.service_id == "PSERV123"

    def test_handles_team_failure_gracefully(self, manager, mock_client):
        """Continues with warnings when team creation fails."""
        manager._default_user_id = "PUSER123"

        def get_side_effect(url, **kwargs):
            resp = MagicMock()
            if "escalation_policies" in url:
                resp.json.return_value = {
                    "escalation_policies": [{"id": "DEFAULT123", "name": "Default"}]
                }
            else:
                resp.json.return_value = {"teams": [], "schedules": [], "services": [], "users": []}
            return resp

        def post_side_effect(url, **kwargs):
            if "/teams" in url:
                raise make_http_error(403, "Forbidden")
            elif "/services" in url:
                resp = MagicMock()
                resp.json.return_value = {"service": {"id": "PSERV123"}}
                return resp
            resp = MagicMock()
            resp.json.return_value = {}
            return resp

        mock_client.get.side_effect = get_side_effect
        mock_client.post.side_effect = post_side_effect

        result = manager.setup_service(
            service_name="my-service",
            team="platform",
            tier="low",  # Low tier has no schedules required
        )

        # Should have warnings about team failure
        assert any("Team" in w or "team" in w.lower() for w in result.warnings)

    def test_handles_api_exception(self, manager, mock_client):
        """Handles API exception during setup."""
        # API errors in individual methods are caught internally
        # This test verifies setup continues but fails at the end
        mock_client.get.side_effect = make_http_error(500, "Server Error")

        result = manager.setup_service(
            service_name="my-service",
            team="platform",
            tier="critical",
        )

        # Setup fails because no resources could be created
        assert result.success is False
        assert len(result.errors) > 0

    def test_handles_unexpected_exception(self, manager, mock_client):
        """Handles unexpected exception during setup."""
        mock_client.get.side_effect = RuntimeError("Unexpected error")

        result = manager.setup_service(
            service_name="my-service",
            team="platform",
            tier="critical",
        )

        assert result.success is False
        assert "Unexpected error" in result.errors[0]


class TestFindMethods:
    """Tests for _find_* helper methods."""

    def test_find_team_by_name(self, manager, mock_client):
        """Finds team by exact name match."""
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "teams": [
                {"id": "PTEAM1", "name": "other-team"},
                {"id": "PTEAM2", "name": "platform"},
            ]
        }
        mock_client.get.return_value = mock_response

        result = manager._find_team("platform")

        assert result["id"] == "PTEAM2"

    def test_find_team_case_insensitive(self, manager, mock_client):
        """Finds team with case-insensitive match."""
        mock_response = MagicMock()
        mock_response.json.return_value = {"teams": [{"id": "PTEAM1", "name": "Platform"}]}
        mock_client.get.return_value = mock_response

        result = manager._find_team("platform")

        assert result["id"] == "PTEAM1"

    def test_find_team_not_found(self, manager, mock_client):
        """Returns None when team not found."""
        mock_response = MagicMock()
        mock_response.json.return_value = {"teams": []}
        mock_client.get.return_value = mock_response

        result = manager._find_team("nonexistent")

        assert result is None

    def test_find_team_handles_error(self, manager, mock_client):
        """Handles API error gracefully."""
        mock_client.get.side_effect = make_http_error(500, "Server Error")

        result = manager._find_team("any-team")

        assert result is None

    def test_find_schedule(self, manager, mock_client):
        """Finds schedule by name."""
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "schedules": [{"id": "PSCHED1", "name": "team-platform-primary"}]
        }
        mock_client.get.return_value = mock_response

        result = manager._find_schedule("team-platform-primary")

        assert result["id"] == "PSCHED1"

    def test_find_escalation_policy(self, manager, mock_client):
        """Finds escalation policy by name."""
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "escalation_policies": [{"id": "PESC1", "name": "team-platform escalation"}]
        }
        mock_client.get.return_value = mock_response

        result = manager._find_escalation_policy("team-platform escalation")

        assert result["id"] == "PESC1"

    def test_find_service(self, manager, mock_client):
        """Finds service by name."""
        mock_response = MagicMock()
        mock_response.json.return_value = {"services": [{"id": "PSERV1", "name": "my-service"}]}
        mock_client.get.return_value = mock_response

        result = manager._find_service("my-service")

        assert result["id"] == "PSERV1"

    def test_find_service_by_id(self, manager, mock_client):
        """Finds service by ID."""
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "service": {
                "id": "PSERV1",
                "name": "my-service",
                "html_url": "https://pagerduty.com/services/PSERV1",
            }
        }
        mock_client.get.return_value = mock_response

        result = manager._find_service_by_id("PSERV1")

        assert result["id"] == "PSERV1"
        assert result["html_url"] == "https://pagerduty.com/services/PSERV1"


class TestGetCurrentUserId:
    """Tests for get_current_user_id method."""

    def test_delegates_to_default_user(self, manager):
        """Delegates to get_default_user_id."""
        manager._default_user_id = "PUSER123"

        result = manager.get_current_user_id()

        assert result == "PUSER123"
