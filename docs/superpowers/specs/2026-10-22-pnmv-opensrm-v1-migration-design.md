# opensrm-pnmv — `opensrm/v1`: reject clearly, migrate to v2

**Bead:** opensrm-pnmv (P1). **Status:** design approved in conversation
2026-10-22; this document is for review.

**Revision 1 (2026-10-22, before planning).** Probing common's parser and the
v2 schema found the first version's map could not produce valid output in
five places. Rob's rulings: v1 judgment SLOs are unmapped; the parser learns
`resource:` refs; a missing `spec.type` is an error unless supplied
(`--service-type`); throughput and parser-untypeable SLOs are unmapped. Also:
error-rate targets complement to good-ratios, `openslo[]` paths become `$ref`
items, `timeWindow` is always emitted, and a v2-invalid name is an error.

## 1. Problem

The spec's published v1 format — `apiVersion: opensrm/v1`, the shape of
`opensrm/spec/v1/schema.json` and every example in `opensrm/examples/` —
cannot be loaded by NthLayer. `load_manifest` recognises only `srm/v1`
(`parser/v1.py`), so an `opensrm/v1` document falls through to the legacy
parser and fails with the misleading `service.name is required`.

Research for this bead found the gap is not an apiVersion rename. `srm/v1`
(what NthLayer parses) and `opensrm/v1` (what the spec publishes) differ in
nearly every section: judgment SLO nesting (`slos.judgment.<type>` vs flat),
contract judgment keys, dependency keys (every schema-shaped dependency would
be dropped), instrumentation, deployment gate keys, `feedback_latency`
(`p50`/`p90` vs `target`+`unit`), and target units (0–1 ratios vs 0–100).
Nothing in the ecosystem produces `opensrm/v1` except the spec's examples, and
the v2 schema already rejects it (AUTHORING.md §2).

## 2. Decision

Rob chose **reject clearly + migrate** (2026-10-22):

- NthLayer keeps one v1 dialect, `srm/v1`. It does not gain an `opensrm/v1`
  parser.
- `load_manifest` recognises `opensrm/v1` and rejects it with an actionable
  error.
- `nthlayer migrate-manifest` converts `opensrm/v1` to
  `opensrm.nthlayer.io/v2`, following the spec's own map
  (`opensrm/spec/v2/AUTHORING.md` §7).
- Fields with no v2 home are never dropped silently: the conversion refuses
  unless `--allow-lossy` is given, and always lists them (Rob, 2026-10-22).
  Entries come in two kinds: *dropped* (not in the output) and *assumed*
  (converted, but with a value v1 does not declare). Only dropped entries make
  the conversion lossy and trigger the refusal; assumed-only output is written
  with a warning (Rob, 2026-10-22).

Recorded as a decision document (§8).

### Scope

In: the loader rejection; the converter in nthlayer-common; `migrate-manifest`
dispatch and `--allow-lossy` in nthlayer-generate; the decision doc; consumer
floor bumps the common release forces (§7).

Also in: common's v2 parser accepts `resource:` entity refs in
`spec.dependencies[].service` (needed by §4's dependency mapping).

Out (existing or new beads): core surfacing load failures via the API
(opensrm-e3tz); generate's own `srm/v1`-only parser (retired by
opensrm-wo62.1); workers' separate measure manifest loader, a third v1 shape
(file a bead); the `srm/v1` lift's own silent drops (file a bead).

## 3. Architecture

**nthlayer-common** (new module `manifest/opensrm_v1.py`, public):

- `OPENSRM_V1_API_VERSION = "opensrm/v1"`
- `is_opensrm_v1_format(data) -> bool` — `apiVersion == "opensrm/v1"`
  (any kind; the kind is checked by the converter).
- `@dataclass(frozen=True) UnmappedField(path: str, reason: str, kind:
  Literal["dropped", "assumed"])` — `path` is a dotted path into the v1
  document (`spec.deployment`, `spec.dependencies[0].critical`); `reason`
  names the AUTHORING §7 row; `kind` is `"dropped"` (value not in the output)
  or `"assumed"` (converted with a value v1 does not declare).
- `@dataclass(frozen=True) MigrationResult(manifest: dict, unmapped:
  tuple[UnmappedField, ...])` — `unmapped` is in document order (depth-first,
  as the fields appear in the v1 file) and holds both kinds; the `lossy`
  property is true only if something was dropped.
- `convert_opensrm_v1_to_v2(data: dict, *, service_type: str | None = None)
  -> MigrationResult` — pure: never decides what to do about loss, only
  reports it. A document it cannot convert at all (wrong kind, unusable
  value, conflicting fields) raises `OpenSRMV1MigrationError(ValueError)`. `service_type` supplies `spec.service.type` when v1 omits it.

Shared helpers with the `srm/v1` lift (`v1_compat.py`) are allowed only where
the semantics are identical (entity-ref building, service-type resolution,
OpenSLO document construction from an already-ratio target). No function
branches on dialect: the two disagree on units and keys, and one function
holding both is where a unit bug hides.

**Loader:** `_detect_format` gains `OPENSRM_V1`; its branch raises
`ManifestLoadError` (§5) instead of falling through to legacy.

**nthlayer-generate:** `migrate-manifest` dispatches on `apiVersion`
(`srm/v1` → existing `convert_v1_to_v2`, unchanged; `opensrm/v1` → the new
converter) and adds `--allow-lossy`.

## 4. Field mapping

Per AUTHORING §7. *Unmapped* = reported in `MigrationResult.unmapped`, never
raised; *dropped* when the value is absent from the output, *assumed* when it
is converted using a value v1 does not declare. Converter errors (not unmapped
fields) raise `OpenSRMV1MigrationError`.

| v1 (`opensrm/v1`) | v2 (`opensrm.nthlayer.io/v2`) | Note |
|---|---|---|
| `apiVersion` / `kind: ServiceReliabilityManifest` | `opensrm.nthlayer.io/v2` / `ServiceManifest` | rename (§7.1); another kind (e.g. `Template`) is an error |
| `metadata.name`, `labels`, `annotations` | same | copy |
| `metadata.team` | `spec.owner.group: "group:default/<team>"` | §7.2 |
| `metadata.tier` | `metadata.labels.tier` | §7.1 |
| `metadata.description` | `spec.service.description` | §7.1 |
| `metadata.template` | — | unmapped: v2 templates are a different mechanism |
| `spec.type` | `spec.service.type` via `resolve_service_type` | invalid → error. Absent (optional in v1, required in v2) → error unless the caller supplies `service_type`; the CLI's `--service-type` feeds it. A supplied type that disagrees with a declared one → error |
| `spec.slos.availability`, `connection_availability` | `spec.slo[]` OpenSLO document (below) | §7.3 |
| `spec.slos.latency`, `duration`, `query_latency` | OpenSLO document; the percentile keys go into `displayName` | §7.3 |
| `spec.slos.error_rate` (a maximum error ratio, e.g. 0.001) | OpenSLO document with target `1 - x` (0.999) | OpenSLO targets are good-ratios; matches the spec's reference output and how consumers read targets |
| `spec.slos.throughput` | — | unmapped: v1 declares a rate (1000 rps), OpenSLO needs a ratio target |
| `spec.slos.success_rate`, `processing_time`, `lag` | — | unmapped: common's v2 parser cannot infer their type (opensrm-47tt) |
| `spec.slos.schedule_adherence`, `data_freshness`, `replication_lag` | — | unmapped: maximum-only (`max_delay`/`max_age`/`max_lag`), no target |
| `spec.slos.openslo[]` (`{path}`) | `spec.slo[]` item `{"$ref": <path>}` | the path stays relative to the manifest |
| `spec.slos.custom[]` | — | unmapped |
| `spec.slos.judgment.reversal_rate`, `high_confidence_failure` | — | unmapped (Rob, 2026-10-22): AUTHORING §7.7 step 8 calls `judgment_slo` new capability, not migration; and no v2 judgment-SLO shape passes both the schema and common's parser (opensrm-a742) |
| `spec.slos.judgment.calibration` (`target`, `window`) | `spec.judgment_threshold[]`, `type: calibration` | §7.6. Converted and reported as *assumed*: v2 requires `measurement.bins` and v1 has none, so `bins: 10` is defaulted |
| `spec.slos.judgment.feedback_latency` (`p50`, `p90`) | `spec.judgment_threshold[]`, `bounds.maximum_p50` / `maximum_p90` | §7.6 |
| `spec.contract.availability`, `latency.p99`, `throughput.max_rps` | `spec.contracts[0]`: `name: <service>`, `promise.{availability, latency_p99, throughput: "<n>rps"}`, `contract_owner` = owner group | §7.4 |
| `spec.contract.latency.p50` / `p999`, `throughput.burst`, `contract.judgment` | — | unmapped: v2's promise has three fields |
| `spec.dependencies[].service` + `type` | `resource:default/<s>` for database/cache/queue; `component:external/<s>` for external; `component:default/<s>` for service | §7.5 and the reference output. common's v2 parser learns to accept `resource:` refs (Rob, 2026-10-22) |
| `spec.dependencies[].expects.availability` / `latency.p99` | `expected_availability` / `expected_latency_p99` | |
| `spec.dependencies[].critical` | — | unmapped: the author must choose a `fallback` (§7.5) |
| `spec.dependencies[].manifest` | — | unmapped (§7.5) |
| `spec.ownership.team` | `spec.owner.group` (if `metadata.team` absent; disagreement → error) | §7.2 |
| `spec.ownership.escalation` | `spec.owner.escalation` (entity ref) | §7.2 |
| `spec.ownership.slack` / `runbook` / `documentation` | `metadata.annotations`: `slack.com/channel`, `opensrm.nthlayer.io/runbook`, `opensrm.nthlayer.io/documentation` | §7.2 |
| `spec.ownership.pagerduty.service_id` | `metadata.annotations["pagerduty.com/service-id"]` | §7.2 |
| `spec.ownership.email`, `spec.ownership.pagerduty.escalation_policy_id` | — | unmapped (dropped): §7.2 names no annotation key for either, and it is the authority; the reference output `api-full-v2.yaml` also drops email |
| `spec.ownership.oncall_required` | — | unmapped |
| `spec.observability.metrics` | — | unmapped: v2 needs a `type` per metric (§7.7 step 6) |
| `spec.observability.dashboards` / `alerts` / `tracing` | — | unmapped (§7.6) |
| `spec.notifications` | — | unmapped (§7.6) |
| `spec.deployment` | — | unmapped (§7.6) |
| `spec.instrumentation.events` / `attributes` | `spec.instrumentation.required_events` | not in §7's map: the plan verifies the v2 shape; if it cannot represent them, unmapped |

**OpenSLO documents** (verified against common's parser and the v2 schema):
`{apiVersion: openslo/v1, kind: SLO, metadata.name: "<service>-<v1 key, _→->",
spec: {service, timeWindow: [{duration: <v1 window>, isRolling: true}],
objectives: [{displayName, target}]}}`, no indicator. `timeWindow` is always
emitted when v1 has a window: without it the parser silently defaults to 30d,
which would turn a 7d v1 window into 30d. When v1 has no window, the v1 schema's
declared default is used; if it declares none, `timeWindow` is omitted and the
parser's 30d default applies (the plan records which).

**Names:** v1 `metadata.name` allows a leading or trailing `-`; v2 does not.
Such a name → error.

## 5. Errors

**Loader:** `ManifestLoadError` whose message says: this is the published
OpenSRM v1 schema (`opensrm/v1`); NthLayer reads `opensrm.nthlayer.io/v2`
(and `srm/v1`, its own v1 dialect); convert with
`nthlayer migrate-manifest <file>`. Core's catalogue already catches
`ManifestLoadError` and skips the file.

**Converter:** `ValueError` only for a document it cannot convert at all —
wrong apiVersion or kind, missing or v2-invalid `metadata.name`, missing
(and not supplied) or invalid `spec.type`, a ratio field outside [0, 1] on a
field the map converts, a malformed duration, a non-mapping where a mapping is
required. Unmapped fields are never errors and are not value-checked.

**Output validity:** every converted manifest validates against
`opensrm/spec/v2/schema.json` and parses with `parse_opensrm_v2`.

## 6. CLI (`nthlayer migrate-manifest`)

| Input | Unmapped | Flag | Result |
|---|---|---|---|
| `opensrm/v1` | none | — | writes v2, exit 0 |
| `opensrm/v1` | assumed only | — | writes v2, warns "Converted with an assumption", exit 0 |
| `opensrm/v1` | some dropped | — | writes nothing, lists them, exit 1 |
| `opensrm/v1` | some dropped | `--allow-lossy` | writes v2, lists them under "Not migrated", exit 0 |
| `opensrm/v1` without `spec.type` | — | `--service-type <t>` | converts with that type; without the flag, error naming the flag |
| `srm/v1` | — | either | unchanged behaviour (`--allow-lossy` and `--service-type` have no effect) |
| other | — | — | error naming the two supported inputs, exit 1 |

Relative openslo `$ref` paths are copied verbatim, so they stay relative to the
input; the CLI warns when `--output` is in a different directory, where they
would resolve differently.

## 7. Testing and release

**Tests (common):**

- Spec examples as fixtures, read from the `../opensrm` sibling, with a
  presence test (named files + minimum count) so a missing checkout fails
  rather than skips.
- `examples/api-full.yaml` (with `service_type="api"`) converts to a document
  equal to `spec/v2/examples/migration/api-full-v2.yaml` on every field §4
  defines. Excluded, and listed in the test: what the reference author decided
  or invented (`fallback`, `api_ref`, `technical_contact`, the
  `backstage.io/component-ref` annotation, `namespace`, `instrumentation`,
  `displayName` wording), and the throughput SLO, which §4 reports unmapped.
- Every `opensrm/v1` example converts (supplying `service_type` for the two
  without one); output validates against the v2 schema and parses with
  `parse_opensrm_v2`; its `unmapped` list is exactly what §4 predicts for that
  file, derived from the example's keys, not from running the converter.
- **Schema completeness (the test this bead owns):** every property of
  `spec/v1/schema.json`'s `Spec`, `Metadata`, `SLOs`, `JudgmentSLOs`,
  `Contract`, `Dependency`, `Ownership`, `Observability`, `Instrumentation`
  definitions is either converted or reported unmapped by the converter. A v1
  field the converter does not know fails the test.
- Loader: each `opensrm/v1` example raises the new `ManifestLoadError`, not
  `service.name is required`.
- Negative fixtures derived from the v1 schema's constraints (not from the
  converter).

**Tests (generate):** the CLI matrix in §6.

**Release and checkpoints** (shared repo first, each R5-gated):

- A — this spec, the plan, the decision doc (front door).
- B — nthlayer-common 5.3.0 (minor: new public API).
- C — nthlayer-generate `migrate-manifest` (`feat`), floor
  `nthlayer-common>=5.3.0`; and, per the rule-10/11/16 floor guard
  (opensrm-g35i), floor bumps with patch releases in core, bench, workers and
  override-adapter.

## 8. Decision document

`nthlayer/docs/superpowers/decisions/opensrm-v1-support.md`: `srm/v1` is
NthLayer's v1 dialect (load + migrate); `opensrm/v1` is migrate-only; v2 is
the target; why not a second v1 parser (two dialects, units disagree, v2
supersedes); link AUTHORING §7.
