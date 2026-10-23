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
#   4. Every core start command (demo/demo.sh, test/_three_tier_lib.sh)
#      invokes a console script nthlayer-core DECLARES and a subcommand its
#      CLI defines [opensrm-dww5]. Both run uv against core's own project,
#      so a script name core does not declare fails only at boot, behind
#      docker. Read from ../nthlayer-core when it is checked out, so the
#      expectation traces to core rather than to the scripts under test; CI
#      stubs the sibling as an empty dir, where the names pinned by the
#      dww5 decision (`nthlayer-core serve`) are used instead, announced.
#
# Runs in ~1s. No Docker. Test 4 needs a Python with tomllib (3.11+) only
# when ../nthlayer-core is checked out.

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
echo "=== Test 4: core start commands name a script and subcommand core declares ==="
CORE_DIR="$WORKSPACE_ROOT/nthlayer-core"
if [[ -f "$CORE_DIR/pyproject.toml" ]]; then
    py=""
    for candidate in python3 python3.14 python3.13 python3.12 python3.11; do
        command -v "$candidate" >/dev/null 2>&1 || continue
        if "$candidate" -c 'import tomllib' >/dev/null 2>&1; then py="$candidate"; break; fi
    done
    if [[ -n "$py" ]]; then
        run_py() { "$py" - "$@"; }
    elif command -v uv >/dev/null 2>&1; then
        run_py() { uv run --quiet --no-project --python 3.12 python - "$@"; }
    else
        run_py() { return 1; }
    fi
    # One name per line. A failure here is a FAIL, not a skip: an unreadable
    # core is the case this check exists to surface.
    core_scripts="$(run_py "$CORE_DIR/pyproject.toml" <<'PY' || true
import sys, tomllib
with open(sys.argv[1], "rb") as f:
    scripts = tomllib.load(f).get("project", {}).get("scripts", {})
print("\n".join(scripts))
PY
)"
    core_subcommands="$(run_py "$CORE_DIR/src/nthlayer_core/cli.py" <<'PY' || true
import ast, sys
tree = ast.parse(open(sys.argv[1]).read())
for node in ast.walk(tree):
    if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
            and node.func.attr == "add_parser" and node.args
            and isinstance(node.args[0], ast.Constant)):
        print(node.args[0].value)
PY
)"
    source_desc="declared by $CORE_DIR"
else
    echo "  NOTE: $CORE_DIR/pyproject.toml absent (CI placeholder) — checking"
    echo "        against the dww5-pinned names 'nthlayer-core' / 'serve'"
    core_scripts="nthlayer-core"
    core_subcommands="serve"
    source_desc="pinned by opensrm-dww5"
fi

if [[ -n "$core_scripts" && -n "$core_subcommands" ]]; then
    pass "core scripts [$(tr '\n' ' ' <<<"$core_scripts" | sed 's/ $//')] and subcommands [$(tr '\n' ' ' <<<"$core_subcommands" | sed 's/ $//')] read ($source_desc)"
else
    fail "could not read core's scripts/subcommands from $CORE_DIR"
fi

for f in demo/demo.sh test/_three_tier_lib.sh; do
    # The start line is `<runner> <script> <subcommand> ...` where the runner
    # is the uv-against-core prefix: $RUN_CORE in demo.sh, ${run_core} in the lib.
    invocations="$(grep -E '^[[:space:]]*(\$RUN_CORE|\$\{run_core\})[[:space:]]+' "$FRONTDOOR/$f" \
        | awk '{print $2, $3}' || true)"
    if [[ -z "$invocations" ]]; then
        fail "$f: no core start command found — the extraction no longer matches"
        continue
    fi
    while read -r script subcommand; do
        if grep -qxF -- "$script" <<<"$core_scripts" && grep -qxF -- "$subcommand" <<<"$core_subcommands"; then
            pass "$f starts core with '$script $subcommand' ($source_desc)"
        else
            fail "$f starts core with '$script $subcommand', not a script+subcommand $source_desc"
        fi
    done <<<"$invocations"
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
