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

# --- Test 9: a worktree must not shadow the real sibling -------------------

echo
echo "=== Test 9: a sibling worktree does not hide findings ==="
# THE REGRESSION TEST FOR THIS TOOL'S OWN CRITICAL BUG. The first version built
# one flat name->version map across every discovered directory. CLAUDE.md
# mandates worktrees named <repo>-<slug>, which sort AFTER <repo>, so the
# worktree overwrote the real checkout and both genuine findings vanished with
# exit 0. This workspace almost always has a worktree on disk, so the detector
# was defeated in precisely its normal operating conditions.
SHADOW="$WORK/shadow"
mkdir -p "$SHADOW"
make_sibling "$SHADOW/nthlayer-common" nthlayer-common 3.5.0
# A worktree-shaped duplicate declaring the same package name at a version that
# would look fine. Sorts after the real one.
make_sibling "$SHADOW/nthlayer-common-wip" nthlayer-common 2.1.2
make_consumer "$SHADOW/nthlayer-core" nthlayer-core ">=2.1.2,<3.0.0" 2.1.2

rc=0
out="$(cd "$SHADOW" && run_doctor)" || rc=$?
if (( rc == FINDINGS_RC )); then
    pass "worktree present, findings still reported"
else
    fail "worktree hid the findings — exited $rc. Output: $out"
fi
if grep -q "SIBLING>CEILING" <<<"$out"; then
    pass "real sibling 3.5.0 still caught against <3.0.0"
else
    fail "did not catch the real sibling — the worktree shadowed it: $out"
fi
if grep -q "DUPLICATE-NAME" <<<"$out"; then
    pass "duplicate package name reported"
else
    fail "two dirs declare nthlayer-common and nothing said so: $out"
fi

# --- Test 10: sibling version comes from the WORKING TREE ------------------

echo
echo "=== Test 10: the sibling's version is read from its working tree ==="
# Half of the asymmetry this tool depends on. Both this and test 11 SURVIVED
# the reviewer's mutation of the source-selection logic, because test 7 only
# ever dirtied uv.lock — the lock half was pinned and the pyproject half was
# not.
WTREE="$WORK/worktree-version"
mkdir -p "$WTREE"
make_sibling "$WTREE/nthlayer-common" nthlayer-common 2.1.2
make_consumer "$WTREE/nthlayer-core" nthlayer-core ">=2.1.2,<3.0.0" 2.1.2
# Bump the sibling in the working tree only; HEAD still says 2.1.2.
printf '[project]\nname = "nthlayer-common"\nversion = "3.5.0"\n' \
    > "$WTREE/nthlayer-common/pyproject.toml"

rc=0
out="$(cd "$WTREE" && run_doctor)" || rc=$?
if grep -q "SIBLING>CEILING" <<<"$out"; then
    pass "working-tree bump to 3.5.0 caught against <3.0.0"
else
    fail "read the sibling from HEAD instead of the working tree: $out"
fi

# --- Test 11: the declared range comes from HEAD ---------------------------

echo
echo "=== Test 11: the consumer's declared range is read from HEAD ==="
# The other half. HEAD is what CI resolves and PyPI publishes, so an
# uncommitted widening in the working tree must not silence a finding.
HRANGE="$WORK/head-range"
mkdir -p "$HRANGE"
make_sibling "$HRANGE/nthlayer-common" nthlayer-common 2.1.2
make_consumer "$HRANGE/nthlayer-core" nthlayer-core ">=1.5.0,<2.0.0" 1.7.0
# Locally "fix" the range without committing. HEAD still declares <2.0.0.
printf '[project]\nname = "nthlayer-core"\nversion = "1.0.0"\ndependencies = [\n    "nthlayer-common>=2.1.2,<3.0.0",\n]\n\n[tool.uv.sources]\nnthlayer-common = { path = "../nthlayer-common", editable = true }\n' \
    > "$HRANGE/nthlayer-core/pyproject.toml"

rc=0
out="$(cd "$HRANGE" && run_doctor)" || rc=$?
if grep -q "SIBLING>CEILING" <<<"$out"; then
    pass "HEAD's <2.0.0 still evaluated despite an uncommitted widening"
else
    fail "read the range from the working tree instead of HEAD: $out"
fi

# --- Test 12: == and ~= imply a real ceiling -------------------------------

echo
echo "=== Test 12: == and ~= produce an actual ceiling, not just a flag ==="
# These recorded "bounded above" without a ceiling VALUE, so SIBLING>CEILING
# could never fire for them — a silent pass on the headline check.
spec_index=0
for spec_case in "==1.6.0" "~=1.6" "===1.6.0"; do
    # Indexed, not derived from the spec string: stripping punctuation mapped
    # "==1.6.0" and "===1.6.0" to the same directory, and the second git commit
    # then had nothing to commit and killed the run under set -e.
    spec_index=$((spec_index + 1))
    CASE="$WORK/spec-$spec_index"
    mkdir -p "$CASE"
    make_sibling "$CASE/nthlayer-common" nthlayer-common 2.1.2
    make_consumer "$CASE/nthlayer-core" nthlayer-core "$spec_case" 1.6.0
    rc=0
    out="$(cd "$CASE" && run_doctor)" || rc=$?
    if grep -q "SIBLING>CEILING" <<<"$out"; then
        pass "$spec_case bounds above and catches a 2.1.2 checkout"
    else
        fail "$spec_case did not produce a ceiling — output: $out"
    fi
done

# --- Test 13: <= is inclusive ----------------------------------------------

echo
echo "=== Test 13: <= admits its own boundary ==="
# Treating <= as < produced a false SIBLING>CEILING exactly at the boundary.
INCL="$WORK/inclusive"
mkdir -p "$INCL"
make_sibling "$INCL/nthlayer-common" nthlayer-common 2.1.2
make_consumer "$INCL/nthlayer-core" nthlayer-core ">=2.0.0,<=2.1.2" 2.1.2

rc=0
out="$(cd "$INCL" && run_doctor)" || rc=$?
if ! grep -q "SIBLING>CEILING" <<<"$out"; then
    pass "<=2.1.2 admits a 2.1.2 checkout"
else
    fail "false SIBLING>CEILING on an inclusive ceiling: $out"
fi

# --- Test 14: effective floor is the MAX of declared floors ----------------

echo
echo "=== Test 14: the effective floor is the highest declared floor ==="
# min() and max() were reversed, so >=1.0.0,>=2.1.2 was checked against 1.0.0
# and a lock at 1.6.0 passed.
EFF="$WORK/effective"
mkdir -p "$EFF"
make_sibling "$EFF/nthlayer-common" nthlayer-common 2.1.2
make_consumer "$EFF/nthlayer-core" nthlayer-core ">=1.0.0,>=2.1.2,<3.0.0" 1.6.0

rc=0
out="$(cd "$EFF" && run_doctor)" || rc=$?
if grep -q "LOCK<FLOOR" <<<"$out"; then
    pass "lock 1.6.0 caught against the effective floor 2.1.2"
else
    fail "used the lowest declared floor instead of the highest: $out"
fi

# --- Test 15: zero-padding — 2.1 and 2.1.0 are the same floor -------------

echo
echo "=== Test 15: >=2.1 admits a 2.1.0 checkout ==="
# Without zero-padding a shorter tuple compares less, so >=2.1 would flag a
# 2.1.0 lock as below floor.
PAD="$WORK/padding"
mkdir -p "$PAD"
make_sibling "$PAD/nthlayer-common" nthlayer-common 2.1.0
make_consumer "$PAD/nthlayer-core" nthlayer-core ">=2.1,<3.0.0" 2.1.0

rc=0
out="$(cd "$PAD" && run_doctor)" || rc=$?
if ! grep -q "LOCK<FLOOR" <<<"$out"; then
    pass ">=2.1 admits 2.1.0"
else
    fail "2.1 sorted below 2.1.0 — padding missing: $out"
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
