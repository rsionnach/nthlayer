# jmy.25 `--json` Output for `learn recommendations` — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an additive `--json` flag to `nthlayer-workers learn recommendations` that emits a single machine-readable JSON document on stdout at end-of-run, covering apply outcomes and PR result (including partial-failure). Preserve the human-readable summary on stderr; suppress the `PR created:` stdout line in JSON mode. Refactor the single soft `_run_pr_path` failure branch to return a result instead of raising.

**Architecture:** Single-repo change in `nthlayer-workers`. New argparse flag `--json`; pre-flight check mirrors `--pr`. `_run_pr_path` soft-failure refactored to return `PRResult` (extended with optional `error` field) to caller. `_cmd_recommendations` builds the JSON document at end-of-run from `ApplyResult` + `PRResult`. `format_summary` output rerouted to stderr when `args.json` is set.

**Tech Stack:** Python 3.11+. No new runtime deps; uses `json` from the stdlib.

**Spec:** `nthlayer/docs/superpowers/specs/2026-05-29-jmy25-json-output-design.md`.

**Bead:** `opensrm-jmy.25`. Parent `opensrm-jmy.6` (Learn → Spec loop) shipped; this is the CI-surface additive.

---

## File structure

### Files modified

| Path | Responsibility |
|---|---|
| `nthlayer-workers/src/nthlayer_workers/learn/cli.py` | Add `--json` flag to `recommendations` subparser; add `--json` pre-flight check (mirrors `--pr` at lines 182–183); reroute `format_summary` output to stderr when `args.json`; suppress `print("PR created: ...")` in JSON mode; build JSON doc at end-of-run; refactor `_run_pr_path` soft-failure branch (line 312) to return `PRResult(error=...)` instead of `SystemExit`. |
| `nthlayer-workers/src/nthlayer_workers/learn/pr.py` | Extend `PRResult` with `error: str \| None = None` so the soft-failure branch can return a structured result. |
| `nthlayer-workers/tests/learn/test_cli_recommendations.py` | 8 tests: pre-flight rejection, clean apply JSON, skipped-only JSON, `--pr` success JSON, `--pr` failure JSON, valid-JSON parse, stderr preservation, exit-code parity with non-JSON mode. |

### Files NOT modified

- `nthlayer-workers/src/nthlayer_workers/learn/apply.py` — `ApplyResult` / `SkippedRecommendation` / `RecOutcome` consumed unchanged.
- `nthlayer-workers/src/nthlayer_workers/learn/recommendations.py` — plan generation untouched; jmy.25 is post-apply.
- Hard-failure call sites (pre-flight, `git push`) — keep their existing `SystemExit` semantics; pre-apply, no JSON to emit.

---

## Phase A — `PRResult` extension

### Task A1: Add `error` field to `PRResult`

**Files:**
- Modify: `nthlayer-workers/src/nthlayer_workers/learn/pr.py`
- Test: `nthlayer-workers/tests/learn/test_pr.py`

- [ ] **Step 1: Write failing test**

```python
def test_prresult_error_field_default_none():
    from nthlayer_workers.learn.pr import PRResult
    r = PRResult(url="https://github.com/org/repo/pull/1", number=1)
    assert r.error is None

def test_prresult_error_field_can_carry_message():
    from nthlayer_workers.learn.pr import PRResult
    r = PRResult(url=None, number=None, error="gh pr create failed: rate limit")
    assert r.error == "gh pr create failed: rate limit"
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd /Users/robfox/Documents/GitHub/nthlayer-ecosystem/nthlayer-workers
uv run pytest tests/learn/test_pr.py -v -k error_field
```

Expected: 2 FAILED — `PRResult` has no `error` field.

- [ ] **Step 3: Add field**

In `pr.py`, extend `PRResult`:

```python
@dataclass
class PRResult:
    url: str | None
    number: int | None
    error: str | None = None
```

Make `url` / `number` `Optional` if they aren't already (soft failure produces `None` for both).

- [ ] **Step 4: Run tests to verify they pass**

```bash
uv run pytest tests/learn/test_pr.py -v
```

Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add src/nthlayer_workers/learn/pr.py tests/learn/test_pr.py
git commit -m "feat(pr): add PRResult.error for soft-failure propagation · opensrm-jmy.25

Adds optional error field on PRResult so _run_pr_path can return a
structured failure to the caller instead of raising SystemExit.
Enables --json mode to emit a partial-failure document at end-of-run."
```

---

## Phase B — CLI `--json` wiring

### Task B1: Add `--json` flag and pre-flight check

**Files:**
- Modify: `nthlayer-workers/src/nthlayer_workers/learn/cli.py`
- Test: `nthlayer-workers/tests/learn/test_cli_recommendations.py`

- [ ] **Step 1: Write failing test**

```python
def test_json_requires_apply_to(capsys):
    """jmy.25: --json without --apply-to is rejected at pre-flight."""
    from nthlayer_workers.learn.cli import main
    with pytest.raises(SystemExit) as exc:
        main(["recommendations", "--from", "plan.yaml", "--json"])
    err = capsys.readouterr().err
    assert exc.value.code != 0
    assert "--json requires --apply-to" in err
```

- [ ] **Step 2: Run test to verify it fails**

Expected: FAIL — flag not yet defined; no pre-flight check.

- [ ] **Step 3: Add flag and pre-flight**

In `cli.py`, add `parser.add_argument("--json", action="store_true", help="Emit machine-readable JSON to stdout at end-of-run.")` to the `recommendations` subparser. After the existing `--pr` pre-flight (lines 182–183) add a sibling check:

```python
if args.json and not args.apply_to:
    parser.error("--json requires --apply-to")
```

- [ ] **Step 4: Run test to verify it passes**

```bash
uv run pytest tests/learn/test_cli_recommendations.py -v -k json_requires_apply_to
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/nthlayer_workers/learn/cli.py tests/learn/test_cli_recommendations.py
git commit -m "feat(cli): add --json flag with --apply-to pre-flight · opensrm-jmy.25

Additive flag on \`learn recommendations\`; pre-flight rejects --json
without --apply-to (mirrors --pr at cli.py:182-183). Plan-only JSON
output is out of scope per the design doc."
```

---

### Task B2: Refactor `_run_pr_path` soft-failure to return `PRResult`

**Files:**
- Modify: `nthlayer-workers/src/nthlayer_workers/learn/cli.py`
- Test: `nthlayer-workers/tests/learn/test_cli_recommendations.py`

- [ ] **Step 1: Write failing test**

```python
def test_run_pr_path_returns_error_result_on_gh_failure(monkeypatch):
    """jmy.25: soft PR failure returns PRResult(error=...) instead of raising."""
    from nthlayer_workers.learn.cli import _run_pr_path
    from nthlayer_workers.learn.pr import PRResult
    # Arrange: monkeypatch gh pr create to fail; ensure git push has succeeded.
    # Act: result = _run_pr_path(...)
    # Assert: isinstance(result, PRResult); result.error is not None;
    #         result.url is None; result.number is None.
```

- [ ] **Step 2: Run test to verify it fails**

Expected: FAIL — current code raises `SystemExit(1)` at line 312.

- [ ] **Step 3: Refactor soft-failure branch**

At `cli.py:312`, replace the `SystemExit(1)` raise with a `return PRResult(url=None, number=None, error=<captured gh stderr>)`. Keep hard-failure raises (preflight, `git push`) intact — they fire pre-apply, so JSON has no contract there.

Update the single caller of `_run_pr_path` to handle a `PRResult(error=...)` return: in non-JSON mode, print the error to stderr and `sys.exit(1)` (preserves current operator-visible behaviour); in JSON mode, fold the error into the end-of-run JSON doc (Task B4).

- [ ] **Step 4: Run test to verify it passes**

```bash
uv run pytest tests/learn/test_cli_recommendations.py -v -k run_pr_path_returns_error
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/nthlayer_workers/learn/cli.py tests/learn/test_cli_recommendations.py
git commit -m "refactor(cli): _run_pr_path returns PRResult on soft failure · opensrm-jmy.25

Replaces the internal SystemExit at cli.py:312 with a structured
PRResult(error=...) return so the caller can decide whether to emit
JSON (jmy.25) or re-raise. Hard failures (preflight, git push) keep
their SystemExit semantics — they fire pre-apply with no JSON contract."
```

---

### Task B3: Reroute `format_summary` to stderr in `--json` mode + suppress `PR created:` print

**Files:**
- Modify: `nthlayer-workers/src/nthlayer_workers/learn/cli.py`
- Test: `nthlayer-workers/tests/learn/test_cli_recommendations.py`

- [ ] **Step 1: Write failing tests**

```python
def test_json_mode_summary_goes_to_stderr(capsys, ...):
    # Drive a clean --apply-to run with --json; assert friendly summary
    # appears on stderr and not on stdout.

def test_json_mode_suppresses_pr_created_line(capsys, ...):
    # Drive --apply-to --pr --json with a successful PR; assert
    # 'PR created:' does NOT appear on stdout.
```

- [ ] **Step 2: Run tests to verify they fail**

Expected: FAIL — `format_summary` and the `PR created:` `print` both write to stdout today.

- [ ] **Step 3: Wire stream selection**

In `_cmd_recommendations`, gate the summary stream on `args.json`:

```python
summary_stream = sys.stderr if args.json else sys.stdout
print(format_summary(apply_result), file=summary_stream)
```

In the `--pr` success branch, guard the `PR created: <url>` print with `if not args.json:`. The URL is recoverable from `pr_url` in the end-of-run JSON.

- [ ] **Step 4: Run tests to verify they pass**

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/nthlayer_workers/learn/cli.py tests/learn/test_cli_recommendations.py
git commit -m "feat(cli): reroute summary to stderr in --json mode · opensrm-jmy.25

format_summary output and the 'PR created:' line are both rerouted
(stderr / suppressed) when --json is set so stdout carries only the
end-of-run JSON document. Operators debugging with --json still see
the friendly summary; CI consumes only stdout."
```

---

### Task B4: Build end-of-run JSON document

**Files:**
- Modify: `nthlayer-workers/src/nthlayer_workers/learn/cli.py`
- Test: `nthlayer-workers/tests/learn/test_cli_recommendations.py`

- [ ] **Step 1: Write failing tests**

```python
def test_json_clean_apply_shape(capsys, ...):
    # Drive --apply-to --json against a plan that applies cleanly.
    # Parse stdout as JSON; assert keys: applied (non-empty), skipped (empty),
    # pr_url is None, pr_number is None, exit_code == 0.

def test_json_skipped_shape(capsys, ...):
    # Drive against a plan that produces one skipped entry (drift_detected).
    # Assert skipped[0] keys: id, service, outcome == "drift_detected", detail.
    # Assert 'type' key is absent (per design 3.3).

def test_json_pr_success_shape(capsys, ...):
    # Drive --apply-to --pr --json with successful gh pr create.
    # Assert pr_url and pr_number present and non-null, exit_code == 0.

def test_json_pr_failure_shape(capsys, ...):
    # Drive --apply-to --pr --json with apply success but gh pr create failure.
    # Assert applied populated, skipped present, pr_url is None,
    # pr_number is None, pr_error is non-empty string, exit_code == 1.

def test_json_stdout_is_valid_json(capsys, ...):
    # Sanity: json.loads(stdout) succeeds; no human text bleeds into stdout.
```

- [ ] **Step 2: Run tests to verify they fail**

Expected: 5 FAILED — JSON doc not yet built.

- [ ] **Step 3: Wire the document**

After apply (and PR path, if requested), assemble the doc:

```python
if args.json:
    doc = {
        "applied": [
            {"id": a.id, "service": a.service, "field": a.field}
            for a in apply_result.applied
        ],
        "skipped": [
            {"id": s.id, "service": s.service, "outcome": s.outcome.value, "detail": s.detail}
            for s in apply_result.skipped
        ],
        "pr_url": pr_result.url if pr_result else None,
        "pr_number": pr_result.number if pr_result else None,
        "exit_code": 1 if (pr_result and pr_result.error) else 0,
    }
    if pr_result and pr_result.error:
        doc["pr_error"] = pr_result.error
    print(json.dumps(doc), file=sys.stdout)
    sys.exit(doc["exit_code"])
```

When `--pr` is not set, `pr_result` is `None` and `pr_url` / `pr_number` are emitted as `null`; `pr_error` is omitted. Without `--json`, the existing post-apply / post-PR flow is unchanged.

- [ ] **Step 4: Run tests to verify they pass**

```bash
uv run pytest tests/learn/test_cli_recommendations.py -v
```

Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add src/nthlayer_workers/learn/cli.py tests/learn/test_cli_recommendations.py
git commit -m "feat(cli): emit end-of-run JSON document in --json mode · opensrm-jmy.25

Builds a single JSON document from ApplyResult + PRResult at end-of-run.
Partial-failure (apply succeeds, PR fails) emits a structured doc with
pr_error and exit_code 1. CI sees apply outcome AND PR failure
structurally — no scraping required."
```

---

### Task B5: Exit-code parity test

**Files:**
- Test: `nthlayer-workers/tests/learn/test_cli_recommendations.py`

- [ ] **Step 1: Write test**

```python
def test_json_mode_exit_code_matches_non_json_mode(capsys, ...):
    # Run twice against the same plan: once without --json, once with.
    # Assert exit codes match (clean: 0/0; PR failure: 1/1).
```

Rationale: `--json` must not silently change exit codes. The JSON `exit_code` field mirrors `sys.exit()`.

- [ ] **Step 2: Run test to verify it passes**

Expected: PASS (no production change needed if Task B4 wired `sys.exit(doc["exit_code"])` correctly).

- [ ] **Step 3: Commit**

```bash
git add tests/learn/test_cli_recommendations.py
git commit -m "test(cli): assert exit-code parity between --json and non-JSON · opensrm-jmy.25

Locks the invariant that --json does not silently change exit codes
relative to the existing non-JSON behaviour."
```

---

## Phase C — Gates + R5

### Task C1: Local gates

- [ ] **pytest**

```bash
cd /Users/robfox/Documents/GitHub/nthlayer-ecosystem/nthlayer-workers
uv run pytest -q
```

Expected: all green; 8 new tests pass; no regressions in the existing CLI suite.

- [ ] **ruff**

```bash
uv run ruff check src/ tests/
```

- [ ] **mypy** (if configured in the repo's CI)

```bash
uv run mypy src/
```

### Task C2: R5 supervise

- [ ] Run `/r5-supervise jmy.25` to drive the 4-pass Rule-of-Five review (Correctness / Clarity / Edge Cases / Excellence) sequentially per the ecosystem-root protocol. Each pass: review → fix findings → commit → next pass. The supervisor coordinates via `.claude/r5-state.json` and the parallel-block hook prevents cross-session reviewer dispatches while state is in flight.

---

## References

- Spec: `nthlayer/docs/superpowers/specs/2026-05-29-jmy25-json-output-design.md`
- Bead: `opensrm-jmy.25`
- Foundation: `nthlayer-workers/src/nthlayer_workers/learn/cli.py::_cmd_recommendations`
- Outcome dataclass: `nthlayer-workers/src/nthlayer_workers/learn/apply.py::ApplyResult`
- PR result: `nthlayer-workers/src/nthlayer_workers/learn/pr.py::PRResult`
- Sibling precedent: `nthlayer/docs/superpowers/plans/2026-05-28-jmy23-financial-impact.md`
