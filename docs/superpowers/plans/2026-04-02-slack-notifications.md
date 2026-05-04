# Slack Notifications Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Send 6 Slack messages per incident lifecycle (breach → correlation → triage → remediation → verification → resolution), threaded via `slack_thread_ts` in verdict metadata.

**Architecture:** Shared `SlackNotifier` transport in nthlayer-common. Component-specific block builders in measure, correlate, respond. Thread parent is the breach notification; downstream components walk verdict lineage to find `slack_thread_ts`. Fail-open throughout.

**Tech Stack:** Python 3.11+, httpx, Slack Block Kit, pytest

**Spec:** `docs/superpowers/specs/2026-04-02-slack-notifications-design.md`

---

## File Structure

```
nthlayer-common/src/nthlayer_common/
└── slack.py                     # NEW — SlackNotifier transport

nthlayer-measure/src/nthlayer_measure/
├── notifications.py             # NEW — build_breach_blocks()
└── cli.py                       # MODIFY — send Slack after breach verdict

nthlayer-correlate/src/nthlayer_correlate/
├── notifications.py             # NEW — build_correlation_blocks()
└── cli.py                       # MODIFY — send Slack after correlation verdict

nthlayer-respond/src/nthlayer_respond/
├── notifications.py             # NEW — build_triage/remediation/verification/resolution blocks
└── coordinator.py               # MODIFY — send Slack after each verdict emission

tests/ (per component)
├── test_slack.py                # nthlayer-common
├── test_notifications.py        # each component
```

---

### Task 1: SlackNotifier transport in nthlayer-common

**Files:**
- Create: `nthlayer-common/src/nthlayer_common/slack.py`
- Modify: `nthlayer-common/src/nthlayer_common/__init__.py`
- Create: `nthlayer-common/tests/test_slack.py`

- [ ] **Step 1: Write tests**

```python
"""Tests for SlackNotifier transport."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from nthlayer_common.slack import SlackNotifier


class TestSlackNotifier:
    @pytest.mark.asyncio
    async def test_send_success_returns_thread_ts(self):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"ok": True, "ts": "1234567890.123456"}
        mock_resp.raise_for_status = MagicMock()

        with patch("nthlayer_common.slack.httpx.AsyncClient") as mock_cls:
            mock_client = AsyncMock()
            mock_client.post = AsyncMock(return_value=mock_resp)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_cls.return_value = mock_client

            notifier = SlackNotifier("https://hooks.slack.com/test")
            ts = await notifier.send([{"type": "section", "text": {"type": "mrkdwn", "text": "test"}}], "test")

        assert ts == "1234567890.123456"

    @pytest.mark.asyncio
    async def test_send_with_thread_ts(self):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"ok": True, "ts": "999"}
        mock_resp.raise_for_status = MagicMock()

        with patch("nthlayer_common.slack.httpx.AsyncClient") as mock_cls:
            mock_client = AsyncMock()
            mock_client.post = AsyncMock(return_value=mock_resp)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_cls.return_value = mock_client

            notifier = SlackNotifier("https://hooks.slack.com/test")
            await notifier.send([], "test", thread_ts="parent_ts")

        call_body = mock_client.post.call_args.kwargs.get("json") or mock_client.post.call_args[1].get("json")
        assert call_body["thread_ts"] == "parent_ts"

    @pytest.mark.asyncio
    async def test_send_failure_returns_none(self):
        with patch("nthlayer_common.slack.httpx.AsyncClient") as mock_cls:
            mock_client = AsyncMock()
            mock_client.post = AsyncMock(side_effect=Exception("connection refused"))
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_cls.return_value = mock_client

            notifier = SlackNotifier("https://hooks.slack.com/test")
            ts = await notifier.send([], "test")

        assert ts is None  # fail-open

    @pytest.mark.asyncio
    async def test_no_webhook_url_returns_none(self):
        notifier = SlackNotifier("")
        ts = await notifier.send([], "test")
        assert ts is None
```

- [ ] **Step 2: Implement SlackNotifier**

Create `nthlayer-common/src/nthlayer_common/slack.py`:

```python
"""Slack notification transport — Block Kit messages via incoming webhook."""
from __future__ import annotations

import logging
from typing import Any

import httpx

logger = logging.getLogger(__name__)


class SlackNotifier:
    """Send Slack Block Kit messages via incoming webhook.

    Fail-open: if Slack is unreachable, log a warning and return None.
    Never block the incident pipeline for a notification failure.
    """

    def __init__(self, webhook_url: str) -> None:
        self.webhook_url = webhook_url

    async def send(
        self,
        blocks: list[dict[str, Any]],
        text: str,
        thread_ts: str | None = None,
    ) -> str | None:
        """Post a Slack message. Returns thread_ts for threading.

        Returns None if sending fails or webhook_url is empty.
        """
        if not self.webhook_url:
            return None

        payload: dict[str, Any] = {
            "text": text,
            "blocks": blocks,
        }
        if thread_ts:
            payload["thread_ts"] = thread_ts

        try:
            async with httpx.AsyncClient() as client:
                resp = await client.post(
                    self.webhook_url,
                    json=payload,
                    timeout=10.0,
                )
                resp.raise_for_status()
                data = resp.json() if resp.headers.get("content-type", "").startswith("application/json") else {}
                return data.get("ts")
        except Exception as exc:
            logger.warning("Slack notification failed: %s", exc)
            return None
```

Add to `__init__.py`:
```python
from nthlayer_common.slack import SlackNotifier
```

- [ ] **Step 3: Run tests**

Run: `cd /Users/robfox/Documents/GitHub/nthlayer-ecosystem/nthlayer-common && uv sync --extra dev && uv run pytest tests/test_slack.py -v`

- [ ] **Step 4: Commit**

```bash
git add src/nthlayer_common/slack.py src/nthlayer_common/__init__.py tests/test_slack.py
git commit -m "feat: SlackNotifier transport — Block Kit messages via webhook, fail-open"
```

---

### Task 2: Block builders + integration in nthlayer-measure

**Files:**
- Create: `nthlayer-measure/src/nthlayer_measure/notifications.py`
- Modify: `nthlayer-measure/src/nthlayer_measure/cli.py` (after `verdict_store.put(v)` in evaluate-once)

- [ ] **Step 1: Create block builder**

Create `nthlayer-measure/src/nthlayer_measure/notifications.py`:

```python
"""Slack block builders for nthlayer-measure verdicts."""
from __future__ import annotations


def build_breach_blocks(verdict) -> tuple[list[dict], str]:
    """Build Slack blocks for SLO breach notification."""
    custom = getattr(verdict.metadata, "custom", {}) or {}
    service = verdict.subject.ref or "unknown"
    slo_name = custom.get("slo_name", "SLO")
    current = custom.get("current_value")
    target = custom.get("target")
    consecutive = custom.get("consecutive")
    confidence = verdict.judgment.confidence

    current_pct = f"{current * 100:.1f}%" if current is not None else "?"
    target_pct = f"{target * 100:.1f}%" if target is not None else "?"

    text = f"\u26a0 SLO breach: {service} {slo_name} {current_pct} (target <{target_pct})"

    blocks = [
        {
            "type": "section",
            "text": {"type": "mrkdwn", "text": f"*\u26a0 SLO BREACH \u00b7 {service}*"},
        },
        {
            "type": "section",
            "text": {"type": "mrkdwn", "text": (
                f"*{slo_name}:* {current_pct} (target <{target_pct})\n"
                + (f"Consecutive breaches: {consecutive}\n" if consecutive else "")
                + "NthLayer detected AI decision quality degradation."
            )},
        },
        {
            "type": "context",
            "elements": [
                {"type": "mrkdwn", "text": f"nthlayer-measure \u00b7 confidence {confidence:.2f} \u00b7 {verdict.id}"},
            ],
        },
    ]

    return blocks, text
```

- [ ] **Step 2: Wire into evaluate-once CLI**

In `nthlayer-measure/src/nthlayer_measure/cli.py`, find the evaluate-once section where `verdict_store.put(v)` is called (around line 184). After it, add:

```python
            # Slack notification for breach verdicts
            if r.breach:
                import os
                slack_url = os.environ.get("SLACK_WEBHOOK_URL", "")
                if slack_url:
                    from nthlayer_common.slack import SlackNotifier
                    from nthlayer_measure.notifications import build_breach_blocks
                    import asyncio

                    blocks, text = build_breach_blocks(v)
                    notifier = SlackNotifier(slack_url)
                    thread_ts = asyncio.run(notifier.send(blocks, text))
                    if thread_ts:
                        # Store thread_ts for downstream threading
                        v.metadata.custom["slack_thread_ts"] = thread_ts
                        verdict_store.put(v)  # re-save with thread_ts
```

Note: `evaluate_slos` is called inside an `asyncio.run(_run())` context. The Slack send needs to be awaited inside that context. Read the actual code structure to determine if we need `await` vs `asyncio.run()`.

- [ ] **Step 3: Run tests**

Run: `cd /Users/robfox/Documents/GitHub/nthlayer-ecosystem/nthlayer-measure && uv run --no-sync pytest tests/ --tb=short`

- [ ] **Step 4: Commit**

```bash
git add src/nthlayer_measure/notifications.py src/nthlayer_measure/cli.py
git commit -m "feat: Slack breach notification from evaluate-once with thread_ts storage"
```

---

### Task 3: Block builder + integration in nthlayer-correlate

**Files:**
- Create: `nthlayer-correlate/src/nthlayer_correlate/notifications.py`
- Modify: `nthlayer-correlate/src/nthlayer_correlate/cli.py` (after `verdict_store.put(corr_verdict)`)

- [ ] **Step 1: Create block builder**

Create `nthlayer-correlate/src/nthlayer_correlate/notifications.py`:

```python
"""Slack block builders for nthlayer-correlate verdicts."""
from __future__ import annotations


def build_correlation_blocks(verdict) -> tuple[list[dict], str]:
    """Build Slack blocks for root cause identification."""
    custom = getattr(verdict.metadata, "custom", {}) or {}
    service = verdict.subject.ref or "unknown"
    root_causes = custom.get("root_causes", [])
    blast_radius = custom.get("blast_radius", [])
    confidence = verdict.judgment.confidence

    rc_text = root_causes[0].get("service", "unknown") if root_causes else "under investigation"
    blast_count = len(blast_radius)

    text = f"\U0001f50d Root cause: {rc_text} \u2014 {blast_count} services in blast radius"

    blocks = [
        {
            "type": "section",
            "text": {"type": "mrkdwn", "text": f"*\U0001f50d ROOT CAUSE IDENTIFIED \u00b7 {service}*"},
        },
        {
            "type": "section",
            "text": {"type": "mrkdwn", "text": (
                f"*Root cause:* {rc_text}\n"
                f"*Blast radius:* {blast_count} services \u2014 "
                + ", ".join(b.get("service", b) if isinstance(b, dict) else b for b in blast_radius[:5])
            )},
        },
        {
            "type": "context",
            "elements": [
                {"type": "mrkdwn", "text": f"nthlayer-correlate \u00b7 confidence {confidence:.2f} \u00b7 {verdict.id}"},
            ],
        },
    ]

    return blocks, text
```

- [ ] **Step 2: Wire into correlate CLI**

In `nthlayer-correlate/src/nthlayer_correlate/cli.py`, after `verdict_store.put(corr_verdict)` (around line 587), add Slack notification with thread_ts lookup from the trigger verdict's lineage.

- [ ] **Step 3: Run tests and commit**

---

### Task 4: Block builders + integration in nthlayer-respond

**Files:**
- Create: `nthlayer-respond/src/nthlayer_respond/notifications.py`
- Modify: `nthlayer-respond/src/nthlayer_respond/coordinator.py`

- [ ] **Step 1: Create block builders**

Create `nthlayer-respond/src/nthlayer_respond/notifications.py` with 4 functions:
- `build_triage_blocks(verdict, context)` — SEV-N, blast radius, team
- `build_remediation_blocks(verdict, context)` — action, target, approval status
- `build_verification_blocks(verdict, context)` — verified true/false, detail
- `build_resolution_blocks(verdict, context)` — resolved, full chain summary
- `find_slack_thread_ts(verdict_store, verdict_ids)` — walk lineage to find thread_ts

- [ ] **Step 2: Wire into coordinator**

After each `_emit_verdict` call in the coordinator pipeline, check `SLACK_WEBHOOK_URL` and send the appropriate block message as a thread reply.

- [ ] **Step 3: Run full test suite and commit**

---

### Task 5: Full verification + push

- [ ] **Step 1: Run all 4 component test suites**

```bash
cd nthlayer-common && uv run pytest tests/ -v
cd nthlayer-measure && uv run --no-sync pytest tests/ -v
cd nthlayer-correlate && uv run pytest tests/ -v
cd nthlayer-respond && uv run --extra dev pytest tests/ -v
```

- [ ] **Step 2: Push all repos**

- [ ] **Step 3: Close bead opensrm-2gg.2**

---

## Verification Checklist

1. `SLACK_WEBHOOK_URL` not set → no Slack messages, no errors, all tests pass
2. Mock Slack in tests → verify block structure and thread_ts propagation
3. Thread propagation → correlate and respond find thread_ts from measure's breach verdict
4. Graceful fallback → respond starts new thread when thread_ts not in lineage
5. All existing tests pass unchanged
