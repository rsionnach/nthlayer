# Respond SRE CLI Inventory — for nthlayer-bench follow-up

**Date:** 2026-04-26
**Source:** `nthlayer-respond/feat/opensrm-0rg-cli` (commits `8e80122` + `4fa616e`)
**Destination:** nthlayer-bench (Tier 3 operator interface) — follow-up bead in P4
**Purpose:** Preserve operator-tooling intent and bench-equivalent shape for 6 SRE CLI subcommands stranded in the deprecated `nthlayer-respond` repo, so the P4 bench bead does not need to reverse-engineer behaviour from legacy code.

## Context

The legacy `feat/opensrm-0rg-cli` branch added 6 SRE-facing CLI subcommands plus 5 supporting logic modules (`sre/brief.py`, `sre/shift_report.py`, `sre/suppression.py`, `sre/delegation.py`, `sre/post_incident.py`). The CLI parser entries were added but **the `main()` dispatch handlers were never wired** — so the parser advertises the commands but invoking them prints help and exits. The logic modules are framework-free (no argparse coupling, no Click coupling) and operate purely on the verdict store. They migrate cleanly to bench.

Decision (2026-04-26): legacy repo deprecates as-is; commands are *not* ported to `nthlayer-workers/respond/cli.py` because they are operator-interactive, not background-computation. Their natural home is bench.

## Commands

### 1. `oncall` — Show current on-call schedule

- **Behaviour.** Reads `ownership.oncall` from OpenSRM manifest YAMLs, resolves the current on-call responder via the existing timezone-aware rotation logic in `nthlayer-respond/oncall/{schedule,runner,escalation}.py`, prints the responder.
- **Data.** Reads OpenSRM manifest specs in `--specs-dir`. Writes nothing.
- **Primary user.** Any SRE who needs to know who's on-call right now — status check, paging context, "should I escalate to who".
- **Bench-equivalent shape.** A persistent "Who's on-call" widget on the situation board, refreshed every 60s. Either a status-bar item or a sidebar panel showing the current responder + the next rotation handover time. The underlying schedule resolution stays the same; bench just renders it.
- **Demo relevance.** Operational-only. Not core demo content — though a status-bar mention would reinforce the operator-experience narrative if framing fits.

### 2. `brief` — Generate paging brief for an incident

- **Behaviour.** Walks verdict lineage from the triage verdict for a given incident; builds a structured `PagingBrief` (severity, service, summary, likely_cause + cause_confidence, blast_radius, recommended_action); renders concise output. Every field traces to a verdict; **no LLM call**.
- **Data.** Reads verdict store (lineage walk + filtered queries). Writes stdout.
- **Primary user.** SRE who has just been paged for an incident and needs the "what's broken, why, what can I do" answer in 5 seconds.
- **Bench-equivalent shape.** When the SRE selects a case in the case bench, the right pane auto-renders the brief from current verdicts. Updates live as new verdicts arrive. This is core case-detail UI — arguably the most-used operator surface.
- **Demo relevance.** **DEMO-RELEVANT.** This is the "how does NthLayer help an SRE understand the incident" flow. Should be in the v1.5 demo. Strong narrative: "you're paged → you see this auto-generated brief → you act."

### 3. `shift-report` — Generate shift report for a time window

- **Behaviour.** Queries verdicts within a `[--from, --to]` time window (triage verdicts as incidents, evaluation verdicts, pending reviews); produces a `ShiftReport` with incident count, evaluation count, pending review count, plus per-incident summaries. No LLM call.
- **Data.** Reads verdict store (windowed query). Writes stdout.
- **Primary user.** SRE at start of shift (handover briefing) or engineering manager reviewing shift activity.
- **Bench-equivalent shape.** A "Shift report" view filterable by time range — date-picker or presets ("last 8h", "since I last logged in", "previous shift"). Tabular layout: incidents in column 1, governance changes in column 2, pending reviews in column 3. Exportable to markdown.
- **Demo relevance.** Possibly demo-relevant for operator-experience storytelling, but secondary to `brief` and `post-incident`. Skip in initial demo unless the script specifically calls for shift-handover narrative.

### 4. `suppress` — Create alert suppression rule

- **Behaviour.** Creates a `Suppression` rule keyed on `(service, metric, window)` with a baseline value and override-threshold multiplier (default 3.0×). If the current metric value exceeds `baseline × multiplier`, the suppression is automatically overridden and the SRE is paged with context explaining why ("suppression overridden — observed 4.2× baseline"). Baseline is arithmetic (historical mean); override detection is one comparison. No LLM call.
- **Data.** Reads nothing at create-time. Writes a suppression rule to a TBD store (legacy implementation has the data structure; persistence layer was unfinished).
- **Primary user.** SRE creating a "don't page me for nightly backup latency 02:00–04:00" type rule.
- **Bench-equivalent shape.** A form in the case bench: "suppress this metric on this service during this window because `<reason>`". Optional review reminder ("re-evaluate in 30 days"). Active suppressions visible as badges in the situation board. The override-on-spike logic stays exactly the same — bench is just the form.
- **Demo relevance.** **POSSIBLY DEMO-RELEVANT** — only if the demo includes a known-flaky alert that should be suppressed (e.g. a nightly batch latency that fires every night without being a real incident). The auto-override behaviour is a good narrative beat: "you suppressed it, but the system overrode you because it crossed 3× baseline." Worth scoping for v1.5 demo if that arc is included.

### 5. `post-incident` — Generate post-incident review

- **Behaviour.** Walks the full verdict chain for an incident; builds a structured `PostIncidentReview` with: chronological timeline (built from verdict timestamps + summaries), what-worked vs what-to-improve (classified from verdict outcomes), per-verdict accuracy (from outcome resolution). Optional LLM call for action-item suggestions, **off by default**.
- **Data.** Reads verdict store (full lineage walk for the incident). Writes stdout (rendered review).
- **Primary user.** Post-incident review team running a retrospective; SRE writing up the incident; engineering manager reading the summary.
- **Bench-equivalent shape.** When an incident is in `RESOLVED` state, a "Review" tab on the case detail auto-renders this content. Editable export to markdown / JIRA / Confluence. The structure (timeline + worked/improve + accuracy) maps directly to most retrospective templates.
- **Demo relevance.** **DEMO-RELEVANT.** Auto-generated retrospectives are a strong NthLayer narrative — "the system writes the review for you, every field traces to a verdict, no hallucinated facts." Should be in the v1.5 demo paired with `brief` (page → understand → resolve → review).

### 6. `delegate` — Delegate incident to autonomous handling

- **Behaviour.** Marks an incident as delegated for a bounded duration (default 2h, parsed as `Nh` / `Nm`). While delegated: coordinator runs only pre-approved safe-actions (no human-approval prompts), notifications suppressed except for `resolution` or `escalation` events. Auto-revoked on expiry or escalation. Status lifecycle: `ACTIVE → EXPIRED | ESCALATED | RESOLVED`.
- **Data.** Reads nothing at delegate-time. Writes a `Delegation` record to a TBD store (legacy implementation has the dataclass; persistence layer was in-memory).
- **Primary user.** SRE in a multi-incident situation who needs to deprioritise a lower-severity incident — "I'm busy with P1, autonomous-handle this P3 for 2h."
- **Bench-equivalent shape.** Right-click on a case → "Delegate for `<duration>`, safe-actions only". Visible badge on the case in the situation board. Active delegations listed in a sidebar with countdown. Auto-revoke produces a notification.
- **Demo relevance.** Operational-only. Advanced workflow that requires multi-incident context to motivate. Skip in initial demo.

## Demo-relevance summary

| Command | Demo prio for v1.5 |
|---|---|
| `brief` | **High** — pair with `post-incident` for full operator narrative |
| `post-incident` | **High** — auto-generated retrospectives are a flagship story |
| `suppress` | **Medium** — only if demo arc includes a flaky alert / override beat |
| `shift-report` | **Low** — secondary operator content |
| `oncall` | **Low** — status bar mention if framing fits, otherwise skip |
| `delegate` | **Low** — needs multi-incident context that the demo doesn't have |

## Migration approach for the P4 bench bead

1. The 5 logic modules in `sre/*.py` (brief, shift_report, suppression, delegation, post_incident) are framework-free and operate against the verdict store via `nthlayer_learn.VerdictFilter`. Migrate them as-is into `nthlayer-bench/src/nthlayer_bench/sre/`. The verdict-store reads need to flip to `CoreAPIClient.get_verdicts(...)` since bench talks to core via HTTP per the three-tier architecture.
2. Each command's bench-equivalent UI is a Textual screen / panel; the logic modules supply the data. UI work is the new piece; logic is forward-port.
3. The two unfinished persistence layers (`Suppression` rules, `Delegation` records) need a home. Likely `nthlayer-core` adds new endpoints (`POST /suppressions`, `POST /delegations` + `GET` variants) since these are reliability-critical state, not background computation.
4. Demo-prioritised order: `brief` + `post-incident` first (both pure-read, no new core endpoints needed), `suppress` second (needs core suppression endpoints), then `shift-report` / `oncall` / `delegate`.

## Source pointers (for the P4 bead author)

- Logic modules: `nthlayer-respond/feat/opensrm-0rg-cli` branch, `src/nthlayer_respond/sre/{brief,shift_report,suppression,delegation,post_incident}.py`
- Tests: `tests/test_sre_brief.py`, `test_sre_shift_report.py`, `test_sre_suppression.py`, `test_sre_delegation.py`, `test_sre_post_incident.py`, plus `test_cli_sre.py` (parser-level)
- On-call resolution: `nthlayer-respond/oncall/{schedule,runner,escalation}.py` — already forward-ported into `nthlayer-workers/respond/oncall/` for worker-mode escalation; bench reuses the same modules for `oncall` command.
- This inventory should be referenced from the `nthlayer-respond` deprecation README so future readers find their way to the work that survived.
