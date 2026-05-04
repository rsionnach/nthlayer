# P3-E.1: Respond Worker Module — Coordinator and Trigger Ingestion

**Date:** 2026-04-25
**Epic:** P3-E (Respond Module)
**Bead:** opensrm-st4s.1
**Dependencies:** P3-A.1 (module runner), P3-D.1 (correlation_snapshot taxonomy + assessment kind)
**Spec:** NTHLAYER-SERVE-MODE-v2.1 §5.5

## Summary

Adapt the existing nthlayer-respond coordinator to run as a worker module within nthlayer-workers. Triggers are polled from the core API: `correlation_snapshot` assessments are the canonical primary trigger, with `quality_breach` verdicts as a fallback when correlate is degraded. Each pipeline step's verdict is submitted to core via `CoreAPIClient.submit_verdict()` — the local `SQLiteVerdictStore` is removed from respond entirely. Incident contexts are persisted to core via the `component_state` API for crash recovery; `SQLiteContextStore` is removed from the worker path.

P3-E.1 is the structural migration: I/O endpoints change from local SQLite to the core HTTP API, and trigger ingestion changes from CLI-driven one-shot to poll-driven worker module. Agent internals (LLM calls, prompt construction) are unchanged here — P3-E.2 swaps to Instructor, P3-E.3 wires safe-action execution, P3-E.4 ports notification backends, P3-E.5 ports on-call resolution.

## Design Principles

1. **Situation-shaped triggers, not signal-shaped.** The respond pipeline's natural unit is the *situation* (triage → investigate → communicate → remediate). Situations correspond to `correlation_snapshot` assessments produced by correlate. Polling 1:1 per upstream signal (every `quality_breach` plus every `correlation_snapshot`) produces duplicate incidents for the same logical event — visible operational quality issue. Trigger from the situation; fall back to the signal only when the situation-producer is unavailable.

2. **Capture-at-write-time.** When a worker has a fresh decision-bearing object (`Verdict`, `Assessment`) in hand, prefer storing decision-relevant fields onto local in-process state (here: `IncidentContext`) over re-fetching from core later. Applies in P3-E.1 to the escalation gate (track flag on context, don't re-query verdicts). Reusable pattern; apply where it fits.

3. **Worker-mode invariant: validate state on entry.** Operations that were safe under operator-driven CLI invocation (where the operator implicitly knew the incident's state) become unsafe under polling-driven worker invocation. Each worker-mode entry point must check the incident's state on entry and return no-op (or appropriate alternate behaviour) if the state doesn't match what the operation assumes.

   *Example:* `_run_pipeline` historically assumed it was being invoked because the operator wanted to advance an incident. Under worker mode it is called on every active incident every cycle, regardless of state. Without a state check at entry, an `AWAITING_APPROVAL` incident would have `_next_step()` return 3 (because `last_completed_step_index = 2`) and step 3 would proceed, bypassing the approval gate. Fix: `if context.state == AWAITING_APPROVAL: return context` at entry.

   This principle generalises beyond the AWAITING_APPROVAL case — future P3-E.2/E.3/E.4/E.5 sub-tasks adding new worker-mode entry points (e.g. an approval-verdict polling loop in P3-E.3) must apply the same check.

4. **Align internal types to canonical v1.5 shapes, don't write adapters.** Core API verdict/assessment shapes are canonical. Respond's `Verdict` construction already uses `nthlayer_common.verdicts.create()` so the data shape is aligned; only the *destination* (local store → core API) changes.

## What's New vs. What Exists

| Concept | Existing code | P3-E.1 |
|---------|--------------|--------|
| **Module shape** | CLI command (`nthlayer-respond respond`) | `RespondModule(WorkerModule)` polling on a cycle |
| **Trigger source** | Single trigger verdict ID passed via `--trigger-verdict` | Poll core: `get_assessments(kind=correlation_snapshot)` (primary) + `get_verdicts(verdict_type=quality_breach)` (fallback) |
| **Trigger semantics** | One-shot per CLI invocation | Cursor-based, dedup against snapshot lineage |
| **Verdict persistence** | `SQLiteVerdictStore.put()` (local) | `CoreAPIClient.submit_verdict()` (HTTP) |
| **Incident context persistence** | `SQLiteContextStore` (local SQLite) | `component_state("respond")` (HTTP, single blob) |
| **Approval flow** | `nthlayer-respond approve INC-...` CLI hits local store | AWAITING_APPROVAL is a v1.5 P3-E.1 dead-end pending P3-E.3 (approval-verdict-poll-and-resume) |
| **Escalation gate** | Re-fetches each verdict in chain via `verdict_store.get()` | Tracks `escalation_pending: bool` field on `IncidentContext`, set at write-time |
| **State on AWAITING_APPROVAL** | `Coordinator.run()` returns; `approve()` is a separate entry point | Same — but `_run_pipeline` adds an early-return guard so the worker can blindly call `run()` on every active incident |
| **Per-step timeout** | None (per-agent timeouts only) | Wraps each step with `asyncio.wait_for(step, step_timeout_seconds)` |

---

## Architecture

### RespondModule (WorkerModule)

**File:** `nthlayer-workers/src/nthlayer_workers/respond/worker.py`

Implements the `WorkerModule` protocol from `runner.py`.

```python
@dataclass
class RespondModule:
    """Respond worker module — drives incidents from triggers polled from core API.

    Reads correlation_snapshot assessments (primary) and quality_breach verdicts
    (fallback) from core, opens incident contexts, runs the agent pipeline,
    submits verdicts back to core, persists incident state to component_state.
    """
    client: CoreAPIClient
    config: RespondConfig
    deployment_id: str | None = None

    # in-memory mirrors of component_state, restored on restore_state()
    _cursors: Cursors = field(default_factory=Cursors)
    _incidents: dict[str, IncidentContext] = field(default_factory=dict)

    @property
    def name(self) -> str:
        return "respond"

    async def restore_state(self, state: dict | None) -> None:
        """Reload cursors and active incidents from component_state."""
        if state is None:
            return
        self._cursors = Cursors.from_dict(state.get("cursors", {}))
        for incident_id, raw in state.get("incidents", {}).items():
            self._incidents[incident_id] = IncidentContext_from_dict(raw)

    async def process_cycle(self) -> None:
        """One cycle: detect new triggers → drive active incidents → save state."""
        await self._ingest_triggers()
        await self._drive_active_incidents()

    async def get_state(self) -> dict:
        """Return cursors + active incidents (with terminal-state pruning)."""
        return {
            "cursors": self._cursors.to_dict(),
            "incidents": {
                inc_id: IncidentContext_to_dict(ctx)
                for inc_id, ctx in self._incidents.items()
                if not _is_terminal_and_aged(ctx, self.config.terminal_retention_seconds)
            },
        }
```

`Cursors` is a dataclass holding `snapshot_after: str | None` and `breach_after: str | None` (ISO 8601). `IncidentContext_to_dict` / `IncidentContext_from_dict` are existing functions in `nthlayer_workers.respond.context_store` — they are made publicly importable (renamed `_to_dict`/`_from_dict` to `IncidentContext_to_dict`/`IncidentContext_from_dict` and moved to module-level export, with `SQLiteContextStore` continuing to use them for legacy CLI). The serialisation already includes `verdict_chain` (it is a dataclass field on `IncidentContext`, picked up by `dataclasses.asdict`); this preservation across roundtrip is a tested invariant — see test `test_state_roundtrip_preserves_all_fields` which explicitly asserts `verdict_chain` survives. Without this, `_emit_verdict()` after restore would read `context.verdict_chain[-1]` against an empty list and break lineage continuity.

### Trigger ingestion: primary path (correlation_snapshot)

```python
async def _ingest_triggers(self) -> None:
    # --- Primary: correlation_snapshot assessments ---
    snap_result = await self.client.get_assessments(
        kind="correlation_snapshot",
        # core API filters by kind only; we filter created_after client-side
        # against self._cursors.snapshot_after. Documented v1.5 limitation
        # mirroring P3-D.1's same constraint.
    )
    if snap_result.ok:
        snapshots = _filter_after(snap_result.data, self._cursors.snapshot_after)
        for snap in snapshots:
            if snap["id"] in self._incidents_triggered_from():
                continue  # already opened
            await self._open_incident_from_snapshot(snap)
            self._cursors.snapshot_after = snap["created_at"]

    # --- Fallback: quality_breach verdicts older than threshold w/o snapshot ---
    cutoff = (datetime.now(timezone.utc)
              - timedelta(seconds=self.config.fallback_threshold_seconds)).isoformat()
    breach_result = await self.client.get_verdicts(
        verdict_type="quality_breach",
        created_before=cutoff,
        created_after=self._cursors.breach_after,
    )
    if breach_result.ok:
        for breach in breach_result.data:
            if await self._has_associated_snapshot(breach["id"]):
                self._cursors.breach_after = breach["created_at"]
                continue  # already represented by a snapshot incident
            if breach["id"] in self._incidents_triggered_from():
                self._cursors.breach_after = breach["created_at"]
                continue
            opened_id = await self._open_incident_from_breach(breach)
            self._cursors.breach_after = breach["created_at"]
            logger.info(
                "fallback_trigger_used",
                incident_id=opened_id,
                breach_id=breach["id"],
                fallback_threshold_seconds=self.config.fallback_threshold_seconds,
            )
```

`_open_incident_from_breach` returns the new incident's id so the structured-log entry can reference it. Same for `_open_incident_from_snapshot`.

**Implementation note (post-R5 review):** the spec described a `_has_associated_snapshot(breach_id)` method that would issue one HTTP fetch per breach to check for an associated snapshot. The shipped implementation instead caches the snapshot page returned by `_ingest_snapshots` and uses a single set-membership lookup via `worker_helpers.breach_ids_with_snapshots(snapshot_cache)`. Behaviourally equivalent for v1.5 demo scale but avoids the per-breach API fan-out. v1.5 limitation persists: core's `/assessments` API does not currently filter by `parent_ids`, so any snapshot not present on the cached page (pagination, snapshots from prior cycles aged out of the response) will not be matched and the fallback path will over-trigger an incident. Tracked v2 follow-up: server-side `parent_ids` filter (see "Out of P3-E.1 scope" table).

`_incidents_triggered_from()` returns the union of `trigger_verdict_ids` across `self._incidents` — used to skip already-processed triggers if cursor advancement hiccups.

### `_open_incident_from_snapshot` vs `_open_incident_from_breach`

These produce `IncidentContext` objects with materially different richness:

**`_open_incident_from_snapshot(snapshot_assessment)`** — primary path, rich context:

```python
async def _open_incident_from_snapshot(self, snap: dict) -> None:
    domain = snap["data"]["domain"]
    service = domain["service"]
    environment = domain["environment"]

    # Walk lineage one hop to pick up the originating quality_breach(es)
    breach_ids = [pid for pid in snap.get("data", {}).get("parent_ids", [])]

    incident_id = _make_incident_id(service)
    now = datetime.now(timezone.utc).isoformat()

    topology = await self._fetch_topology(snap["data"].get("affected_services", [service]))

    self._incidents[incident_id] = IncidentContext(
        id=incident_id,
        state=IncidentState.TRIGGERED,
        created_at=now,
        updated_at=now,
        trigger_source="nthlayer-correlate",
        trigger_verdict_ids=[snap["id"], *breach_ids],
        topology=topology,
        metadata={
            "blast_radius": snap["data"].get("blast_radius", []),
            "correlation_summary": snap["data"].get("nl_summary"),
            "peak_severity": snap["data"].get("peak_severity"),
            "event_count": snap["data"].get("event_count"),
            "affected_services": snap["data"].get("affected_services", []),
            "service_context": await self._build_service_context(service, breach_ids),
        },
    )
```

**`_open_incident_from_breach(breach_verdict)`** — fallback path, thinner context:

```python
async def _open_incident_from_breach(self, breach: dict) -> None:
    service = breach["service"]
    incident_id = _make_incident_id(service)
    now = datetime.now(timezone.utc).isoformat()

    topology = await self._fetch_topology([service])

    self._incidents[incident_id] = IncidentContext(
        id=incident_id,
        state=IncidentState.TRIGGERED,
        created_at=now,
        updated_at=now,
        trigger_source="nthlayer-measure-fallback",
        trigger_verdict_ids=[breach["id"]],
        topology=topology,
        metadata={
            "fallback_reason": "no_correlation_snapshot",  # static; threshold logged via structlog at trigger time
            "severity": breach.get("severity"),
            "service_context": await self._build_service_context(service, [breach["id"]]),
        },
    )
```

The fallback path is intentionally a degraded mode. The triage agent produces a thinner initial briefing because it has less context; that's appropriate, since the fallback only fires when correlate is degraded. We deliberately do *not* synthesise blast radius from manifest dependents in the fallback — respond's job isn't to recompute correlate's output.

### Lineage continuity across modules

Respond is not the root of the verdict chain. Two fields carry ancestry:

- `lineage.parent` — the previous verdict in *this incident's chain* within respond. `None` on the first respond verdict.
- `lineage.context` — list of upstream trigger verdict IDs (e.g. `correlation_snapshot` ID, originating `quality_breach` ID). Preserved across every verdict in the incident.
- `parent_ids` — v1.5 transitional field on the Verdict model. Carries multi-parent ancestry: the immediate predecessor for chained verdicts, the upstream trigger(s) for the first verdict.

Existing `_emit_verdict()` in `agents/base.py:113-114` already sets `lineage.context` and `lineage.parent` correctly. P3-E.1 adds `parent_ids` handling so cross-module ancestry is walkable via the canonical v1.5 field:

```python
# In _emit_verdict (worker mode), after constructing v
v.lineage.context = list(context.trigger_verdict_ids)
if context.verdict_chain:
    v.lineage.parent = context.verdict_chain[-1]
    v.parent_ids = [context.verdict_chain[-1]]
else:
    v.lineage.parent = None
    v.parent_ids = list(context.trigger_verdict_ids)  # cross-module bridge
```

The "one chain" property holds across modules because every verdict — measure's `quality_breach`, correlate's `correlation_snapshot`, respond's pipeline verdicts — terminates in core's verdict store. Walking back from any respond verdict via `parent_ids` reaches the first respond verdict, whose `parent_ids` references the upstream trigger; from there, the trigger's own `parent_ids`/`data.parent_ids` lead further upstream.

A future contributor reading respond's code should not infer that the chain begins at respond's first verdict; it begins upstream (or earlier) and respond extends it.

### Verdict submission via core API

`SQLiteVerdictStore` is removed from respond entirely. All verdict writes funnel through a new helper:

```python
# nthlayer-workers/src/nthlayer_workers/respond/verdict_submission.py

async def submit_verdict_to_core(
    client: CoreAPIClient,
    verdict: Verdict,
    *,
    deployment_id: str | None = None,
) -> None:
    """Wrap a Verdict dataclass in a CloudEvents envelope and submit to core."""
    envelope = wrap_verdict(
        to_dict(verdict),
        component="respond",
        deployment_id=deployment_id,
    )
    result = await client.submit_verdict(envelope["data"])
    if not result.ok:
        # Submission failure does not crash the cycle. Log and continue —
        # the verdict object remains constructed locally, lineage is intact
        # in IncidentContext.verdict_chain, and the next agent's verdict
        # will still chain correctly via parent. Operator visibility comes
        # from the errors_total Prometheus metric and structured log entry.
        logger.warning(
            "respond_verdict_submit_failed",
            verdict_id=verdict.id,
            status_code=result.status_code,
            error=result.error,
        )
        from nthlayer_common.metrics import errors_total
        errors_total.labels(component="respond", error_type="verdict_submit").inc()
```

The `_emit_verdict()` helper in `agents/base.py` is updated. It becomes `async` (its only caller, `agent.execute()`, is already async) and dispatches on configured backend:

```python
async def _emit_verdict(self, ...) -> Verdict:
    v = verdict_create(...)

    # Wire lineage (existing) + parent_ids (new in P3-E.1)
    v.lineage.context = list(context.trigger_verdict_ids)
    if context.verdict_chain:
        v.lineage.parent = context.verdict_chain[-1]
        v.parent_ids = [context.verdict_chain[-1]]
    else:
        v.lineage.parent = None
        v.parent_ids = list(context.trigger_verdict_ids)

    # Persist via configured backend (worker vs legacy CLI; exactly one is set)
    if self._client is not None:
        await submit_verdict_to_core(self._client, v, deployment_id=self._deployment_id)
    elif self._verdict_store is not None:
        self._verdict_store.put(v)
    else:
        raise RuntimeError("AgentBase: neither client nor verdict_store configured")

    context.verdict_chain.append(v.id)
    return v
```

Agent constructors gain `client: CoreAPIClient | None = None` and `deployment_id: str | None = None`; existing `verdict_store: Any | None = None` becomes optional. Worker mode passes `client` and `deployment_id`; legacy CLI passes `verdict_store`. Exactly one is set. The `RuntimeError` is a defensive check, not an expected runtime path — caught by tests in step 5 of the work sequence.

The capture-at-write-time escalation flag (next section) is set inside this helper, after the `verdict_chain.append`.

### Escalation gate via captured flag (capture-at-write-time)

The current `_check_escalation()` loops over `context.verdict_chain` and calls `verdict_store.get(id)` per verdict. In worker mode, that becomes one HTTP round-trip per verdict per step — wasteful and flaky.

Instead, when an agent writes a verdict with `action=escalate, confidence < threshold`, set a flag on the incident context immediately:

```python
# In _emit_verdict (agents/base.py)
if (
    v.judgment.action == "escalate"
    and v.judgment.confidence < context.metadata.get("escalation_threshold", 0.0)
):
    context.metadata["escalation_pending"] = True
```

```python
# In coordinator._check_escalation
def _check_escalation(self, context: IncidentContext) -> bool:
    return bool(context.metadata.get("escalation_pending", False))
```

`escalation_threshold` is captured into `context.metadata` once at incident open, from `config.escalation_threshold`. The gate check is now a dict lookup — no API calls, no race conditions.

### State storage: D-blob component_state

Single `component_state("respond")` document. All cursors, all active incidents, one JSON blob.

```python
{
    "cursors": {
        "snapshot_after": "2026-04-25T12:00:00Z",
        "breach_after": "2026-04-25T11:59:00Z",
    },
    "incidents": {
        "INC-FRAUD-DETECT-20260425-120000": {
            # full IncidentContext serialisation (existing _to_dict shape)
        },
        ...
    },
}
```

**Pruning on save:** `get_state()` filters out incidents whose state is in `TERMINAL_STATES` and whose `updated_at` is older than `workers.respond.terminal_retention_seconds` (default 86400 = 24h). Active incidents are never pruned. Terminal incidents persist for 24h so operators can inspect them.

**Contention:** Every step rewrites the whole blob. At v1.5 demo scale (typically <10 active incidents) this is fine. The runner already persists state once per cycle, not once per step, so a typical cycle has one PUT regardless of how many incident steps ran.

**D-cases deferred:** The Cases API is the right home for incidents long-term — it provides queryability, lease-based ownership, and bench integration. Bringing the Cases API into P3-E.1 expands scope into priority derivation, lease acquisition for human handlers, and bench integration design. Those are meaningful design decisions deserving dedicated scope. Follow-up bead: P3-E case-API integration (post-P3-E.5, parallel with bench Phase 4 work).

### Coordinator: AWAITING_APPROVAL early return + per-step timeout

Two changes to `nthlayer_workers/respond/coordinator.py`:

**1. Early-return guard on AWAITING_APPROVAL.**

```python
async def _run_pipeline(self, context: IncidentContext) -> IncidentContext:
    """Walk through pipeline steps, running agents and checking gates."""

    # P3-E.1: AWAITING_APPROVAL is a non-progressable wait state in worker
    # mode. The next progression happens when P3-E.3 detects an approval
    # verdict in core and resumes the pipeline. For P3-E.1, we return
    # immediately so process_cycle can move to the next active incident.
    if context.state == IncidentState.AWAITING_APPROVAL:
        return context

    start_step = self._next_step(context)
    ...
```

This makes `_run_pipeline` idempotent on AWAITING_APPROVAL incidents — the worker can blindly call `coordinator.run()` on every non-terminal incident in `_drive_active_incidents()` without special-casing the approval state.

**2. Per-step timeout.**

```python
# In _run_pipeline, around each step invocation
import asyncio
...
try:
    if len(step_roles) == 1:
        await asyncio.wait_for(
            self._run_serial_step(context, step_roles[0]),
            timeout=self._config.step_timeout_seconds,
        )
    else:
        await asyncio.wait_for(
            self._run_parallel_step(context, step_roles),
            timeout=self._config.step_timeout_seconds,
        )
except asyncio.TimeoutError:
    step_label = step_roles[0].value if len(step_roles) == 1 else "+".join(r.value for r in step_roles)
    context.state = IncidentState.FAILED
    context.error = f"step_timeout: {step_label} exceeded {self._config.step_timeout_seconds}s"
    return context  # exits _run_pipeline; worker persists context at end of cycle
```

`step_timeout_seconds` is added to `RespondConfig` with default 90. The `_NoopContextStore` adapter (see `_drive_active_incidents`) means the coordinator's existing `self._context_store.save(context)` calls become no-ops in worker mode — the worker is the sole persistence boundary, called once per cycle by the runner. No save call needed in the timeout branch.

**Naming choice (FAILED vs new ERRORED state):** we use the existing `IncidentState.FAILED` rather than introducing an `ERRORED` state. `FAILED` is the existing taxonomy for unrecoverable errors, and `error="step_timeout: ..."` carries the specific reason. Adding a new state would ripple through every consumer of `IncidentState`.

**Per-step timeout vs per-agent timeout:** the agent itself still has its own timeout (`config.triage_timeout` etc.). The per-step timeout is a coarser guard one level up that catches anything the agent's internal timeout misses (e.g. retry loops, asyncio scheduling lag). It also bounds parallel-step duration by the longest single agent rather than the sum.

**`context.error` format convention:** the existing codebase has only one `context.error` assignment (`coordinator.py:86`, `context.error = str(exc)` — raw exception message, no structured prefix). P3-E.1's `step_timeout: <step_name> exceeded <N>s` format establishes a new `<reason>: <details>` convention. Future error assignments should follow it (e.g. `verdict_submit_failed: ...`, `agent_init_failed: ...`) so operators can grep error reasons across incidents without parsing free-form exception text. The existing raw-exception case at `coordinator.py:86` is updated as part of step 3 of the work sequence to `context.error = f"unrecoverable: {exc}"` for consistency — small change, in scope. Any test asserting on the exact error string at line 86 must be updated to match.

### Latency property and future module split

**Documented limitation:** New trigger detection latency is bounded by the longest currently-running incident's pipeline duration. At v1.5 demo scale (typically <5 active incidents, pipelines completing in 10–30s), this is acceptable.

If higher scale or stricter trigger-detection latency is needed in operation, split into two modules following the pattern from observe (Collect/Drift/Topology) and correlate (Session/Topology/Contract):

- `RespondTriggerModule` — fast cycle (e.g. 10s), polls for triggers and creates incident contexts. Persists to component_state. Does not run the agent pipeline.
- `RespondPipelineModule` — slower cycle (e.g. 30s), reads incidents in non-terminal states from component_state, drives them through pipeline steps. Submits verdicts.

Both modules share the same component_state document but at different cadences. This is a v1.5-shaped follow-up if needed, not a v2-only concern.

### `_drive_active_incidents`

```python
async def _drive_active_incidents(self) -> None:
    coordinator = Coordinator(
        agents=self._agents,
        context_store=_NoopContextStore(self),  # see below
        config=self.config,
        client=self.client,  # for verdict submission
        deployment_id=self.deployment_id,
        # safe_action_registry, escalation_runner deferred to P3-E.3 / P3-E.5
    )
    for incident_id, context in list(self._incidents.items()):
        if context.state in TERMINAL_STATES:
            continue
        if context.state == IncidentState.AWAITING_APPROVAL:
            continue  # waits for P3-E.3 approval-verdict polling
        try:
            updated = await coordinator.run(context)
            self._incidents[incident_id] = updated
        except Exception:
            logger.exception("respond_incident_drive_failed", incident_id=incident_id)
            # Coordinator.run already catches inner exceptions and sets FAILED;
            # this catch is for unexpected escapes (e.g. coordinator construction).
```

`_NoopContextStore` is a thin adapter that satisfies the coordinator's `context_store` parameter without writing anywhere — the worker is the single owner of the in-memory `_incidents` dict, and persistence happens in `get_state()` once per cycle. The coordinator's `save(context)` calls become no-ops; the worker's per-cycle `component_state` PUT is the persistence boundary.

```python
# nthlayer-workers/src/nthlayer_workers/respond/worker.py

class _NoopContextStore:
    """Satisfies the coordinator's context_store interface without persisting.

    Worker mode owns persistence at the cycle boundary, not per-step. The
    coordinator's existing save(context) calls are still invoked (we don't
    refactor the coordinator's persistence touchpoints in P3-E.1); they
    just become no-ops here. Reads are NEVER expected in worker mode — the
    worker holds the live IncidentContext in self._incidents — so load() and
    list_active() raise loudly rather than returning silent-wrong-answer values
    like None or []. Loud failure on misuse beats invisible bugs.
    """
    def save(self, context: IncidentContext) -> None:
        pass

    def load(self, incident_id: str):
        raise NotImplementedError(
            "worker mode reads from RespondModule._incidents directly, not context_store"
        )

    def list_active(self) -> list[str]:
        raise NotImplementedError(
            "worker mode reads from RespondModule._incidents directly, not context_store"
        )

    def close(self) -> None:
        pass
```

The coordinator's `_check_escalation` reads from `context.metadata["escalation_pending"]` (set at write-time) so it never needs the verdict store to make the gate decision.

### Worker ↔ coordinator/agent isolation invariant

**Agents and the coordinator have no back-reference to the worker.** `self._incidents` is mutated only by `_drive_active_incidents` after `coordinator.run(context)` completes for each incident, and by `_ingest_triggers` before the drive phase. The coordinator and agents receive only the `IncidentContext` (and the `CoreAPIClient` for verdict submission) — they have no handle on the `RespondModule` instance. This makes the data-flow direction one-way (worker → coordinator → agent → core API) and prevents future contributors from accidentally introducing back-references that would make state mutations harder to reason about.

### What the cycle does, step by step

```text
process_cycle()
  │
  ├─ _ingest_triggers()
  │     ├─ Poll get_assessments(kind=correlation_snapshot)
  │     │   filter created_after self._cursors.snapshot_after
  │     │   for each: open incident from snapshot
  │     ├─ Poll get_verdicts(verdict_type=quality_breach,
  │     │                    created_before=now - fallback_threshold_seconds,
  │     │                    created_after=self._cursors.breach_after)
  │     │   for each: check _has_associated_snapshot; if false, open from breach
  │     └─ Update cursors
  │
  └─ _drive_active_incidents()
        ├─ For each non-terminal, non-AWAITING_APPROVAL incident:
        │     ├─ coordinator.run(context)  (idempotent on AWAITING_APPROVAL)
        │     ├─ Each step wrapped in asyncio.wait_for(step_timeout_seconds)
        │     └─ Verdicts submitted to core via submit_verdict_to_core helper
        └─ (state persisted to component_state by runner via get_state())
```

After `process_cycle` returns, the runner calls `get_state()` (which prunes terminal-aged incidents) and PUTs to `component_state("respond")`.

---

## Backwards compatibility: legacy CLI mode

The existing `nthlayer-respond` CLI commands (`replay`, `respond`, `serve`, `status`, `approve`, `reject`, `resume`) are used by the demo (`demo/demo.sh` Step 6) and by integration tests. P3-E.1 cannot break these.

**Approach:** keep `cli.py` largely unchanged. The legacy CLI continues to construct agents with a `SQLiteVerdictStore` and `SQLiteContextStore`, runs the coordinator in one-shot mode, and exits. The agent base class's `_emit_verdict()` is updated to dispatch on whether `self._client` is set (worker mode) or `self._verdict_store` is set (legacy CLI mode) — exactly one is set, never both. The two backends share the in-memory `Verdict` construction but diverge on persistence.

`SQLiteContextStore` and `SQLiteVerdictStore` remain in the codebase for the legacy CLI; they are simply never used by `RespondModule`. This is a temporary duplication, not a permanent shim — when bench replaces the legacy CLI in Phase 4, the legacy CLI mode and its stores are deleted.

The `nthlayer-respond approve INC-... ` and `reject` CLI continue to work in legacy mode against `SQLiteContextStore`. They do not work in worker mode — AWAITING_APPROVAL incidents in worker mode are P3-E.3 territory.

**Demo impact:** `demo/demo.sh` Step 6 invokes `nthlayer-respond respond --trigger-verdict ...` (legacy CLI mode). No change required. The worker-mode flow is exercised by the new e2e and integration tests, not the demo, until P3-E.3 lands the approval-verdict path.

---

## Configuration

Additions to `RespondConfig` (`nthlayer-workers/src/nthlayer_workers/respond/config.py`):

```python
@dataclass
class RespondConfig:
    ...  # existing fields preserved

    # P3-E.1 worker-mode additions
    cycle_interval_seconds: float = 30.0
    fallback_threshold_seconds: float = 60.0
    terminal_retention_seconds: float = 86400.0
    step_timeout_seconds: float = 90.0
```

YAML key path: `workers.respond.{cycle_interval_seconds, fallback_threshold_seconds, terminal_retention_seconds, step_timeout_seconds}` in `nthlayer.yaml`. Loaded via `nthlayer_common.config.Config.get(...)` in the workers CLI, threaded into `RespondConfig`.

---

## CLI registration in `nthlayer-workers serve`

In `nthlayer-workers/src/nthlayer_workers/cli.py`:

```python
from nthlayer_workers.respond.worker import RespondModule

# In serve command handler:
respond_config = RespondConfig.from_dict(config.get("workers.respond") or {})
respond = RespondModule(
    client=runner.client,
    config=respond_config,
    deployment_id=config.deployment_id,
)
runner.register(respond, interval_seconds=respond_config.cycle_interval_seconds)
```

CLI flag: `--respond-interval` (default 30) override.

---

## Test Strategy

### New test file: `tests/respond/test_respond_worker.py`

**Module protocol:**
- `test_respond_module_protocol` — `RespondModule` satisfies `WorkerModule` (name="respond", restore_state, process_cycle, get_state)
- `test_restore_state_none` — empty state, no incidents, default cursors
- `test_restore_state_roundtrip` — cursors + 2 incidents persisted and restored

**Trigger ingestion (primary):**
- `test_ingest_correlation_snapshot_opens_incident` — mock core returns one snapshot → incident opened with `trigger_source="nthlayer-correlate"`, `trigger_verdict_ids` includes snapshot id + parent breach ids
- `test_ingest_snapshot_metadata_populated` — verify `blast_radius`, `correlation_summary`, `peak_severity`, `event_count`, `affected_services` all in metadata
- `test_ingest_snapshot_cursor_advances` — cursor moves to latest snapshot's `created_at`
- `test_ingest_no_new_snapshots_noop` — empty page, no incidents, cursor unchanged

**Trigger ingestion (fallback):**
- `test_ingest_breach_with_snapshot_skipped` — mock returns breach + snapshot referencing it → no incident opened (snapshot path takes precedence elsewhere; fallback dedup correct)
- `test_ingest_orphan_breach_opens_fallback_incident` — breach older than fallback threshold, no snapshot referencing it → incident opened with `trigger_source="nthlayer-measure-fallback"`, `metadata.fallback_reason="no_correlation_snapshot"`
- `test_ingest_breach_below_threshold_not_yet_triggered` — breach within fallback threshold → not yet triggered (waits for snapshot or threshold expiry)
- `test_ingest_fallback_logs_threshold` — verify structlog message includes `fallback_threshold_seconds` field

**Trigger dedup:**
- `test_already_triggered_snapshot_skipped` — snapshot with id already in active incidents' `trigger_verdict_ids` → skipped on re-ingest (defence against cursor hiccups)
- `test_breach_already_triggered_skipped` — same for breaches in fallback path

**Pipeline drive:**
- `test_drive_progresses_triaged_incident` — mock agents, incident in TRIAGING → cycle drives to RESOLVED
- `test_drive_skips_terminal_incidents` — incidents in {RESOLVED, ESCALATED, FAILED} → no agent calls
- `test_drive_skips_awaiting_approval` — incident in AWAITING_APPROVAL → no agent calls (waits for P3-E.3)
- `test_drive_step_timeout_marks_failed` — mock agent that hangs > step_timeout_seconds → state=FAILED, error starts with `"step_timeout:"`, cycle continues to next incident
- `test_drive_one_incident_failure_does_not_block_others` — incident A raises → A marked FAILED, incident B still drives normally

**Verdict submission:**
- `test_verdicts_submitted_via_core_api` — mock CoreAPIClient.submit_verdict, run incident → submit called for triage/investigation/communication/remediation, each wrapped in CloudEvents envelope with `component="respond"`
- `test_verdict_submit_failure_does_not_crash_cycle` — mock submit returns 503 → cycle continues, errors_total counter incremented, verdict still in `context.verdict_chain` locally (lineage intact for next step)

**State persistence:**
- `test_get_state_serializes_cursors_and_incidents` — set cursors, add 2 incidents → get_state() returns expected shape
- `test_get_state_prunes_terminal_aged_incidents` — incident in RESOLVED with updated_at older than terminal_retention_seconds → not in get_state output; recent terminal incident → in output
- `test_get_state_keeps_active_incidents` — TRIAGING incident always in output regardless of age
- `test_state_roundtrip_preserves_all_fields` — get_state → restore_state on fresh module → same incidents, same cursors. **Explicitly assert `verdict_chain` survives roundtrip** (incident with non-empty verdict_chain pre-roundtrip, same list of IDs post-roundtrip). This guards the lineage continuity invariant: without it, post-restart `_emit_verdict()` would read `context.verdict_chain[-1]` against an empty list and produce verdicts with `lineage.parent=None` and broken `parent_ids`, breaking the chain.

**Lineage:**
- `test_first_verdict_from_snapshot_parents_correctly` — open incident from snapshot → first agent verdict has `lineage.parent=None`, `parent_ids=[snapshot["id"]]`, `lineage.context = [snapshot["id"]]`
- `test_chained_verdicts_parent_to_previous_respond_verdict` — second/third agent verdicts have `lineage.parent` and `parent_ids[0]` pointing to the previous respond verdict, `lineage.context` still references upstream trigger
- `test_fallback_path_lineage_walk` — open incident via fallback path (orphan quality_breach), run pipeline through to remediation, then walk `parent_ids` from the final verdict back through the chain: assert each step in (remediation → communication → investigation → triage → quality_breach) is reachable via `parent_ids` traversal. Validates that fallback-path lineage is structurally identical to snapshot-path lineage (same chaining rules, just different originating trigger).

**Escalation gate:**
- `test_escalation_flag_set_at_write_time` — agent emits escalate verdict below threshold → `metadata["escalation_pending"]` becomes True without verdict store re-fetch
- `test_escalation_gate_short_circuits` — `metadata["escalation_pending"]=True` → `_check_escalation()` returns True without API call

### Coordinator changes (`tests/respond/test_coordinator.py`)

Existing 32 test files in `tests/respond/` continue to pass. Two new tests added:

- `test_coordinator_returns_immediately_on_awaiting_approval` — context with state=AWAITING_APPROVAL → `coordinator.run()` returns same context unchanged (no agent calls, no state mutation)
- `test_coordinator_step_timeout_marks_failed` — mock triage agent that sleeps longer than `step_timeout_seconds` → state=FAILED, error contains "step_timeout"

### Integration test

Add to `test/integration-chain.sh` (existing 8-step chain) or as a separate respond-worker-mode test:

- Start core in-memory
- Seed correlation_snapshot assessment with parent quality_breach verdict
- Run RespondModule for one cycle
- Assert: incident in component_state, triage/investigation/communication/remediation verdicts in core with correct lineage, all chained back to the seeded snapshot

---

## Acceptance Criteria

From the bead, refined:

1. `RespondModule` implements `WorkerModule` protocol (name, restore_state, process_cycle, get_state)
2. Triggers polled from core: `correlation_snapshot` assessments (primary) + `quality_breach` verdicts (fallback after threshold, dedup against snapshot lineage)
3. State machine advances through all 4 pipeline steps in order; existing coordinator tests pass with the new AWAITING_APPROVAL early-return guard
4. Incident contexts persisted to `component_state("respond")` after each cycle; cursors persisted alongside
5. On worker restart: `restore_state` rebuilds incidents and cursors; in-flight pipelines resume from `last_completed_step_index`
6. All respond verdicts submitted to core via `CoreAPIClient.submit_verdict()` wrapped in CloudEvents envelope; `SQLiteVerdictStore` removed from worker path
7. Per-step timeout (`step_timeout_seconds` default 90) prevents single-incident lockup
8. Pruning rule: terminal-state incidents older than `terminal_retention_seconds` (default 86400) dropped from state on save
9. Latency property documented (new-trigger detection bounded by longest in-flight pipeline) with module-split fallback path
10. Escalation gate uses captured `metadata["escalation_pending"]` flag, not verdict re-fetch
11. Lineage continuity: respond's first verdict per incident sets `lineage.parent = trigger_verdict_id`, `lineage.context = trigger_verdict_ids`
12. Existing 32 respond test files pass (legacy CLI mode preserved)

## Out of P3-E.1 scope (explicit handoffs)

| Concern | Handoff |
|---------|---------|
| AWAITING_APPROVAL resumption (poll for `approval`/`denial` verdicts and resume pipeline) | P3-E.3 — safe-actions execution + approval-verdict polling |
| Replace raw `llm_call()` with Instructor `structured_call_with_usage` | P3-E.2 — Instructor-backed agent calls |
| Notification backends (Slack, ntfy, stdout) operate from worker context | P3-E.4 — notification backends |
| On-call escalation runner integrated into worker cycle | P3-E.5 — on-call resolution and escalation |
| Cases API integration (queryability, leasing, bench) | Follow-up P3-E case-API bead, post-P3-E.5 |
| Bench integration | Phase 4 (`P4.x` tasks) |
| Per-incident component_state keys (avoid blob contention at higher scale) | Either follow-up bead or v2 work depending on operational signal |
| Server-side `parent_ids` filter on core's `/assessments` API (replaces client-side O(N) scan in `_has_associated_snapshot`) | v2 — when core API supports `?parent_ids=<id>` query param, `_has_associated_snapshot` becomes a single targeted call rather than fetching a `kind=correlation_snapshot` page and scanning. Same upgrade path applies to correlate's parent-id lookups. |

---

## Work Sequence

| Step | What | Verify |
|------|------|--------|
| 1 | Add `RespondConfig` worker-mode fields (`cycle_interval_seconds`, `fallback_threshold_seconds`, `terminal_retention_seconds`, `step_timeout_seconds`) | `pytest tests/respond/test_config.py` |
| 2 | Add AWAITING_APPROVAL early-return guard to `_run_pipeline` | New coordinator test passes; existing 32 tests pass |
| 3 | Add per-step timeout wrapping in `_run_pipeline`; update `coordinator.py:86` to `unrecoverable: <exc>` format for `<reason>: <details>` convention | New coordinator timeout test passes; existing tests pass (any tests asserting on the raw exception string at line 86 updated to expect the `unrecoverable: ` prefix) |
| 4 | Refactor escalation gate to use captured flag (`metadata["escalation_pending"]`) | New escalation-flag test; existing escalation tests pass |
| 5 | Implement `submit_verdict_to_core` helper + dispatch in `agents/base.py._emit_verdict` (worker mode vs legacy CLI mode) | New verdict-submission test; existing agent tests pass with legacy path |
| 6 | Implement `RespondModule.restore_state`/`get_state` + `Cursors` + state pruning | restore/get_state roundtrip tests pass |
| 7 | Implement `RespondModule._ingest_triggers` (primary path: correlation_snapshot) | Snapshot ingest tests pass |
| 8 | Implement `RespondModule._ingest_triggers` (fallback path: quality_breach + `_has_associated_snapshot` dedup) | Fallback ingest tests pass |
| 9 | Implement `RespondModule._drive_active_incidents` with `_NoopContextStore` adapter | Drive tests pass |
| 10 | Implement `_open_incident_from_snapshot` and `_open_incident_from_breach` (incl. service_context, topology fetch from manifests) | Open-incident tests pass |
| 11 | Register `RespondModule` in `nthlayer-workers serve` CLI | Full workers test suite passes |
| 12 | Integration test against real core API (seeded snapshot → full pipeline → verdict chain in core) | Integration test passes |

Steps 1–4 are independent of each other and can be done in any order. Step 5 is the largest single change but is mechanical. Steps 6–10 are sequential within `RespondModule`. Step 11 requires all prior. Step 12 is end-to-end verification.

---

## Decisions captured during brainstorming

- **Q1 (trigger sources & dedup):** primary = `correlation_snapshot`, fallback = `quality_breach` after threshold without snapshot. Lineage-aware dedup. Rationale: situation-shaped pipeline needs situation-shaped triggers; 1:1 per signal would produce duplicate incidents (operational quality issue, not refinement-deferred).
- **Q2 (verdict-write boundary):** all respond verdicts submitted to core via `CoreAPIClient.submit_verdict()` in P3-E.1. `SQLiteVerdictStore` fully removed from worker path. Escalation gate refactored to capture-at-write-time, eliminating per-step API round-trip.
- **Q3 (context storage):** D-blob — single `component_state("respond")` document, prune terminal-aged incidents on save. D-cases deferred to a dedicated follow-up bead.
- **Q4 (concurrency within cycle):** sequential (no `asyncio.gather`). Per-step timeout (`step_timeout_seconds` default 90) guards against single-incident lockup. Latency property documented; module-split (Trigger / Pipeline) is the pre-designed v1.5-shaped escape hatch if higher scale demands it.
- **AWAITING_APPROVAL semantics:** existing `_run_pipeline` already returns immediately at the gate; P3-E.1 adds a top-of-`_run_pipeline` early-return guard so worker-mode `coordinator.run()` calls are idempotent on this state. Resumption (poll for approval verdict) is P3-E.3.
- **`fallback_reason` value:** static string `"no_correlation_snapshot"` in metadata; threshold value emitted in structlog at trigger time. Avoids drift if threshold becomes operationally configurable.
- **Pattern naming:** "Capture-at-write-time" — when a worker has a fresh decision-bearing object, prefer storing decision-relevant fields onto local in-process state over re-fetching later. Applied here to escalation flag; reusable where it fits.
- **Pattern naming:** "Worker-mode invariant: validate state on entry" — polling-driven entry points lack the state-knowledge that operator-driven CLI invocation has. Every worker-mode entry point must validate state on entry and return no-op when assumptions don't hold. Applied here to `_run_pipeline` (AWAITING_APPROVAL guard); P3-E.2/E.3/E.4/E.5 sub-tasks must apply the same check at any new entry points they add.
- **`context.error` format convention:** P3-E.1 establishes `<reason>: <details>` (e.g. `step_timeout: triage exceeded 90s`). Existing single occurrence at `coordinator.py:86` updated to `unrecoverable: <exc>` for consistency.
