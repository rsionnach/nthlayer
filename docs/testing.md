# Testing in NthLayer

How we write, organise, and maintain tests across the NthLayer ecosystem.

This document covers conventions for tests written within the NthLayer codebase. It does not cover testing practices for adopters integrating NthLayer into their systems (that's the OpenSRM specification's domain), nor R5 reviews (a parallel quality mechanism documented separately).

## Test categories

NthLayer uses several categories of tests, each with different conventions and trade-offs:

**Unit tests** verify individual modules, functions, and classes in isolation. They mock dependencies at module boundaries, run fast (typically under 100ms each), and execute on every push. They form the bulk of the test suite and provide the primary safety net during development.

**Integration tests** verify behaviour across multiple modules within a single repo or across repo boundaries without external service dependencies. They mock less than unit tests — typically only at infrastructure boundaries (HTTP clients, databases, external APIs). They run more slowly (seconds rather than milliseconds) and execute on push to main.

**End-to-end tests** verify the full ecosystem flow across multiple components and processes. The canonical example is `test/integration-three-tier.sh` in the front-door repo, which orchestrates the three-tier stack (core + workers + bench) against real infrastructure. They typically run via shell scripts that orchestrate multiple processes against real (or in-memory) infrastructure. Slow (minutes), run manually before releases or in scheduled CI jobs.

Cross-component shape agreement (what a previous revision of this document called "contract tests") is enforced in-tree by shared imports from `nthlayer-common` — `Verdict`, `ReliabilityManifest`, `Assessment`, and the shared `serialise.from_dict` / `to_dict` helpers. A separate fixture-based contracts surface is not maintained; round-trip serialisation tests, where they exist, live in `nthlayer-common` itself.

The sections below are organised by category. Some conventions (naming, the lifecycle of failing tests) apply across categories and have their own sections at the end.

---

## Unit tests

The largest test category. Most files in `tests/` are unit tests by default.

### Organisation

Two layouts are in active use across the ecosystem; pick the one that matches the shape of the repo.

**Flat layout** — one test file per source module, all at the top of `tests/`. Used by `nthlayer-core`, `nthlayer-common`, `nthlayer-bench`, and `nthlayer-generate`:

```
<repo>/
├── src/<package>/
│   ├── module_a.py
│   └── module_b.py
└── tests/
    ├── test_module_a.py     # One test file per source module
    └── test_module_b.py
```

**Subpackage-nested layout** — `tests/` mirrors the subpackage structure of `src/`. Used by `nthlayer-workers`, where the five internal modules (observe / measure / correlate / respond / learn) each get their own `tests/<subpackage>/` directory with module-scoped fixtures:

```
nthlayer-workers/
├── src/nthlayer_workers/
│   ├── observe/
│   ├── measure/
│   └── ...
└── tests/
    ├── observe/
    │   ├── conftest.py
    │   └── test_*.py
    ├── measure/
    │   ├── conftest.py
    │   └── test_*.py
    └── ...
```

For larger modules in a flat-layout repo, split into a directory:

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

**Test count alone never warrants a split; topical incoherence does.** A 40-test file covering one module's full API surface (happy path, edge cases, errors, parametrised variants) is coherent — exactly what a healthy suite for a non-trivial module looks like. Split only when the file is two unrelated concerns wearing one filename and a developer looking for tests of concern X has to scroll past concern Y. Auditors should not flag files by `def test_` count; the relevant signal is whether the test names map cleanly to one module/subsystem or whether the file is doing two jobs.

### Principles

**Test behaviour, not implementation.** Tests describe what the code does from the perspective of a caller, not how it does it internally. A test that breaks when you refactor the implementation but didn't change the behaviour is testing the wrong thing.

**Each test answers one question.** If a test fails, the failure message and test name should make clear what behaviour broke. Tests that verify multiple behaviours at once produce ambiguous failures.

**Prefer behavioural assertions over structural ones.** `assert verdict.action == "approve"` is better than `assert verdict == {"action": "approve", ...full dict}`. Structural assertions break on irrelevant changes; behavioural assertions only break when the relevant behaviour changes.

### Mocking conventions

**Mock at module boundaries.** When testing module logic, mock the dependencies the module imports (CoreAPIClient, external services), not internal helpers within the module under test.

**Patch at the use site's lookup path, not at the canonical source.** Where Python resolves a name at call time depends on how the consuming module imported it: `from x import Name` binds the name into the consumer's namespace; `import x; x.Name` looks the name up on the imported module. Patching the canonical source for a `from`-import leaves the consumer's reference untouched and the test passes having mocked nothing. See [mocking-classification.md](mocking-classification.md) for the rule, the descriptive A/A-flag/B/C taxonomy, and the application procedure used by the per-repo test-suite cleanups.

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

Async test conventions vary by tier:

- **`nthlayer-workers` (Tier 2)** — module code is async by idiom (cycle loops, concurrent evaluation), so most tests are `async def` and rely on `asyncio_mode = "auto"` to drive them.
- **`nthlayer-core` (Tier 1)** — Starlette server; tests are async because they drive the live app via `httpx.AsyncClient`, not because the domain code is concurrent.
- **`nthlayer-bench` (Tier 3)** — Textual TUI; mixed sync/async depending on whether the test exercises render-side logic or app-driver coroutines.
- **`nthlayer-common`, `nthlayer-generate`** — synchronous unless the unit under test is async.

Under `asyncio_mode = "auto"`, `async def test_*` functions do not need an explicit `@pytest.mark.asyncio` decorator; under default mode they do. The examples below show the decorator-bearing form (which works in both modes); omit the decorator in repos that set `asyncio_mode = "auto"` (currently `nthlayer-workers`, `nthlayer-core`).

Worker-tier pattern (async module under test):

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

Where fixtures are used, they live in `conftest.py` at the appropriate scope — top-level fixtures in `tests/conftest.py`, package-level fixtures in `tests/<package>/conftest.py`. Practice varies across the ecosystem:

- `nthlayer-bench` has a top-level `tests/conftest.py`.
- `nthlayer-generate` has both a top-level `conftest.py` and a per-subdir `tests/smoke/conftest.py`.
- `nthlayer-workers` has per-subpackage conftests (`tests/measure/conftest.py`, `tests/correlate/conftest.py`, `tests/respond/conftest.py`) but no top-level one; `tests/observe/` and `tests/learn/` carry their fixtures inline.
- `nthlayer-common` has only `tests/records/conftest.py`.
- `nthlayer-core` has **no `conftest.py` anywhere**. The rationale lives in §Reference architecture, below.

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

Integration tests verify behaviour across multiple modules within a single repo. There is no single prescribed location: `nthlayer-generate` keeps them under `tests/integration/`; most other repos colocate them with unit tests in the same `tests/` (or `tests/<subpackage>/`) tree, distinguishing them by name and content rather than directory. Cross-repo integration tests live in the front-door repo's `nthlayer/test/` directory — see the End-to-end tests section below.

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

End-to-end tests verify the full ecosystem flow across multiple components and processes. The canonical example is `test/integration-three-tier.sh` in the front-door repo, which boots core + workers + bench against real infrastructure (Prometheus, Tempo, SQLite). See `docs/integration-testing.md` for the full harness cross-reference.

### Characteristics

E2E tests differ from unit and integration tests in several ways:

- **Multiple processes.** They orchestrate the three runtime tiers (core + workers + bench) as separate running processes.
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

## Reference architecture

`nthlayer-core`'s test pattern is the sanctioned reference for the ecosystem. The pattern is:

- **Real `Store(tmp_path)`**, not a `MemoryStore` mock — the same SQLite store class the production server uses, backed by a per-test temp directory.
- **Real `httpx.AsyncClient` against the live Starlette app**, not a hand-rolled request fake or a mocked handler.
- **Zero own-package mocking** — no `patch("nthlayer_core...")` sites at all.
- **Zero `conftest.py`** anywhere under `tests/`.
- **Zero `_helpers.py`** modules — each test file is self-contained, building the small amount of state it needs inline. This is a core-tier discipline; `_helpers.py` is the canonical pattern elsewhere (see §Naming).

The rationale (pinned in `nthlayer-core/CLAUDE.md` Hard Rule 8: "Tests use real `Store(tmp_path)`, not a MemoryStore mock — same rule as the rest of the ecosystem. Assertions on structured-data primitives […], not captured response text.") is that an HTTP-server tier benefits from exercising the real serialisation, routing, and store-side validation paths on every test, and the cost is small because `Store(tmp_path)` is cheap to construct.

**Scope.** This pattern applies to **HTTP-server-shaped tiers** (like `nthlayer-core`) and to **new** test files in such tiers. It is not a worker/library/TUI pattern: `nthlayer-workers`, `nthlayer-bench`, `nthlayer-common`, and `nthlayer-generate` continue to use conftests, `_helpers.py`, and the async-mock idioms appropriate to their shape. **Existing siblings are not expected to retroactively migrate.** If you are starting a new tier or a new test file against a real-store-plus-HTTP shape, core's layout is the one to copy.

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

For helpers that aren't tests themselves, the convention is a separate `_helpers.py` module alongside the tests that use it (as in `nthlayer-generate/tests/smoke/_helpers.py`), or — where the helper is a factory or builder shared across a subpackage — a `conftest.py` exposing it as a fixture. Do not name helper *functions* with a `test_` prefix; pytest will collect them as tests.

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

Every active repo has a CI workflow under `.github/workflows/` that runs unit and integration tests on push to main and on pull requests. The filename is not uniform across the ecosystem:

| Repo | Workflow file |
|---|---|
| `nthlayer-common` | `ci.yml` |
| `nthlayer-core` | `ci.yml` |
| `nthlayer-generate` | `ci.yml` |
| `nthlayer` (front-door) | `ci.yml` (shell `bash -n` only — no Python suite) |
| `nthlayer-workers` | `test.yml` |
| `nthlayer-bench` | `test.yml` |
| `nthlayer-override-adapter` | `test.yml` |

Treat the table above as ground truth and the filename as a per-repo detail rather than a prescription. Each workflow uses `uv` for dependency management and `ruff` for linting alongside `pytest` for tests (front-door excepted — see above).

E2E tests run separately, either manually or in scheduled CI jobs (nightly is typical), since their runtime makes them unsuitable for every-push execution.

A green main branch is the project's invariant for unit and integration tests. Failing tests on main are treated as P1 — they get fixed, reverted, or explicitly xfailed (with documented reason and resolution path) within 24 hours.

E2E test failures get more latitude (the next scheduled run is the typical resolution window) but are still tracked actively.

---

## Maintenance

Once a year (or after major architectural shifts), every active Python repo gets a test suite audit pass. (`opensrm` and `nthlayer-site` have no Python suites; the front-door's audit covers its shell scripts and helper modules only.) The audit checks for:

- Tests that no longer test what their name suggests
- Redundant tests where multiple tests cover the same behaviour from the same angle
- Tests of code that has been deleted but the tests remained
- Tests that test implementation details rather than behaviour
- Test suites with persistent xfails that haven't been resolved
- Integration tests that could be unit tests (and should be migrated to be faster)
- Unit tests that grew into integration tests (and should be properly relocated)

The output is a clean test suite where every test earns its place at the right level.
