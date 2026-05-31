#!/usr/bin/env bash
# test_demo_paths.sh — regression test for demo/demo.sh path resolution.
#
# Surfaced by opensrm-oey5. The path-resolution fix in nthlayer@ae21c26
# split the conflated ECOSYSTEM_DIR into FRONTDOOR_ROOT (this repo) and
# WORKSPACE_ROOT (parent dir for sibling component repos). Nothing in CI
# asserted the new layout held; a future refactor could silently regress
# it back to the conflated form.
#
# What this test checks:
#   1. bash -n on demo.sh — syntax regression catcher (cheap).
#   2. Sourcing demo/_paths.sh resolves FRONTDOOR_ROOT to this repo and
#      WORKSPACE_ROOT to the parent dir.
#   3. WORKSPACE_ROOT contains the four sibling component dirs that
#      cmd_start_preflight requires (nthlayer-core/-workers/-bench/-common).
#      In CI these can be empty placeholders — the test asserts shape,
#      not contents.
#
# Runs in <1s. No Docker, no Python deps.

set -euo pipefail

TEST_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
FRONTDOOR="$(cd "$TEST_DIR/.." && pwd)"

pass_count=0
fail_count=0

pass() { echo "  PASS: $*"; pass_count=$((pass_count + 1)); }
fail() { echo "  FAIL: $*" >&2; fail_count=$((fail_count + 1)); }

assert_eq() {
    local actual="$1" expected="$2" desc="$3"
    if [[ "$actual" == "$expected" ]]; then
        pass "$desc"
    else
        fail "$desc — expected '$expected', got '$actual'"
    fi
}

assert_dir_exists() {
    local path="$1" desc="$2"
    if [[ -d "$path" ]]; then
        pass "$desc"
    else
        fail "$desc — directory missing: $path"
    fi
}

echo "=== Test 1: bash -n syntax check on demo/demo.sh ==="
if bash -n "$FRONTDOOR/demo/demo.sh"; then
    pass "demo.sh parses cleanly"
else
    fail "demo.sh has a shell syntax error"
fi

echo
echo "=== Test 2: source _paths.sh and assert FRONTDOOR_ROOT / WORKSPACE_ROOT ==="
# Source in a subshell so we don't pollute this script's env.
paths_output="$(
    source "$FRONTDOOR/demo/_paths.sh"
    echo "DEMO_DIR=$DEMO_DIR"
    echo "FRONTDOOR_ROOT=$FRONTDOOR_ROOT"
    echo "WORKSPACE_ROOT=$WORKSPACE_ROOT"
)"
eval "$paths_output"

assert_eq "$DEMO_DIR" "$FRONTDOOR/demo" "DEMO_DIR resolves to <repo>/demo"
assert_eq "$FRONTDOOR_ROOT" "$FRONTDOOR" "FRONTDOOR_ROOT resolves to repo root"
assert_eq "$WORKSPACE_ROOT" "$(cd "$FRONTDOOR/.." && pwd)" "WORKSPACE_ROOT resolves to parent dir"

echo
echo "=== Test 3: WORKSPACE_ROOT contains sibling component dirs ==="
for sibling in nthlayer-core nthlayer-workers nthlayer-bench nthlayer-common; do
    assert_dir_exists "$WORKSPACE_ROOT/$sibling" "$sibling exists under WORKSPACE_ROOT"
done

echo
echo "==============================================="
echo "  Passed: $pass_count"
echo "  Failed: $fail_count"
echo "==============================================="

if (( fail_count > 0 )); then
    exit 1
fi
exit 0
