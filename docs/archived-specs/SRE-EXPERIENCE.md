# SRE-EXPERIENCE.md — Human-in-the-Loop Experience Specification

This document specifies the features that make the OpenSRM ecosystem a joy to be on-call with. Every feature is built from verdict queries and templates. No new components. No new infrastructure. One optional model call (post-incident action item suggestions), clearly bounded and marked.

Read VERDICT.md first. Every feature here is a view over verdicts.


## Design Principle

**The SRE sees intelligence. The implementation is templates over queries.**

The gap between perceived intelligence and actual implementation is the ZFC principle at work. The transport layer creates the experience. The model (where it exists) provides judgment. The SRE can't tell which is which because the interface is the same.

Every feature in this document is explicitly specified as:
1. A verdict query (what data to retrieve)
2. A template (how to render it)
3. A delivery mechanism (where it goes)

This prevents Claude Code from reaching for a model call when a `format_string.format(**verdict_fields)` will do.


## 1. The Paging Brief

### What the SRE Sees

When paged, a single concise message arrives alongside (or instead of) the raw PagerDuty alert. The brief answers three questions in one glance: what's broken, why, and what can I do about it.

```
🔴 P2: payment-api latency spike

What's happening: p99 latency at 520ms (SLO target: 200ms) for 8 minutes.
Checkout-service error rate rising (dependency).

Likely cause: deploy v2.3.1 to payment-api 14 minutes ago
(SitRep confidence: 0.74). Deploy modified connection pooling config.

Blast radius: payment-api, checkout-service.
Unaffected: billing-service, inventory-service.

Rollback available: yes (v2.3.0 was healthy).

Mayday recommends: rollback payment-api to v2.3.0 (pre-approved safe action).

→ Reply APPROVE to execute rollback
→ Reply INVESTIGATE for detailed context
→ Reply ACK to acknowledge without action
```

### Implementation (Transport)

**Query:**

```python
def build_paging_brief(incident_id: str, verdict_store: VerdictStore) -> PagingBrief:
    # Get the triage verdict (first Mayday verdict for this incident)
    triage = verdict_store.query(
        producer_system="mayday",
        producer_instance="triage-agent",
        subject_ref=incident_id,
        limit=1
    )[0]

    # Get the SitRep correlation verdicts linked to this incident
    correlations = verdict_store.query(
        producer_system="sitrep",
        subject_type="correlation",
        verdict_ids=triage.lineage.context  # SitRep verdicts that informed triage
    )

    # Get the remediation verdict if available
    remediation = verdict_store.query(
        producer_system="mayday",
        producer_instance="remediation-agent",
        subject_ref=incident_id,
        limit=1
    )

    # Get the candidate change from the highest-confidence correlation
    top_correlation = max(correlations, key=lambda v: v.judgment.confidence)

    return PagingBrief(
        severity=triage.judgment.tags,  # ["P2"]
        service=triage.subject.service,
        summary=triage.judgment.reasoning,
        likely_cause=top_correlation.judgment.reasoning,
        cause_confidence=top_correlation.judgment.confidence,
        blast_radius=triage.judgment.dimensions.get("blast_radius", []),
        unaffected=triage.judgment.dimensions.get("unaffected", []),
        remediation=remediation[0] if remediation else None,
        rollback_available=_check_rollback(top_correlation)
    )
```

**Template:**

```python
PAGING_BRIEF_TEMPLATE = """
{severity_emoji} {severity}: {service} {summary_short}

What's happening: {metric_summary}

Likely cause: {likely_cause}
(SitRep confidence: {cause_confidence})

Blast radius: {blast_radius_list}.
{unaffected_line}

{rollback_line}

{remediation_line}

→ Reply APPROVE to execute {recommended_action}
→ Reply INVESTIGATE for detailed context
→ Reply ACK to acknowledge without action
"""
```

Every field in the template comes from a verdict field. No model call. The "intelligence" is in the SitRep and Mayday verdicts that were produced earlier by agents. The brief is just rendering those verdicts for a human.

**Severity emoji mapping (deterministic):**

```python
SEVERITY_EMOJI = {"P1": "🔴", "P2": "🟠", "P3": "🟡", "P4": "🔵"}
```

**Delivery:**

The brief is sent via the notification channels configured in the OpenSRM manifest (`spec.notifications.channels`). For Slack, it's a structured message. For SMS/PagerDuty, it's a condensed version (first 3 lines only with a link to the full brief). For email, it's the full template.

**Reply handling:**

Replies (APPROVE, INVESTIGATE, ACK) are received via the notification channel's interaction mechanism (Slack interactive message, PagerDuty custom action, email reply parsing). Each reply maps to a `HumanInput` object that the Mayday coordinator processes (see MAYDAY.md):

```python
REPLY_MAPPING = {
    "APPROVE": HumanInput(input_type="remediation_approval", payload={"approved_action": "rollback"}),
    "INVESTIGATE": HumanInput(input_type="additional_context", payload={"request": "detailed_investigation"}),
    "ACK": HumanInput(input_type="additional_context", payload={"request": "acknowledge_only"})
}
```

### When It's Generated

The coordinator in Mayday calls `build_paging_brief()` immediately after the triage agent completes and the remediation agent has produced a recommendation (or after a configurable timeout if remediation is slow). If the remediation agent hasn't responded within 30 seconds of triage completing, the brief is sent without a remediation recommendation (the "Mayday recommends" line is replaced with "Investigation in progress").


## 2. The Shift Report

### What the SRE Sees

At the start of every on-call shift (configurable time, default 09:00 local), the SRE receives a summary of what happened since the last shift report.

**Quiet shift example:**

```
Shift Report: March 7, 08:00 → March 8, 08:00

Nothing required your attention overnight. ✓

Background:
• Arbiter reduced code-reviewer autonomy (reversal rate 0.08,
  target 0.05). 3 overrides this week, all missing input validation.
  Review verdicts: [link]

• SitRep flagged slow memory growth on cache-service correlated
  with yesterday's config change. Not breaching SLOs yet.
  Confidence: 0.45. Worth watching today.

• 2 deploys overnight, both passed check-deploy. No quality signals.

Pending verdicts needing your review: 3 (none overdue)
Confidence dashboard: [link]
```

**Busy shift example:**

```
Shift Report: March 7, 08:00 → March 8, 08:00

1 incident resolved overnight.

INC-2026-0142 (P2, 16 minutes)
  payment-api latency spike caused by deploy v2.3.1.
  Rollback approved by @rob at 14:26. Resolved at 14:35.
  Post-incident review: [link]

Governance changes:
• Arbiter reduced code-reviewer autonomy (reversal rate 0.08).
  Triggered by 3 overrides related to input validation.
  Review verdicts: [link]

Ecosystem health:
• SitRep correlation accuracy (30d): 0.87 ✓
• Arbiter evaluation accuracy (30d): 0.94 ✓
• Mayday triage accuracy: insufficient data (< 10 incidents)

Pending: 5 verdicts needing review (1 overdue by 6 hours)
Action items from INC-2026-0142: 3 open [link]
```

### Implementation (Transport)

**Query:**

```python
def build_shift_report(shift_start: str, shift_end: str, verdict_store: VerdictStore) -> ShiftReport:
    window = TimeRange(shift_start, shift_end)

    # Incidents (Mayday incident summary verdicts)
    incidents = verdict_store.query(
        subject_type="incident_summary",
        time_range=window
    )

    # Governance actions (Arbiter governance verdicts)
    governance = verdict_store.query(
        producer_system="arbiter",
        tags=["governance"],
        time_range=window
    )

    # State transitions (SitRep state change verdicts)
    state_transitions = verdict_store.query(
        producer_system="sitrep",
        tags=["state_transition"],
        time_range=window
    )

    # Deploys (change events that passed through the ecosystem)
    deploys = verdict_store.query(
        subject_type="change",
        time_range=window
    )

    # SitRep correlations worth watching (confidence between 0.3 and 0.6, not yet escalated)
    watching = verdict_store.query(
        producer_system="sitrep",
        subject_type="correlation",
        time_range=window,
        min_confidence=0.3,
        max_confidence=0.6
    )

    # Pending reviews
    pending = verdict_store.query(status="pending")
    overdue = [v for v in pending if age(v) > review_threshold(v)]

    # Accuracy (rolling 30 day)
    arbiter_accuracy = verdict_store.accuracy(producer_system="arbiter", time_range=last_30d)
    sitrep_accuracy = verdict_store.accuracy(producer_system="sitrep", time_range=last_30d)
    mayday_accuracy = verdict_store.accuracy(producer_system="mayday", time_range=last_30d)

    # Action items still open
    open_actions = verdict_store.query(
        subject_type="action_item",
        status="pending"
    )

    return ShiftReport(
        window=window,
        incidents=incidents,
        governance=governance,
        state_transitions=state_transitions,
        deploys=deploys,
        watching=watching,
        pending_reviews=pending,
        overdue_reviews=overdue,
        accuracy={
            "arbiter": arbiter_accuracy,
            "sitrep": sitrep_accuracy,
            "mayday": mayday_accuracy
        },
        open_actions=open_actions
    )
```

**Template:**

```python
SHIFT_REPORT_TEMPLATE = """
Shift Report: {window_start} → {window_end}

{headline}

{incidents_section}
{governance_section}
{watching_section}
{deploys_section}
{ecosystem_health_section}
{pending_section}
{action_items_section}
"""

def render_headline(report: ShiftReport) -> str:
    if not report.incidents and not report.governance and not report.state_transitions:
        return "Nothing required your attention. ✓"
    parts = []
    if report.incidents:
        parts.append(f"{len(report.incidents)} incident(s) resolved.")
    if report.governance:
        parts.append(f"{len(report.governance)} governance change(s).")
    return " ".join(parts)

def render_incidents_section(incidents: list) -> str:
    if not incidents:
        return ""
    lines = []
    for inc in incidents:
        lines.append(f"""
{inc.subject.ref} ({inc.judgment.tags[0]}, {inc.metadata.get('duration', 'unknown')})
  {inc.subject.summary}
  Post-incident review: [{link(inc)}]
""")
    return "\n".join(lines)

# Similar render functions for each section...
# Each function reads verdict fields and formats them. No model calls.
```

**Delivery:**

Sent via the configured notification channel at shift start time. Shift times are configured in the OpenSRM manifest:

```yaml
spec:
  oncall:
    shift_report:
      enabled: true
      times: ["09:00", "21:00"]      # start of each shift in local time
      timezone: "Europe/Dublin"
      channel: slack                   # or email
      include_accuracy: true           # include 30-day accuracy metrics
      include_action_items: true       # include open post-incident action items
```

**Quiet detection (deterministic):**

```python
def is_quiet(report: ShiftReport) -> bool:
    return (
        len(report.incidents) == 0
        and len(report.governance) == 0
        and len(report.state_transitions) == 0
        and len(report.overdue_reviews) == 0
    )
```


## 3. Alert Suppression ("Don't Page Me For This")

### What the SRE Sees

After being paged for a known non-issue, the SRE sends a suppression command:

```
SRE: /suppress payment-api latency_p99 --window 02:00-04:00 --reason "nightly backup"

Ecosystem response:
✓ Suppression rule added for payment-api latency_p99 during 02:00-04:00 daily.
  Baseline captured: p99 = 350ms during backup window (30-day average).
  Override threshold: 1050ms (3x baseline).
  If latency exceeds 1050ms during the backup window, you'll still be paged.
  Suppression verdict: vrd-2026-03-08-00891
  Review in 30 days: [link]
```

### Implementation (Transport)

**Suppression rule schema (added to OpenSRM manifest):**

```yaml
spec:
  suppressions:
    - id: "sup-payment-api-backup"
      service: payment-api
      metric: latency_p99
      window:
        type: daily                    # daily | weekly | cron
        start: "02:00"
        end: "04:00"
        timezone: "Europe/Dublin"
      reason: "nightly backup causes expected latency spike"
      baseline:
        value: 350                     # ms, computed from historical data
        window_days: 30                # how many days of history the baseline covers
      override_threshold_multiplier: 3  # page if value exceeds baseline * multiplier
      created_by: "human:rob"
      created_at: "2026-03-08T03:15:00Z"
      review_after: "2026-04-07"       # 30-day review reminder
      verdict_id: "vrd-2026-03-08-00891"
```

**Suppression creation (transport):**

```python
def create_suppression(command: SuppressionCommand, manifest: Manifest, metrics_client: PrometheusClient) -> Suppression:
    # 1. Compute baseline from historical data (arithmetic, not judgment)
    historical_values = metrics_client.query_range(
        metric=command.metric,
        service=command.service,
        start=now() - timedelta(days=30),
        end=now(),
        time_filter=command.window  # only values during the specified window
    )
    baseline = statistics.mean(historical_values)
    stddev = statistics.stdev(historical_values)

    # 2. Set override threshold (deterministic: baseline * multiplier)
    override_threshold = baseline * command.override_multiplier  # default 3x

    # 3. Create suppression verdict
    v = verdict.create(
        subject=Subject(
            type="suppression",
            service=command.service,
            ref=f"sup-{command.service}-{command.metric}",
            summary=f"Suppress {command.metric} alerts on {command.service} during {command.window}"
        ),
        judgment=Judgment(
            action="suppress",
            confidence=1.0,  # human decision, not model judgment
            reasoning=command.reason
        ),
        producer=Producer(system="human", instance=command.actor)
    )
    verdict_store.put(v)

    # 4. Update manifest with suppression rule
    suppression = Suppression(
        service=command.service,
        metric=command.metric,
        window=command.window,
        baseline=baseline,
        override_threshold=override_threshold,
        reason=command.reason,
        verdict_id=v.id,
        review_after=now() + timedelta(days=30)
    )
    manifest.add_suppression(suppression)

    # 5. Regenerate alerting rules via NthLayer
    nthlayer.generate(manifest)  # deterministic: new rules include suppression window

    return suppression
```

**Override detection during suppressed window (transport, arithmetic):**

```python
def check_suppression_override(suppression: Suppression, current_value: float) -> bool:
    """Returns True if the current value exceeds the override threshold."""
    return current_value > suppression.override_threshold
```

When an alert fires during a suppressed window:
- If `current_value <= override_threshold`: alert is suppressed, SitRep deprioritises the signal
- If `current_value > override_threshold`: suppression is overridden, SRE is paged with context:

```
⚠️ Override: payment-api latency during backup window

This alert is normally suppressed (nightly backup), but current value
is 1,840ms — significantly above the 1,050ms override threshold
(3x your 350ms baseline).

This is NOT the usual backup spike. Investigate.
```

**Suppression review (transport):**

When `review_after` is reached, the suppression verdict surfaces in the shift report and verdict feed as overdue for review. The SRE confirms (suppression still valid), modifies (adjust threshold or window), or removes (the pattern has changed).

If SitRep detects that the suppressed metric's baseline has drifted significantly (the backup now takes twice as long and the latency during backup has doubled), the suppression verdict is auto-flagged for review with the new baseline data.

**SitRep integration:**

SitRep reads suppression rules from the manifest and adjusts its correlation engine:
- Events matching a suppression window are pre-scored with reduced severity (unless they exceed the override threshold)
- Correlation verdicts that include suppressed signals note the suppression: "latency spike on payment-api during suppressed backup window (within expected range)"


## 4. Auto-Generated Post-Incident Review

### What the SRE Sees

After an incident resolves, a draft post-incident review appears in the configured channel (Slack, email, or a linked document). The SRE reviews, edits, and publishes.

```
Post-Incident Review: INC-2026-0142
Auto-generated from verdict chain. Review and edit before publishing.

Timeline:
14:10  Deploy v2.3.1 to payment-api
14:22  SitRep: latency spike correlated with deploy (confidence 0.74)
14:23  Mayday triage: P2, blast radius: payment-api + checkout-service
14:24  Investigation: connection pooling config removed (confidence 0.82)
14:25  SRE paged, received brief
14:26  SRE approved rollback
14:27  Rollback executed
14:35  SLOs recovered

Detection time: 12 minutes
Resolution time: 16 minutes (5 minutes human involvement)

What worked:
• SitRep correctly identified deploy as cause (confirmed ✓)
• Triage severity was accurate (confirmed ✓)
• Pre-approved rollback enabled phone-based resolution
• Total human involvement: 5 minutes

What to improve:
• Detection took 12 minutes. connection_pool_active metric hit 0 at T+10m
  but wasn't in the primary alert path.
• Arbiter auto-approved the deploy (risk tier: standard). The change
  modified connection pooling config, which should arguably be "deep" tier.

Action items:
• [ ] Add database_connection_pool_active to payment-api SLO targets
      (auto-detected: metric was at 0 during incident but not in manifest)
• [ ] Review Arbiter risk classification for connection pool config changes
      (auto-detected: Arbiter verdict overridden for this change category)
• [ ] Add this incident as a SitRep replay scenario
      (auto-generated: scenarios/real/inc-2026-0142.yaml)

Verdict accuracy:
  SitRep correlation:     confirmed ✓
  Mayday triage:          confirmed ✓
  Mayday investigation:   confirmed ✓
  Mayday remediation:     confirmed ✓
  Arbiter evaluation:     overridden ✗ (approved the deploy that caused incident)
```

### Implementation

**Timeline (transport):**

```python
def build_timeline(incident_id: str, verdict_store: VerdictStore) -> list[TimelineEntry]:
    """
    Reconstruct the incident timeline from verdict timestamps.
    Pure query + sort. No model call.
    """
    # Get all verdicts for this incident
    verdicts = verdict_store.query(subject_ref=incident_id)

    # Get the change events from the incident context
    incident_summary = verdict_store.query(
        subject_type="incident_summary",
        subject_ref=incident_id,
        limit=1
    )[0]

    # Get SitRep correlation verdicts linked via lineage
    sitrep_verdicts = verdict_store.by_lineage(
        verdicts[0].id, direction="up"
    )

    # Combine all events and sort by timestamp
    entries = []
    for v in verdicts + sitrep_verdicts:
        entries.append(TimelineEntry(
            timestamp=v.timestamp,
            source=v.producer.system,
            agent=v.producer.instance,
            summary=v.subject.summary,
            confidence=v.judgment.confidence
        ))

    entries.sort(key=lambda e: e.timestamp)
    return entries
```

**"What worked" / "What to improve" (transport):**

```python
def build_review_sections(verdicts: list[Verdict]) -> tuple[list[str], list[str]]:
    """
    What worked = confirmed verdicts.
    What to improve = overridden verdicts + timing gaps.
    Pure filtering over verdict outcomes. No model call.
    """
    worked = []
    improve = []

    for v in verdicts:
        if v.outcome.status == "confirmed":
            worked.append(f"{v.producer.instance}: {v.subject.summary} (confirmed ✓)")
        elif v.outcome.status == "overridden":
            improve.append(
                f"{v.producer.instance}: {v.outcome.override.reasoning} "
                f"(original: {v.judgment.reasoning})"
            )

    # Timing analysis (arithmetic)
    change_time = find_earliest(verdicts, subject_type="change")
    detection_time = find_earliest(verdicts, producer_system="sitrep")
    if change_time and detection_time:
        gap = detection_time.timestamp - change_time.timestamp
        if gap > timedelta(minutes=10):
            improve.append(
                f"Detection took {gap.total_seconds() / 60:.0f} minutes. "
                f"Review whether earlier signals were available."
            )

    return worked, improve
```

**Verdict accuracy section (transport):**

```python
def build_accuracy_section(verdicts: list[Verdict]) -> list[str]:
    """
    For each verdict in the incident chain, show confirmed/overridden status.
    Pure iteration over verdict outcomes.
    """
    lines = []
    for v in verdicts:
        if v.producer.system in ("sitrep", "mayday", "arbiter"):
            status = "confirmed ✓" if v.outcome.status == "confirmed" else "overridden ✗"
            detail = ""
            if v.outcome.status == "overridden" and v.outcome.override.reasoning:
                detail = f" ({v.outcome.override.reasoning})"
            lines.append(f"  {v.producer.instance}: {status}{detail}")
    return lines
```

**Action item suggestions (THIS IS THE ONE MODEL CALL):**

```python
def suggest_action_items(incident_context: IncidentContext, verdicts: list[Verdict]) -> list[ActionItem]:
    """
    THIS IS THE ONLY MODEL CALL IN THE POST-INCIDENT REVIEW.
    It is optional. The review is complete and useful without it.

    The model receives the structured incident data (not raw events)
    and suggests structural improvements.
    """
    # First, generate rule-based suggestions (transport, no model)
    rule_based = []

    # If a metric was at an extreme value during the incident but isn't in the manifest
    for metric_anomaly in find_unmonitored_anomalies(incident_context):
        rule_based.append(ActionItem(
            description=f"Add {metric_anomaly.metric} to {metric_anomaly.service} SLO targets",
            source="auto-detected",
            reasoning=f"Metric was at {metric_anomaly.value} during incident but not in manifest"
        ))

    # If the Arbiter was overridden, suggest reviewing classification
    overridden_arbiter = [v for v in verdicts if v.producer.system == "arbiter" and v.outcome.status == "overridden"]
    for v in overridden_arbiter:
        rule_based.append(ActionItem(
            description=f"Review Arbiter risk classification for {v.subject.summary}",
            source="auto-detected",
            reasoning=f"Arbiter verdict overridden: {v.outcome.override.reasoning}"
        ))

    # Always suggest adding to replay suite (transport)
    rule_based.append(ActionItem(
        description="Add this incident as a replay scenario",
        source="auto-generated",
        reasoning=f"Scenario exported: scenarios/real/{incident_context.id}.yaml"
    ))

    # OPTIONAL: model-based suggestions for structural improvements
    if config.post_incident_model_suggestions:
        model_suggestions = model.complete(
            POST_INCIDENT_SUGGESTION_PROMPT.format(
                timeline=format_timeline(verdicts),
                overridden_verdicts=format_overridden(verdicts),
                current_manifest=manifest_summary,
                current_arbiter_config=arbiter_config_summary
            )
        )
        # Parse model output into ActionItem objects
        # Model suggestions are tagged source="model-suggested" to distinguish
        # from rule-based suggestions
        rule_based.extend(parse_model_suggestions(model_suggestions))

    return rule_based
```

**The model prompt for action item suggestions (the bounded model call):**

```
You are reviewing a resolved incident to suggest structural improvements.
Do not summarise the incident. Do not write a narrative. Only suggest
specific, actionable changes to configuration, manifests, or monitoring.

TIMELINE:
{timeline}

OVERRIDDEN VERDICTS (where the ecosystem was wrong):
{overridden_verdicts}

CURRENT MANIFEST EXCERPT:
{current_manifest}

Suggest 1-3 specific improvements. For each:
- What to change (be specific: which file, which field, what value)
- Why (connect to the incident evidence)
- Priority (high: would have prevented this incident, medium: would have
  detected faster, low: general improvement)

Respond in this format:
SUGGESTIONS:
- CHANGE: [specific change]
  WHY: [reasoning connected to evidence]
  PRIORITY: high | medium | low
```

**Action item tracking (transport):**

Each action item becomes a verdict:

```python
def create_action_items(items: list[ActionItem], incident_id: str, verdict_store: VerdictStore):
    for item in items:
        v = verdict.create(
            subject=Subject(
                type="action_item",
                ref=incident_id,
                summary=item.description
            ),
            judgment=Judgment(
                action="recommend",
                confidence=1.0 if item.source != "model-suggested" else 0.7,
                reasoning=item.reasoning,
                tags=[item.priority, item.source]
            ),
            producer=Producer(
                system="mayday" if item.source != "model-suggested" else "mayday-model",
                instance="post-incident"
            )
        )
        verdict_store.put(v)
```

**Completion detection for action items (transport):**

```python
def check_action_item_completion(item_verdict: Verdict, manifest: Manifest, git_client: GitClient) -> bool:
    """
    Check if an action item has been completed.
    Deterministic: compare manifest state against the suggested change.
    """
    if "Add" in item_verdict.subject.summary and "SLO targets" in item_verdict.subject.summary:
        # Check if the metric was added to the manifest
        metric_name = extract_metric_name(item_verdict.subject.summary)
        service_name = extract_service_name(item_verdict.subject.summary)
        return manifest.has_slo_metric(service_name, metric_name)

    if "replay scenario" in item_verdict.subject.summary:
        # Check if the scenario file exists
        scenario_path = extract_scenario_path(item_verdict.judgment.reasoning)
        return git_client.file_exists(scenario_path)

    # For action items that can't be auto-detected, remain pending until human resolves
    return False
```

**Recurring incident detection (transport, uses existing SitRep):**

When an incident occurs and its root cause pattern matches an open action item, the post-incident review notes this:

```python
def check_recurring_pattern(incident: IncidentContext, verdict_store: VerdictStore) -> list[str]:
    """
    Check if any open action items would have prevented or mitigated this incident.
    Deterministic: compare incident root cause against action item descriptions.
    """
    open_actions = verdict_store.query(subject_type="action_item", status="pending")
    recurring = []
    for action in open_actions:
        # Simple keyword overlap between action item and incident root cause
        if keyword_overlap(action.subject.summary, incident.investigation.root_cause_explanation) > 0.5:
            recurring.append(
                f"Action item from {action.subject.ref} was not completed: "
                f"'{action.subject.summary}'. This incident may have been "
                f"prevented or detected faster if it had been."
            )
    return recurring
```

Note: `keyword_overlap` is a simple term intersection ratio (transport), not semantic similarity (which would require embeddings and would cross into ML territory).

**Delivery:**

The post-incident review is generated by the Mayday coordinator during `_finalise_incident()` (see MAYDAY.md). It's delivered via the configured notification channel with a link to the full review. The review is stored as a markdown file in the repo (alongside the scenario export) and as a set of linked verdicts in the verdict store.

```yaml
spec:
  oncall:
    post_incident:
      auto_generate: true
      delivery: slack                  # or email, or git_commit
      model_suggestions: true          # enable the optional model call for action items
      action_item_check_interval: 24h  # how often to check for completed action items
      recurring_pattern_check: true    # flag recurring patterns in new incidents
```


## 5. The Confidence Dashboard

### What the SRE Sees

A Grafana dashboard (generated by NthLayer) that shows the ecosystem's track record. The SRE uses this to calibrate their trust: where can they delegate, where should they double-check.

### Implementation (Transport)

**All panels are NthLayer-generated Grafana panels from verdict accuracy queries.**

Panel 1: Per-component accuracy over time (line chart)

```promql
# Arbiter confirmation rate (30-day rolling)
1 - (
  sum(rate(gen_ai_override_reversal_total{system="arbiter"}[30d]))
  /
  sum(rate(gen_ai_decision_total{system="arbiter"}[30d]))
)
```

Panel 2: Per-agent accuracy breakdown (table)

```promql
# Per-agent override rate
sum by (agent) (rate(gen_ai_override_reversal_total{system="arbiter"}[30d]))
/
sum by (agent) (rate(gen_ai_decision_total{system="arbiter"}[30d]))
```

Panel 3: Calibration gap (confidence vs actual accuracy)

```
Mean confidence on confirmed verdicts vs mean confidence on overridden verdicts.
A well-calibrated system has higher confidence on correct decisions than incorrect ones.
```

This is computed by the `verdict.accuracy()` query and emitted as a metric:

```promql
gen_ai_decision_calibration_gap{system="arbiter"}
```

Panel 4: Track record for specific action types

```
"Of the last N incidents where Mayday recommended rollback, X were correct."
```

```promql
sum(gen_ai_decision_total{system="mayday", agent="remediation-agent", action="rollback"})  # total
sum(gen_ai_override_reversal_total{system="mayday", agent="remediation-agent", action="rollback"})  # overridden
```

Panel 5: Areas of uncertainty (table, filtered to low-accuracy combinations)

```
SitRep correlation confidence on database-related incidents: 0.52
Arbiter evaluation accuracy on security-tagged reviews: 0.78
```

This surfaces the specific contexts where the ecosystem is weakest, so the SRE knows to pay extra attention.

Panel 6: Pending and overdue review counts (stat panel)

```promql
verdict_pending_total
verdict_overdue_total
```

**Dashboard generation:**

NthLayer generates this dashboard when the manifest declares `type: ai-gate` services. The dashboard template is part of NthLayer's existing template library, extended with verdict-specific panels. The command is the same as always:

```bash
nthlayer apply --manifest service.reliability.yaml
# Generates: confidence-dashboard.json (Grafana)
```

The SRE doesn't build this dashboard. It appears automatically when they adopt the ecosystem.


## 6. Delegation Mode ("I'm Busy, Handle It")

### What the SRE Sees

During a multi-incident situation, the SRE delegates a lower-priority incident:

```
SRE: /delegate INC-2026-0143 --safe-actions-only --summarise-when-done

Ecosystem response:
✓ Delegated INC-2026-0143 (P3: cache-service memory growth).
  Mayday will handle with pre-approved safe actions only.
  You won't receive updates until resolution or escalation.
  If safe actions are insufficient, you'll be interrupted with a brief.
```

Later:

```
Delegation summary: INC-2026-0143 (resolved autonomously)

Action taken: scale-up cache-service from 3 to 6 replicas (pre-approved safe action).
Memory growth stabilised after scale-up. SLOs recovered.
Duration: 23 minutes. No human involvement after delegation.

Verdict chain: [link]
Post-incident review: [link]
```

Or, if escalation is needed:

```
⚠️ Delegation escalation: INC-2026-0143

Safe actions exhausted. cache-service memory growth continues after scale-up.
Mayday investigation suggests a memory leak in cache-service v3.2.0
(confidence: 0.62). Recommended action: rollback to v3.1.0.

This is NOT a pre-approved safe action for cache-service.
Your approval is required.

→ Reply APPROVE to execute rollback
→ Reply MANUAL to take over investigation
```

### Implementation (Transport)

**Delegation is a governance configuration change on the incident:**

```python
def delegate_incident(incident_id: str, actor: str, config: DelegationConfig, verdict_store: VerdictStore):
    """
    Delegation modifies the incident's governance policy.
    Deterministic configuration change, not a model call.
    """
    # 1. Create delegation verdict
    v = verdict.create(
        subject=Subject(
            type="delegation",
            ref=incident_id,
            summary=f"Incident {incident_id} delegated to autonomous handling"
        ),
        judgment=Judgment(
            action="delegate",
            confidence=1.0,  # human decision
            reasoning=f"Delegated by {actor}: safe actions only, summarise when done"
        ),
        producer=Producer(system="human", instance=actor)
    )
    verdict_store.put(v)

    # 2. Update incident governance policy
    incident = get_incident(incident_id)
    incident.governance.mode = "delegated"
    incident.governance.constraints = config.constraints   # safe_actions_only, etc.
    incident.governance.notification_mode = "on_resolution_or_escalation"
    incident.governance.delegated_by = actor
    incident.governance.delegated_at = now()

    # 3. Mayday coordinator continues processing with modified notification behaviour
    # (no updates sent during delegated mode, only escalation or resolution)
```

**Escalation from delegation (transport, threshold check):**

```python
def check_delegation_escalation(incident: IncidentContext, remediation_result: RemediationResult) -> bool:
    """
    If the remediation agent proposes an action that isn't pre-approved,
    escalate back to the delegating SRE.
    """
    if incident.governance.mode != "delegated":
        return False

    if remediation_result.action_type == "requires_approval":
        return True  # safe actions exhausted, must escalate

    return False
```

**Resolution summary after delegation (transport, template):**

```python
DELEGATION_SUMMARY_TEMPLATE = """
Delegation summary: {incident_id} (resolved autonomously)

Action taken: {remediation_summary}
{outcome_summary}
Duration: {duration}. No human involvement after delegation.

Verdict chain: [{verdict_link}]
Post-incident review: [{review_link}]
"""
```

**Configuration:**

```yaml
spec:
  oncall:
    delegation:
      enabled: true
      max_autonomous_duration: 2h      # auto-escalate if not resolved within 2 hours
      safe_actions_only: true           # default constraint (can be overridden per delegation)
      summary_on_resolution: true       # send summary when incident resolves autonomously
```


## 7. CLI Commands

All features are also accessible via CLI for SREs who prefer the terminal.

```bash
# Paging brief for a specific incident
opensrm brief INC-2026-0142

# Shift report for a time window
opensrm shift-report --from "2026-03-07T08:00" --to "2026-03-08T08:00"

# Suppress an alert pattern
opensrm suppress payment-api latency_p99 --window 02:00-04:00 --reason "nightly backup"

# List active suppressions
opensrm suppressions list

# Review suppression (confirm it's still valid)
opensrm suppressions review sup-payment-api-backup

# Generate post-incident review
opensrm post-incident INC-2026-0142

# Check action item completion
opensrm action-items --status pending

# Delegate an incident
opensrm delegate INC-2026-0143 --safe-actions-only

# Ecosystem health check
opensrm status
# Output:
#   Arbiter: operational (accuracy 0.94, 30d)
#   SitRep: operational (accuracy 0.87, 30d)
#   Mayday: insufficient data (< 10 incidents)
#   Verdict store: healthy (12,847 verdicts, 234 pending review)
#   Pending reviews: 5 (1 overdue)
#   Open action items: 3
#   Active suppressions: 2

# Quick verdict review from terminal
verdict review --pending --overdue
verdict confirm vrd-0142 --reason "reviewed, judgment was correct"
verdict override vrd-0139 --action reject --reason "missed rate limiting"
```


## Implementation Priority

1. **Paging brief** (highest immediate value, transforms the on-call experience). Requires: Mayday coordinator integration, notification channel setup, reply handling.

2. **Shift report** (daily value, no incident required). Requires: verdict queries, template, scheduled delivery.

3. **Post-incident review generation** (closes the documentation gap after every incident). Requires: Mayday post-incident processing, timeline reconstruction, action item creation.

4. **Action item tracking** (closes the learning loop). Requires: action item verdicts, completion detection, recurring pattern check.

5. **Alert suppression** (reduces toil over time). Requires: suppression schema in manifest, NthLayer rule regeneration, SitRep integration, baseline computation.

6. **Confidence dashboard** (builds calibrated trust). Requires: NthLayer Grafana template, verdict accuracy metrics in Prometheus.

7. **Delegation mode** (enables focused attention during multi-incident situations). Requires: governance policy modification, escalation detection, summary generation.

8. **CLI commands** (terminal-first SRE workflow). Can be implemented incrementally alongside each feature.

Items 1-3 give the SRE an immediately better on-call experience. Items 4-5 reduce toil over time. Items 6-7 enable sophisticated trust and delegation. Item 8 is ongoing.


## Relationship to Other Specs

| Spec | What This Document Adds |
|------|------------------------|
| **MAYDAY.md** | Paging brief generation in the coordinator, post-incident review generation in `_finalise_incident()`, delegation mode as a governance modifier |
| **VERDICT.md** | Suppression verdicts, action item verdicts, delegation verdicts as new subject types |
| **SITREP-PRECORRELATION.md** | Suppression integration in the pre-correlation engine (deprioritise suppressed signals) |
| **ECOSYSTEM-GAPS.md** | Notification configuration (used by all features here), contract manifests (used by delegation escalation) |
| **BRIEF.md** | On-call configuration section in the OpenSRM manifest (`spec.oncall`), suppression schema (`spec.suppressions`) |
| **COSTOPTIMISATION.md** | One optional model call per post-incident review. All other features are zero model cost. |
