# End-to-end Integration Test for `add_dependency` Emission Design (opensrm-1mja)

**Status:** Design-locked. Author: Rob Fox. Date: 2026-05-30. Bead: `opensrm-1mja`. Parent: `opensrm-dpws` (closed 2026-05-30 — wired `trigger_service` + `declared_dependencies_by_service` into both retrospective paths). Sibling: `opensrm-jmy.21` (added `add_dependency` recommendation type with the `[+]` sigil and apply-layer support, closed 2026-05-29).

**Foundation:**
- `nthlayer/test/learn-recommendations-integration.sh` — existing cross-process integration test for jmy.6. Drives the apply path against a real tmp git repo + stub `gh` via PATH injection. Six sections: seed manifest, build plan, init git, stub gh, run `--apply-to`, reset + run `--apply-to --pr`. Asserts manifest mutation + comment preservation + PR branch creation.
- `nthlayer-workers/src/nthlayer_workers/learn/recommendations.py:485` — jmy.21's `_add_dependency_recommendations` emits `Recommendation(field="spec.dependencies[+]", proposed_value={"name": <svc>, "type": "unknown"})`. Verified: the sigil `[+]` lives inside `field` as a path suffix; there is no separate `operation` field on `Recommendation` (dataclass has `id/service/type/rationale/proposed_value/field/current_value/confidence` only).
- `nthlayer-workers/src/nthlayer_workers/learn/_yaml.py` — apply layer: `LIST_APPEND_SIGIL = "[+]"`; `apply_at_path` dispatches on the sigil; `classify_outcome` returns `APPLY_CLEAN` for novel append, `ALREADY_APPLIED` when the name already exists in the list, `DRIFT_DETECTED` when the name exists with a different `type`.
- `nthlayer-workers/src/nthlayer_workers/learn/cli.py` — `--json` mode (jmy.25) emits a structured doc to stdout with `applied`, `skipped`, `pr_url`, `pr_number`, `pr_error`, `exit_code`. Each `skipped` entry has `{id, service, outcome, detail}` where `outcome` is the OutcomeKind enum's string value (e.g. `"already_applied"`).

---

## 1. Problem statement

`opensrm-jmy.21` shipped the `add_dependency` recommendation type with the `[+]` sigil apply primitive. `opensrm-dpws` wired the upstream `trigger_service` key so the heuristic actually fires. Both bead closures relied on unit + worker tests; no integration coverage exists that drives the full Learn → Spec CLI surface end-to-end for `add_dependency`. The existing `learn-recommendations-integration.sh` exercises only `tighten_slo` (scalar overwrite path). Without an `add_dependency`-specific scenario, the apply-layer's two list-append outcomes (`APPLY_CLEAN`, `ALREADY_APPLIED`) are not validated through the operator-facing CLI command — a regression in the sigil dispatch or the list-dedup logic would not surface until field use.

---

## 2. Existing surface

- `learn-recommendations-integration.sh` structure: trap-on-EXIT cleanup, `$WORK = mktemp -d`, isolated `$SPECS_DIR`, stub gh via PATH, real ruamel.yaml, `GIT_CONFIG_GLOBAL=/dev/null` for git config isolation. ~164 lines, six numbered sections.
- The plan-building Python snippet (section 2) directly imports `SpecRecommendation`, `Recommendation`, `compute_rec_id` from `nthlayer_workers.learn.recommendations` and writes `plan.to_yaml()`. Bypasses `--incident` (which is still a `NotImplementedError` stub).
- The `--apply-to` path is invoked via `python -m nthlayer_workers.learn recommendations --from <plan> --apply-to <specs>`. Exit code, stdout, and resulting filesystem state are all observable to the script.
- jmy.25's `--json` mode produces `{applied: [{id, service, field}], skipped: [{id, service, outcome, detail}], pr_url, pr_number, pr_error, exit_code}` on a single stdout line. The `outcome` field is the OutcomeKind enum's value as a string — canonical lowercase: `apply_clean`, `already_applied`, `drift_detected`.

---

## 3. Locked decisions

### 3.1 Extend the existing script, isolated subdir for the new scenarios

Append two new sections (7 happy-path, 8 idempotency) to `learn-recommendations-integration.sh` after the existing `--pr` section. New scenarios get their own subdir `$WORK/specs-add-dep/` so the git-committed `fraud-detect.yaml` workspace from sections 1–6 stays untouched. Reuses the trap, `$WORK`, uv environment, and PATH stub from the existing setup. Smallest diff; one place to look for the Learn → Spec apply contract.

Rationale: ~50 lines of additive code beats a sibling script that would duplicate ~50 lines of git-init + stub-gh setup. Test isolation is preserved at the subdir level, not the script level.

### 3.2 Two scenarios — APPLY_CLEAN + ALREADY_APPLIED

Skip `DRIFT_DETECTED` coverage; it requires a contrived seed (existing dep with same name but different `type` field) and the dispatch path is uniform across the three outcomes. The two chosen scenarios cover the operationally meaningful semantics: "did the append work" and "is the operation idempotent". `--pr` coverage is skipped because the PR layer is generic over recommendation types and already exercised by tighten_slo in section 6.

### 3.3 Manifest with NO `spec.dependencies` block (most demanding seed)

The seed manifest at `$WORK/specs-add-dep/payments-api.yaml` will omit `spec.dependencies` entirely. The `[+]` sigil must therefore both CREATE the missing block AND append the entry — the maximally demanding APPLY_CLEAN path. Seeding with an empty list or pre-populated list would be a weaker test.

Manifest carries an inline comment explaining its minimality (per refinement 3 below) so future maintenance doesn't "fix it" by adding `tier`/`type`/SLO fields:

```yaml
# Minimal manifest for add_dependency apply testing.
# Lacks tier/type/SLO fields that real manifests would have.
# Intentional: testing apply layer in isolation, not full manifest
# schema validation.
metadata:
  name: payments-api
  team: payments-platform
spec:
  slos:
    availability:
      target: 99.9
      window: 30d
```

The apply layer operates on the YAML doc via ruamel.yaml, not via `load_manifest()` → Manifest dataclass, so the missing `tier`/`type` doesn't fail.

### 3.4 Plan fixture uses hardcoded stable values

`incident_id = "inc-add-dep-test"`, `generated_at = datetime(2026, 5, 30, tzinfo=timezone.utc)`, `rec.id` computed deterministically via `compute_rec_id(incident_id, "add_dependency", "spec.dependencies[+].svc-new")`. No `datetime.now()`, no random IDs. Failure diffs stay readable across runs and CI logs match local logs byte-for-byte.

The plan-building Python snippet:

```python
from datetime import datetime, timezone
from pathlib import Path
from nthlayer_workers.learn.recommendations import (
    SpecRecommendation, Recommendation, compute_rec_id,
)

incident_id = "inc-add-dep-test"
rec = Recommendation(
    id=compute_rec_id(incident_id, "add_dependency", "spec.dependencies[+].svc-new"),
    service="payments-api",
    type="add_dependency",
    rationale="Integration test add_dependency recommendation",
    field="spec.dependencies[+]",  # sigil-in-field, per jmy.21 contract
    current_value=None,
    proposed_value={"name": "svc-new", "type": "api"},
    confidence=0.5,
)
plan = SpecRecommendation(
    incident=incident_id,
    generated_by="integration-test",
    generated_at=datetime(2026, 5, 30, tzinfo=timezone.utc),
    confidence=0.5,
    recommendations=[rec],
)
Path("$PLAN_FILE").write_text(plan.to_yaml())
```

Note: the field path is `spec.dependencies[+]` (sigil at end of dotted path). `proposed_value` is the full dep dict. The apply layer uses `proposed_value["name"]` to dedup-check existing entries — this is the contract jmy.21 R5 locked in.

### 3.5 Section 7 assertions — structural Python parse, not grep

The apply-result assertion uses `--json` + `jq` (structured) for exit_code / applied count / skipped count. The manifest assertion uses a Python YAML parse to verify the dep exists at the right structural location with the right shape — NOT `grep` (which would be vulnerable to comment text matching the pattern).

```bash
# Apply with --json
APPLY1_JSON="$WORK/apply1.json"
PATH="$STUB_GH_DIR:$PATH" GIT_CONFIG_GLOBAL=/dev/null \
  uv run --directory "$WORKERS_ROOT" \
    python -m nthlayer_workers.learn recommendations \
      --from "$PLAN_FILE_ADD_DEP" \
      --apply-to "$WORK/specs-add-dep" \
      --json > "$APPLY1_JSON"

# Structured assertions via jq
[ "$(jq '.exit_code' "$APPLY1_JSON")" = "0" ] || fail "apply1 exit_code != 0"
[ "$(jq '.applied | length' "$APPLY1_JSON")" = "1" ] || fail "apply1 applied != 1"
[ "$(jq '.skipped | length' "$APPLY1_JSON")" = "0" ] || fail "apply1 skipped != 0"

# Structural manifest assertion via Python YAML parse
uv run --directory "$WORKERS_ROOT" python <<EOF
import yaml
from pathlib import Path
doc = yaml.safe_load(Path("$WORK/specs-add-dep/payments-api.yaml").read_text())
deps = doc.get("spec", {}).get("dependencies", [])
matching = [d for d in deps if d.get("name") == "svc-new"]
assert len(matching) == 1, f"expected 1 matching dep, got {len(matching)}: {matching}"
assert matching[0].get("type") == "api", f"expected type=api, got {matching[0]}"
EOF
```

`fail()` is a small helper added at the top of the script: `fail() { echo "FAIL: $*" >&2; exit 1; }`. Matches the failure style of existing sections.

### 3.6 Section 8 assertions — semantic dep-list comparison, not byte diff

Re-run the SAME plan against the now-modified manifest. Assert the apply layer reports skip (not append), AND the parsed dep list is semantically unchanged. Byte-identical comparison is rejected because ruamel.yaml's serialisation choices (whitespace, key ordering, quote style) can drift across runs without changing semantics — that would produce false-positive failures.

```bash
# Snapshot the dep list semantically BEFORE the idempotent re-run
DEPS_BEFORE="$WORK/deps-before.json"
uv run --directory "$WORKERS_ROOT" python <<EOF > "$DEPS_BEFORE"
import json, yaml
from pathlib import Path
doc = yaml.safe_load(Path("$WORK/specs-add-dep/payments-api.yaml").read_text())
print(json.dumps(doc.get("spec", {}).get("dependencies", []), sort_keys=True))
EOF

# Idempotent re-run with same plan
APPLY2_JSON="$WORK/apply2.json"
PATH="$STUB_GH_DIR:$PATH" GIT_CONFIG_GLOBAL=/dev/null \
  uv run --directory "$WORKERS_ROOT" \
    python -m nthlayer_workers.learn recommendations \
      --from "$PLAN_FILE_ADD_DEP" \
      --apply-to "$WORK/specs-add-dep" \
      --json > "$APPLY2_JSON"

# Apply-result assertions: skipped, not applied
[ "$(jq '.exit_code' "$APPLY2_JSON")" = "0" ] || fail "apply2 exit_code != 0"
[ "$(jq '.applied | length' "$APPLY2_JSON")" = "0" ] || fail "apply2 applied != 0"
[ "$(jq '.skipped | length' "$APPLY2_JSON")" = "1" ] || fail "apply2 skipped != 1"
[ "$(jq -r '.skipped[0].outcome' "$APPLY2_JSON")" = "already_applied" ] || \
  fail "apply2 skipped[0].outcome != already_applied"

# Semantic manifest comparison: parsed dep list unchanged
DEPS_AFTER="$WORK/deps-after.json"
uv run --directory "$WORKERS_ROOT" python <<EOF > "$DEPS_AFTER"
import json, yaml
from pathlib import Path
doc = yaml.safe_load(Path("$WORK/specs-add-dep/payments-api.yaml").read_text())
print(json.dumps(doc.get("spec", {}).get("dependencies", []), sort_keys=True))
EOF

diff -u "$DEPS_BEFORE" "$DEPS_AFTER" || fail "dep list changed on idempotent re-run"
```

Why `json.dumps(..., sort_keys=True)`: gives a stable canonical form for diff. The diff is between JSON snapshots of the parsed Python lists, not between the YAML files themselves. A reorder of dict keys in the YAML doesn't show up; an actual semantic change (extra dep, changed type) does.

### 3.7 `jq` is a non-trivial new dependency for this script — verify presence

The existing `learn-recommendations-integration.sh` does not use `jq`. The three-tier test does (per `_three_tier_lib.sh` preflight). Add a preflight check at the top of section 7:

```bash
command -v jq >/dev/null 2>&1 || {
  echo "SKIP: jq required for add_dependency assertions (sections 7-8)"; SUCCESS=1; exit 0;
}
```

`SKIP` exit-0 means CI environments without jq don't fail the build, but local dev sees the skip. (Alternative: fail hard. Reject for now — jq is universally available on macOS + Linux CI runners, but if some constrained CI environment lacks it we don't want to block.)

---

## 4. Out of scope

- Implementing `_build_plan_from_incident` (still `NotImplementedError` stub in `cli.py:327`). Its own bead. Would require `CoreAPIClient.get_retrospective_for_incident`.
- Three-tier integration coverage of add_dependency (would belong in `integration-three-tier.sh`, requires real core + worker stack — different scope, different test infrastructure).
- Demo orchestrator (`demo/demo.sh`) wiring for add_dependency.
- DRIFT_DETECTED scenario (contrived; dispatch path uniform with the other two outcomes; YAGNI).
- `--pr` coverage for add_dependency (PR layer is generic; tighten_slo's section 6 covers it).
- Coverage of `add_deploy_gate` or re-run of `tighten_slo` (scoped specifically to `add_dependency`).
- Replacing or refactoring the existing sections 1–6 (additive only).

---

## 5. Test surface

Two new top-level sections in `learn-recommendations-integration.sh`:

- **Section 7 (APPLY_CLEAN happy path):** seed minimal manifest with no `spec.dependencies`, build plan with one `add_dependency` rec, run `--apply-to --json`, assert `applied==1 / skipped==0 / exit_code==0` via jq, assert structural manifest shape via Python YAML parse.
- **Section 8 (ALREADY_APPLIED idempotency):** snapshot the parsed dep list, re-run the SAME plan, assert `applied==0 / skipped==1 / skipped[0].outcome=="already_applied"` via jq, assert the parsed dep list is semantically unchanged via JSON-canonicalised diff.

No new Python tests. No new pytest files. The integration test runs as a shell script invoked from CI / local dev.

---

## 6. Implementation plan

Single file modified: `nthlayer/test/learn-recommendations-integration.sh`. Two changes:

1. Add a `fail()` helper near the top (if not already there) for consistent failure messaging. Add the `jq` preflight check before section 7.
2. Append sections 7 and 8 with the code shown in §§ 3.5 and 3.6, plus the manifest seed from § 3.3 and the plan-building from § 3.4.

One commit. No R5 supervisor expected to find issues beyond polish — this is a test-script change, not production code.

---

## 7. Effort

- ~70 lines added to `learn-recommendations-integration.sh` (manifest seed + 2 plan-building Python heredocs + 2 apply invocations + 6 jq assertions + 2 Python YAML-parse heredocs + fail/jq preflight).
- Manual test run on local dev to verify the script passes end-to-end.
- R5 supervise (lighter pass — shell + bash, not Python; reviewers will focus on quote escaping, trap correctness, exit-on-failure discipline).
- 0.5 session total.
