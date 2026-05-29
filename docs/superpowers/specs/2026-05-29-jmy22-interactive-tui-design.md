# Interactive TUI Walkthrough for `learn recommendations` Design (opensrm-jmy.22)

**Status:** Design-locked. Author: Rob Fox. Date: 2026-05-29. Bead: `opensrm-jmy.22`.

**Foundation:**
- `nthlayer-workers/src/nthlayer_workers/learn/cli.py::_cmd_recommendations` (line 183) — current orchestrator with `--from` / `--apply-to` / `--pr` / `--output` / `--json` plus `--include` / `--exclude` (jmy.24).
- `nthlayer-workers/src/nthlayer_workers/learn/_apply.py::apply_recommendations` — consumes `plan.recommendations` in order.
- `nthlayer-workers/src/nthlayer_workers/learn/_preview.py::build_preview` — diff renderer shipped in jmy.6; reused verbatim.
- `nthlayer-workers/src/nthlayer_workers/learn/recommendations.py::SpecRecommendation` — mutable dataclass; `proposed_value` is the field the operator can rewrite.
- Bench convention: `nthlayer-bench/src/nthlayer_bench/sre/` (pure logic) + `nthlayer-bench/src/nthlayer_bench/widgets/` (Textual). Pure-logic-first split is the house style.

---

## 1. Problem statement

`nthlayer-workers learn recommendations --apply-to <dir>` is an all-or-nothing apply. jmy.24 added `--include` / `--exclude` for non-interactive subsetting, but the operator still has to copy rec-ids out of a separate plan-print run, and there is no way to tweak a single `proposed_value` short of hand-editing the plan file (which destroys the deterministic id). jmy.22 adds an interactive carousel TUI — one rec at a time, accept / reject / modify — that flows the accepted set into the same `apply_recommendations` pipeline. The non-interactive `--include` / `--exclude` flags remain the scriptable surface; this bead adds the operator-driven path.

---

## 2. Existing surface

- `_cmd_recommendations` — orchestrator; current pre-flight rejects `--pr` / `--json` without `--apply-to` and `--include` / `--exclude` without `--apply-to` (jmy.24).
- `apply_recommendations(plan, …)` — iterates `plan.recommendations`; returns `ApplyResult(applied, skipped)`. Same consumer as today.
- `build_preview(rec) -> str` — colourised diff string for a single `SpecRecommendation`; used today in the plan-print path.
- `SpecRecommendation` — mutable dataclass; `proposed_value: Any`. Modifying it in place before `apply_recommendations` runs is supported by construction.
- Bench `sre/` + `widgets/` split — pure logic lives in `sre/`, Textual widgets in `widgets/`; same convention adopted here as `learn/_interactive.py` (pure) + `learn/_interactive_app.py` (Textual).

---

## 3. Decisions

### 3.1 Location: `learn recommendations --interactive`

A new boolean flag on the existing subcommand, not a sibling subcommand. Direct in-process composition with `--from`, `--apply-to`, `--pr`, `--include`, `--exclude`, `--output`. Textual becomes a workers runtime dependency (gated below the `learn` import boundary). Rationale: operators already know the subcommand; carving off `learn interactive` would force them to learn a second flag surface for the same plan.

### 3.2 Pure-logic + Textual-widget split

Two new modules mirroring the bench `sre/` + `widgets/` convention:

- `learn/_interactive.py` — no Textual import. Holds `WalkthroughState` dataclass (`recs: list[SpecRecommendation]`, `cursor: int`, `accepted: set[str]`, `rejected: set[str]`, `modifications: dict[str, Any]`), pure transition functions (`accept`, `reject`, `modify`, `next`, `prev`), and `finalize(state) -> list[SpecRecommendation]` returning the accepted-and-possibly-modified subset.
- `learn/_interactive_app.py` — Textual `App` + `Screen` + `Input` widget. Thin shell around the pure module.

Rationale: the bench split is the existing house pattern; pure logic is unit-testable without booting Textual; Textual widget tests stay optional.

### 3.3 Required flag combinations

Pre-flight rejects `--interactive` without **either** `--apply-to` or `--output`. The TUI's accept set must flow somewhere — apply to specs, or save the filtered plan. Mutex with `--json` (the TUI owns stdout/stderr; structured JSON output is incompatible with a terminal app driving the screen). Rationale: same tier as the jmy.24 `--pr requires --apply-to` check; an interactive walkthrough with no sink is dead-ended intent.

### 3.4 UI shape: carousel, one rec at a time

Header shows `[N of M]` plus rec metadata (service, field, type). Diff pane below reuses `_preview.build_preview`. Bindings footer at the bottom. Rationale: a single-rec-at-a-time carousel matches the operator's actual cognitive unit (one decision per screen); multi-select inside a screen is out of scope (see §5).

### 3.5 Bindings

- `a` — accept (current rec joins the accepted set)
- `r` — reject (current rec joins the rejected set)
- `m` — modify (open inline YAML Input on `proposed_value`)
- `n` — next
- `p` — previous
- `q` — quit and apply the accepted set
- `Esc` — cancel modify (only meaningful while modify Input is open)

Rationale: single-key bindings with mnemonic letters; `q` runs the apply rather than discarding because the operator's mental model of "I'm done" is "apply what I've decided so far."

### 3.6 Modify mechanic: inline YAML Input widget

When the operator hits `m`, dump the current `proposed_value` as YAML (`yaml.safe_dump`) into a Textual `Input` widget overlaid on the screen. Operator edits in place. On Enter: `yaml.safe_load`. Parse error → keep the Input open with a stderr error line (e.g. `parse error: <msg>`); operator can keep editing. `Esc` → close the Input, revert to the pre-edit value. Handles scalar, dict, and list shapes uniformly (YAML round-trips them all). Rationale: YAML is the on-disk format the operator already reads; a single Input handles every shape; round-tripping through `safe_load` gives the operator schema validation by way of "if it parses, it's a value."

### 3.7 Output buckets: accept + reject only

Two buckets — accepted and rejected. Rejected recs are discarded; accepted recs (with any modifications applied to `proposed_value`) flow into `apply_recommendations`. The deferred-bucket variant (3-way accept/reject/defer) is out of scope; file a follow-up bead if requested. Rationale: a two-bucket model matches the apply layer's existing semantics (recs are either applied or absent); a third "defer" bucket needs persistence we do not yet have.

### 3.8 Composition with `--include` / `--exclude`

The TUI sees the post-filter set. If `--include rec-A` is set, the walkthrough only shows rec-A. Rationale: filtering happens upstream of the TUI by construction; the operator's mental model is "narrow first, walk through what's left."

### 3.9 Composition with `--output`

The post-walkthrough plan (accepted recs with modifications applied) is written to `--output` before `--apply-to` runs. Mirrors jmy.24's post-filter ordering. Rationale: the file on disk reflects the operator's decisions; if `--apply-to` later errors, the plan-file artefact survives as the audit trail.

### 3.10 Composition with `--pr`

Standard pipeline: after `apply_recommendations` runs against the accepted set, the PR carries the post-walkthrough manifest changes. No special PR-mode behaviour. Rationale: `--pr` is a layer above apply; the interactive flow lands above both.

---

## 4. TUI sketch

```
┌─────────────────────────────────────────────────────────────────────┐
│ Recommendation [2 of 7]  rec-abc123def012                           │
│ Service: fraud-detect   Field: slo.target   Type: relax_target      │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│   slo:                                                              │
│ -   target: 99.9                                                    │
│ +   target: 99.5                                                    │
│                                                                     │
│   Rationale: 28-day budget exhausted twice; trailing window         │
│   suggests 99.5 is the achievable bar.                              │
│                                                                     │
├─────────────────────────────────────────────────────────────────────┤
│ [a]ccept  [r]eject  [m]odify  [n]ext  [p]rev  [q]uit-and-apply      │
└─────────────────────────────────────────────────────────────────────┘
```

Modify mode (overlay):

```
├─────────────────────────────────────────────────────────────────────┤
│ Modify proposed_value (YAML; Enter to confirm, Esc to cancel):     │
│ > 99.5                                                              │
└─────────────────────────────────────────────────────────────────────┘
```

---

## 5. Modify-mechanic examples

Scalar (`proposed_value: 99.5`) → Input shows `99.5`. Operator types `99.0`, hits Enter → `yaml.safe_load("99.0")` → `99.0` (float). Stored on the rec.

Dict (`proposed_value: {target: 99.9, window: 28d}`) →
```yaml
target: 99.9
window: 28d
```
Operator edits → Enter → parsed back to dict.

Invalid YAML (`proposed_value: 99.5` → operator types `[ unbalanced`) → on Enter, `yaml.YAMLError` raised. Input stays open; error line below shows `parse error: while parsing a flow node`. Operator fixes or hits `Esc` to revert.

---

## 6. Out of scope

| Concern | Why deferred |
|---|---|
| Deferred bucket (3-way accept/reject/defer) | Two-bucket model matches the apply layer; defer needs persistence. |
| Mouse support | Keyboard-only matches the operator's expected workflow (ssh, tmux). |
| Multi-select within a single screen | Carousel model is one decision per screen; multi-select is a different shape. |
| `$EDITOR` popup for modify | Inline YAML Input handles every value shape; `$EDITOR` is a feature creep. |
| TUI replay / undo | Decisions are recorded into `WalkthroughState`; undo is a future enhancement. |
| Color theming | Textual defaults are good enough; theming is a separate concern. |

---

## 7. Follow-ups

- Deferred-bucket bead (later, if operators ask for the 3-way workflow).
- TUI for retrospective inspection — broader bench surface, separate concern; this bead is scoped to the `learn recommendations` apply flow only.

---

## 8. References

- Bead: `opensrm-jmy.22`.
- Foundation: `nthlayer-workers/src/nthlayer_workers/learn/cli.py::_cmd_recommendations`.
- Diff renderer: `nthlayer-workers/src/nthlayer_workers/learn/_preview.py::build_preview` (jmy.6).
- Apply layer: `nthlayer-workers/src/nthlayer_workers/learn/_apply.py::apply_recommendations`.
- Pure-widget split convention: `nthlayer-bench/src/nthlayer_bench/sre/` + `widgets/`.
- Sibling: `nthlayer/docs/superpowers/specs/2026-05-29-jmy24-include-exclude-design.md` (non-interactive subsetting).
