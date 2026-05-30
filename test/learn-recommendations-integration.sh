#!/usr/bin/env bash
# Cross-process integration test for opensrm-jmy.6.
#
# Drives the audited two-step Learn → Spec workflow end-to-end against
# a real tmp git repo, real ruamel.yaml, and a stubbed gh CLI (via
# PATH injection) so no real GitHub credentials or network are needed.
#
# Isolation guarantees (per jmy.6 § 8):
#   - All filesystem operations confined to $WORK
#   - gh stubbed via PATH injection
#   - git uses local config only (GIT_CONFIG_GLOBAL=/dev/null)
#   - No network access required
#   - Cleanup via trap

set -euo pipefail

fail() {
  echo "FAIL: $*" >&2
  exit 1
}

# Resolve repo roots
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
FRONTDOOR_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
WORKSPACE_ROOT="$(cd "$FRONTDOOR_ROOT/.." && pwd)"
WORKERS_ROOT="$WORKSPACE_ROOT/nthlayer-workers"

# tmp workspace
WORK="$(mktemp -d -t jmy6-integration-XXXXXX)"
SPECS_DIR="$WORK/specs"
STUB_GH_DIR="$WORK/stub-gh"
ORIGIN_BARE="$WORK/origin.git"
mkdir -p "$SPECS_DIR" "$STUB_GH_DIR"

# Cleanup trap (only on success; preserve on failure for debug)
SUCCESS=0
cleanup() {
  if [ "$SUCCESS" = "1" ]; then
    rm -rf "$WORK"
  else
    echo "Integration test failed. Logs preserved in $WORK"
  fi
}
trap cleanup EXIT

# 1. Seed manifest in specs dir
cat > "$SPECS_DIR/fraud-detect.yaml" <<'EOF'
metadata:
  name: fraud-detect
  team: payments-ml
spec:
  slos:
    judgment:
      target: 95.0  # current SLO target — operator comment
      window: 30d
EOF

# 2. Build a plan file (via Python; bypasses --incident path which requires core)
PLAN_FILE="$WORK/plan.yaml"
uv run --directory "$WORKERS_ROOT" python <<EOF
from datetime import datetime, timezone
from pathlib import Path
from nthlayer_workers.learn.recommendations import (
    SpecRecommendation, Recommendation, compute_rec_id,
)

incident_id = "inc-integration-test"
rec = Recommendation(
    id=compute_rec_id(incident_id, "tighten_slo", "spec.slos.judgment.target"),
    service="fraud-detect",
    type="tighten_slo",
    rationale="Integration test recommendation",
    field="spec.slos.judgment.target",
    current_value=95.0,
    proposed_value=98.5,
)
plan = SpecRecommendation(
    incident=incident_id,
    generated_by="integration-test",
    generated_at=datetime(2026, 5, 26, tzinfo=timezone.utc),
    confidence=0.8,
    recommendations=[rec],
)
Path("$PLAN_FILE").write_text(plan.to_yaml())
EOF
echo "✓ plan.yaml generated"

# 3. Init the specs dir as a git repo
#    Use a local bare repo as origin so 'git push' succeeds without network
GIT_CONFIG_GLOBAL=/dev/null git -C "$SPECS_DIR" init -q
GIT_CONFIG_GLOBAL=/dev/null git -C "$SPECS_DIR" config user.email "integration-test@nthlayer.io"
GIT_CONFIG_GLOBAL=/dev/null git -C "$SPECS_DIR" config user.name "Integration Test"
GIT_CONFIG_GLOBAL=/dev/null git -C "$SPECS_DIR" add fraud-detect.yaml
GIT_CONFIG_GLOBAL=/dev/null git -C "$SPECS_DIR" commit -q -m "initial commit"

# Create a local bare repo and add it as origin so 'git push' and
# 'git ls-remote' succeed without any network access.
GIT_CONFIG_GLOBAL=/dev/null git init --bare -q "$ORIGIN_BARE"
GIT_CONFIG_GLOBAL=/dev/null git -C "$SPECS_DIR" remote add origin "$ORIGIN_BARE"
# Push main branch to origin so ls-remote finds it (branch check needs it)
GIT_CONFIG_GLOBAL=/dev/null git -C "$SPECS_DIR" push -q origin main 2>/dev/null || \
  GIT_CONFIG_GLOBAL=/dev/null git -C "$SPECS_DIR" push -q origin HEAD:main

# 4. Build stub gh
cat > "$STUB_GH_DIR/gh" <<'STUBEOF'
#!/usr/bin/env bash
# Stub gh — records argv and emits a fake PR URL on `pr create`.
case "$1" in
  --version)
    echo "gh version 2.99.0 (stub)"
    exit 0 ;;
  auth)
    [ "$2" = "status" ] && exit 0 ;;
  pr)
    [ "$2" = "create" ] && echo "https://github.com/org/repo/pull/42"
    exit 0 ;;
esac
exit 0
STUBEOF
chmod +x "$STUB_GH_DIR/gh"

# 5. Run --apply-to (no --pr first; verify writes + comment preservation)
PATH="$STUB_GH_DIR:$PATH" GIT_CONFIG_GLOBAL=/dev/null \
  uv run --directory "$WORKERS_ROOT" \
    python -m nthlayer_workers.learn recommendations \
      --from "$PLAN_FILE" \
      --apply-to "$SPECS_DIR"

# Assert manifest modified
grep -q "target: 98.5" "$SPECS_DIR/fraud-detect.yaml" || {
  echo "FAIL: target not updated"; exit 1;
}
# Assert original comment preserved (the core ruamel.yaml promise)
grep -q "current SLO target" "$SPECS_DIR/fraud-detect.yaml" || {
  echo "FAIL: operator comment lost on round-trip"; exit 1;
}
echo "✓ --apply-to wrote manifest, comment preserved"

# 6. Reset for the --pr path
GIT_CONFIG_GLOBAL=/dev/null git -C "$SPECS_DIR" checkout fraud-detect.yaml
PATH="$STUB_GH_DIR:$PATH" GIT_CONFIG_GLOBAL=/dev/null \
  uv run --directory "$WORKERS_ROOT" \
    python -m nthlayer_workers.learn recommendations \
      --from "$PLAN_FILE" \
      --apply-to "$SPECS_DIR" \
      --pr | tee "$WORK/cli-output.log"

# Assert PR URL printed
grep -q "PR created: https://github.com/org/repo/pull/42" "$WORK/cli-output.log" || {
  echo "FAIL: PR URL not in stdout"; exit 1;
}

# Assert branch exists
GIT_CONFIG_GLOBAL=/dev/null git -C "$SPECS_DIR" rev-parse --verify \
  "learn/recommendations/inc-integration-test" >/dev/null 2>&1 || {
  echo "FAIL: PR branch not created"; exit 1;
}

# Assert single commit on the branch
COMMIT_COUNT=$(GIT_CONFIG_GLOBAL=/dev/null git -C "$SPECS_DIR" \
  log "learn/recommendations/inc-integration-test" --not main --oneline | wc -l | tr -d '[:space:]')
[ "$COMMIT_COUNT" = "1" ] || {
  echo "FAIL: expected 1 commit on PR branch, got $COMMIT_COUNT"; exit 1;
}

echo "✓ --pr path: branch + commit + stub gh pr create OK"
echo ""
echo "All tighten_slo + --pr assertions passed."

# ─────────────────────────────────────────────────────────────────────────
# Sections 7-8: add_dependency apply path (opensrm-1mja)
# Verifies the [+] sigil and ALREADY_APPLIED dedup end-to-end via
# --apply-to + --json, using structured jq assertions and a Python
# YAML parse for manifest shape.
# ─────────────────────────────────────────────────────────────────────────

# Preflight: jq is required for --json apply-result assertions.
# Skip-not-fail so constrained CI environments don't block on jq absence.
# Message goes to stderr so the skip is visible to operators tailing
# CI logs (a stdout-only message would let a regression in the CI
# image hide that sections 7-8 stopped running while suite reported pass).
command -v jq >/dev/null 2>&1 || {
  echo "SKIP: jq required for add_dependency assertions (sections 7-8)" >&2
  SUCCESS=1
  exit 0
}

# 7. add_dependency — APPLY_CLEAN happy path
ADD_DEP_SPECS="$WORK/specs-add-dep"
mkdir -p "$ADD_DEP_SPECS"

# Minimal seed manifest with NO spec.dependencies block.
# The [+] sigil must CREATE the block AND append the entry — the
# maximally demanding APPLY_CLEAN path.
cat > "$ADD_DEP_SPECS/payments-api.yaml" <<'EOF'
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
EOF

# Build plan with one add_dependency recommendation.
# All values hardcoded for deterministic test runs.
PLAN_FILE_ADD_DEP="$WORK/plan-add-dep.yaml"
uv run --directory "$WORKERS_ROOT" python <<EOF
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
    field="spec.dependencies[+]",
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
Path("$PLAN_FILE_ADD_DEP").write_text(plan.to_yaml())
EOF
echo "✓ plan-add-dep.yaml generated"

# Apply with --json (structured stdout for jq).
APPLY1_JSON="$WORK/apply1.json"
PATH="$STUB_GH_DIR:$PATH" GIT_CONFIG_GLOBAL=/dev/null \
  uv run --directory "$WORKERS_ROOT" \
    python -m nthlayer_workers.learn recommendations \
      --from "$PLAN_FILE_ADD_DEP" \
      --apply-to "$ADD_DEP_SPECS" \
      --json > "$APPLY1_JSON"

# Apply-result assertions via jq.
[ "$(jq '.exit_code' "$APPLY1_JSON")" = "0" ] || fail "apply1 exit_code != 0"
[ "$(jq '.applied | length' "$APPLY1_JSON")" = "1" ] || fail "apply1 applied != 1"
[ "$(jq '.skipped | length' "$APPLY1_JSON")" = "0" ] || fail "apply1 skipped != 0"

# Structural manifest assertion via Python YAML parse.
# Verifies the dep exists at spec.dependencies[].{name, type} — not a
# string-pattern match (which would false-positive on comment text).
uv run --directory "$WORKERS_ROOT" python <<EOF
import yaml
from pathlib import Path
doc = yaml.safe_load(Path("$ADD_DEP_SPECS/payments-api.yaml").read_text())
deps = doc.get("spec", {}).get("dependencies", [])
matching = [d for d in deps if d.get("name") == "svc-new"]
assert len(matching) == 1, f"expected 1 matching dep, got {len(matching)}: {matching}"
assert matching[0].get("type") == "api", f"expected type=api, got {matching[0]}"
EOF
echo "✓ Section 7: add_dependency APPLY_CLEAN path"

# 8. add_dependency — ALREADY_APPLIED idempotency
# Re-run the SAME plan against the now-modified manifest. The apply
# layer must report skip (not append), and the parsed dep list must
# be semantically unchanged. Byte-identical comparison would be brittle
# to ruamel.yaml's serialisation choices; we compare the parsed Python
# list canonicalised through json.dumps(sort_keys=True) instead.

# Snapshot the dep list semantically BEFORE the idempotent re-run.
DEPS_BEFORE="$WORK/deps-before.json"
uv run --directory "$WORKERS_ROOT" python <<EOF > "$DEPS_BEFORE"
import json, yaml
from pathlib import Path
doc = yaml.safe_load(Path("$ADD_DEP_SPECS/payments-api.yaml").read_text())
print(json.dumps(doc.get("spec", {}).get("dependencies", []), sort_keys=True))
EOF

# Re-run the SAME plan against the now-modified specs dir.
APPLY2_JSON="$WORK/apply2.json"
PATH="$STUB_GH_DIR:$PATH" GIT_CONFIG_GLOBAL=/dev/null \
  uv run --directory "$WORKERS_ROOT" \
    python -m nthlayer_workers.learn recommendations \
      --from "$PLAN_FILE_ADD_DEP" \
      --apply-to "$ADD_DEP_SPECS" \
      --json > "$APPLY2_JSON"

# Apply-result assertions: 0 applied, 1 skipped, outcome=already_applied.
[ "$(jq '.exit_code' "$APPLY2_JSON")" = "0" ] || fail "apply2 exit_code != 0"
[ "$(jq '.applied | length' "$APPLY2_JSON")" = "0" ] || fail "apply2 applied != 0"
[ "$(jq '.skipped | length' "$APPLY2_JSON")" = "1" ] || fail "apply2 skipped != 1"
[ "$(jq -r '.skipped[0].outcome' "$APPLY2_JSON")" = "already_applied" ] || \
  fail "apply2 skipped[0].outcome != already_applied"

# Semantic manifest comparison: parsed dep list unchanged.
DEPS_AFTER="$WORK/deps-after.json"
uv run --directory "$WORKERS_ROOT" python <<EOF > "$DEPS_AFTER"
import json, yaml
from pathlib import Path
doc = yaml.safe_load(Path("$ADD_DEP_SPECS/payments-api.yaml").read_text())
print(json.dumps(doc.get("spec", {}).get("dependencies", []), sort_keys=True))
EOF

diff -u "$DEPS_BEFORE" "$DEPS_AFTER" || fail "dep list changed on idempotent re-run"
echo "✓ Section 8: add_dependency ALREADY_APPLIED idempotency"

echo ""
echo "All integration assertions passed."
SUCCESS=1
