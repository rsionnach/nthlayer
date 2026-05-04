# NthLayer Serve Mode Spec v2 — Pull-Based Pipeline

**Version:** 2.0-draft
**Supersedes:** Serve Mode Spec v1 (2026-04-12)
**Depends on:** Content-addressed decision records, assessment store, verdict store, case store, OpenSRM v1, OpenSRM RBAC Extension
**Unlocks:** Fully autonomous pipeline with authorisation enforcement, NthLayer Bench v2

---

## 1. Changes from v1

1. **Active-incident deduplication.** Measure and correlate now query for active incidents before emitting new verdicts for the same service/SLO. Eliminates verdict-store noise during active incidents.

2. **Semantic deduplication.** Components deduplicate based on semantic identity (service + SLO + breach class) rather than strict hash equality. An assessment with a slightly different timestamp for the same underlying breach does not trigger duplicate evaluation.

3. **Two new components.** `nthlayer-authorise` (decides whether actions may execute) and `nthlayer-executor` (carries out authorised actions) are added to the pipeline. Respond's remediation agent now emits action_request verdicts rather than invoking remediation directly.

4. **Pipeline liveness.** Each component writes a heartbeat assessment that downstream consumers and the Bench can observe to detect dead components.

5. **Pipeline latency tracking.** Each verdict records the hash chain latency from trigger signal, so end-to-end pipeline health is visible without external instrumentation.

6. **Restart resilience.** Hysteresis and watermark state persist to the component_state table, not just in-memory, so restarts are transparent to downstream consumers.

7. **Reference to Bench spec.** The v1 section describing a "Textual Dashboard Connection" is removed. The Bench is specified independently in its own spec; this document references that spec rather than duplicating content.

8. **Backpressure and retention.** Explicit handling of store growth and processing lag.

---

## 2. Architecture

Every NthLayer runtime component has a `serve` subcommand that runs indefinitely. Each component polls the shared store for new records, processes them, and writes its own records. No HTTP event ingestion between components. No message queue. No webhook receiver. Just store-driven polling on a shared SQLite database in WAL mode.

### 2.1 Pipeline

```
observe serve
  │ polls Prometheus on schedule
  │ writes hashed assessments to store
  │ writes heartbeat assessments
  │
  ▼ (measure polls store for breach assessments)
measure serve
  │ checks for active incidents → suppress duplicate
  │ runs LLM evaluation
  │ writes hashed evaluation verdicts
  │
  ▼ (correlate polls store for new evaluation verdicts with breach=true)
correlate serve
  │ checks for active incidents → suppress duplicate
  │ gathers signals, runs LLM reasoning
  │ writes hashed correlation verdicts
  │
  ▼ (respond polls store for new correlation verdicts)
respond serve  [existing component, extended]
  │ runs agent pipeline (triage → investigation → remediation)
  │ writes incident verdicts
  │ remediation agent emits action_request verdicts
  │ escalation, Slack, approval workflow
  │
  ▼ (authorise polls store for new action_request verdicts)
authorise serve  [NEW]
  │ loads action definitions from manifests
  │ evaluates preconditions and policies
  │ checks approval level → creates case if human approval needed
  │ writes capability or denial verdicts
  │
  ▼ (executor polls store for new capability verdicts)
executor serve  [NEW]
  │ verifies capability, consumes one-shot token
  │ invokes execution binding
  │ runs verification
  │ writes execution verdicts
  │ triggers rollback if verification fails and reversibility allows
  │
  ▼ (learn polls store for resolved incident verdicts and execution outcomes)
learn serve
  │ runs retrospective analysis
  │ writes retrospective verdicts
  │ closes the feedback loop
```

### 2.2 Independence

Each component is independent. Start them in any order. If correlate isn't running, measure still writes evaluation verdicts — they accumulate in the store and correlate processes them when it starts. The store is the integration layer.

### 2.3 Active-Incident Suppression

When an incident is active for a service/SLO combination, upstream components (measure, correlate) suppress duplicate verdicts for the same breach:

```python
# Conceptual check before emitting a new verdict
def should_emit_verdict(service: str, slo_name: str) -> bool:
    active_incidents = store.query_verdicts(VerdictFilter(
        verdict_type="incident",
        service=service,
        status="open",
    ))
    for incident in active_incidents:
        if slo_name in incident.data.get("affected_slos", []):
            return False  # Incident already open, suppress
    return True
```

When suppressed, the component writes a lightweight `verdict_suppressed` audit record rather than the full verdict, so the suppression is visible in the audit trail without polluting the lineage chain.

Incidents are considered closed when their `status` transitions to `resolved` or `closed`. After closure, new breaches emit fresh verdicts even if they look semantically identical to the resolved incident's trigger.

### 2.4 Semantic Deduplication

Within an incident window, each component deduplicates based on semantic identity, not hash equality:

```python
semantic_key = (service, slo_name, breach_class)
# breach_class is one of: availability, latency, error_rate, judgment.*
```

A component records the semantic_keys it has processed in the current window (per-component state). An assessment with a new hash but the same semantic_key within the window is deduplicated. This prevents the "slightly different timestamp" duplicate-emission problem.

Semantic deduplication resets when incidents close, so recurring breaches in subsequent incidents are not suppressed.

---

## 3. Shared Patterns

### 3.1 Component Base Pattern

```python
class ComponentServer:
    """Base pattern for all NthLayer serve modes."""

    component_name: str = "override"

    def __init__(self, config, store):
        self.config = config
        self.store = store
        self._state = ComponentState(
            component_name=self.component_name,
            store=store,
        )
        self._running = False

    async def run(self):
        self._running = True
        logger.info("serve_started", component=self.component_name)

        # Recover watermark from persistent state
        await self._state.load()

        while self._running:
            await self._write_heartbeat()
            try:
                await self._poll_cycle()
            except Exception as e:
                logger.error("poll_cycle_error", error=str(e))
                # Fail-open: log and continue, don't crash

            await asyncio.sleep(self.config.poll_interval_seconds)

    async def _write_heartbeat(self):
        """Write a liveness record so downstream knows we're alive."""
        self.store.put_heartbeat(Heartbeat(
            component=self.component_name,
            timestamp=datetime.now(UTC),
            state_summary=self._state.summary(),
        ))

    async def _poll_cycle(self):
        """Override in each component."""
        raise NotImplementedError
```

### 3.2 ComponentState

Persistent state for each component, stored in a `component_state` table in the shared database:

```python
@dataclass
class ComponentState:
    component_name: str
    store: Any
    last_processed_timestamp: datetime | None = None
    processed_semantic_keys: dict[str, datetime] = field(default_factory=dict)
    hysteresis_counters: dict[str, int] = field(default_factory=dict)

    async def load(self):
        """Restore state from store."""
        record = self.store.get_component_state(self.component_name)
        if record:
            self.last_processed_timestamp = record.last_processed_timestamp
            self.processed_semantic_keys = record.processed_semantic_keys
            self.hysteresis_counters = record.hysteresis_counters

    async def save(self):
        self.store.put_component_state(
            self.component_name,
            self.last_processed_timestamp,
            self.processed_semantic_keys,
            self.hysteresis_counters,
        )

    def summary(self) -> dict:
        return {
            "last_processed": self.last_processed_timestamp,
            "in_flight_breaches": len(self.processed_semantic_keys),
        }
```

State is persisted after every poll cycle. Restarts resume from the last persisted watermark with no gap and no duplicate processing.

### 3.3 Heartbeat

Every component writes a heartbeat record on each poll cycle (before processing). Heartbeats are a lightweight record type in the assessment store:

```python
@dataclass
class Heartbeat:
    component: str              # observe, measure, correlate, respond, authorise, executor, learn
    timestamp: datetime
    state_summary: dict         # component-specific status
    version: str = "1"          # component version for compatibility tracking
```

Components that depend on upstream output can check heartbeats to distinguish "no new work" from "upstream is dead":

```python
async def upstream_alive(upstream: str, max_age_seconds: int = 60) -> bool:
    last_heartbeat = self.store.get_latest_heartbeat(upstream)
    if not last_heartbeat:
        return False
    age = (datetime.now(UTC) - last_heartbeat.timestamp).total_seconds()
    return age < max_age_seconds
```

The Bench surfaces heartbeat status in its Situation Board so operators see when a component is silent.

### 3.4 Pipeline Latency

Every verdict includes a `pipeline_latency` field recording the elapsed time from the triggering signal:

```python
@dataclass
class Verdict:
    # ... existing fields ...
    pipeline_latency_ms: int | None = None   # ms since originating assessment
    chain_depth: int | None = None           # number of verdicts in lineage
```

This lets downstream consumers (and the Bench) display end-to-end pipeline health without external instrumentation. A case shown in the Bench can say "pipeline latency: 76s, chain depth: 4" — the operator sees how long it took the pipeline to produce this case.

### 3.5 Graceful Shutdown

All serve modes handle SIGINT and SIGTERM. The main loop checks `self._running` on each iteration. In-progress work completes before exit. State is saved before exit. No partial records in the store.

### 3.6 Backpressure

A component that falls behind (polls slower than upstream produces) will see its watermark lag. Each component exposes a `lag_seconds` metric:

```python
lag_seconds = (now - self._state.last_processed_timestamp).total_seconds()
```

If lag exceeds a configurable threshold (default: 300 seconds), the component writes a `backpressure` assessment indicating it cannot keep up. The Bench shows this as a Situation Board warning. Operators can scale the component horizontally (running multiple instances with a leader election mechanism — future work) or accept the lag.

No blocking of upstream: the store accumulates. This is an intentional design choice. It degrades gracefully under load rather than dropping data.

### 3.7 Retention

The store is append-only but not infinite. Retention policy:

| Record type | Default retention | Notes |
|-------------|-------------------|-------|
| assessment (slo_state, drift) | 30 days | High volume, lower value |
| heartbeat | 7 days | Very high volume, diagnostic only |
| verdict (evaluation, correlation) | 1 year | Moderate volume, high value |
| verdict (action_request, approval, capability, denial, execution) | 3 years | Compliance-relevant |
| verdict (incident, retrospective) | 3 years | Compliance-relevant |
| case | 30 days after resolution | Ephemeral; underlying verdicts retained |

A daily maintenance job (part of observe serve or a dedicated `nthlayer-maintenance` command) prunes records per the retention policy. Archived records are written to cold storage (S3, GCS, or equivalent) if configured.

---

## 4. Component: nthlayer-observe serve

### 4.1 What It Does

Polls Prometheus on a configurable schedule. For each service in the specs directory, collects SLO metrics and writes `slo_state` assessments. Optionally runs drift analysis. Writes a heartbeat each cycle.

### 4.2 CLI

```bash
nthlayer-observe serve \
  --specs-dir ./specs/ \
  --prometheus-url http://localhost:9090 \
  --store ./nthlayer.db \
  --interval 30 \
  --include-drift \
  --drift-interval 300
```

### 4.3 Serve Loop

Substantially unchanged from v1. Additional responsibilities:

1. Heartbeat emission on each cycle.
2. Pipeline latency stamp on assessments (assessments are the pipeline entry point so latency starts at 0; downstream components increment).
3. State persistence.

### 4.4 What It Writes

- `slo_state` assessments per service per SLO per cycle
- `drift` assessments (less frequently)
- `heartbeat` records (every cycle)
- `backpressure` assessments (when lagging)

### 4.5 What Triggers Downstream

Nothing explicitly. Measure polls the assessment store.

---

## 5. Component: nthlayer-measure serve

### 5.1 What It Does

Polls the assessment store for new `slo_state` assessments indicating a breach. For each breach, checks for active incidents (suppress if duplicate), checks semantic deduplication, then runs evaluation. Writes evaluation verdicts.

### 5.2 Changes from v1

1. Active-incident check before emitting.
2. Semantic deduplication.
3. Hysteresis state persists across restarts.
4. Heartbeat.

### 5.3 Serve Loop

```python
class MeasureServer(ComponentServer):
    component_name = "measure"

    async def _poll_cycle(self):
        new_assessments = self.store.query(AssessmentFilter(
            assessment_type="slo_state",
            from_time=self._state.last_processed_timestamp,
        ))

        if not new_assessments:
            return

        for assessment in sorted(new_assessments, key=lambda a: a.timestamp):
            # Only breach-status assessments matter
            if assessment.data.get("status") not in ("EXHAUSTED", "CRITICAL", "WARNING"):
                self._state.last_processed_timestamp = assessment.timestamp
                continue

            service = assessment.service
            slo_name = assessment.data.get("slo_name")
            breach_class = assessment.data.get("breach_class", slo_name)
            semantic_key = f"{service}:{slo_name}:{breach_class}"

            # Active incident suppression
            if self._has_active_incident(service, slo_name):
                self._write_suppression(assessment, reason="active-incident")
                self._state.last_processed_timestamp = assessment.timestamp
                continue

            # Semantic deduplication
            if semantic_key in self._state.processed_semantic_keys:
                self._state.last_processed_timestamp = assessment.timestamp
                continue

            # Hysteresis
            self._state.hysteresis_counters[semantic_key] = \
                self._state.hysteresis_counters.get(semantic_key, 0) + 1
            if self._state.hysteresis_counters[semantic_key] < self.config.breach_cycles:
                self._state.last_processed_timestamp = assessment.timestamp
                continue

            # Evaluate
            spec = self._load_service_spec(service)
            if spec and spec.get("type") == "ai-gate":
                verdict = await self._evaluate_judgment_slo(assessment, spec)
            else:
                verdict = self._evaluate_traditional_slo(assessment, spec)

            verdict.pipeline_latency_ms = self._compute_latency(assessment)
            verdict.chain_depth = 1  # first verdict in chain
            self.store.put_verdict(verdict)

            # Mark semantic key processed
            self._state.processed_semantic_keys[semantic_key] = datetime.now(UTC)
            self._state.last_processed_timestamp = assessment.timestamp

            logger.info(
                "evaluation_complete",
                service=service,
                slo=slo_name,
                breach=True,
                pipeline_latency_ms=verdict.pipeline_latency_ms,
            )

        await self._state.save()

    def _has_active_incident(self, service: str, slo_name: str) -> bool:
        incidents = self.store.query_verdicts(VerdictFilter(
            verdict_type="incident",
            service=service,
            status="open",
        ))
        return any(
            slo_name in i.data.get("affected_slos", [])
            for i in incidents
        )

    def _write_suppression(self, assessment, reason: str):
        self.store.put_audit(SuppressionAudit(
            assessment_hash=assessment.hash,
            component="measure",
            reason=reason,
            timestamp=datetime.now(UTC),
        ))
```

### 5.4 Hysteresis Persistence

Hysteresis counters live in `ComponentState.hysteresis_counters`, persisted per cycle. A restart mid-breach resumes with the counter intact. The counter is cleared when:

- The breach recovers (recovery_cycles consecutive healthy assessments)
- The semantic_key has been emitted (moves to processed_semantic_keys)
- A related incident opens (suppression takes over)

### 5.5 What It Writes

- `evaluation` verdicts with `breach: true` and `input_hashes` referencing the assessment
- `verdict_suppressed` audit records when duplicates are suppressed
- `heartbeat` records

---

## 6. Component: nthlayer-correlate serve

### 6.1 What It Does

Polls for evaluation verdicts with breach=true. Applies active-incident suppression. Gathers signals, runs correlation, writes correlation verdicts with root cause analysis.

### 6.2 Changes from v1

1. Active-incident check.
2. Semantic deduplication.
3. Pipeline latency propagation.
4. Heartbeat.

### 6.3 Serve Loop

Structure matches v1 with suppression and semantic deduplication added per §5.3. Key difference: correlate references its triggering evaluation verdict in `input_hashes` and propagates pipeline latency:

```python
verdict = create_verdict(
    verdict_type="correlation",
    service=breach_verdict.service,
    agent="correlate",
    input_hashes=[breach_verdict.hash],
    pipeline_latency_ms=breach_verdict.pipeline_latency_ms +
        (int((datetime.now(UTC) - breach_verdict.timestamp).total_seconds() * 1000)),
    chain_depth=breach_verdict.chain_depth + 1,
    data={
        "trigger_verdict": breach_verdict.hash,
        "root_causes": reasoning.root_causes,
        "blast_radius": reasoning.blast_radius,
        "confidence": reasoning.confidence,
        # ...
    },
)
```

### 6.4 What It Writes

- `correlation` verdicts
- `verdict_suppressed` audit records
- `heartbeat` records

---

## 7. Component: nthlayer-respond serve

### 7.1 What It Does

Polls for correlation verdicts. Runs the agent pipeline: triage → investigation → communication → remediation. The remediation agent now emits `action_request` verdicts instead of directly invoking remediation. Creates/manages incidents. Retains HTTP approval surface for Slack.

### 7.2 Changes from v1

1. Remediation agent emits `action_request` verdicts rather than executing remediation directly.
2. HTTP approval server now writes `approval` verdicts on behalf of Slack-based approvers.
3. Approval workflow delegates to `nthlayer-authorise` rather than being part of respond.
4. Heartbeat.

### 7.3 Remediation as action_request

In v1, respond's remediation agent directly invoked actions for pre-approved "safe actions" and escalated to humans for others. In v2, all remediation flows through the authorisation layer:

```python
# v1 (deprecated)
if action in safe_actions:
    execute(action, params)
else:
    escalate_to_human(action, params)

# v2
verdict = create_verdict(
    verdict_type="action_request",
    service=target_service,
    principal={
        "type": "agent",
        "id": f"nthlayer-respond/remediation@{agent_hash}",
    },
    data={
        "action_id": proposed_action.id,
        "parameters": proposed_params,
        "reasoning": reasoning,
        "input_hashes": [correlation_verdict.hash],
    },
)
self.store.put_verdict(verdict)
# Done. Authorise will handle the rest.
```

Respond no longer decides whether to execute. It proposes, via a verdict. Authorise decides.

### 7.4 HTTP Approval Server

The existing Slack approval server is retained but now writes `approval` verdicts rather than triggering execution directly:

```python
@app.post("/approve/{action_request_hash}")
async def approve(action_request_hash: str, request: Request):
    operator = await verify_slack_principal(request)
    verdict = create_verdict(
        verdict_type="approval",
        principal={"type": "human", "id": operator.id, "mfa": operator.mfa},
        data={
            "action_request_hash": action_request_hash,
            "decision": "approve",
            "reasoning": request.json().get("reasoning"),
        },
    )
    store.put_verdict(verdict)
    return {"status": "approval-recorded"}
```

The Bench and the Slack surface write the same verdict type into the same store. Neither is canonical; they are peer surfaces.

### 7.5 What It Writes

- Incident verdicts (triage, investigation, communication, resolution)
- `action_request` verdicts (from remediation agent)
- `approval` verdicts (from Slack approval handler)
- `heartbeat` records

---

## 8. Component: nthlayer-authorise serve (NEW)

### 8.1 What It Does

Polls the verdict store for new `action_request` and `approval` verdicts. Evaluates preconditions, blast radius, policies, and approval sufficiency. Issues capability tokens or writes denial verdicts. Creates cases when human approval is required.

This component is defined in detail in the OpenSRM RBAC Extension. This section covers serve-mode specifics.

### 8.2 CLI

```bash
nthlayer-authorise serve \
  --store ./nthlayer.db \
  --case-store ./nthlayer.db \
  --specs-dir ./specs/ \
  --policies-dir ./policies/ \
  --interval 5 \
  --signing-key-path /secrets/authorise-signing-key.pem \
  --capability-ttl 300
```

### 8.3 Serve Loop

```python
class AuthoriseServer(ComponentServer):
    component_name = "authorise"

    async def _poll_cycle(self):
        # Process new action_request verdicts
        requests = self.store.query_verdicts(VerdictFilter(
            verdict_type="action_request",
            from_time=self._state.last_processed_timestamp,
        ))

        for request in requests:
            await self._process_action_request(request)

        # Process new approval verdicts (may unblock pending authorisations)
        approvals = self.store.query_verdicts(VerdictFilter(
            verdict_type="approval",
            from_time=self._state.last_processed_approval_timestamp,
        ))

        for approval in approvals:
            await self._process_approval(approval)

        await self._state.save()

    async def _process_action_request(self, request):
        # 1. Load action definition
        spec = self._load_service_spec(request.service)
        action = self._find_action(spec, request.data["action_id"])
        if not action:
            self._write_denial(request, reason="undeclared-action")
            return

        # 2. Validate parameters
        if not self._validate_parameters(action, request.data["parameters"]):
            self._write_denial(request, reason="invalid-parameters")
            return

        # 3. Validate blast radius
        if not self._validate_blast_radius(action, request):
            self._write_denial(request, reason="blast-radius-violation")
            return

        # 4. Evaluate preconditions
        precondition_results = await self._evaluate_preconditions(action, request)
        if any(r.result == "fail" for r in precondition_results):
            self._write_denial(
                request,
                reason="precondition-failed",
                details={"preconditions": precondition_results},
            )
            return

        # 5. Evaluate policies
        policy_result = await self._evaluate_policies(action, request)
        if policy_result.effect == "deny":
            self._write_denial(request, reason="policy-denied",
                               details=policy_result.details)
            return

        # 6. Check approval level
        if action.approval_level == "autonomous":
            await self._issue_capability(action, request, [], precondition_results)
        elif action.approval_level == "prohibited":
            self._write_denial(request, reason="action-prohibited")
        else:
            # Create case, wait for approvals
            await self._create_pending_case(action, request)

    async def _process_approval(self, approval):
        request_hash = approval.data["action_request_hash"]
        request = self.store.get_verdict(request_hash)
        if not request:
            logger.warning("approval_for_unknown_request", hash=request_hash)
            return

        if approval.data["decision"] == "reject":
            self._write_denial(request, reason="human-rejected",
                              details={"reasoning": approval.data.get("reasoning")})
            await self._close_case(request_hash, "rejected")
            return

        if approval.data["decision"] == "request-modification":
            # Create new action_request with modified parameters
            modified_request = self._create_modified_request(request, approval)
            self.store.put_verdict(modified_request)
            await self._close_case(request_hash, "modified")
            # New request will be processed on next poll cycle
            return

        # decision == "approve"
        action = self._find_action(
            self._load_service_spec(request.service),
            request.data["action_id"],
        )
        approvals = self._collect_approvals_for(request_hash)

        if self._has_sufficient_approvals(action, approvals):
            precondition_results = await self._evaluate_preconditions(action, request)
            if any(r.result == "fail" for r in precondition_results):
                # Preconditions changed since request; deny
                self._write_denial(request, reason="precondition-failed-at-approval")
                await self._close_case(request_hash, "precondition-failed")
                return

            await self._issue_capability(action, request, approvals, precondition_results)
            await self._close_case(request_hash, "approved")
```

### 8.4 What It Writes

- `capability` verdicts (authorisations)
- `denial` verdicts (rejections at any stage)
- `heartbeat` records
- Case creation and transition records (to the case store)

### 8.5 Capability Signing

The signing key is held exclusively by this component. Key rotation is out of scope for this spec but the capability verdict records the key_id used so multiple active keys can be supported (e.g., during rotation).

---

## 9. Component: nthlayer-executor serve (NEW)

### 9.1 What It Does

Polls for capability verdicts. Verifies signature, consumes the one-shot token, invokes the execution binding, runs verification, writes execution verdicts. Triggers rollback if verification fails and reversibility permits.

### 9.2 CLI

```bash
nthlayer-executor serve \
  --store ./nthlayer.db \
  --specs-dir ./specs/ \
  --bindings-config ./executor-bindings.yaml \
  --interval 5 \
  --signing-public-key-path /secrets/authorise-public-key.pem
```

### 9.3 Bindings Configuration

```yaml
# executor-bindings.yaml — held by executor, not in OpenSRM manifests
bindings:
  deploy-service:
    type: webhook
    url: https://deploy.internal/api/v1/
    auth:
      type: bearer
      token_env: DEPLOY_SERVICE_TOKEN
    timeout: 60s

  prod-cluster:
    type: kubernetes
    kubeconfig: /secrets/kubeconfigs/prod-cluster
    context: prod-eu-west-1

  agent-config-service:
    type: webhook
    url: https://agents.internal/api/v1/config
    auth:
      type: bearer
      token_env: AGENT_CONFIG_TOKEN
    timeout: 30s
```

The binding name in an OpenSRM manifest references an entry here. Credentials are held by the executor, never by the manifest or any other component.

### 9.4 Serve Loop

```python
class ExecutorServer(ComponentServer):
    component_name = "executor"

    async def _poll_cycle(self):
        capabilities = self.store.query_verdicts(VerdictFilter(
            verdict_type="capability",
            from_time=self._state.last_processed_timestamp,
        ))

        for capability in capabilities:
            # Check for revocation
            if self._is_revoked(capability):
                await self._record_unused_capability(capability, reason="revoked")
                continue

            # Check if already consumed
            if self._is_consumed(capability):
                logger.error("capability_replay_attempt", hash=capability.hash)
                self._write_execution(capability, outcome="replay-rejected")
                continue

            # Check expiry
            if self._is_expired(capability):
                await self._record_unused_capability(capability, reason="expired")
                continue

            # Verify signature
            if not self._verify_signature(capability):
                logger.error("capability_signature_invalid", hash=capability.hash)
                self._write_execution(capability, outcome="signature-invalid")
                continue

            # Mark consumed (atomic)
            if not self._mark_consumed(capability):
                # Lost race with another executor instance
                continue

            # Re-validate blast radius at execution time
            if not self._revalidate_blast_radius(capability):
                self._write_execution(capability, outcome="blast-radius-violation-at-execution")
                continue

            # Execute
            outcome = await self._execute(capability)

            # Verify
            if capability.data.get("verification"):
                verification_result = await self._verify_outcome(capability, outcome)
                if verification_result.status == "failed":
                    if capability.data.get("reversibility") == "reversible-auto":
                        await self._trigger_rollback(capability)
                    outcome.verification_failed = True
                    outcome.verification_result = verification_result

            self._write_execution(capability, outcome)

            logger.info(
                "execution_complete",
                capability_id=capability.data["capability_id"],
                action_id=capability.data["action_id"],
                outcome=outcome.status,
            )
```

### 9.5 What It Writes

- `execution` verdicts
- `heartbeat` records
- `rollback_triggered` audit records when auto-rollback is invoked

---

## 10. Component: nthlayer-learn serve

### 10.1 What It Does

Polls for resolved incidents and execution verdicts. Reconstructs timelines from verdict chains, measures accuracy, produces retrospective verdicts. Updates correlate and measure calibration metrics.

### 10.2 Changes from v1

1. Consumes execution verdicts (new type) as part of retrospective analysis.
2. Measures execution outcome agreement (did the action work as expected?).
3. Writes retrospective verdicts with richer structure including authorisation chain.

### 10.3 Serve Loop

Structure matches v1 with additions:

- Walk lineage includes action_request → capability → execution chain
- Retrospective data includes: was the action approved? Did it execute? Did verification pass? Did it need rollback?
- Pipeline latency across the whole chain is computed

### 10.4 What It Writes

- `retrospective` verdicts with expanded structure
- Updates to measure/correlate calibration (via `calibration_update` verdicts)
- `heartbeat` records

---

## 11. Configuration

### 11.1 Shared Config

```yaml
# nthlayer.yaml
store:
  path: ./nthlayer.db
  retention:
    assessment_days: 30
    heartbeat_days: 7
    evaluation_verdict_days: 365
    authorisation_verdict_days: 1095
    case_days_after_resolution: 30

prometheus:
  url: http://localhost:9090

specs:
  dir: ./specs/

policies:
  dir: ./policies/

model:
  default: anthropic/claude-sonnet-4-20250514

slack:
  bot_token: "${SLACK_BOT_TOKEN}"
  signing_secret: "${SLACK_SIGNING_SECRET}"

# Per-component overrides
observe:
  interval: 30
  include_drift: true
  drift_interval: 300

measure:
  interval: 15
  hysteresis:
    breach_cycles: 3
    recovery_cycles: 5

correlate:
  interval: 10
  reasoning_enabled: true
  trace_backend: tempo
  tempo_endpoint: http://tempo:3200

respond:
  host: 0.0.0.0
  port: 8090
  interval: 10
  approval_timeout: 900

authorise:
  interval: 5
  signing_key_path: /secrets/authorise-signing-key.pem
  capability_ttl: 300

executor:
  interval: 5
  signing_public_key_path: /secrets/authorise-public-key.pem
  bindings_config: ./executor-bindings.yaml

learn:
  interval: 60
```

### 11.2 Environment Variables

Any config field is overridable via env var following the pattern `NTHLAYER_<SECTION>_<FIELD>`:

```bash
NTHLAYER_STORE_PATH=./nthlayer.db
NTHLAYER_MODEL=anthropic/claude-sonnet-4-20250514
NTHLAYER_AUTHORISE_INTERVAL=5
```

---

## 12. Deployment

### 12.1 Development (Single Machine)

```bash
# Terminal 1: observe
nthlayer-observe serve

# Terminal 2: measure
nthlayer-measure serve

# Terminal 3: correlate
nthlayer-correlate serve

# Terminal 4: respond
nthlayer-respond serve

# Terminal 5: authorise  (NEW)
nthlayer-authorise serve

# Terminal 6: executor   (NEW)
nthlayer-executor serve

# Terminal 7: learn
nthlayer-learn serve

# Terminal 8: bench (operator interface)
nthlayer bench
```

### 12.2 Docker Compose

Docker compose configuration extends the v1 setup with the two new components. Executor is the only component needing credentials for target systems — keep its mount list and env vars minimal and audited.

```yaml
services:
  # existing: observe, measure, correlate, respond, learn

  authorise:
    image: nthlayer-authorise
    command: serve
    volumes:
      - store:/data
      - ./specs:/specs:ro
      - ./policies:/policies:ro
      - ./secrets/authorise-signing-key.pem:/secrets/signing-key.pem:ro
    environment:
      NTHLAYER_STORE_PATH: /data/nthlayer.db

  executor:
    image: nthlayer-executor
    command: serve
    volumes:
      - store:/data
      - ./specs:/specs:ro
      - ./executor-bindings.yaml:/bindings.yaml:ro
      - ./secrets/authorise-public-key.pem:/secrets/public-key.pem:ro
      - ./secrets/kubeconfigs:/secrets/kubeconfigs:ro
    environment:
      NTHLAYER_STORE_PATH: /data/nthlayer.db
      DEPLOY_SERVICE_TOKEN: "${DEPLOY_SERVICE_TOKEN}"
      AGENT_CONFIG_TOKEN: "${AGENT_CONFIG_TOKEN}"

volumes:
  store:
```

---

## 13. Observability of the Pipeline Itself

The pipeline is self-observed via heartbeats, lag metrics, and suppression records. The Bench's Situation Board surfaces pipeline health:

```
PIPELINE — all components alive

  observe      last heartbeat 2s ago    lag 0s
  measure      last heartbeat 5s ago    lag 12s
  correlate    last heartbeat 3s ago    lag 4s
  respond      last heartbeat 4s ago    lag 1s
  authorise    last heartbeat 1s ago    lag 0s
  executor     last heartbeat 2s ago    lag 0s
  learn        last heartbeat 14s ago   lag 2s
```

When a component's heartbeat is older than a threshold (default: 60s), the Bench surfaces the warning prominently. Operators can see pipeline degradation immediately without external monitoring.

---

## 14. Verification

### 14.1 Per-Component

Each serve mode is testable in isolation with in-memory store fixtures. Tests verify: heartbeat emission, state persistence across restart, active-incident suppression, semantic deduplication, correct verdict/assessment schemas, pipeline latency propagation.

### 14.2 End-to-End

The integration test:

1. Start all seven serve processes.
2. Start a fake service exporting metrics to Prometheus.
3. Degrade the fake service.
4. Watch the store: slo_state → evaluation → correlation → incident → action_request → (case created) → approval (auto or test operator) → capability → execution → retrospective.
5. Verify the verdict chain is complete and hash-linked.
6. Verify pipeline_latency is populated at each step.
7. Verify end-to-end latency is within expected bounds (target: < 90 seconds from breach detection to execution for autonomous actions).
8. Verify Slack notifications were sent (or mock verified).
9. Verify the retrospective correctly identifies the root cause and action outcome.
10. Verify an incident-active-suppression test: inject a second breach of the same service/SLO; verify it's suppressed.
11. Verify capability replay is rejected.
12. Verify execution with verification failure triggers rollback (for reversible-auto actions).

This is the demo: "Point NthLayer at your Prometheus endpoint and your specs directory. Watch it observe, decide, authorise, execute, and learn — end to end, with full audit chain."

---

## 15. Implementation Priority

| Component | Effort | Notes |
|-----------|--------|-------|
| observe serve | 2-3 days | Largely from v1 |
| measure serve with incident suppression | 3-4 days | v1 logic + suppression + persistent state |
| correlate serve with incident suppression | 3-4 days | v1 logic + suppression + persistent state |
| respond serve (refactored) | 3-5 days | Remediation as action_request; approval server rewrite |
| authorise serve | 5-7 days | New component; signing key; policy evaluation |
| executor serve | 5-7 days | New component; bindings; verification; rollback |
| learn serve | 3-4 days | v1 logic + execution outcome integration |
| Case store | 2-3 days | Schema; leasing; state machine |
| Shared config loader + heartbeat | 2 days | Cross-cutting |
| Integration test | 3-5 days | Full pipeline including authorise/executor |

Total: ~31-44 days for the full v2 pipeline. This is substantially larger than v1 (14-19 days) because authorise and executor are new and non-trivial. The v1 pipeline without authorise/executor can ship first as an interim milestone that enables the Bench to work against a less-safe but functional ecosystem.

---

## Appendix A: Interim Milestone Strategy

Given the scope difference between v1 and v2, an interim milestone is worth considering:

**Milestone 1 (v1.5):** v1 pipeline (observe through respond + learn) with the remediation agent's "safe actions" implemented as a simplified capability concept — no signing key, no separate executor, no policies, but the action concept and the Bench approval flow work end-to-end. This ships the Bench and gets operators using the decision interface.

**Milestone 2 (v2):** Add authorise and executor as separate components, migrate the simplified capability model to signed tokens, add policy evaluation. Ship the full authorisation chain.

This lets the Bench and Textual UI work ship sooner without blocking on the more ambitious authorisation work. Organisations that want the full authorisation model wait for v2; those that are comfortable with respond's existing safe action model can use v1.5.

---

## Appendix B: Revision History

| Version | Date | Changes |
|---------|------|---------|
| 1.0 | 2026-04-12 | Initial pull-based pipeline |
| 2.0-draft | 2026-04-18 | Active-incident suppression; semantic dedup; persistent hysteresis; pipeline latency; heartbeat; authorise and executor components; case store integration; retention policy; Bench spec cross-reference (replaces duplicate Textual section) |
