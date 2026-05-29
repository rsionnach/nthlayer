# jmy.24 `--include` / `--exclude` per-rec Filtering — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add two additive flags — `--include <id>[,...]` and `--exclude <id>[,...]` — to `nthlayer-workers learn recommendations`. Mutually exclusive (argparse-enforced). Both require `--apply-to`. Unknown ids are a hard error (exit 2) reporting all unknowns in one message. Filter mutates `plan.recommendations` between `parse_plan_file` and `apply_recommendations`. `--json` reflects the filtered set by construction.

**Architecture:** Single-repo change in `nthlayer-workers`. Two flags added inside a mutually-exclusive group on the `recommendations` subparser. Pre-flight check in `_cmd_recommendations` mirrors `--pr` / `--json`. Filter logic inserted between `parse_plan_file` (cli.py:193) and `apply_recommendations` (cli.py:207); rebinds `plan.recommendations` to the surviving list. No changes to `apply.py`, `recommendations.py`, or `pr.py`.

**Tech Stack:** Python 3.11+. Stdlib only.

**Spec:** `nthlayer/docs/superpowers/specs/2026-05-29-jmy24-include-exclude-design.md`.

**Bead:** `opensrm-jmy.24`. Parent `opensrm-jmy.6` (Learn → Spec loop) shipped; sibling of jmy.25 (`--json`).

---

## File structure

### Files modified

| Path | Responsibility |
|---|---|
| `nthlayer-workers/src/nthlayer_workers/learn/cli.py` | Add `--include` and `--exclude` to `_add_recommendations_subcommand` via `add_mutually_exclusive_group`; add pre-flight check (`--include`/`--exclude` requires `--apply-to`); insert filter logic in `_cmd_recommendations` between `parse_plan_file` and `apply_recommendations`; unknown-id detection collects all unknowns and raises `SystemExit` with exit code 2. |
| `nthlayer-workers/tests/learn/test_cli_recommendations.py` | New `TestIncludeExcludeFlags` class with 8 tests (see Test plan). |

### Files NOT modified

- `nthlayer-workers/src/nthlayer_workers/learn/_apply.py` — `apply_recommendations` consumed unchanged; empty-plan path already exits 0.
- `nthlayer-workers/src/nthlayer_workers/learn/recommendations.py` — plan parsing untouched.
- `nthlayer-workers/src/nthlayer_workers/learn/pr.py` — PR path untouched; runs against the filtered plan transparently.

---

## Phase A — argparse wiring

### Task A1: Add mutually-exclusive `--include` / `--exclude` group

**Files:**
- Modify: `nthlayer-workers/src/nthlayer_workers/learn/cli.py`
- Test: `nthlayer-workers/tests/learn/test_cli_recommendations.py`

- [ ] **Step 1: Write failing test**

```python
class TestIncludeExcludeFlags:
    def test_include_and_exclude_are_mutually_exclusive(self, capsys):
        """jmy.24: --include and --exclude cannot be combined (argparse)."""
        from nthlayer_workers.learn.cli import main
        with pytest.raises(SystemExit) as exc:
            main([
                "recommendations", "--from", "plan.yaml",
                "--apply-to", "specs/",
                "--include", "rec-aaa",
                "--exclude", "rec-bbb",
            ])
        err = capsys.readouterr().err
        assert exc.value.code != 0
        assert "not allowed with" in err or "mutually exclusive" in err
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd /Users/robfox/Documents/GitHub/nthlayer-ecosystem/nthlayer-workers
uv run pytest tests/learn/test_cli_recommendations.py -v -k mutually_exclusive
```

Expected: FAIL — flags do not yet exist.

- [ ] **Step 3: Add mutex group + flags**

In `_add_recommendations_subcommand` (cli.py:148), add inside the subparser:

```python
filter_group = p.add_mutually_exclusive_group()
filter_group.add_argument(
    "--include",
    dest="include_ids",
    default=None,
    help="rec-ids (comma-separated) to apply; mutually exclusive with --exclude",
)
filter_group.add_argument(
    "--exclude",
    dest="exclude_ids",
    default=None,
    help="rec-ids (comma-separated) to skip; mutually exclusive with --include",
)
```

- [ ] **Step 4: Run test to verify it passes**

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/nthlayer_workers/learn/cli.py tests/learn/test_cli_recommendations.py
git commit -m "feat(cli): add --include/--exclude mutex group on recommendations · opensrm-jmy.24

Two new flags on \`learn recommendations\`. Mutual exclusion is
argparse-owned (add_mutually_exclusive_group), no hand-rolled check.
Pre-flight + filter logic land in follow-up tasks."
```

---

## Phase B — Pre-flight + filter

### Task B1: Pre-flight (`--include`/`--exclude` requires `--apply-to`)

**Files:**
- Modify: `nthlayer-workers/src/nthlayer_workers/learn/cli.py`
- Test: `nthlayer-workers/tests/learn/test_cli_recommendations.py`

- [ ] **Step 1: Write failing test**

```python
def test_include_requires_apply_to(self, capsys):
    """jmy.24: --include without --apply-to is rejected at pre-flight."""
    from nthlayer_workers.learn.cli import main
    with pytest.raises(SystemExit) as exc:
        main(["recommendations", "--from", "plan.yaml", "--include", "rec-aaa"])
    err = capsys.readouterr().err
    assert "--include/--exclude requires --apply-to" in err

def test_exclude_requires_apply_to(self, capsys):
    from nthlayer_workers.learn.cli import main
    with pytest.raises(SystemExit) as exc:
        main(["recommendations", "--from", "plan.yaml", "--exclude", "rec-aaa"])
    err = capsys.readouterr().err
    assert "--include/--exclude requires --apply-to" in err
```

- [ ] **Step 2: Run tests to verify they fail**

Expected: FAIL — pre-flight not yet wired.

- [ ] **Step 3: Add pre-flight check**

In `_cmd_recommendations` next to the existing `--pr` / `--json` checks (cli.py:187/189):

```python
if (args.include_ids or args.exclude_ids) and not args.apply_to:
    raise SystemExit("error: --include/--exclude requires --apply-to")
```

- [ ] **Step 4: Run tests to verify they pass**

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/nthlayer_workers/learn/cli.py tests/learn/test_cli_recommendations.py
git commit -m "feat(cli): require --apply-to for --include/--exclude · opensrm-jmy.24

Pre-flight rejects either filter flag without --apply-to (mirrors the
existing --pr / --json checks at cli.py:187/189). Filtering a non-apply
path is a no-op masquerading as intent."
```

---

### Task B2: Apply the filter to `plan.recommendations`

**Files:**
- Modify: `nthlayer-workers/src/nthlayer_workers/learn/cli.py`
- Test: `nthlayer-workers/tests/learn/test_cli_recommendations.py`

- [ ] **Step 1: Write failing tests**

```python
def test_include_applies_subset(self, tmp_path, ...):
    """jmy.24: --include keeps only the listed ids."""
    # Arrange: plan with 3 recs (rec-A, rec-B, rec-C).
    # Act: run with --include rec-A,rec-C.
    # Assert: ApplyResult.applied covers rec-A and rec-C only;
    #         rec-B does not appear in applied or skipped.

def test_exclude_applies_complement(self, tmp_path, ...):
    """jmy.24: --exclude drops the listed ids; remainder is applied."""
    # Arrange: plan with 3 recs.
    # Act: run with --exclude rec-B.
    # Assert: applied covers rec-A and rec-C only.

def test_exclude_all_exits_zero(self, tmp_path, capsys, ...):
    """jmy.24: --exclude that removes every rec exits 0 with empty apply."""
    # Arrange: plan with 2 recs (rec-A, rec-B).
    # Act: --exclude rec-A,rec-B.
    # Assert: exit code 0; format_summary prints 'Applied: 0 / Skipped: 0'.
```

- [ ] **Step 2: Run tests to verify they fail**

Expected: FAIL — filter not yet applied.

- [ ] **Step 3: Wire the filter**

Between `parse_plan_file` (cli.py:193) and `apply_recommendations` (cli.py:207):

```python
if args.include_ids or args.exclude_ids:
    plan.recommendations = _apply_id_filter(
        plan.recommendations,
        include=args.include_ids,
        exclude=args.exclude_ids,
    )
```

Add module-local helper `_apply_id_filter(recs, *, include, exclude) -> list[SpecRecommendation]`:

```python
def _apply_id_filter(recs, *, include, exclude):
    known = {r.id for r in recs}
    requested = include or exclude
    requested_ids = [s.strip() for s in requested.split(",") if s.strip()]
    unknown = [rid for rid in requested_ids if rid not in known]
    if unknown:
        joined = ", ".join(f"'{u}'" for u in unknown)
        raise SystemExit(
            f"error: --include/--exclude id {joined} not found in plan"
        )
    if include is not None:
        keep = set(requested_ids)
        return [r for r in recs if r.id in keep]
    drop = set(requested_ids)
    return [r for r in recs if r.id not in drop]
```

`SystemExit` with a string message produces exit code 2 (argparse convention; consistent with the existing `--pr` / `--json` pre-flight errors).

- [ ] **Step 4: Run tests to verify they pass**

```bash
uv run pytest tests/learn/test_cli_recommendations.py -v -k "include or exclude"
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/nthlayer_workers/learn/cli.py tests/learn/test_cli_recommendations.py
git commit -m "feat(cli): filter plan.recommendations by --include/--exclude · opensrm-jmy.24

Filter mutates plan.recommendations between parse_plan_file and
apply_recommendations. Empty filtered plan exits 0 (legitimate
preview-only workflow). --json reflects the filtered set by
construction — the apply layer never sees filtered-out recs."
```

---

### Task B3: Unknown-id hard error (collect all)

**Files:**
- Modify: `nthlayer-workers/src/nthlayer_workers/learn/cli.py` (covered in B2; this task adds the tests)
- Test: `nthlayer-workers/tests/learn/test_cli_recommendations.py`

- [ ] **Step 1: Write failing tests**

```python
def test_include_unknown_id_hard_error(self, tmp_path, capsys, ...):
    """jmy.24: unknown id in --include raises SystemExit (exit code 2)."""
    # Arrange: plan with rec-A only.
    # Act: --include rec-NOPE.
    # Assert: SystemExit; exit code == 2; stderr contains 'not found in plan'
    #         and the offending id.

def test_multiple_unknown_ids_reported_together(self, tmp_path, capsys, ...):
    """jmy.24: all unknown ids appear in a single error message."""
    # Arrange: plan with rec-A.
    # Act: --include rec-NOPE1,rec-NOPE2.
    # Assert: stderr message names both rec-NOPE1 and rec-NOPE2 in one line.
```

- [ ] **Step 2: Run tests to verify they pass** (B2 already wired the logic)

Expected: PASS.

- [ ] **Step 3: Commit**

```bash
git add tests/learn/test_cli_recommendations.py
git commit -m "test(cli): assert unknown-id hard error reports all unknowns · opensrm-jmy.24

Locks the invariant that --include/--exclude collects all unknown ids
into a single error message rather than short-circuiting on the first.
Avoids the fix-one-find-next loop for operators."
```

---

### Task B4: `--json` reflects filtered set

**Files:**
- Test: `nthlayer-workers/tests/learn/test_cli_recommendations.py`

- [ ] **Step 1: Write failing test**

```python
def test_json_mode_reflects_filtered_set(self, tmp_path, capsys, ...):
    """jmy.24: --exclude removes recs from --json's applied/skipped arrays."""
    # Arrange: plan with rec-A, rec-B, rec-C.
    # Act: --apply-to specs/ --exclude rec-B --json.
    # Assert: json.loads(stdout)['applied'] ids are subset of {rec-A, rec-C};
    #         no entry has id == 'rec-B' in either applied or skipped.
```

- [ ] **Step 2: Run test to verify it passes** (no production change needed; the filter runs upstream of `apply_recommendations`, which is what `--json` reads)

Expected: PASS.

- [ ] **Step 3: Commit**

```bash
git add tests/learn/test_cli_recommendations.py
git commit -m "test(cli): assert --json reflects --include/--exclude filtered set · opensrm-jmy.24

Sibling-flag interaction test. The filter runs upstream of
apply_recommendations, so the --json document's applied/skipped arrays
exclude filtered recs by construction. This test locks the contract."
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

- [ ] Run `/r5-supervise jmy.24` to drive the 4-pass Rule-of-Five review (Correctness / Clarity / Edge Cases / Excellence) sequentially per the ecosystem-root protocol. Each pass: review → fix findings → commit → next pass. The supervisor coordinates via `.claude/r5-state.json`; the parallel-block hook prevents cross-session reviewer dispatches while state is in flight.

---

## Test plan (summary)

`TestIncludeExcludeFlags` in `nthlayer-workers/tests/learn/test_cli_recommendations.py`:

1. `test_include_and_exclude_are_mutually_exclusive` — argparse rejects both flags together.
2. `test_include_requires_apply_to` — pre-flight rejects `--include` without `--apply-to`.
3. `test_exclude_requires_apply_to` — pre-flight rejects `--exclude` without `--apply-to`.
4. `test_include_applies_subset` — `--include rec-A,rec-C` keeps only those recs.
5. `test_exclude_applies_complement` — `--exclude rec-B` drops only that rec.
6. `test_include_unknown_id_hard_error` — unknown id → `SystemExit` with exit code 2.
7. `test_multiple_unknown_ids_reported_together` — all unknowns in one message.
8. `test_exclude_all_exits_zero` — fully-emptied plan exits 0; summary prints `Applied: 0`.
9. `test_json_mode_reflects_filtered_set` — filtered recs absent from `--json` `applied`/`skipped`.

(Test plan deliberately overshoots the original "8" count by one — the `--json` interaction test is load-bearing for the sibling-flag contract.)

---

## References

- Spec: `nthlayer/docs/superpowers/specs/2026-05-29-jmy24-include-exclude-design.md`
- Bead: `opensrm-jmy.24`
- Foundation: `nthlayer-workers/src/nthlayer_workers/learn/cli.py::_cmd_recommendations`
- Plan parser: `nthlayer-workers/src/nthlayer_workers/learn/recommendations.py::parse_plan_file`
- Apply layer: `nthlayer-workers/src/nthlayer_workers/learn/_apply.py::apply_recommendations`
- Deterministic id: `compute_rec_id` (shipped in jmy.6)
- Sibling precedent: `nthlayer/docs/superpowers/plans/2026-05-29-jmy25-json-output.md`
- Follow-up: `opensrm-jmy.22` (interactive per-rec selection)
