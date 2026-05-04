# Testing in NthLayer

How we write, organise, and maintain tests across the NthLayer ecosystem.

This document covers conventions for tests written within the NthLayer codebase. It does not cover testing practices for adopters integrating NthLayer into their systems (that's the OpenSRM specification's domain), nor R5 reviews (a parallel quality mechanism documented separately).

## Test categories

NthLayer uses several categories of tests, each with different conventions and trade-offs:

**Unit tests** verify individual modules, functions, and classes in isolation. They mock dependencies at module boundaries, run fast (typically under 100ms each), and execute on every push. They form the bulk of the test suite and provide the primary safety net during development.

**Integration tests** verify behaviour across multiple modules within a single repo or across repo boundaries without external service dependencies. They mock less than unit tests — typically only at infrastructure boundaries (HTTP clients, databases, external APIs). They run more slowly (seconds rather than milliseconds) and execute on push to main.

**End-to-end tests** verify the full ecosystem flow across multiple components and processes. The canonical example is `test/integration-chain.sh`, which exercises the measure → correlate → respond → learn pipeline. They typically run via shell scripts that orchestrate multiple processes against real (or in-memory) infrastructure. Slow (minutes), run manually before releases or in scheduled CI jobs.

**Contract tests** verify API boundaries between components. Core's HTTP API as consumed by workers is the primary example. They pin the interface shape so changes are detected explicitly, preventing silent breakage when one component evolves faster than its consumers.

The sections below are organised by category. Some conventions (naming, the lifecycle of failing tests) apply across categories and have their own sections at the end.

---

## Unit tests

The largest test category. Most files in `tests/` are unit tests by default.

### Organisation

Each repo follows a consistent structure:

```
<repo>/
├── src/<package>/
│   ├── module_a.py
│   └── module_b.py
└── tests/
    ├── conftest.py          # Shared fixtures
    ├── test_module_a.py     # One test file per source module
    └── test_module_b.py
```

For larger modules, split into a directory:

```
tests/
└── module_a/
    ├── __init__.py
    ├── conftest.py
    ├── test_happy_path.py
    ├── test_edge_cases.py
    └── test_error_handling.py
```

The split-by-concern pattern is preferred when a module's behaviour has clearly distinct categories worth separating.

### Principles

**Test behaviour, not implementation.** Tests describe what the code does from the perspective of a caller, not how it does it internally. A test that breaks when you refactor the implementation but didn't change the behaviour is testing the wrong thing.

**Each test answers one question.** If a test fails, the failure message and test name should make clear what behaviour broke. Tests that verify multiple behaviours at once produce ambiguous failures.

**Prefer behavioural assertions over structural ones.** `assert verdict.action == "approve"` is better than `assert verdict == {"action": "approve", ...full dict}`. Structural assertions break on irrelevant changes; behavioural assertions only break when the relevant behaviour changes.

### Mocking conventions

**Mock at module boundaries.** When testing module logic, mock the dependencies the module imports (CoreAPIClient, external services), not internal helpers within the module under test.

**Use `unittest.mock.AsyncMock` for async functions.** Don't reach for third-party async-mock libraries; the standard library covers what we need.

**Prefer realistic mock data.** A mock returning `{"id": "test", "data": {}}` is fine for a happy-path test but doesn't catch issues that arise from real-shaped data. For tests that exercise data handling, use mock data that mirrors actual shapes from production.

### What to test

For each module, ensure coverage of:

1. **Happy path.** The most common successful execution.
2. **Edge cases.** Empty inputs, single-element inputs, large inputs, None values where applicable.
3. **Error paths.** What happens when dependencies fail, time out, return malformed data.
4. **State transitions.** If the module has state (lifecycle, status, mode), each transition gets a test.
5. **Public API contract.** Type signatures, return shapes, documented exceptions.

Skip tests for trivial getters/setters, pass-through wrappers, and constants unless their derivation is non-trivial.

### What not to do

**Don't test private methods directly.** If a private method has behaviour worth testing, that behaviour is observable through the public interface — test it there. Private method tests couple tests to implementation, making refactoring expensive.

**Don't write tests just to hit coverage numbers.** A test that exercises code without asserting specific behaviour is worse than no test — it gives false confidence and slows down the suite.

**Don't catch broad exceptions.** `with pytest.raises(Exception)` is almost always wrong. Be specific about what exception is expected.

**Don't sleep in tests.** If you find yourself adding `time.sleep(1)` to make a test pass, the test is flaky. Mock the clock or restructure the test to be deterministic.

### Async tests

All worker module tests are async. Use `pytest.mark.asyncio` and `async def`:

```python
@pytest.mark.asyncio
async def test_module_processes_cycle():
    module = ModuleUnderTest(client=mock_client)
    await module.process_cycle()
    mock_client.submit_assessment.assert_called_once()
```

For testing concurrent behaviour, use `asyncio.gather`:

```python
@pytest.mark.asyncio
async def test_concurrent_evaluation_respects_semaphore():
    results = await asyncio.gather(*[module.evaluate(slo) for slo in slos])
    assert len(results) == len(slos)
```

### Test data

**Use factories, not fixtures, for parameterised data.** When you need many similar-but-different test inputs, a factory function beats many fixtures:

```python
def make_verdict(
    *,
    type: str = "quality_breach",
    service: str = "test-service",
    severity: str = "high",
    parent_ids: list[str] | None = None,
) -> dict:
    """Build a verdict dict with sensible defaults; override what matters."""
    return {
        "id": str(uuid.uuid4()),
        "created_at": datetime.now(UTC).isoformat(),
        "type": type,
        "service": service,
        "metadata": {"custom": {"severity": severity}},
        "parent_ids": parent_ids or [],
        # ... rest of canonical shape
    }
```

This pattern (factory function with keyword-only overrides) is the standard. Test files create the verdicts they need with the variations they need; they don't share fixtures of complete verdicts unless the same exact verdict is used by many tests.

### Fixtures

Fixtures live in `conftest.py` at the appropriate scope. Module-level fixtures in `tests/conftest.py`; package-level fixtures in `tests/<package>/conftest.py`.

Name fixtures by what they represent, not what they do:

```python
@pytest.fixture
def quality_breach_verdict() -> dict:
    """A canonical quality_breach verdict for triage tests."""
    ...

@pytest.fixture
def core_client_with_no_data() -> CoreAPIClient:
    """A CoreAPIClient mock that returns empty results for all queries."""
    ...
```

Avoid fixtures named `setup_thing`, `make_thing`, `data` — these don't tell the reader what they're getting.

---

## Integration tests

Integration tests verify behaviour across multiple modules within a single repo. They're located under `tests/integration/` per repo.

### When to write integration tests

Write an integration test when:

- The behaviour you're verifying spans multiple modules and the interaction between them is the thing that matters.
- A unit test would require so much mocking that the test becomes more about the mocks than the behaviour.
- The interface between two modules has subtle requirements (e.g., async ordering, transaction boundaries) that unit tests would miss.

Don't write an integration test when a unit test would suffice. Integration tests are slower, harder to debug when they fail, and accumulate maintenance cost faster than unit tests.

### Mocking conventions

Integration tests mock at infrastructure boundaries, not module boundaries:

- Mock the HTTP client (`httpx.AsyncClient`), not the CoreAPIClient that uses it.
- Mock the database connection, not the repository class that uses it.
- Mock external services (Prometheus, Tempo, etc.) at their HTTP API, not at the abstraction layer.

This means integration tests exercise the real abstractions inside your code (CoreAPIClient, repository classes) but don't talk to real external systems. The boundary makes clear what's being tested as a system and what's being assumed.

### Test data

Integration tests typically need richer test data than unit tests because they exercise more code paths. Reuse the factory functions from unit tests where possible (`make_verdict`, etc.) but expect to need additional setup helpers for multi-step scenarios.

Common pattern: a `setup_pipeline_state(...)` helper that creates the chain of verdicts/assessments needed to drive a particular pipeline state, used as the starting point for tests that verify behaviour from that state forward.

### Naming

Integration test names should describe the cross-module behaviour being verified:

```python
def test_correlation_snapshot_triggers_respond_pipeline_via_polling(): ...
def test_drift_assessment_persists_and_resurfaces_after_module_restart(): ...
def test_verdict_lineage_chain_walks_correctly_across_module_boundaries(): ...
```

Avoid integration test names that look like unit test names (`test_<function>_<scenario>`) — the cross-module nature should be visible in the name.

---

## End-to-end tests

End-to-end tests verify the full ecosystem flow across multiple components and processes. The canonical example is `test/integration-chain.sh`.

### Characteristics

E2E tests differ from unit and integration tests in several ways:

- **Multiple processes.** They orchestrate measure, correlate, respond, learn, and core as separate running processes.
- **Real (or in-memory) infrastructure.** They use actual SQLite databases, actual HTTP servers, sometimes actual Prometheus instances.
- **Shell-script driven.** Bash scripts are the primary tool for orchestration, since pytest's process model isn't well-suited to multi-process coordination.
- **Slow.** A full E2E run takes minutes, not seconds.
- **Manual or scheduled.** They don't run on every push. They run before releases, in scheduled nightly CI jobs, or manually during development of cross-component changes.

### What to verify

E2E tests verify behaviours that can only be observed across the full pipeline:

- A quality_breach in measure produces a correlation_snapshot in correlate, which triggers respond's incident handling, which produces verdicts that learn resolves into outcomes.
- Verdict lineage is preserved across all module boundaries.
- Configuration changes (e.g., manifest updates) propagate correctly through the pipeline.
- System behaviour under realistic timing (cycle intervals, retry backoffs) matches design.

E2E tests should not duplicate what unit and integration tests already verify. If a behaviour can be verified without spinning up the full ecosystem, that's where the test belongs.

### Conventions

E2E tests follow shell-script conventions rather than pytest conventions. Each script:

1. Sets up its own environment (creates temp directories, starts processes).
2. Runs the scenario.
3. Asserts outcomes via process exit codes, output grep, or database queries.
4. Cleans up (kills processes, removes temp data).

Keep scripts idempotent where possible — if a previous run left state behind, the next run should clean it up rather than failing.

Document each E2E test with a header comment explaining what it verifies and why it needs to be E2E (rather than integration).

---

## Contract tests

Contract tests verify API boundaries between components. They're located under `tests/contracts/` where applicable.

### Purpose

When component A produces data consumed by component B, both sides need to agree on the data's shape. Contract tests pin this shape from both directions:

- **Producer-side.** The contract test asserts that the producer's output matches the agreed shape. If the producer's serialisation changes, the contract test fails before consumers break.
- **Consumer-side.** The contract test asserts that the consumer correctly parses canonical shapes. If the consumer's parsing logic changes, the contract test fails before producer changes are misinterpreted.

The pair catches breakage early: a producer change that violates the contract fails its own test, not a downstream consumer's test that's harder to debug.

### When to write contract tests

Write contract tests for:

- Cross-component HTTP APIs (core's API as consumed by workers).
- Persistent data formats (verdict serialisation, assessment serialisation).
- Cross-version compatibility (when an API needs to remain stable across versions).

Don't write contract tests for purely internal interfaces or interfaces that are only used in one place — unit tests cover those well enough.

### Conventions

Contract tests use canonical fixture data representing the agreed shape. Both producer and consumer test against the same fixtures, so any divergence shows up as a test failure on whichever side broke.

Store contract fixtures in a shared location (e.g., `nthlayer-common/tests/contracts/fixtures/`) so both sides reference the same source of truth.

Name contract tests for the contract being verified:

```python
def test_quality_breach_verdict_serialisation_matches_v15_contract(): ...
def test_correlation_snapshot_assessment_serialisation_matches_v15_contract(): ...
```

When a contract changes, version the fixtures (e.g., `v15/`, `v16/`) and update both sides explicitly. Contract changes are not silent — they require deliberate updates on both sides of the boundary.

---

## Naming conventions

These apply across all test categories.

Test functions describe the scenario and expected behaviour:

```python
def test_verdict_chain_preserves_lineage_across_module_restart(): ...
def test_drift_detector_returns_none_when_prometheus_unreachable(): ...
def test_brief_renders_minimal_state_when_no_respond_verdicts(): ...
```

Avoid:
- `test_<function_name>` — too vague; doesn't say what about the function is being tested.
- `test_works_correctly` — meaningless.
- `test_case_<n>` — relies on test ordering, which is fragile.

Use `_test_` prefix for helper functions that aren't tests themselves.

---

## Lifecycle of a failing test

When a test is failing, the question isn't always "fix the test." Sometimes the right answer is:

1. **The test is right and the code is wrong.** Fix the code.
2. **The test was right but the requirements changed.** Update the test to reflect new requirements.
3. **The test was testing implementation details that have legitimately changed.** Delete the test or rewrite it to test behaviour.
4. **The test was redundant.** Delete it.

The instinct to "make the failing test pass" should always come second to "understand why the test was written and whether it's still relevant."

When refactoring causes tests to fail, the first question is whether the refactor preserves a behaviour the test was protecting. Sometimes it doesn't, and the test caught the regression. Sometimes the test was protecting an implementation detail that the refactor intentionally changed.

This applies across all test categories, but the cost of getting it wrong scales with category. A wrongly-deleted unit test is annoying. A wrongly-deleted integration or contract test can cause silent cross-component breakage that doesn't surface until production.

---

## CI

Every active repo has a CI workflow (`.github/workflows/ci.yml`) that runs unit and integration tests on push to main and on pull requests. The workflow uses `uv` for dependency management and `ruff` for linting alongside `pytest` for tests.

E2E tests run separately, either manually or in scheduled CI jobs (nightly is typical), since their runtime makes them unsuitable for every-push execution.

A green main branch is the project's invariant for unit and integration tests. Failing tests on main are treated as P1 — they get fixed, reverted, or explicitly xfailed (with documented reason and resolution path) within 24 hours.

E2E test failures get more latitude (the next scheduled run is the typical resolution window) but are still tracked actively.

---

## Maintenance

Once a year (or after major architectural shifts), every active repo gets a test suite audit pass. The audit checks for:

- Tests that no longer test what their name suggests
- Redundant tests where multiple tests cover the same behaviour from the same angle
- Tests of code that has been deleted but the tests remained
- Tests that test implementation details rather than behaviour
- Test suites with persistent xfails that haven't been resolved
- Integration tests that could be unit tests (and should be migrated to be faster)
- Unit tests that grew into integration tests (and should be properly relocated)

The output is a clean test suite where every test earns its place at the right level.
