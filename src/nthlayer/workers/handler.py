from __future__ import annotations

import asyncio
import json
import time
from typing import Any

import structlog

from nthlayer.clients import CortexClient, SlackNotifier
from nthlayer.config import Settings, get_settings
from nthlayer.db.repositories import RunRepository
from nthlayer.db.session import get_session, init_engine
from nthlayer.domain.models import RunStatus
from nthlayer.logging import configure_logging
from nthlayer.cloudwatch import get_metrics_collector
from nthlayer.providers import create_provider
from nthlayer.tracing import init_xray, trace_async
from nthlayer.workflows.team_reconcile import TeamReconcileState, TeamReconcileWorkflow

logger = structlog.get_logger()


@trace_async("process_job")
async def process_job(payload: dict[str, Any], settings: Settings) -> None:
    job_id = payload["job_id"]
    body = payload.get("payload", {})
    team_id = body["team_id"]

    log = logger.bind(job_id=job_id, team_id=team_id)
    metrics = get_metrics_collector("NthLayer", settings.aws_region)

    cortex_token = settings.cortex_token
    pagerduty_token = settings.pagerduty_token
    slack_token = settings.slack_bot_token

    pagerduty_provider = create_provider(
        "pagerduty",
        api_token=pagerduty_token,
        base_url=str(settings.pagerduty_base_url),
        timeout=settings.http_timeout,
        default_from=settings.pagerduty_from_email,
    )

    async for session in get_session():
        repo = RunRepository(session)
        start_ts = time.time()

        log.info("job_started")
        await metrics.emit("JobStarted", 1, JobType=payload.get("job_type", "unknown"))

        await repo.update_status(job_id, RunStatus.running, started_at=start_ts)
        await session.commit()

        workflow = TeamReconcileWorkflow(
            cortex=CortexClient(
                str(settings.cortex_base_url),
                cortex_token,
                timeout=settings.http_timeout,
                max_retries=settings.http_max_retries,
                backoff_factor=settings.http_retry_backoff_factor,
            ),
            pagerduty=pagerduty_provider,
            slack=SlackNotifier(
                slack_token,
                timeout=settings.http_timeout,
                max_retries=settings.http_max_retries,
                backoff_factor=settings.http_retry_backoff_factor,
            ),
            repository=repo,
        )

        state: TeamReconcileState = {
            "job_id": job_id,
            "team_id": team_id,
            "desired": body.get("desired"),
            "requested_by": payload.get("requested_by"),
            "slack_channel": body.get("slack_channel") or settings.slack_default_channel,
        }

        try:
            async with metrics.timer("JobDuration", JobType=payload.get("job_type", "unknown")):
                result_state = await workflow.run(state)
        except Exception as exc:  # pragma: no cover
            duration = time.time() - start_ts
            await repo.update_status(
                job_id,
                RunStatus.failed,
                finished_at=time.time(),
                failure_reason=str(exc),
            )
            await session.commit()
            log.error("job_failed", error=str(exc), duration=duration)
            await metrics.emit("JobFailed", 1, JobType=payload.get("job_type", "unknown"))
            raise
        else:
            duration = time.time() - start_ts
            await repo.update_status(
                job_id,
                RunStatus.succeeded,
                finished_at=time.time(),
                outcome=result_state.get("outcome"),
            )
            await session.commit()
            log.info("job_succeeded", outcome=result_state.get("outcome"), duration=duration)
            await metrics.emit("JobSucceeded", 1, JobType=payload.get("job_type", "unknown"))
        finally:
            break
    await pagerduty_provider.aclose()


async def handle_event(event: dict[str, Any], settings: Settings) -> dict[str, Any]:
    """
    Handle SQS event with partial batch failure support.
    Returns batchItemFailures for failed messages.
    """
    records = event.get("Records", [])
    failed_message_ids = []

    for record in records:
        message_id = record.get("messageId")
        try:
            payload = json.loads(record["body"])
            await process_job(payload, settings)
        except Exception as exc:
            logger.error(
                "message_processing_failed",
                message_id=message_id,
                error=str(exc),
            )
            failed_message_ids.append(message_id)

    return {"batchItemFailures": [{"itemIdentifier": msg_id} for msg_id in failed_message_ids]}


def lambda_handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    settings = get_settings()
    configure_logging()
    init_engine(settings)
    init_xray("nthlayer-worker")

    logger.info(
        "lambda_invoked",
        request_id=getattr(context, "aws_request_id", "unknown"),
        record_count=len(event.get("Records", [])),
    )

    return asyncio.run(handle_event(event, settings))
