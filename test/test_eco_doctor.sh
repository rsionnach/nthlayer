#!/usr/bin/env bash
# test_eco_doctor.sh — regression test for scripts/eco-doctor.sh.
#
# Filed as opensrm-8hn3 after opensrm-p3bm and opensrm-z7gn. Five member repos
# had shipped, or were about to ship, a declared nthlayer-common range that no
# test had exercised, and every one of them also carried a committed uv.lock
# recording a stale sibling version. Nothing in the workspace compared the two.
#
# The detector exists because `tool.uv.sources` points siblings at local
# checkouts, and a path source REPLACES registry resolution rather than being
# filtered by the version specifier — so `uv sync` and `uv pip install .`
# install whatever the sibling happens to be, regardless of what is declared,
# and neither warns.
#
# EVERY ASSERTION HERE RUNS AGAINST SYNTHETIC FIXTURE REPOS built in a temp
# dir, never against the live ecosystem. Asserting against the real workspace
# would pass or fail by accident: it is clean today, so a broken detector would
# look correct, and it would break the moment someone bumps a sibling. That is
# the same fixture-provenance trap opensrm-oh27 shipped — a predicate matched
# only by a shape no real input has.
#
# What this test checks:
#   1. bash -n on eco-doctor.sh — syntax regression catcher (cheap).
#   2. A clean workspace exits 0 and reports no findings.
#   3. A lock recording an older sibling version than the sibling's own
#      pyproject is reported STALE, exit non-zero.
#   4. A lock recording a version BELOW the consumer's declared floor is
#      reported LOCK<FLOOR — the nthlayer-workers case in p3bm.
#   5. A sibling whose version EXCEEDS the consumer's declared ceiling is
#      reported SIBLING>CEILING — the core/bench/override-adapter case.
#   6. A declared range with no upper bound is reported NO-CEILING — the
#      nthlayer-generate case in z7gn, which made it the resolver's escape
#      hatch once the others were bounded.
#   7. The COMMITTED lock is read, not the working tree. A dirty working-tree
#      lock that would pass must still be reported if HEAD's is stale. This is
#      the detail three hand-rolled versions of this scan got wrong.
#   8. Findings are one line each and name the repo.
#
# Runs in a few seconds. No Docker, no network, no Python deps.

set -euo pipefail

TEST_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
FRONTDOOR="$(cd "$TEST_DIR/.." && pwd)"
DOCTOR="$FRONTDOOR/scripts/eco-doctor.sh"

pass_count=0
fail_count=0

pass() { echo "  PASS: $*"; pass_count=$((pass_count + 1)); }
fail() { echo "  FAIL: $*" >&2; fail_count=$((fail_count + 1)); }

WORK=""
cleanup() { [[ -n "$WORK" && -d "$WORK" ]] && rm -rf "$WORK"; }
trap cleanup EXIT

# --- fixture builders -------------------------------------------------------
#
# Fixtures are real git repos with real committed files, because the detector
# reads `git show HEAD:uv.lock`. A fake directory tree would not exercise that
# path at all, and the whole point of check 7 is that HEAD is what counts.

# make_sibling <dir> <name> <version>
make_sibling() {
    local dir="$1" name="$2" version="$3"
    mkdir -p "$dir"
    printf '[project]\nname = "%s"\nversion = "%s"\n' "$name" "$version" \
        > "$dir/pyproject.toml"
    git -C "$dir" init -q
    git -C "$dir" add -A
    git -C "$dir" -c user.email=t@t -c user.name=t commit -qm init
}

# make_consumer <dir> <name> <declared-range> <locked-sibling-version>
make_consumer() {
    local dir="$1" name="$2" range="$3" locked="$4"
    mkdir -p "$dir"
    printf '[project]\nname = "%s"\nversion = "1.0.0"\ndependencies = [\n    "nthlayer-common%s",\n]\n\n[tool.uv.sources]\nnthlayer-common = { path = "../nthlayer-common", editable = true }\n' \
        "$name" "$range" > "$dir/pyproject.toml"
    printf 'version = 1\n\n[[package]]\nname = "nthlayer-common"\nversion = "%s"\nsource = { editable = "../nthlayer-common" }\n' \
        "$locked" > "$dir/uv.lock"
    git -C "$dir" init -q
    git -C "$dir" add -A
    git -C "$dir" -c user.email=t@t -c user.name=t commit -qm init
}

run_doctor() {
    # Prints output, returns the exit code without tripping set -e.
    local rc=0
    bash "$DOCTOR" "$@" 2>&1 || rc=$?
    return $rc
}

# FINDINGS_RC is the documented exit code for "drift found". Assertions check
# for exactly this, never merely non-zero: 127 (missing), 2 (usage) and 1 must
# stay distinguishable, or a broken invocation reads as a successful detection.
FINDINGS_RC=1

# --- Precondition ----------------------------------------------------------
#
# Without this, every "exits non-zero" assertion below is satisfied by a
# MISSING script exiting 127, and the suite reports passes for a tool that does
# not exist. Caught while this test was still red — the same false-pass shape
# opensrm-oh27 shipped.

if [[ ! -f "$DOCTOR" ]]; then
    echo "FATAL: $DOCTOR does not exist. Every assertion below would be" >&2
    echo "satisfied by exit 127 and report a false pass." >&2
    exit 2
fi

# --- Test 1: syntax --------------------------------------------------------

echo "=== Test 1: bash -n syntax check on eco-doctor.sh ==="
if bash -n "$DOCTOR" 2>/dev/null; then
    pass "eco-doctor.sh parses cleanly"
else
    fail "eco-doctor.sh has a shell syntax error"
fi

# --- Test 2: clean workspace ------------------------------------------------

echo
echo "=== Test 2: a clean workspace exits 0 ==="
WORK="$(mktemp -d)"
CLEAN="$WORK/clean"
mkdir -p "$CLEAN"
make_sibling "$CLEAN/nthlayer-common" nthlayer-common 2.1.2
make_consumer "$CLEAN/nthlayer-core" nthlayer-core ">=2.1.2,<3.0.0" 2.1.2

rc=0
out="$(cd "$CLEAN" && run_doctor)" || rc=$?
if (( rc == 0 )); then
    pass "clean workspace exits 0"
else
    fail "clean workspace exited $rc — output: $out"
fi
if ! grep -qE "STALE|FLOOR|CEILING" <<<"$out"; then
    pass "clean workspace reports no findings"
else
    fail "clean workspace reported a finding: $out"
fi

# --- Test 3: stale lock -----------------------------------------------------

echo
echo "=== Test 3: lock older than the sibling is STALE ==="
STALE="$WORK/stale"
mkdir -p "$STALE"
make_sibling "$STALE/nthlayer-common" nthlayer-common 2.1.2
make_consumer "$STALE/nthlayer-core" nthlayer-core ">=2.0.0,<3.0.0" 2.0.0

rc=0
out="$(cd "$STALE" && run_doctor)" || rc=$?
if (( rc == FINDINGS_RC )); then
    pass "stale lock exits non-zero"
else
    fail "stale lock exited $rc, want $FINDINGS_RC — output: $out"
fi
if grep -q "STALE" <<<"$out"; then
    pass "stale lock reports STALE"
else
    fail "stale lock did not report STALE — output: $out"
fi
if grep -q "nthlayer-core" <<<"$out"; then
    pass "finding names the repo"
else
    fail "finding does not name the repo — output: $out"
fi

# --- Test 4: lock below the declared floor ---------------------------------

echo
echo "=== Test 4: lock below the declared floor is LOCK<FLOOR ==="
FLOORCASE="$WORK/floor"
mkdir -p "$FLOORCASE"
make_sibling "$FLOORCASE/nthlayer-common" nthlayer-common 2.1.2
# The nthlayer-workers case: floor raised to 2.1.2, lock still recording 1.6.0.
make_consumer "$FLOORCASE/nthlayer-workers" nthlayer-workers ">=2.1.2,<3.0.0" 1.6.0

rc=0
out="$(cd "$FLOORCASE" && run_doctor)" || rc=$?
if (( rc == FINDINGS_RC )); then
    pass "lock-below-floor exits non-zero"
else
    fail "lock-below-floor exited $rc, want $FINDINGS_RC — output: $out"
fi
if grep -q "LOCK<FLOOR" <<<"$out"; then
    pass "reports LOCK<FLOOR"
else
    fail "did not report LOCK<FLOOR — output: $out"
fi

# --- Test 5: sibling above the declared ceiling ----------------------------

echo
echo "=== Test 5: sibling above the declared ceiling is SIBLING>CEILING ==="
CEIL="$WORK/ceiling"
mkdir -p "$CEIL"
make_sibling "$CEIL/nthlayer-common" nthlayer-common 2.1.2
# The core/bench/override-adapter case: <2.0.0 declared while 2.1.2 is built
# and tested against, which uv sync installs regardless.
make_consumer "$CEIL/nthlayer-bench" nthlayer-bench ">=1.5.0,<2.0.0" 1.7.0

rc=0
out="$(cd "$CEIL" && run_doctor)" || rc=$?
if (( rc == FINDINGS_RC )); then
    pass "sibling-above-ceiling exits non-zero"
else
    fail "sibling-above-ceiling exited $rc, want $FINDINGS_RC — output: $out"
fi
if grep -q "SIBLING>CEILING" <<<"$out"; then
    pass "reports SIBLING>CEILING"
else
    fail "did not report SIBLING>CEILING — output: $out"
fi

# --- Test 6: no upper bound ------------------------------------------------

echo
echo "=== Test 6: a range with no upper bound is NO-CEILING ==="
NOCEIL="$WORK/noceiling"
mkdir -p "$NOCEIL"
make_sibling "$NOCEIL/nthlayer-common" nthlayer-common 2.1.2
# The nthlayer-generate case: >=2.0.0 with no ceiling made it the resolver's
# escape hatch once every other member was bounded.
make_consumer "$NOCEIL/nthlayer-generate" nthlayer-generate ">=2.1.2" 2.1.2

rc=0
out="$(cd "$NOCEIL" && run_doctor)" || rc=$?
if (( rc == FINDINGS_RC )); then
    pass "no-ceiling exits non-zero"
else
    fail "no-ceiling exited $rc, want $FINDINGS_RC — output: $out"
fi
if grep -q "NO-CEILING" <<<"$out"; then
    pass "reports NO-CEILING"
else
    fail "did not report NO-CEILING — output: $out"
fi

# --- Test 7: reads the COMMITTED lock, not the working tree ----------------

echo
echo "=== Test 7: the COMMITTED lock is authoritative, not the working tree ==="
# This is the check that matters most. Three hand-rolled versions of this scan
# read the working tree and reported 'ok' for a repo whose committed lock was
# stale — because an uncommitted relock was sitting in the tree. CI resolves
# HEAD, so HEAD is what the detector must read.
HEADCASE="$WORK/headcase"
mkdir -p "$HEADCASE"
make_sibling "$HEADCASE/nthlayer-common" nthlayer-common 2.1.2
make_consumer "$HEADCASE/nthlayer-core" nthlayer-core ">=2.0.0,<3.0.0" 2.0.0
# Now dirty the working tree with a relock that WOULD pass. HEAD stays stale.
printf 'version = 1\n\n[[package]]\nname = "nthlayer-common"\nversion = "2.1.2"\nsource = { editable = "../nthlayer-common" }\n' \
    > "$HEADCASE/nthlayer-core/uv.lock"

rc=0
out="$(cd "$HEADCASE" && run_doctor)" || rc=$?
if (( rc == FINDINGS_RC )); then
    pass "dirty-tree-passing but HEAD-stale still exits non-zero"
else
    fail "exited $rc, want $FINDINGS_RC — read the working tree instead of HEAD?"
fi
if grep -q "STALE" <<<"$out"; then
    pass "reports STALE from HEAD despite a clean-looking working tree"
else
    fail "did not report STALE from HEAD — output: $out"
fi

# --- Test 8: one line per finding ------------------------------------------

echo
echo "=== Test 8: findings are one line each ==="
MULTI="$WORK/multi"
mkdir -p "$MULTI"
make_sibling "$MULTI/nthlayer-common" nthlayer-common 2.1.2
make_consumer "$MULTI/nthlayer-core" nthlayer-core ">=1.5.0,<2.0.0" 1.7.0
make_consumer "$MULTI/nthlayer-bench" nthlayer-bench ">=2.0.0" 2.0.0

rc=0
out="$(cd "$MULTI" && run_doctor)" || rc=$?
finding_lines="$(grep -cE "STALE|LOCK<FLOOR|SIBLING>CEILING|NO-CEILING" <<<"$out" || true)"
if (( finding_lines >= 2 )); then
    pass "both repos reported ($finding_lines finding lines)"
else
    fail "expected findings for two repos, got $finding_lines — output: $out"
fi

echo
echo "==============================================="
echo "  Passed: $pass_count"
echo "  Failed: $fail_count"
echo "==============================================="

if (( fail_count > 0 )); then
    exit 1
fi
exit 0
