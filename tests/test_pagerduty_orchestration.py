"""
Tests for PagerDuty Event Orchestration management.
"""

from unittest.mock import MagicMock, patch

import pagerduty
from nthlayer.pagerduty.orchestration import (
    EventOrchestrationManager,
    OrchestrationResult,
    RoutingRule,
)


class TestRoutingRule:
    """Tests for RoutingRule dataclass."""

    def test_create_routing_rule(self):
        """Test creating a routing rule."""
        rule = RoutingRule(
            label="Route to SRE",
            condition_field="event.custom_details.routing",
            condition_value="sre",
            escalation_policy_id="P123456",
        )

        assert rule.label == "Route to SRE"
        assert rule.condition_field == "event.custom_details.routing"
        assert rule.condition_value == "sre"
        assert rule.escalation_policy_id == "P123456"


class TestOrchestrationResult:
    """Tests for OrchestrationResult dataclass."""

    def test_success_result(self):
        """Test successful orchestration result."""
        result = OrchestrationResult(
            success=True,
            orchestration_id="O123456",
            rules_created=3,
        )

        assert result.success is True
        assert result.orchestration_id == "O123456"
        assert result.rules_created == 3
        assert result.error is None
        assert result.warnings == []

    def test_failure_result(self):
        """Test failed orchestration result."""
        result = OrchestrationResult(
            success=False,
            error="API error: 403 Forbidden",
        )

        assert result.success is False
        assert result.orchestration_id is None
        assert result.rules_created == 0
        assert result.error == "API error: 403 Forbidden"

    def test_result_with_warnings(self):
        """Test result with warnings."""
        result = OrchestrationResult(
            success=True,
            warnings=["No routing rules provided"],
        )

        assert result.success is True
        assert len(result.warnings) == 1


class TestEventOrchestrationManager:
    """Tests for EventOrchestrationManager."""

    def test_init(self):
        """Test manager initialization."""
        manager = EventOrchestrationManager(
            api_key="test-api-key",
            default_from="test@example.com",
            timeout=60.0,
        )

        assert manager.api_key == "test-api-key"
        assert manager.default_from == "test@example.com"
        assert manager.timeout == 60.0
        assert manager._client is None

    def test_init_defaults(self):
        """Test manager initialization with defaults."""
        manager = EventOrchestrationManager(api_key="test-key")

        assert manager.default_from == "nthlayer@example.com"
        assert manager.timeout == 30.0

    @patch("nthlayer.pagerduty.orchestration.RestApiV2Client")
    def test_client_lazy_initialization(self, mock_client_class):
        """Test that client is lazily initialized."""
        mock_client = MagicMock()
        mock_client_class.return_value = mock_client

        manager = EventOrchestrationManager(api_key="test-key")

        # Client not created yet
        assert manager._client is None

        # Access client property
        client = manager.client

        # Now client should be created
        mock_client_class.assert_called_once_with(
            "test-key",
            default_from="nthlayer@example.com",
        )
        assert client == mock_client

    @patch("nthlayer.pagerduty.orchestration.RestApiV2Client")
    def test_close(self, mock_client_class):
        """Test closing the client."""
        mock_client = MagicMock()
        mock_client_class.return_value = mock_client

        manager = EventOrchestrationManager(api_key="test-key")
        _ = manager.client  # Initialize client

        manager.close()

        mock_client.close.assert_called_once()
        assert manager._client is None

    def test_close_without_client(self):
        """Test close when client not initialized."""
        manager = EventOrchestrationManager(api_key="test-key")
        manager.close()  # Should not raise

    @patch("nthlayer.pagerduty.orchestration.RestApiV2Client")
    def test_context_manager(self, mock_client_class):
        """Test context manager usage."""
        mock_client = MagicMock()
        mock_client_class.return_value = mock_client

        with EventOrchestrationManager(api_key="test-key") as manager:
            _ = manager.client  # Use the client

        mock_client.close.assert_called_once()

    def test_setup_orchestration_no_rules(self):
        """Test setup with no routing rules."""
        manager = EventOrchestrationManager(api_key="test-key")

        result = manager.setup_service_orchestration(
            service_id="P123456",
            routing_rules=[],
        )

        assert result.success is True
        assert "No routing rules" in result.warnings[0]

    @patch("nthlayer.pagerduty.orchestration.RestApiV2Client")
    def test_setup_orchestration_success(self, mock_client_class):
        """Test successful orchestration setup."""
        mock_client = MagicMock()
        mock_client_class.return_value = mock_client

        # Mock get existing orchestration
        mock_get_response = MagicMock()
        mock_get_response.status_code = 200
        mock_get_response.json.return_value = {"orchestration_path": {"id": "orch-123"}}

        # Mock update orchestration
        mock_put_response = MagicMock()
        mock_put_response.raise_for_status = MagicMock()

        mock_client.get.return_value = mock_get_response
        mock_client.put.return_value = mock_put_response

        manager = EventOrchestrationManager(api_key="test-key")

        rules = [
            RoutingRule(
                label="Route to SRE",
                condition_field="event.custom_details.routing",
                condition_value="sre",
                escalation_policy_id="P999",
            )
        ]

        result = manager.setup_service_orchestration(
            service_id="P123456",
            routing_rules=rules,
        )

        assert result.success is True
        assert result.orchestration_id == "orch-123"
        assert result.rules_created == 1

    @patch("nthlayer.pagerduty.orchestration.RestApiV2Client")
    def test_setup_orchestration_get_orchestration_fails(self, mock_client_class):
        """Test when getting orchestration fails."""
        mock_client = MagicMock()
        mock_client_class.return_value = mock_client

        # Mock failed get with proper HttpError
        mock_response = MagicMock()
        mock_response.status_code = 404
        mock_response.text = "Not found"
        mock_client.get.side_effect = pagerduty.HttpError("Not found", mock_response)

        manager = EventOrchestrationManager(api_key="test-key")

        rules = [
            RoutingRule(
                label="Route to SRE",
                condition_field="event.custom_details.routing",
                condition_value="sre",
                escalation_policy_id="P999",
            )
        ]

        result = manager.setup_service_orchestration(
            service_id="P123456",
            routing_rules=rules,
        )

        assert result.success is False
        assert "Failed to get or create" in result.error

    @patch("nthlayer.pagerduty.orchestration.RestApiV2Client")
    def test_setup_orchestration_http_error(self, mock_client_class):
        """Test handling of HTTP error during update."""
        mock_client = MagicMock()
        mock_client_class.return_value = mock_client

        # Get succeeds to return orchestration
        mock_get_response = MagicMock()
        mock_get_response.status_code = 200
        mock_get_response.json.return_value = {"orchestration_path": {"id": "orch-123"}}
        mock_client.get.return_value = mock_get_response

        # Put fails with HTTP error
        mock_error_response = MagicMock()
        mock_error_response.status_code = 403
        mock_error_response.text = "Forbidden"

        error = pagerduty.HttpError("Forbidden", mock_error_response)
        error.response = mock_error_response
        mock_client.put.side_effect = error

        manager = EventOrchestrationManager(api_key="test-key")

        rules = [
            RoutingRule(
                label="Test",
                condition_field="field",
                condition_value="value",
                escalation_policy_id="P999",
            )
        ]

        result = manager.setup_service_orchestration(
            service_id="P123456",
            routing_rules=rules,
        )

        assert result.success is False
        assert "Failed to update orchestration" in result.error

    @patch("nthlayer.pagerduty.orchestration.RestApiV2Client")
    def test_setup_orchestration_unexpected_error(self, mock_client_class):
        """Test handling of unexpected error."""
        mock_client = MagicMock()
        mock_client_class.return_value = mock_client
        mock_client.get.side_effect = RuntimeError("Unexpected!")

        manager = EventOrchestrationManager(api_key="test-key")

        rules = [
            RoutingRule(
                label="Test",
                condition_field="field",
                condition_value="value",
                escalation_policy_id="P999",
            )
        ]

        result = manager.setup_service_orchestration(
            service_id="P123456",
            routing_rules=rules,
        )

        assert result.success is False
        assert "Unexpected error" in result.error

    @patch("nthlayer.pagerduty.orchestration.RestApiV2Client")
    def test_get_or_create_orchestration_existing(self, mock_client_class):
        """Test getting existing orchestration."""
        mock_client = MagicMock()
        mock_client_class.return_value = mock_client

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"orchestration_path": {"id": "existing-orch"}}
        mock_client.get.return_value = mock_response

        manager = EventOrchestrationManager(api_key="test-key")
        result = manager._get_or_create_service_orchestration("P123456")

        assert result == {"id": "existing-orch"}

    @patch("nthlayer.pagerduty.orchestration.RestApiV2Client")
    def test_get_or_create_orchestration_create_new(self, mock_client_class):
        """Test creating new orchestration when none exists."""
        mock_client = MagicMock()
        mock_client_class.return_value = mock_client

        # First call fails (not found), second succeeds (creates)
        mock_fail_response = MagicMock()
        mock_fail_response.status_code = 404

        mock_success_response = MagicMock()
        mock_success_response.status_code = 200
        mock_success_response.raise_for_status = MagicMock()
        mock_success_response.json.return_value = {"orchestration_path": {"id": "new-orch"}}

        mock_client.get.side_effect = [
            pagerduty.HttpError("Not found", mock_fail_response),
            mock_success_response,
        ]

        manager = EventOrchestrationManager(api_key="test-key")
        result = manager._get_or_create_service_orchestration("P123456")

        assert result == {"id": "new-orch"}

    @patch("nthlayer.pagerduty.orchestration.RestApiV2Client")
    def test_get_or_create_orchestration_fails(self, mock_client_class):
        """Test when both get attempts fail."""
        mock_client = MagicMock()
        mock_client_class.return_value = mock_client

        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.text = "Server error"

        error = pagerduty.HttpError("Server error", mock_response)
        mock_client.get.side_effect = error

        manager = EventOrchestrationManager(api_key="test-key")
        result = manager._get_or_create_service_orchestration("P123456")

        assert result is None

    @patch("nthlayer.pagerduty.orchestration.RestApiV2Client")
    def test_update_orchestration_rules_success(self, mock_client_class):
        """Test successful rule update."""
        mock_client = MagicMock()
        mock_client_class.return_value = mock_client

        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_client.put.return_value = mock_response

        manager = EventOrchestrationManager(api_key="test-key")

        rules = [
            RoutingRule(
                label="SRE Route",
                condition_field="event.custom_details.routing",
                condition_value="sre",
                escalation_policy_id="P999",
            ),
            RoutingRule(
                label="Platform Route",
                condition_field="event.custom_details.routing",
                condition_value="platform",
                escalation_policy_id="P888",
            ),
        ]

        result = manager._update_orchestration_rules("orch-123", "svc-456", rules)

        assert result["success"] is True
        mock_client.put.assert_called_once()

        # Verify the payload structure
        call_args = mock_client.put.call_args
        assert "/event_orchestrations/services/svc-456" in call_args[0][0]

    @patch("nthlayer.pagerduty.orchestration.RestApiV2Client")
    def test_update_orchestration_rules_failure(self, mock_client_class):
        """Test failed rule update."""
        mock_client = MagicMock()
        mock_client_class.return_value = mock_client

        mock_response = MagicMock()
        mock_response.text = "Invalid payload"
        mock_client.put.side_effect = pagerduty.HttpError("Invalid payload", mock_response)

        manager = EventOrchestrationManager(api_key="test-key")

        rules = [
            RoutingRule(
                label="Test",
                condition_field="field",
                condition_value="value",
                escalation_policy_id="P999",
            )
        ]

        result = manager._update_orchestration_rules("orch-123", "svc-456", rules)

        assert result["success"] is False
        assert "Failed to update orchestration" in result["error"]

    def test_create_sre_routing_rule(self):
        """Test creating standard SRE routing rule."""
        manager = EventOrchestrationManager(api_key="test-key")

        rule = manager.create_sre_routing_rule(
            sre_escalation_policy_id="P123",
            label="Custom SRE Label",
        )

        assert rule.label == "Custom SRE Label"
        assert rule.condition_field == "event.custom_details.routing"
        assert rule.condition_value == "sre"
        assert rule.escalation_policy_id == "P123"

    def test_create_sre_routing_rule_default_label(self):
        """Test SRE routing rule with default label."""
        manager = EventOrchestrationManager(api_key="test-key")

        rule = manager.create_sre_routing_rule(sre_escalation_policy_id="P123")

        assert rule.label == "Route to SRE"

    def test_get_routing_rules_from_alerts_with_sre(self):
        """Test generating routing rules from alerts with SRE routing."""
        manager = EventOrchestrationManager(api_key="test-key")

        alerts = [
            {"name": "High Error Rate", "routing": "sre"},
            {"name": "Low Memory", "routing": "team"},
            {"name": "Budget Exhausted", "routing": "sre"},
        ]

        rules = manager.get_routing_rules_from_alerts(
            alerts=alerts,
            sre_escalation_policy_id="P999",
        )

        # Should create one SRE routing rule for all SRE alerts
        assert len(rules) == 1
        assert rules[0].condition_value == "sre"
        assert rules[0].escalation_policy_id == "P999"

    def test_get_routing_rules_from_alerts_no_sre(self):
        """Test generating routing rules when no SRE alerts."""
        manager = EventOrchestrationManager(api_key="test-key")

        alerts = [
            {"name": "High Error Rate", "routing": "team"},
            {"name": "Low Memory"},  # No routing field
        ]

        rules = manager.get_routing_rules_from_alerts(
            alerts=alerts,
            sre_escalation_policy_id="P999",
        )

        assert len(rules) == 0

    def test_get_routing_rules_from_alerts_empty(self):
        """Test generating routing rules from empty alerts."""
        manager = EventOrchestrationManager(api_key="test-key")

        rules = manager.get_routing_rules_from_alerts(
            alerts=[],
            sre_escalation_policy_id="P999",
        )

        assert len(rules) == 0
