# NthLayer: Respond Communications & On-Call Spec

**Status:** Proposal  
**Author:** Rob  
**Date:** 2026-04-02  
**Depends on:** Existing respond coordinator, incident verdict schema, OpenSRM manifest ownership block  
**Context:** Grafana OnCall OSS archived 2026-03-24. Keep acquired by Elastic. Open-source on-call space has no credible standalone tool. NthLayer fills this gap with schedule-as-code and Slack-first paging.

---

## Design Principles

1. **Schedule is spec.** On-call rotation is declared in the OpenSRM manifest alongside SLOs, ownership, and dependencies. No separate UI, no separate tool. Your schedule lives in Git, gets validated by `nthlayer validate`, and is the single source of truth.

2. **Slack is the pager.** For 90% of incidents, a Slack DM with interactive buttons is sufficient. Slack is already on every engineer's phone. NthLayer doesn't build a mobile app.

3. **ntfy is the siren.** For critical escalations where Slack notifications might be missed (3am, phone on silent), ntfy provides DND-override push notifications. Self-hosted, open source, one Docker container.

4. **Phone calls are optional.** Twilio (or Fonoster for self-hosted) is available as a last-resort escalation for teams that need voice calls. It's an adapter, not a core dependency.

5. **Adapters, not integrations.** Every notification channel is a `NotificationBackend` protocol implementation. Adding a new channel is one file. The escalation engine doesn't know or care about delivery mechanisms.

---

## Non-Goals

- No web UI for schedule management. The manifest is the UI. Edit YAML, open a PR.
- No mobile app. Slack and ntfy are the mobile apps.
- No shift swap workflows. Edit the overrides array in the manifest.
- No competing with PagerDuty's Event Intelligence. NthLayer's correlation happens in nthlayer-correlate, not in the paging layer.
- No bidirectional sync with PagerDuty. PagerDuty is a thin webhook-out target for teams that need it, not an integration partner.

---

## Part 1: Manifest Schema Extension

### 1.1 On-Call Block

The manifest's `spec.ownership` gains an `oncall` block. This is optional — teams without on-call schedules still get Slack channel notifications as before.

```yaml
apiVersion: opensrm.io/v1
kind: ServiceReliabilityManifest
metadata:
  name: fraud-detect
  tier: critical

spec:
  type: ai-gate
  
  ownership:
    team: ml-platform
    slack_channel: "#ml-platform-oncall"
    
    oncall:
      timezone: "Europe/Dublin"
      
      # Rotation schedule
      rotation:
        type: weekly                    # weekly | daily | custom
        handoff: "monday 09:00"         # when rotation advances (in timezone above)
        roster:
          - name: Alice
            slack_id: U0123ALICE
            ntfy_topic: oncall-alice     # personal ntfy topic for DND-override
            phone: "+353851234567"       # optional, for Twilio voice escalation
          - name: Bob
            slack_id: U0456BOB
            ntfy_topic: oncall-bob
          - name: Charlie
            slack_id: U0789CHARLIE
            ntfy_topic: oncall-charlie
      
      # Manual overrides (holidays, swaps)
      overrides:
        - start: "2026-04-14T00:00:00Z"
          end: "2026-04-21T00:00:00Z"
          user: Bob                      # Bob covers Alice's week
          reason: "Alice on annual leave"
      
      # Escalation policy
      escalation:
        - after: 0m
          notify: slack_dm               # DM current on-call via Slack
        - after: 5m
          notify: ntfy                   # critical push, overrides DND
        - after: 10m
          notify: slack_dm
          target: next_oncall            # DM next person in rotation
        - after: 15m
          notify: ntfy
          target: next_oncall
        - after: 20m
          notify: slack_channel          # post to team channel, @here
        - after: 30m
          notify: phone                  # optional, Twilio voice call
          target: engineering_manager
          phone: "+353859876543"
```

### 1.2 Validation Rules

`nthlayer validate` checks:

- At least one person in the roster
- All `slack_id` values present (required for Slack DM)
- `ntfy_topic` present if any escalation step uses `notify: ntfy`
- `phone` present if any escalation step uses `notify: phone`
- Escalation steps are in ascending `after` order
- No duplicate `after` values
- Overrides don't overlap for the same user
- Timezone is a valid IANA timezone string

```bash
$ nthlayer validate service.reliability.yaml
✓ Schema valid
✓ On-call roster: 3 engineers
✓ Escalation policy: 6 steps, max wait 30m
✓ ntfy topics configured for all roster members
⚠ Phone escalation configured but TWILIO_ACCOUNT_SID not set (will skip phone steps at runtime)
```

---

## Part 2: Schedule Resolver

### 2.1 Core Function

Pure function. No state. No database. Given the oncall config and a timestamp, returns who is on call.

```python
# nthlayer-respond/src/nthlayer_respond/oncall/schedule.py

from dataclasses import dataclass
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo


@dataclass
class OnCallResult:
    """Who is on call right now."""
    primary: RosterMember           # current on-call
    secondary: RosterMember         # next in rotation (for escalation)
    rotation_handoff: datetime      # when primary's shift ends
    source: str                     # "rotation" | "override"


@dataclass
class RosterMember:
    name: str
    slack_id: str
    ntfy_topic: str | None
    phone: str | None


def resolve_oncall(oncall_config: dict, now: datetime) -> OnCallResult:
    """
    Determine who is on call at the given time.
    
    Algorithm:
    1. Check overrides first — if an override covers `now`, that person is primary
    2. Otherwise compute rotation position:
       - Parse handoff time and timezone
       - Calculate elapsed time since first handoff
       - Divide by rotation period (1 week for weekly, 1 day for daily)
       - Modulo roster length = current position
    3. Secondary is always the next person in rotation after primary
    """
    roster = [
        RosterMember(
            name=r["name"],
            slack_id=r["slack_id"],
            ntfy_topic=r.get("ntfy_topic"),
            phone=r.get("phone"),
        )
        for r in oncall_config["rotation"]["roster"]
    ]
    
    tz = ZoneInfo(oncall_config["timezone"])
    now_local = now.astimezone(tz)
    
    # Check overrides
    for override in oncall_config.get("overrides", []):
        override_start = datetime.fromisoformat(override["start"])
        override_end = datetime.fromisoformat(override["end"])
        if override_start <= now < override_end:
            override_user = next(
                m for m in roster if m.name == override["user"]
            )
            # Secondary: next person after override user in roster
            idx = roster.index(override_user)
            secondary = roster[(idx + 1) % len(roster)]
            return OnCallResult(
                primary=override_user,
                secondary=secondary,
                rotation_handoff=override_end,
                source="override",
            )
    
    # Compute rotation position
    rotation_type = oncall_config["rotation"]["type"]
    handoff_str = oncall_config["rotation"]["handoff"]  # e.g. "monday 09:00"
    
    period = _rotation_period(rotation_type)
    anchor = _compute_anchor(handoff_str, tz, now_local)
    
    elapsed = now_local - anchor
    if elapsed.total_seconds() < 0:
        # Before first handoff — first person in roster
        position = 0
    else:
        rotations_elapsed = int(elapsed.total_seconds() // period.total_seconds())
        position = rotations_elapsed % len(roster)
    
    primary = roster[position]
    secondary = roster[(position + 1) % len(roster)]
    
    # When does current rotation end?
    next_handoff = anchor + (period * (rotations_elapsed + 1)) if elapsed.total_seconds() >= 0 else anchor
    
    return OnCallResult(
        primary=primary,
        secondary=secondary,
        rotation_handoff=next_handoff.astimezone(tz),
        source="rotation",
    )


def _rotation_period(rotation_type: str) -> timedelta:
    if rotation_type == "weekly":
        return timedelta(weeks=1)
    elif rotation_type == "daily":
        return timedelta(days=1)
    raise ValueError(f"Unknown rotation type: {rotation_type}")


def _compute_anchor(handoff_str: str, tz: ZoneInfo, reference: datetime) -> datetime:
    """
    Compute the anchor datetime for rotation calculation.
    
    For "monday 09:00" with weekly rotation: find the most recent
    Monday 09:00 before or equal to reference, then walk back to
    the rotation epoch.
    """
    # Parse "monday 09:00" or "09:00" (for daily)
    parts = handoff_str.lower().split()
    if len(parts) == 2:
        day_name, time_str = parts
        day_map = {
            "monday": 0, "tuesday": 1, "wednesday": 2,
            "thursday": 3, "friday": 4, "saturday": 5, "sunday": 6,
        }
        target_weekday = day_map[day_name]
    else:
        time_str = parts[0]
        target_weekday = None
    
    hour, minute = map(int, time_str.split(":"))
    
    # Find the most recent handoff before reference
    candidate = reference.replace(hour=hour, minute=minute, second=0, microsecond=0)
    
    if target_weekday is not None:
        # Walk back to the target weekday
        days_back = (candidate.weekday() - target_weekday) % 7
        candidate -= timedelta(days=days_back)
    
    if candidate > reference:
        candidate -= _rotation_period("weekly" if target_weekday is not None else "daily")
    
    return candidate
```

### 2.2 CLI Command

```bash
# Who is on call right now?
$ nthlayer oncall --specs-dir ./specs/

fraud-detect:
  On-call: Alice (rotation, since Mon 09:00)
  Next: Bob
  Handoff: Mon Apr 07 09:00 IST

payment-api:
  On-call: Dave (override: "Dave covers Eve's holiday")
  Next: Frank
  Override ends: Sun Apr 13 23:59 IST
```

---

## Part 3: Notification Backends

### 3.1 Protocol

Same adapter pattern as traces and profiles.

```python
# nthlayer-respond/src/nthlayer_respond/notifications/protocol.py

from dataclasses import dataclass
from typing import Protocol


@dataclass
class NotificationPayload:
    """What to tell the human."""
    incident_id: str
    severity: int                       # 1 = P1 (critical), 2 = P2, etc.
    title: str                          # e.g. "fraud-detect reversal rate breach"
    summary: str                        # 2-3 sentence incident summary
    root_cause: str | None              # if known
    blast_radius: list[str]             # affected service names
    actions_url: str | None             # link to incident details / dashboard
    escalation_step: int                # which step in the policy triggered this
    requires_ack: bool                  # should we wait for acknowledgment?


@dataclass
class NotificationResult:
    """What happened when we tried to notify."""
    delivered: bool
    channel: str                        # "slack_dm" | "ntfy" | "phone" | etc.
    recipient: str                      # user name or identifier
    timestamp: datetime
    message_id: str | None              # for tracking ack on Slack messages
    error: str | None


class NotificationBackend(Protocol):
    """
    Protocol for all notification delivery mechanisms.
    Each backend handles one delivery channel.
    """
    
    async def send(
        self,
        recipient: "RosterMember",
        payload: NotificationPayload,
    ) -> NotificationResult:
        ...
    
    async def health_check(self) -> bool:
        ...
```

### 3.2 Slack Backend

Primary notification channel. Sends DMs with interactive buttons for acknowledge/escalate. Also posts to team channels.

```python
# nthlayer-respond/src/nthlayer_respond/notifications/slack.py

import os
import httpx

from .protocol import NotificationBackend, NotificationPayload, NotificationResult
from ..oncall.schedule import RosterMember


class SlackNotificationBackend:
    """
    Slack notification delivery.
    
    Two modes:
    - DM: sends a direct message to a specific user (slack_id)
    - Channel: posts to a Slack channel with @here
    
    Messages include interactive buttons (Acknowledge, Escalate)
    via Slack Block Kit. Button interactions are received by
    the webhook handler (Part 5).
    """
    
    def __init__(self, bot_token: str | None = None):
        self.bot_token = bot_token or os.environ["SLACK_BOT_TOKEN"]
        self._client = httpx.AsyncClient(
            headers={"Authorization": f"Bearer {self.bot_token}"},
            timeout=10,
        )
    
    async def send(
        self, recipient: RosterMember, payload: NotificationPayload
    ) -> NotificationResult:
        """Send a DM to the recipient."""
        blocks = self._build_incident_blocks(payload)
        
        response = await self._client.post(
            "https://slack.com/api/chat.postMessage",
            json={
                "channel": recipient.slack_id,
                "text": f"🔴 {payload.title}",  # fallback for notifications
                "blocks": blocks,
            },
        )
        data = response.json()
        
        return NotificationResult(
            delivered=data.get("ok", False),
            channel="slack_dm",
            recipient=recipient.name,
            timestamp=datetime.utcnow(),
            message_id=data.get("ts"),
            error=data.get("error"),
        )
    
    async def send_to_channel(
        self, channel: str, payload: NotificationPayload
    ) -> NotificationResult:
        """Post to a Slack channel with @here."""
        blocks = self._build_incident_blocks(payload, include_at_here=True)
        
        response = await self._client.post(
            "https://slack.com/api/chat.postMessage",
            json={
                "channel": channel,
                "text": f"<!here> 🔴 {payload.title}",
                "blocks": blocks,
            },
        )
        data = response.json()
        
        return NotificationResult(
            delivered=data.get("ok", False),
            channel="slack_channel",
            recipient=channel,
            timestamp=datetime.utcnow(),
            message_id=data.get("ts"),
            error=data.get("error"),
        )
    
    async def update_message(
        self, channel: str, message_ts: str, text: str
    ):
        """Update an existing Slack message (e.g., mark as acknowledged)."""
        await self._client.post(
            "https://slack.com/api/chat.update",
            json={
                "channel": channel,
                "ts": message_ts,
                "text": text,
            },
        )
    
    def _build_incident_blocks(
        self, payload: NotificationPayload, include_at_here: bool = False
    ) -> list[dict]:
        """Build Slack Block Kit blocks for incident notification."""
        severity_emoji = {1: "🔴", 2: "🟠", 3: "🟡", 4: "🔵"}.get(
            payload.severity, "⚪"
        )
        
        blocks = [
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": f"{severity_emoji} {payload.incident_id}: {payload.title}",
                },
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": payload.summary,
                },
            },
        ]
        
        # Root cause if known
        if payload.root_cause:
            blocks.append({
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*Root cause:* {payload.root_cause}",
                },
            })
        
        # Blast radius
        if payload.blast_radius:
            services = ", ".join(f"`{s}`" for s in payload.blast_radius)
            blocks.append({
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*Blast radius:* {services}",
                },
            })
        
        # Action buttons
        if payload.requires_ack:
            buttons = [
                {
                    "type": "button",
                    "text": {"type": "plain_text", "text": "Acknowledge"},
                    "style": "primary",
                    "action_id": "incident_ack",
                    "value": payload.incident_id,
                },
                {
                    "type": "button",
                    "text": {"type": "plain_text", "text": "Escalate"},
                    "style": "danger",
                    "action_id": "incident_escalate",
                    "value": payload.incident_id,
                },
            ]
            
            if payload.actions_url:
                buttons.append({
                    "type": "button",
                    "text": {"type": "plain_text", "text": "View Details"},
                    "url": payload.actions_url,
                    "action_id": "incident_view",
                })
            
            blocks.append({"type": "actions", "elements": buttons})
        
        return blocks
    
    async def health_check(self) -> bool:
        try:
            response = await self._client.post(
                "https://slack.com/api/auth.test"
            )
            return response.json().get("ok", False)
        except Exception:
            return False
```

### 3.3 ntfy Backend

DND-override push notifications. One HTTP POST per notification.

```python
# nthlayer-respond/src/nthlayer_respond/notifications/ntfy.py

import os
import httpx

from .protocol import NotificationBackend, NotificationPayload, NotificationResult
from ..oncall.schedule import RosterMember


class NtfyNotificationBackend:
    """
    ntfy push notification delivery.
    
    Sends high-priority notifications that override Do Not Disturb
    on Android (via notification channel config) and iOS (via
    interruption levels).
    
    Each roster member has a personal ntfy topic. The ntfy server
    can be self-hosted (single Docker container) or use ntfy.sh.
    """
    
    def __init__(
        self,
        server_url: str | None = None,
        auth_token: str | None = None,
    ):
        self.server_url = (
            server_url
            or os.environ.get("NTFY_SERVER_URL", "https://ntfy.sh")
        )
        self.auth_token = auth_token or os.environ.get("NTFY_AUTH_TOKEN")
        
        headers = {}
        if self.auth_token:
            headers["Authorization"] = f"Bearer {self.auth_token}"
        
        self._client = httpx.AsyncClient(headers=headers, timeout=10)
    
    async def send(
        self, recipient: RosterMember, payload: NotificationPayload
    ) -> NotificationResult:
        if not recipient.ntfy_topic:
            return NotificationResult(
                delivered=False,
                channel="ntfy",
                recipient=recipient.name,
                timestamp=datetime.utcnow(),
                message_id=None,
                error="No ntfy_topic configured for this user",
            )
        
        # Map incident severity to ntfy priority
        # P1 = max (overrides DND), P2 = urgent, P3 = high, P4 = default
        priority_map = {1: "max", 2: "urgent", 3: "high", 4: "default"}
        priority = priority_map.get(payload.severity, "high")
        
        title = f"{payload.incident_id}: {payload.title}"
        body = payload.summary
        if payload.root_cause:
            body += f"\nRoot cause: {payload.root_cause}"
        
        tags = ["rotating_light", "warning"]
        if payload.severity == 1:
            tags = ["rotating_light", "fire"]
        
        headers = {
            "Title": title,
            "Priority": priority,
            "Tags": ",".join(tags),
        }
        
        if payload.actions_url:
            headers["Click"] = payload.actions_url
        
        # Action buttons in ntfy
        if payload.requires_ack:
            actions = (
                f"http, Acknowledge, "
                f"{self._ack_webhook_url(payload.incident_id)}, "
                f"method=POST, clear=true"
            )
            headers["Actions"] = actions
        
        try:
            response = await self._client.post(
                f"{self.server_url}/{recipient.ntfy_topic}",
                content=body,
                headers=headers,
            )
            response.raise_for_status()
            data = response.json()
            
            return NotificationResult(
                delivered=True,
                channel="ntfy",
                recipient=recipient.name,
                timestamp=datetime.utcnow(),
                message_id=data.get("id"),
                error=None,
            )
        except Exception as e:
            return NotificationResult(
                delivered=False,
                channel="ntfy",
                recipient=recipient.name,
                timestamp=datetime.utcnow(),
                message_id=None,
                error=str(e),
            )
    
    def _ack_webhook_url(self, incident_id: str) -> str:
        """URL for the acknowledge webhook, called from ntfy action button."""
        base = os.environ.get(
            "NTHLAYER_WEBHOOK_URL", "http://localhost:8090"
        )
        return f"{base}/api/v1/incidents/{incident_id}/ack"
    
    async def health_check(self) -> bool:
        try:
            response = await self._client.get(
                f"{self.server_url}/v1/health"
            )
            return response.status_code == 200
        except Exception:
            return False
```

### 3.4 Twilio Voice Backend (Optional)

Last-resort phone call escalation. Single API call. Not required for basic operation.

```python
# nthlayer-respond/src/nthlayer_respond/notifications/twilio_voice.py

import os
import httpx
from base64 import b64encode

from .protocol import NotificationBackend, NotificationPayload, NotificationResult
from ..oncall.schedule import RosterMember


class TwilioVoiceBackend:
    """
    Twilio voice call for last-resort escalation.
    
    Makes a phone call using Twilio's REST API with a TwiML
    text-to-speech message. This is intentionally minimal —
    one API call, one dependency (httpx), no Twilio SDK.
    """
    
    def __init__(
        self,
        account_sid: str | None = None,
        auth_token: str | None = None,
        from_number: str | None = None,
    ):
        self.account_sid = account_sid or os.environ.get("TWILIO_ACCOUNT_SID")
        self.auth_token = auth_token or os.environ.get("TWILIO_AUTH_TOKEN")
        self.from_number = from_number or os.environ.get("TWILIO_FROM_NUMBER")
        
        if not all([self.account_sid, self.auth_token, self.from_number]):
            self._available = False
        else:
            self._available = True
            credentials = b64encode(
                f"{self.account_sid}:{self.auth_token}".encode()
            ).decode()
            self._client = httpx.AsyncClient(
                headers={"Authorization": f"Basic {credentials}"},
                timeout=15,
            )
    
    async def send(
        self, recipient: RosterMember, payload: NotificationPayload
    ) -> NotificationResult:
        phone = recipient.phone
        if not phone:
            # Check if the escalation step has a direct phone override
            return NotificationResult(
                delivered=False,
                channel="phone",
                recipient=recipient.name,
                timestamp=datetime.utcnow(),
                message_id=None,
                error="No phone number configured",
            )
        
        if not self._available:
            return NotificationResult(
                delivered=False,
                channel="phone",
                recipient=recipient.name,
                timestamp=datetime.utcnow(),
                message_id=None,
                error="Twilio not configured (missing credentials)",
            )
        
        # TwiML message — Twilio reads this to the caller
        twiml = (
            f'<Response><Say voice="alice">'
            f'NthLayer incident alert. {payload.title}. '
            f'{payload.summary}. '
            f'Press 1 to acknowledge.'
            f'</Say>'
            f'<Gather numDigits="1" action="{self._ack_webhook_url(payload.incident_id)}">'
            f'<Say>Press 1 to acknowledge this incident.</Say>'
            f'</Gather>'
            f'</Response>'
        )
        
        try:
            response = await self._client.post(
                f"https://api.twilio.com/2010-04-01/Accounts/{self.account_sid}/Calls.json",
                data={
                    "To": phone,
                    "From": self.from_number,
                    "Twiml": twiml,
                },
            )
            response.raise_for_status()
            data = response.json()
            
            return NotificationResult(
                delivered=True,
                channel="phone",
                recipient=recipient.name,
                timestamp=datetime.utcnow(),
                message_id=data.get("sid"),
                error=None,
            )
        except Exception as e:
            return NotificationResult(
                delivered=False,
                channel="phone",
                recipient=recipient.name,
                timestamp=datetime.utcnow(),
                message_id=None,
                error=str(e),
            )
    
    def _ack_webhook_url(self, incident_id: str) -> str:
        base = os.environ.get(
            "NTHLAYER_WEBHOOK_URL", "http://localhost:8090"
        )
        return f"{base}/api/v1/incidents/{incident_id}/ack"
    
    async def health_check(self) -> bool:
        if not self._available:
            return False
        try:
            response = await self._client.get(
                f"https://api.twilio.com/2010-04-01/Accounts/{self.account_sid}.json"
            )
            return response.status_code == 200
        except Exception:
            return False
```

### 3.5 PagerDuty Webhook-Out (Optional)

Thin, one-way event delivery for teams with PagerDuty entrenched. Sends an event via Events API v2. No bidirectional sync.

```python
# nthlayer-respond/src/nthlayer_respond/notifications/pagerduty.py

import os
import httpx

from .protocol import NotificationPayload, NotificationResult
from ..oncall.schedule import RosterMember


class PagerDutyWebhookBackend:
    """
    PagerDuty Events API v2 — one-way event delivery.
    
    Sends a trigger event to PagerDuty. PagerDuty handles
    its own routing and escalation from there. NthLayer does
    not read PagerDuty state or compete with Event Intelligence.
    """
    
    def __init__(self, routing_key: str | None = None):
        self.routing_key = routing_key or os.environ.get("PAGERDUTY_ROUTING_KEY")
        self._client = httpx.AsyncClient(timeout=10)
    
    async def send(
        self, recipient: RosterMember, payload: NotificationPayload
    ) -> NotificationResult:
        if not self.routing_key:
            return NotificationResult(
                delivered=False,
                channel="pagerduty",
                recipient="pagerduty",
                timestamp=datetime.utcnow(),
                message_id=None,
                error="No PagerDuty routing key configured",
            )
        
        severity_map = {1: "critical", 2: "error", 3: "warning", 4: "info"}
        
        event = {
            "routing_key": self.routing_key,
            "event_action": "trigger",
            "dedup_key": payload.incident_id,
            "payload": {
                "summary": f"{payload.incident_id}: {payload.title}",
                "source": "nthlayer-respond",
                "severity": severity_map.get(payload.severity, "warning"),
                "custom_details": {
                    "root_cause": payload.root_cause,
                    "blast_radius": payload.blast_radius,
                    "summary": payload.summary,
                },
            },
        }
        
        if payload.actions_url:
            event["links"] = [{"href": payload.actions_url, "text": "View in NthLayer"}]
        
        try:
            response = await self._client.post(
                "https://events.pagerduty.com/v2/enqueue",
                json=event,
            )
            response.raise_for_status()
            data = response.json()
            
            return NotificationResult(
                delivered=True,
                channel="pagerduty",
                recipient="pagerduty",
                timestamp=datetime.utcnow(),
                message_id=data.get("dedup_key"),
                error=None,
            )
        except Exception as e:
            return NotificationResult(
                delivered=False,
                channel="pagerduty",
                recipient="pagerduty",
                timestamp=datetime.utcnow(),
                message_id=None,
                error=str(e),
            )
    
    async def health_check(self) -> bool:
        return self.routing_key is not None
```

### 3.6 Stdout Backend (Testing)

For local development and CI.

```python
# nthlayer-respond/src/nthlayer_respond/notifications/stdout.py

class StdoutNotificationBackend:
    """Print notifications to stdout. For testing and local development."""
    
    async def send(self, recipient, payload) -> NotificationResult:
        print(f"\n{'='*60}")
        print(f"NOTIFICATION → {recipient.name}")
        print(f"  Incident: {payload.incident_id}")
        print(f"  Severity: P{payload.severity}")
        print(f"  Title: {payload.title}")
        print(f"  Summary: {payload.summary}")
        if payload.root_cause:
            print(f"  Root cause: {payload.root_cause}")
        print(f"  Blast radius: {', '.join(payload.blast_radius)}")
        print(f"{'='*60}\n")
        
        return NotificationResult(
            delivered=True,
            channel="stdout",
            recipient=recipient.name,
            timestamp=datetime.utcnow(),
            message_id=None,
            error=None,
        )
    
    async def health_check(self) -> bool:
        return True
```

---

## Part 4: Escalation Engine

### 4.1 State Machine

The escalation engine is a lightweight state machine driven by the respond coordinator. It walks the escalation policy, waits for acknowledgment, and advances to the next step if none arrives.

```python
# nthlayer-respond/src/nthlayer_respond/oncall/escalation.py

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum


class EscalationStatus(Enum):
    ACTIVE = "active"           # escalation in progress
    ACKNOWLEDGED = "acknowledged"  # someone acked
    EXHAUSTED = "exhausted"     # all steps executed, no ack
    RESOLVED = "resolved"       # incident resolved


@dataclass
class EscalationStep:
    """A single step in the escalation policy."""
    after: timedelta            # delay from escalation start
    notify: str                 # "slack_dm" | "ntfy" | "slack_channel" | "phone" | "pagerduty"
    target: str | None          # "next_oncall" | "engineering_manager" | None (= current oncall)
    phone: str | None           # direct phone override for this step


@dataclass
class EscalationState:
    """
    Tracks the state of an active escalation for one incident.
    """
    incident_id: str
    started_at: datetime
    steps: list[EscalationStep]
    
    # Mutable state
    current_step_index: int = 0
    acknowledged_by: str | None = None
    acknowledged_at: datetime | None = None
    status: EscalationStatus = EscalationStatus.ACTIVE
    notifications_sent: list["NotificationResult"] = field(default_factory=list)
    
    def acknowledge(self, user: str, at: datetime):
        """Mark escalation as acknowledged. Stops all further steps."""
        self.acknowledged_by = user
        self.acknowledged_at = at
        self.status = EscalationStatus.ACKNOWLEDGED
    
    def resolve(self):
        """Mark escalation as resolved."""
        self.status = EscalationStatus.RESOLVED
    
    def next_due_step(self, now: datetime) -> EscalationStep | None:
        """
        Return the next escalation step that should fire, or None.
        
        Steps fire when:
        - Status is ACTIVE (not acked/resolved/exhausted)
        - Current time >= started_at + step.after
        - The step hasn't been executed yet
        """
        if self.status != EscalationStatus.ACTIVE:
            return None
        
        if self.current_step_index >= len(self.steps):
            self.status = EscalationStatus.EXHAUSTED
            return None
        
        step = self.steps[self.current_step_index]
        due_at = self.started_at + step.after
        
        if now >= due_at:
            self.current_step_index += 1
            return step
        
        return None
    
    def time_until_next_step(self, now: datetime) -> timedelta | None:
        """How long until the next step fires. For the polling loop."""
        if self.status != EscalationStatus.ACTIVE:
            return None
        if self.current_step_index >= len(self.steps):
            return None
        
        step = self.steps[self.current_step_index]
        due_at = self.started_at + step.after
        remaining = due_at - now
        return max(remaining, timedelta(0))
```

### 4.2 Escalation Runner

The runner is the loop that drives the state machine and dispatches to notification backends.

```python
# nthlayer-respond/src/nthlayer_respond/oncall/runner.py

import asyncio
import structlog

from .schedule import resolve_oncall, OnCallResult, RosterMember
from .escalation import EscalationState, EscalationStep, EscalationStatus
from ..notifications.protocol import NotificationBackend, NotificationPayload

logger = structlog.get_logger()


class EscalationRunner:
    """
    Drives the escalation state machine.
    
    Called by the respond coordinator when an incident is created.
    Runs in the background, checking for due steps and dispatching
    notifications until acknowledged, resolved, or exhausted.
    """
    
    def __init__(
        self,
        backends: dict[str, NotificationBackend],
        oncall_config: dict,
        slack_channel: str | None = None,
    ):
        self.backends = backends      # {"slack_dm": SlackBackend, "ntfy": NtfyBackend, ...}
        self.oncall_config = oncall_config
        self.slack_channel = slack_channel
        self._active_escalations: dict[str, EscalationState] = {}
    
    async def start_escalation(
        self,
        incident_id: str,
        payload: NotificationPayload,
        steps: list[EscalationStep],
    ) -> EscalationState:
        """Start a new escalation for an incident."""
        from datetime import datetime, timezone
        
        state = EscalationState(
            incident_id=incident_id,
            started_at=datetime.now(timezone.utc),
            steps=steps,
        )
        self._active_escalations[incident_id] = state
        
        # Run the escalation loop as a background task
        asyncio.create_task(self._run_loop(state, payload))
        
        return state
    
    async def acknowledge(self, incident_id: str, user: str):
        """Acknowledge an escalation. Called from webhook handler."""
        from datetime import datetime, timezone
        
        state = self._active_escalations.get(incident_id)
        if state and state.status == EscalationStatus.ACTIVE:
            state.acknowledge(user, datetime.now(timezone.utc))
            logger.info(
                "escalation_acknowledged",
                incident_id=incident_id,
                user=user,
            )
            
            # Update Slack messages to show ack
            if "slack_dm" in self.backends:
                slack = self.backends["slack_dm"]
                for notif in state.notifications_sent:
                    if notif.channel == "slack_dm" and notif.message_id:
                        await slack.update_message(
                            notif.recipient,
                            notif.message_id,
                            f"✅ Acknowledged by {user}",
                        )
    
    async def _run_loop(
        self, state: EscalationState, payload: NotificationPayload
    ):
        """
        Main escalation loop. Checks for due steps, dispatches
        notifications, sleeps until the next step is due.
        """
        from datetime import datetime, timezone
        
        while state.status == EscalationStatus.ACTIVE:
            now = datetime.now(timezone.utc)
            step = state.next_due_step(now)
            
            if step:
                await self._execute_step(state, step, payload)
            
            # Sleep until next step or check every 5s for ack
            wait = state.time_until_next_step(now)
            if wait is None:
                break  # exhausted or no more steps
            
            sleep_secs = min(wait.total_seconds(), 5.0)
            await asyncio.sleep(max(sleep_secs, 1.0))
        
        if state.status == EscalationStatus.EXHAUSTED:
            logger.warning(
                "escalation_exhausted",
                incident_id=state.incident_id,
                steps_executed=state.current_step_index,
            )
    
    async def _execute_step(
        self,
        state: EscalationState,
        step: EscalationStep,
        payload: NotificationPayload,
    ):
        """Execute a single escalation step."""
        from datetime import datetime, timezone
        
        oncall = resolve_oncall(self.oncall_config, datetime.now(timezone.utc))
        
        # Determine recipient
        if step.notify == "slack_channel":
            # Post to team channel
            if self.slack_channel and "slack_dm" in self.backends:
                result = await self.backends["slack_dm"].send_to_channel(
                    self.slack_channel, payload
                )
                state.notifications_sent.append(result)
                logger.info("escalation_step_sent", step=step.notify, channel=self.slack_channel)
            return
        
        if step.notify == "pagerduty":
            if "pagerduty" in self.backends:
                result = await self.backends["pagerduty"].send(oncall.primary, payload)
                state.notifications_sent.append(result)
                logger.info("escalation_step_sent", step="pagerduty")
            return
        
        # Determine target person
        if step.target == "next_oncall":
            recipient = oncall.secondary
        elif step.target == "engineering_manager":
            # Use phone from step config directly
            recipient = RosterMember(
                name="Engineering Manager",
                slack_id="",
                ntfy_topic=None,
                phone=step.phone,
            )
        else:
            recipient = oncall.primary
        
        # Dispatch to backend
        backend = self.backends.get(step.notify)
        if not backend:
            logger.warning(
                "escalation_backend_missing",
                step=step.notify,
                incident_id=state.incident_id,
            )
            return
        
        result = await backend.send(recipient, payload)
        state.notifications_sent.append(result)
        
        logger.info(
            "escalation_step_sent",
            step=step.notify,
            recipient=recipient.name,
            delivered=result.delivered,
            error=result.error,
        )
```

---

## Part 5: Webhook Handler

A small HTTP server that receives acknowledgment callbacks from Slack interactive buttons, ntfy action buttons, and Twilio digit presses.

```python
# nthlayer-respond/src/nthlayer_respond/webhooks/server.py

"""
Lightweight webhook receiver for escalation interactions.

Endpoints:
  POST /api/v1/incidents/<id>/ack     — acknowledge from any source
  POST /slack/interactions             — Slack interactive message callback
  POST /twilio/voice-ack              — Twilio gather callback

Runs alongside the respond coordinator. Single async HTTP server
using a lightweight framework (aiohttp or starlette).
"""

# Slack interaction payload handling
async def handle_slack_interaction(request):
    """
    Slack sends a JSON payload when a user clicks a button.
    Extract action_id and value (incident_id), route to escalation runner.
    """
    payload = json.loads(request.form["payload"])
    
    for action in payload.get("actions", []):
        if action["action_id"] == "incident_ack":
            incident_id = action["value"]
            user = payload["user"]["username"]
            await escalation_runner.acknowledge(incident_id, user)
            
            return json_response({
                "response_type": "in_channel",
                "replace_original": True,
                "text": f"✅ Acknowledged by @{user}",
            })
        
        elif action["action_id"] == "incident_escalate":
            incident_id = action["value"]
            # Force advance to next escalation step
            # ... implementation
    
    return json_response({"ok": True})


# Generic ack endpoint (called from ntfy action buttons)
async def handle_ack(request, incident_id: str):
    """
    Generic acknowledge endpoint. Called from ntfy action buttons
    and any other source that can make an HTTP POST.
    """
    await escalation_runner.acknowledge(incident_id, "ntfy_user")
    return json_response({"acknowledged": True, "incident_id": incident_id})
```

---

## Part 6: Configuration

### 6.1 Global Config

```yaml
# ~/.nthlayer/config.yaml

notifications:
  # Slack (required for basic operation)
  slack:
    bot_token: "${SLACK_BOT_TOKEN}"
  
  # ntfy (recommended for DND-override paging)
  ntfy:
    server_url: "https://ntfy.example.com"    # self-hosted
    # server_url: "https://ntfy.sh"           # or public server
    auth_token: "${NTFY_AUTH_TOKEN}"           # optional, for self-hosted auth
  
  # Twilio (optional, for voice call escalation)
  twilio:
    account_sid: "${TWILIO_ACCOUNT_SID}"
    auth_token: "${TWILIO_AUTH_TOKEN}"
    from_number: "+15551234567"
  
  # PagerDuty (optional, thin webhook-out)
  pagerduty:
    routing_key: "${PAGERDUTY_ROUTING_KEY}"
  
  # Webhook receiver for ack callbacks
  webhook:
    listen: "0.0.0.0:8090"
    public_url: "https://nthlayer.example.com"  # for Slack/ntfy callbacks
```

### 6.2 CLI Flags

```bash
# Use stdout for testing (no Slack/ntfy required)
nthlayer respond \
  --correlation ./correlations/corr_d4e5f6.json \
  --specs-dir ./specs/ \
  --notify stdout

# Use configured backends
nthlayer respond \
  --correlation ./correlations/corr_d4e5f6.json \
  --specs-dir ./specs/ \
  --notify slack,ntfy
```

---

## Part 7: Integration with Respond Coordinator

The respond coordinator already runs a pipeline: Triage → Investigation + Communication → Remediation. The communication agent's output now feeds into the escalation runner.

```python
# In coordinator.py, after triage determines severity and blast radius:

if incident.severity <= 2:  # P1 or P2
    # Load on-call config from the affected service's manifest
    oncall_config = load_oncall_config(specs_dir, incident.primary_service)
    
    if oncall_config:
        escalation_steps = parse_escalation_policy(oncall_config["escalation"])
        
        payload = NotificationPayload(
            incident_id=incident.id,
            severity=incident.severity,
            title=incident.title,
            summary=communication_agent.initial_summary,
            root_cause=investigation_agent.root_cause,
            blast_radius=incident.blast_radius,
            actions_url=f"{dashboard_url}/incidents/{incident.id}",
            escalation_step=0,
            requires_ack=True,
        )
        
        await escalation_runner.start_escalation(
            incident.id, payload, escalation_steps
        )
    else:
        # No on-call config — fall back to Slack channel notification
        await slack_backend.send_to_channel(
            incident.slack_channel, payload
        )
```

---

## Part 8: Incident Verdict Extension

Escalation actions are recorded in the incident verdict for the audit trail:

```yaml
incident_verdict:
  id: "v-inc-INC-4821"
  verdict_type: incident
  
  escalation:
    started_at: "2026-04-02T14:32:00Z"
    acknowledged_by: "Alice"
    acknowledged_at: "2026-04-02T14:34:22Z"
    acknowledged_via: "slack_dm"        # which channel they acked from
    steps_executed: 2                   # slack_dm at 0m, ntfy at 5m
    steps_total: 6
    notifications:
      - channel: slack_dm
        recipient: Alice
        delivered: true
        at: "2026-04-02T14:32:00Z"
      - channel: ntfy
        recipient: Alice
        delivered: true
        at: "2026-04-02T14:37:00Z"
```

This feeds into nthlayer-learn's retrospective: "Time to acknowledge: 2m22s. Acknowledged via Slack DM on first escalation step."

---

## Implementation Priority

| Phase | Work | Effort | Outcome |
|---|---|---|---|
| **1** | Manifest schema + schedule resolver | 2 days | `nthlayer oncall` command works |
| **2** | Notification protocol + stdout + Slack backends | 3 days | Slack DMs with buttons |
| **3** | Escalation state machine + runner | 2-3 days | Timed escalation works |
| **4** | Webhook handler for ack callbacks | 2 days | Slack button acks stop escalation |
| **5** | ntfy backend | 1 day | DND-override push notifications |
| **6** | Twilio voice backend | 1 day | Phone call escalation |
| **7** | PagerDuty webhook-out | 0.5 days | One-way event delivery |
| **8** | Coordinator integration + verdict extension | 2 days | Full pipeline wired |

**Phases 1-4:** ~9-10 days for a working on-call + Slack paging system.
**Phase 5:** adds DND-override for +1 day.
**Phases 6-7:** optional adapters, +1.5 days.

---

## Audit First

Before implementing, Claude Code must:

1. Read `nthlayer-respond/src/nthlayer_respond/coordinator.py` — understand the existing incident lifecycle, where communication happens, and where escalation should hook in.
2. Read the existing notification code — is there already a webhook/stdout notification channel? What interface does it use?
3. Read `nthlayer-respond/src/nthlayer_respond/agents/` — specifically the communication agent, to understand what output it produces that should feed into notification payloads.
4. Check if any Slack integration code already exists anywhere in the NthLayer codebase.
5. Read the manifest schema — understand the current `spec.ownership` structure and how to extend it with `oncall`.
6. Check the existing CLI argument parsing to understand how `--notify` flags should be added consistently.
7. Document findings before implementing.
