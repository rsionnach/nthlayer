"""Tests for nthlayer.integrations.pagerduty — PagerDuty API client."""

from unittest.mock import MagicMock, patch

import httpx

from nthlayer.integrations.pagerduty import PagerDutyClient, PagerDutySetupResult


class TestPagerDutySetupResult:
    def test_defaults(self):
        r = PagerDutySetupResult(success=True)
        assert r.service_id is None
        assert r.created_service is False
        assert r.created_escalation_policy is False
        assert r.created_team is False
        assert r.error is None
        assert r.warnings is None

    def test_full(self):
        r = PagerDutySetupResult(
            success=True,
            service_id="SVC1",
            service_url="https://pd.com/svc/1",
            escalation_policy_id="EP1",
            team_id="T1",
            created_service=True,
            created_escalation_policy=True,
            created_team=True,
            warnings=["Created team"],
        )
        assert r.service_id == "SVC1"
        assert r.warnings == ["Created team"]


class TestPagerDutyClient:
    def _make_client(self):
        return PagerDutyClient(api_key="test-key")

    def test_init(self):
        client = self._make_client()
        assert client.api_key == "test-key"
        assert client.base_url == "https://api.pagerduty.com"
        client.close()

    def test_context_manager(self):
        with PagerDutyClient(api_key="test-key") as client:
            assert client.api_key == "test-key"

    def test_setup_existing_service(self):
        """When service already exists, return it without creating."""
        client = self._make_client()
        existing = {
            "id": "SVC1",
            "name": "checkout",
            "html_url": "https://pd.com/svc/1",
            "escalation_policy": {"id": "EP1"},
        }

        with patch.object(client, "_find_service", return_value=existing):
            result = client.setup_service("checkout")

        assert result.success is True
        assert result.service_id == "SVC1"
        assert result.created_service is False
        assert "already exists" in result.warnings[0]
        client.close()

    def test_setup_new_service_with_policy_id(self):
        """Create new service using provided escalation_policy_id."""
        client = self._make_client()

        mock_response = MagicMock()
        mock_response.json.return_value = {
            "service": {
                "id": "SVC_NEW",
                "html_url": "https://pd.com/svc/new",
            }
        }
        mock_response.raise_for_status = MagicMock()

        with (
            patch.object(client, "_find_service", return_value=None),
            patch.object(client.client, "post", return_value=mock_response),
        ):
            result = client.setup_service(
                "checkout",
                escalation_policy_id="EP1",
            )

        assert result.success is True
        assert result.service_id == "SVC_NEW"
        assert result.created_service is True
        assert result.escalation_policy_id == "EP1"
        client.close()

    def test_setup_creates_default_ep_when_none_provided(self):
        """When no EP provided, create a default escalation policy."""
        client = self._make_client()

        mock_service_response = MagicMock()
        mock_service_response.json.return_value = {
            "service": {"id": "SVC_NEW", "html_url": "https://pd.com/svc/new"}
        }
        mock_service_response.raise_for_status = MagicMock()

        with (
            patch.object(client, "_find_service", return_value=None),
            patch.object(
                client,
                "_create_default_escalation_policy",
                return_value={"id": "EP_DEFAULT"},
            ),
            patch.object(client.client, "post", return_value=mock_service_response),
        ):
            result = client.setup_service("checkout")

        assert result.success is True
        assert result.created_escalation_policy is True
        assert result.escalation_policy_id == "EP_DEFAULT"
        client.close()

    def test_setup_ep_not_found_no_config_returns_error(self):
        """When EP name given but not found and no config, return error."""
        client = self._make_client()

        with (
            patch.object(client, "_find_service", return_value=None),
            patch.object(client, "_find_escalation_policy", return_value=None),
        ):
            result = client.setup_service(
                "checkout",
                escalation_policy_name="nonexistent",
            )

        assert result.success is False
        assert "not found" in result.error
        client.close()

    def test_setup_with_team_creates_team(self):
        """When team_name given and team doesn't exist, create it."""
        client = self._make_client()

        mock_service_response = MagicMock()
        mock_service_response.json.return_value = {
            "service": {"id": "SVC1", "html_url": "https://pd.com/svc/1"}
        }
        mock_service_response.raise_for_status = MagicMock()

        with (
            patch.object(client, "_find_service", return_value=None),
            patch.object(
                client,
                "_create_default_escalation_policy",
                return_value={"id": "EP1"},
            ),
            patch.object(client.client, "post", return_value=mock_service_response),
            patch.object(client, "_find_team", return_value=None),
            patch.object(client, "_create_team", return_value={"id": "T_NEW"}),
            patch.object(client, "_add_service_to_team"),
        ):
            result = client.setup_service("checkout", team_name="platform")

        assert result.success is True
        assert result.team_id == "T_NEW"
        assert result.created_team is True
        client.close()

    def test_setup_http_error(self):
        """HTTP errors are caught and returned as failed result."""
        client = self._make_client()

        mock_response = MagicMock()
        mock_response.status_code = 400
        mock_response.text = "Bad Request"
        http_error = httpx.HTTPStatusError("error", request=MagicMock(), response=mock_response)

        with (
            patch.object(client, "_find_service", side_effect=http_error),
        ):
            result = client.setup_service("checkout")

        assert result.success is False
        assert "400" in result.error
        client.close()

    def test_find_service_exact_match(self):
        """_find_service returns only exact name matches."""
        client = self._make_client()

        mock_response = MagicMock()
        mock_response.json.return_value = {
            "services": [
                {"name": "checkout-v2", "id": "SVC2"},
                {"name": "checkout", "id": "SVC1"},
            ]
        }
        mock_response.raise_for_status = MagicMock()

        with patch.object(client.client, "get", return_value=mock_response):
            result = client._find_service("checkout")

        assert result["id"] == "SVC1"
        client.close()

    def test_find_service_no_match(self):
        """_find_service returns None when no exact match."""
        client = self._make_client()

        mock_response = MagicMock()
        mock_response.json.return_value = {
            "services": [{"name": "other-service", "id": "SVC_OTHER"}]
        }
        mock_response.raise_for_status = MagicMock()

        with patch.object(client.client, "get", return_value=mock_response):
            result = client._find_service("checkout")

        assert result is None
        client.close()
