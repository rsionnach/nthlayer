# opensrm-wo62.1 — nthlayer-generate on nthlayer-common's manifest model

**Bead:** opensrm-wo62.1 (P1), epic opensrm-wo62. **Status:** for review.
**Binding input:** Rob's four decisions of 2026-10-24 (bead notes), restated in
§2. Every `Ruling:` line below is a call this document makes on Rob's behalf,
with what it costs if it is wrong; each needs his yes before Checkpoint A.

All file:line citations were checked against nthlayer-generate `main`
(ebf484c, 2.1.1) and nthlayer-common `main` (052a8fb, 5.3.1) on 2026-10-24.

## 1. Problem

nthlayer-generate runs a second manifest stack — `specs/manifest.py` (931
lines), `specs/loader.py` (570), `specs/opensrm_parser.py` (670) — beside
nthlayer-common's, which every other member uses. Consequences measured today:

- **v2 is unreadable.** generate's `load_manifest` (`specs/loader.py:60`)
  knows `srm/v1` and legacy only; an `opensrm.nthlayer.io/v2` manifest falls to
  the legacy branch and fails with `service.name is required`.
- **Vocabulary drift.** generate's `JUDGMENT_SLO_TYPES`
  (`specs/manifest.py:125`) still lists `calibration` and `feedback_latency` as
  SLOs; common 4.0 made them `JudgmentThreshold`s (decision 3c, opensrm-l33e).
- **Two parses of one file disagree.** Loading the 27 example manifests with
  both loaders (§6) gives different `slo_type`, `dependencies`,
  `indicator_query` or judgment structure on 16 of them.

## 2. Decisions (Rob, 2026-10-24 — binding)

1. **Scope.** Retire generate's manifest stack (`specs/manifest.py`,
   `specs/loader.py`, `specs/opensrm_parser.py`). Every `load_manifest`
   consumer moves to `nthlayer_common.manifest.load_manifest` /
   `ReliabilityManifest` (align, don't adapt). The legacy
   `parse_service_file` / `ServiceContext` stack (`specs/parser.py`,
   `specs/models.py`; 12 CLI commands and plan/apply) is **out**: a follow-up
   bead routes it through common.
2. **Judgment rules.** Port the `ai_gate:calibration:*` and
   `ai_gate:feedback_latency:*` recording rules in this bead, built from
   common's `JudgmentThreshold`, with identical record names and labels.
   wo62.2 adds alerts, docs, segments, stability and audit_backlog.
3. **common first, a minor.** common gains `ReliabilityManifest.authored_type`
   and its srm/v1 parser reads an SLO's top-level `query:`; gated and released
   before generate starts. generate keeps generate-only behaviour: it parses the
   raw `alerting` dict with its own `parse_alerting_config` at the use sites,
   adapts `specs/contracts.py` to `manifest.contracts`, and owns local helpers
   for what `to_dict` / `as_service_context` did.
4. **Pin before switching.** Golden tests capture today's outputs — all 7
   srm/v1 examples × every manifest-path consumer, plus the legacy examples ×
   the `load_manifest` consumers — before the switch. After it, every golden
   change and every newly-failing manifest is listed for Rob before the R5 gate.

## 3. What the switch changes, mechanically

| # | Today (generate model) | Under common | Where generate reads it |
|---|---|---|---|
| D1 | `calibration`, `feedback_latency` are `SLODefinition`s | `JudgmentThreshold`s in `judgment_thresholds`; absent from `slos` | `recording_rules/manifest_builder.py:333-357` (dispatch), `:457`, `:499`; every consumer iterating `slos` |
| D2 | srm/v1 SLO `query:` → `indicator_query` (`specs/opensrm_parser.py:237`); `indicator.query` ignored | `indicator.query` only (`parser/v1.py:196-213`); top-level `query` dropped since opensrm-0i5h (0fb5096) | sloth, dashboards, pipeline |
| D3 | `alerting: AlertingConfig` parsed at load (`specs/opensrm_parser.py:524`) | raw dict (`models.py:983`, `parser/v1.py:124`) | `slos/pipeline.py:117,127`; `generators/alerts.py:128,228`; `cli/alerts.py:75` |
| D4 | `contract: Contract` (single) | `contracts: list[ReliabilityContract]`; srm/v1 contract becomes `contracts[0]` named `<service>-api` | `specs/contracts.py:37-38,145,178-180` |
| D5 | `validate_contracts` compares raw judgment ratios, "below" | direction-based, judgment promise in SLI-floor space (`models.py:1066`; `target_validation.py:280`) | `specs/validator.py:148` |
| D6 | `authored_type` kept (`specs/manifest.py:527,594`) | aliases rewritten in place (`models.py:1025`); no authored spelling | `generators/sloth.py:264` (`${type}`) |
| D7 | `to_dict`, `as_service_context`, `as_resources`, `to_service_context` | none | `cli/migrate.py:101`; `dashboards/manifest_builder.py:78`; `metrics/recommender.py:39` (the other two have no `src` caller) |
| D8 | `slo_type` may be `None` | always inferred; raises if not inferable | sloth `:239`, backstage `sloType`, docs Type column, dashboards, recording-rule dispatch |
| D9 | `SourceFormat.OPENSRM = "opensrm"` | `SRM_V1 = OPENSRM = "srm_v1"`, plus `OPENSRM_V2` (`models.py:195-207`) | `cli/migrate.py:92` |
| D10 | no load-time warnings | `TargetConventionWarning` for any SLO target in (0, 1) (`target_validation.py:312-358`, called at `parser/loader.py:139`) | every load |
| D11 | legacy: `service.pagerduty` → ownership (`specs/loader.py:219-227`); `Dependencies.spec.services` ignored | the reverse | legacy consumers |
| D12 | judgment rules dispatch on `slo.name` (`manifest_builder.py:348-355`) | v2 judgment SLO names are free-form; the type is `judgment_type` | recording rules |
| D13 | `is_valid_service_name`, `SERVICE_NAME_PATTERN`, `VALID_TIERS` live in `specs/manifest.py:42-100` | — (these are generate's own, stricter rule) | `cli/init.py:22`, `cli/setup.py:51`, `specs/validator.py:29` |

D1–D10 are the survey's; D11–D13 were found while writing this spec.

## 4. nthlayer-common 5.4.0 (Checkpoint A)

### 4.1 `ReliabilityManifest.authored_type`

The invariant is opensrm-z3ab's, stated at `nthlayer-generate/src/nthlayer_generate/specs/models.py:74-92`:
`type` is the resolved spelling internal branches compare against;
`authored_type` is exactly what the author wrote, and is what `${type}`
substitutes into generated PromQL, because rewriting `web` to `x-web` inside a
label matcher run against the operator's existing Prometheus selects zero
series. Pinned in generate by
`tests/test_service_type_agreement.py:325` and the sloth assertion above it.

- New field `authored_type: str | None = None`, **declared** (so
  `dataclasses.replace` keeps it — the second half of z3ab), placed last in
  the dataclass so no positional construction shifts.
- `__post_init__` sets it from `self.type` **before** the alias rewrite at
  `models.py:1025`, only when it is `None`.
- The v2 parser resolves the type before constructing the manifest
  (`parser/v2.py:164-170`), so it passes `authored_type=` the raw
  `spec.service.type`. The v1 and legacy parsers pass the raw type already and
  need no change.
- `convert_v1_to_v2` keeps writing the resolved spelling: a written v2 file
  carries the canonical type (same rule as generate's `to_dict`,
  `specs/manifest.py:854-860`).

### 4.2 srm/v1 top-level `query:`

`_extract_indicator_query(config)` (`parser/v1.py:196`) becomes the one reader
for both spellings: `indicator.query` if present, else a top-level `query`
string; empty or non-string values are absent, as today. It feeds
`_parse_slos`, `_infer_slo_type` (`:241`) and — so a migrated manifest does not
lose what a parsed one keeps — `v1_compat._v1_slo_to_openslo`
(`v1_compat.py:352-353`).

opensrm-0i5h removed the top-level read on the grounds that it was "not in any
spec or example". It is in one: nthlayer-generate's
`examples/uat/payment-api.reliability.yaml:23,35`, which generate's own parser
reads (`specs/opensrm_parser.py:237`). Its docstring is corrected to say so.

**Ruling: `indicator.query` plus a different top-level `query` is an `OpenSRMParseError`, not a precedence rule. Cost if wrong: such a manifest (none exists today) stops loading.**

Either precedence would silently discard a query the author wrote.

### 4.3 Release

Minor (5.4.0): one additive field, one parser that accepts strictly more. Notes
in `docs/architecture.md`'s manifest section. No upgrading guide (nothing a
consumer must change).

**Ruling: all five consumer floor bumps to 5.4.0, generate's included, land in Checkpoint A — the floor guard requires floor == installed (`nthlayer-generate/tests/test_dependency_declarations.py:140-190`). Cost if wrong: five extra patch releases.**

## 5. nthlayer-generate 3.0.0 (Checkpoints B and C)

### 5.1 The switch

Every import of `specs.manifest`, `specs.loader`, `specs.opensrm_parser`
moves to `nthlayer_common.manifest` (`load_manifest`, `ReliabilityManifest`,
`SLODefinition`, `ManifestLoadError`, `LegacyFormatWarning`,
`is_manifest_file`, `SourceFormat`). The three files are deleted. Consumers:
CLI migrate, topology, docs, backstage, alerts, simulate, validate;
`PolicyHandler` (`orchestration/handlers.py:468`); library generators
(sloth, alerts, dashboards, loki, recording rules, metrics, topology
enrichment, simulate graph, policies, backstage, docs) and
`specs/helpers.py`, `specs/contracts.py`, `specs/validator.py`.

Generate-owned rules that lived in `specs/manifest.py` move, unchanged, to a
new `specs/names.py`: `SERVICE_NAME_PATTERN`, `is_valid_service_name` (D13).
`VALID_TIERS` comes from common.

### 5.2 Use-site adaptations

- **alerting (D3).** `parse_alerting_config(manifest.alerting)` at the three use
  sites, through one helper `specs/alerting.py::manifest_alerting(manifest)`.
  A malformed `alerting` block now fails where it is used, not at load:
  `docs` and `backstage` accept a manifest they used to reject. Listed.
- **contracts (D4).** `ContractRegistry` stores `list[ReliabilityContract]` per
  service. Provider availability for `validate_dependency_expectations` is the
  minimum `promise.availability` over that service's contracts (the weakest
  promise is the most a consumer may rely on). `validate_transitive_feasibility`
  checks each of the manifest's contracts that declares availability; its
  message is unchanged when there is one contract and names the contract when
  there are several. For srm/v1 (one contract) behaviour is identical.
- **service context (D7).** `specs/context.py::service_context_from_manifest(manifest) -> ServiceContext`
  replaces `as_service_context` (same mapping: `authored_type` carried,
  PagerDuty escalation from `ownership.pagerduty`). `as_resources`,
  `to_service_context` and `load_as_legacy` have no `src` caller and go.
- **migrate (D7, D9).** `cli/migrate.py` gets a private
  `_legacy_to_srm_v1(manifest) -> dict`, a port of `to_dict`
  (`specs/manifest.py:839-931`) covering what the legacy parser can populate.
- **validator.** `specs/validator.py:107-118` routes `srm/v1` **and v2** to the
  manifest path (today v2 goes to `parse_service_file`), and filters common's
  `LegacyFormatWarning` (it filters generate's today; the classes differ).
- **recording-rule dispatch (D12).** Judgment SLO rules dispatch on
  `slo.judgment_type`, not `slo.name` (equal for srm/v1, different for v2).

**Ruling: `cli/migrate.py:92` becomes `source_format != SourceFormat.LEGACY`; srm/v1 and v2 both need no migration. Cost if wrong: a naive enum swap "migrates" v2 down to srm/v1.**

### 5.3 Judgment recording rules from `JudgmentThreshold` (D1)

`ManifestRecordingRuleBuilder` builds the judgment group from
`get_judgment_slos()` **then** `get_judgment_thresholds()`, and emits the group
if either is non-empty. Record names, expressions and labels are byte-identical
to today's (`manifest_builder.py:457-545`):

| Threshold | Emitted when | `target` label |
|---|---|---|
| calibration | `maximum_expected_calibration_error` in `bounds` | `str(bound)` — `"0.05"` for the ai-gate example, as today |
| feedback_latency, `:p50/:p95/:p99` | always | — (none today) |
| feedback_latency, `:bucket` | `maximum_p50` in `bounds` | `str(duration_seconds(maximum_p50))` — `"3600.0"`, as today; also the `le` value |

Not emitted, deferred to wo62.2: Brier-only calibration
(`opensrm/spec/v2/examples/judgment-thresholds/all-five-types.yaml`), and a
p90-only feedback bound — no identical-name rule exists for either. One
deliberate difference: srm/v1 `feedback_latency` with `unit: m` used to emit
`le="60.0"` for 60 minutes (a bug, `le` is in seconds); it now emits `3600.0`.
No example has a unit.

Ordering: today's group follows `spec.slos` order. Thresholds now follow the
judgment SLOs, so a manifest that lists `calibration` before `reversal_rate`
reorders its group. The ai-gate example does not.

Metric-contract note for wo62.3: common already has a threshold series
contract (`nthlayer_common/manifest/threshold_series.py`, opensrm-g32d) naming
`gen_ai_calibration_ece` and `gen_ai_feedback_latency_seconds`; these rules
read `ai_gate_calibration_error` and `ai_gate_feedback_latency_seconds_*`.
Decision 2 keeps them identical here, so the divergence survives this bead.

### 5.4 Warnings and contract semantics

**Ruling: adopt common's direction-based `validate_contracts` unchanged. Cost if wrong: `validate --strict` on the ai-gate example goes exit 0 → 1 (reversal_rate 0.05 "looser than" 90.0).**

The new warning is correct under common's convention: srm/v1 judgment targets
are 0–100 SLI floors (opensrm-5fff, opensrm-ocvu), and the example writes the
ratio `0.05`. The example is not edited in this bead — it is a golden input,
and editing it in the same diff would hide the change. Follow-up bead.

**Ruling: generate neither filters nor re-routes `TargetConventionWarning`; goldens record it. Cost if wrong: 4 of 7 examples newly warn on stderr, the 3 error_rate ones falsely (follow-up bead).**

It reaches stderr through `warnings`, as common intends (opensrm-pa2w). The
error_rate targets (0.1, 0.01, 0.5) are percentages, so those three warnings
are false positives of common's heuristic.

### 5.5 Public API and release

**Ruling: release generate 3.0.0 (`feat!` + `BREAKING CHANGE:`): `nthlayer_generate.specs` loses four names and three modules. Cost if wrong: a needless major; no ecosystem repo imports `nthlayer_generate`.**

Also breaking: every `*_from_manifest` takes common's model, and
`ContractRegistry.get_contract` is replaced (§5.2).

`nthlayer_generate.specs.__init__` keeps the legacy exports
(`parse_service_file`, `ServiceContext`, `Resource`) and stops re-exporting the
manifest names: callers import them from `nthlayer_common.manifest`.

**Ruling: delete `tests/uat_opensrm.py` — never collected, imports the retired loader, subsumed by the goldens. Cost if wrong: a manual script, recoverable from git.**

It is not collected because `testpaths = ["tests"]` only picks up `test_*`
files.

## 6. Goldens (Checkpoint B) and the predicted diff (Checkpoint C)

### 6.1 Corpus

- **srm/v1 (7):** `examples/opensrm/{ai-gate,api-basic,api-critical,batch,stream,worker}.reliability.yaml`,
  `examples/uat/payment-api.reliability.yaml`.
- **legacy (20):** `examples/services/*.yaml` (17) and
  `examples/uat/{payment-api,payment-api-with-slas,payment-api-partial-slas}.yaml`.
  `analytics-stream.yaml` fails in both loaders today (`Invalid type
  'stream-processor'`); it is pinned as a failure.
- **non-manifests (12), load record only:** `examples/environments/*.yaml` (6),
  `examples/services/environments/*.yaml` (3), `examples/slos/*.yaml` (3) —
  fragments that both loaders reject with `service.name is required`.
- **v2 (spec examples):** every `kind: ServiceManifest` file under
  `opensrm/spec/v2/examples/`, read from the `../opensrm` sibling with an
  assertion that it is present (generate's CI checks it out:
  `.github/workflows/ci.yml:27-37`; the "no opensrm checkout" comment at
  `specs/manifest.py:68-77` is stale and goes with the file). In B they are
  load records (all fail today); in C they get the full matrix.

Corpus lists are explicit and a presence test compares them with the
directory globs, so a new example fails the suite until it is classified.

### 6.2 Matrix (per manifest, one golden file per cell)

Load record (ok / exception type + message / warnings as category + message),
recording rules, sloth spec, `generate_alerts_from_manifest` output file, dashboard
JSON, Loki ruler file, metric recommendation, Backstage entity, docs (README,
ADRs, API doc), policy report against `examples/policies.yaml`,
`validate_manifest` result with a `ContractRegistry` built from
`examples/opensrm/`, alert pipeline result at 50 % simulated burn, simulate
failure/dependency models and a seeded (42, 200-run) `run_simulation`,
`build_topology` over a fixed graph, and CLI exit codes (+ written files) for
migrate, validate (+`--strict`, +`--policies`), alerts evaluate/show/test,
docs, backstage, simulate, topology export; `PolicyHandler.generate`'s count.
Outputs are compared as structure (YAML/JSON loaded), never as captured
console text. Masked values (Backstage `generatedAt`, pipeline timestamps and
alert ids) are found mechanically — each cell is run twice and every differing
leaf must be in the mask — and the mask is asserted non-vacuous.

### 6.3 Predicted golden changes at C

Measured by loading the corpus through both loaders on 2026-10-24. Rob
approves the actual list against this one; anything unpredicted is a finding.

| # | Change | Manifests |
|---|---|---|
| G1 | `slo_type` `None` → inferred: Backstage `sloType`, docs Type column, dashboard indicator type; sloth SLI branch where the name was not an exact type (e.g. `latency-p95` → latency branch) | all 6 `examples/opensrm`; legacy analytics-pipeline, auth-api, checkout-service, identity-service, mobile-api, notification-worker |
| G2 | `calibration`, `feedback_latency` leave `slos`: gone from Backstage, docs (README table, ai-gate API "Judgment SLOs"), dashboard, sloth, pipeline budgets; **recording rules unchanged** | ai-gate |
| G3 | `TargetConventionWarning` in the load record | ai-gate (2), api-critical, stream, worker |
| G4 | new contract warning; `validate --strict` exit 0 → 1 | ai-gate |
| G5 | legacy `Dependencies.spec.services` now read: new dependencies in alerts, docs, topology, simulate, policies, dashboards, migrate output, validate ("critical dependency has no contract") | analytics-pipeline, auth-api, mobile-api, payment-api, payment-api-with-deps, search-api |
| G6 | **none** — top-level `query:` carried by common 5.4.0 | uat/payment-api.reliability.yaml |
| G7 | newly load; every cell new | v2 spec examples |
| G8 | none expected | the other srm/v1 and legacy cells |

Newly failing manifests predicted: **none** (all 27 load or fail identically
under both loaders today). If any appears, it is listed separately.

## 7. Testing

- **common:** `authored_type` across v1, v2 and legacy for an alias (`web`,
  `background-job`, `pipeline` — common's `SERVICE_TYPE_ALIASES`, the
  documented input conveniences) and an extension type
  (`opensrm/spec/v2/examples/x-service-type.yaml`); survives
  `dataclasses.replace`. Top-level `query` with the SLO block copied verbatim
  from generate's `examples/uat/payment-api.reliability.yaml` (provenance
  comment with path and commit); both-keys-agree, both-keys-differ; migration
  carries it.
- **generate:** the goldens; the judgment port against the ai-gate example
  and `opensrm/spec/v2/examples/judgment-thresholds/{all-five-types,calibration-both-bounds,feedback-latency-p50-only}.yaml`;
  z3ab tests ported to common's model; every test that hand-builds generate's
  `SLODefinition` / `ReliabilityManifest` (13 files) moved to common's
  constructors with `slo_type` taken from the example the test claims to model.
  21 test files reference the retired stack (`grep -rlE
  "ReliabilityManifest|SLODefinition|load_manifest|specs\.manifest|specs\.loader|opensrm_parser" tests`).
- **Kill checks (provenance pass):** renaming a calibration record, dropping
  the threshold branch, or reverting `authored_type` substitution must each turn
  a golden or targeted test red.

## 8. Out of scope (follow-up beads, Checkpoint D)

1. Route the legacy `parse_service_file` / `ServiceContext` CLI (12 commands)
   and plan/apply through common (decision 1).
2. Rewrite `examples/opensrm/ai-gate.reliability.yaml`'s judgment targets in
   the 0–100 convention, or migrate it to v2 (§5.4).
3. common: `TargetConventionWarning` false positives on `error_rate` targets.
4. wo62.2 inputs: Brier-only calibration and p90 feedback rules (§5.3).
5. wo62.3 input: `ai_gate_*` source metrics vs common's `THRESHOLD_SERIES`
   `gen_ai_*` names; the `target` label means a ratio for srm/v1 examples and an
   SLI floor for v2 judgment SLOs.
6. `cli/migrate.py:169-171` compares the resolved type with alias spellings and
   can never fire.
