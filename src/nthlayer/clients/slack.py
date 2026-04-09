"""
Re-export shim — canonical source is nthlayer_common.clients.slack.

The class was renamed to SlackAPIClient in common to avoid collision with
nthlayer_common.slack.SlackNotifier (the webhook-based notifier).
This shim preserves the original name for backward compatibility.
"""

from nthlayer_common.clients.slack import SlackAPIClient as SlackNotifier  # noqa: F401

__all__ = ["SlackNotifier"]
