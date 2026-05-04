# NthLayer Bench — Product Specification (v2)

**"Humans read prose, not graphs and not pixels."**

**Version:** 2.0-draft
**Supersedes:** NthLayer Bench v1.0
**Depends on:** OpenSRM v1, OpenSRM RBAC Extension, NthLayer Serve Mode v2

---

## 1. Overview

The NthLayer Bench is a terminal-native operator interface built with Textual. It provides two primitives — the **Situation Board** and the **Case Bench** — that replace traditional dashboards with narrative-driven situational awareness and a judicial decision workflow.

The Bench treats human attention as the scarcest resource in reliability operations. Instead of showing data and expecting operators to synthesise meaning, it presents pre-synthesised narrative and asks for judgment only when judgment is required.

### 1.1 Scope

The Bench is an operator decision interface. It reads from the shared verdict store, writes approval and rejection verdicts, and displays the state of authorisations requiring human attention.

The Bench is explicitly **not**:
- A system of record for post-incident retrospectives (those live in Jira/Linear/Backstage).
- A configuration interface for manifests, policies, or component configuration.
- A real-time monitoring dashboard (it uses prose, not charts, and polls at low frequency).

### 1.2 Changes from v1

1. **Cases are first-class.** A case is now a defined data structure in the verdict store, not an implicit Bench concept. Cases wrap one or more verdicts requiring human attention, with their own lifecycle and state machine.

2. **Integration with authorisation.** Cases are created by `nthlayer-authorise` when action requests require human approval. The Bench writes `approval` verdicts (per the RBAC Extension) on operator action.

3. **Concurrent operator safety.** Case leasing is defined. Multiple operators can use the Bench simultaneously without rendering contradictory verdicts.

4. **Reasoning capture.** Rejection, modification, and deferral verdicts include structured reasoning fields.

5. **Idle state defined.** Operator experience when no cases are pending is explicit.

6. **Retrospective signal (not system of record).** An operator's Bench shows when their past verdicts have been validated by retrospective review, but the Bench does not own the retrospective process.

---

## 2. Architecture Context

```
┌─────────────────────────────────────────────────────────┐
│                    NthLayer Platform                     │
│                                                         │
│  nthlayer-observe       → slo_state, drift assessments  │
│  nthlayer-measure       → evaluation verdicts           │
│  nthlayer-correlate     → correlation verdicts          │
│  nthlayer-respond       → incident, action_request      │
│  nthlayer-authorise     → capability, denial verdicts   │
│                          + pending authorisations       │
│                          (ephemeral state)              │
│  nthlayer-executor      → execution verdicts            │
│  nthlayer-learn         → retrospective verdicts        │
│  verdict store          → append-only, hash-chained     │
│  case store             → ephemeral case lifecycle      │
│                                                         │
├─────────────────────────────────────────────────────────┤
│                      Interfaces                          │
│                                                         │
│  nthlayer bench         → Operator interface (this)     │
│  nthlayer CLI           → CI/CD and scripting           │
│  nthlayer-respond HTTP  → Slack approval surface        │
│  textual-web            → SaaS delivery of the bench    │
└─────────────────────────────────────────────────────────┘
```

The Bench reads from the verdict store and the case store. It writes `approval` verdicts (defined in the RBAC Extension) and case state transitions. It is a peer surface to nthlayer-respond's HTTP/Slack approval endpoint, not a layer above it — both write the same approval verdicts into the same store.

---

## 3. Design Principles

1. **Prose over pixels.** Every piece of information is rendered as natural language. Metrics appear inline within sentences, not as isolated numbers.
2. **Pull over push.** The operator sits down when ready. No interrupts, no toasts. The Bench respects the operator's schedule.
3. **Cases over streams.** Information is organised into discrete decision units, not continuous feeds. Each case has a beginning, a briefing, and a resolution.
4. **Verdicts are verdicts.** Human judgments are recorded with the same structural guarantees as AI verdicts.
5. **Terminal-native.** Keyboard-driven. Works over SSH. Works in tmux. No mouse required.
6. **Reasoning is data.** When an operator rejects or modifies a proposal, their reasoning is captured as structured data, not free text buried in notes.

---

## 4. Cases as First-Class Concept

### 4.1 Case Definition

A case is a wrapper around one or more verdicts requiring human attention. Unlike verdicts, cases have mutable state and explicit lifecycle. Cases live in a dedicated `case` store (a separate table in the same SQLite database as the verdict store, for locality).

```yaml
# Case data model
case:
  id: case-2026-04-18-0007
  created_at: "2026-04-18T14:23:14Z"

  # References to verdicts (immutable)
  action_request_hash: "sha256:abc..."  # The verdict that triggered this case
  related_verdicts:                     # Verdicts in the lineage
    - hash: "sha256:def..."
      type: correlation
    - hash: "sha256:ghi..."
      type: evaluation
    - hash: "sha256:jkl..."
      type: slo_state

  # Case state
  state: awaiting_verdict    # pending | assigned | awaiting_verdict | resolved | expired
  service: payment-service
  severity: P1
  approval_level: single-human

  # Case assignment (ephemeral)
  assigned_to: null          # operator_id when assigned
  assigned_at: null
  lease_expires_at: null     # for concurrent operator safety

  # Resolution (populated when resolved)
  resolved_by: null          # operator_id
  resolved_at: null
  resolution_verdict_hash: null   # The approval/rejection verdict
```

### 4.2 Case Lifecycle

```
      ┌───────────────┐
      │    pending    │    Created by authorise; awaiting operator attention
      └───────┬───────┘
              │ Operator opens case
              ▼
      ┌───────────────┐
      │   assigned    │    Leased to a specific operator for N minutes
      └───────┬───────┘
              │ Operator begins rendering verdict
              ▼
      ┌───────────────┐
      │awaiting_verdict│   Operator is actively deciding (sub-state of assigned)
      └───────┬───────┘
              │
       ┌──────┴──────┐
       │ Operator    │ Operator
       │ verdict     │ defers
       ▼             ▼
   ┌────────┐   ┌────────┐
   │resolved│   │ pending│   (re-queued)
   └────────┘   └────────┘

  Lease expires → state returns to pending
  Timeout expires → state becomes expired; denial verdict written
```

### 4.3 Case Creation

Cases are created by `nthlayer-authorise` when an action request requires human approval. Authorise writes the action_request verdict to the store, then creates a case record with:

- The action_request_hash
- Related verdicts from the request's lineage (correlation, evaluation, etc.)
- Approval level from the action definition
- Severity inferred from the triggering signal's severity
- Service from the action_request

Cases MAY also be created by `nthlayer-respond` for non-authorisation decisions (e.g., an incident that benefits from human review but has no specific action to approve). These cases have no `action_request_hash` and resolve with informational verdicts rather than approvals.

### 4.4 Case Assignment and Leasing

When an operator opens a case, the Bench issues a lease:

```
operator opens case-007 →
  Bench sends: assign(case_id=007, operator_id=rob@workday.com, ttl=10m)
  Case store atomically:
    - Check case is in `pending` state
    - Set state=assigned, assigned_to=rob@workday.com, lease_expires_at=now+10m
    - Return success or lease-conflict error
```

If a second operator tries to open the same case while leased, they receive a "currently being reviewed by [operator]" indicator and cannot open it. The lease renews automatically while the operator is active in the case (every 2 minutes). If the operator closes the Bench or becomes idle, the lease expires and the case returns to pending.

This is the concurrent-operator safety mechanism. It does not require distributed locking or complex coordination — just an atomic state update against the case store.

### 4.5 Case Resolution

A case is resolved when the operator writes a resolution verdict. Depending on the case type:

- **Approval case (authorisation):** Operator writes an `approval` verdict (decision: approve | reject | request-modification). Case transitions to resolved with resolution_verdict_hash set.
- **Informational case:** Operator writes an `operator_note` verdict (new type, defined in §4.6). Case transitions to resolved.

Resolved cases remain queryable for 30 days (configurable) for operator history and retrospective linking, then are archived. The underlying verdicts are immutable and retained indefinitely per the verdict store policy.

### 4.6 operator_note Verdict

A new verdict type for informational cases (no action to approve, but operator input captured):

```json
{
  "verdict_type": "operator_note",
  "hash": "sha256:...",
  "timestamp": "2026-04-18T14:25:00Z",
  "service": "payment-service",
  "principal": {
    "type": "human",
    "id": "rob@workday.com"
  },
  "data": {
    "case_id": "case-2026-04-18-0007",
    "note_type": "acknowledged",   // acknowledged | escalated | dismissed
    "reasoning": "Reviewed correlation; not actionable at this time. Monitoring.",
    "referenced_verdicts": ["sha256:abc..."]
  }
}
```

---

## 5. Interface Layout

```
┌──────────────────────────────────────────────────────────┐
│ ◆ NthLayer Bench              cluster: prod-eu-west-1    │
│ ─────────────────────────────────────────────────────────│
│ SITUATION — 09:41 UTC — 2 active cases, 1 watch          │
│                                                          │
│ ▸ payment-service DEGRADED 14m. Error rate 4.2% against  │
│   1% SLO target. Correlated with deploy d-4521 (canary,  │
│   09:27). Remediation agent proposes ROLLBACK. Awaiting  │
│   your verdict. [Case #7]                                │
│                                                          │
│ ▸ search-api WATCH. p99 latency trending upward, 340ms   │
│   against 500ms target. No action required. Budget burn  │
│   rate 1.4x — will breach in ~6 days at current rate.    │
│                                                          │
│ ▸ All other services NOMINAL. 14/16 SLOs healthy.        │
│   Error budget period: 22 days remaining.                │
├──────────────────────────────────────────────────────────┤
│ BENCH — 1 case awaiting verdict (1 in review elsewhere)  │
│                                                          │
│ ┌ Case #7 ─ payment-service ─ ROLLBACK proposed ───────┐ │
│ │                                                       │ │
│ │ BRIEFING                                              │ │
│ │ At 09:27 UTC, canary deploy d-4521 (commit abc123,    │ │
│ │ author: jsmith) was promoted to 25% traffic. Within   │ │
│ │ 3 minutes, error rate rose from 0.4% to 4.2%. The     │ │
│ │ triage agent classified this as deployment-correlated │ │
│ │ with HIGH confidence (0.94). The investigation agent  │ │
│ │ confirmed no upstream dependencies are degraded. The  │ │
│ │ remediation agent proposes rollback to d-4520.        │ │
│ │                                                       │ │
│ │ LINEAGE   (depth 4, latency 76s)                      │ │
│ │ 09:27:12  slo_state      availability breach          │ │
│ │ 09:27:48  evaluation     confirmed breach, sev=P1     │ │
│ │ 09:28:05  correlation    root cause: deploy d-4521    │ │
│ │ 09:28:28  action_request rollback-deploy to d-4520    │ │
│ │                                                       │ │
│ │ EVIDENCE                                              │ │
│ │ Error rate ──────── ▁▁▁▂▃▅▇█ 4.2%  (SLO: 1%)        │ │
│ │ p99 latency ─────── ▁▁▁▁▂▂▃▃ 210ms (SLO: 500ms)     │ │
│ │ Canary traffic ──── ████████ 25%                     │ │
│ │ Error budget ────── ██░░░░░░ 12% consumed (14m)      │ │
│ │                                                       │ │
│ │ AUTHORISATION                                         │ │
│ │ action: rollback-deploy (single-human approval)       │ │
│ │ preconditions:                                        │ │
│ │   ✓ no-change-freeze                                  │ │
│ │   ✓ rate-limit (0/3 in 1h)                            │ │
│ │ blast radius: payment-service, production             │ │
│ │                                                       │ │
│ │ YOUR VERDICT                                          │ │
│ │ [A]pprove  [R]eject  [M]odify  [D]efer  [E]scalate   │ │
│ └───────────────────────────────────────────────────────┘ │
├──────────────────────────────────────────────────────────┤
│ F1 Help  F2 History  F3 SLO Status  F5 Refresh  Q Quit   │
└──────────────────────────────────────────────────────────┘
```

### 5.1 Changes from v1 layout

- Case header now shows "(1 in review elsewhere)" when other operators have cases leased.
- New "LINEAGE" section shows the verdict chain that produced this case, with depth and end-to-end pipeline latency. This addresses the v1 gap of not exposing how long the pipeline took.
- "AUTHORISATION" section replaces the v1 "AGENT VERDICTS" section. Instead of listing each agent verdict (which is now in LINEAGE), this section shows the authorisation context: action id, approval level, preconditions, and blast radius. This is the information most relevant to an approval decision.

---

## 6. Verdict Actions

The Bench supports six verdict actions. Each produces a specific verdict type per the RBAC Extension.

### 6.1 Action Specifications

| Key | Action | Produces | Requires Input |
|-----|--------|----------|----------------|
| `A` | Approve | approval (decision: approve) | No, but optional reasoning field |
| `R` | Reject | approval (decision: reject) | Yes, reasoning (min 20 chars) |
| `M` | Modify | approval (decision: request-modification) | Yes, modification proposal |
| `D` | Defer | case transition (state → pending) | Yes, re-queue time |
| `E` | Escalate | case transition (assigned_to → [team]) | Yes, escalation target |
| `Esc` | Cancel | no verdict, lease released | No |

### 6.2 Approve

Writes an `approval` verdict with decision: approve. Operator MAY add reasoning. On submission:

1. Write approval verdict.
2. Transition case to resolved.
3. nthlayer-authorise observes the approval, issues capability.
4. nthlayer-executor consumes capability, performs action.
5. Operator sees execution outcome in Bench history (F2).

Approval is the terminal verdict — once approved, the case is complete regardless of execution outcome.

### 6.3 Reject

Writes an `approval` verdict with decision: reject. Operator MUST provide reasoning (minimum 20 characters, enforced by the Bench). Optional fields:

- `confidence`: high | medium | low
- `referenced_verdicts`: hashes of verdicts informing the rejection
- `counter_proposal`: text describing what should happen instead

The counter_proposal is captured but does not automatically trigger a new action request; it's an annotation for the AI agents to consider in future cases and for human reviewers in retrospective.

### 6.4 Modify

Writes an `approval` verdict with decision: request-modification. The modification is expressed as a revised parameter set:

```json
{
  "decision": "request-modification",
  "reasoning": "Rollback target should be d-4519, not d-4520. d-4520 had the connection pool regression reported last week.",
  "modified_parameters": {
    "target_version": "d-4519"
  }
}
```

On submission, nthlayer-authorise creates a new action_request with the modified parameters and writes a new capability if preconditions still pass. The original case resolves; a new case is created for the modified request if further approval is needed.

Modifications cannot escape action declarations. The modified parameters MUST still validate against the action's schema and blast radius. The Bench validates this client-side before submission so the operator sees errors immediately.

### 6.5 Defer

No verdict is written. The case transitions back to `pending` state with a `not_before` timestamp. Re-queue options: 15 minutes, 1 hour, 4 hours, next shift. Deferred cases appear in the pending queue again after the deferral period.

A case may be deferred at most twice. On the third deferral attempt, the Bench requires the operator to either resolve or escalate.

### 6.6 Escalate

Transitions the case's assignment to another operator or team. The escalator provides:

- Target (operator_id or team name)
- Brief reason

No verdict is written at escalation time; the case simply moves to a different assignment context. When the escalation target resolves the case, the original escalator is recorded in the resolution's lineage.

### 6.7 Reasoning Capture

All verdict actions except Approve (optional) and Cancel require structured reasoning. Reasoning is captured in the approval verdict's `reasoning` field as plain text, plus optional structured fields:

```json
{
  "reasoning": "Free-text reasoning from operator",
  "reasoning_tags": ["incorrect-target", "missing-context"],
  "confidence": "high",
  "referenced_verdicts": ["sha256:..."]
}
```

Tags are operator-selected from a fixed vocabulary. This is the highest-value data for training future agent behaviour and for retrospective review. The vocabulary is configurable per-organisation but a default set is provided:

- `incorrect-target`, `wrong-timing`, `insufficient-context`, `conflicting-evidence`, `safer-alternative-exists`, `needs-investigation`, `needs-coordination`, `severity-mismatch`

---

## 7. Idle State

When no cases are pending, the Bench shows the Situation Board in full-height mode and replaces the Case Bench panel with a status summary:

```
┌──────────────────────────────────────────────────────────┐
│ BENCH — No cases awaiting verdict                        │
│                                                          │
│ Last resolved case: #6 (15m ago)                         │
│   payment-service scale-up, approved by rob@workday.com  │
│   Execution succeeded, verification passed.              │
│                                                          │
│ Recent activity:                                         │
│   09:26  checkout-service   autonomous scale-up         │
│   09:18  search-api         autonomous restart          │
│   08:52  user-auth          scheduled maintenance       │
│                                                          │
│ Pending authorisations in other channels:                │
│   Slack: 0 awaiting approval                             │
│                                                          │
│ Press F2 to view your verdict history.                   │
│ Press F3 for portfolio SLO status.                       │
└──────────────────────────────────────────────────────────┘
```

The idle state is deliberately informative rather than empty. It shows recent autonomous activity (so operators understand what's happening without their intervention), other approval channels' state (so operators know whether someone else might be working), and navigation hints. The Bench is useful even when there are no cases.

---

## 8. Retrospective Signal

When `nthlayer-learn` writes a retrospective verdict that references a case the operator worked, the Bench surfaces this in the operator's history view (F2) and optionally as a notification on next Bench open.

```
┌──────────────────────────────────────────────────────────┐
│ RETROSPECTIVE REVIEW                                     │
│                                                          │
│ Case #7 (3 days ago) was reviewed in the retrospective:  │
│                                                          │
│ Your verdict: APPROVED rollback to d-4520                │
│ Retrospective finding: Correct. Root cause confirmed as  │
│   deploy d-4521's connection pool regression. Rollback   │
│   was the appropriate action. Fix shipped in d-4523.     │
│                                                          │
│ [C]ontinue                                               │
└──────────────────────────────────────────────────────────┘
```

This is the feedback loop the operator gets on their own decisions. It is **not** a system of record for retrospective management. The retrospective itself lives in whatever tool the organisation uses (Jira, Linear, Backstage, a shared document). The Bench shows the operator's personal slice of the retrospective — whether their individual verdict was validated — and nothing more.

Retrospective signals SHOULD be aggregated into a `verdict_agreement_rate` metric in the operator's history (per §12), but this is for the operator's self-improvement, not for performance evaluation. The Bench does not expose other operators' agreement rates.

---

## 9. Detail Pane (F2 / Enter)

A slide-out panel for drilling into any element:

- **Verdict detail:** Full provenance — the prompt sent to the agent, the assessments it consumed, the raw LLM response, the extracted verdict. Verifiable via hash.
- **Case history:** All cases the operator has worked, filterable by outcome. Each case shows: case ID, service, resolution, timing, retrospective validation if available.
- **Service detail:** OpenSRM manifest excerpt including actions block, dependency tree, current SLO status.
- **Verdict chain:** All verdicts in a case's lineage, with hash-chain verification status.

---

## 10. SLO Status View (F3)

In v1 this was a table. In v2 it retains the table but leads with a prose summary:

```
SLO STATUS — 09:41 UTC

14 services nominal. 2 services not nominal: payment-service
(DEGRADED, case #7 in progress), search-api (WATCH, no action
needed yet).

Error budget period: 22 days remaining (30-day window).

Highest burn rates:
  payment-service    8.4x    budget exhausts in ~2h if unabated
  search-api         1.4x    budget exhausts in ~6d if unabated

[Press Enter to expand to per-service table]
```

Pressing Enter expands to the v1 sortable table. The prose summary is the default because it's the answer to the question the operator actually has — "what's going on?" — rather than the raw data they'd need to interpret to answer that question.

---

## 11. Case Prioritisation

Cases in the pending queue are ordered by:

1. **Severity** (P0 > P1 > P2 > P3)
2. **Error budget impact** (cases affecting services with less remaining budget first)
3. **Age** (older cases first, to avoid starvation)
4. **Approval level** (emergency > multi-human > single-human > autonomous — though autonomous cases don't appear in the Bench)

This is deterministic and inspectable. An operator can ask "why is case #7 at the top?" and the Bench shows the ranking factors.

Operators SHOULD NOT be able to reorder the queue manually. Manual reordering introduces inconsistency between operators and defeats the prioritisation model. Operators MAY filter the queue (by service, by team, by action type) but the order within the filtered set is still deterministic.

---

## 12. Instrumentation

The Bench emits telemetry about operator behaviour (per OpenSRM's decision telemetry semantic conventions):

### 12.1 Operator Metrics

| Metric | Description |
|--------|-------------|
| `bench.time_to_verdict` | Seconds from case assignment to verdict submission |
| `bench.verdict_agreement_rate` | Approval rate on agent-proposed actions (per operator) |
| `bench.case_deferral_rate` | Proportion of cases deferred vs resolved directly |
| `bench.modification_rate` | Proportion of approvals that modified parameters |
| `bench.investigation_request_rate` | Proportion of cases that triggered `nthlayer-respond investigate-further` |
| `bench.session_duration` | How long operators spend in the Bench per session |
| `bench.cases_per_session` | Throughput of human decision-making |
| `bench.retrospective_agreement_rate` | Proportion of past verdicts validated by retrospective |

These metrics feed into the operator's own quality signal, exposed in their F2 history view. They do not feed into any performance evaluation system. They are operator self-knowledge.

### 12.2 Case Metrics

| Metric | Description |
|--------|-------------|
| `case.pipeline_latency` | Time from trigger signal to case creation |
| `case.queue_depth` | Number of pending cases at any moment |
| `case.lease_conflicts` | Attempts to open leased cases |
| `case.expiration_rate` | Proportion of cases expiring without resolution |

Case metrics inform platform tuning (are there too many cases? is the pipeline fast enough? are operators available?).

---

## 13. Textual Implementation

### 13.1 Widget Hierarchy

```python
class NthLayerBench(App):
    """Main application."""

    CSS_PATH = "bench.tcss"
    BINDINGS = [
        ("f1", "show_help", "Help"),
        ("f2", "toggle_history", "History"),
        ("f3", "toggle_slo_status", "SLO Status"),
        ("f5", "refresh", "Refresh"),
        ("q", "quit", "Quit"),
    ]

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        yield SituationBoard(id="situation")
        yield CaseBench(id="bench")
        yield Footer()
```

### 13.2 Case Lifecycle Management

```python
class CaseBench(Widget):
    """Judicial decision workspace."""

    current_case = reactive(None)
    _lease_renewal_task = None

    async def open_case(self, case_id: str) -> bool:
        """Attempt to lease a case for this operator."""
        result = await self.app.api.assign_case(
            case_id=case_id,
            operator_id=self.app.operator_id,
            lease_duration=600,  # 10 minutes
        )
        if result.status == "leased":
            self.current_case = result.case
            self._start_lease_renewal()
            return True
        elif result.status == "already_leased":
            self.app.notify(f"Case {case_id} is being reviewed by {result.leased_to}")
            return False
        else:
            self.app.notify(f"Cannot open case {case_id}: {result.reason}")
            return False

    def _start_lease_renewal(self):
        """Renew the lease every 2 minutes while this case is open."""
        self._lease_renewal_task = self.set_interval(
            120.0,
            self._renew_lease,
        )

    async def _renew_lease(self):
        if self.current_case:
            await self.app.api.renew_lease(
                case_id=self.current_case.id,
                operator_id=self.app.operator_id,
            )

    async def close_case(self, resolved: bool = False):
        """Release lease and clear state."""
        if self._lease_renewal_task:
            self._lease_renewal_task.stop()
            self._lease_renewal_task = None

        if self.current_case and not resolved:
            await self.app.api.release_lease(
                case_id=self.current_case.id,
                operator_id=self.app.operator_id,
            )

        self.current_case = None
```

### 13.3 Verdict Submission

```python
class VerdictBar(Static):
    """Keybinding-driven action bar."""

    async def action_approve(self):
        case = self.app.query_one("#bench").current_case
        reasoning = await self._prompt_optional_reasoning()

        verdict = ApprovalVerdict(
            action_request_hash=case.action_request_hash,
            principal_id=self.app.operator_id,
            principal_type="human",
            principal_mfa=self.app.principal_mfa,
            decision="approve",
            reasoning=reasoning,
        )

        result = await self.app.api.submit_verdict(verdict)
        if result.status == "accepted":
            await self.app.query_one("#bench").close_case(resolved=True)
            self.app.query_one("#bench").load_next_case()
        else:
            self.app.notify(f"Verdict rejected: {result.reason}")

    async def action_reject(self):
        case = self.app.query_one("#bench").current_case
        reasoning, tags, counter = await self._prompt_rejection_details()

        if len(reasoning) < 20:
            self.app.notify("Rejection reasoning must be at least 20 characters.")
            return

        verdict = ApprovalVerdict(
            action_request_hash=case.action_request_hash,
            principal_id=self.app.operator_id,
            principal_type="human",
            decision="reject",
            reasoning=reasoning,
            reasoning_tags=tags,
            counter_proposal=counter,
        )

        result = await self.app.api.submit_verdict(verdict)
        # ... as above
```

### 13.4 Concurrent Operator Indicator

The Situation Board queries case lease state and displays it:

```python
class SituationBoard(Static):
    async def refresh_situation(self):
        assessments = await self.app.api.get_current_assessments()
        verdicts = await self.app.api.get_recent_verdicts()
        pending = await self.app.api.get_pending_cases()
        leased = await self.app.api.get_leased_cases(
            exclude_operator=self.app.operator_id,
        )

        self.situation_text = SituationRenderer.render(
            assessments=assessments,
            verdicts=verdicts,
            pending=pending,
            leased_elsewhere=leased,
        )
```

---

## 14. SaaS Delivery via textual-web

```bash
# Local operation
nthlayer bench --cluster prod-eu-west-1

# SaaS delivery
textual-web serve nthlayer.bench:NthLayerBench \
  --host 0.0.0.0 \
  --port 8443 \
  --tls
```

**Session model:** One Python process per connected operator. For a typical enterprise deployment (5-20 SRE users per tenant), this is well within resource bounds.

**Polling consolidation:** Rather than each session polling independently, the server-side process maintains a single polling loop per tenant and fans out updates to connected clients via Textual's reactive attributes. This reduces backend load by a factor of N where N is the number of concurrent operators.

**Authentication:** textual-web supports reverse proxy auth headers. In SaaS mode, the Bench reads `X-Operator-Id` and `X-Operator-MFA` from the proxy to identify the operator.

**Multi-tenancy:** Each tenant's Bench connects to their NthLayer platform APIs. Tenant isolation is at the API layer, not the UI layer.

---

## 15. Relationship to Other Interfaces

| Interface | Audience | Purpose | Medium |
|-----------|----------|---------|--------|
| `nthlayer bench` | SRE operator | Make decisions, situational awareness | Terminal / textual-web |
| `nthlayer` CLI | CI/CD, scripts | Generate, measure, evaluate | Terminal (non-interactive) |
| `nthlayer-respond` HTTP/Slack | Mobile/async approvers | Slack-based approval for the same cases | Browser/Slack |
| Grafana dashboards | Deep investigation | Metric exploration, ad-hoc queries | Browser |
| Jira/Linear/Backstage | Retrospective management | Post-incident follow-up actions | Browser |

The Bench and the Slack approval surface write the same `approval` verdicts into the same store for the same cases. An operator can start reviewing a case in the Bench and an approver can complete it in Slack, or vice versa. Case leases prevent conflicts.

The Bench does not replace Grafana — operators open Grafana for deep metric exploration. The Bench's job is to make that unnecessary for 90% of operational decisions.

The Bench does not manage retrospectives — it surfaces an operator's personal signal from completed retrospectives but the retrospective itself lives in the organisation's existing tool.

---

## 16. Build Sequence

### Phase 1: Case data model and API (3-4 days)
- Case store schema in SQLite
- Case lifecycle state machine
- Lease atomicity (single-writer WAL)
- Case creation API (called by authorise)
- Case query API (called by Bench)

### Phase 2: Static Textual prototype (2-3 days)
- Situation board with templated prose rendering
- Case bench panel with mock case
- Verdict bar with keybinding actions
- Nord palette styling
- Serve via textual-web for shareable demo URL

### Phase 3: Live data integration (3-5 days)
- Connect to case store
- Connect to verdict store for verdict submission
- Connect to Prometheus for sparkline data (via nthlayer-observe API)
- Lease acquisition and renewal
- Concurrent operator indicators

### Phase 4: Authorisation integration (3-5 days)
- Wire authorisation-created cases into the Bench
- Write approval verdicts on operator actions
- Validate modified parameters against action schemas
- Display authorisation preconditions and blast radius

### Phase 5: Operational completeness (3-5 days)
- SLO status view (F3) with prose summary
- Detail pane with verdict provenance
- Operator history with retrospective agreement
- Case deferral with re-queue scheduling
- Escalation flow
- Idle state

### Phase 6: SaaS readiness (2-3 days)
- textual-web deployment configuration
- Reverse proxy auth integration with MFA claim propagation
- Operator identification from auth headers
- Session polling consolidation
- TLS configuration

Total: ~16-25 days for Bench v2 with full ecosystem integration.

---

## 17. Open Questions

1. **Team-based case filtering.** Should operators default to seeing only cases for their owned services, or see everything and opt-in to filters? Probably the former with a clear "show all" toggle, but this adds complexity to the assignment model.

2. **Mobile surface.** textual-web renders in a browser, which means it technically works on mobile. The keyboard-driven interaction model doesn't translate. The intended mobile surface is Slack via nthlayer-respond's existing HTTP approval endpoint. Worth confirming this covers the mobile use cases before adding Bench-specific mobile work.

3. **Case aggregation.** If multiple services experience the same root cause (e.g., a shared dependency fails), should the cases be grouped into an incident-level super-case, or remain separate? Separate is simpler; super-cases are more operator-friendly during broad incidents. Candidate for v2.1.

4. **Operator training cases.** Should the Bench support a "training mode" where operators work historical cases to build intuition, with their verdicts compared to the actual outcomes? Potentially valuable but scope creep; worth noting but not committing.

5. **Notification policy.** Currently the Bench is pure-pull (no notifications). This is correct as a default. But there are cases (P0 with no response after 10 minutes) where a push is appropriate. Should the Bench escalate through Slack to on-call if cases go unattended? Probably yes, but this needs explicit policy not just ad-hoc escalation.

---

## Appendix A: Glossary

| Term | Definition |
|------|------------|
| **Case** | A wrapper around one or more verdicts requiring human attention; has mutable state. |
| **Lease** | A short-lived exclusive assignment of a case to an operator. |
| **Approval verdict** | A verdict written by a human principal authorising or rejecting an action request. |
| **Reasoning tags** | Operator-selected labels categorising why a decision was made. |
| **Retrospective signal** | An operator-facing indicator of whether their past verdicts were validated in retrospective review. |
| **Idle state** | Bench display when no cases are pending. |
| **Situation Board** | The top panel showing narrative system state. |
| **Case Bench** | The bottom panel showing the current case. |

---

## Appendix B: Revision History

| Version | Date | Changes |
|---------|------|---------|
| 1.0 | 2026-04-10 | Initial spec |
| 2.0-draft | 2026-04-18 | Cases as first-class; RBAC integration; concurrent operator safety; reasoning capture; idle state; retrospective signal narrowed to operator-facing only |
