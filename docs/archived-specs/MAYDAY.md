# MAYDAY.md — Multi-Agent Incident Response Specification

This document specifies the Mayday component: a purpose-built incident response pipeline where specialised agents collaborate under human supervision to triage, investigate, communicate about, and remediate incidents. Mayday is the most agentic component in the ecosystem and intentionally the last one teams adopt (Tier 3).

Read VERDICT.md first (Mayday produces and consumes verdicts). Read SITREP-PRECORRELATION.md for context on how SitRep provides correlated intelligence that Mayday consumes.


## Core Principle

**The coordinator is transport. The agents are judgment.**

The coordinator is a deterministic state machine that sequences function calls. It doesn't reason about what to do next. The pipeline is fixed: triage → investigation + communication (parallel) → remediation + communication (parallel). Agents reason within their step. The coordinator handles sequencing, timeout, fallback, and lifecycle management.

This is ZFC applied to incident response. The coordinator is code. Each agent is a model call with a focused prompt, structured input, and structured output.


## Architecture Overview

```
Incident Trigger
(SitRep correlation verdict, PagerDuty webhook, manual declaration)
       │
       ▼
┌──────────────────────────────────────────────────────────────┐
│                     COORDINATOR                               │
│                                                               │
│  Deterministic state machine. Not an agent. No model calls.  │
│  Sequences agent functions, manages incident context,         │
│  enforces timeouts and authority boundaries.                  │
│                                                               │
│  ┌─────────┐   ┌─────────────┐   ┌─────────────┐            │
│  │ Triage  │──▶│ Investigate │──▶│ Remediate   │            │
│  │         │   │             │   │             │            │
│  │         │   │  parallel   │   │  parallel   │            │
│  │         │   │  with:      │   │  with:      │            │
│  │         │   │             │   │             │            │
│  │         │   │ Communicate │   │ Communicate │            │
│  └─────────┘   └─────────────┘   └─────────────┘            │
│       │              │                  │                     │
│       ▼              ▼                  ▼                     │
│  ┌──────────────────────────────────────────────────────┐    │
│  │          SHARED INCIDENT CONTEXT                      │    │
│  │  Accumulates findings from each agent.                │    │
│  │  All agents read from and write to this object.       │    │
│  │  In-memory within the coordinator process.            │    │
│  └──────────────────────────────────────────────────────┘    │
│       │                                                       │
│       ▼                                                       │
│  ┌──────────────────────────────────────────────────────┐    │
│  │          VERDICT STORE                                │    │
│  │  Every agent judgment produces a verdict with         │    │
│  │  lineage linking to its inputs.                       │    │
│  └──────────────────────────────────────────────────────┘    │
└──────────────────────────────────────────────────────────────┘
```


## The Coordinator

The coordinator is the entry point for Mayday. It receives incident triggers, creates the incident context, sequences agent calls, enforces boundaries, and manages the incident lifecycle.

### Interface

```python
class MaydayCoordinator:
    def __init__(self, config: MaydayConfig, verdict_store: VerdictStore):
        """
        config: Mayday configuration (model settings, timeouts, safe actions)
        verdict_store: shared verdict store for reading SitRep verdicts and writing Mayday verdicts
        """

    async def handle_incident(self, trigger: IncidentTrigger) -> IncidentOutcome:
        """
        Main entry point. Runs the full incident pipeline.
        Returns when the incident is resolved or escalated to humans.
        """

    async def handle_escalation(self, incident_id: str, human_input: HumanInput) -> None:
        """
        Called when a human provides input to an active incident
        (severity override, root cause correction, remediation approval).
        """
```

### Incident Trigger Schema

```python
@dataclass
class IncidentTrigger:
    source: str                          # "sitrep" | "pagerduty" | "webhook" | "manual"
    timestamp: str                       # ISO 8601
    source_id: str                       # SitRep verdict ID, PagerDuty incident ID, etc.

    # Pre-populated if from SitRep (correlation verdicts provide rich context)
    sitrep_verdicts: list[Verdict]       # correlation verdicts that triggered this incident
    affected_services: list[str]         # services mentioned in SitRep verdicts
    candidate_changes: list[dict]        # recent changes from SitRep's change attribution

    # Pre-populated if from PagerDuty or other alerting
    alert_details: dict | None           # raw alert payload
    severity_hint: int | None            # source-suggested severity (Mayday may override)
```

### Pipeline Execution

The coordinator runs the pipeline as direct function calls within a single process. No message bus, no mailbox system, no separate processes.

```python
async def handle_incident(self, trigger: IncidentTrigger) -> IncidentOutcome:
    # 1. Create incident context
    context = IncidentContext.create(trigger)

    # 2. Triage (sequential, must complete before anything else)
    triage_result = await self._run_agent(
        agent=self.triage_agent,
        context=context,
        timeout=self.config.triage_timeout,       # default 120s
        fallback=self._triage_fallback             # template-based if model unavailable
    )
    context.update_triage(triage_result)

    # 3. Investigation + Communication (parallel)
    investigation_task = self._run_agent(
        agent=self.investigation_agent,
        context=context,
        timeout=self.config.investigation_timeout,  # default 600s
        fallback=self._investigation_fallback
    )
    initial_comms_task = self._run_agent(
        agent=self.communication_agent,
        context=context,
        timeout=self.config.communication_timeout,  # default 60s
        fallback=self._communication_fallback,
        phase="initial"
    )
    investigation_result, initial_comms_result = await asyncio.gather(
        investigation_task, initial_comms_task
    )
    context.update_investigation(investigation_result)
    context.update_communication(initial_comms_result)

    # 4. If root cause found with sufficient confidence, proceed to remediation
    if context.investigation.root_cause and context.investigation.root_cause_confidence >= self.config.root_cause_confidence_threshold:  # default 0.6

        # 5. Remediation + Updated Communication (parallel)
        remediation_task = self._run_agent(
            agent=self.remediation_agent,
            context=context,
            timeout=self.config.remediation_timeout,  # default 300s
            fallback=self._remediation_fallback
        )
        update_comms_task = self._run_agent(
            agent=self.communication_agent,
            context=context,
            timeout=self.config.communication_timeout,
            fallback=self._communication_fallback,
            phase="root_cause_found"
        )
        remediation_result, update_comms_result = await asyncio.gather(
            remediation_task, update_comms_task
        )
        context.update_remediation(remediation_result)
        context.update_communication(update_comms_result)

        # 6. Execute remediation if approved
        if remediation_result.action_type == "safe_action":
            execution_result = await self._execute_safe_action(remediation_result, context)
            context.update_execution(execution_result)
        else:
            # Requires human approval, escalate
            await self._escalate_for_approval(context, remediation_result)

    else:
        # Root cause not found with sufficient confidence, escalate
        await self._escalate_for_investigation(context)

    # 7. Post-incident
    return self._finalise_incident(context)
```

### Agent Runner

Each agent call follows the same pattern: assemble prompt, call model, parse response, emit verdict.

```python
async def _run_agent(self, agent, context, timeout, fallback, **kwargs):
    """
    Runs a single agent with timeout and fallback.
    All agents follow the same interface.
    """
    try:
        result = await asyncio.wait_for(
            agent.run(context, **kwargs),
            timeout=timeout
        )
        return result
    except asyncio.TimeoutError:
        # Agent timed out, use fallback
        result = fallback(context, **kwargs)
        result.metadata["degraded"] = True
        result.metadata["reason"] = f"agent timed out after {timeout}s"
        return result
    except ModelUnavailableError:
        # Model API down, use fallback
        result = fallback(context, **kwargs)
        result.metadata["degraded"] = True
        result.metadata["reason"] = "model API unavailable"
        return result
```


## Shared Incident Context

All agents read from and write to a single incident context object. This is not a database. It's an in-memory data structure passed between function calls within the coordinator process.

```python
@dataclass
class IncidentContext:
    # Identity
    id: str                              # INC-{year}-{sequence}
    declared_at: str                     # ISO 8601
    source: str                          # what triggered this incident
    trigger: IncidentTrigger             # the original trigger

    # SitRep context (from trigger or queried at start)
    sitrep_verdicts: list[Verdict]       # correlation verdicts providing pre-correlated context
    topology: dict                       # service dependency graph (from NthLayer or SitRep)
    slo_targets: dict                    # per-service SLO targets (from OpenSRM manifest)

    # Triage (filled by Triage agent)
    triage: TriageResult | None

    # Investigation (filled by Investigation agent)
    investigation: InvestigationResult | None

    # Communication (accumulated)
    communications: list[CommunicationResult]

    # Remediation (filled by Remediation agent)
    remediation: RemediationResult | None
    execution: ExecutionResult | None

    # Lifecycle
    status: str                          # active | escalated | resolved | post_mortem
    escalations: list[EscalationRecord]  # human interventions during the incident
    resolved_at: str | None
    resolution_summary: str | None

    # Verdict chain
    verdict_ids: list[str]               # all verdict IDs produced during this incident

    @classmethod
    def create(cls, trigger: IncidentTrigger) -> "IncidentContext":
        return cls(
            id=generate_incident_id(),
            declared_at=now_iso(),
            source=trigger.source,
            trigger=trigger,
            sitrep_verdicts=trigger.sitrep_verdicts,
            topology={},
            slo_targets={},
            triage=None,
            investigation=None,
            communications=[],
            remediation=None,
            execution=None,
            status="active",
            escalations=[],
            resolved_at=None,
            resolution_summary=None,
            verdict_ids=[]
        )
```


## Agent Specifications

### Common Agent Interface

Every Mayday agent implements the same interface. The coordinator doesn't know the internals of any agent. It calls `run()`, gets a result, emits a verdict.

```python
class MaydayAgent:
    def __init__(self, config: AgentConfig, verdict_store: VerdictStore):
        self.config = config
        self.verdict_store = verdict_store
        self.model = ModelClient(config.model, config.max_tokens)

    async def run(self, context: IncidentContext, **kwargs) -> AgentResult:
        """
        1. Assemble prompt from context + agent-specific template
        2. Call model
        3. Parse structured response
        4. Emit verdict with lineage to input verdicts
        5. Return result
        """
        prompt = self.build_prompt(context, **kwargs)
        raw_response = await self.model.complete(prompt)
        result = self.parse_response(raw_response, context)
        self.emit_verdict(result, context)
        return result

    def build_prompt(self, context, **kwargs) -> str:
        """Subclasses implement: assemble the prompt from context and template."""
        raise NotImplementedError

    def parse_response(self, raw: str, context: IncidentContext) -> AgentResult:
        """Subclasses implement: parse model output into structured result."""
        raise NotImplementedError

    def emit_verdict(self, result: AgentResult, context: IncidentContext):
        """
        Common verdict emission. All agents emit verdicts with lineage
        linking to the SitRep verdicts and any prior Mayday verdicts.
        """
        v = verdict.create(
            subject=Subject(
                type=self.verdict_type,         # triage | investigation | communication | remediation
                service=result.primary_service,
                ref=context.id,
                summary=result.summary
            ),
            judgment=Judgment(
                action=result.action,
                confidence=result.confidence,
                reasoning=result.reasoning,
                tags=result.tags
            ),
            producer=Producer(
                system="mayday",
                instance=self.agent_name,
                model=self.config.model
            ),
            lineage=Lineage(
                context=[v.id for v in context.sitrep_verdicts],
                parent=context.verdict_ids[-1] if context.verdict_ids else None
            )
        )
        self.verdict_store.put(v)
        context.verdict_ids.append(v.id)
```

### Triage Agent

**Purpose:** Assess severity and blast radius. Determine which services are affected, which teams own them, and how urgent the response needs to be.

**Inputs (assembled into prompt):**
- SitRep correlation verdicts (pre-correlated context, candidate changes)
- Service topology from OpenSRM manifest (dependency graph)
- Active SLO status (which SLOs are currently breaching, queried from Prometheus via tool call)
- Historical incident data (optional, recent incidents on the same services)

**Prompt Template:**

```
You are the Triage agent for an incident response system. Your single job is to assess severity and blast radius. Do not investigate root cause. Do not suggest fixes. Only classify.

INCIDENT TRIGGER:
{trigger_summary}

SITREP CORRELATION VERDICTS:
{formatted_sitrep_verdicts}

SERVICE TOPOLOGY:
{topology_subgraph_for_affected_services}

CURRENT SLO STATUS:
{slo_breach_summary}

SEVERITY GUIDE:
P1: Customer-facing impact, revenue loss, data integrity risk
P2: Significant degradation, no data loss, workaround exists
P3: Minor impact, limited blast radius, no customer-facing effect
P4: Cosmetic or non-urgent, can wait for normal working hours

Respond in this exact format:
SEVERITY: P1|P2|P3|P4
BLAST_RADIUS: [list of affected services]
AFFECTED_SLOS: [list of breaching SLOs]
OWNING_TEAMS: [list of teams to page]
CONFIDENCE: 0.0-1.0
REASONING: [2-3 sentences explaining the classification]
ESCALATION_NOTES: [anything unusual that the investigation agent should know]
```

**Output Schema:**

```python
@dataclass
class TriageResult:
    severity: int                        # 1-4
    blast_radius: list[str]              # affected service names
    affected_slos: list[str]             # SLO identifiers currently breaching
    owning_teams: list[str]              # teams to page
    confidence: float                    # 0.0-1.0
    reasoning: str
    escalation_notes: str | None
    summary: str                         # one-line summary for verdict
    action: str = "escalate"             # triage always escalates to investigation
    primary_service: str = ""            # most affected service
    tags: list[str] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)
```

**Tool Calls:** The triage agent may call:
- `nthlayer topology export` (deterministic: get dependency graph for affected services)
- Prometheus query (deterministic: get current SLO status for affected services)
- PagerDuty API (deterministic: create incident, page teams based on severity and owning_teams)

**Decision Authority:** Can set severity. Can page teams. Can assign ownership. Cannot remediate. Cannot override existing incident classification without human approval.

**Judgment SLO:** Severity reversal rate. Target: less than 10% of severity assignments are overridden by humans.

**Fallback (model unavailable):** Template-based triage using SitRep verdict severity scores and service tier from the manifest. Severity = highest SitRep severity mapped to P1-P4. Blast radius = services mentioned in SitRep verdicts. Confidence = 0.0. Reasoning = "template-based, model unavailable".


### Investigation Agent

**Purpose:** Generate hypotheses about root cause, gather evidence, and rank hypotheses by confidence.

**Inputs (assembled into prompt):**
- Triage result (severity, blast radius, affected SLOs)
- SitRep correlation verdicts (candidate changes, temporal correlations)
- Service topology (dependency paths between affected services)
- Recent change history (deploys, config changes, model version swaps from the change event index)
- Metric snapshots for affected services (queried from Prometheus)
- Recent log patterns (if log search is available)

**Prompt Template:**

```
You are the Investigation agent for an incident response system. Your job is to identify the root cause of this incident. You have access to tools for querying metrics and logs.

TRIAGE SUMMARY:
Severity: {severity}
Blast radius: {blast_radius}
Affected SLOs: {affected_slos}

SITREP CORRELATION VERDICTS:
{formatted_sitrep_verdicts_with_candidate_changes}

SERVICE TOPOLOGY (relevant subgraph):
{topology}

RECENT CHANGES (last 2 hours):
{changes_formatted}

CURRENT METRICS:
{metric_snapshots}

Form hypotheses about the root cause. For each hypothesis:
1. State the hypothesis clearly
2. List the evidence supporting it
3. List evidence against it or gaps in evidence
4. Assign a confidence score

If you need more evidence, use the available tools to query metrics or logs, then update your hypotheses.

When one hypothesis reaches confidence >= {root_cause_confidence_threshold}, declare it as the root cause.

Respond in this exact format:
HYPOTHESES:
- H1: [description]
  CONFIDENCE: 0.0-1.0
  EVIDENCE_FOR: [list]
  EVIDENCE_AGAINST: [list]
  EVIDENCE_GAPS: [list]
- H2: ...

ROOT_CAUSE: H1|H2|...|NONE
ROOT_CAUSE_CONFIDENCE: 0.0-1.0
ROOT_CAUSE_EXPLANATION: [detailed explanation of the causal chain]
RECOMMENDED_INVESTIGATION: [if no root cause found, what should be investigated next]
```

**Output Schema:**

```python
@dataclass
class Hypothesis:
    id: str                              # H1, H2, etc.
    description: str
    confidence: float
    evidence_for: list[str]
    evidence_against: list[str]
    evidence_gaps: list[str]

@dataclass
class InvestigationResult:
    hypotheses: list[Hypothesis]
    root_cause: str | None               # hypothesis ID or None
    root_cause_confidence: float
    root_cause_explanation: str
    recommended_investigation: str | None  # if no root cause found
    confidence: float                    # overall investigation confidence
    reasoning: str
    summary: str
    action: str                          # "root_cause_found" | "escalate" | "inconclusive"
    primary_service: str
    tags: list[str] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)
```

**Tool Calls:**
- Prometheus queries (metric retrieval for affected services, specific metric investigation)
- Log search APIs (pattern matching, error extraction)
- `nthlayer topology export` (dependency path exploration)
- Deployment history lookup (via Git/ArgoCD APIs)
- Verdict store query (historical verdicts for the same services, previous incident patterns)

**Decision Authority:** Can form and rank hypotheses. Can declare root cause when confidence exceeds threshold. Cannot execute any remediation. Publishes findings to incident context.

**Judgment SLO:** Root cause agreement with post-incident review. Target: 70% agreement at maturity.

**Fallback:** Returns hypotheses based solely on SitRep's correlation verdicts without additional investigation. Root cause = SitRep's highest-confidence correlation. Confidence reduced by 0.3 from SitRep's confidence. Reasoning notes model unavailability.

**Investigation Iteration:** The coordinator may re-run the investigation agent if:
- Initial run returns no root cause and time permits (configurable max investigation iterations, default 3)
- Each re-run receives the previous hypotheses and updated context
- If max iterations reached without root cause, escalate to human

```python
# In coordinator
for iteration in range(self.config.max_investigation_iterations):
    investigation_result = await self._run_agent(
        agent=self.investigation_agent,
        context=context,
        timeout=self.config.investigation_timeout,
        fallback=self._investigation_fallback,
        iteration=iteration
    )
    context.update_investigation(investigation_result)

    if investigation_result.root_cause:
        break

    if iteration < self.config.max_investigation_iterations - 1:
        # Gather more evidence for next iteration
        await self._gather_additional_evidence(context, investigation_result)
```


### Communication Agent

**Purpose:** Draft audience-appropriate messages for stakeholders. Selects channels, determines detail level, manages update timing.

**Inputs (assembled into prompt):**
- Incident context (triage result, investigation findings, remediation status)
- Stakeholder map from OpenSRM ownership fields
- Phase indicator (initial, root_cause_found, remediation_in_progress, resolved)
- Communication history (what has already been sent, to avoid repetition)

**Prompt Template:**

```
You are the Communication agent for an incident response system. Draft a stakeholder update appropriate for the current incident phase.

INCIDENT SUMMARY:
ID: {incident_id}
Severity: {severity}
Status: {phase}
Blast radius: {blast_radius}

INVESTIGATION STATUS:
{investigation_summary_or_pending}

REMEDIATION STATUS:
{remediation_summary_or_pending}

PREVIOUS COMMUNICATIONS:
{communication_history}

STAKEHOLDER MAP:
{stakeholder_channels_and_audiences}

Draft messages for each required channel. Adapt the detail level and tone for the audience:
- Technical channel (#platform-incidents): detailed, include metrics and hypotheses
- Status page: customer-facing, no internal details, focus on impact and ETA
- Management: high-level, focus on business impact and timeline

Do not contradict investigation findings. Do not promise resolution times unless remediation is confirmed. If this is an update, only include new information since the last communication.

Respond in this exact format:
MESSAGES:
- CHANNEL: [channel name or type]
  AUDIENCE: [technical | customer | management]
  CONTENT: [message text]
  URGENCY: [immediate | normal | low]
```

**Output Schema:**

```python
@dataclass
class Message:
    channel: str
    audience: str                        # technical | customer | management
    content: str
    urgency: str                         # immediate | normal | low

@dataclass
class CommunicationResult:
    messages: list[Message]
    phase: str                           # initial | root_cause_found | remediation | resolved
    confidence: float
    reasoning: str
    summary: str
    action: str = "communicate"
    primary_service: str = ""
    tags: list[str] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)
```

**Tool Calls:**
- Slack API (send messages to channels)
- Status page API (create or update incident on status page)
- Email API (send to stakeholder distribution lists)

**Decision Authority:** Can draft and send updates within pre-approved templates. Can choose channels and timing. Cannot send communications that contradict investigation findings. Cannot communicate resolution until remediation is confirmed.

**Judgment SLO:** Human edit rate on outgoing communications. Target: less than 15% of messages require human editing before or after send.

**Fallback:** Template-based messages using incident context fields. "We are investigating an issue affecting {blast_radius}. Severity: {severity}. We will provide updates as more information becomes available."


### Remediation Agent

**Purpose:** Propose and (if pre-approved) execute fixes. Assess risk of each option. Determine whether the fix requires human approval.

**Inputs (assembled into prompt):**
- Investigation result (root cause, confidence, causal chain)
- Safe action registry from OpenSRM manifest
- Current system state (deployment versions, feature flag states)
- Change history (what can be rolled back)
- Blast radius from triage

**Prompt Template:**

```
You are the Remediation agent for an incident response system. Propose a fix for the identified root cause.

ROOT CAUSE:
{root_cause_explanation}
Confidence: {root_cause_confidence}

CURRENT STATE:
{current_deployment_versions}
{current_feature_flag_states}

AVAILABLE SAFE ACTIONS (pre-approved, can execute without human approval):
{safe_actions_from_manifest}

BLAST RADIUS:
{blast_radius}

CHANGE HISTORY (rollback candidates):
{recent_changes_with_rollback_availability}

Propose a remediation action. For each option:
1. Describe the action
2. Assess the risk (will this fix it? could it make things worse?)
3. Estimate time to resolution
4. Classify: safe_action (pre-approved) or requires_approval

If the best option is a safe action, recommend it for immediate execution.
If the best option requires approval, explain why and what the human needs to decide.

Respond in this exact format:
PROPOSED_ACTION: [description]
ACTION_TYPE: safe_action | requires_approval
TARGET_SERVICE: [service name]
SPECIFIC_ACTION: rollback | feature_flag_disable | scale_up | config_revert | custom
ACTION_DETAILS:
  [action-specific fields, e.g., rollback_to_version, flag_name, scale_target]
RISK_ASSESSMENT: low | medium | high
RISK_EXPLANATION: [why this risk level]
ESTIMATED_RESOLUTION_TIME: [duration]
CONFIDENCE: 0.0-1.0
REASONING: [why this is the best option]
ALTERNATIVES:
- [other options considered and why they were not chosen]
```

**Output Schema:**

```python
@dataclass
class RemediationResult:
    proposed_action: str
    action_type: str                     # safe_action | requires_approval
    target_service: str
    specific_action: str                 # rollback | feature_flag_disable | scale_up | config_revert | custom
    action_details: dict                 # action-specific parameters
    risk_assessment: str                 # low | medium | high
    risk_explanation: str
    estimated_resolution_time: str
    alternatives: list[dict]
    confidence: float
    reasoning: str
    summary: str
    action: str                          # "execute" | "request_approval"
    primary_service: str = ""
    tags: list[str] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)
```

**Tool Calls:**
- ArgoCD API (rollback deployment)
- Feature flag APIs (LaunchDarkly toggle)
- Kubernetes API (scale HPA, restart pods)
- `nthlayer check-deploy` (verify error budget allows the action)
- Git API (revert commit if needed)

**Decision Authority:** Can suggest fixes to humans. Can execute pre-approved safe actions without human approval. Cannot execute novel remediation. Cannot make changes to services outside the blast radius.

**Judgment SLO:** Fix success rate and time-to-remediation. Target: 80% fix success rate.

**Fallback:** Lists available safe actions for the affected services (from the manifest) with "human review recommended" flag. No execution without model confidence.


## Safe Action Registry

Safe actions are declared in the OpenSRM manifest. They define what the Remediation agent can execute without human approval. Everything not in the registry requires approval.

```yaml
# In service.reliability.yaml
spec:
  safe_actions:
    - action: rollback
      description: "Rollback to the previous deployment version"
      target: self                       # this service only
      conditions:
        - "previous_version_healthy: true"   # only if previous version was healthy
        - "rollback_available: true"         # only if the change source supports rollback
      max_blast_radius: 1                # only if this is the only affected service
      cooldown: 30m                      # don't rollback again within 30 minutes

    - action: feature_flag_disable
      description: "Disable a feature flag that was recently enabled"
      target: self
      conditions:
        - "flag_changed_within: 2h"      # only if the flag was changed recently
      max_blast_radius: 3

    - action: scale_up
      description: "Increase replica count or HPA target"
      target: self
      conditions:
        - "current_replicas < max_replicas"
      scale_factor: 2                    # at most double the current count
      cooldown: 15m

    - action: config_revert
      description: "Revert a configuration change"
      target: self
      conditions:
        - "config_changed_within: 2h"
        - "previous_config_available: true"
      max_blast_radius: 1
```

### Safe Action Evaluation

When the Remediation agent proposes a safe action, the coordinator validates it against the registry before execution:

```python
async def _execute_safe_action(self, remediation: RemediationResult, context: IncidentContext):
    # 1. Find the matching safe action in the manifest
    safe_action = self._find_safe_action(
        remediation.specific_action,
        remediation.target_service,
        context
    )

    if not safe_action:
        # No matching safe action, escalate for approval
        return await self._escalate_for_approval(context, remediation)

    # 2. Validate conditions
    conditions_met = self._validate_conditions(safe_action.conditions, context)
    if not conditions_met:
        return await self._escalate_for_approval(context, remediation)

    # 3. Check cooldown
    if self._in_cooldown(safe_action, remediation.target_service):
        return await self._escalate_for_approval(context, remediation)

    # 4. Check blast radius
    if len(context.triage.blast_radius) > safe_action.max_blast_radius:
        return await self._escalate_for_approval(context, remediation)

    # 5. Execute
    execution_result = await self._execute(remediation)

    # 6. Emit execution verdict
    self._emit_execution_verdict(execution_result, remediation, context)

    return execution_result
```

This validation is entirely deterministic (transport). The model proposes. The transport validates and executes (or escalates).


## Incident Lifecycle

### States

```
DECLARED → TRIAGING → INVESTIGATING → REMEDIATING → RESOLVED
                          │                  │
                          ▼                  ▼
                      ESCALATED ◀────── ESCALATED
                          │
                          ▼
                    HUMAN_ACTIVE
                          │
                          ▼
                      RESOLVED
```

| State | Entry Condition | What Happens |
|-------|----------------|--------------|
| DECLARED | Trigger received | Coordinator creates context, queries SitRep for latest verdicts |
| TRIAGING | Context created | Triage agent runs, pages teams, sets severity |
| INVESTIGATING | Triage complete | Investigation + Communication agents run in parallel |
| REMEDIATING | Root cause found | Remediation + Communication agents run in parallel |
| ESCALATED | Agent can't proceed (no root cause, needs approval, model down) | Human notified with full context, awaiting input |
| HUMAN_ACTIVE | Human provides input | Coordinator updates context, may re-run agents with new info |
| RESOLVED | Remediation confirmed or human declares resolved | Post-incident processing begins |

### Escalation

Escalation happens when:
- Triage agent can't classify severity (model unavailable, ambiguous signals)
- Investigation agent exhausts max iterations without finding root cause
- Remediation agent proposes an action that isn't in the safe action registry
- Any agent's confidence is below a configurable floor (default 0.3)
- Human override is received at any point

Escalation produces a verdict:

```python
def _escalate(self, context, reason, agent_result=None):
    v = verdict.create(
        subject=Subject(
            type="escalation",
            service=context.triage.blast_radius[0] if context.triage else "unknown",
            ref=context.id,
            summary=f"Incident {context.id} escalated: {reason}"
        ),
        judgment=Judgment(
            action="escalate",
            confidence=agent_result.confidence if agent_result else 0.0,
            reasoning=reason
        ),
        producer=Producer(system="mayday", instance="coordinator")
    )
    self.verdict_store.put(v)
    context.verdict_ids.append(v.id)
    context.status = "escalated"

    # Notify via configured channels
    self._notify_escalation(context, reason)
```

### Human Input

When a human responds to an escalation (or proactively overrides at any point), the coordinator receives structured input:

```python
@dataclass
class HumanInput:
    incident_id: str
    input_type: str                      # severity_override | root_cause_correction |
                                         # remediation_approval | remediation_rejection |
                                         # additional_context | resolve
    payload: dict                        # type-specific data
    actor: str                           # human:name
    timestamp: str

# Example: human overrides severity
HumanInput(
    incident_id="INC-2026-0142",
    input_type="severity_override",
    payload={"new_severity": 1, "reason": "customer-facing revenue impact confirmed"},
    actor="human:rob",
    timestamp="2026-02-23T14:45:00Z"
)

# Example: human approves remediation
HumanInput(
    incident_id="INC-2026-0142",
    input_type="remediation_approval",
    payload={"approved_action": "rollback", "modifications": None},
    actor="human:rob",
    timestamp="2026-02-23T14:52:00Z"
)
```

Human input produces override verdicts linked to the relevant agent verdict:

```python
async def handle_escalation(self, incident_id, human_input):
    context = self._get_active_incident(incident_id)

    if human_input.input_type == "severity_override":
        # Resolve the triage verdict as overridden
        triage_verdict_id = context.verdict_ids[0]  # first verdict is always triage
        verdict.resolve(
            verdict_id=triage_verdict_id,
            status="overridden",
            override=Override(
                by=human_input.actor,
                action=f"severity changed to P{human_input.payload['new_severity']}",
                reasoning=human_input.payload["reason"]
            )
        )
        context.triage.severity = human_input.payload["new_severity"]

    elif human_input.input_type == "remediation_approval":
        # Execute the proposed remediation
        execution_result = await self._execute(context.remediation)
        context.update_execution(execution_result)

    elif human_input.input_type == "resolve":
        context.status = "resolved"
        context.resolved_at = human_input.timestamp
        context.resolution_summary = human_input.payload.get("summary", "")
        self._finalise_incident(context)
```


## Post-Incident Processing

When an incident resolves, the coordinator runs post-incident processing:

```python
def _finalise_incident(self, context: IncidentContext) -> IncidentOutcome:
    # 1. Resolve all pending verdicts in the chain
    for verdict_id in context.verdict_ids:
        v = self.verdict_store.get(verdict_id)
        if v.outcome.status == "pending":
            # If no human override, mark as confirmed (incident resolved successfully)
            verdict.resolve(verdict_id, status="confirmed")

    # 2. Export the verdict chain as a scenario (for replay)
    scenario = self._export_scenario(context)
    # Write to scenarios/real/ directory for future replay testing

    # 3. Produce post-incident summary verdict
    summary_verdict = verdict.create(
        subject=Subject(
            type="incident_summary",
            ref=context.id,
            summary=f"Incident {context.id} resolved: {context.resolution_summary}"
        ),
        judgment=Judgment(
            action="resolve",
            confidence=1.0,  # post-incident, we know the outcome
            reasoning=self._build_incident_summary(context)
        ),
        producer=Producer(system="mayday", instance="coordinator"),
        lineage=Lineage(context=context.verdict_ids)
    )
    self.verdict_store.put(summary_verdict)

    # 4. Return outcome for learning loop
    return IncidentOutcome(
        incident_id=context.id,
        duration=context.resolved_at - context.declared_at,
        severity=context.triage.severity,
        root_cause=context.investigation.root_cause_explanation if context.investigation else None,
        remediation_action=context.remediation.proposed_action if context.remediation else None,
        verdict_chain=context.verdict_ids,
        scenario_path=scenario.path if scenario else None
    )
```

### Scenario Export

The post-incident scenario export creates a replay-ready scenario from the incident's event stream and verdict chain:

```python
def _export_scenario(self, context: IncidentContext):
    """
    Converts an incident's events and verdicts into a scenario file
    for future replay testing. Anonymises by default.
    """
    scenario = {
        "id": f"scn-{context.id}",
        "source": "real-incident",
        "anonymised": True,
        "description": context.resolution_summary,
        "duration": str(context.resolved_at - context.declared_at),
        "events": self._reconstruct_event_timeline(context),
        "expected_outcomes": {
            "root_cause": context.investigation.root_cause_explanation if context.investigation else None,
            "severity": context.triage.severity if context.triage else None,
            "affected_services": context.triage.blast_radius if context.triage else [],
            "correct_remediation": context.remediation.proposed_action if context.remediation else None
        },
        "expected_verdicts": self._extract_verdict_expectations(context)
    }
    return scenario
```

This closes the learning loop: real incidents become test scenarios for future improvement.


## Integration Points

### SitRep → Mayday

Mayday consumes SitRep's correlation verdicts as the primary incident context. The consumption follows the interaction contract defined in ECOSYSTEM-GAPS.md:

```yaml
# mayday.contracts.yaml
consumes:
  sitrep.correlation_verdicts:
    required: false
    max_staleness: 10m
    on_unavailable: "operate without pre-correlated context, note in verdict reasoning, reduce confidence by 0.2"
    on_stale: "use stale verdicts with reduced confidence, note staleness in verdict reasoning"
    timeout: 5s
```

When Mayday starts processing an incident, the coordinator queries the verdict store for SitRep's recent correlation verdicts:

```python
sitrep_verdicts = self.verdict_store.query(
    producer_system="sitrep",
    subject_type="correlation",
    time_range=last_30_minutes,
    min_confidence=0.3
)
```

If SitRep verdicts are unavailable, Mayday operates without pre-correlated context (all agents note this in their reasoning, confidence is reduced).

### Mayday → Arbiter

The Arbiter measures Mayday's judgment quality through the same verdict accuracy mechanism as any other agent. Each Mayday agent has its own judgment SLO declared in its OpenSRM manifest:

```yaml
# mayday-triage.reliability.yaml
spec:
  type: ai-gate
  slos:
    judgment:
      reversal_rate:
        target: 0.10    # less than 10% severity reversals
        window: 90d
```

### Mayday → NthLayer

NthLayer generates dashboards and recording rules for Mayday's judgment SLOs. No direct integration between Mayday and NthLayer at runtime. Verdicts flow to Prometheus via OTel, NthLayer queries Prometheus.

### Mayday → Notification System

Escalations, resolutions, and communication agent outputs flow through the notification system defined in ECOSYSTEM-GAPS.md. Mayday produces the content, the notification system delivers it.


## Degradation Behaviour

| Failure | Mayday Behaviour |
|---------|-----------------|
| SitRep unavailable | Operate without pre-correlated context. All agents note absence. Confidence reduced. |
| Model API down (all agents) | All agents use fallback (template-based). Coordinator immediately escalates to human. |
| Model API down (one agent) | That agent uses fallback. Other agents proceed normally. |
| Verdict store unavailable | Verdicts buffered in memory. OTel emission continues. Lineage may be incomplete. |
| PagerDuty/Slack unavailable | Retry with exponential backoff. Log the communication attempt. Human may not receive notification. |
| Prometheus unavailable | Triage and Investigation operate with SitRep data only (no live metric queries). Confidence reduced. |
| Coordinator crash | Incident context is lost (in-memory). The incident must be re-triaged if restarted. Verdicts already emitted are durable in the store. |

**Coordinator persistence (deferred):** In Tier 1, the coordinator is stateless (incident context is in-memory). If the coordinator crashes mid-incident, the incident must be re-declared. In future tiers, the incident context could be persisted to the verdict store or a separate state store for crash recovery. This is a Tier 2+ concern.


## Configuration

```yaml
# mayday.yaml
manifest: ./service.reliability.yaml     # OpenSRM manifest (source of truth)

coordinator:
  triage_timeout: 120                    # seconds
  investigation_timeout: 600
  communication_timeout: 60
  remediation_timeout: 300
  max_investigation_iterations: 3
  root_cause_confidence_threshold: 0.6
  min_agent_confidence: 0.3              # below this, escalate to human

agents:
  triage:
    model: claude-sonnet-4-20250514
    max_tokens: 2048
  investigation:
    model: claude-sonnet-4-20250514      # or frontier for critical incidents
    max_tokens: 4096
  communication:
    model: claude-sonnet-4-20250514      # lighter model acceptable
    max_tokens: 2048
  remediation:
    model: claude-sonnet-4-20250514
    max_tokens: 2048

verdict:
  store:
    backend: sqlite
    path: verdicts.db

notifications:
  escalation_channels:
    - type: slack
      webhook: "https://hooks.slack.com/..."
    - type: pagerduty
      service_key: "..."

# Safe actions are read from the OpenSRM manifest, not duplicated here
```


## Implementation Priority

1. **Coordinator with incident context** — the state machine, lifecycle management, agent runner with timeout and fallback. Testable with mock agents.

2. **Triage agent** — first agent to implement. Simplest prompt, clearest output schema. Produces the verdict that everything else links to.

3. **Investigation agent with iteration** — the most complex agent. Implement hypothesis generation and ranking first, tool calls second.

4. **Safe action registry and validation** — the deterministic gate between "agent proposes" and "system executes." Must be rock solid.

5. **Remediation agent** — depends on safe action registry and investigation agent.

6. **Communication agent** — can run with template fallback initially. Model-powered communication is a quality improvement, not a functional requirement.

7. **Human input handling** — escalation, override, approval flows. Verdict resolution from human input.

8. **Post-incident processing** — scenario export, verdict chain resolution, summary generation.

9. **Scenario replay** — `nthlayer-respond replay --scenario scenarios/` for regression testing.

Items 1-4 give you a working Mayday that can triage, investigate, and execute pre-approved safe actions. Items 5-7 complete the agent pipeline. Items 8-9 close the learning loop.
