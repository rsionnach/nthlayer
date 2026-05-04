# P4 — Bench `brief` Command Design

**Date:** 2026-04-28
**Phase:** P4 (nthlayer-bench)
**Bead:** opensrm-81rn.4 (case detail with reasoning capture)
**Source migration:** `nthlayer-respond/feat/opensrm-0rg-cli` (commits `8e80122` + `4fa616e`), `src/nthlayer_respond/sre/brief.py`
**Inventory reference:** `docs/superpowers/specs/2026-04-26-respond-sre-cli-inventory-for-bench.md`

## Context

`brief` is the highest-priority operator surface migrating from the deprecated `nthlayer-respond` SRE CLI into nthlayer-bench. It answers the SRE's first question after being paged: *what's broken, why, and what can I do about it?* Every field traces to a verdict — no LLM call, no hallucination.

In the bench, the brief auto-renders in the case-detail right pane when an operator selects a case in the case bench. It updates live as new verdicts arrive in the case's lineage.

This spec covers the **logic module** (pure async, no UI deps) and the **Textual widget** that consumes it. Implementation lives under bead opensrm-81rn.4 in Phase 4.

## Architectural Decisions

### Input identity: `case_id`

The brief takes `case_id`. Cases are the Tier 1 first-class concept the bench surfaces; the case-detail panel already has the case loaded; passing `case_id` to brief is a one-line invocation.

Rejected alternatives:
- `incident_id` (legacy v1.0 shape) — not a first-class v1.5 concept; would require client-side filtering since `metadata.custom` isn't a query parameter on `GET /verdicts`.
- A triage `verdict_id` directly — inverts responsibility. Each caller would have to find the right verdict from the case before invoking brief.

### Lineage anchor: `case.underlying_verdict`

The case schema (nthlayer-core/store.py:58) has `underlying_verdict TEXT NOT NULL`, set at case creation. It is the verdict that triggered the case (typically a `quality_breach` or `correlation_snapshot`). It is distinct from `resolution_id`, which is set only on resolved cases.

The brief walks **descendants** of `underlying_verdict` to find the response chain (triage → correlation → remediation). It does not walk from `resolution_id`, which is at the end of the chain (or absent for open cases).

### Brief shape: current-state snapshot, not chronological narrative

The right pane in case-detail answers "what does the operator need to know *right now*". For each role in the response chain, the brief shows the **latest** verdict of that role:

- `triage` (subject_type) → severity, summary, blast_radius
- `correlation` → likely_cause, cause_confidence
- `remediation` → recommended_action

Chronological narrative is the responsibility of the `post-incident` command, which renders the full timeline from trigger to resolution. Brief and post-incident share the lineage walk but project different views.

Note on subject types: v1.5 retains `subject.type = "triage"` / `"correlation"` / `"remediation"` as the legacy verdict role labels. The newer `verdict_type` field (`VALID_VERDICT_TYPES`: `quality_breach`, `correlation_snapshot`, `action_request`, etc.) is orthogonal — it classifies envelope semantics. The brief filters on `subject.type` because that's what respond actually emits today and what matches the legacy logic. If a future migration changes role taxonomy, the role-mapping dict in `brief.py` is the single point of change.

### Tie-breaking on simultaneous verdicts

When multiple verdicts of the same role have identical `created_at` timestamps, ties are broken by `verdict_id` (deterministic but arbitrary). At v1.5 demo scale this is unlikely to matter; if production usage surfaces ordering issues, switch to a chain-depth tiebreaker via `parent_ids` walk.

### Async throughout

`build_paging_brief` is `async`. CoreAPIClient is async-only; bench is a Textual app (already async). No sync bridge.

### Dependency: structured remediation emission (Bead 1)

The brief reads `recommended_action` from `metadata.custom["proposed_action"]` and `recommended_target` from `metadata.custom["target"]` on the latest remediation verdict. These keys do not exist in v1.5 respond's current emission shape — the action name is currently embedded only in human-readable strings (`subject.summary`, `judgment.reasoning`). Bead 1 ("Respond — structured remediation emission") adds these structured fields across four emission sites: agent normal path (`agents/base.py:482` via `_emit_verdict`), agent degraded path (`_degraded_verdict` — `proposed_action` is `None`), coordinator approve success (`coordinator.py:142–155`), coordinator approve failure (`coordinator.py:166–180`). Bead 2 (this brief) blocks on Bead 1 landing and a 24h soak in main.

**v1.5 scope.** Bead 1 emits `proposed_action` and `target` only. Action-specific parameters (rollback target version, scale_up replica count, restart graceful-timeout, etc.) are deferred to v2 — at v1.5 demo scale, the action+target pair conveys enough for operator comprehension.

### Logic / UI separation

```
nthlayer-bench/src/nthlayer_bench/
  sre/
    __init__.py
    brief.py           # Pure async logic. Imports CoreAPIClient. No UI deps.
  widgets/
    __init__.py
    case_brief.py      # Textual widget. Calls brief.py. Renders state-aware UI.
```

Tests, future CLI wrappers, and HTTP handlers can all import `sre.brief` without dragging Textual in.

## Public API

### `nthlayer_bench.sre.brief`

```python
from dataclasses import dataclass, field
from typing import Literal

BriefState = Literal[
    "minimal",                  # Anchor verdict only; no respond chain yet
    "triage_complete",          # Triage verdict present
    "investigation_complete",   # Triage + correlation present
    "remediation_proposed",     # Triage + correlation + remediation present
]

@dataclass
class PagingBrief:
    case_id: str
    service: str
    severity: int | None
    summary: str
    likely_cause: str | None = None
    cause_confidence: float | None = None
    blast_radius: list[str] = field(default_factory=list)
    recommended_action: str | None = None
    recommended_target: str | None = None
    state: BriefState = "minimal"
    awaiting: list[str] = field(default_factory=list)


class BriefError(Exception):
    """Raised when the brief cannot be built."""


class CaseNotFoundError(BriefError): ...
class AnchorVerdictMissingError(BriefError): ...
class CoreUnreachableError(BriefError): ...


async def build_paging_brief(
    client: CoreAPIClient,
    case_id: str,
) -> PagingBrief: ...


def render_brief(brief: PagingBrief) -> str:
    """Render a PagingBrief to plain text. Used by tests and any future CLI wrapper."""
```

### Algorithm

```
1. case_result = await client.get_case(case_id)
   - status_code 404 → raise CaseNotFoundError(case_id)
   - status_code 0 (connection_failed) → raise CoreUnreachableError
   - other non-2xx → raise BriefError with detail

2. anchor_id = case["underlying_verdict"]
   service   = case["service"] or "unknown"

3. anchor_result = await client.get_verdict(anchor_id)
   - 404 → raise AnchorVerdictMissingError(anchor_id) (data integrity issue worth surfacing)

4. desc_result = await client.get_descendants(anchor_id)
   - non-2xx → raise CoreUnreachableError(detail)

5. chain = [anchor] + descendants
   sorted descending by (created_at, verdict_id)

6. latest_by_role: dict[str, dict] = {}
   for v in chain (already sorted desc):
       role = v["subject"]["type"]
       latest_by_role.setdefault(role, v)

7. triage      = latest_by_role.get("triage")
   correlation = latest_by_role.get("correlation")
   remediation = latest_by_role.get("remediation")

8. severity      = triage["metadata"]["custom"].get("severity") if triage else None
   blast_radius  = triage["metadata"]["custom"].get("blast_radius", []) if triage else []
   summary       = triage["judgment"]["reasoning"] if triage else anchor["judgment"]["reasoning"]

9. likely_cause = correlation["judgment"]["reasoning"] if correlation else None
   cause_confidence = correlation["judgment"]["confidence"] if correlation else None

10. recommended_action =
       remediation["metadata"]["custom"].get("proposed_action") if remediation else None
    recommended_target =
       remediation["metadata"]["custom"].get("target") if remediation else None
    (Renderer composes "{proposed_action} on {target}" when both present;
     falls back to proposed_action alone if target is None;
     None if proposed_action is None — degraded path or pre-remediation.)

11. state, awaiting = derive_state(triage, correlation, remediation)
       (none)                       → "minimal",                awaiting=["triage","correlation","remediation"]
       (triage)                     → "triage_complete",        awaiting=["correlation","remediation"]
       (triage, correlation)        → "investigation_complete", awaiting=["remediation"]
       (triage, correlation, rem)   → "remediation_proposed",   awaiting=[]
   (Inconsistency case: correlation present but triage absent is treated as "minimal"
   with the anchor as summary source. This shouldn't occur in v1.5's respond pipeline
   — triage emits first; encountering it indicates system inconsistency. Brief handles
   defensively; an OTel event flagging the anomaly belongs in respond's instrumentation,
   not in brief.)

12. return PagingBrief(...)
```

### Renderer

`render_brief(brief)` — text output, faithful to the legacy renderer's shape so anyone reading the v1.0 brief code can recognise the output. Differences from legacy:

- Adds a state line after the severity line: `Status: investigation_complete (awaiting: remediation)` when state ≠ `remediation_proposed`. Operators reading the rendered text see lifecycle state at a glance.
- `severity is None` (legacy defaulted to 3) renders as `Severity: unknown`. Don't fabricate a P3.

## Textual widget

`nthlayer_bench.widgets.case_brief.CaseBriefPanel` — a `Static`-derived widget mounted in the case-detail right pane.

Behaviour:
- Constructed with `(client: CoreAPIClient, case_id: str)`.
- On mount: schedules `_refresh()` via `call_later`, then `set_interval(5.0, self._refresh)` for live updates.
- `_refresh()` calls `build_paging_brief(client, case_id)` and updates content. On `BriefError` subclasses, renders an inline error state (not a popup) — the case-detail pane should never be empty.
- Renders state-aware visuals:
  - `minimal` → "Awaiting triage" header + service/summary from anchor.
  - `triage_complete` → triage info; "Investigation in progress" placeholder for likely_cause.
  - `investigation_complete` → triage + cause; "Awaiting remediation" placeholder for recommended_action.
  - `remediation_proposed` → all fields populated; no placeholders.

The widget never blocks the event loop — all I/O is async. Refresh interval is 5s (matches the existing `ConnectionStatus` cadence). When the user navigates away from the case, the widget's `on_unmount` clears the interval.

The 5s polling interval continues regardless of case state. Terminal cases (resolved, escalated) don't generate new verdicts, so polling is wasteful but harmless at v1.5 scale. v2 should consider backing off polling interval on terminal cases or stopping entirely until manual refresh.

The widget itself does **not** render text via `render_brief`. It uses Textual primitives (`Static`, `Label`) for richer formatting. `render_brief` exists for tests and any future text-only consumer.

## Testing

### Unit tests for `sre/brief.py` (`tests/test_sre_brief.py`)

Mock `CoreAPIClient` (`AsyncMock`); inject `APIResult` payloads representing real HTTP responses. Tests use the JSON dict shape returned by core's `GET /verdicts/...`, not the dataclass `Verdict` model — bench is HTTP-only, so the logic operates on dicts.

Cases:
1. **Happy path with full chain** — anchor + triage + correlation + remediation → `state="remediation_proposed"`, all fields populated (`recommended_action` and `recommended_target` both set from `metadata.custom`).
2. **Triage only** — `state="triage_complete"`, `awaiting=["correlation","remediation"]`, `recommended_action is None`, `likely_cause is None`.
3. **Triage + correlation, no remediation** — `state="investigation_complete"`, `awaiting=["remediation"]`.
4. **Anchor only (no respond chain)** — `state="minimal"`, `summary` taken from anchor, `severity is None`.
5. **Latest-of-role selection** — multiple triage verdicts, only the most recent (by `created_at`) is used.
6. **Tie-breaker** — two triage verdicts with identical `created_at`, the one with the higher `verdict_id` wins. Documents the chosen rule.
7. **Severity missing from custom** — `state="triage_complete"`, `severity is None`. Don't fabricate.
8. **Blast radius missing** — `blast_radius == []`.
9. **404 on case** — raises `CaseNotFoundError`.
10. **404 on anchor verdict** (data integrity edge case) — raises `AnchorVerdictMissingError`.
11. **Connection failed on get_descendants** — raises `CoreUnreachableError`.
12. **Correlation without triage** (system inconsistency) — treated as `state="minimal"`. Triage is required for any non-minimal state.
13. **Anchor reasoning fallback** — case has anchor verdict but no triage. The brief uses `anchor["judgment"]["reasoning"]` as the `summary`. Locks in the fallback so future refactors don't silently break minimal-state summaries.
14. **Remediation with `proposed_action` set, `target` unset** — `recommended_action == "rollback"`, `recommended_target is None`. Renderer falls back to `recommended_action` alone (no "on {target}" suffix).
15. **Degraded remediation** — remediation verdict has `metadata.custom["proposed_action"] is None` (agent hit degraded path). `recommended_action is None`. State is still `remediation_proposed` (a remediation verdict was emitted) but renderer surfaces "manual intervention required".

### Renderer tests (same file)

Cover legacy parity (severity emoji, blast radius lines, remediation line) plus the new state-line rendering for non-`remediation_proposed` states and the `severity is None` → "Severity: unknown" rendering.

### Widget tests (`tests/test_widgets_case_brief.py`)

Use Textual's `App.run_test()` harness. Mock `CoreAPIClient`; verify the widget renders the right placeholder text per `BriefState`, and that `BriefError` subclasses render inline error states rather than crashing the app.

## Out of scope (deferred)

- **Live verdict push.** The widget polls every 5s; there's no server-side push. v2 may add SSE or websocket from core; revisit then.
- **Editable export to markdown / JIRA / Confluence.** Belongs to `post-incident`, not `brief`.
- **Operator reasoning capture** (acceptance criteria for opensrm-81rn.4 mentions reasoning capture). That's a separate widget under the same bead — not blocked by brief but tracked separately. The brief is read-only.
- **Reconnect with exponential backoff + write queue** (opensrm-81rn.1 acceptance criteria). Not in this bead — and the brief is pure-read so the write queue doesn't apply to it.
- **Other 5 SRE commands** (`shift-report`, `suppress`, `post-incident`, `oncall`, `delegate`). Each gets its own spec/bead. `post-incident` is the next priority per the inventory.

## Acceptance criteria for the brief portion of opensrm-81rn.4

1. `nthlayer_bench.sre.brief.build_paging_brief(client, case_id)` returns a `PagingBrief` for any case in the four lifecycle states (minimal, triage_complete, investigation_complete, remediation_proposed).
2. All errors are `BriefError` subclasses; the widget never crashes the bench app.
3. `CaseBriefPanel` renders state-aware content and refreshes every 5s.
4. Test coverage: 12 logic-module cases, all renderer paths, widget state rendering.
5. R5 reviews (Correctness, Clarity, Edge Cases, Excellence) all four passes complete with no Critical or High findings before the bead closes.
6. Logic module has no Textual import; widget module has no UI-free consumer dependencies on it beyond `build_paging_brief` / `PagingBrief` / `BriefError`.

## Migration receipt

Legacy `sre/brief.py` is the inspiration but not a faithful port. Differences:

| Legacy | v1.5 bench |
|---|---|
| Sync, talks to `SQLiteVerdictStore` directly | Async, talks to core via `CoreAPIClient` |
| Keyed on `incident_id` (string, not actually filtered on) | Keyed on `case_id`, walks `case.underlying_verdict` |
| `VerdictFilter` queries | `get_descendants` + `get_verdict` |
| `by_lineage(direction="both")` | `get_descendants` only (descendants of trigger = the response chain) |
| `severity` defaults to 3 when missing | `severity` is `None` when missing — no fabricated P3 |
| No lifecycle-state field | Explicit `BriefState` + `awaiting` |
| Operates on `Verdict` dataclass instances | Operates on JSON dicts (HTTP response shape) |
| Read `proposed_action` from `metadata.custom` (test-fixture-only — coordinator never wrote it) | Read `proposed_action` and `target` from `metadata.custom` after Bead 1 lands the structured emission across the four sites enumerated in the *Dependency: structured remediation emission* section above |

The legacy tests (`tests/test_sre_brief.py`) remain a useful reference for the renderer's output shape, but the new tests are written against the HTTP dict shape, not the `Verdict` dataclass.
