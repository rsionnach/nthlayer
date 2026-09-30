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
# Tests 9-16 extend the range arithmetic (worktree shadowing, working-tree vs
# HEAD provenance for each fact, == / ~= / <= ceilings, max-of-floors,
# zero-padding, pre-releases, name normalisation).
#
# Tests 17-24 are REPOSITORY IDENTITY [opensrm-bnal] — that a repo and its
# worktrees are one package checked out twice, while two distinct repos claiming
# one name stay a finding. Each banner names its own hazard; three of them
# substitute a `git` shim on PATH because the hazard only bites on a git version
# no machine running this suite has:
#   17/18. a real worktree is not a duplicate; two `git init` repos still are.
#   19.    an unreadable checkout splits rather than merging.
#   20.    both of those still hold on git < 2.31, which does not know
#          --path-format and ECHOES an unrecognised flag at exit 0.
#   21.    a relative --git-common-dir resolving to a non-git directory is
#          rejected, so two worktrees of different repos do not merge.
#   22.    an ANCESTOR repo's git dir, reached because git ascends out of a
#          half-cloned directory, is not this checkout's identity.
#   23.    an ambient GIT_DIR does not redirect the whole scan.
#   24.    reporting names the main checkout, not a worktree that happens to
#          sort first.
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

# make_consumer <dir> <name> <declared-range> <locked-sibling-version> [dep-name] [sibling-path]
#
# dep-name / sibling-path default to nthlayer-common / ../nthlayer-common. Every
# consumer also declares a THIRD-PARTY dep (starlette), because the guard that
# skips non-path-sourced deps is load-bearing in production — every real member
# declares starlette/uvicorn/httpx — and was untested without one. Removing that
# guard raises KeyError only when such a dep exists.
make_consumer() {
    local dir="$1" name="$2" range="$3" locked="$4"
    local dep="${5:-nthlayer-common}" spath="${6:-../nthlayer-common}"
    # uv NORMALISES names when it writes the lock, so a pyproject declaring
    # nthlayer_common yields a lock entry named nthlayer-common. Defaults to
    # dep; variant (d) sets it explicitly to exercise that mismatch.
    local lockname="${7:-$dep}"
    mkdir -p "$dir"
    printf '[project]\nname = "%s"\nversion = "1.0.0"\ndependencies = [\n    "%s%s",\n    "starlette>=0.40",\n]\n\n[tool.uv.sources]\n%s = { path = "%s", editable = true }\n' \
        "$name" "$dep" "$range" "$dep" "$spath" > "$dir/pyproject.toml"
    printf 'version = 1\n\n[[package]]\nname = "%s"\nversion = "%s"\nsource = { editable = "%s" }\n\n[[package]]\nname = "starlette"\nversion = "0.48.0"\nsource = { registry = "https://pypi.org/simple" }\n' \
        "$lockname" "$locked" "$spath" > "$dir/uv.lock"
    git -C "$dir" init -q
    git -C "$dir" add -A
    git -C "$dir" -c user.email=t@t -c user.name=t commit -qm init
}

# make_worktree <existing-repo-dir> <new-worktree-dir>
#
# A REAL `git worktree add`, not a second `git init`. That distinction is the
# whole point of tests 17/18/21/24: two independent repos claiming one name is a
# genuine ambiguity, while one repo checked out twice is the workspace's mandated
# working mode (.claude/bin/eco-worktree.sh).
make_worktree() {
    local parent="$1" dest="$2"
    git -C "$parent" worktree add -q --detach "$dest" HEAD
}

# --- git shims: reproducing older git, because the suite cannot otherwise ----
#
# Two of this bead's hazards only bite on git < 2.31, so on any machine that
# runs this suite the real git hides them and a reinstated flag or a weakened
# guard passes unopposed. eco_doctor.py invokes ["git", ...] without a shell, so
# prepending a shim directory to PATH is enough to substitute an older git for
# the doctor's own calls while the fixtures are still built by the real one.
#
# Each shim is self-checked at its point of use before anything is asserted
# through it. A shim that quietly stopped reproducing the old behaviour would
# otherwise turn these tests green for the wrong reason — the fixture-provenance
# failure this file's header already describes.

# shim_preamble <dir> — an executable `git` in *dir* that knows the real one.
shim_preamble() {
    mkdir -p "$1"
    printf '#!/usr/bin/env bash\n' > "$1/git"
    printf 'REAL=%q\n' "$(command -v git)" >> "$1/git"
}

# make_old_git_shim <dir>
#
# git < 2.31 does not know `--path-format`, and `git rev-parse` ECHOES an
# unrecognised argument to stdout and exits 0 rather than failing. Verified
# against the real git before this shim was written:
#
#     $ git -C repo rev-parse --bogus-flag=x --git-common-dir
#     --bogus-flag=x
#     .git
#     $ echo $?
#     0
#
# Echoed before delegating, which is where the real git prints it: the flag
# precedes --git-common-dir in the call under test.
make_old_git_shim() {
    shim_preamble "$1"
    cat >> "$1/git" <<'SHIM'
args=(); unknown=()
for a in "$@"; do
    case "$a" in
        --path-format=*) unknown+=("$a") ;;
        *) args+=("$a") ;;
    esac
done
if (( ${#unknown[@]} )) && [[ " $* " == *" rev-parse "* ]]; then
    printf '%s\n' "${unknown[@]}"
fi
exec "$REAL" "${args[@]}"
SHIM
    chmod +x "$1/git"
}

# make_relative_commondir_shim <dir>
#
# Before 2.31, `rev-parse --git-common-dir` inside a linked worktree could print
# the raw contents of .git/worktrees/<name>/commondir — the relative string
# `../..` — rather than a path resolved for the caller. Reproduced by reading
# that file directly. Only the doctor's exact call is intercepted; everything
# else reaches the real git untouched.
make_relative_commondir_shim() {
    shim_preamble "$1"
    cat >> "$1/git" <<'SHIM'
# Matched by SCANNING the arguments, never by position. Keying on `$3 ==
# rev-parse` would stop intercepting the moment git() gained a global option
# (--no-pager, -c foo=bar), and the failure mode is that test 21 goes VACUOUS
# rather than red — the shim would quietly delegate to the real git, the
# worktrees would resolve correctly, and the assertion would pass no matter what
# the guard did. The self-check at the point of use probes with a global option
# inserted for exactly that reason.
target=""; prev=""; want_revparse=0; want_common=0
for a in "$@"; do
    case "$a" in
        rev-parse)         want_revparse=1 ;;
        --git-common-dir)  want_common=1 ;;
    esac
    [[ "$prev" == -C ]] && target="$a"
    prev="$a"
done
if (( want_revparse && want_common )) && [[ -n "$target" && -f "$target/.git" ]]; then
    gitdir="$(sed -n 's/^gitdir: //p' "$target/.git")"
    if [[ -n "$gitdir" && -f "$gitdir/commondir" ]]; then
        cat "$gitdir/commondir"
        exit 0
    fi
fi
exec "$REAL" "$@"
SHIM
    chmod +x "$1/git"
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
# A second independent repo declaring the same package name at a version that
# would look fine, sorting after the real one. NOT a worktree — see
# make_worktree and test 17 for that case, which must NOT be reported.
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

# --- Test 16: coverage variants the gate identified -------------------------

echo
echo "=== Test 16: min-of-ceilings, pre-release, > floor, underscore name ==="
# Each of these behaviours is correct in the code but was unpinned — the
# corresponding mutant survived. The reviewer verified each by hand; these
# assertions stop them regressing silently.

# (a) effective ceiling is the LOWEST declared, mirroring test 14's floor case.
V="$WORK/v-ceiling"; mkdir -p "$V"
make_sibling "$V/nthlayer-common" nthlayer-common 2.5.0
make_consumer "$V/c" c ">=2.0.0,<2.0.0,<3.0.0" 2.5.0
out="$(cd "$V" && run_doctor)" || true
if grep -q "ceiling 2.0.0" <<<"$out"; then
    pass "effective ceiling is the lowest declared (2.0.0, not 3.0.0)"
else
    fail "used the highest declared ceiling: $out"
fi

# (b) a pre-release does not satisfy a floor at its own release.
V="$WORK/v-prerelease"; mkdir -p "$V"
make_sibling "$V/nthlayer-common" nthlayer-common 2.1.0
make_consumer "$V/c" c ">=2.1.0,<3.0.0" 2.1.0rc1
out="$(cd "$V" && run_doctor)" || true
if grep -q "LOCK<FLOOR" <<<"$out"; then
    pass "lock 2.1.0rc1 is below floor 2.1.0"
else
    fail "pre-release treated as its own release: $out"
fi

# (c) an exclusive floor excludes its own boundary.
V="$WORK/v-exclusive"; mkdir -p "$V"
make_sibling "$V/nthlayer-common" nthlayer-common 2.1.2
make_consumer "$V/c" c ">2.1.2,<3.0.0" 2.1.2
out="$(cd "$V" && run_doctor)" || true
if grep -q "LOCK<FLOOR" <<<"$out"; then
    pass ">2.1.2 excludes a 2.1.2 lock"
else
    fail "exclusive floor treated as inclusive: $out"
fi

# (d) name normalisation: pyproject says nthlayer_common, the lock says
#     nthlayer-common — which is what uv actually writes. The assertion has to
#     DEPEND on the lock being found, so the lock is stale: with canonical()
#     reduced to identity the lookup misses, no STALE is reported, and this
#     fails. An earlier version of this variant spelled the dep the same way on
#     both sides, so normalisation was never needed and the mutant survived.
V="$WORK/v-canonical"; mkdir -p "$V"
make_sibling "$V/nthlayer-common" nthlayer-common 2.1.2
make_consumer "$V/c" c ">=2.1.2,<3.0.0" 1.6.0 nthlayer_common ../nthlayer-common nthlayer-common
out="$(cd "$V" && run_doctor)" || true
if grep -q "STALE" <<<"$out"; then
    pass "underscore dep matched against a hyphenated lock entry"
else
    fail "separator difference lost the lock entry: $out"
fi

# (e) a path source pointing nowhere is reported, not skipped.
V="$WORK/v-missing"; mkdir -p "$V"
make_sibling "$V/nthlayer-common" nthlayer-common 2.1.2
make_consumer "$V/c" c ">=2.1.2,<3.0.0" 2.1.2 nthlayer-common ../nthlayer-gone
out="$(cd "$V" && run_doctor)" || true
if grep -q "SIBLING-MISSING" <<<"$out"; then
    pass "a path source with no readable pyproject is reported"
else
    fail "silently skipped a missing sibling: $out"
fi

# --- Test 17: a worktree of the same repo is not a duplicate ---------------

echo
echo "=== Test 17: a git worktree does not trigger DUPLICATE-NAME ==="
# opensrm-bnal. DUPLICATE-NAME was added as a safety net beneath NAME-BASED
# sibling resolution, but the same change replaced that with [tool.uv.sources]
# path resolution — so the net sits beneath a mechanism that no longer uses
# names. Meanwhile CLAUDE.md MANDATES sibling worktrees, and a worktree always
# declares its parent's project.name, so the finding fired on every correct
# workflow and (classified as blocking by the opensrm-px23 pre-flight) refused
# every R5 gate in the workspace. Found on that pre-flight's first real use.
WT="$WORK/worktree-dup"
mkdir -p "$WT"
make_sibling "$WT/nthlayer-common" nthlayer-common 2.1.2
make_consumer "$WT/nthlayer-core" nthlayer-core ">=2.1.2,<3.0.0" 2.1.2
make_worktree "$WT/nthlayer-common" "$WT/nthlayer-common-wip"

rc=0
out="$(cd "$WT" && run_doctor)" || rc=$?
if ! grep -q "DUPLICATE-NAME" <<<"$out"; then
    pass "a worktree of the same repo is not reported as a duplicate"
else
    fail "worktree reported as DUPLICATE-NAME — blocks every gate: $out"
fi
if (( rc == 0 )); then
    pass "clean workspace with a worktree present still exits 0"
else
    fail "exited $rc with only a worktree present — output: $out"
fi

# --- Test 18: two distinct repos claiming one name still report -------------

echo
echo "=== Test 18: two DISTINCT repos claiming one name still report ==="
# The other side. Test 9 already covers the shadowing protection; this asserts
# the finding survives for the case it was actually written for, so the bnal fix
# cannot be mistaken for deleting the check.
DIST="$WORK/distinct-dup"
mkdir -p "$DIST"
make_sibling "$DIST/nthlayer-common" nthlayer-common 2.1.2
make_sibling "$DIST/nthlayer-common-rival" nthlayer-common 3.5.0
make_consumer "$DIST/nthlayer-core" nthlayer-core ">=2.1.2,<3.0.0" 2.1.2
# A worktree of the real one MUST be present for the naming assertion below to
# mean anything: without it every identity appears exactly once and first-wins
# is indistinguishable from last-wins. The first version of this fixture had no
# worktree, so the assertion passed against the bug it was written to catch.
make_worktree "$DIST/nthlayer-common" "$DIST/nthlayer-common-wt"

rc=0
out="$(cd "$DIST" && run_doctor)" || rc=$?
if grep -q "DUPLICATE-NAME" <<<"$out"; then
    pass "two independent repos claiming one name still reported"
else
    fail "the genuine duplicate case was lost: $out"
fi
# The finding must name the checkout actually in conflict.
# The worktree shares the real repo's identity, so last-wins would name
# nthlayer-common-wt — which declares nothing of its own — instead of
# nthlayer-common, the checkout actually in conflict with the rival.
if grep "DUPLICATE-NAME" <<<"$out" | grep -qv "nthlayer-common-wt"; then
    pass "names the real conflicting checkout, not the worktree bystander"
else
    fail "named a worktree instead of the conflicting checkout: $(grep DUPLICATE-NAME <<<"$out")"
fi

# --- Test 19: an unreadable repo is treated as distinct ---------------------

echo
echo "=== Test 19: an unreadable repo is treated as distinct, not merged ==="
# The fallback. A wrong MERGE silences a real ambiguity; a wrong SPLIT reports
# one that is easy to dismiss.
#
# The .git must still EXIST or discover_repos skips the directory entirely and
# there is no duplicate to find — the first version of this fixture deleted it
# and the test failed for that reason, not the one intended. Replacing it with
# an unreadable file keeps the directory discoverable while making rev-parse
# fail, which is the path under test.
ORPH="$WORK/orphan"; mkdir -p "$ORPH"
# BOTH must be unreadable. With only one, a fallback that merged every failure
# into a single identity would still leave two distinct identities overall and
# the finding would appear anyway — the first version of this fixture had one
# and passed against the bug it was written to catch.
make_sibling "$ORPH/nthlayer-common-broken-a" nthlayer-common 2.1.2
make_sibling "$ORPH/nthlayer-common-broken-b" nthlayer-common 3.5.0
for broken in a b; do
    rm -rf "$ORPH/nthlayer-common-broken-$broken/.git"
    printf 'not a git directory\n' > "$ORPH/nthlayer-common-broken-$broken/.git"
done
make_consumer "$ORPH/nthlayer-core" nthlayer-core ">=2.1.2,<3.0.0" 2.1.2

out="$(cd "$ORPH" && run_doctor)" || true
if grep -q "DUPLICATE-NAME" <<<"$out"; then
    pass "an unreadable checkout stays distinct and is still reported"
else
    fail "unreadable checkout merged into another identity: $out"
fi

# --- Test 20: the worktree fix must hold on git < 2.31 ---------------------

echo
echo "=== Test 20: identity survives a git that does not know --path-format ==="
# opensrm-bnal, round-1 CRITICAL. Reinstating `--path-format=absolute` in
# repo_identity() survives every other test in this file, because the flag works
# on git >= 2.31 and that is what any machine running this suite has. The failure
# is invisible without an older git, so someone tidying the flag back in would
# meet a green suite — and on the old git the identity collapses to the constant
# "--path-format=absolute\n.git" for every main checkout, merging all distinct
# repositories into one and silencing genuine duplicates.
#
# Re-runs the fixtures from tests 17 and 18 with an older git substituted for the
# doctor's calls, so BOTH directions are covered on the version that breaks.
SHIMBIN="$WORK/oldgit-bin"
make_old_git_shim "$SHIMBIN"

# Shim self-check FIRST. If the shim does not reproduce the hazard — echoing the
# unknown flag and still exiting 0 — the two assertions below pass for the wrong
# reason and prove nothing.
shim_rc=0
shim_out="$(PATH="$SHIMBIN:$PATH" git -C "$WT/nthlayer-common" \
    rev-parse --path-format=absolute --git-common-dir 2>&1)" || shim_rc=$?
if (( shim_rc == 0 )) && [[ "$(head -1 <<<"$shim_out")" == "--path-format=absolute" ]] \
   && (( $(wc -l <<<"$shim_out") == 2 )); then
    pass "shim reproduces pre-2.31 rev-parse: echoes the unknown flag, exits 0"
else
    fail "shim does not reproduce pre-2.31 rev-parse (rc=$shim_rc): $shim_out"
fi

rc=0
out="$(cd "$WT" && PATH="$SHIMBIN:$PATH" run_doctor)" || rc=$?
if ! grep -q "DUPLICATE-NAME" <<<"$out" && (( rc == 0 )); then
    pass "on git < 2.31 a worktree is still not a duplicate (exit $rc)"
else
    fail "old git reintroduced the bnal bug (exit $rc): $out"
fi

rc=0
out="$(cd "$DIST" && PATH="$SHIMBIN:$PATH" run_doctor)" || rc=$?
if grep -q "DUPLICATE-NAME" <<<"$out" \
   && grep "DUPLICATE-NAME" <<<"$out" | grep -qv "nthlayer-common-wt"; then
    pass "on git < 2.31 the genuine duplicate is still reported, named correctly"
else
    fail "old git lost or misnamed the genuine duplicate (exit $rc): $out"
fi

# --- Test 21: a bogus-but-existing common-dir must not merge two repos ------

echo
echo "=== Test 21: a relative --git-common-dir must not merge distinct repos ==="
# opensrm-bnal. `candidate.exists()` was both untested — when git succeeds the
# path always exists, so `if True:` survived — and too weak. Before 2.31,
# --git-common-dir inside a linked worktree could print the raw contents of
# .git/worktrees/<name>/commondir, the relative string `../..`. Resolved against
# the checkout that is the workspace's PARENT, which exists, so an existence
# check accepts it as an identity.
#
# Two worktrees of two DIFFERENT repos then land on the same ancestor and are
# merged, so the duplicate they genuinely are goes unreported — the false
# negative the fallback exists to prevent. Requiring (candidate / "HEAD") rejects
# any path that is not a git directory.
#
# The parent repos live OUTSIDE the scanned workspace deliberately: with a parent
# present, its own identity resolves correctly and the name still maps to more
# than one identity, so the finding appears either way and the fixture proves
# nothing.
REL="$WORK/rel-commondir"
RELPARENTS="$WORK/rel-parents"
mkdir -p "$REL" "$RELPARENTS"
make_sibling "$RELPARENTS/upstream-a" nthlayer-common 2.1.2
make_sibling "$RELPARENTS/upstream-b" nthlayer-common 3.5.0
make_worktree "$RELPARENTS/upstream-a" "$REL/nthlayer-common-wt-a"
make_worktree "$RELPARENTS/upstream-b" "$REL/nthlayer-common-wt-b"

RELBIN="$WORK/relgit-bin"
make_relative_commondir_shim "$RELBIN"

# Shim self-check, and a check that the fixture's own premise holds: the string
# must be relative, and must resolve to a directory that EXISTS but is NOT a git
# directory. If either stops being true the assertion below is vacuous.
#
# `|| probe=""` is load-bearing, not defensive noise. Under `set -euo pipefail` a
# failing command substitution in an ASSIGNMENT aborts the script — verified:
# `x="$(cd /tmp && cd notadir 2>/dev/null && pwd)"` exits 1 without reaching the
# next line. Unguarded, a broken premise would kill the suite here, BEFORE the
# `fail` below that exists to report it, before test 21's real assertion, and
# before the PASS/FAIL summary. Not a false green, but it turns a deliberate
# diagnostic into a silent early exit.
#
# A GLOBAL OPTION is inserted deliberately — see make_relative_commondir_shim
# for why the shim scans its arguments instead of keying on their position. If
# the probe stops going through the shim, test 21 passes VACUOUSLY.
probe="$(PATH="$RELBIN:$PATH" git --no-pager -C "$REL/nthlayer-common-wt-a" \
    rev-parse --git-common-dir 2>&1)" || probe="<git failed: $?>"
resolved="$(cd "$REL/nthlayer-common-wt-a" && cd "$probe" 2>/dev/null && pwd)" \
    || resolved=""
if [[ "$probe" == "../.." && -n "$resolved" && ! -e "$resolved/HEAD" ]]; then
    pass "shim intercepts past a global option, yielding a relative common-dir"
else
    fail "fixture premise broken: probe='$probe' resolved='$resolved'"
fi

rc=0
out="$(cd "$REL" && PATH="$RELBIN:$PATH" run_doctor)" || rc=$?
if grep -q "DUPLICATE-NAME" <<<"$out"; then
    pass "a non-git common-dir is rejected, so the two repos stay distinct"
else
    fail "two distinct repos merged on a bogus common-dir, duplicate silenced (exit $rc): $out"
fi

# --- Test 22: git ASCENDS — a common-dir must belong to the checkout ---------

echo
echo "=== Test 22: an ancestor's git dir is not this checkout's identity ==="
# opensrm-bnal, round-3 (correctness pass). `git rev-parse` does not fail for a
# directory that merely LOOKS like a repo — it ascends. A `.git` that is an empty
# DIRECTORY (an interrupted clone, a half-finished copy) is not a repository, so
# rev-parse answers for the nearest ancestor repo and exits 0. Verified:
#
#     $ git -C ws/member rev-parse --git-common-dir
#     ../../.git
#     $ echo $?
#     0
#
# That path has a HEAD, so the (candidate / "HEAD") guard from test 21 accepts
# it, and EVERY such member collapses onto the ancestor's identity — a genuine
# duplicate silenced. Reachable on ANY git version, unlike the relative-commondir
# case. An invalid `.git` FILE fails cleanly (rc=128), which is why test 19's
# fixture was already sound and this one needs a directory.
ANC="$WORK/ancestor"
mkdir -p "$ANC"
git -C "$ANC" init -q
git -C "$ANC" -c user.email=t@t -c user.name=t commit -q --allow-empty -m init
ANCWS="$ANC/ws"
mkdir -p "$ANCWS"
for half in a b; do
    mkdir -p "$ANCWS/nthlayer-common-half-$half/.git"
    printf '[project]\nname = "nthlayer-common"\nversion = "2.1.%s"\n' "$half" \
        > "$ANCWS/nthlayer-common-half-$half/pyproject.toml"
done

# Premise check: the ancestor must actually be reachable by ascent, or the
# assertion below passes because there was nothing to be hijacked by.
anc_probe="$(git -C "$ANCWS/nthlayer-common-half-a" rev-parse --git-common-dir 2>&1)" \
    || anc_probe="<git failed: $?>"
anc_resolved="$(cd "$ANCWS/nthlayer-common-half-a" && cd "$anc_probe" 2>/dev/null && pwd)" \
    || anc_resolved=""
if [[ -n "$anc_resolved" && -e "$anc_resolved/HEAD" ]]; then
    pass "premise holds: rev-parse ascends to a real git dir ('$anc_probe')"
else
    fail "premise broken: probe='$anc_probe' resolved='$anc_resolved'"
fi

rc=0
out="$(cd "$ANCWS" && run_doctor)" || rc=$?
if grep -q "DUPLICATE-NAME" <<<"$out"; then
    pass "two half-cloned checkouts do not merge onto the ancestor's identity"
else
    fail "ancestor identity merged both checkouts, duplicate silenced (exit $rc): $out"
fi

# --- Test 23: an ambient GIT_DIR must not redirect the whole scan -----------

echo
echo "=== Test 23: GIT_DIR in the environment does not hijack the scan ==="
# GIT_DIR / GIT_COMMON_DIR / GIT_WORK_TREE OVERRIDE `-C`, so one exported by a
# hook or a wrapper makes every repo answer for the same repository: the same
# pyproject and the same uv.lock read for all of them. Asserted on a RANGE
# finding rather than on DUPLICATE-NAME, because the identity cross-check added
# in test 22 already rejects a hijacked toplevel — the committed-lock reads are
# where the scrub is the only thing standing in the way.
#
# Reuses test 3's stale-lock fixture: with GIT_DIR pointing elsewhere,
# `git show HEAD:uv.lock` reads the WRONG repo, finds no lock, and the repo drops
# out of the scan entirely — the workspace reports clean.
#
# Its OWN decoy repo, not test 22's `$ANC`. Borrowing a fixture across tests
# means deleting or reordering the earlier one aborts the suite here under
# `set -euo pipefail` rather than failing this assertion — a fragility of exactly
# the kind this bead keeps finding.
DECOY="$WORK/git-dir-decoy"
mkdir -p "$DECOY"
git -C "$DECOY" init -q
git -C "$DECOY" -c user.email=t@t -c user.name=t commit -q --allow-empty -m init

rc=0
out="$(cd "$STALE" && GIT_DIR="$DECOY/.git" run_doctor)" || rc=$?
if grep -q "STALE" <<<"$out" && (( rc == FINDINGS_RC )); then
    pass "an ambient GIT_DIR is scrubbed; the stale lock is still found"
else
    fail "GIT_DIR redirected the scan, findings lost (exit $rc): $out"
fi

# --- Test 24: naming must not depend on how directories sort ----------------

echo
echo "=== Test 24: a worktree sorting BEFORE its parent is still not named ==="
# Test 18 proves the finding names the conflicting checkout rather than a
# worktree bystander, but only because discover_repos() sorts lexicographically
# and `nthlayer-common-wt` happens to sort after `nthlayer-common`. Nothing
# enforces that — `git worktree add` accepts any destination, and only
# eco-worktree.sh's `<repo>-<slug>` convention keeps it true. A worktree named to
# sort FIRST would be named in place of the parent, reintroducing the round-1
# defect. Main checkouts are now processed before linked worktrees regardless of
# name.
SORT="$WORK/sort-order"
mkdir -p "$SORT"
make_sibling "$SORT/nthlayer-common" nthlayer-common 2.1.2
make_sibling "$SORT/nthlayer-common-rival" nthlayer-common 3.5.0
# "aaa-" sorts before every other entry, so first-wins by sort order would pick
# this worktree as the representative of the parent's identity.
make_worktree "$SORT/nthlayer-common" "$SORT/aaa-common-wt"

rc=0
out="$(cd "$SORT" && run_doctor)" || rc=$?
dupline="$(grep "DUPLICATE-NAME" <<<"$out" || true)"
if [[ "$dupline" == *"nthlayer-common,"* || "$dupline" == *" nthlayer-common" ]]; then
    pass "names the parent checkout even though the worktree sorts first"
else
    fail "a first-sorting worktree was named instead of the parent: '$dupline'"
fi
if [[ "$dupline" != *"aaa-common-wt"* ]]; then
    pass "the first-sorting worktree bystander is not named"
else
    fail "worktree bystander named: '$dupline'"
fi

# --- Test 25: a non-UTF8 pyproject must not kill the scan -------------------

echo
echo "=== Test 25: an undecodable pyproject does not abort the whole scan ==="
# opensrm-bnal, edge-cases pass. THE WORST SHAPE THIS TOOL CAN FAIL IN. Both
# `pj.read_text()` and git()'s `text=True` decode as UTF-8, and an undecodable
# byte raises UnicodeDecodeError — a ValueError, so neither `except OSError` nor
# `except TOMLDecodeError` caught it. One latin-1 byte in one pyproject killed
# the ENTIRE scan with a traceback at exit 1.
#
# Exit 1 is also the code for "drift found", and the /r5-supervise pre-flight
# classifies findings by line PREFIX rather than by exit code — deliberately,
# see opensrm-px23. A traceback carries no prefix, so the pre-flight read zero
# blocking findings and PROCEEDED, having scanned nothing at all. A clean record
# from a check that never ran is precisely what this tool exists to prevent, and
# what CLAUDE.md calls worse than no gate.
#
# A latin-1 author comment or a UTF-16 BOM from a Windows editor is enough.
U8="$WORK/non-utf8"
mkdir -p "$U8"
make_sibling "$U8/nthlayer-common" nthlayer-common 2.1.2
make_sibling "$U8/nthlayer-common-rival" nthlayer-common 3.5.0
# Stray 0xff in a COMMENT, so the file is still valid TOML once decodable: the
# name must still be read and the duplicate must still be found, not merely
# survived.
printf '[project]\nname = "nthlayer-common"\nversion = "3.5.0"  # \xff\n' \
    > "$U8/nthlayer-common-rival/pyproject.toml"

rc=0
out="$(cd "$U8" && run_doctor)" || rc=$?
if ! grep -qE "Traceback|UnicodeDecodeError" <<<"$out"; then
    pass "an undecodable pyproject does not traceback"
else
    fail "traceback on an undecodable pyproject: $out"
fi
if grep -q "DUPLICATE-NAME" <<<"$out" && (( rc == FINDINGS_RC )); then
    pass "the other findings still print (exit $rc)"
else
    fail "findings lost to an undecodable pyproject (exit $rc): $out"
fi

# The COMMITTED-file path is separate: it decodes inside subprocess.run via
# git(), not via read_text(), and had the same defect.
U8C="$WORK/non-utf8-committed"
mkdir -p "$U8C/nthlayer-core"
printf '[project]\nname = "nthlayer-core"\nversion = "1.0.0"  # \xff\n' \
    > "$U8C/nthlayer-core/pyproject.toml"
git -C "$U8C/nthlayer-core" init -q
git -C "$U8C/nthlayer-core" add -A
git -C "$U8C/nthlayer-core" -c user.email=t@t -c user.name=t commit -qm init

# Premise: the byte must actually have reached HEAD, or this asserts nothing
# about git()'s decode. `git show` is the exact call the doctor makes.
if git -C "$U8C/nthlayer-core" show HEAD:pyproject.toml 2>/dev/null \
       | LC_ALL=C grep -q $'\xff'; then
    pass "premise: the committed blob really is not valid UTF-8"
else
    fail "premise broken: the 0xff byte did not reach HEAD"
fi

rc=0
out="$(cd "$U8C" && run_doctor)" || rc=$?
if ! grep -qE "Traceback|UnicodeDecodeError" <<<"$out"; then
    pass "an undecodable COMMITTED pyproject does not traceback either"
else
    fail "traceback via git()'s decode: $out"
fi

# --- Test 26: a worktree whose parent vanished is still one repo -------------

echo
echo "=== Test 26: worktrees of a MOVED parent are not a duplicate ==="
# opensrm-bnal, edge-cases pass. Two worktrees remain in the workspace, their
# parent repo is moved or deleted. git can resolve neither, so both took the
# path fallback and were reported as a DUPLICATE-NAME — which is blocking, so it
# refused every gate in the workspace exactly as the original bug did, AND was
# untrue: it said two DISTINCT repositories claim one name when they are one
# repository checked out twice.
#
# A worktree's `.git` file records `gitdir: <parent>/.git/worktrees/<name>`,
# written by git at creation, so the parent is recoverable from the worktree
# alone. Two worktrees of one parent therefore still agree after the parent is
# gone. Nothing is dereferenced — the recorded path is only an opaque key.
MOVED="$WORK/moved-parent"
MOVEDP="$WORK/moved-parent-upstreams"
mkdir -p "$MOVED" "$MOVEDP"
make_sibling "$MOVEDP/upstream" nthlayer-common 2.1.2
make_worktree "$MOVEDP/upstream" "$MOVED/nthlayer-common-wt-a"
make_worktree "$MOVEDP/upstream" "$MOVED/nthlayer-common-wt-b"

# Premise: alive, they must already agree — otherwise this test could pass
# without the parent ever having gone missing.
rc=0
out="$(cd "$MOVED" && run_doctor)" || rc=$?
if ! grep -q "DUPLICATE-NAME" <<<"$out"; then
    pass "premise: with the parent alive the two worktrees agree"
else
    fail "premise broken, worktrees disagreed while the parent was alive: $out"
fi

mv "$MOVEDP/upstream" "$MOVEDP/upstream-moved"
rc=0
out="$(cd "$MOVED" && run_doctor)" || rc=$?
if ! grep -q "DUPLICATE-NAME" <<<"$out" && (( rc == 0 )); then
    pass "two worktrees of a vanished parent are still one repo (exit $rc)"
else
    fail "a moved parent resurrected the blocking false positive (exit $rc): $out"
fi

# --- Test 27: ...but two vanished parents are still two repos ---------------

echo
echo "=== Test 27: stale worktrees of DIFFERENT parents still report ==="
# The other direction, and the reason test 26 cannot be mistaken for deleting
# the check. Each worktree records its OWN parent, so distinct parents yield
# distinct keys even though neither path exists any more.
TWOP="$WORK/two-moved-parents"
TWOPP="$WORK/two-moved-upstreams"
mkdir -p "$TWOP" "$TWOPP"
for up in alpha beta; do
    make_sibling "$TWOPP/$up" nthlayer-common "2.1.2"
    make_worktree "$TWOPP/$up" "$TWOP/nthlayer-common-wt-$up"
    mv "$TWOPP/$up" "$TWOPP/$up-moved"
done

rc=0
out="$(cd "$TWOP" && run_doctor)" || rc=$?
if grep -q "DUPLICATE-NAME" <<<"$out" && (( rc == FINDINGS_RC )); then
    pass "two vanished parents remain two repositories (exit $rc)"
else
    fail "distinct stale parents merged, duplicate silenced (exit $rc): $out"
fi

# --- Test 28: a whitespace-only project.name is not a name ------------------

echo
echo "=== Test 28: a whitespace-only project.name is skipped, not printed ==="
# `if not name` admitted "   ", which rendered a finding with an empty gap where
# the package name belongs — unreadable, and indistinguishable from a formatting
# bug in the tool itself.
BLANK="$WORK/blank-name"
mkdir -p "$BLANK"
for d in one two; do
    mkdir -p "$BLANK/$d"
    printf '[project]\nname = "   "\nversion = "1.0.0"\n' > "$BLANK/$d/pyproject.toml"
    git -C "$BLANK/$d" init -q
    git -C "$BLANK/$d" add -A
    git -C "$BLANK/$d" -c user.email=t@t -c user.name=t commit -qm init
done

rc=0
out="$(cd "$BLANK" && run_doctor)" || rc=$?
if ! grep -q "DUPLICATE-NAME" <<<"$out"; then
    pass "a whitespace-only name is skipped rather than printed blank"
else
    fail "printed a nameless finding: $(grep DUPLICATE-NAME <<<"$out")"
fi

# --- Test 29: a padded name is the same name --------------------------------

echo
echo "=== Test 29: \" dup \" and \"dup\" are one name, not two ==="
# opensrm-bnal, edge-cases iteration 2. canonical() collapses [-_.]+ and
# lowercases; it does NOT trim. The whitespace guard added in test 28 only
# TESTED name.strip() while the key stayed canonical(name) on the untrimmed
# string, so "dup" and " dup " keyed differently and a genuine duplicate was
# silenced. False-negative direction, and reachable from an ordinary hand-edited
# pyproject.
PAD="$WORK/padded-name"
mkdir -p "$PAD"
for pair in "one:dup" "two: dup "; do
    d="${pair%%:*}"; n="${pair#*:}"
    mkdir -p "$PAD/$d"
    printf '[project]\nname = "%s"\nversion = "1.0.0"\n' "$n" > "$PAD/$d/pyproject.toml"
    git -C "$PAD/$d" init -q
    git -C "$PAD/$d" add -A
    git -C "$PAD/$d" -c user.email=t@t -c user.name=t commit -qm init
done

rc=0
out="$(cd "$PAD" && run_doctor)" || rc=$?
if grep -q "DUPLICATE-NAME" <<<"$out" && (( rc == FINDINGS_RC )); then
    pass "a padded name still collides with the bare one (exit $rc)"
else
    fail "padding evaded the duplicate check (exit $rc): $out"
fi
# The printed name must be the stripped one, or the column has a leading gap.
if grep -qE "DUPLICATE-NAME .* dup declared by" <<<"$out"; then
    pass "the printed name is trimmed"
else
    fail "printed an untrimmed name: $(grep DUPLICATE-NAME <<<"$out")"
fi

# --- Test 30: absolute and relative recorded gitdirs are one parent ---------

echo
echo "=== Test 30: mixed absolute/relative gitdir is still one repository ==="
# opensrm-bnal, edge-cases iteration 2. git >= 2.48 can write a RELATIVE gitdir
# (worktree.useRelativePaths, --relative-paths). recorded_common_dir() used the
# recorded string as an opaque key, so one worktree created before that setting
# and one after DISAGREED about the same parent — splitting them and firing the
# blocking DUPLICATE-NAME that test 26 exists to prevent. Resolving against the
# checkout makes both forms comparable.
#
# The relative form is written by hand because the local git (2.39) cannot
# produce it. The string is exactly what git >= 2.48 records, and the absolute
# sibling is left as git actually wrote it, so only the FORM differs.
MIX="$WORK/mixed-gitdir"
MIXP="$WORK/mixed-gitdir-upstream"
mkdir -p "$MIX" "$MIXP"
make_sibling "$MIXP/shared" nthlayer-common 2.1.2
make_worktree "$MIXP/shared" "$MIX/nthlayer-common-wt-abs"
make_worktree "$MIXP/shared" "$MIX/nthlayer-common-wt-rel"
printf 'gitdir: ../../mixed-gitdir-upstream/shared/.git/worktrees/nthlayer-common-wt-rel\n' \
    > "$MIX/nthlayer-common-wt-rel/.git"

# Premise: the two recorded forms must actually DIFFER as strings, or resolution
# is not what makes this test pass.
abs_rec="$(sed -n 's/^gitdir: //p' "$MIX/nthlayer-common-wt-abs/.git")"
rel_rec="$(sed -n 's/^gitdir: //p' "$MIX/nthlayer-common-wt-rel/.git")"
if [[ "$abs_rec" != "$rel_rec" && "$abs_rec" == /* && "$rel_rec" != /* ]]; then
    pass "premise: one recorded gitdir is absolute, the other relative"
else
    fail "premise broken: abs='$abs_rec' rel='$rel_rec'"
fi

mv "$MIXP/shared" "$MIXP/shared-moved"
rc=0
out="$(cd "$MIX" && run_doctor)" || rc=$?
if ! grep -q "DUPLICATE-NAME" <<<"$out" && (( rc == 0 )); then
    pass "absolute and relative gitdirs resolve to one parent (exit $rc)"
else
    fail "mixed gitdir forms split one repo into a blocking duplicate (exit $rc): $out"
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
