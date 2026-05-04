# nthlayer-measure — v1-draft

**Status:** Draft for implementation
**Date:** 2026-04-19
**Scope:** NthLayer reference implementation; not part of OpenSRM specification

---

## 1. Purpose

nthlayer-measure is the AI quality measurement and autonomy governance component of the NthLayer ecosystem. It owns:

1. **Judgment SLO evaluation.** Computing the eight judgment SLO types defined in OpenSRM core §5 against actual agent decisions.
2. **Self-calibration.** Measuring its own accuracy as an evaluator. A measurement system that doesn't know how accurate it is, is useless.
3. **Autonomy governance.** A one-way ratchet that reduces an agent's autonomy level when its judgment SLOs breach; human approval is required to raise autonomy back.
4. **Calibration consumption.** Consuming calibration signals from nthlayer-learn to refine judgment-SLO computations.

The component is the mechanism by which OpenSRM judgment SLOs become operational rather than aspirational. A manifest can declare "triage agent reversal rate must be below 5%"; nthlayer-measure is what actually checks it and acts on breaches.

## 2. Position in the Pipeline

```
                            OpenSRM manifest
                            (judgment SLOs)
                                  │
                                  ▼
observe ──┐
correlate ┼──→ agents ──┬──→ measure ──→ verdicts (autonomy-change)
respond ──┘            │                       │
                       │                       ▼
                       └──→ learn ─────→ calibration signals
```

Inputs:
- Judgment SLO declarations from OpenSRM manifests
- Agent decision verdicts (from respond, correlate, or any agent-bearing component)
- Calibration signals from nthlayer-learn
- Periodic audit samples (LLM-as-judge or human-in-the-loop)

Outputs:
- Judgment SLO evaluation assessments (continuous)
- Autonomy-change verdicts (when autonomy adjusts)
- Quality-breach verdicts (when an SLO breaches)

## 3. Architectural Thesis

Three load-bearing choices:

**Measurement is itself measured.** An evaluator that claims 99% accuracy without evidence is indistinguishable from noise. measure tracks its own calibration via a sampled ground-truth pipeline and surfaces its error-bars to consumers.

**Autonomy is a ratchet, not a dial.** Agent autonomy can be reduced automatically based on measurement. It cannot be raised without human approval. This prevents the failure mode where a marginal improvement in a recent window triggers automatic autonomy restoration that proves premature.

**Judgment SLOs are universal, not AI-specific.** The same framework applies to any decision-making service — ML classifiers, rule-based gates, human-in-the-loop approvals, AI agents. Treating this as "AI quality measurement" is an understatement that narrows the addressable problem.

## 4. Judgment SLO Evaluation

### 4.1 Eight types from OpenSRM §5.2

measure implements evaluators for all eight standard judgment SLO types:

- **Reversal rate.** How often decisions are reversed.
- **High-confidence failure.** How often high-confidence decisions turn out wrong.
- **Audit sampling.** Stratified sampling completeness and timeliness.
- **Outcomes.** Intended-outcome rate via downstream signals.
- **Escalation.** Escalation rate and escalation-quality.
- **Segments.** Variance across segments (customer tier, geography, request type).
- **Stability.** Decision consistency over time on a frozen probe set.
- **Calibration.** Confidence-vs-accuracy alignment.

Each type has a dedicated evaluator module. Custom types (organisations defining their own under non-standard `apiVersion`) plug in as additional modules.

### 4.2 Evaluation cycle

On each cycle (default 60 seconds):

1. Load all currently-active judgment SLO declarations from cached OpenSRM manifests
2. For each declaration, invoke the appropriate evaluator
3. The evaluator reads relevant verdicts and calibration signals from the store
4. The evaluator computes the SLO's current value and compares to the target
5. Emit a `judgment_slo_evaluation` assessment with the computed value, target, and status
6. If the SLO is in breach, trigger the declared `breach_actions` (notification, case creation, autonomy adjustment, action request)

### 4.3 Evaluator interface

```python
class JudgmentSLOEvaluator(Protocol):
    slo_type: str

    async def evaluate(
        self,
        declaration: JudgmentSLODeclaration,
        store: Store,
        window: TimeWindow,
    ) -> JudgmentSLOResult:
        ...

    def statistical_requirements(self) -> StatisticalRequirements:
        """Describe the statistical methods used, for audit."""
```

### 4.4 Worked example: reversal rate evaluator

```python
class ReversalRateEvaluator:
    slo_type = "reversal_rate"

    async def evaluate(self, decl, store, window):
        service = decl.spec.service
        source = decl.spec.measurement.source

        # Get all decisions from this service in the window
        decisions = await store.query_verdicts(
            service=service,
            types=["action_request", "approval", "classification"],
            created_between=(window.start, window.end),
        )

        reversal_count = 0
        for decision in decisions:
            # A reversal is a subsequent verdict with nthlayer.decision.reversal_of
            # pointing at this decision
            reversals = await store.query_descendants(
                decision.cid,
                attribute_filter={"nthlayer.decision.reversal_of": decision.cid},
            )
            if reversals:
                reversal_count += 1

        rate = reversal_count / len(decisions) if decisions else 0.0
        ci = binomial_confidence_interval(reversal_count, len(decisions), alpha=0.05)

        return JudgmentSLOResult(
            slo_cid=decl.cid,
            window=window,
            value=rate,
            target=decl.spec.target.maximum_reversal_rate,
            status="healthy" if rate <= decl.spec.target.maximum_reversal_rate else "breach",
            confidence_interval=ci,
            sample_size=len(decisions),
        )
```

Similar evaluator shapes exist for each of the other seven types. The pattern is: query store for relevant verdicts, compute the type-specific metric, produce a confidence interval, compare to target.

## 5. Self-Calibration

### 5.1 The problem

measure's evaluators are themselves making judgments about whether agents' judgments are sound. Those evaluations can be wrong. If measure claims "triage agent is meeting its reversal-rate SLO" and the evaluation itself is miscalibrated, the claim is worse than useless — it's actively misleading.

Every evaluator therefore has its own calibration metric, tracked continuously.

### 5.2 Calibration pipeline

Periodically (default daily):

1. A stratified sample of recent evaluations is extracted (e.g., 100 judgment-SLO evaluations across types, agents, and outcome categories)
2. Each sample is independently re-evaluated by a ground-truth process:
   - For reversible/verifiable SLOs (reversal rate, outcomes): ground-truth from lineage and observed outcomes
   - For subjective SLOs (audit sampling decisions): human review of a smaller secondary sample
3. Measure's evaluation is compared to ground truth
4. Agreement rate is recorded per evaluator

### 5.3 Evaluator agreement SLO

Each evaluator has its own judgment SLO (yes, it's recursive):

```yaml
apiVersion: opensrm.nthlayer.io/v2
kind: JudgmentSLO
metadata:
  name: measure-reversal-evaluator-agreement
spec:
  service: nthlayer-measure
  judgment_type: outcomes
  outcome_signal:
    source: self-calibration-pipeline
    window: 24h
  target:
    desired_outcome_rate: 0.95    # measure agrees with ground truth 95% of the time
```

If an evaluator's agreement rate drops below target, measure marks that evaluator's outputs as degraded. Downstream consumers (the autonomy ratchet, the Bench's quality display) treat degraded evaluations with lower trust.

### 5.4 Recursion termination

"The evaluator has its own SLO evaluated by the evaluator" is logically recursive but practically bounded: the recursion terminates at the first level because the measure-of-measure doesn't itself have another measure-of-measure-of-measure.

The second-level check is: a human operator periodically audits a small sample of self-calibration results. This is the final ground-truth source and is low-volume enough to be practical (typically < 10 samples per quarter).

## 6. Autonomy Governance

### 6.1 Autonomy levels

An agent's autonomy level determines what actions it can request without human approval. Five levels, ordered:

| Level | Meaning |
|---|---|
| `observer` | Agent produces verdicts but no action requests |
| `advisor` | Agent produces action requests; all require human approval |
| `limited-autonomous` | Agent can execute low-blast-radius actions without approval; anything with production blast radius requires approval |
| `autonomous` | Agent can execute most actions without approval; only highest-severity actions require approval |
| `fully-autonomous` | Agent can execute any declared action (still subject to policy evaluation) |

An agent's current autonomy level is recorded in the store's `agent_state` table and is a required input to authorisation decisions (via the `principal.attributes.agent.autonomy_level` principal attribute).

### 6.2 The ratchet

When an agent's judgment SLOs breach, measure emits an `autonomy_change` verdict that reduces the agent's autonomy level. The ratchet rule:

**Automatic reduction.** Autonomy can drop to a lower level automatically based on evaluator output. The reduction happens within the cycle that detected the breach.

**Manual elevation only.** Autonomy cannot be raised automatically. Even if subsequent measurement shows the agent is performing well, the agent stays at the reduced level until a human operator explicitly raises it via an `autonomy_elevation` action request (which itself goes through the normal authorisation flow).

### 6.3 Reduction logic

The mapping from breach severity to autonomy reduction is:

- Single SLO in breach, low severity: autonomy drops one level (e.g., autonomous → limited-autonomous)
- Single SLO in breach, high severity (e.g., reversal rate 3x target): autonomy drops two levels
- Multiple SLOs in breach: autonomy drops to `advisor` regardless of prior level
- Critical SLO breach (e.g., high-confidence failure rate above 10%): autonomy drops to `observer`

Reductions are conservative by design. Recovery requires human judgment, not statistical improvement alone.

### 6.4 Why one-way

The failure mode this prevents: an agent has a bad week (say, a model update introduces regressions). Its SLOs breach and autonomy reduces appropriately. The model is rolled back. Statistics improve within hours. If autonomy elevation were automatic, the agent would be restored to full autonomy based on 24 hours of good data after a week of bad data. The same model update could happen again and again. One-way ratcheting forces humans into the loop for elevation, creating a deliberate checkpoint.

### 6.5 Bench integration

When autonomy reduces, a case is created in the Bench explaining the reduction and inviting a human operator to investigate. The case includes:

- Which SLOs breached
- The evaluation's confidence interval (so operators can see if the breach is marginal or clear)
- Recent evaluation history (context)
- The prior autonomy level and the new one

If an operator decides to elevate autonomy after investigation, they issue an `autonomy_elevation` action request from the Bench, which flows through the normal authorisation process (including dual-human approval requirements for significant elevations).

## 7. Audit Sampling

For services whose outcomes aren't automatically verifiable (classification tasks, content moderation, subjective judgments), the `audit_sampling` judgment SLO type specifies human-in-the-loop review.

### 7.1 Sampling strategy

measure maintains per-service audit queues. Sampling is stratified:

```yaml
sampling:
  overall_rate: 0.01            # 1% of decisions
  stratified:
    - segment: "high_stakes"
      rate: 0.1                 # 10% of high-stakes decisions
    - segment: "low_confidence"
      rate: 0.25                # 25% of low-confidence decisions
```

Sampled decisions are queued for human review. The queue is a separate case type in the Bench.

### 7.2 Review integration

Reviewers see the original input, the agent's decision, and its reasoning. They mark the decision as "correct," "incorrect," or "partial." These labels flow back to measure as calibration signals.

### 7.3 Backlog management

The SLO's `audit_backlog_maximum_age` target bounds how long an audit can wait. If the backlog exceeds the target, this is itself an SLO breach — the audit infrastructure is under-resourced and the sample isn't representative.

## 8. LLM-as-Judge for Outcomes

For judgment types where the outcome is textual and not numerical (e.g., "did the investigation agent correctly identify the root cause?"), measure uses LLM-as-judge:

### 8.1 Pattern

Given a decision and observable outcome, an LLM evaluator produces:

```python
class OutcomeJudgement(BaseModel):
    outcome_correct: bool
    confidence: float = Field(ge=0.0, le=1.0)
    reasoning: str
    notable_observations: list[str]
```

### 8.2 Structured output via Instructor

```python
judgement = await llm.complete(
    prompt=build_outcome_prompt(decision, observed_outcome),
    response_model=OutcomeJudgement,
    model=config.outcome_judge_model,
)
```

Instructor handles validation, retry, and partial-streaming.

### 8.3 LLM-as-judge calibration

LLM-as-judge introduces its own potential miscalibration. Its agreement with human reviewers is tracked as part of the self-calibration pipeline (§5). When agreement drops, LLM-as-judge outputs are marked degraded.

## 9. Output: Verdicts

### 9.1 judgment_slo_evaluation assessment

```json
{
  "specversion": "1.0",
  "type": "io.nthlayer.assessment.judgment_slo_evaluation.v1",
  "data": {
    "nthlayer.evaluation.slo_cid": "bafyrei...slo",
    "nthlayer.evaluation.service": "triage-agent",
    "nthlayer.evaluation.type": "reversal_rate",
    "nthlayer.evaluation.value": 0.032,
    "nthlayer.evaluation.target": 0.05,
    "nthlayer.evaluation.status": "healthy",
    "nthlayer.evaluation.confidence_interval": [0.028, 0.037],
    "nthlayer.evaluation.sample_size": 4827,
    "nthlayer.evaluation.evaluator_degraded": false
  }
}
```

### 9.2 autonomy_change verdict

```json
{
  "type": "io.nthlayer.verdict.autonomy_change.v1",
  "data": {
    "nthlayer.autonomy.agent": "triage-agent",
    "nthlayer.autonomy.previous_level": "autonomous",
    "nthlayer.autonomy.new_level": "limited-autonomous",
    "nthlayer.autonomy.direction": "reduced",
    "nthlayer.autonomy.reason": "Reversal rate SLO breach: 0.087 observed vs 0.05 target",
    "nthlayer.autonomy.breach_slo_cids": ["bafyrei...slo"],
    "nthlayer.autonomy.automatic": true
  }
}
```

### 9.3 quality_breach verdict

```json
{
  "type": "io.nthlayer.verdict.quality_breach.v1",
  "data": {
    "nthlayer.breach.slo_cid": "bafyrei...slo",
    "nthlayer.breach.service": "triage-agent",
    "nthlayer.breach.slo_type": "reversal_rate",
    "nthlayer.breach.observed_value": 0.087,
    "nthlayer.breach.target": 0.05,
    "nthlayer.breach.severity": "moderate",
    "nthlayer.breach.actions_triggered": ["create_case", "reduce_autonomy"]
  }
}
```

## 10. State and Persistence

Per the base serve-mode pattern:

- `component_state.measure` holds last cursor, calibration history, queue depths
- `agent_state` table holds current autonomy level per agent
- Audit sample queues are their own tables
- Heartbeats every 10 seconds

## 11. Failure Modes

**Self-calibration ground truth unavailable.** Evaluators continue producing outputs but mark them as "calibration unavailable." The autonomy ratchet becomes more conservative (any breach triggers reduction).

**LLM-as-judge unavailable.** Outcome evaluations for text-shaped outcomes pause. Numerical-outcome evaluations continue. Operators see degraded quality visibility.

**Audit queue saturated.** Sampling rate is capped to the review capacity. Audit-SLO breaches are surfaced.

**Store query performance degrades.** Evaluators take longer per cycle. Cycle time extends; heartbeat shows degraded state. Not a correctness issue, just a latency one.

**Recursion in self-calibration.** Hypothetically possible but prevented by the one-level rule (§5.4).

## 12. Implementation Notes

### 12.1 Library dependencies

- `nthlayer-common.llm` — LLM wrapper (see nthlayer-common spec)
- `Instructor` — structured LLM outputs
- `scipy.stats` — confidence intervals, hypothesis testing
- `numpy` — binning and aggregation
- Appropriate calibration-metric libraries (scikit-learn or similar, based on the metric in use)

### 12.2 Performance

Per cycle (60s default), for a deployment with ~20 agents × ~5 SLOs each:

- 100 evaluator invocations × ~50ms median = 5s
- Self-calibration pipeline daily: 10-30 minutes
- LLM-as-judge calls: bounded by call rate limits; budget separate from critical-path LLM use

### 12.3 Principle of statistical conservatism

Where statistical methods could produce optimistic or pessimistic readings, measure chooses pessimistic. Confidence intervals use 95% coverage by default (wider than 90%). Evaluations near thresholds are marked "marginal" rather than "healthy." Autonomy reductions are conservative — quick to reduce, slow to restore.

The reason: optimistic measurement enables the failure mode where bad agent behaviour goes undetected. Pessimistic measurement enables the failure mode where operators see more breaches than necessary. The latter is recoverable via human judgment; the former is not.

## 13. Future Work

**Adaptive sampling rates.** When audit queues are empty, sample more aggressively; when backed up, sample less. Requires careful calibration to avoid skewing the sample.

**Probe-set rotation for stability SLO.** Frozen probe sets drift from production distributions over time. Periodic rotation against labelled ground-truth sets would keep the probe aligned.

**Multi-dimensional segments.** Currently segment SLOs are one-dimensional (customer tier OR geography OR type). Multi-dimensional segment analysis (tier × geography) is more informative but computationally more expensive.

**Prompt/model-change detection.** When an agent's underlying model or prompt changes, flag subsequent measurements as "post-change" for a warm-up period. Useful for detecting regressions that appear with small delay.

## 14. References

- OpenSRM v2 §5 (judgment SLO specification)
- Instructor: https://github.com/567-labs/instructor
- nthlayer-common spec (LLM wrapper)
- nthlayer-learn spec (calibration signals, outcome resolution)
- Serve mode v2.1 (store, state, heartbeats)

## 15. Revision History

| Version | Date | Changes |
|---------|------|---------|
| 1-draft | 2026-04-19 | Initial spec |
