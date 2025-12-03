"""
Notification handlers for alert events.

Sends notifications to Slack, PagerDuty, etc.
"""

from __future__ import annotations

from typing import Any

import httpx
import structlog

from nthlayer.slos.alerts import AlertEvent

logger = structlog.get_logger()


class NotificationError(Exception):
    """Raised when notification fails."""


class SlackNotifier:
    """Send notifications to Slack via webhook."""
    
    def __init__(self, webhook_url: str, timeout: float = 10.0) -> None:
        self.webhook_url = webhook_url
        self.timeout = timeout
    
    async def send_alert(self, event: AlertEvent) -> dict[str, Any]:
        """
        Send alert to Slack.
        
        Args:
            event: Alert event to send
            
        Returns:
            Response from Slack
            
        Raises:
            NotificationError: If sending fails
        """
        logger.info(
            "sending_slack_alert",
            service=event.service,
            slo_id=event.slo_id,
            severity=event.severity.value,
        )
        
        # Format Slack message
        payload = self._format_slack_message(event)
        
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
                    self.webhook_url,
                    json=payload,
                )
                response.raise_for_status()
            
            logger.info(
                "slack_alert_sent",
                service=event.service,
                slo_id=event.slo_id,
            )
            
            return {"status": "sent", "channel": "slack"}
            
        except httpx.HTTPError as exc:
            logger.error(
                "slack_alert_failed",
                service=event.service,
                error=str(exc),
            )
            raise NotificationError(f"Failed to send Slack alert: {exc}") from exc
    
    def _format_slack_message(self, event: AlertEvent) -> dict[str, Any]:
        """Format alert as Slack message."""
        # Color based on severity
        color_map = {
            "info": "#36a64f",      # Green
            "warning": "#ff9900",   # Orange
            "critical": "#ff0000",  # Red
        }
        color = color_map.get(event.severity.value, "#999999")
        
        # Build Slack blocks
        blocks = [
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": event.title,
                },
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": event.message,
                },
            },
            {
                "type": "context",
                "elements": [
                    {
                        "type": "mrkdwn",
                        "text": f"*Triggered:* {event.triggered_at.strftime('%Y-%m-%d %H:%M:%S UTC')}",
                    },
                ],
            },
        ]
        
        # Add action buttons
        if event.details.get("burned_minutes", 0) > 0:
            blocks.append({
                "type": "actions",
                "elements": [
                    {
                        "type": "button",
                        "text": {
                            "type": "plain_text",
                            "text": "View Error Budget",
                        },
                        "url": f"https://your-nthlayer.com/slos/{event.service}",
                        "action_id": "view_budget",
                    },
                    {
                        "type": "button",
                        "text": {
                            "type": "plain_text",
                            "text": "Check Deployments",
                        },
                        "url": f"https://your-nthlayer.com/deployments/{event.service}",
                        "action_id": "view_deployments",
                    },
                ],
            })
        
        return {
            "text": event.title,  # Fallback text
            "blocks": blocks,
            "attachments": [
                {
                    "color": color,
                    "text": f"Severity: {event.severity.value.upper()}",
                }
            ],
        }


class PagerDutyNotifier:
    """Send notifications to PagerDuty."""
    
    def __init__(self, integration_key: str, timeout: float = 10.0) -> None:
        self.integration_key = integration_key
        self.timeout = timeout
        self.api_url = "https://events.pagerduty.com/v2/enqueue"
    
    async def send_alert(self, event: AlertEvent) -> dict[str, Any]:
        """
        Send alert to PagerDuty.
        
        Args:
            event: Alert event to send
            
        Returns:
            Response from PagerDuty
            
        Raises:
            NotificationError: If sending fails
        """
        logger.info(
            "sending_pagerduty_alert",
            service=event.service,
            slo_id=event.slo_id,
            severity=event.severity.value,
        )
        
        # Only send critical alerts to PagerDuty
        if event.severity.value != "critical":
            logger.info("skipping_non_critical_pagerduty_alert")
            return {"status": "skipped", "reason": "not_critical"}
        
        # Format PagerDuty event
        payload = self._format_pagerduty_event(event)
        
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
                    self.api_url,
                    json=payload,
                )
                response.raise_for_status()
                result = response.json()
            
            logger.info(
                "pagerduty_alert_sent",
                service=event.service,
                dedup_key=result.get("dedup_key"),
            )
            
            return {"status": "sent", "channel": "pagerduty", "dedup_key": result.get("dedup_key")}
            
        except httpx.HTTPError as exc:
            logger.error(
                "pagerduty_alert_failed",
                service=event.service,
                error=str(exc),
            )
            raise NotificationError(f"Failed to send PagerDuty alert: {exc}") from exc
    
    def _format_pagerduty_event(self, event: AlertEvent) -> dict[str, Any]:
        """Format alert as PagerDuty event."""
        return {
            "routing_key": self.integration_key,
            "event_action": "trigger",
            "dedup_key": event.id,
            "payload": {
                "summary": event.title,
                "severity": event.severity.value,
                "source": f"nthlayer-{event.service}",
                "component": event.slo_id,
                "custom_details": event.details,
            },
        }


class AlertNotifier:
    """Unified alert notifier that routes to multiple channels."""
    
    def __init__(self) -> None:
        self.notifiers: dict[str, Any] = {}
    
    def add_slack(self, webhook_url: str) -> None:
        """Add Slack notifier."""
        self.notifiers["slack"] = SlackNotifier(webhook_url)
    
    def add_pagerduty(self, integration_key: str) -> None:
        """Add PagerDuty notifier."""
        self.notifiers["pagerduty"] = PagerDutyNotifier(integration_key)
    
    async def send_alert(self, event: AlertEvent) -> dict[str, Any]:
        """
        Send alert to all configured channels.
        
        Args:
            event: Alert event to send
            
        Returns:
            Status of each notification
        """
        results = {}
        
        for channel, notifier in self.notifiers.items():
            try:
                result = await notifier.send_alert(event)
                results[channel] = result
            except NotificationError as exc:
                results[channel] = {
                    "status": "failed",
                    "error": str(exc),
                }
        
        return results
