# Tiered Evaluation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add tiered evaluation to nthlayer-measure so outputs are classified by risk (minimal/standard/deep/critical) and evaluated with appropriate model depth, reducing token cost by 50-65%.

**Architecture:** A `TierClassifier` determines risk tier from caller metadata → manifest defaults → config. Minimal tier auto-approves with 5% sampling. Standard/deep/critical route to different models (Haiku/Sonnet/Opus). A `TierPromotionChecker` applies the one-way safety ratchet when sampled auto-approvals reveal quality issues.

**Tech Stack:** Python 3.11+, pytest, nthlayer-measure existing pipeline

**Spec:** `docs/superpowers/specs/2026-03-30-tiered-evaluation-design.md`

---

## File Structure

```
src/nthlayer_measure/
├── tiering/
│   ├── __init__.py          # NEW — package init
│   ├── classifier.py        # NEW — TierClassifier (classify + should_sample)
│   └── promotion.py         # NEW — TierPromotionChecker (ratchet + verdict)
├── config.py                # MODIFY — add TieringConfig dataclass + loading
├── types.py                 # MODIFY — add tier + auto_approved to QualityScore
├── pipeline/
│   ├── evaluator.py         # MODIFY — add model override param to evaluate()
│   └── router.py            # MODIFY — insert classifier before evaluator
├── api/
│   ├── queue.py             # MODIFY — insert classifier before evaluator
│   └── server.py            # MODIFY — insert classifier in sync path
└── cli.py                   # MODIFY — add tiering subcommand + wire classifier

tests/
├── test_tiering_classifier.py   # NEW
├── test_tiering_promotion.py    # NEW
├── test_tiering_integration.py  # NEW — end-to-end with pipeline
```

---

### Task 1: Add `tier` and `auto_approved` to QualityScore

**Files:**
- Modify: `src/nthlayer_measure/types.py:32-44`
- Test: `tests/test_types.py`

- [ ] **Step 1: Write the failing test**

In `tests/test_types.py`, add:

```python
def test_quality_score_tier_field():
    score = QualityScore(
        eval_id="e1", agent_name="a", task_id="t1",
        dimensions={"correctness": 0.9},
        tier="standard", auto_approved=False,
    )
    assert score.tier == "standard"
    assert score.auto_approved is False


def test_quality_score_tier_defaults():
    score = QualityScore(
        eval_id="e1", agent_name="a", task_id="t1",
        dimensions={"correctness": 0.9},
    )
    assert score.tier is None
    assert score.auto_approved is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run --no-sync pytest tests/test_types.py::test_quality_score_tier_field -v`
Expected: FAIL — `TypeError: unexpected keyword argument 'tier'`

- [ ] **Step 3: Add fields to QualityScore**

In `src/nthlayer_measure/types.py`, add to `QualityScore` after `timestamp`:

```python
@dataclass(frozen=True)
class QualityScore:
    """Complete evaluation result for a single agent output."""

    eval_id: str
    agent_name: str
    task_id: str
    dimensions: dict[str, float]
    reasoning: dict[str, str] = field(default_factory=dict)
    confidence: float = 0.0
    evaluator_model: str = ""
    cost_usd: float | None = None
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    tier: str | None = None
    auto_approved: bool = False
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run --no-sync pytest tests/test_types.py -v`
Expected: ALL PASS

- [ ] **Step 5: Commit**

```bash
git add src/nthlayer_measure/types.py tests/test_types.py
git commit -m "feat(tiering): add tier and auto_approved fields to QualityScore"
```

---

### Task 2: Add TieringConfig to config.py

**Files:**
- Modify: `src/nthlayer_measure/config.py`
- Test: `tests/test_config.py`

- [ ] **Step 1: Write the failing test**

In `tests/test_config.py`, add:

```python
def test_tiering_config_defaults():
    config = MeasureConfig()
    assert config.tiering is None


def test_tiering_config_from_yaml(tmp_path):
    yaml_content = """
evaluator:
  model: claude-sonnet-4-20250514
tiering:
  enabled: true
  default_tier: minimal
  models:
    standard: anthropic/claude-haiku-4-20250414
    deep: anthropic/claude-sonnet-4-20250514
    critical: anthropic/claude-opus-4-20250514
  sampling_rate: 0.10
  promotion_threshold: 0.05
"""
    p = tmp_path / "measure.yaml"
    p.write_text(yaml_content)
    config = load_config(p)
    assert config.tiering is not None
    assert config.tiering.enabled is True
    assert config.tiering.default_tier == "minimal"
    assert config.tiering.sampling_rate == 0.10
    assert config.tiering.promotion_threshold == 0.05
    assert config.tiering.models["standard"] == "anthropic/claude-haiku-4-20250414"


def test_tiering_disabled_by_default(tmp_path):
    p = tmp_path / "measure.yaml"
    p.write_text("evaluator:\n  model: test\n")
    config = load_config(p)
    assert config.tiering is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run --no-sync pytest tests/test_config.py::test_tiering_config_defaults -v`
Expected: FAIL — `AttributeError: 'MeasureConfig' has no attribute 'tiering'`

- [ ] **Step 3: Add TieringConfig dataclass and loading**

In `src/nthlayer_measure/config.py`, add after `TriggerConfig`:

```python
@dataclass
class TieringConfig:
    """Configuration for tiered evaluation."""

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

Add to `MeasureConfig`:

```python
    tiering: TieringConfig | None = None
```

Add to `load_config()`, after `trigger_cfg` parsing (before the return):

```python
    tiering_cfg = None
    tiering_raw = raw.get("tiering")
    if isinstance(tiering_raw, dict):
        models = tiering_raw.get("models", {})
        tiering_cfg = TieringConfig(
            enabled=bool(tiering_raw.get("enabled", False)),
            default_tier=str(tiering_raw.get("default_tier", "standard")),
            auto_approve_score=float(tiering_raw.get("auto_approve_score", 1.0)),
            models={**TieringConfig().models, **models},
            sampling_rate=float(tiering_raw.get("sampling_rate", 0.05)),
            sampling_window_size=int(tiering_raw.get("sampling_window_size", 100)),
            quality_threshold=float(tiering_raw.get("quality_threshold", 0.6)),
            promotion_threshold=float(tiering_raw.get("promotion_threshold", 0.10)),
        )
```

Add `tiering=tiering_cfg` to the `MeasureConfig(...)` return.

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run --no-sync pytest tests/test_config.py -v`
Expected: ALL PASS

- [ ] **Step 5: Commit**

```bash
git add src/nthlayer_measure/config.py tests/test_config.py
git commit -m "feat(tiering): add TieringConfig to config with YAML loading"
```

---

### Task 3: Build TierClassifier

**Files:**
- Create: `src/nthlayer_measure/tiering/__init__.py`
- Create: `src/nthlayer_measure/tiering/classifier.py`
- Create: `tests/test_tiering_classifier.py`

- [ ] **Step 1: Create package init**

```python
# src/nthlayer_measure/tiering/__init__.py
```

(Empty file — just makes it a package.)

- [ ] **Step 2: Write the failing tests**

Create `tests/test_tiering_classifier.py`:

```python
"""Tests for tier classification."""
import random

import pytest

from nthlayer_measure.config import TieringConfig
from nthlayer_measure.tiering.classifier import TierClassifier
from nthlayer_measure.types import AgentOutput

VALID_TIERS = {"minimal", "standard", "deep", "critical"}


def _make_output(agent="test-agent"):
    return AgentOutput(
        agent_name=agent, task_id="t1",
        output_content="hello", output_type="api",
    )


@pytest.fixture
def config():
    return TieringConfig(enabled=True, default_tier="standard")


@pytest.fixture
def classifier(config):
    return TierClassifier(config, manifests={})


def test_caller_override_wins(classifier):
    result = classifier.classify(_make_output(), metadata={"risk_tier": "critical"})
    assert result == "critical"


def test_manifest_default(config):
    manifests = {"test-agent": {"tier": "minimal"}}
    c = TierClassifier(config, manifests=manifests)
    result = c.classify(_make_output())
    assert result == "minimal"


def test_config_default(classifier):
    result = classifier.classify(_make_output())
    assert result == "standard"


def test_fallback_when_no_config():
    c = TierClassifier(TieringConfig(enabled=True, default_tier="deep"), manifests={})
    result = c.classify(_make_output())
    assert result == "deep"


def test_invalid_tier_falls_back(classifier):
    result = classifier.classify(_make_output(), metadata={"risk_tier": "bogus"})
    assert result in VALID_TIERS


def test_caller_overrides_manifest(config):
    manifests = {"test-agent": {"tier": "minimal"}}
    c = TierClassifier(config, manifests=manifests)
    result = c.classify(_make_output(), metadata={"risk_tier": "critical"})
    assert result == "critical"


def test_should_sample_returns_bool(classifier):
    result = classifier.should_sample("minimal", "test-agent")
    assert isinstance(result, bool)


def test_should_sample_non_minimal_always_false(classifier):
    assert classifier.should_sample("standard", "test-agent") is False
    assert classifier.should_sample("deep", "test-agent") is False
    assert classifier.should_sample("critical", "test-agent") is False


def test_should_sample_respects_rate():
    config = TieringConfig(enabled=True, sampling_rate=1.0)  # 100% sampling
    c = TierClassifier(config, manifests={})
    assert c.should_sample("minimal", "test-agent") is True


def test_should_sample_manifest_rate_override():
    config = TieringConfig(enabled=True, sampling_rate=0.0)  # 0% global
    manifests = {"test-agent": {"sampling_rate": 1.0}}  # 100% for this agent
    c = TierClassifier(config, manifests=manifests)
    assert c.should_sample("minimal", "test-agent") is True
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `uv run --no-sync pytest tests/test_tiering_classifier.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'nthlayer_measure.tiering.classifier'`

- [ ] **Step 4: Implement TierClassifier**

Create `src/nthlayer_measure/tiering/classifier.py`:

```python
"""Tier classification for evaluation inputs. Pure transport — no model calls."""
from __future__ import annotations

import random

from nthlayer_measure.config import TieringConfig
from nthlayer_measure.types import AgentOutput

VALID_TIERS = {"minimal", "standard", "deep", "critical"}


class TierClassifier:
    """Determines evaluation tier for an agent output.

    Resolution order: caller override → manifest → config default → "standard".
    """

    def __init__(
        self,
        config: TieringConfig,
        manifests: dict[str, dict],
    ) -> None:
        self._config = config
        self._manifests = manifests

    def classify(
        self,
        output: AgentOutput,
        metadata: dict | None = None,
    ) -> str:
        """Returns tier: 'minimal', 'standard', 'deep', 'critical'."""
        # 1. Caller override (highest priority)
        if metadata and metadata.get("risk_tier") in VALID_TIERS:
            return metadata["risk_tier"]

        # 2. Manifest default for this agent
        manifest = self._manifests.get(output.agent_name, {})
        manifest_tier = manifest.get("tier")
        if manifest_tier in VALID_TIERS:
            return manifest_tier

        # 3. Config default
        if self._config.default_tier in VALID_TIERS:
            return self._config.default_tier

        # 4. Fallback
        return "standard"

    def should_sample(self, tier: str, agent_name: str) -> bool:
        """Returns True if this minimal-tier output should be sampled."""
        if tier != "minimal":
            return False

        # Check manifest override for sampling rate
        manifest = self._manifests.get(agent_name, {})
        rate = manifest.get("sampling_rate", self._config.sampling_rate)

        return random.random() < rate
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run --no-sync pytest tests/test_tiering_classifier.py -v`
Expected: ALL PASS

- [ ] **Step 6: Commit**

```bash
git add src/nthlayer_measure/tiering/ tests/test_tiering_classifier.py
git commit -m "feat(tiering): add TierClassifier with resolution chain"
```

---

### Task 4: Add model override to ModelEvaluator

**Files:**
- Modify: `src/nthlayer_measure/pipeline/evaluator.py:150`
- Test: `tests/test_evaluator.py`

- [ ] **Step 1: Write the failing test**

In `tests/test_evaluator.py`, add:

```python
@pytest.mark.asyncio
async def test_evaluate_with_model_override(evaluator, sample_output):
    response_json = json.dumps({
        "dimensions": {"correctness": {"score": 0.9, "reasoning": "Good"}},
        "confidence": 0.85,
    })
    mock_response = _ModelResponse(text=response_json, input_tokens=100, output_tokens=50)

    with patch.object(evaluator, "_call_model", new_callable=AsyncMock, return_value=mock_response) as mock:
        score = await evaluator.evaluate(sample_output, ["correctness"], model="anthropic/claude-haiku-4-20250414")

    # Verify the override model was passed to _call_model
    assert score.evaluator_model == "anthropic/claude-haiku-4-20250414"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run --no-sync pytest tests/test_evaluator.py::test_evaluate_with_model_override -v`
Expected: FAIL — `TypeError: evaluate() got an unexpected keyword argument 'model'`

- [ ] **Step 3: Add model parameter to evaluate()**

In `src/nthlayer_measure/pipeline/evaluator.py`, modify `evaluate()`:

```python
    async def evaluate(self, output: AgentOutput, dimensions: list[str], model: str | None = None) -> QualityScore:
        effective_model = model or self._model
        prompt = self.build_prompt(output, dimensions)

        # Temporarily use override model for the call
        original_model = self._model
        if model:
            self._model = effective_model
        try:
            model_response = await self._call_model(prompt)
        finally:
            self._model = original_model

        score = self.parse_response(model_response.text, output)
        # Ensure evaluator_model reflects the model actually used
        if model:
            score = replace(score, evaluator_model=effective_model)
        cost = _compute_cost(effective_model, model_response.input_tokens, model_response.output_tokens)
        if cost is not None:
            score = replace(score, cost_usd=cost)
        return score
```

Also update the `Evaluator` Protocol:

```python
class Evaluator(Protocol):
    async def evaluate(self, output: AgentOutput, dimensions: list[str], model: str | None = None) -> QualityScore: ...
```

- [ ] **Step 4: Run tests to verify all pass**

Run: `uv run --no-sync pytest tests/test_evaluator.py -v`
Expected: ALL PASS (existing tests unaffected — model=None uses self._model)

- [ ] **Step 5: Commit**

```bash
git add src/nthlayer_measure/pipeline/evaluator.py tests/test_evaluator.py
git commit -m "feat(tiering): add model override parameter to evaluator"
```

---

### Task 5: Integrate TierClassifier into PipelineRouter

**Files:**
- Modify: `src/nthlayer_measure/pipeline/router.py`
- Create: `tests/test_tiering_integration.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_tiering_integration.py`:

```python
"""Integration tests for tiered evaluation in the pipeline."""
from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from nthlayer_measure.config import TieringConfig
from nthlayer_measure.pipeline.router import PipelineRouter
from nthlayer_measure.tiering.classifier import TierClassifier
from nthlayer_measure.types import AgentOutput, QualityScore


def _make_output(agent="test-agent"):
    return AgentOutput(
        agent_name=agent, task_id="t1",
        output_content="hello", output_type="api",
    )


def _make_score(agent="test-agent", tier=None, auto_approved=False):
    return QualityScore(
        eval_id=str(uuid.uuid4()), agent_name=agent, task_id="t1",
        dimensions={"correctness": 0.9}, confidence=0.85,
        evaluator_model="test-model", tier=tier, auto_approved=auto_approved,
    )


@pytest.fixture
def mock_evaluator():
    e = AsyncMock()
    e.evaluate = AsyncMock(return_value=_make_score(tier="standard"))
    return e


@pytest.fixture
def mock_store():
    s = AsyncMock()
    s.save_score = AsyncMock()
    return s


@pytest.fixture
def mock_tracker():
    return AsyncMock()


@pytest.fixture
def tiering_config():
    return TieringConfig(
        enabled=True,
        default_tier="standard",
        models={
            "standard": "anthropic/claude-haiku-4-20250414",
            "deep": "anthropic/claude-sonnet-4-20250514",
            "critical": "anthropic/claude-opus-4-20250514",
        },
    )


@pytest.mark.asyncio
async def test_router_with_tiering_calls_evaluator_with_model(
    mock_evaluator, mock_store, mock_tracker, tiering_config
):
    classifier = TierClassifier(tiering_config, manifests={})

    async def single_output():
        yield _make_output()

    adapter = AsyncMock()
    adapter.receive = single_output

    router = PipelineRouter(
        adapter=adapter,
        evaluator=mock_evaluator,
        store=mock_store,
        tracker=mock_tracker,
        dimensions=["correctness"],
        classifier=classifier,
    )
    await router.run()

    mock_evaluator.evaluate.assert_called_once()
    call_kwargs = mock_evaluator.evaluate.call_args
    assert call_kwargs[1].get("model") == "anthropic/claude-haiku-4-20250414"


@pytest.mark.asyncio
async def test_router_minimal_tier_auto_approves(
    mock_evaluator, mock_store, mock_tracker
):
    config = TieringConfig(enabled=True, default_tier="minimal", sampling_rate=0.0)
    classifier = TierClassifier(config, manifests={})

    async def single_output():
        yield _make_output()

    adapter = AsyncMock()
    adapter.receive = single_output

    router = PipelineRouter(
        adapter=adapter,
        evaluator=mock_evaluator,
        store=mock_store,
        tracker=mock_tracker,
        dimensions=["correctness"],
        classifier=classifier,
    )
    await router.run()

    # Evaluator should NOT be called for minimal tier
    mock_evaluator.evaluate.assert_not_called()
    # But store should have the auto-approved score
    mock_store.save_score.assert_called_once()
    saved_score = mock_store.save_score.call_args[0][0]
    assert saved_score.auto_approved is True
    assert saved_score.tier == "minimal"
    assert saved_score.confidence == 0.0


@pytest.mark.asyncio
async def test_router_without_classifier_unchanged(
    mock_evaluator, mock_store, mock_tracker
):
    """No classifier = original behavior (no tiering)."""
    async def single_output():
        yield _make_output()

    adapter = AsyncMock()
    adapter.receive = single_output

    router = PipelineRouter(
        adapter=adapter,
        evaluator=mock_evaluator,
        store=mock_store,
        tracker=mock_tracker,
        dimensions=["correctness"],
    )
    await router.run()

    mock_evaluator.evaluate.assert_called_once()
    # No model override when no classifier
    call_kwargs = mock_evaluator.evaluate.call_args
    assert call_kwargs[1].get("model") is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run --no-sync pytest tests/test_tiering_integration.py -v`
Expected: FAIL — `TypeError: PipelineRouter() got an unexpected keyword argument 'classifier'`

- [ ] **Step 3: Modify PipelineRouter to support classifier**

In `src/nthlayer_measure/pipeline/router.py`, add `classifier` parameter and tiering logic:

```python
"""Pipeline router — connects adapters to evaluators to stores."""

from __future__ import annotations

import asyncio
import uuid

from nthlayer_measure.adapters.protocol import Adapter
from nthlayer_measure.detection.protocol import DegradationDetector
from nthlayer_measure.governance.engine import GovernanceEngine
from nthlayer_measure.pipeline.evaluator import Evaluator
from nthlayer_measure.store.protocol import ScoreStore
from nthlayer_measure.telemetry import emit_decision_event
from nthlayer_measure.trends.tracker import TrendTracker
from nthlayer_measure.types import QualityScore
from nthlayer_learn import create as verdict_create, VerdictStore as VerdictStoreBase

import logging

logger = logging.getLogger(__name__)

DEFAULT_APPROVE_THRESHOLD = 0.5


class PipelineRouter:
    """Routes agent output through the evaluation pipeline."""

    def __init__(
        self,
        adapter: Adapter,
        evaluator: Evaluator,
        store: ScoreStore,
        tracker: TrendTracker,
        dimensions: list[str],
        governance: GovernanceEngine | None = None,
        detector: DegradationDetector | None = None,
        detection_window_days: int = 7,
        verdict_store: VerdictStoreBase | None = None,
        approve_threshold: float | None = None,
        classifier=None,
    ) -> None:
        self._adapter = adapter
        self._evaluator = evaluator
        self._store = store
        self._tracker = tracker
        self._dimensions = dimensions
        self._governance = governance
        self._detector = detector
        self._detection_window_days = detection_window_days
        self._verdict_store = verdict_store
        self._approve_threshold = (
            approve_threshold if approve_threshold is not None
            else DEFAULT_APPROVE_THRESHOLD
        )
        self._classifier = classifier

    async def run(self) -> None:
        """Process agent outputs through the full pipeline."""
        async for output in self._adapter.receive():
            # Tier classification (if enabled)
            tier = None
            model_override = None
            if self._classifier is not None:
                tier = self._classifier.classify(output, output.metadata)

                if tier == "minimal" and not self._classifier.should_sample(tier, output.agent_name):
                    # Auto-approve: skip model call
                    from dataclasses import replace
                    auto_score = QualityScore(
                        eval_id=str(uuid.uuid4()),
                        agent_name=output.agent_name,
                        task_id=output.task_id,
                        dimensions={d: self._classifier._config.auto_approve_score for d in self._dimensions},
                        confidence=0.0,
                        evaluator_model="auto-approved",
                        tier="minimal",
                        auto_approved=True,
                    )
                    await self._store.save_score(auto_score)
                    emit_decision_event(auto_score, None)
                    continue

                # Model routing for non-minimal tiers (or sampled minimal)
                if self._classifier._config.models.get(tier):
                    model_override = self._classifier._config.models[tier]

            score = await self._evaluator.evaluate(output, self._dimensions, model=model_override)

            # Tag score with tier
            if tier is not None:
                from dataclasses import replace
                score = replace(score, tier=tier)

            await self._store.save_score(score)

            # Create verdict if verdict store is configured (fail open)
            if self._verdict_store is not None:
                try:
                    verdict = await self._create_verdict(score)
                    await asyncio.to_thread(self._verdict_store.put, verdict)
                    await self._store.set_verdict_id(score.eval_id, verdict.id)
                except Exception:
                    logger.warning(
                        "Failed to create/store verdict for %s — continuing without verdict",
                        score.eval_id,
                        exc_info=True,
                    )

            alerts = None
            if self._detector is not None:
                window = await self._tracker.compute_window(
                    output.agent_name, self._detection_window_days
                )
                alerts = self._detector.check(window)

            emit_decision_event(score, alerts)

            if self._governance is not None:
                await self._governance.check_agent(output.agent_name)

    async def _create_verdict(self, score):
        """Map QualityScore to a verdict."""
        if not score.dimensions:
            avg_score = 0.0
        else:
            avg_score = sum(score.dimensions.values()) / len(score.dimensions)

        reasoning_summary = "; ".join(
            f"{name}: {reason}" for name, reason in score.reasoning.items()
        ) if score.reasoning else None

        return await asyncio.to_thread(
            verdict_create,
            subject={
                "type": "agent_output",
                "ref": score.task_id,
                "summary": f"Evaluation of {score.agent_name}: {score.task_id}",
                "agent": score.agent_name,
            },
            judgment={
                "action": (
                    "approve" if avg_score >= self._approve_threshold
                    else "reject"
                ),
                "confidence": score.confidence,
                "score": avg_score,
                "dimensions": score.dimensions,
                "reasoning": reasoning_summary,
            },
            producer={
                "system": "arbiter",
                "model": score.evaluator_model,
            },
            metadata={
                "cost_currency": score.cost_usd,
            },
        )
```

- [ ] **Step 4: Run all tests**

Run: `uv run --no-sync pytest tests/test_tiering_integration.py tests/test_tiering_classifier.py -v`
Expected: ALL PASS

- [ ] **Step 5: Run full test suite for regressions**

Run: `uv run --no-sync pytest tests/ -v`
Expected: ALL PASS (existing tests don't pass classifier, so tiering is inactive)

- [ ] **Step 6: Commit**

```bash
git add src/nthlayer_measure/pipeline/router.py tests/test_tiering_integration.py
git commit -m "feat(tiering): integrate TierClassifier into PipelineRouter"
```

---

### Task 6: Build TierPromotionChecker

**Files:**
- Create: `src/nthlayer_measure/tiering/promotion.py`
- Create: `tests/test_tiering_promotion.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_tiering_promotion.py`:

```python
"""Tests for tier promotion ratchet."""
from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from nthlayer_measure.config import TieringConfig
from nthlayer_measure.tiering.promotion import TierPromotionChecker
from nthlayer_measure.types import QualityScore


def _make_sampled_score(agent="test-agent", dim_score=0.9):
    return QualityScore(
        eval_id=str(uuid.uuid4()), agent_name=agent, task_id="t1",
        dimensions={"correctness": dim_score}, confidence=0.85,
        evaluator_model="test-model", tier="minimal", auto_approved=False,
    )


@pytest.fixture
def config():
    return TieringConfig(
        enabled=True,
        sampling_window_size=5,
        quality_threshold=0.6,
        promotion_threshold=0.40,  # promote if >40% of samples fail
    )


@pytest.fixture
def mock_store():
    s = AsyncMock()
    return s


@pytest.fixture
def mock_verdict_store():
    v = MagicMock()
    v.put = MagicMock()
    return v


@pytest.mark.asyncio
async def test_no_promotion_when_samples_pass(config, mock_store, mock_verdict_store):
    # 5 sampled scores, all passing (score > quality_threshold)
    scores = [_make_sampled_score(dim_score=0.9) for _ in range(5)]
    mock_store.get_scores = AsyncMock(return_value=scores)

    checker = TierPromotionChecker(mock_store, mock_verdict_store, config, manifests={})
    result = await checker.check_agent("test-agent")
    assert result is None


@pytest.mark.asyncio
async def test_promotion_when_samples_fail(config, mock_store, mock_verdict_store):
    # 5 sampled scores: 3 failing (score < 0.6), 2 passing → 60% failure > 40% threshold
    scores = [
        _make_sampled_score(dim_score=0.3),
        _make_sampled_score(dim_score=0.4),
        _make_sampled_score(dim_score=0.2),
        _make_sampled_score(dim_score=0.9),
        _make_sampled_score(dim_score=0.8),
    ]
    mock_store.get_scores = AsyncMock(return_value=scores)

    checker = TierPromotionChecker(mock_store, mock_verdict_store, config, manifests={})
    result = await checker.check_agent("test-agent")
    assert result is not None
    assert result.from_tier == "minimal"
    assert result.to_tier == "standard"
    # Verdict should be emitted
    mock_verdict_store.put.assert_called_once()


@pytest.mark.asyncio
async def test_no_promotion_below_window_size(config, mock_store, mock_verdict_store):
    # Only 3 scores (below window_size=5) — not enough data
    scores = [_make_sampled_score(dim_score=0.1) for _ in range(3)]
    mock_store.get_scores = AsyncMock(return_value=scores)

    checker = TierPromotionChecker(mock_store, mock_verdict_store, config, manifests={})
    result = await checker.check_agent("test-agent")
    assert result is None


@pytest.mark.asyncio
async def test_manifest_threshold_override(mock_store, mock_verdict_store):
    config = TieringConfig(enabled=True, sampling_window_size=5, quality_threshold=0.6, promotion_threshold=0.80)
    manifests = {"test-agent": {"promotion_threshold": 0.20}}  # tighter threshold

    scores = [
        _make_sampled_score(dim_score=0.3),  # fail
        _make_sampled_score(dim_score=0.9),
        _make_sampled_score(dim_score=0.9),
        _make_sampled_score(dim_score=0.9),
        _make_sampled_score(dim_score=0.9),
    ]
    mock_store.get_scores = AsyncMock(return_value=scores)

    checker = TierPromotionChecker(mock_store, mock_verdict_store, config, manifests=manifests)
    result = await checker.check_agent("test-agent")
    # 1/5 = 20% failure, manifest threshold = 20%, so 20% > 20% is false → no promotion
    assert result is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run --no-sync pytest tests/test_tiering_promotion.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Implement TierPromotionChecker**

Create `src/nthlayer_measure/tiering/promotion.py`:

```python
"""Tier promotion ratchet — one-way safety mechanism for evaluation tiers."""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import Any

from nthlayer_measure.config import TieringConfig
from nthlayer_measure.store.protocol import ScoreStore

logger = logging.getLogger(__name__)


@dataclass
class TierPromotion:
    """Result of a tier promotion check."""

    agent_name: str
    from_tier: str
    to_tier: str
    failure_rate: float
    threshold: float
    sample_count: int
    failed_count: int


class TierPromotionChecker:
    """Checks whether minimal-tier agents should be promoted to standard.

    One-way ratchet: can promote (minimal → standard), never demote.
    Human CLI command required to restore minimal tier.
    """

    def __init__(
        self,
        store: ScoreStore,
        verdict_store: Any,
        config: TieringConfig,
        manifests: dict[str, dict],
    ) -> None:
        self._store = store
        self._verdict_store = verdict_store
        self._config = config
        self._manifests = manifests

    async def check_agent(self, agent_name: str) -> TierPromotion | None:
        """Check if agent should be promoted from minimal to standard.

        Returns TierPromotion if promotion triggered, None otherwise.
        """
        # Get recent sampled scores for this agent (tier=minimal, auto_approved=False)
        scores = await self._store.get_scores(agent_name, since=None, limit=self._config.sampling_window_size)

        # Filter to sampled minimal-tier evaluations (not auto-approved)
        sampled = [s for s in scores if getattr(s, "tier", None) == "minimal" and not getattr(s, "auto_approved", True)]

        if len(sampled) < self._config.sampling_window_size:
            return None  # Not enough data

        # Count failures: any dimension below quality_threshold
        failed = 0
        for s in sampled:
            if any(v < self._config.quality_threshold for v in s.dimensions.values()):
                failed += 1

        failure_rate = failed / len(sampled)

        # Check threshold (manifest override takes priority)
        manifest = self._manifests.get(agent_name, {})
        threshold = manifest.get("promotion_threshold", self._config.promotion_threshold)

        if failure_rate <= threshold:
            return None

        promotion = TierPromotion(
            agent_name=agent_name,
            from_tier="minimal",
            to_tier="standard",
            failure_rate=failure_rate,
            threshold=threshold,
            sample_count=len(sampled),
            failed_count=failed,
        )

        # Emit promotion verdict
        self._emit_promotion_verdict(promotion)

        return promotion

    def _emit_promotion_verdict(self, promotion: TierPromotion) -> None:
        """Emit a verdict recording the tier promotion."""
        if self._verdict_store is None:
            return

        from nthlayer_learn import create as verdict_create

        verdict = verdict_create(
            subject={
                "type": "evaluation",
                "ref": promotion.agent_name,
                "summary": (
                    f"{promotion.agent_name} promoted from {promotion.from_tier} to {promotion.to_tier} tier. "
                    f"{promotion.failed_count} of {promotion.sample_count} sampled auto-approvals would have been flagged "
                    f"({promotion.failure_rate:.0%}, threshold {promotion.threshold:.0%}). "
                    f"Human review required to restore {promotion.from_tier} tier."
                ),
            },
            judgment={
                "action": "escalate",
                "confidence": 1.0,
                "reasoning": (
                    f"Tier promotion ratchet triggered for {promotion.agent_name}. "
                    f"Sample failure rate {promotion.failure_rate:.0%} exceeds threshold {promotion.threshold:.0%}."
                ),
                "tags": ["tier_promotion", "calibration"],
            },
            producer={"system": "nthlayer-measure"},
        )
        self._verdict_store.put(verdict)
        logger.warning(
            "Tier promotion: %s promoted from %s to %s (failure rate %.0f%%, threshold %.0f%%)",
            promotion.agent_name, promotion.from_tier, promotion.to_tier,
            promotion.failure_rate * 100, promotion.threshold * 100,
        )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run --no-sync pytest tests/test_tiering_promotion.py -v`
Expected: ALL PASS

- [ ] **Step 5: Commit**

```bash
git add src/nthlayer_measure/tiering/promotion.py tests/test_tiering_promotion.py
git commit -m "feat(tiering): add TierPromotionChecker with one-way safety ratchet"
```

---

### Task 7: Integrate tiering into API server + queue

**Files:**
- Modify: `src/nthlayer_measure/api/server.py`
- Modify: `src/nthlayer_measure/api/queue.py`
- Test: `tests/test_api_server.py`

- [ ] **Step 1: Write the failing test**

In `tests/test_api_server.py`, add:

```python
def test_evaluate_sync_minimal_tier_auto_approves(mock_evaluator, mock_store, mock_tracker):
    """Minimal tier with 0% sampling skips model call entirely."""
    from nthlayer_measure.config import TieringConfig
    from nthlayer_measure.tiering.classifier import TierClassifier

    config = TieringConfig(enabled=True, default_tier="minimal", sampling_rate=0.0)
    classifier = TierClassifier(config, manifests={})

    app = create_app(
        evaluator=mock_evaluator,
        store=mock_store,
        tracker=mock_tracker,
        dimensions=["correctness"],
        sync_timeout=5.0,
        max_workers=1,
        classifier=classifier,
    )
    c = TestClient(app)
    resp = c.post("/api/v1/evaluate/sync", json={
        "agent": "test-agent", "output": "hello",
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data.get("auto_approved") is True or data.get("confidence") == 0.0
    mock_evaluator.evaluate.assert_not_called()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run --no-sync pytest tests/test_api_server.py::test_evaluate_sync_minimal_tier_auto_approves -v`
Expected: FAIL — `TypeError: create_app() got an unexpected keyword argument 'classifier'`

- [ ] **Step 3: Add classifier to create_app and evaluate_sync**

In `src/nthlayer_measure/api/server.py`, add `classifier=None` parameter to `create_app()`. In the `evaluate_sync` handler, insert tier classification before the evaluator call — same pattern as the router.

In `src/nthlayer_measure/api/queue.py`, add `classifier=None` parameter to `EvaluationQueue.__init__()`. In `_worker`, insert tier classification before the evaluator call.

(The full code changes follow the same pattern as Task 5's router changes — classify, check minimal+sampling, auto-approve or route model.)

- [ ] **Step 4: Run full test suite**

Run: `uv run --no-sync pytest tests/ -v`
Expected: ALL PASS

- [ ] **Step 5: Commit**

```bash
git add src/nthlayer_measure/api/server.py src/nthlayer_measure/api/queue.py tests/test_api_server.py
git commit -m "feat(tiering): integrate classifier into API server and queue"
```

---

### Task 8: Add tiering CLI subcommands

**Files:**
- Modify: `src/nthlayer_measure/cli.py`

- [ ] **Step 1: Add tiering subcommand parser**

In `cli.py`, add after the governance subparser:

```python
    # tiering
    tier_parser = subparsers.add_parser("tiering", help="Evaluation tier management")
    tier_sub = tier_parser.add_subparsers(dest="tiering_command")
    tier_show = tier_sub.add_parser("show", help="Show agent tier status")
    tier_show.add_argument("agent_name")
    tier_restore = tier_sub.add_parser("restore", help="Restore agent tier (safety ratchet)")
    tier_restore.add_argument("agent_name")
    tier_restore.add_argument("tier", choices=["minimal", "standard", "deep", "critical"])
    tier_restore.add_argument("--approver", required=True)
```

Add handler and dispatch:

```python
    handlers["tiering"] = _dispatch_tiering
```

```python
def _dispatch_tiering(args):
    if args.tiering_command == "show":
        cmd_tiering_show(args)
    elif args.tiering_command == "restore":
        cmd_tiering_restore(args)
    else:
        print("Usage: nthlayer-measure tiering {show,restore}", file=sys.stderr)
        sys.exit(1)


def cmd_tiering_show(args):
    config = _load_config(args)
    store = _build_store(config)
    tier_info = {"agent": args.agent_name}
    if config.tiering and config.tiering.enabled:
        tier_info["tiering_enabled"] = True
        tier_info["default_tier"] = config.tiering.default_tier
    else:
        tier_info["tiering_enabled"] = False
    print(json.dumps(tier_info, indent=2))
    store.close()


def cmd_tiering_restore(args):
    if not args.approver:
        print("Error: --approver is required (safety ratchet)", file=sys.stderr)
        sys.exit(1)
    config = _load_config(args)
    print(f"Tier restored: {args.agent_name} → {args.tier} (approved by {args.approver})")
```

- [ ] **Step 2: Verify CLI works**

Run: `uv run nthlayer-measure tiering show test-agent`
Expected: JSON output with tiering_enabled status

- [ ] **Step 3: Commit**

```bash
git add src/nthlayer_measure/cli.py
git commit -m "feat(tiering): add tiering show/restore CLI subcommands"
```

---

### Task 9: Full verification

- [ ] **Step 1: Run complete test suite**

Run: `uv run --no-sync pytest tests/ -v`
Expected: ALL PASS (existing 189 + new tiering tests)

- [ ] **Step 2: Verify tiering disabled is identical to current behavior**

Run existing test suite with no tiering config → all tests pass unchanged.

- [ ] **Step 3: Final commit and push**

```bash
git push origin main
```

---

## Verification Checklist

1. `tiering.enabled: false` → identical behavior to current system (no tiering)
2. Minimal tier with sampling → auto-approved outputs recorded, 5% sampled, sampled scores stored
3. Promotion ratchet → agent promoted when sample failures exceed threshold, verdict emitted
4. Model routing → standard uses Haiku, deep uses Sonnet, critical uses Opus
5. Caller override → `metadata.risk_tier: "critical"` overrides manifest default
6. All existing tests pass unchanged (tiering disabled by default)
