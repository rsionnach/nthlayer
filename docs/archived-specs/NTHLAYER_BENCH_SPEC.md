# NthLayer Bench — Product Specification

**"Humans read prose, not graphs and not pixels."**

## Overview

The NthLayer Bench is a terminal-native operator interface built with Textual (Python TUI framework). It provides two novel primitives — the **Situation Board** and the **Case Bench** — that replace traditional dashboards with narrative-driven situational awareness and a judicial decision workflow.

The Bench treats human attention as the scarcest resource in reliability operations. Instead of showing data and expecting operators to synthesise meaning, it presents pre-synthesised narrative and asks for judgment only when judgment is required.

## Architecture Context

```
┌─────────────────────────────────────────────────────────┐
│                    NthLayer Platform                     │
│                                                         │
│  nthlayer-observe    → assessments (deterministic)      │
│  nthlayer-respond    → verdicts (AI agents: triage,     │
│                        investigation, communication,     │
│                        remediation)                      │
│  verdict store       → append-only, hash-chained        │
│  Prometheus/Grafana  → metrics + visualisation          │
│                                                         │
├─────────────────────────────────────────────────────────┤
│                    Interfaces                            │
│                                                         │
│  nthlayer bench      → Operator interface (this spec)   │
│  nthlayer CLI        → CI/CD and scripting              │
│  React topology      → Architecture view / buyer demo   │
│  textual-web         → SaaS delivery of bench           │
└─────────────────────────────────────────────────────────┘
```

The Bench reads from the same verdict store and assessment APIs that power the CLI and React views. It produces human verdicts back into the same store. It is a peer of the AI agents, not a layer above them.

## Design Principles

1. **Prose over pixels.** Every piece of information is rendered as natural language. Metrics appear inline within sentences, not as isolated numbers.
2. **Pull over push.** The operator sits down when ready. No interrupts, no alerts, no toasts. The Bench respects your schedule.
3. **Cases over streams.** Information is organised into discrete decision units (cases), not continuous feeds. Each case has a beginning, a briefing, and a resolution.
4. **Verdicts are verdicts.** Human judgments are recorded with the same structural guarantees as AI verdicts: append-only, hash-chained, full provenance.
5. **Terminal-native.** Keyboard-driven, works over SSH, works in tmux, no mouse required. Textual's CSS-like styling provides visual hierarchy without a browser.

## Interface Layout

```
┌──────────────────────────────────────────────────────────┐
│ ◆ NthLayer Bench              cluster: prod-eu-west-1    │
│ ─────────────────────────────────────────────────────────│
│ SITUATION — 09:41 UTC — 2 active cases, 1 watch          │
│                                                          │
│ ▸ payment-service DEGRADED 14m. Error rate 4.2% against  │
│   1% SLO target. Correlated with deploy d-4521 (canary,  │
│   09:27). Remediation agent proposes ROLLBACK. Awaiting   │
│   your verdict. [Case #7]                                │
│                                                          │
│ ▸ search-api WATCH. p99 latency trending upward, 340ms   │
│   against 500ms target. No action required. Budget burn   │
│   rate 1.4x — will breach in ~6 days at current rate.    │
│                                                          │
│ ▸ All other services NOMINAL. 14/16 SLOs healthy.        │
│   Error budget period: 22 days remaining.                │
├──────────────────────────────────────────────────────────┤
│ BENCH — 1 case awaiting verdict                          │
│                                                          │
│ ┌ Case #7 ─ payment-service ─ ROLLBACK proposed ───────┐ │
│ │                                                       │ │
│ │ BRIEFING                                              │ │
│ │ At 09:27 UTC, canary deploy d-4521 (commit abc123,    │ │
│ │ author: jsmith) was promoted to 25% traffic.          │ │
│ │ Within 3 minutes, error rate rose from 0.4% to 4.2%. │ │
│ │ The triage agent classified this as deployment-        │ │
│ │ correlated with HIGH confidence (0.94). The           │ │
│ │ investigation agent confirmed no upstream              │ │
│ │ dependencies are degraded. The remediation agent      │ │
│ │ proposes rollback to d-4520 based on OpenSRM spec     │ │
│ │ context indicating this service has a model quality   │ │
│ │ SLO that is being violated.                           │ │
│ │                                                       │ │
│ │ EVIDENCE                                              │ │
│ │ ── Error rate ─────── ▁▁▁▂▃▅▇█ 4.2%  (SLO: 1%)     │ │
│ │ ── p99 latency ────── ▁▁▁▁▂▂▃▃ 210ms (SLO: 500ms)  │ │
│ │ ── Canary traffic ─── ████████ 25%                   │ │
│ │ ── Error budget ───── ██░░░░░░ 12% consumed (14m)    │ │
│ │                                                       │ │
│ │ AGENT VERDICTS                                        │ │
│ │ triage    → deployment-correlated (0.94)    09:30 UTC │ │
│ │ investigate → no upstream cause found (0.91) 09:31 UTC│ │
│ │ remediate → ROLLBACK d-4520 proposed (0.88)  09:32 UTC│ │
│ │                                                       │ │
│ │ YOUR VERDICT                                          │ │
│ │ [A]pprove rollback  [R]eject  [M]odify  [D]efer      │ │
│ │ [E]scalate          [I]nvestigate further             │ │
│ └───────────────────────────────────────────────────────┘ │
├──────────────────────────────────────────────────────────┤
│ F1 Help  F2 History  F3 SLO Status  F5 Refresh  Q Quit  │
└──────────────────────────────────────────────────────────┘
```

## Component Specification

### 1. Situation Board

The top-level panel. Always visible. Updates every 5 seconds.

**Data sources:**
- `nthlayer-observe` assessments (service health, SLO status)
- `nthlayer-respond` verdict stream (what agents have decided or proposed)
- Prometheus (current metric values for inline rendering)
- Pending case queue (what needs human attention)

**Rendering rules:**
- Each service with a non-NOMINAL status gets a paragraph.
- Paragraphs are ordered by severity: CRITICAL → DEGRADED → WATCH → NOMINAL.
- NOMINAL services are collapsed into a single summary line.
- Metrics appear inline within prose: "Error rate 4.2% against 1% SLO target" not "error_rate: 4.2%".
- Temporal context is always included: "14m" (duration of condition), "09:27" (when it started).
- If a case is pending, the paragraph links to it: "[Case #7]".
- Correlation is stated explicitly: "Correlated with deploy d-4521."
- Projections are included when relevant: "will breach in ~6 days at current rate."

**Prose generation:**
The situation board narrative is assembled deterministically from structured data, not generated by an LLM. This is important: the prose is templated from assessments and verdicts, ensuring consistency and speed. The templates are sophisticated enough to read naturally but mechanical enough to be trustworthy.

Example template structure:
```python
def render_degraded(service, assessment, verdict_chain):
    duration = humanize_duration(assessment.started_at)
    return (
        f"{service.name} DEGRADED {duration}. "
        f"{assessment.primary_metric.name} {assessment.primary_metric.value} "
        f"against {assessment.slo_target} SLO target. "
        f"{render_correlation(assessment)}. "
        f"{render_proposed_action(verdict_chain)}."
    )
```

### 2. Case Bench

The decision workspace. Shows one case at a time with full briefing.

**Case lifecycle:**
```
PROPOSED → BRIEFED → AWAITING_VERDICT → RESOLVED
                                      ↗
                          DEFERRED ──→ (re-queued)
```

**Case sources — a case is created when:**
- A remediation agent proposes an action requiring human approval (per safe action registry)
- An agent verdict has confidence below a configurable threshold
- An SLO breach is projected within a configurable window
- An anomaly is detected but no automated correlation is found
- A human-requested investigation completes

**Briefing structure:**

Each case briefing has four sections, always in this order:

1. **BRIEFING** — Narrative prose describing what happened, when, and what the agents found. Written in past tense. Includes temporal sequence, causal reasoning, and confidence levels. This is the "clerk's brief" — everything the operator needs to understand the situation without opening another tool.

2. **EVIDENCE** — Sparkline visualisations of the key metrics. Textual supports unicode block characters (▁▂▃▄▅▆▇█) which render reliable sparklines. Each line shows: metric name, sparkline (last 30 minutes), current value, and SLO target. Maximum 6 metrics per case to prevent cognitive overload.

3. **AGENT VERDICTS** — The chain of AI verdicts that led to this case. Each entry shows: agent role, verdict summary, confidence score, and timestamp. Displayed as a compact table. The operator can expand any verdict to see full provenance (prompt, input assessments, raw response).

4. **YOUR VERDICT** — The action bar. Keybinding-driven. Options vary by case type.

**Verdict actions:**

| Key | Action | Effect |
|-----|--------|--------|
| A | Approve | Accept the proposed action. Records approval verdict. Triggers execution. |
| R | Reject | Reject the proposed action. Records rejection verdict. Requires reason (opens input). |
| M | Modify | Modify the proposed action. Opens editor with proposed action as template. |
| D | Defer | Move case to deferred queue. Requires re-queue time (15m / 1h / 4h / next shift). |
| E | Escalate | Escalate to another operator or team. Opens recipient selector. |
| I | Investigate | Request further investigation. Opens prompt input for investigation direction. |

**Human verdict record:**

When the operator renders a verdict, the following is written to the verdict store:

```json
{
  "verdict_id": "v-2026-04-10-0941-human-001",
  "type": "human_verdict",
  "case_id": "case-007",
  "operator": "rob@workday.com",
  "action": "approve",
  "target_verdict": "v-2026-04-10-0932-remediate-001",
  "reasoning": null,
  "rendered_at": "2026-04-10T09:41:33Z",
  "time_to_verdict_seconds": 87,
  "parent_hash": "sha256:abc123...",
  "hash": "sha256:def456..."
}
```

This verdict has the same structural guarantees as any AI verdict: append-only, hash-chained, full provenance. The `time_to_verdict_seconds` field is automatically captured (time from case presentation to action) and feeds back into the learn cycle as a human decision quality signal.

### 3. Detail Pane (F2 / Enter to expand)

A slide-out panel for drilling into any element:

- **Verdict detail:** Full provenance — the prompt sent to the agent, the assessments it consumed, the raw LLM response, the extracted verdict.
- **Assessment detail:** The raw metric queries, evaluation results, threshold comparisons.
- **Service detail:** OpenSRM spec excerpt, dependency tree (rendered as a Textual Tree widget), current SLO status table.
- **History:** Verdict chain for a service — all verdicts in chronological order with hash verification status.

### 4. SLO Status View (F3)

A full-screen table view of all services and their SLO status:

```
SERVICE              SLO TARGET   CURRENT   BUDGET    BURN RATE   STATUS
payment-service      99.0%        95.8%     12%       8.4x        DEGRADED
search-api           99.5%        99.2%     64%       1.4x        WATCH
user-auth            99.9%        99.95%    88%       0.3x        NOMINAL
catalog-service      99.0%        99.7%     94%       0.2x        NOMINAL
...
```

Sortable by any column. Colour-coded status. This is the "at a glance" view that replaces a Grafana SLO dashboard for most purposes.

## Data Flow

```
Prometheus ──→ nthlayer-observe ──→ Assessment Store
                                         │
                                         ▼
                                   nthlayer-respond
                                   (triage, investigate,
                                    communicate, remediate)
                                         │
                                         ▼
                                    Verdict Store ◄──── nthlayer bench
                                         │              (human verdicts)
                                         ▼
                                    Case Queue
                                         │
                                         ▼
                                   ┌─────────────┐
                                   │  BENCH UI    │
                                   │              │
                                   │ Situation    │
                                   │ Board        │
                                   │              │
                                   │ Case Bench   │
                                   │              │
                                   │ Detail Pane  │
                                   └─────────────┘
```

The Bench polls the following APIs:

| Endpoint | Interval | Purpose |
|----------|----------|---------|
| `/api/v1/assessments/current` | 5s | Service health for situation board |
| `/api/v1/verdicts/pending` | 2s | Cases awaiting human verdict |
| `/api/v1/verdicts/recent` | 10s | Agent activity for situation context |
| `/api/v1/slos/status` | 30s | SLO table data |
| Prometheus `/api/v1/query_range` | 5s | Sparkline data for case evidence |

## Textual Implementation

### Widget Hierarchy

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

### Key Widgets

```python
class SituationBoard(Static):
    """Living narrative of system state."""

    situation_text = reactive("")

    def on_mount(self):
        self.set_interval(5.0, self.refresh_situation)

    async def refresh_situation(self):
        assessments = await self.app.api.get_current_assessments()
        verdicts = await self.app.api.get_recent_verdicts()
        pending = await self.app.api.get_pending_cases()
        self.situation_text = SituationRenderer.render(
            assessments, verdicts, pending
        )

    def watch_situation_text(self, text: str):
        self.update(Rich.from_markup(text))


class CaseBench(Widget):
    """Judicial decision workspace."""

    current_case = reactive(None)

    def compose(self) -> ComposeResult:
        yield CaseBriefing(id="briefing")
        yield EvidencePanel(id="evidence")
        yield AgentVerdictTable(id="agent-verdicts")
        yield VerdictBar(id="verdict-bar")

    async def load_next_case(self):
        case = await self.app.api.get_next_pending_case()
        if case:
            self.current_case = case
            self.query_one("#briefing").render_case(case)
            self.query_one("#evidence").render_evidence(case)
            self.query_one("#agent-verdicts").render_chain(case)
            self.query_one("#verdict-bar").activate(case)


class EvidencePanel(Static):
    """Sparkline visualisations of case-relevant metrics."""

    SPARKLINE_CHARS = "▁▂▃▄▅▆▇█"

    def render_evidence(self, case: Case):
        lines = []
        for metric in case.evidence_metrics[:6]:
            spark = self.sparkline(metric.values)
            status_color = "red" if metric.breaching else "green"
            lines.append(
                f"── {metric.label} ──── {spark} "
                f"[{status_color}]{metric.current}[/] "
                f"(SLO: {metric.target})"
            )
        self.update("\n".join(lines))


class VerdictBar(Static):
    """Keybinding-driven action bar."""

    BINDINGS = [
        ("a", "approve", "Approve"),
        ("r", "reject", "Reject"),
        ("m", "modify", "Modify"),
        ("d", "defer", "Defer"),
        ("e", "escalate", "Escalate"),
        ("i", "investigate", "Investigate further"),
    ]

    async def action_approve(self):
        case = self.app.query_one("#bench").current_case
        verdict = HumanVerdict(
            case_id=case.id,
            action="approve",
            target_verdict=case.proposed_verdict_id,
            operator=self.app.operator_id,
        )
        await self.app.api.submit_verdict(verdict)
        self.app.query_one("#bench").load_next_case()
```

### Styling (bench.tcss)

```css
/* Nord palette */
$nord0: #2E3440;
$nord1: #3B4252;
$nord2: #434C5E;
$nord3: #4C566A;
$nord4: #D8DEE9;
$nord6: #ECEFF4;
$nord8: #88C0D0;
$nord11: #BF616A;
$nord13: #EBCB8B;
$nord14: #A3BE8C;

Screen {
    background: $nord0;
    color: $nord4;
}

#situation {
    height: auto;
    max-height: 40%;
    padding: 1 2;
    border-bottom: solid $nord3;
}

#bench {
    height: 1fr;
    padding: 1 2;
}

#verdict-bar {
    dock: bottom;
    height: 3;
    background: $nord1;
    padding: 0 2;
}
```

## SaaS Delivery via textual-web

```bash
# Local operation
nthlayer bench --cluster prod-eu-west-1

# SaaS delivery
textual-web serve nthlayer.bench:NthLayerBench \
  --host 0.0.0.0 \
  --port 8443 \
  --tls
```

**Session model:** One Python process per connected operator. For a typical enterprise deployment (5-20 SRE users per tenant), this is well within resource bounds. Each session maintains its own polling loops and case queue position.

**Authentication:** textual-web supports reverse proxy auth headers. In SaaS mode, the Bench reads `X-Operator-Id` from the proxy to identify the operator for verdict attribution.

**Multi-tenancy:** Each tenant's Bench instance connects to their NthLayer platform APIs. Tenant isolation is at the API layer, not the UI layer.

## Relationship to Other Interfaces

| Interface | Audience | Purpose | Medium |
|-----------|----------|---------|--------|
| `nthlayer bench` | SRE operator | Make decisions, situational awareness | Terminal / textual-web |
| `nthlayer` CLI | CI/CD, scripts | Generate, measure, evaluate | Terminal (non-interactive) |
| React topology | VP, buyer, demo | Architecture visualisation, sales | Browser |
| Grafana dashboards | Deep investigation | Metric exploration, ad-hoc queries | Browser |

The Bench does not replace Grafana. When an operator needs to explore data beyond what the case briefing provides, they open Grafana. The Bench's job is to make that unnecessary for 90% of operational decisions.

## Metrics the Bench Captures

The Bench itself is instrumented. Every human interaction produces telemetry:

- **time_to_verdict**: Seconds from case presentation to verdict action.
- **verdict_agreement_rate**: How often the human approves vs rejects agent proposals.
- **case_deferral_rate**: How often cases are deferred rather than resolved.
- **investigation_request_rate**: How often the human asks for more information (signals briefing quality).
- **session_duration**: How long operators spend in the Bench.
- **cases_per_session**: Throughput of human decision-making.

These feed directly into Judgment SLOs. The Bench doesn't just consume the reliability loop — it instruments the human's participation in it.

## Build Sequence

### Phase 1: Static prototype (2-3 days)
- Textual app with hardcoded data
- Situation board with three mock services
- One mock case with full briefing
- Verdict actions that print to console
- Nord palette styling
- Serve via textual-web for shareable demo URL

### Phase 2: Live data integration (3-5 days)
- Connect to nthlayer-observe assessment API
- Connect to verdict store
- Connect to Prometheus for sparkline data
- Case queue from pending verdicts
- Human verdict submission to verdict store

### Phase 3: Operational completeness (3-5 days)
- SLO status table (F3)
- Detail pane with verdict provenance
- Verdict history view (F2)
- Keyboard shortcuts for all navigation
- Case deferral with re-queue scheduling
- Escalation flow

### Phase 4: SaaS readiness (2-3 days)
- textual-web deployment configuration
- Reverse proxy auth integration
- Operator identification from auth headers
- Session management
- TLS configuration

## Open Questions

1. **Case prioritisation algorithm.** Currently implied as severity-based. Should it factor in error budget burn rate, time-sensitivity of proposed action, or operator expertise?

2. **Multi-operator coordination.** If two operators are on the Bench simultaneously, how are cases assigned? First-come-first-served with locking? Round-robin? Explicit assignment?

3. **Offline verdict queue.** If the operator is not on the Bench, should proposed actions auto-execute after a configurable timeout, or wait indefinitely? This is a per-action-type policy decision that belongs in the OpenSRM spec.

4. **Situation board personalisation.** Should operators be able to filter the situation board to their services, or should everyone see everything? Team-based scoping seems right but adds complexity.

5. **Mobile access.** textual-web renders in a browser, which means it technically works on mobile. But the keyboard-driven interaction model doesn't translate. Is there a separate mobile notification surface, or does ntfy (already in the respond spec) cover this?
