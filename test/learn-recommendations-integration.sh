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
echo "All integration assertions passed."
SUCCESS=1
