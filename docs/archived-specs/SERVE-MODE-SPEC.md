# NthLayer: Serve Mode Spec — Pull-Based Pipeline

**Status:** Proposal  
**Date:** 2026-04-12  
**Depends on:** Content-addressed decision records (done), assessment store (done), verdict store (done)  
**Unlocks:** Fully autonomous pipeline, Textual TUI dashboard

---

## Architecture

Every NthLayer runtime component gets a `serve` subcommand that runs indefinitely. Each component polls the shared store for new records, processes them, and writes its own records. No HTTP event ingestion. No message queue. No webhook receiver. Just store-driven polling on a shared SQLite database in WAL mode.

The pipeline is pull-based:

```
observe serve
  │ polls Prometheus on schedule
  │ writes hashed assessments to store
  │
  ▼ (measure polls store for breach assessments)
measure serve
  │ runs LLM evaluation
  │ writes hashed evaluation verdicts to store
  │
  ▼ (correlate polls store for new evaluation verdicts with breach=true)
correlate serve
  │ gathers signals, runs LLM reasoning
  │ writes hashed correlation verdicts to store
  │
  ▼ (respond polls store for new correlation verdicts)
respond serve  [already exists — approval server]
  │ runs agent pipeline (triage → investigation → remediation)
  │ writes incident verdicts to store
  │ escalation, Slack, approval workflow
  │
  ▼ (learn polls store for resolved incident verdicts)
learn serve
  │ runs retrospective analysis
  │ writes retrospective verdicts to store
  │ closes the feedback loop
```

Each component is independent. Start them in any order. If correlate isn't running, measure still writes breach verdicts — they accumulate in the store and correlate processes them when it starts. If respond isn't running, correlation verdicts accumulate. The store is the integration layer.

---

## Shared Patterns

Every serve mode follows the same structure:

```python
class ComponentServer:
    """Base pattern for all NthLayer serve modes."""
    
    def __init__(self, config, store):
        self.config = config
        self.store = store
        self._last_processed_hash: str | None = None
        self._running = False
    
    async def run(self):
        """Main serve loop."""
        self._running = True
        logger.info("serve_started", component=self.component_name)
        
        while self._running:
            try:
                await self._poll_cycle()
            except Exception as e:
                logger.error("poll_cycle_error", error=str(e))
                # Fail-open: log and continue, don't crash the server
            
            await asyncio.sleep(self.config.poll_interval_seconds)
    
    async def _poll_cycle(self):
        """Override in each component. Query store, process new records."""
        raise NotImplementedError
    
    def stop(self):
        self._running = False
```

### Store Polling Pattern

Each component tracks the hash of the last record it processed. On each poll cycle, it queries the store for records newer than its last processed timestamp. This is cheap — a single indexed SQLite query.

```python
async def _poll_for_new_records(
    self,
    record_type: str,          # "assessment" or "verdict"
    filter_type: str,          # e.g. "slo_state" or "evaluation"
    since: datetime | None,
) -> list[Record]:
    """Query store for records newer than last processed."""
    if record_type == "assessment":
        return self.store.query(AssessmentFilter(
            assessment_type=filter_type,
            from_time=since,
        ))
    else:
        return self.store.query(VerdictFilter(
            verdict_type=filter_type,
            from_time=since,
        ))
```

### Deduplication

Content-addressed records make deduplication trivial. If a component has already processed a record with hash `a8f2c1`, it skips it. The `_last_processed_hash` is persisted to a small state file (or a `_component_state` table in the shared store) so it survives restarts.

### Graceful Shutdown

All serve modes handle SIGINT and SIGTERM. The main loop checks `self._running` on each iteration. In-progress work completes before exit. No partial records in the store.

---

## Component 1: nthlayer-observe serve

### What It Does

Polls Prometheus on a configurable schedule. For each service in the specs directory, collects SLO metrics and writes `slo_state` assessments to the store. Optionally runs drift analysis on the collected data.

### CLI

```bash
nthlayer-observe serve \
  --specs-dir ./specs/ \
  --prometheus-url http://localhost:9090 \
  --store ./nthlayer.db \
  --interval 30                    # seconds between collection cycles
  --include-drift                  # also run drift analysis each cycle
  --drift-interval 300             # drift analysis every 5 min (less frequent)
```

### Serve Loop

```python
class ObserveServer:
    """Scheduled SLO collection + drift detection."""
    
    component_name = "observe"
    
    def __init__(self, config: ObserveConfig, store: AssessmentStore):
        self.config = config
        self.store = store
        self.collector = SLOMetricCollector(config.prometheus_url)
        self.drift_analyzer = DriftAnalyzer() if config.include_drift else None
        self._last_drift_run: datetime | None = None
    
    async def _poll_cycle(self):
        """One collection cycle: query Prometheus, write assessments."""
        specs = load_specs(self.config.specs_dir)
        
        # Group SLOs by service
        by_service: dict[str, list[SLODefinition]] = {}
        for spec in specs:
            by_service.setdefault(spec.service, []).append(spec)
        
        breach_count = 0
        
        for service, slos in by_service.items():
            # Collect SLO metrics
            results = await self.collector.collect(slos, service)
            assessments = results_to_assessments(results, service)
            
            for assessment in assessments:
                self.store.put(assessment)
                if assessment.data.get("status") in ("EXHAUSTED", "CRITICAL"):
                    breach_count += 1
            
            # Drift analysis (less frequent)
            if self.drift_analyzer and self._should_run_drift():
                drift_result = await self.drift_analyzer.analyze(
                    service, self.config.prometheus_url
                )
                if drift_result:
                    drift_assessment = drift_to_assessment(drift_result, service)
                    self.store.put(drift_assessment)
        
        logger.info(
            "observe_cycle_complete",
            services=len(by_service),
            assessments=sum(len(v) for v in by_service.values()),
            breaches=breach_count,
        )
    
    def _should_run_drift(self) -> bool:
        if not self._last_drift_run:
            return True
        elapsed = (datetime.now(UTC) - self._last_drift_run).total_seconds()
        return elapsed >= self.config.drift_interval_seconds
```

### What It Writes

`slo_state` assessments (every cycle) and `drift` assessments (less frequently). Each assessment is content-addressed with a pre-computed summary.

### What Triggers Downstream

Nothing explicitly. Measure's serve mode polls the store for `slo_state` assessments with breach status. The trigger is implicit — observe writes, measure reads.

---

## Component 2: nthlayer-measure serve

### What It Does

Polls the assessment store for new `slo_state` assessments that indicate a breach. For each breach, runs the LLM evaluation to determine whether the breach represents genuine AI decision quality degradation (for `ai-gate` services) or a traditional SLO violation. Writes evaluation verdicts.

### CLI

```bash
nthlayer-measure serve \
  --store ./nthlayer.db \
  --specs-dir ./specs/ \
  --interval 15                    # seconds between poll cycles
  --model anthropic/claude-sonnet-4-20250514
```

### Serve Loop

```python
class MeasureServer:
    """Polls for breach assessments, runs LLM evaluation."""
    
    component_name = "measure"
    
    def __init__(self, config: MeasureConfig, store):
        self.config = config
        self.store = store
        self._last_processed_time: datetime | None = None
    
    async def _poll_cycle(self):
        """Check for new breach assessments, evaluate each."""
        # Query for slo_state assessments since last check
        new_assessments = self.store.query(AssessmentFilter(
            assessment_type="slo_state",
            from_time=self._last_processed_time,
        ))
        
        if not new_assessments:
            return
        
        # Filter to breaching assessments only
        breaches = [
            a for a in new_assessments
            if a.data.get("status") in ("EXHAUSTED", "CRITICAL", "WARNING")
        ]
        
        for assessment in breaches:
            # Check if we've already evaluated this assessment (by hash)
            if self._already_evaluated(assessment.hash):
                continue
            
            # Load the service spec to determine type (ai-gate vs traditional)
            spec = self._load_service_spec(assessment.service)
            
            if spec and spec.get("type") == "ai-gate":
                # LLM evaluation for AI decision quality
                verdict = await self._evaluate_judgment_slo(assessment, spec)
            else:
                # Deterministic evaluation for traditional SLOs
                verdict = self._evaluate_traditional_slo(assessment, spec)
            
            self.store.put_verdict(verdict)
            
            logger.info(
                "evaluation_complete",
                service=assessment.service,
                slo=assessment.data.get("slo_name"),
                breach=verdict.data.get("breach", False),
                confidence=verdict.data.get("confidence"),
                input_hash=assessment.hash,
            )
        
        # Update watermark
        self._last_processed_time = max(a.timestamp for a in new_assessments)
    
    def _already_evaluated(self, assessment_hash: str) -> bool:
        """Check if an evaluation verdict already references this assessment."""
        existing = self.store.query_verdicts(VerdictFilter(
            verdict_type="evaluation",
        ))
        return any(
            assessment_hash in v.data.get("input_hashes", [])
            for v in existing
        )
    
    async def _evaluate_judgment_slo(self, assessment, spec) -> Verdict:
        """LLM-powered evaluation for ai-gate services."""
        # Build context from recent assessments for this service
        recent = self.store.query(AssessmentFilter(
            service=assessment.service,
            assessment_type="slo_state",
            limit=10,
        ))
        
        # Run the existing evaluation pipeline
        # (evaluate-once logic, now triggered by store polling)
        result = await self.evaluator.evaluate(
            service=assessment.service,
            assessments=recent,
            spec=spec,
        )
        
        return create_verdict(
            verdict_type="evaluation",
            service=assessment.service,
            agent="measure",
            input_hashes=[assessment.hash],
            data={
                "slo_name": assessment.data.get("slo_name"),
                "breach": True,
                "confidence": result.confidence,
                "severity": result.severity,
                "reasoning": result.reasoning,
            },
        )
```

### Hysteresis

Measure applies hysteresis to avoid flapping:
- **Breach detection:** assessment must show breach status for N consecutive poll cycles (configurable, default 3 cycles = ~45 seconds at 15s interval) before emitting a verdict.
- **Recovery detection:** assessment must show healthy status for M consecutive cycles (default 5 = ~75 seconds, asymmetric to prevent flapping).

State for hysteresis tracking is kept in memory (reset on restart — conservative, re-evaluates from current state).

### What It Writes

Evaluation verdicts with `breach: true` and the assessment hash in `input_hashes`. For traditional SLOs, the verdict is deterministic. For ai-gate services, the verdict includes LLM-derived confidence and reasoning.

### What Triggers Downstream

Nothing explicitly. Correlate polls for evaluation verdicts with `breach: true`.

---

## Component 3: nthlayer-correlate serve

### What It Does

Polls the verdict store for new evaluation verdicts with `breach: true`. For each, gathers correlated signals (alerts, other assessments, trace evidence if configured), runs the LLM reasoning layer, and writes a correlation verdict with root cause analysis.

### CLI

```bash
nthlayer-correlate serve \
  --store ./nthlayer.db \
  --specs-dir ./specs/ \
  --prometheus-url http://localhost:9090 \
  --interval 10                    # seconds between poll cycles
  --model anthropic/claude-sonnet-4-20250514
  --trace-backend tempo             # optional
  --tempo-endpoint http://tempo:3200 # optional
```

### Serve Loop

```python
class CorrelateServer:
    """Polls for breach verdicts, runs causal reasoning."""
    
    component_name = "correlate"
    
    def __init__(self, config: CorrelateConfig, store):
        self.config = config
        self.store = store
        self._last_processed_time: datetime | None = None
    
    async def _poll_cycle(self):
        """Check for new breach verdicts, run correlation."""
        new_verdicts = self.store.query_verdicts(VerdictFilter(
            verdict_type="evaluation",
            from_time=self._last_processed_time,
        ))
        
        if not new_verdicts:
            return
        
        # Filter to breach verdicts only
        breaches = [
            v for v in new_verdicts
            if v.data.get("breach") is True
        ]
        
        for breach_verdict in breaches:
            if self._already_correlated(breach_verdict.hash):
                continue
            
            # Gather signals for correlation
            signals = await self._gather_signals(breach_verdict)
            
            # Run correlation engine (deterministic grouping)
            groups = self.engine.correlate(signals)
            
            # Run reasoning layer (LLM causal analysis)
            if self.config.reasoning_enabled:
                reasoning = await self.reasoning.analyze(
                    groups=groups,
                    dependency_graph=signals.dependency_graph,
                    trace_evidence=signals.trace_evidence,
                )
            else:
                reasoning = self._heuristic_analysis(groups)
            
            # Write correlation verdict
            verdict = create_verdict(
                verdict_type="correlation",
                service=breach_verdict.service,
                agent="correlate",
                input_hashes=[breach_verdict.hash],
                data={
                    "trigger_verdict": breach_verdict.hash,
                    "root_causes": reasoning.root_causes,
                    "blast_radius": reasoning.blast_radius,
                    "confidence": reasoning.confidence,
                    "groups": len(groups),
                    "evidence_sources": signals.sources_summary(),
                },
            )
            self.store.put_verdict(verdict)
            
            # Send Slack notification (breach detected + root cause)
            if self.config.slack_enabled:
                await self._notify_slack(verdict, breach_verdict)
            
            logger.info(
                "correlation_complete",
                service=breach_verdict.service,
                root_causes=len(reasoning.root_causes),
                confidence=reasoning.confidence,
                groups=len(groups),
            )
        
        self._last_processed_time = max(v.timestamp for v in new_verdicts)
    
    async def _gather_signals(self, breach_verdict) -> GatheredSignals:
        """Gather all available evidence for correlation."""
        service = breach_verdict.service
        
        # Time window: 30 min before breach to now
        window_start = breach_verdict.timestamp - timedelta(minutes=30)
        window_end = datetime.now(UTC)
        
        # Assessments from observe (SLO state, drift, dependencies)
        slo_assessments = self.store.query(AssessmentFilter(
            service=service,
            assessment_type="slo_state",
            from_time=window_start,
        ))
        
        drift_assessments = self.store.query(AssessmentFilter(
            service=service,
            assessment_type="drift",
            from_time=window_start,
        ))
        
        dep_assessments = self.store.query(AssessmentFilter(
            assessment_type="dependency",
            from_time=window_start,
        ))
        
        # Prometheus alerts (direct query)
        alerts = await self.prometheus.query_alerts(window_start, window_end)
        
        # Trace evidence (if configured)
        trace_evidence = None
        if self.trace_backend:
            blast_services = self._compute_blast_radius(service, dep_assessments)
            trace_evidence = await self.trace_backend.get_trace_evidence(
                services=blast_services,
                start=window_start,
                end=window_end,
            )
        
        return GatheredSignals(
            slo_assessments=slo_assessments,
            drift_assessments=drift_assessments,
            dependency_assessments=dep_assessments,
            alerts=alerts,
            trace_evidence=trace_evidence,
        )
```

### What It Writes

Correlation verdicts with root causes, blast radius, confidence, and references to the input verdict hashes. Optionally sends Slack notifications for the breach detection and root cause identification lifecycle messages.

### What Triggers Downstream

Nothing explicitly. Respond polls for new correlation verdicts.

---

## Component 4: nthlayer-respond serve (Extended)

### What Already Exists

Respond already has a serve mode: the starlette approval server with HTTP routes for approve/reject, Slack interaction handler, and approval timeout tracking. This extends it to also poll for new correlation verdicts and automatically start the agent pipeline.

### CLI (Updated)

```bash
nthlayer-respond serve \
  --store ./nthlayer.db \
  --specs-dir ./specs/ \
  --host 0.0.0.0 \
  --port 8090 \
  --interval 10                    # poll interval for new correlation verdicts
  --model anthropic/claude-sonnet-4-20250514
  --notify slack                   # notification channels
```

### Extended Serve Loop

```python
class RespondServer:
    """
    Extended from existing ApprovalServer.
    Adds: polling for new correlation verdicts → auto-start agent pipeline.
    Keeps: HTTP approval routes, Slack interaction handler, timeout tracking.
    """
    
    def __init__(self, config, store, coordinator):
        # Existing
        self.approval_server = ApprovalServer(coordinator, store, config)
        self.coordinator = coordinator
        
        # New: correlation verdict polling
        self.store = store
        self.config = config
        self._last_processed_time: datetime | None = None
    
    async def run(self):
        """Run HTTP server + correlation polling concurrently."""
        # Start the starlette server (existing)
        server_task = asyncio.create_task(
            self._run_http_server()
        )
        
        # Start the correlation verdict poll loop (new)
        poll_task = asyncio.create_task(
            self._poll_loop()
        )
        
        await asyncio.gather(server_task, poll_task)
    
    async def _poll_loop(self):
        """Poll for new correlation verdicts, start agent pipeline."""
        while self._running:
            try:
                await self._check_for_correlations()
            except Exception as e:
                logger.error("respond_poll_error", error=str(e))
            
            await asyncio.sleep(self.config.poll_interval_seconds)
    
    async def _check_for_correlations(self):
        """Look for new correlation verdicts that need response."""
        new_correlations = self.store.query_verdicts(VerdictFilter(
            verdict_type="correlation",
            from_time=self._last_processed_time,
        ))
        
        if not new_correlations:
            return
        
        for correlation in new_correlations:
            if self._already_responded(correlation.hash):
                continue
            
            # Start the agent pipeline
            # Triage → Investigation + Communication → Remediation
            incident_context = await self.coordinator.handle_incident(
                correlation_verdict=correlation,
                specs_dir=self.config.specs_dir,
            )
            
            # Escalation runner starts if on-call is configured
            if incident_context.requires_escalation:
                await self.escalation_runner.start_escalation(
                    incident_context.incident_id,
                    self._build_notification_payload(incident_context),
                    incident_context.escalation_steps,
                )
            
            logger.info(
                "incident_opened",
                incident_id=incident_context.incident_id,
                severity=incident_context.severity,
                service=correlation.service,
            )
        
        self._last_processed_time = max(c.timestamp for c in new_correlations)
```

### What It Writes

Incident verdicts (triage, investigation, remediation, resolution). The existing verdict chain from the respond spec.

---

## Component 5: nthlayer-learn serve

### What It Does

Polls the verdict store for incident verdicts with status "resolved." For each, runs the retrospective analysis: reconstructs the incident timeline from the verdict chain, measures whether the correlation was accurate, whether the remediation worked, and produces a retrospective verdict.

### CLI

```bash
nthlayer-learn serve \
  --store ./nthlayer.db \
  --specs-dir ./specs/ \
  --interval 60                    # check every minute (incidents resolve infrequently)
  --model anthropic/claude-sonnet-4-20250514
```

### Serve Loop

```python
class LearnServer:
    """Polls for resolved incidents, runs retrospectives."""
    
    component_name = "learn"
    
    def __init__(self, config: LearnConfig, store):
        self.config = config
        self.store = store
        self._last_processed_time: datetime | None = None
    
    async def _poll_cycle(self):
        """Check for newly resolved incidents."""
        resolved = self.store.query_verdicts(VerdictFilter(
            verdict_type="incident",
            from_time=self._last_processed_time,
        ))
        
        # Filter to resolved incidents
        resolved = [
            v for v in resolved
            if v.data.get("status") == "resolved"
        ]
        
        for incident_verdict in resolved:
            if self._already_reviewed(incident_verdict.hash):
                continue
            
            # Walk the verdict chain back to the original assessment
            chain = self._reconstruct_chain(incident_verdict)
            
            # Run retrospective analysis
            retro = await self.analyzer.analyze(
                incident=incident_verdict,
                chain=chain,
                specs_dir=self.config.specs_dir,
            )
            
            # Write retrospective verdict
            verdict = create_verdict(
                verdict_type="retrospective",
                service=incident_verdict.service,
                agent="learn",
                input_hashes=[incident_verdict.hash],
                data={
                    "incident_id": incident_verdict.data.get("incident_id"),
                    "duration_minutes": retro.duration_minutes,
                    "root_cause_accurate": retro.root_cause_accurate,
                    "remediation_effective": retro.remediation_effective,
                    "recommendations": retro.recommendations,
                    "decisions_during_incident": retro.decision_count,
                    "reversal_rate": retro.reversal_rate,
                    "timeline": retro.timeline,
                },
            )
            self.store.put_verdict(verdict)
            
            # Optionally update spec recommendations
            if retro.spec_changes:
                logger.info(
                    "spec_recommendation",
                    service=incident_verdict.service,
                    changes=retro.spec_changes,
                )
            
            logger.info(
                "retrospective_complete",
                incident_id=incident_verdict.data.get("incident_id"),
                root_cause_accurate=retro.root_cause_accurate,
                remediation_effective=retro.remediation_effective,
            )
        
        if resolved:
            self._last_processed_time = max(v.timestamp for v in resolved)
    
    def _reconstruct_chain(self, incident_verdict) -> list:
        """Walk input_hashes backward to reconstruct the full chain."""
        chain = [incident_verdict]
        current = incident_verdict
        
        while current.data.get("input_hashes"):
            for parent_hash in current.data["input_hashes"]:
                parent = self.store.get_verdict(parent_hash)
                if parent:
                    chain.append(parent)
                    current = parent
                    break
            else:
                break
        
        chain.reverse()  # chronological order
        return chain
```

### What It Writes

Retrospective verdicts with accuracy measurements, duration, recommendation list, and the reconstructed verdict chain. This closes the feedback loop — learn's output informs whether measure's evaluations and correlate's reasoning were correct.

### Poll Interval

60 seconds, not 10-15 like the other components. Incidents resolve infrequently. Polling every minute is plenty.

---

## Configuration

### Shared Config Pattern

All components use the same config structure for shared settings:

```yaml
# nthlayer.yaml (ecosystem-wide config)

store:
  path: ./nthlayer.db               # shared SQLite database

prometheus:
  url: http://localhost:9090

specs:
  dir: ./specs/

model:
  default: anthropic/claude-sonnet-4-20250514

slack:
  bot_token: "${SLACK_BOT_TOKEN}"
  signing_secret: "${SLACK_SIGNING_SECRET}"

# Per-component overrides
observe:
  interval: 30                       # collection interval (seconds)
  include_drift: true
  drift_interval: 300

measure:
  interval: 15                       # poll interval
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

learn:
  interval: 60
```

### Environment Variable Overrides

Every config field can be overridden by environment variable:

```bash
NTHLAYER_STORE_PATH=./nthlayer.db
NTHLAYER_PROMETHEUS_URL=http://localhost:9090
NTHLAYER_MODEL=anthropic/claude-sonnet-4-20250514
NTHLAYER_OBSERVE_INTERVAL=30
NTHLAYER_MEASURE_INTERVAL=15
```

---

## Deployment

### Development (Single Machine)

```bash
# Terminal 1: observe
nthlayer-observe serve --specs-dir ./specs/ --prometheus-url http://localhost:9090

# Terminal 2: measure
nthlayer-measure serve --store ./nthlayer.db --specs-dir ./specs/

# Terminal 3: correlate
nthlayer-correlate serve --store ./nthlayer.db --specs-dir ./specs/ --prometheus-url http://localhost:9090

# Terminal 4: respond
nthlayer-respond serve --store ./nthlayer.db --specs-dir ./specs/

# Terminal 5: learn
nthlayer-learn serve --store ./nthlayer.db --specs-dir ./specs/

# Terminal 6 (optional): Textual dashboard
nthlayer dashboard --store ./nthlayer.db --specs-dir ./specs/
```

### Docker Compose

```yaml
services:
  observe:
    image: nthlayer-observe
    command: serve --specs-dir /specs --prometheus-url http://prometheus:9090
    volumes:
      - store:/data
      - ./specs:/specs:ro

  measure:
    image: nthlayer-measure
    command: serve --store /data/nthlayer.db --specs-dir /specs
    volumes:
      - store:/data
      - ./specs:/specs:ro

  correlate:
    image: nthlayer-correlate
    command: serve --store /data/nthlayer.db --specs-dir /specs --prometheus-url http://prometheus:9090
    volumes:
      - store:/data
      - ./specs:/specs:ro

  respond:
    image: nthlayer-respond
    command: serve --store /data/nthlayer.db --specs-dir /specs
    ports:
      - "8090:8090"
    volumes:
      - store:/data
      - ./specs:/specs:ro

  learn:
    image: nthlayer-learn
    command: serve --store /data/nthlayer.db --specs-dir /specs
    volumes:
      - store:/data
      - ./specs:/specs:ro

volumes:
  store:
```

**Note on shared SQLite in Docker:** All containers mount the same volume for the store. SQLite WAL mode handles concurrent readers. Only one writer at a time — but each component writes infrequently (one record per event, not continuous streams), so contention is minimal. If it becomes a bottleneck at scale, the store abstraction supports swapping to PostgreSQL without changing component code.

---

## Textual Dashboard Connection

The Textual TUI (`nthlayer dashboard`) is a read-only consumer of the same store. It polls the assessment and verdict tables and renders:

- **SLO Status Table** — latest `slo_state` assessments per service
- **Verdict Stream** — newest verdicts across all components, colour-coded by type
- **Incident Panel** — open incidents with root cause and blast radius
- **Lifecycle Bar** — which components are active, last poll time, record counts

The dashboard doesn't trigger anything. It's a window into the store. It runs alongside the serve processes or independently.

---

## Implementation Priority

| Component | Effort | Notes |
|---|---|---|
| **observe serve** | 2-3 days | Scheduled collection loop, most straightforward |
| **measure serve** | 2-3 days | Store polling + hysteresis, existing evaluate-once logic |
| **correlate serve** | 2-3 days | Store polling + signal gathering, existing correlate logic |
| **respond serve extension** | 1-2 days | Add poll loop alongside existing HTTP server |
| **learn serve** | 2-3 days | Chain reconstruction + retrospective |
| **Shared config loader** | 1-2 days | nthlayer.yaml with env var overrides |
| **Integration test** | 2-3 days | End-to-end: inject fault → observe detects → pipeline runs → retrospective produced |

Total: ~14-19 days for the full autonomous pipeline.

---

## Verification

### Per-Component

Each serve mode is testable in isolation:
- observe serve: mock Prometheus, verify assessments appear in store
- measure serve: pre-populate store with breach assessments, verify evaluation verdicts
- correlate serve: pre-populate with breach verdicts, verify correlation verdicts
- respond serve: pre-populate with correlation verdicts, verify incident handling
- learn serve: pre-populate with resolved incidents, verify retrospectives

### End-to-End

The integration test is the ultimate verification:

1. Start all five serve processes
2. Start a fake service exporting metrics to Prometheus
3. Degrade the fake service (model regression scenario)
4. Watch the store: `slo_state` assessment → `evaluation` verdict → `correlation` verdict → `incident` verdict → `retrospective` verdict
5. Verify the verdict chain is complete and hash-linked
6. Verify Slack notifications were sent (mock or real)
7. Verify the retrospective correctly identifies the root cause

This is the demo: "Point NthLayer at your Prometheus endpoint and your specs directory. Watch it work."
