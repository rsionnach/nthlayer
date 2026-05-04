# P3-C.3: Measure Module — Instructor-Backed Evaluation

**Date:** 2026-04-24
**Epic:** P3-C (Measure Module)
**Dependencies:** P1-A.1 (Instructor integration), P3-C.1
**Spec:** NTHLAYER-MEASURE-v1 §8 (LLM-as-judge)

## Summary

Replace raw `llm_call()` + manual JSON parsing in the measure evaluator with `structured_call()` using Instructor. Defines Pydantic response models for evaluation results. Automatic retry on validation failure. Adds parallel evaluation with concurrency cap.

**P3-C.3 changes the evaluator only.** Governance decisions remain deterministic per P3-C.2; no LLM in the autonomy ratchet. The severity classification and reduction rules are purely arithmetic — intentionally not LLM-mediated.

---

## Pydantic Response Model

```python
from pydantic import BaseModel, Field


class DimensionScore(BaseModel):
    """Score for a single quality dimension."""
    score: float = Field(ge=0.0, le=1.0)
    reasoning: str = ""


class EvaluationResult(BaseModel):
    """Structured evaluation result from LLM-as-judge."""
    dimensions: dict[str, DimensionScore]
    confidence: float = Field(ge=0.0, le=1.0, default=0.0)
```

Replaces the manual `json.loads` + `_clamp()` + field extraction in `parse_response()`. Instructor handles JSON schema enforcement, validation (0.0-1.0 bounds), and retry on malformed responses.

---

## Changes to ModelEvaluator

### Before (current)

```python
# _call_model: llm_call() → raw text
# parse_response: json.loads + manual extraction → QualityScore
# evaluate: build_prompt → _call_model → parse_response → QualityScore
```

### After

```python
# evaluate: build_prompt → structured_call(response_model=EvaluationResult) → convert → QualityScore
```

The `_call_model` and `parse_response` methods are replaced by a single `structured_call()` invocation. `build_prompt()` is unchanged — same YAML template, same prompt construction.

```python
async def evaluate(self, output: AgentOutput, dimensions: list[str], model: str | None = None) -> QualityScore:
    effective_model = model or self._model
    prompt = self.build_prompt(output, dimensions)
    system_prompt = load_prompt(_PROMPT_PATH).system

    result = await asyncio.wait_for(
        asyncio.to_thread(
            structured_call,
            system=system_prompt,
            user=prompt,
            response_model=EvaluationResult,
            model=effective_model,
            max_tokens=self._max_tokens,
            timeout=self._timeout,
            max_retries=3,
        ),
        timeout=self._timeout + 5.0,
    )

    return _to_quality_score(result, output, effective_model)
```

### Conversion

```python
def _to_quality_score(result: EvaluationResult, output: AgentOutput, model: str) -> QualityScore:
    return QualityScore(
        eval_id=str(uuid.uuid4()),
        agent_name=output.agent_name,
        task_id=output.task_id,
        dimensions={name: ds.score for name, ds in result.dimensions.items()},
        reasoning={name: ds.reasoning for name, ds in result.dimensions.items() if ds.reasoning},
        confidence=result.confidence,
        evaluator_model=model,
    )
```

---

## Timeout

**Default: 30 seconds** (was 120s). Configurable via `ModelEvaluator(timeout=...)`.

The old 120s default was inherited from the CLI's full LLM-as-judge pathway with large prompts. 30s is appropriate for structured evaluation calls:
- Instructor adds schema enforcement overhead (~1-2s)
- Evaluation prompts are moderate size (agent output + dimensions, not full incident windows)
- 30s gives ~3x margin over typical 8-12s LLM response times

Outer `asyncio.wait_for` set to `timeout + 5.0` (safety net, same pattern as P3-D.3).

If prompts grow to require >30s, the right response is to redesign the prompt (sample evidence, not full output) rather than extending the timeout.

---

## Parallel Evaluation

Existing code evaluates SLOs sequentially. With 5 SLOs at 30s timeout, sequential worst case is 2.5 minutes — past the 60s cycle interval.

**Fix:** Parallel evaluation with `asyncio.Semaphore` concurrency cap.

```python
# Configurable via workers.measure.evaluation_concurrency in nthlayer.yaml
# Default 5; operators tune based on LLM provider rate limits.
EVAL_CONCURRENCY = 5

async def _evaluate_slos_parallel(self, slos_to_eval, provider, manifests):
    sem = asyncio.Semaphore(EVAL_CONCURRENCY)

    async def eval_one(service, slo):
        async with sem:
            await self._evaluate_slo(service, slo, provider, ...)

    tasks = [eval_one(svc, slo) for svc, slo in slos_to_eval]
    await asyncio.gather(*tasks, return_exceptions=True)
```

Bounded resource usage (5 concurrent LLM calls max), latency drops from `N × timeout` to `ceil(N / 5) × timeout`.

**Note:** This changes the `process_cycle` flow from sequential `for slo in slos` to parallel `gather`. Breach detection (Phase 2) still runs after all evaluations complete — no race on `current_status`.

---

## Cost Accounting

`structured_call` returns only the validated Pydantic model — token usage from the underlying API response is not exposed. But `cost_usd` is actively used by four downstream consumers:
1. `TrendTracker.compute_window()` — aggregates into `TrendWindow.total_cost_usd`
2. CLI `status` command — displays `total_cost_usd`
3. `SQLiteStore.save_score()` — persists `cost_usd` column
4. API queue — passes as `metadata.cost_currency`

Losing it silently would produce `total_cost_usd: 0.0` for all evaluations.

**Fix: `structured_call_with_usage()` in nthlayer-common.** Uses Instructor's public `create_with_completion()` API which returns `(validated_model, completion)`. The `completion.usage` provides `prompt_tokens` and `completion_tokens` — stable, documented, survives Instructor upgrades.

```python
# nthlayer_common/llm_structured.py

@dataclass
class StructuredCallUsage:
    input_tokens: int = 0
    output_tokens: int = 0

@dataclass
class StructuredCallResult(Generic[T]):
    data: T
    usage: StructuredCallUsage

def structured_call_with_usage(
    system, user, response_model, model=None, max_tokens=2000,
    timeout=None, max_retries=3,
) -> StructuredCallResult[T]:
    """Like structured_call but also returns token usage for cost accounting.

    Uses Instructor's create_with_completion() — public API that returns
    both the validated model and the raw completion with usage data.
    """
    # Anthropic path:
    #   model, completion = client.messages.create_with_completion(...)
    #   usage = StructuredCallUsage(completion.usage.input_tokens, completion.usage.output_tokens)
    # OpenAI path:
    #   model, completion = client.chat.completions.create_with_completion(...)
    #   usage = StructuredCallUsage(completion.usage.prompt_tokens, completion.usage.completion_tokens)
```

The evaluator calls `structured_call_with_usage()` and passes `usage` to `_compute_cost()` for `QualityScore.cost_usd`. The existing `structured_call()` stays unchanged — P3-D.3 (correlate NL summary) and other callers that don't need cost data continue using the simple API.

**Acceptance criterion:** All four downstream consumers receive non-None `cost_usd` values after the change. Not just "doesn't crash" — `TrendTracker` aggregates real cost data.

---

## What Doesn't Change

- `Evaluator` protocol (same `evaluate` signature)
- `QualityScore` dataclass (output shape unchanged)
- `build_prompt()` (prompt construction unchanged)
- Governance logic (deterministic per P3-C.2)
- Pipeline router (calls `evaluator.evaluate()` unchanged)
- Detection/alerting logic
- Tiering logic

---

## Test Strategy

### Pydantic model
- `test_evaluation_result_valid` — dimensions + confidence in range
- `test_evaluation_result_clamps_bounds` — out-of-range values rejected by Pydantic
- `test_dimension_score_default_reasoning` — empty string default

### Evaluator
- `test_evaluate_uses_structured_call` — mock structured_call, verify EvaluationResult returned
- `test_evaluate_converts_to_quality_score` — EvaluationResult → QualityScore correctly
- `test_evaluate_timeout` — structured_call hangs → timeout → raises
- `test_evaluate_validation_retry` — Instructor retries on malformed response

### Parallel evaluation
- `test_parallel_evaluation` — multiple SLOs evaluated concurrently
- `test_parallel_failure_isolation` — one SLO fails, others succeed

### Existing tests
Update `test_evaluator.py` tests that mock `llm_call` to mock `structured_call` instead.

---

## Acceptance Criteria

From the epic tree:
1. Evaluation results are validated Pydantic models (not parsed JSON)
2. Retry on malformed LLM response (up to 3 attempts)
3. Cost accounting OTel events emitted per call

Added:
4. 30s default timeout (configurable)
5. Parallel evaluation with concurrency cap (configurable, default 5)
6. Governance unchanged (deterministic, no LLM)
7. `cost_usd` preserved via `structured_call_with_usage()` using Instructor's public `create_with_completion()` API
8. Four downstream consumers verified: trend tracker, CLI, store, API queue all receive real cost data

---

## Work Sequence

| Step | What | Verify |
|------|------|--------|
| 1 | Add `structured_call_with_usage()` to nthlayer-common using `create_with_completion()` | `pytest nthlayer-common/ -x` |
| 2 | Define `EvaluationResult` + `DimensionScore` Pydantic models | Model tests pass |
| 3 | Replace `_call_model` + `parse_response` with `structured_call_with_usage` in `ModelEvaluator`; verify cost_usd flows to all 4 consumers | Evaluator tests pass |
| 4 | Add parallel evaluation in `MeasureModule.process_cycle` with configurable concurrency | Parallel tests pass; full suite passes |
