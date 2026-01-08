"""Tests for workers/handler.py.

Tests for SQS Lambda handler including job processing,
event handling, and partial batch failure support.
"""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from nthlayer.workers.handler import (
    handle_event,
    lambda_handler,
    process_job,
)


@pytest.fixture
def mock_settings():
    """Create mock settings for testing."""
    settings = MagicMock()
    settings.aws_region = "us-east-1"
    settings.cortex_token = "test-cortex-token"
    settings.pagerduty_token = "test-pd-token"
    settings.slack_bot_token = "test-slack-token"
    settings.pagerduty_base_url = "https://api.pagerduty.com"
    settings.cortex_base_url = "https://api.cortex.io"
    settings.http_timeout = 30
    settings.http_max_retries = 3
    settings.http_retry_backoff_factor = 1.0
    settings.pagerduty_from_email = "test@example.com"
    settings.slack_default_channel = "#alerts"
    return settings


@pytest.fixture
def sample_payload():
    """Create a sample job payload."""
    return {
        "job_id": "job-123",
        "job_type": "team_reconcile",
        "requested_by": "user@example.com",
        "payload": {
            "team_id": "team-456",
            "desired": {"name": "Platform Team"},
            "slack_channel": "#platform",
        },
    }


@pytest.fixture
def sample_sqs_event(sample_payload):
    """Create a sample SQS event."""
    return {
        "Records": [
            {
                "messageId": "msg-001",
                "body": json.dumps(sample_payload),
            }
        ]
    }


class TestProcessJob:
    """Tests for process_job function."""

    @pytest.mark.asyncio
    @patch("nthlayer.workers.handler.create_provider")
    @patch("nthlayer.workers.handler.get_session")
    @patch("nthlayer.workers.handler.get_metrics_collector")
    async def test_successful_job(
        self,
        mock_metrics,
        mock_get_session,
        mock_create_provider,
        mock_settings,
        sample_payload,
    ):
        """Test successful job processing."""
        # Setup mocks
        mock_metrics_instance = MagicMock()
        mock_metrics_instance.emit = AsyncMock()
        mock_metrics_instance.timer = MagicMock(return_value=AsyncMock())
        mock_metrics.return_value = mock_metrics_instance

        mock_session = AsyncMock()
        mock_session.commit = AsyncMock()

        async def session_generator():
            yield mock_session

        mock_get_session.return_value = session_generator()

        mock_repo = MagicMock()
        mock_repo.update_status = AsyncMock()

        mock_provider = AsyncMock()
        mock_provider.aclose = AsyncMock()
        mock_create_provider.return_value = mock_provider

        mock_workflow = MagicMock()
        mock_workflow.run = AsyncMock(return_value={"outcome": "success"})

        with patch("nthlayer.workers.handler.RunRepository", return_value=mock_repo):
            with patch(
                "nthlayer.workers.handler.TeamReconcileWorkflow", return_value=mock_workflow
            ):
                with patch("nthlayer.workers.handler.CortexClient"):
                    with patch("nthlayer.workers.handler.SlackNotifier"):
                        await process_job(sample_payload, mock_settings)

        # Verify workflow was run
        mock_workflow.run.assert_called_once()

    @pytest.mark.asyncio
    @patch("nthlayer.workers.handler.create_provider")
    @patch("nthlayer.workers.handler.get_session")
    @patch("nthlayer.workers.handler.get_metrics_collector")
    async def test_job_uses_default_slack_channel(
        self,
        mock_metrics,
        mock_get_session,
        mock_create_provider,
        mock_settings,
    ):
        """Test job uses default slack channel when not provided."""
        payload = {
            "job_id": "job-123",
            "payload": {
                "team_id": "team-456",
            },
        }

        mock_metrics_instance = MagicMock()
        mock_metrics_instance.emit = AsyncMock()
        mock_metrics_instance.timer = MagicMock(return_value=AsyncMock())
        mock_metrics.return_value = mock_metrics_instance

        mock_session = AsyncMock()
        mock_session.commit = AsyncMock()

        async def session_generator():
            yield mock_session

        mock_get_session.return_value = session_generator()

        mock_repo = MagicMock()
        mock_repo.update_status = AsyncMock()

        mock_provider = AsyncMock()
        mock_provider.aclose = AsyncMock()
        mock_create_provider.return_value = mock_provider

        mock_workflow = MagicMock()
        mock_workflow.run = AsyncMock(return_value={"outcome": "success"})

        with patch("nthlayer.workers.handler.RunRepository", return_value=mock_repo):
            with patch(
                "nthlayer.workers.handler.TeamReconcileWorkflow", return_value=mock_workflow
            ):
                with patch("nthlayer.workers.handler.CortexClient"):
                    with patch("nthlayer.workers.handler.SlackNotifier"):
                        await process_job(payload, mock_settings)

        # Verify the state passed to workflow includes default channel
        call_args = mock_workflow.run.call_args[0][0]
        assert call_args["slack_channel"] == "#alerts"


class TestHandleEvent:
    """Tests for handle_event function."""

    @pytest.mark.asyncio
    @patch("nthlayer.workers.handler.process_job")
    async def test_successful_event_handling(
        self, mock_process_job, mock_settings, sample_sqs_event
    ):
        """Test successful event handling."""
        mock_process_job.return_value = None

        result = await handle_event(sample_sqs_event, mock_settings)

        assert result == {"batchItemFailures": []}
        mock_process_job.assert_called_once()

    @pytest.mark.asyncio
    @patch("nthlayer.workers.handler.process_job")
    async def test_empty_event(self, mock_process_job, mock_settings):
        """Test handling empty event."""
        result = await handle_event({"Records": []}, mock_settings)

        assert result == {"batchItemFailures": []}
        mock_process_job.assert_not_called()

    @pytest.mark.asyncio
    @patch("nthlayer.workers.handler.process_job")
    async def test_partial_batch_failure(self, mock_process_job, mock_settings):
        """Test partial batch failure handling."""
        event = {
            "Records": [
                {
                    "messageId": "msg-001",
                    "body": json.dumps({"job_id": "1", "payload": {"team_id": "t1"}}),
                },
                {
                    "messageId": "msg-002",
                    "body": json.dumps({"job_id": "2", "payload": {"team_id": "t2"}}),
                },
                {
                    "messageId": "msg-003",
                    "body": json.dumps({"job_id": "3", "payload": {"team_id": "t3"}}),
                },
            ]
        }

        # Second message fails
        mock_process_job.side_effect = [None, Exception("Failed"), None]

        result = await handle_event(event, mock_settings)

        assert result == {"batchItemFailures": [{"itemIdentifier": "msg-002"}]}

    @pytest.mark.asyncio
    @patch("nthlayer.workers.handler.process_job")
    async def test_all_messages_fail(self, mock_process_job, mock_settings):
        """Test when all messages fail."""
        event = {
            "Records": [
                {
                    "messageId": "msg-001",
                    "body": json.dumps({"job_id": "1", "payload": {"team_id": "t1"}}),
                },
                {
                    "messageId": "msg-002",
                    "body": json.dumps({"job_id": "2", "payload": {"team_id": "t2"}}),
                },
            ]
        }

        mock_process_job.side_effect = Exception("All failed")

        result = await handle_event(event, mock_settings)

        assert len(result["batchItemFailures"]) == 2
        assert {"itemIdentifier": "msg-001"} in result["batchItemFailures"]
        assert {"itemIdentifier": "msg-002"} in result["batchItemFailures"]

    @pytest.mark.asyncio
    @patch("nthlayer.workers.handler.process_job")
    async def test_invalid_json_body(self, mock_process_job, mock_settings):
        """Test handling invalid JSON in message body."""
        event = {
            "Records": [
                {"messageId": "msg-001", "body": "invalid json"},
            ]
        }

        result = await handle_event(event, mock_settings)

        assert result == {"batchItemFailures": [{"itemIdentifier": "msg-001"}]}
        mock_process_job.assert_not_called()


class TestLambdaHandler:
    """Tests for lambda_handler function."""

    @patch("nthlayer.workers.handler.asyncio.run")
    @patch("nthlayer.workers.handler.init_xray")
    @patch("nthlayer.workers.handler.init_engine")
    @patch("nthlayer.workers.handler.configure_logging")
    @patch("nthlayer.workers.handler.get_settings")
    def test_lambda_handler_setup(
        self,
        mock_get_settings,
        mock_configure_logging,
        mock_init_engine,
        mock_init_xray,
        mock_asyncio_run,
        mock_settings,
        sample_sqs_event,
    ):
        """Test lambda handler setup."""
        mock_get_settings.return_value = mock_settings
        mock_asyncio_run.return_value = {"batchItemFailures": []}

        mock_context = MagicMock()
        mock_context.aws_request_id = "req-123"

        result = lambda_handler(sample_sqs_event, mock_context)

        mock_get_settings.assert_called_once()
        mock_configure_logging.assert_called_once()
        mock_init_engine.assert_called_once_with(mock_settings)
        mock_init_xray.assert_called_once_with("nthlayer-worker")
        assert result == {"batchItemFailures": []}

    @patch("nthlayer.workers.handler.asyncio.run")
    @patch("nthlayer.workers.handler.init_xray")
    @patch("nthlayer.workers.handler.init_engine")
    @patch("nthlayer.workers.handler.configure_logging")
    @patch("nthlayer.workers.handler.get_settings")
    def test_lambda_handler_no_context_request_id(
        self,
        mock_get_settings,
        mock_configure_logging,
        mock_init_engine,
        mock_init_xray,
        mock_asyncio_run,
        mock_settings,
        sample_sqs_event,
    ):
        """Test lambda handler with no request ID in context."""
        mock_get_settings.return_value = mock_settings
        mock_asyncio_run.return_value = {"batchItemFailures": []}

        mock_context = MagicMock(spec=[])  # No aws_request_id attribute

        result = lambda_handler(sample_sqs_event, mock_context)

        assert result == {"batchItemFailures": []}

    @patch("nthlayer.workers.handler.asyncio.run")
    @patch("nthlayer.workers.handler.init_xray")
    @patch("nthlayer.workers.handler.init_engine")
    @patch("nthlayer.workers.handler.configure_logging")
    @patch("nthlayer.workers.handler.get_settings")
    def test_lambda_handler_empty_records(
        self,
        mock_get_settings,
        mock_configure_logging,
        mock_init_engine,
        mock_init_xray,
        mock_asyncio_run,
        mock_settings,
    ):
        """Test lambda handler with empty records."""
        mock_get_settings.return_value = mock_settings
        mock_asyncio_run.return_value = {"batchItemFailures": []}

        mock_context = MagicMock()

        result = lambda_handler({}, mock_context)

        assert result == {"batchItemFailures": []}
