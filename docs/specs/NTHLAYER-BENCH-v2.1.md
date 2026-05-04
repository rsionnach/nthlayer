# NthLayer Bench — v2.1-draft

**Status:** Draft for implementation
**Supersedes:** NTHLAYER-BENCH-V2.md v2.0-draft
**Date:** 2026-04-19

---

## Delta Summary

This revision updates the Bench spec to align with the technology choices from the v1.1 RBAC extension and the OSS delegation research. The architectural model (cases as first-class primitives, concurrent operator safety via leasing, structured reasoning capture, idle state, retrospective signals) is unchanged. What changes is integration with the newly adopted primitives and the delivery/visualisation stack:

| v2.0 (unspecified or implicit) | v2.1 (delegated) | Rationale |
|---|---|---|
| SaaS delivery via "textual-web or similar" | **`textual-serve`** explicitly | textual-web is a demo tunnel ("if you close the browser tab it will also close the Textual app"); textual-serve is the production self-hosted path |
| Sparklines as unspecified rendering | **Built-in Textual `Sparkline` widget** | Ships with Textual; no extra dependency |
| Richer charts (burn rates, etc.) as unspecified | **`textual-plotext`** | Textualize-maintained, theme-aware |
| Capability token display | **Biscuit token summary rendering** | Must surface attenuation comprehensibly without requiring Datalog literacy |
| Action request/approval flow generic | **Rego policy reasoning surfaced** | When policy requires approval, show matched rules and required attributes |
| Case/verdict identifiers generic | **IPLD CIDs** | Content-addressed identifiers are shareable and verifiable |

The biggest UX question added in v2.1 is how the Bench surfaces Biscuit tokens to operators — it's discussed in §7.

---

## 1. Motivation

Unchanged from v2.0.

Operators need a single place to see what the system wants approval on, review context, decide, and capture reasoning. The Bench is that place. It is deliberately terminal-native (runs over SSH, works on any laptop, no JavaScript bundle required) and deliberately prose-first (descriptions over dashboards, structured explanations over trend charts).

The thesis: humans communicate intent and context in prose; they absorb pattern and state visually. The Bench uses both — prose for the situational description and the operator reasoning, sparkline charts for state shape.

## 2. Scope

Unchanged. The Bench is the **decision interface** for the NthLayer ecosystem. It is not:

- A retrospective management system (those belong in Jira/Linear/Backstage)
- A monitoring dashboard (those belong in Grafana/Pyrra)
- A notification system (pure-pull with optional escalation to on-call)

It *is*:

- The operator-facing surface for reviewing cases requiring human attention
- The capture mechanism for human reasoning as structured data
- The situation board for current system state in prose form

## 3. Technology Stack

### 3.1 Framework

**Textual** (textualize/textual) — the Rich/Textual Python TUI framework. Actively maintained by Will McGugan's team, first-class async support, rich widget library.

### 3.2 Delivery

Two modes, depending on deployment:

**Local terminal.** Operators SSH to a deployment node or run `nthlayer bench` locally. Textual renders to the terminal directly. This is the default for on-premises deployments.

**SaaS delivery via `textual-serve`** (textualize/textual-serve). Wraps the Textual application in a WebSocket server, serves it over HTTP with a terminal emulator in the browser. Critical note: **`textual-web` is not the production path**. textual-web is Textualize's hosted tunnel service, explicitly a demo convenience ("if you close the browser tab it will also close the Textual app"). textual-serve is the self-hostable version with file delivery, `open_url`, and multi-instance support across CPUs.

Production deployment wraps textual-serve in an ASGI app behind the organisation's auth gateway. Per-tab subprocesses are hardened with cwd isolation and resource limits (memory, CPU, subprocess count).

### 3.3 Visualisation

**Sparklines:** The built-in Textual `Sparkline` widget. No extra dependency. Unicode-block rendering, theme-aware, handles resize. Single-line by design — multi-series charts compose vertically with separate Sparkline widgets.

**Richer charts:** `textual-plotext` (Textualize, Apache-2.0). Theme-aware Plotext integration. Used for burn-rate plots, error-budget trajectories, SLO histograms. Alternative: `textual-plot` if hi-res Braille line plots with pan/zoom become a requirement.

**Skipped:** `uniplot`, `plotille`. Both bypass the Textual widget layer (write to stdout) and don't integrate with Textual's layout or theme systems.

### 3.4 Polling and async

Reactive polling uses Textual's native `@work` decorator and `set_interval` APIs. The shared store (SQLite WAL) is accessed via async SQLAlchemy with connection pooling. Polling cadence: 2-5 seconds for case list, 30-60 seconds for situation board context.

## 4. Domain Model

Cases and verdicts, as in v2.0, with these refinements:

### 4.1 Case

```python
@dataclass
class Case:
    id: CID                              # IPLD CID, content-addressed
    kind: CaseKind                       # approval_required | attention_required | investigation_required
    priority: Priority                   # P0 | P1 | P2 | P3
    created_at: datetime
    state: CaseState                     # pending | leased | resolved | expired
    lease: Optional[CaseLease]

    # What triggered this case
    underlying_verdict: CID              # the action_request, denial, or attention signal
    service: str                         # affected service
    policy_context: Optional[PolicyContext]  # for approval cases

    # Human-consumable description
    briefing: str                        # prose description
    recommended_action: Optional[str]    # prose recommendation, if any

    # Resolution
    resolution: Optional[CaseResolution] # populated when resolved
```

### 4.2 CID identifiers

v2.0 used opaque string identifiers. v2.1 uses **IPLD CIDs** via `libipld` (MarshalX/python-libipld, Rust+PyO3, MIT). CIDs are content-addressed — shareable between systems, verifiable, and embed the hash algorithm so future migrations are transparent. The Bench displays CIDs in short form (first 12 chars + ellipsis) but the full CID is available on click/expansion.

### 4.3 PolicyContext (for approval cases)

When a case exists because nthlayer-authorise's Rego evaluation required approval, the case carries the policy context:

```python
@dataclass
class PolicyContext:
    matched_rules: list[str]              # ["production-tightening.rules[0]"]
    required_approvals: list[ApprovalKind] # ["single-human", "dual-human"]
    approvals_received: list[CID]          # verdict CIDs of approvals so far
    required_attributes: dict              # {"principal.team": "sre"}
    deny_reasons_if_rejected: list[str]    # what happens if rejected
```

The Bench surfaces this as prose ("This case requires dual-human approval because production-tightening policy applies to agent-initiated production actions"). Operators who want the full Rego evaluation trace can drill in via a keyboard shortcut.

### 4.4 Leasing

Unchanged from v2.0. Atomic lease acquisition via SQLite transaction:

```sql
UPDATE cases
SET lease_holder = ?, lease_expires_at = ?
WHERE id = ? AND (lease_holder IS NULL OR lease_expires_at < ?)
```

Lease TTL: 5 minutes, renewable. Multiple operators see the case in their list but only one can open it at a time; the UI shows a "leased by operator-X since N minutes ago" indicator.

## 5. Screens

Structure unchanged from v2.0. Three primary screens:

### 5.1 Situation Board

Prose-first description of current system state. Built from nthlayer-observe assessments and nthlayer-correlate snapshots.

```
┌─ Situation Board ──────────────────────────────────────────────────┐
│                                                                    │
│ Production is healthy. All SLOs within budget. No active incidents.│
│                                                                    │
│ SLO burn: 3 services within 10% of burn-rate threshold             │
│   payment-service       ▁▂▃▂▃▄▃▂▁      87% budget remaining        │
│   checkout-service      ▁▁▂▂▁▂▁▁▁      94% budget remaining        │
│   notification-service  ▂▃▄▅▆▅▆▅▆      23% budget remaining ⚠       │
│                                                                    │
│ Agent quality: 4 agents reporting, all within quality SLOs.        │
│   triage-agent          judgment SLO 97% (target 95%)              │
│   investigation-agent   judgment SLO 92% (target 90%)              │
│   ...                                                              │
│                                                                    │
│ Open change freezes: 1 (incident-driven, payment-service, lifted   │
│ after incident INC-2026-04-01847 resolves)                         │
│                                                                    │
│ Last updated 47 seconds ago.                                       │
└────────────────────────────────────────────────────────────────────┘
```

The charts are built-in `Sparkline` widgets. Longer-horizon burn-rate charts shown on drill-down use `textual-plotext`.

### 5.2 Case Bench

The case list. Cases grouped by priority; within each, ordered by creation time.

Team filtering behaviour: **default to operator's team's services, with an explicit "show all" toggle**. This resolves v2.0 open question #1 in favour of the team default.

```
┌─ Case Bench ───────────────────────────────────────────────────────┐
│                                                                    │
│ Showing: my team (sre) │ [tab] to toggle all teams                 │
│                                                                    │
│ P0 (1)                                                             │
│  ● payment-service: rollback requested by triage-agent             │
│    Needs: dual-human approval │ 2m ago │ bafyrei...                │
│                                                                    │
│ P1 (0)                                                             │
│                                                                    │
│ P2 (3)                                                             │
│    checkout-service: judgment SLO calibration review               │
│    Needs: attention │ 14m ago │ bafyrei...                         │
│    ...                                                             │
│                                                                    │
│ Open 1 of 4 │ j/k to move │ enter to open │ a:approve r:reject     │
└────────────────────────────────────────────────────────────────────┘
```

### 5.3 Case Detail

The decision surface. When operator opens a case, they see:

- **Briefing:** prose description of why this case exists
- **Context:** verdict lineage (what produced the action_request, what the agent's reasoning was, what preconditions the policy evaluator checked)
- **State:** relevant SLO status, recent similar decisions from history
- **Action:** decision buttons, reasoning capture, optional operator note

```
┌─ Case bafyrei...fhq3 ──────────────────────────────────────────────┐
│                                                                    │
│ payment-service: rollback requested by triage-agent                │
│                                                                    │
│ ── Briefing ─────────────────────────────────────────────────────  │
│                                                                    │
│ The triage agent has determined that a payment-service failure     │
│ correlates with deployment v2.47.3 shipped 23 minutes ago.         │
│                                                                    │
│ Error rate rose from 0.02% to 4.7% within 90 seconds of deploy.    │
│ Latency p99 increased from 340ms to 2100ms. The deploy changed     │
│ the payment gateway client library.                                │
│                                                                    │
│ ── Policy Context ───────────────────────────────────────────────  │
│                                                                    │
│ This case requires dual-human approval because:                    │
│   • production-tightening.rules[0] applies                         │
│   • Principal is an agent requesting a production action           │
│                                                                    │
│ Approvals received: 0 of 2 required.                               │
│ Required attributes: principal.team = sre                          │
│                                                                    │
│ [space] show full Rego trace                                       │
│                                                                    │
│ ── SLO Impact ────────────────────────────────────────────────────  │
│                                                                    │
│ payment-service availability SLO (99.9% target)                    │
│   ▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▂▃▅▇████▇▇▇▇                          │
│   Currently burning 47x budget. At this rate, monthly budget       │
│   exhausted in 19 minutes.                                         │
│                                                                    │
│ ── Your Decision ─────────────────────────────────────────────────  │
│                                                                    │
│ Tags (one or more):                                                │
│   [✓] matches-agent-recommendation                                 │
│   [ ] overriding-policy                                            │
│   [ ] uncertain                                                    │
│   [ ] emergency-judgement                                          │
│                                                                    │
│ Reasoning (optional):                                              │
│ > Clear deploy-to-error correlation, rollback is the right call    │
│                                                                    │
│ [a] approve  [r] reject  [d] defer  [n] add note                   │
└────────────────────────────────────────────────────────────────────┘
```

## 6. Reasoning Capture

Unchanged from v2.0 structurally. Reasoning is captured as:

- **Tags** (structured, multi-select from a controlled vocabulary)
- **Prose reasoning** (freeform, optional)

### 6.1 Tag Vocabulary (v2.1: ship with this default)

Resolves v2.0 open question #7. The spec ships with this vocabulary; organisations may extend via configuration but cannot remove core tags.

**Agreement/disagreement:**
- `matches-agent-recommendation`
- `overrides-agent-recommendation`
- `partial-agreement`

**Confidence:**
- `high-confidence`
- `uncertain`
- `emergency-judgement` (speed over certainty)

**Policy context:**
- `following-policy`
- `overriding-policy` (requires prose reasoning)
- `policy-ambiguous`

**Data quality:**
- `insufficient-data`
- `conflicting-signals`

**Operational:**
- `similar-recent-case` (links to prior case ID)
- `pattern-match` (matches known pattern)
- `novel-situation`

## 7. Capability Token Display

New in v2.1. When the authorisation flow results in a Biscuit capability token, the Bench must surface it comprehensibly.

### 7.1 What operators see

```
┌─ Capability Issued ────────────────────────────────────────────────┐
│                                                                    │
│ Token: bscrn:...4hq9                                               │
│ Issued to: triage-agent-01                                         │
│ Action: payments.rollback-deployment                               │
│ Target: deployment/payment-service                                 │
│                                                                    │
│ Valid: 2026-04-19 09:32:15 → 09:42:15 (10 minutes)                 │
│                                                                    │
│ Conditions:                                                        │
│   ● Target deployment must exist                                   │
│   ● Parameters must match the approved hash                        │
│   ● Change freeze must be in effect OR action must be excepted     │
│   ● Current time must be within validity window                    │
│                                                                    │
│ [space] show full Datalog                                          │
└────────────────────────────────────────────────────────────────────┘
```

### 7.2 Design principle

Operators should never need to read Datalog to trust a capability. The Bench translates Biscuit's embedded checks into prose using a fixed mapping from Datalog predicate patterns to English sentences. Operators who want to verify the translation or inspect the full token can drill in.

### 7.3 Attenuation

If the token has attenuation blocks (operator or system added further restrictions), those appear as additional "Conditions" entries with a visual distinction (different indent color) so operators can see which conditions came from the authority block versus from attenuation.

## 8. Retrospective Signal

Unchanged in purpose from v2.0. When a case is resolved, nthlayer-learn eventually establishes whether the outcome matched the decision. This outcome flows back as:

- A follow-up signal appearing in the operator's own case history ("Your decision on bafy...fhq3 on 2026-04-19 led to resolution of INC-2026-04-01847 within 14 minutes")
- An aggregate signal on the situation board ("SRE team: 94% of approvals in last 30 days led to successful outcomes")

Scope clarification (unchanged): the retrospective signal is **operator-facing only**. Full retrospective management (action items, owner assignments, delivery tracking) is out of scope — it lives in Jira/Linear/Backstage.

## 9. Idle State

Unchanged from v2.0. When there are no cases, the Bench shows the situation board with "No cases requiring attention" prominently. This is a feature, not a bug: the absence of cases is itself operationally meaningful.

## 10. Concurrent Operator Handling

Unchanged from v2.0.

- Atomic lease acquisition (§4.4)
- Other operators see "leased by X" indicator
- Lease timeout (5m default, renewable)
- Lease release on resolution, rejection, defer, or explicit release
- Heartbeat lease renewal every 2 minutes while case is open

## 11. Notification Policy

Resolves v2.0 open question #5. The Bench is pure-pull for routine cases but escalates unattended P0/P1 cases to on-call.

**Defaults:**
- P0: escalate to on-call via organisation's notification system if unclaimed after 5 minutes
- P1: escalate after 10 minutes
- P2/P3: no escalation

Escalation is an event emitted to the notification system (Slack webhook, PagerDuty API call, etc.) with a link to the case. It's not a new case or case modification.

This introduces push behaviour that partially violates "pull over push" but pragmatism wins: P0s left unclaimed are genuinely urgent and the cost of accidental escalation (a Slack ping to on-call) is low.

## 12. Implementation Phases

Phase 1: Static prototype.
Phase 2: Live data integration via store polling.
Phase 3: Lease acquisition and release.
Phase 4: Full authorisation integration (Biscuit token display, Rego context display).
Phase 5: Operational completeness (situation board, retrospective signal, idle state).
Phase 6: SaaS delivery via textual-serve.
Phase 7: Polish (concurrent operator indicators, reasoning capture UX, keyboard navigation).

v1.5 releases Phases 1-3 + simplified Phase 4 (without full Rego/Biscuit integration). v2 releases complete Phases 4-7.

## 13. Open Questions

Resolved from v2.0:
- ~~Team-based case filtering default~~ → default to team, toggle to show all (§5.2)
- ~~Notification policy~~ → pure-pull with P0/P1 escalation (§11)
- ~~Reasoning tag vocabulary~~ → ship with v2.1 vocabulary (§6.1)
- ~~SaaS delivery~~ → textual-serve, not textual-web (§3.2)

Still open:
- **Rego trace display UX.** When operator presses [space] to see the full Rego trace, what's the right visualisation? Indented JSON is the naive answer but unreadable at depth.
- **Cross-case linking.** When an operator has addressed several similar cases recently, should the Bench proactively surface pattern recognition? Probably yes but the UX is non-obvious.
- **Mobile/small-terminal layout.** textual-serve works in mobile browsers but the layouts assume 80+ columns. A compact mode for <80 columns is future work.

## 14. References

- Textual: https://github.com/textualize/textual
- textual-serve: https://github.com/textualize/textual-serve
- textual-plotext: https://github.com/textualize/textual-plotext
- libipld: https://github.com/MarshalX/python-libipld
- RBAC extension v1.1 (Biscuit/Regorus specifics)
- nthlayer-learn spec (CID generation, verdict chains)

## 15. Revision History

| Version | Date | Changes |
|---------|------|---------|
| 2.0-draft | 2026-04-18 | Initial case-as-first-class spec |
| 2.1-draft | 2026-04-19 | Confirmed textual-serve/textual-plotext/Sparkline; added Biscuit token display (§7); added Rego policy context display (§4.3, §5.3); adopted IPLD CIDs; resolved open questions from v2.0 |
