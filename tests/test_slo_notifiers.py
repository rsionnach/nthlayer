"""Tests for slos/notifiers.py.

Tests for Slack and PagerDuty notification handlers.
"""

from datetime import datetime
from unittest.mock import AsyncMock, patch

import httpx
import pytest
from nthlayer.slos.alerts import AlertEvent, AlertSeverity
from nthlayer.slos.notifiers import (
    AlertNotifier,
    NotificationError,
    PagerDutyNotifier,
    SlackNotifier,
)


@pytest.fixture
def sample_alert_event():
    """Create a sample alert event."""
    return AlertEvent(
        id="alert-test-001",
        rule_id="rule-001",
        service="test-service",
        slo_id="slo-001",
        severity=AlertSeverity.WARNING,
        title="Error Budget Alert: test-service",
        message="Error budget is at 80%",
        details={
            "budget_consumed_percent": 80.0,
            "threshold_percent": 75.0,
            "burned_minutes": 34.5,
            "remaining_minutes": 8.7,
        },
        triggered_at=datetime(2025, 1, 10, 12, 0, 0),
    )


@pytest.fixture
def critical_alert_event():
    """Create a critical severity alert event."""
    return AlertEvent(
        id="alert-critical-001",
        rule_id="rule-002",
        service="test-service",
        slo_id="slo-001",
        severity=AlertSeverity.CRITICAL,
        title="High Burn Rate Alert: test-service",
        message="Burn rate is 5x baseline",
        details={
            "burn_rate": 5.0,
            "threshold": 3.0,
            "burned_minutes": 40.0,
            "remaining_minutes": 3.2,
        },
        triggered_at=datetime(2025, 1, 10, 12, 30, 0),
    )


class TestNotificationError:
    """Tests for NotificationError exception."""

    def test_raise_error(self):
        """Test raising NotificationError."""
        with pytest.raises(NotificationError) as exc_info:
            raise NotificationError("Failed to send")

        assert "Failed to send" in str(exc_info.value)


class TestSlackNotifier:
    """Tests for SlackNotifier class."""

    def test_init(self):
        """Test SlackNotifier initialization."""
        notifier = SlackNotifier("https://hooks.slack.com/test")

        assert notifier.webhook_url == "https://hooks.slack.com/test"
        assert notifier.timeout == 10.0

    def test_init_custom_timeout(self):
        """Test SlackNotifier with custom timeout."""
        notifier = SlackNotifier("https://hooks.slack.com/test", timeout=30.0)

        assert notifier.timeout == 30.0

    @pytest.mark.asyncio
    async def test_send_alert_success(self, sample_alert_event):
        """Test successfully sending alert to Slack."""
        notifier = SlackNotifier("https://hooks.slack.com/test")

        with patch("httpx.AsyncClient") as mock_client:
            mock_response = AsyncMock()
            mock_response.raise_for_status = AsyncMock()
            mock_client.return_value.__aenter__.return_value.post = AsyncMock(
                return_value=mock_response
            )

            result = await notifier.send_alert(sample_alert_event)

        assert result == {"status": "sent", "channel": "slack"}

    @pytest.mark.asyncio
    async def test_send_alert_http_error(self, sample_alert_event):
        """Test handling HTTP error from Slack."""
        notifier = SlackNotifier("https://hooks.slack.com/test")

        with patch("httpx.AsyncClient") as mock_client:
            mock_client.return_value.__aenter__.return_value.post = AsyncMock(
                side_effect=httpx.HTTPError("Connection failed")
            )

            with pytest.raises(NotificationError) as exc_info:
                await notifier.send_alert(sample_alert_event)

        assert "Failed to send Slack alert" in str(exc_info.value)

    def test_format_slack_message_warning(self, sample_alert_event):
        """Test Slack message formatting for warning severity."""
        notifier = SlackNotifier("https://hooks.slack.com/test")

        payload = notifier._format_slack_message(sample_alert_event)

        assert payload["text"] == sample_alert_event.title
        assert "blocks" in payload
        assert len(payload["blocks"]) >= 3
        # Check header block
        assert payload["blocks"][0]["type"] == "header"
        assert payload["blocks"][0]["text"]["text"] == "Error Budget Alert: test-service"
        # Check attachments color (orange for warning)
        assert payload["attachments"][0]["color"] == "#ff9900"

    def test_format_slack_message_critical(self, critical_alert_event):
        """Test Slack message formatting for critical severity."""
        notifier = SlackNotifier("https://hooks.slack.com/test")

        payload = notifier._format_slack_message(critical_alert_event)

        # Check attachments color (red for critical)
        assert payload["attachments"][0]["color"] == "#ff0000"

    def test_format_slack_message_info(self):
        """Test Slack message formatting for info severity."""
        event = AlertEvent(
            id="alert-info-001",
            rule_id="rule-001",
            service="test-service",
            slo_id="slo-001",
            severity=AlertSeverity.INFO,
            title="Info Alert",
            message="Just informational",
            details={"burned_minutes": 5.0},
            triggered_at=datetime(2025, 1, 10, 12, 0, 0),
        )

        notifier = SlackNotifier("https://hooks.slack.com/test")
        payload = notifier._format_slack_message(event)

        # Check attachments color (green for info)
        assert payload["attachments"][0]["color"] == "#36a64f"

    def test_format_slack_message_with_action_buttons(self, sample_alert_event):
        """Test Slack message includes action buttons when burned_minutes > 0."""
        notifier = SlackNotifier("https://hooks.slack.com/test")

        payload = notifier._format_slack_message(sample_alert_event)

        # Should have action buttons since burned_minutes > 0
        action_blocks = [b for b in payload["blocks"] if b.get("type") == "actions"]
        assert len(action_blocks) == 1
        assert len(action_blocks[0]["elements"]) == 2
        assert action_blocks[0]["elements"][0]["text"]["text"] == "View Error Budget"

    def test_format_slack_message_no_action_buttons(self):
        """Test Slack message has no action buttons when burned_minutes = 0."""
        event = AlertEvent(
            id="alert-001",
            rule_id="rule-001",
            service="test-service",
            slo_id="slo-001",
            severity=AlertSeverity.WARNING,
            title="Test Alert",
            message="Test",
            details={"burned_minutes": 0},
            triggered_at=datetime(2025, 1, 10, 12, 0, 0),
        )

        notifier = SlackNotifier("https://hooks.slack.com/test")
        payload = notifier._format_slack_message(event)

        action_blocks = [b for b in payload["blocks"] if b.get("type") == "actions"]
        assert len(action_blocks) == 0


class TestPagerDutyNotifier:
    """Tests for PagerDutyNotifier class."""

    def test_init(self):
        """Test PagerDutyNotifier initialization."""
        notifier = PagerDutyNotifier("test-integration-key")

        assert notifier.integration_key == "test-integration-key"
        assert notifier.timeout == 10.0
        assert "pagerduty.com" in notifier.api_url

    def test_init_custom_timeout(self):
        """Test PagerDutyNotifier with custom timeout."""
        notifier = PagerDutyNotifier("test-key", timeout=30.0)

        assert notifier.timeout == 30.0

    @pytest.mark.asyncio
    async def test_send_alert_critical_success(self, critical_alert_event):
        """Test successfully sending critical alert to PagerDuty."""
        notifier = PagerDutyNotifier("test-integration-key")

        with patch("httpx.AsyncClient") as mock_client:
            mock_response = AsyncMock()
            mock_response.raise_for_status = AsyncMock()
            mock_response.json = lambda: {"dedup_key": "dedup-123"}
            mock_client.return_value.__aenter__.return_value.post = AsyncMock(
                return_value=mock_response
            )

            result = await notifier.send_alert(critical_alert_event)

        assert result["status"] == "sent"
        assert result["channel"] == "pagerduty"
        assert result["dedup_key"] == "dedup-123"

    @pytest.mark.asyncio
    async def test_send_alert_skips_non_critical(self, sample_alert_event):
        """Test PagerDuty skips non-critical alerts."""
        notifier = PagerDutyNotifier("test-integration-key")

        result = await notifier.send_alert(sample_alert_event)

        assert result == {"status": "skipped", "reason": "not_critical"}

    @pytest.mark.asyncio
    async def test_send_alert_http_error(self, critical_alert_event):
        """Test handling HTTP error from PagerDuty."""
        notifier = PagerDutyNotifier("test-integration-key")

        with patch("httpx.AsyncClient") as mock_client:
            mock_client.return_value.__aenter__.return_value.post = AsyncMock(
                side_effect=httpx.HTTPError("Connection failed")
            )

            with pytest.raises(NotificationError) as exc_info:
                await notifier.send_alert(critical_alert_event)

        assert "Failed to send PagerDuty alert" in str(exc_info.value)

    def test_format_pagerduty_event(self, critical_alert_event):
        """Test PagerDuty event formatting."""
        notifier = PagerDutyNotifier("test-integration-key")

        payload = notifier._format_pagerduty_event(critical_alert_event)

        assert payload["routing_key"] == "test-integration-key"
        assert payload["event_action"] == "trigger"
        assert payload["dedup_key"] == "alert-critical-001"
        assert payload["payload"]["summary"] == critical_alert_event.title
        assert payload["payload"]["severity"] == "critical"
        assert payload["payload"]["source"] == "nthlayer-test-service"
        assert payload["payload"]["component"] == "slo-001"
        assert payload["payload"]["custom_details"] == critical_alert_event.details


class TestAlertNotifier:
    """Tests for AlertNotifier unified notifier class."""

    def test_init(self):
        """Test AlertNotifier initialization."""
        notifier = AlertNotifier()

        assert notifier.notifiers == {}

    def test_add_slack(self):
        """Test adding Slack notifier."""
        notifier = AlertNotifier()
        notifier.add_slack("https://hooks.slack.com/test")

        assert "slack" in notifier.notifiers
        assert isinstance(notifier.notifiers["slack"], SlackNotifier)

    def test_add_pagerduty(self):
        """Test adding PagerDuty notifier."""
        notifier = AlertNotifier()
        notifier.add_pagerduty("test-key")

        assert "pagerduty" in notifier.notifiers
        assert isinstance(notifier.notifiers["pagerduty"], PagerDutyNotifier)

    def test_add_multiple_channels(self):
        """Test adding multiple notification channels."""
        notifier = AlertNotifier()
        notifier.add_slack("https://hooks.slack.com/test")
        notifier.add_pagerduty("test-key")

        assert len(notifier.notifiers) == 2

    @pytest.mark.asyncio
    async def test_send_alert_to_all_channels(self, critical_alert_event):
        """Test sending alert to all configured channels."""
        notifier = AlertNotifier()
        notifier.add_slack("https://hooks.slack.com/test")
        notifier.add_pagerduty("test-key")

        with patch.object(SlackNotifier, "send_alert", new_callable=AsyncMock) as mock_slack:
            with patch.object(PagerDutyNotifier, "send_alert", new_callable=AsyncMock) as mock_pd:
                mock_slack.return_value = {"status": "sent", "channel": "slack"}
                mock_pd.return_value = {
                    "status": "sent",
                    "channel": "pagerduty",
                    "dedup_key": "123",
                }

                results = await notifier.send_alert(critical_alert_event)

        assert results["slack"]["status"] == "sent"
        assert results["pagerduty"]["status"] == "sent"

    @pytest.mark.asyncio
    async def test_send_alert_handles_channel_failure(self, critical_alert_event):
        """Test handling failure in one channel doesn't stop others."""
        notifier = AlertNotifier()
        notifier.add_slack("https://hooks.slack.com/test")
        notifier.add_pagerduty("test-key")

        with patch.object(SlackNotifier, "send_alert", new_callable=AsyncMock) as mock_slack:
            with patch.object(PagerDutyNotifier, "send_alert", new_callable=AsyncMock) as mock_pd:
                mock_slack.side_effect = NotificationError("Slack failed")
                mock_pd.return_value = {
                    "status": "sent",
                    "channel": "pagerduty",
                    "dedup_key": "123",
                }

                results = await notifier.send_alert(critical_alert_event)

        assert results["slack"]["status"] == "failed"
        assert "Slack failed" in results["slack"]["error"]
        assert results["pagerduty"]["status"] == "sent"

    @pytest.mark.asyncio
    async def test_send_alert_no_channels_configured(self, sample_alert_event):
        """Test sending alert with no channels configured."""
        notifier = AlertNotifier()

        results = await notifier.send_alert(sample_alert_event)

        assert results == {}
