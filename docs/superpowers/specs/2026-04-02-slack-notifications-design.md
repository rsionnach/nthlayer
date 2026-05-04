# Slack Notification Design — Incident Lifecycle Messages

**Date:** 2026-04-02
**Beads:** opensrm-2gg.2 (Slack notifications), partially opensrm-2gg.1 (notification config)
**Status:** Design approved, ready for implementation plan

## Problem

NthLayer detects incidents, correlates root causes, and remediates — but the on-call engineer only knows if they're watching the terminal or the demo page. Slack is where teams live during incidents. Without Slack integration, NthLayer's value is invisible to the people who need it most.

## Design

### 6-Message Incident Lifecycle

Each incident produces up to 6 Slack messages, all in a single thread:

| # | Source | Trigger | Message | Color |
|---|--------|---------|---------|-------|
| 1 | nthlayer-measure | Evaluation breach detected | "⚠ SLO breach: fraud-detect reversal rate 2.7% (target <1.5%)" | Red |
| 2 | nthlayer-correlate | Correlation verdict | "🔍 Root cause: fraud-detect — 2 services in blast radius" | Yellow |
| 3 | nthlayer-respond | Triage verdict | "🚨 Incident opened: SEV-1 — AI model quality degradation" | Red |
| 4 | nthlayer-respond | Remediation proposed | "🔧 Remediation: rollback fraud-detect (awaiting approval)" | Orange |
| 5 | nthlayer-respond | Remediation verified/failed | "✅ Verified: error rate 0.3%" or "❌ Verification failed" | Green/Red |
| 6 | nthlayer-respond | Incident resolved | "✅ Incident resolved — full chain in NthLayer" | Green |

### Threading Model

Message 1 (breach notification) is the **thread parent**. It fires before an incident ID exists — it's nthlayer-measure detecting a breach, not nthlayer-respond opening an incident.

All subsequent messages (2-6) reply to the thread started by message 1.

**Thread propagation via verdict metadata:**

When message 1 is sent, the Slack API returns a `ts` (timestamp) that serves as the thread ID. This is stored in the evaluation verdict's `metadata.custom.slack_thread_ts`.

Each downstream component (correlate, respond) walks the trigger verdict's lineage to find the earliest verdict with `slack_thread_ts` and uses it for threading.

```
measure sends breach → Slack returns ts → stored in evaluation verdict metadata
correlate reads evaluation verdict → gets slack_thread_ts → replies to thread
respond reads correlation verdict → walks lineage → gets slack_thread_ts → replies to thread
```

**Graceful degradation:** If the thread is lost (measure didn't have Slack configured, breach detected via a different path, or lineage walk fails), respond falls back to posting a new top-level message and starting a new thread from message 3. Not a hard failure.

### Shared Transport: nthlayer-common

New file: `nthlayer-common/src/nthlayer_common/slack.py`

Slim transport layer (~60 lines):

```python
class SlackNotifier:
    """Send Slack Block Kit messages via incoming webhook."""

    def __init__(self, webhook_url: str):
        self.webhook_url = webhook_url

    async def send(self, blocks: list[dict], text: str,
                   thread_ts: str | None = None) -> str | None:
        """Post message. Returns thread_ts for threading.
        Returns None if sending fails (fail-open)."""
```

Uses httpx. Fail-open — if Slack is unreachable, log a warning and continue. Never block the incident pipeline for a notification failure.

The existing `SlackNotifier` in `nthlayer/src/nthlayer/slos/notifiers.py` stays as-is for now (it has SLO-specific formatting). Future consolidation can merge them, but that's a separate task.

### Component-Specific Block Builders

Each component builds its own Slack blocks from verdict data. The blocks are the judgment-specific formatting; the transport (`SlackNotifier.send()`) is shared.

**nthlayer-measure** (`measure/src/nthlayer_measure/notifications.py`):
```python
def build_breach_blocks(verdict) -> tuple[list[dict], str]:
    """Build Slack blocks for SLO breach notification.
    Returns (blocks, fallback_text)."""
```

**nthlayer-correlate** (`correlate/src/nthlayer_correlate/notifications.py`):
```python
def build_correlation_blocks(verdict) -> tuple[list[dict], str]:
    """Build Slack blocks for root cause identification."""
```

**nthlayer-respond** (`respond/src/nthlayer_respond/notifications.py`):
```python
def build_triage_blocks(verdict, context) -> tuple[list[dict], str]:
def build_remediation_blocks(verdict, context) -> tuple[list[dict], str]:
def build_verification_blocks(verdict, context) -> tuple[list[dict], str]:
def build_resolution_blocks(verdict, context) -> tuple[list[dict], str]:
```

### Configuration

**Environment variable:** `SLACK_WEBHOOK_URL` — the Slack incoming webhook URL. If not set, Slack notifications are silently skipped (fail-open).

**CLI flag:** `--notify` on each CLI command already exists in nthlayer-respond. Extend the pattern:
- `--notify stdout` — print to stdout (default, existing)
- `--notify slack` — send to Slack using `SLACK_WEBHOOK_URL`
- `--notify https://custom-webhook.com` — POST to custom webhook (existing)

**Manifest hint:** The OpenSRM spec `ownership.slack` field (e.g., `"#payments-oncall"`) is included in the Slack message as context but is NOT used for routing (the webhook URL determines the channel). This is intentional — the webhook is configured per environment, not per service.

### Slack Block Kit Message Format

Each message follows a consistent structure:

```
┌─ [COLOR BAR] ────────────────────────────────────┐
│                                                    │
│  ⚠ SLO BREACH · fraud-detect                     │
│                                                    │
│  reversal_rate: 2.7% (target <1.5%)              │
│  Consecutive breaches: 2                           │
│                                                    │
│  NthLayer detected AI decision quality             │
│  degradation on this judgment SLO.                 │
│                                                    │
│  ┌──────────────┐                                 │
│  │ View in Demo │                                 │
│  └──────────────┘                                 │
│                                                    │
│  nthlayer-measure · confidence 0.85               │
│  INC-FRAUD-20260402 · 16:29:03                    │
│                                                    │
└────────────────────────────────────────────────────┘
```

Blocks:
1. **Header section** — emoji + verdict type + service name
2. **Detail section** — key metrics from `verdict.metadata.custom`
3. **Context section** — human-readable explanation (same curated text as guided demo cards)
4. **Action button** — "View in Demo" linking to `?mode=guided&step=N` or Grafana dashboard
5. **Footer context** — producer, confidence, incident ID, timestamp

### Integration Points

**nthlayer-measure (evaluate-once CLI):**
After writing a breach evaluation verdict, check `SLACK_WEBHOOK_URL`. If set, build blocks and send. Store returned `thread_ts` in `verdict.metadata.custom.slack_thread_ts`.

**nthlayer-correlate (correlate CLI):**
After writing correlation verdict, walk lineage to find `slack_thread_ts` from the trigger evaluation verdict. Build blocks and send as thread reply.

**nthlayer-respond (coordinator):**
After each verdict emission in the pipeline (triage, remediation, resolution), walk lineage to find `slack_thread_ts`. Build blocks and send as thread reply. If thread not found, start new thread and store `slack_thread_ts` on the triage verdict.

### What Doesn't Change

- Incident pipeline (coordinator, agents, approval flow) — notification is a side-effect, not blocking
- Verdict store — `slack_thread_ts` is just another field in `metadata.custom`
- Demo infrastructure — no changes to demo.sh or verdict-feed
- Existing `--notify` webhook behavior — still works alongside Slack

## Verification

1. `SLACK_WEBHOOK_URL` not set → no Slack messages, no errors, pipeline runs normally
2. `SLACK_WEBHOOK_URL` set → 6 messages in a single thread over the course of an incident
3. Thread propagation → message 3 (triage) replies to message 1's thread
4. Slack unreachable → warning logged, pipeline continues (fail-open)
5. Thread lost (measure didn't send) → respond starts new thread from message 3
6. All existing tests pass unchanged (Slack is opt-in, not in test path)
