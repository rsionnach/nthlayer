# opensrm-wo62.2 — judgment-threshold recording rules, alerts and docs

**Bead:** opensrm-wo62.2 (epic opensrm-wo62) · **Repo:** nthlayer-generate
**Date:** 2026-10-27 · **Builds on:** `2026-10-24-wo62-1-generate-on-common-manifest-design.md` §5.3
**Spec:** `opensrm/OPENSRM-CORE-v2.md` §5.5 (types, bounds), §5.5.6 E1–E4

## 1. Goal

Make every declared `spec.judgment_threshold` bound visible in generate's
output:

- Each bound that has a data source gets a recording rule, a breach alert and
  a not-evaluable alert.
- A bound with no data source is shown in the docs as evaluated by
  nthlayer-workers.

Today's gaps:
- Brier-only calibration emits nothing.
- There is no p90 rule.
- Generate emits no judgment alerts.
- The docs list judgment SLOs but no thresholds.

## 2. Rulings (Rob, 2026-10-27)

| # | Decision | Ruling |
|---|---|---|
| D1 | Metric names | New rules stay in the `ai_gate_*` family. Alerts read **only** generate's own `ai_gate:*` recording rules, never raw series. When opensrm-ln7w (A1 revision) fixes OpenSRM's metric prefix, wo62.3 renames the recording rules' *sources* and the alerts do not change. |
| D2 | segments / stability / audit_backlog | No rules. common's `THRESHOLD_SERIES` maps them to `{}` (no data source). The docs section lists each declared bound as "evaluated by nthlayer-workers; no Prometheus rule". |
| D3 | E3 in Prometheus | Each bound gets a breach alert plus a `…NotEvaluable` companion alert. |
| D4 | Defaults | Breach: `severity: warning`, `for: 15m`. NotEvaluable: `severity: info`, `for: 1h`. |
| D5 | Release | generate 3.1.0, a minor release: new rules and alerts appear in the output, and no existing rule changes. No nthlayer-common change is expected. If one is needed, stop, then gate and release common first. |

## 3. Window and tier rulings (Rob, 2026-10-27: Q1 and Q2 as recommended)

**Q1 — Window semantics for feedback_latency alerts.** The existing
`ai_gate:feedback_latency:p50/p95/p99` rules are 5-minute quantiles. §5.5.5
defines p50 and p90 over a rolling **30-day** window of arrivals. A 5-minute
p50 compared against the bound would fire on noise, so it is not E1 as the
spec writes it.

- *Ruled:* add two window-correct rules, used only by alerts and emitted
  only for a declared bound:
  - `ai_gate:feedback_latency:p50_30d`
  - `ai_gate:feedback_latency:p90_30d`

  Each is `histogram_quantile(q, sum by (le) (increase(ai_gate_feedback_latency_seconds_bucket{service="S"}[30d])))`,
  the same query shape workers' sampler uses. The existing 5m rules stay
  byte-identical. Cost: one 30-day range query per declared bound per rule
  evaluation. Set `interval: 5m` on this group if a per-group interval is
  available.
- *Rejected:* alert on the 5-minute rules and accept noise.

**Q2 — Tier filtering.** `filter_by_tier` keeps only `critical` alerts for
`tier: low`, and `standard` keeps `critical` and `warning`. As written, D4
would drop every threshold alert on a low-tier ai-gate, and every info
NotEvaluable on a standard-tier one.

- *Ruled:* threshold alerts are added **after** tier filtering. A
  declared bound is an explicit request, unlike a dependency template.

Calibration needs no window ruling. `ai_gate_calibration_error` is a gauge
that is already computed over the declared window (common's contract labels
it with `bins` and `window`).

## 4. Recording rules (Checkpoint B)

Group `<name>_judgment_metrics` (30s), ordered as today: judgment SLOs, then
thresholds in manifest order. Existing rules stay byte-identical. The `_30d`
rules go in a separate group, `<name>_judgment_thresholds_30d`, at
`interval: 5m` (Rob, Checkpoint B), so the 30-day range query does not run
every 30s.

| Type | Bound declared | Rules emitted | Change |
|---|---|---|---|
| calibration | ECE | `ai_gate:calibration:ece` + 3 `calibration_bucket` | unchanged |
| calibration | Brier | **`ai_gate:calibration:brier`** = `avg(ai_gate_calibration_brier{service="S"})`, labels `service`, `target=str(bound)`, `slo=calibration` | new |
| calibration | both | union of the two rows above | new |
| feedback_latency | any | `:p50/:p95/:p99` (5m) | unchanged |
| feedback_latency | p50 | `:bucket` + **`:p50_30d`** (Q1) | `_30d` new |
| feedback_latency | p90 | **`:p90_30d`** (Q1), labels `service`, `target=<seconds>`, `slo=feedback_latency` | new |
| segments / stability / audit_backlog | any | none (D2) | unchanged |

A `target` label carries the bound in the comparison unit: a ratio as
declared, a Duration in seconds via common's `duration_seconds` (E2).

Two entries with the same bound produce identical rule pairs. This is
pre-existing and out of scope; record it as a minor follow-up if the golden
corpus shows it.

`ai_gate_calibration_brier` is a new source name inside the D1 family. It
mirrors common's `gen_ai_calibration_brier`, and wo62.3 maps one onto the
other.

## 5. Alert rules (Checkpoint C)

New module `generators/judgment_threshold_alerts.py`. It turns a
`ReliabilityManifest` into a `list[AlertRule]`.
`generate_alerts_from_manifest` appends its output after tier filtering
(Q2). The output appears in the `alerts` and `cli_alerts_*` golden cells.

For each declared bound with a rule, given its record `R`, label selector `{service="S", …}` and comparison value `B`:

| Alert | expr | for | severity |
|---|---|---|---|
| `AIGate<Type><Bound>Breach` | `R{sel} > B` (E1: strictly greater) | 15m | warning |
| `AIGate<Type><Bound>NotEvaluable` | `absent(R{sel}) or (R{sel} != R{sel})` | 1h | info |

- Names: `AIGateCalibrationECE…`, `AIGateCalibrationBrier…`,
  `AIGateFeedbackLatencyP50…`, `AIGateFeedbackLatencyP90…`.
- `R != R` catches NaN. `histogram_quantile` over a window in which no
  ground truth arrived returns NaN rather than an absent series, and E3 counts
  that window as not evaluable.
- Calibration selectors include `target="<bound>"`, so several entries stay
  distinct.
- Labels on both alerts: `service`, `team`, `threshold_type`, `bound`
  (for example `maximum_p90`), `severity`.
- Annotations: summary and description state the measured value, the bound
  and spec §5.5.6. The runbook comes from `runbook_url`, as for other alerts.
- E4 (combining outcomes into one) is not encoded in Prometheus. Each bound
  alerts on its own, which is the most granular form E4 allows. Combining is
  workers' job (`evaluate_threshold`).

## 6. Docs (Checkpoint D)

`generators/docs.py` `_api_docs_ai_gate` gets a "## Judgment thresholds"
section after "## Judgment SLOs", listing one row per declared entry and
bound:

| Type | Bound | Value | Evaluated by |
|---|---|---|---|
| calibration | maximum_brier_score | 0.05 | Prometheus: `ai_gate:calibration:brier`; alerts `AIGateCalibrationBrier{Breach,NotEvaluable}` |
| segments | maximum_variance_from_overall | 0.05 | nthlayer-workers; no Prometheus rule |

- Measurement fields (bins, window, segment dimension/values, probe) go
  under each row.
- The section is omitted when the manifest declares no thresholds.
- The README section is unchanged. It lists SLOs, and thresholds are not
  SLOs (§5.5).

## 7. Tests and goldens

- Unit tests derive every fixture shape from the spec bound table (§5.5)
  and common's `THRESHOLD_BOUNDS`, not from the builder (provenance rule).
- They cover: Brier-only, ECE-only, both bounds, p50-only, p90-only, both
  bounds, two calibration entries, no-source types, and E1 equality
  (a value equal to the bound does not fire). Check equality with promtool
  `test rules` if promtool is available; otherwise assert the expression's
  operator.
- Golden fixtures: `opensrm/spec/v2/examples/judgment-thresholds/*` and
  `examples/opensrm/ai-gate.reliability.yaml`.

**Expected golden diff:**

| Cell | Change |
|---|---|
| `recording_rules` | `all-five-types` gains brier + p50_30d + p90_30d; `calibration-both-bounds` gains brier; `single-bounds` gains p90_30d; `feedback-latency-p50-only` and the srm/v1 example gain p50_30d |
| `alerts`, `cli_alerts_*` | new alerts for the same files |
| `docs`, `cli_docs` | new section for the five threshold fixtures and the srm/v1 example |
| everything else | no change |

Any diff outside that list is a bug until explained. Rob approves each
checkpoint's diff (`handoffs/…-wo62-2-checkpoint-{B,C,D}-golden-diff.md`).

## 8. Out of scope

- Renaming `ai_gate_*` → OpenSRM prefix (wo62.3, after ln7w).
- Rules for segments / stability / audit_backlog (needs a series contract first).
- Legacy-format segments / stability / audit_backlog (opensrm-1l6f).
- Duplicate rules from duplicate entries (pre-existing).
