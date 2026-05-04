# Tiered Evaluation Design — nthlayer-measure

**Date:** 2026-03-30
**Bead:** opensrm-8o6.2
**Status:** Design approved, ready for implementation plan

## Problem

nthlayer-measure evaluates every agent output at the same depth with the same model. A documentation typo fix and a payment fraud decision get identical token spend. The COSTOPTIMISATION spec estimates 50-65% token reduction from tiered evaluation.

## Design

### Tier Classification

A `TierClassifier` sits between the router/API and the evaluator. It determines the evaluation tier for each `AgentOutput`, then routes accordingly:

```
AgentOutput → TierClassifier → minimal:  auto-approve (sampled)
                              → standard: evaluate with cheaper model
                              → deep:     evaluate with default model
                              → critical: evaluate with frontier model
```

**Four tiers:**

| Tier | Model Call | Model | Use Case |
|------|-----------|-------|----------|
| `minimal` | No (sampled %) | N/A | Docs, formatting, low-risk outputs |
| `standard` | Yes | Cheaper (e.g. Haiku) | Routine code, standard tasks |
| `deep` | Yes | Default (e.g. Sonnet) | Critical paths, complex outputs |
| `critical` | Yes | Frontier (e.g. Opus) | Cross-service, security, agent config changes |

### Tier Resolution Order

Classification follows a priority chain:

1. **Caller override** — `metadata.risk_tier` in API request (highest priority)
2. **OpenSRM manifest** — `spec.evaluation.tier` per agent/service
3. **Config default** — `tiering.default_tier` in `measure.yaml`
4. **Fallback** — `standard`

This means: the orchestrator knows its own risk context best (caller override), the operator declares policy per agent/service (manifest), and the system has a safe default.

### Minimal Tier — Auto-Approve with Sampling

Outputs classified as `minimal` skip the model entirely:

- **No model call.** Score recorded as auto-approved: `confidence: 0.0`, all dimensions set to a configurable `auto_approve_score` (default `1.0`), tagged `auto_approved: true`.
- **Random sampling.** A configurable percentage (default 5%) of auto-approved outputs are still sent through full evaluation. The sample score is stored alongside the auto-approved score for calibration comparison.
- **Verdict.** Auto-approved outputs still produce a verdict (`action: "approve"`, `confidence: 0.0`) so the audit trail is complete. Sampled outputs produce a second verdict with the actual evaluation result.

### Tier Promotion Ratchet

When sampled evaluations reveal quality issues, the system automatically tightens:

- After each calibration window (configurable, default 100 sampled evaluations), compute the **sample failure rate**: fraction of sampled auto-approvals where the model would have flagged the output (model score below `quality_threshold` on any dimension).
- If `sample_failure_rate > promotion_threshold` (configurable per agent, default 10%), **promote the agent from minimal to standard tier**.
- Promotion is a **one-way safety ratchet** — only a human can restore `minimal` tier.
- Promotion emits a verdict:
  - `subject.type: "evaluation"`, `subject.ref: agent_name`
  - `judgment.action: "escalate"`, `judgment.confidence: 1.0`
  - `judgment.reasoning: "{agent} promoted from minimal to standard tier. {n} of {total} sampled auto-approvals would have been flagged ({rate:.0%}, threshold {threshold:.0%}). Human review required to restore minimal tier."`
  - `judgment.tags: ["tier_promotion", "calibration"]`

### Standard/Deep/Critical — Model Routing

These tiers all call the model. The only difference is which model:

- Same prompt template (no prompt engineering per tier)
- Same dimensions list
- Same response parsing
- Different `model` parameter passed to `ModelEvaluator.evaluate()`

The model per tier is configured in `measure.yaml`:

```yaml
tiering:
  enabled: true
  default_tier: standard
  auto_approve_score: 1.0
  models:
    standard: "anthropic/claude-haiku-4-20250414"
    deep: "anthropic/claude-sonnet-4-20250514"
    critical: "anthropic/claude-opus-4-20250514"
  sampling:
    rate: 0.05           # 5% of minimal-tier outputs sampled
    window_size: 100     # evaluate promotion after this many samples
    quality_threshold: 0.6  # model score below this = "would have been flagged"
```

If `tiering.enabled` is `false` (default), all outputs use the existing single-model path. Tiering is fully opt-in.

### OpenSRM Manifest Extension

Per-agent evaluation policy in the OpenSRM spec:

```yaml
spec:
  evaluation:
    tier: minimal
    sampling_rate: 0.05
    promotion_threshold: 0.10
```

Fields:
- `tier` — default tier for this agent/service (`minimal`, `standard`, `deep`, `critical`)
- `sampling_rate` — override the global sampling rate for this agent (optional)
- `promotion_threshold` — override the global promotion threshold (optional)

If no `evaluation` block is present, the agent uses `tiering.default_tier` from `measure.yaml`.

### API Request Override

Callers can override the tier per-request via the existing `metadata` field:

```json
{
  "agent": "fraud-detect",
  "output": "Approved: transaction $45,000...",
  "metadata": {
    "risk_tier": "critical"
  }
}
```

The caller override always wins. This lets orchestrators escalate individual high-value decisions without changing the agent's default tier.

### QualityScore Extension

`QualityScore` gains two optional fields:

```python
tier: str | None = None           # "minimal", "standard", "deep", "critical"
auto_approved: bool = False       # True if skipped model evaluation
```

These flow through to the verdict `metadata.custom` for audit trail.

## Components

### New: `TierClassifier` (`src/nthlayer_measure/tiering/classifier.py`)

Pure transport — no model calls, no judgment.

```python
class TierClassifier:
    def __init__(self, config: TieringConfig, manifests: dict[str, ManifestEvalConfig]):
        ...

    def classify(self, output: AgentOutput, metadata: dict | None = None) -> str:
        """Returns tier: 'minimal', 'standard', 'deep', 'critical'."""

    def should_sample(self, tier: str, agent_name: str) -> bool:
        """Returns True if this minimal-tier output should be sampled."""
```

Resolution: `metadata.risk_tier` → manifest tier → config default → `"standard"`.

### New: `TierPromotionChecker` (`src/nthlayer_measure/tiering/promotion.py`)

Runs after calibration sampling. Checks sample failure rates against thresholds. Emits promotion verdicts.

```python
class TierPromotionChecker:
    def __init__(self, store: ScoreStore, verdict_store, config: TieringConfig, manifests: dict):
        ...

    async def check_agent(self, agent_name: str) -> TierPromotion | None:
        """Check if agent should be promoted from minimal to standard."""
```

One-way ratchet: can promote (minimal → standard), never demote. Demoting requires `nthlayer-measure tiering restore <agent> minimal --approver <human>` CLI command.

### New: `TieringConfig` (`config.py` extension)

```python
@dataclass
class TieringConfig:
    enabled: bool = False
    default_tier: str = "standard"
    auto_approve_score: float = 1.0
    models: dict[str, str] = field(default_factory=lambda: {
        "standard": "anthropic/claude-haiku-4-20250414",
        "deep": "anthropic/claude-sonnet-4-20250514",
        "critical": "anthropic/claude-opus-4-20250514",
    })
    sampling_rate: float = 0.05
    sampling_window_size: int = 100
    quality_threshold: float = 0.6
    promotion_threshold: float = 0.10
```

### Modified: `PipelineRouter.run()`

Before `evaluator.evaluate()`, call `classifier.classify()`. If minimal and not sampled, create auto-approved score. Otherwise, select model from tier and evaluate.

### Modified: `EvaluationQueue._worker()`

Same insertion point. Classifier runs before evaluator.

### Modified: `evaluate_sync` endpoint

Same insertion point. If minimal and not sampled, return fast (no model call, ~0ms instead of ~2-5s).

### Modified: `ModelEvaluator`

Add optional `model` parameter override to `evaluate()`:

```python
async def evaluate(self, output: AgentOutput, dimensions: list[str], model: str | None = None) -> QualityScore:
```

When `model` is passed, use it instead of `self._model`. This lets the caller (router/queue/API) specify the tier-appropriate model without creating multiple evaluator instances.

### New CLI: `nthlayer-measure tiering`

```bash
nthlayer-measure tiering show <agent_name>     # show current tier + promotion status
nthlayer-measure tiering restore <agent> <tier> --approver <human>  # restore tier (safety ratchet)
```

## What Doesn't Change

- **Prompt template** — one prompt for all tiers, same dimensions
- **Verdict creation** — all tiers produce verdicts (auto-approved verdicts have `confidence: 0.0`)
- **Self-calibration** — existing `JudgmentSLOChecker` continues to work. Sampled auto-approvals feed into it naturally.
- **Governance** — `ErrorBudgetGovernance` is independent of evaluation tiering
- **API contract** — no breaking changes to the evaluate endpoints. `risk_tier` is in `metadata` (optional).
- **Store schema** — `QualityScore` fields are additive (optional, defaults to None/False)

## Verification

1. `tiering.enabled: false` → identical behavior to current system (no tiering)
2. Minimal tier with sampling → auto-approved outputs recorded, 5% sampled, sampled scores stored
3. Promotion ratchet → agent promoted when sample failures exceed threshold, verdict emitted
4. Model routing → standard uses Haiku, deep uses Sonnet, critical uses Opus
5. Caller override → `metadata.risk_tier: "critical"` overrides manifest default
6. All existing tests pass unchanged (tiering disabled by default)
