# jmy.22 Interactive TUI Walkthrough for `learn recommendations` — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a `--interactive` boolean flag to `nthlayer-workers learn recommendations`. The TUI walks the operator through the post-filter recommendation set one rec at a time. Accept / reject / modify (inline YAML); on quit, the accepted set flows into the existing `apply_recommendations` pipeline (or `--output`). Pre-flight requires either `--apply-to` or `--output`, and is mutex with `--json`. Pure-logic module (`_interactive.py`) is built and unit-tested first; Textual `App` (`_interactive_app.py`) is the thin wrapper added after.

**Architecture:** Single-repo change in `nthlayer-workers`. Two new modules — `learn/_interactive.py` (pure, no Textual import) and `learn/_interactive_app.py` (Textual `App` + `Input` widget) — plus a flag + pre-flight + dispatch in `learn/cli.py`. Textual is a new runtime dependency declared in `pyproject.toml`. No changes to `_apply.py`, `recommendations.py`, `_preview.py`, or `pr.py`.

**Tech Stack:** Python 3.11+. Textual 1.0+ (new runtime dep). PyYAML (already a transitive dep via the plan parser).

**Spec:** `nthlayer/docs/superpowers/specs/2026-05-29-jmy22-interactive-tui-design.md`.

**Bead:** `opensrm-jmy.22`. Parent `opensrm-jmy.6` (Learn → Spec loop) shipped; sibling of jmy.24 (`--include` / `--exclude`).

---

## File structure

### Files added

| Path | Responsibility |
|---|---|
| `nthlayer-workers/src/nthlayer_workers/learn/_interactive.py` | Pure logic. `WalkthroughState` dataclass; pure transitions (`accept`, `reject`, `modify`, `next_rec`, `prev_rec`); `finalize(state) -> list[SpecRecommendation]`; `parse_yaml_value(text) -> Any` (raises `yaml.YAMLError`). No Textual import. |
| `nthlayer-workers/src/nthlayer_workers/learn/_interactive_app.py` | Textual `App` + `RecScreen` + modal `ModifyInput`. Imports `_interactive` for state and transitions. Reuses `_preview.build_preview` for the diff pane. Exposes `run_walkthrough(plan) -> list[SpecRecommendation]` as the dispatch entry point. |
| `nthlayer-workers/tests/learn/test_interactive.py` | Pure-logic unit tests (~10 tests; see Test plan). |

### Files modified

| Path | Responsibility |
|---|---|
| `nthlayer-workers/src/nthlayer_workers/learn/cli.py` | Add `--interactive` flag in `_add_recommendations_subcommand`; pre-flight rejects `--interactive` without `--apply-to` or `--output`; pre-flight rejects `--interactive --json` (mutex); dispatch calls `run_walkthrough(plan)` and rebinds `plan.recommendations` to the returned list. |
| `nthlayer-workers/pyproject.toml` | Add `textual>=1.0` runtime dependency. |
| `nthlayer-workers/tests/learn/test_cli_recommendations.py` | New `TestInteractiveFlag` class (~5 tests; see Test plan). |

### Files NOT modified

- `nthlayer-workers/src/nthlayer_workers/learn/_apply.py` — `apply_recommendations` consumed unchanged.
- `nthlayer-workers/src/nthlayer_workers/learn/_preview.py` — `build_preview` reused verbatim inside the Textual screen.
- `nthlayer-workers/src/nthlayer_workers/learn/recommendations.py` — plan parsing untouched.
- `nthlayer-workers/src/nthlayer_workers/learn/pr.py` — PR path runs over the accepted set transparently.

---

## Phase A — Pure logic + tests (no Textual)

### Task A1: `_interactive.py` pure module

**Files:**
- Add: `nthlayer-workers/src/nthlayer_workers/learn/_interactive.py`

- [ ] **Step 1: Write failing tests first** (see Task A2 — TDD; logic and tests land together).
- [ ] **Step 2: Implement the pure module**

```python
# learn/_interactive.py
from dataclasses import dataclass, field
from typing import Any
import yaml

from .recommendations import SpecRecommendation


@dataclass
class WalkthroughState:
    recs: list[SpecRecommendation]
    cursor: int = 0
    accepted: set[str] = field(default_factory=set)
    rejected: set[str] = field(default_factory=set)
    modifications: dict[str, Any] = field(default_factory=dict)

    @property
    def current(self) -> SpecRecommendation:
        return self.recs[self.cursor]


def accept(state: WalkthroughState) -> None:
    rid = state.current.id
    state.accepted.add(rid)
    state.rejected.discard(rid)


def reject(state: WalkthroughState) -> None:
    rid = state.current.id
    state.rejected.add(rid)
    state.accepted.discard(rid)


def modify(state: WalkthroughState, new_value: Any) -> None:
    state.modifications[state.current.id] = new_value


def next_rec(state: WalkthroughState) -> None:
    if state.cursor < len(state.recs) - 1:
        state.cursor += 1


def prev_rec(state: WalkthroughState) -> None:
    if state.cursor > 0:
        state.cursor -= 1


def parse_yaml_value(text: str) -> Any:
    """Parse the modify-input text. Raises yaml.YAMLError on failure."""
    return yaml.safe_load(text)


def finalize(state: WalkthroughState) -> list[SpecRecommendation]:
    """Return accepted recs with modifications applied to proposed_value."""
    result = []
    for rec in state.recs:
        if rec.id not in state.accepted:
            continue
        if rec.id in state.modifications:
            rec.proposed_value = state.modifications[rec.id]
        result.append(rec)
    return result
```

- [ ] **Step 3: Commit**

```bash
git add src/nthlayer_workers/learn/_interactive.py
git commit -m "feat(learn): add interactive walkthrough pure-logic module · opensrm-jmy.22

WalkthroughState dataclass + pure transitions (accept, reject, modify,
next_rec, prev_rec, finalize). No Textual import. Matches the bench
sre/+widgets/ split convention. Textual App lands in a follow-up task."
```

---

### Task A2: `test_interactive.py` — TDD per pure function

**Files:**
- Add: `nthlayer-workers/tests/learn/test_interactive.py`

- [ ] **Step 1: Write the tests** (alongside Task A1; TDD order — tests fail first, then A1's implementation makes them pass)

Tests to write:

1. `test_walkthrough_starts_at_first_rec` — cursor=0; `current` returns recs[0].
2. `test_accept_records_rec_id` — `accept(state)`; `state.current.id in state.accepted`.
3. `test_reject_records_rec_id` — `reject(state)`; in `rejected`.
4. `test_accept_then_reject_moves_to_rejected` — accept removes the prior reject vote and vice versa.
5. `test_modify_stores_new_value_keyed_by_rec_id` — `modify(state, 99.0)`; `state.modifications[rec.id] == 99.0`.
6. `test_next_rec_advances_cursor` — cursor 0 → 1.
7. `test_next_rec_stops_at_last` — cursor M-1 stays at M-1.
8. `test_prev_rec_stops_at_zero` — cursor 0 stays at 0.
9. `test_parse_yaml_value_handles_scalar_dict_list_invalid` — `99.5` → float, `{a: 1}` → dict, `[1,2]` → list, `[ unbalanced` → raises `yaml.YAMLError`.
10. `test_finalize_returns_accepted_with_modifications_applied` — three recs (A accepted+modified, B rejected, C accepted unmodified): result is `[A', C]` where `A'.proposed_value` reflects the modification; `C.proposed_value` unchanged.

- [ ] **Step 2: Run tests; verify they pass after Task A1's module exists**

```bash
cd /Users/robfox/Documents/GitHub/nthlayer-ecosystem/nthlayer-workers
uv run pytest tests/learn/test_interactive.py -v
```

- [ ] **Step 3: Commit**

```bash
git add tests/learn/test_interactive.py
git commit -m "test(learn): pure-logic tests for interactive walkthrough · opensrm-jmy.22

10 tests covering state transitions (accept, reject, modify, next, prev),
YAML parsing (scalar/dict/list/invalid), and finalize. Pure module — no
Textual harness needed."
```

---

## Phase B — Textual dep + App

### Task B1: Add `textual>=1.0` runtime dep

**Files:**
- Modify: `nthlayer-workers/pyproject.toml`

- [ ] **Step 1: Add the dep to the `[project] dependencies` list**

```toml
"textual>=1.0",
```

- [ ] **Step 2: Re-lock**

```bash
cd /Users/robfox/Documents/GitHub/nthlayer-ecosystem/nthlayer-workers
uv lock
```

- [ ] **Step 3: Commit**

```bash
git add pyproject.toml uv.lock
git commit -m "deps: add textual>=1.0 for interactive walkthrough · opensrm-jmy.22

Textual is the TUI framework for the new \`learn recommendations
--interactive\` flag. Pure-logic module already isolates the import
behind _interactive_app.py."
```

---

### Task B2: `_interactive_app.py` — Textual App on top of pure logic

**Files:**
- Add: `nthlayer-workers/src/nthlayer_workers/learn/_interactive_app.py`

- [ ] **Step 1: Implement the Textual App**

Shape:

```python
# learn/_interactive_app.py
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.screen import Screen
from textual.widgets import Footer, Header, Input, Static
import yaml

from . import _interactive
from ._preview import build_preview
from .recommendations import SpecRecommendation


class RecScreen(Screen):
    BINDINGS = [
        Binding("a", "accept", "accept"),
        Binding("r", "reject", "reject"),
        Binding("m", "modify", "modify"),
        Binding("n", "next", "next"),
        Binding("p", "prev", "prev"),
        Binding("q", "quit", "quit-and-apply"),
    ]
    # compose() yields Header / Static (diff pane) / Footer.
    # action_accept/reject/modify/next/prev call the pure transitions
    # and refresh the diff pane. action_quit calls App.exit() with the
    # finalized list as the exit value.


class WalkthroughApp(App):
    def __init__(self, state: _interactive.WalkthroughState):
        super().__init__()
        self.state = state

    def on_mount(self) -> None:
        self.push_screen(RecScreen())


def run_walkthrough(recs: list[SpecRecommendation]) -> list[SpecRecommendation]:
    """Dispatch entry point: drive the TUI; return finalized accepted set."""
    state = _interactive.WalkthroughState(recs=list(recs))
    app = WalkthroughApp(state)
    app.run()  # blocks until quit
    return _interactive.finalize(state)
```

Modify mode: `action_modify` pushes a modal screen containing an `Input` pre-filled with `yaml.safe_dump(state.current.proposed_value)`. On submit, the screen calls `_interactive.parse_yaml_value(input.value)` inside a try/except; success → `_interactive.modify(state, parsed)` + close modal; `yaml.YAMLError` → set an error `Static` line below the Input and keep the modal open. `Esc` key on the modal closes without committing.

- [ ] **Step 2: Smoke-run the app locally** (manual, optional — Textual headless test harness is out of scope; widget-level tests are noted as optional in the test plan).

- [ ] **Step 3: Commit**

```bash
git add src/nthlayer_workers/learn/_interactive_app.py
git commit -m "feat(learn): Textual app for interactive walkthrough · opensrm-jmy.22

Thin wrapper around the pure _interactive module. RecScreen carousel
with single-key bindings (a/r/m/n/p/q). Modify mode pushes a modal
Input pre-filled with yaml.safe_dump(proposed_value); parse errors
keep the modal open. run_walkthrough() is the dispatch entry point."
```

---

## Phase C — CLI wiring

### Task C1: Add `--interactive` flag + pre-flight + dispatch

**Files:**
- Modify: `nthlayer-workers/src/nthlayer_workers/learn/cli.py`
- Test: `nthlayer-workers/tests/learn/test_cli_recommendations.py`

- [ ] **Step 1: Write failing CLI tests** (Task C2 batch — tests written here, run after the production change)

- [ ] **Step 2: Add the flag**

In `_add_recommendations_subcommand`:

```python
p.add_argument(
    "--interactive",
    action="store_true",
    help="walk through recommendations one at a time in a TUI; "
         "requires --apply-to or --output; incompatible with --json",
)
```

- [ ] **Step 3: Add pre-flight**

In `_cmd_recommendations`, next to the jmy.24 `--include`/`--exclude` check:

```python
if args.interactive:
    if not (args.apply_to or args.output):
        raise SystemExit(
            "error: --interactive requires --apply-to or --output"
        )
    if args.json:
        raise SystemExit("error: --interactive is incompatible with --json")
```

- [ ] **Step 4: Add the dispatch**

After `--include` / `--exclude` filtering and before `--output` write / `apply_recommendations` call:

```python
if args.interactive:
    from ._interactive_app import run_walkthrough
    plan.recommendations = run_walkthrough(plan.recommendations)
```

The import is inside the if so the Textual import only happens when the flag is used (keeps CLI startup time honest for the non-interactive path).

- [ ] **Step 5: Commit**

```bash
git add src/nthlayer_workers/learn/cli.py
git commit -m "feat(cli): add --interactive flag + dispatch · opensrm-jmy.22

New boolean flag on \`learn recommendations\`. Pre-flight requires
either --apply-to or --output (the TUI's accept set has to flow
somewhere) and is mutex with --json (TUI owns stdout/stderr). Dispatch
runs the walkthrough, rebinds plan.recommendations to the accepted set,
then continues into the existing --output / --apply-to / --pr pipeline."
```

---

### Task C2: CLI integration tests

**Files:**
- Test: `nthlayer-workers/tests/learn/test_cli_recommendations.py`

- [ ] **Step 1: Write tests** (`TestInteractiveFlag` class, ~5 tests)

Tests:

1. `test_interactive_without_apply_to_or_output_rejected` — pre-flight error; exit code 2; stderr contains `--interactive requires --apply-to or --output`.
2. `test_interactive_with_json_rejected` — pre-flight error; stderr contains `--interactive is incompatible with --json`.
3. `test_interactive_with_output_only_accepted` — pre-flight passes with `--output` and no `--apply-to`; `run_walkthrough` is monkeypatched to return the input list; `--output` file is written.
4. `test_interactive_dispatch_calls_run_walkthrough_with_filtered_set` — combined with `--include rec-A`; monkeypatched `run_walkthrough` is called with `[rec-A]` only; result feeds `apply_recommendations`.
5. `test_interactive_accepted_set_flows_to_apply` — monkeypatched `run_walkthrough` returns a 2-rec subset; `ApplyResult.applied` covers those two; the third (rejected) rec is absent from `applied` and `skipped`.

The Textual app itself is monkeypatched (`monkeypatch.setattr("nthlayer_workers.learn._interactive_app.run_walkthrough", fake)`) — these tests cover the CLI contract, not the widget behaviour.

- [ ] **Step 2: Run tests; verify they pass**

```bash
uv run pytest tests/learn/test_cli_recommendations.py -v -k Interactive
```

- [ ] **Step 3: Commit**

```bash
git add tests/learn/test_cli_recommendations.py
git commit -m "test(cli): interactive walkthrough CLI integration · opensrm-jmy.22

5 tests cover pre-flight (apply-to/output requirement, --json mutex),
the dispatch wiring (run_walkthrough sees the post-filter set), and the
contract that the accepted set flows into apply_recommendations. The
Textual app is monkeypatched — widget behaviour is covered (optionally)
in a separate Textual harness."
```

---

## Phase D — Gates + R5

### Task D1: Local gates

- [ ] **pytest**

```bash
cd /Users/robfox/Documents/GitHub/nthlayer-ecosystem/nthlayer-workers
uv run pytest -q
```

Expected: all green; ~15 new tests (10 pure-logic + 5 CLI integration); no regressions.

- [ ] **ruff**

```bash
uv run ruff check src/ tests/
```

- [ ] **mypy** (if configured)

```bash
uv run mypy src/
```

### Task D2: R5 supervise

- [ ] Run `/r5-supervise jmy.22` to drive the 4-pass Rule-of-Five review (Correctness / Clarity / Edge Cases / Excellence) sequentially per the ecosystem-root protocol. Each pass: review → fix findings → commit → next pass. The supervisor coordinates via `.claude/r5-state.json`; the parallel-block hook prevents cross-session reviewer dispatches while state is in flight.

---

## Test plan (summary)

**Pure-logic** (`tests/learn/test_interactive.py`, ~10 tests):

1. `test_walkthrough_starts_at_first_rec`
2. `test_accept_records_rec_id`
3. `test_reject_records_rec_id`
4. `test_accept_then_reject_moves_to_rejected`
5. `test_modify_stores_new_value_keyed_by_rec_id`
6. `test_next_rec_advances_cursor`
7. `test_next_rec_stops_at_last`
8. `test_prev_rec_stops_at_zero`
9. `test_parse_yaml_value_handles_scalar_dict_list_invalid`
10. `test_finalize_returns_accepted_with_modifications_applied`

**CLI integration** (`tests/learn/test_cli_recommendations.py::TestInteractiveFlag`, ~5 tests):

1. `test_interactive_without_apply_to_or_output_rejected`
2. `test_interactive_with_json_rejected`
3. `test_interactive_with_output_only_accepted`
4. `test_interactive_dispatch_calls_run_walkthrough_with_filtered_set`
5. `test_interactive_accepted_set_flows_to_apply`

**Textual widget tests** — optional. The Textual `Pilot` harness exists; a smoke test that mounts `WalkthroughApp` and asserts the diff pane renders is welcome but not gating. The pure-logic + CLI-integration coverage is the contract.

---

## References

- Spec: `nthlayer/docs/superpowers/specs/2026-05-29-jmy22-interactive-tui-design.md`
- Bead: `opensrm-jmy.22`
- Foundation: `nthlayer-workers/src/nthlayer_workers/learn/cli.py::_cmd_recommendations`
- Diff renderer: `nthlayer-workers/src/nthlayer_workers/learn/_preview.py::build_preview` (jmy.6)
- Apply layer: `nthlayer-workers/src/nthlayer_workers/learn/_apply.py::apply_recommendations`
- Pure-widget split convention: `nthlayer-bench/src/nthlayer_bench/sre/` + `widgets/`
- Sibling: `nthlayer/docs/superpowers/plans/2026-05-29-jmy24-include-exclude.md` (non-interactive subsetting)
- Follow-ups: deferred-bucket bead (TBD if requested); TUI for retrospective inspection (broader bench surface)
