#!/usr/bin/env bash
# test_demo_start_lock.sh — regression test for demo/_start_lock.sh.
#
# Surfaced by opensrm-36es. The m7su start-lock guard works for the
# common 2-racer case; R5 dry-run flagged 7 IMPORTANT edge cases plus
# 5 missing test scenarios. This harness covers those scenarios by
# exercising the lock primitives in isolation — no docker, no uv, no
# nthlayer dependencies. Mirrors the test_demo_paths.sh pattern.
#
# What this test covers:
#   1. bash -n on demo.sh and demo/_start_lock.sh.
#   2. _acquire_start_lock returns 0 on first acquire, 1 on contended,
#      and the lock dir holds correct pid + owner metadata.
#   3. _demo_cleanup_start_lock removes the lock when WE own it.
#   4. _demo_cleanup_start_lock leaves the lock alone if pid mismatches.
#   5. Concurrent acquire under contention: N racers, exactly one wins.
#   6. Stale-lock reclaim path: dead PID inside lock → reclaim succeeds.
#   7. Owner-tag mismatch on live PID: treated as stale (PID-recycle
#      defense — protects against a recycled PID pointing at the user's
#      IDE/browser after PID wraparound).
#   8. EXIT trap fires on normal exit AND on `exit 1`.
#   9. EXIT trap fires on SIGINT (Ctrl-C mid-acquire).
#
# Runs in ~3-5s. No external dependencies beyond bash + coreutils.

set -uo pipefail

TEST_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
FRONTDOOR="$(cd "$TEST_DIR/.." && pwd)"
LOCK_LIB="$FRONTDOOR/demo/_start_lock.sh"
DEMO_SH="$FRONTDOOR/demo/demo.sh"

# Per-run scratch dir; cleaned on exit.
SCRATCH="$(mktemp -d -t demo-start-lock-test.XXXXXX)"
trap 'rm -rf "$SCRATCH"' EXIT

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
    if [[ -d "$1" ]]; then pass "$2"; else fail "$2 — missing: $1"; fi
}

assert_dir_missing() {
    if [[ ! -d "$1" ]]; then pass "$2"; else fail "$2 — still exists: $1"; fi
}

# --------------------------------------------------------------------------
echo "=== Test 1: bash -n syntax check ==="
if bash -n "$DEMO_SH"; then
    pass "demo.sh parses cleanly"
else
    fail "demo.sh has a shell syntax error"
fi
if bash -n "$LOCK_LIB"; then
    pass "_start_lock.sh parses cleanly"
else
    fail "_start_lock.sh has a shell syntax error"
fi

# --------------------------------------------------------------------------
echo
echo "=== Test 2: acquire + metadata shape ==="
LOCK="$SCRATCH/t2/.start.lock"
mkdir -p "$SCRATCH/t2"
(
    # shellcheck source=../demo/_start_lock.sh
    source "$LOCK_LIB"
    if _acquire_start_lock "$LOCK"; then
        echo "ACQUIRED"
    else
        echo "FAILED"
    fi
) > "$SCRATCH/t2.out"
assert_eq "$(cat "$SCRATCH/t2.out")" "ACQUIRED" "first acquire returns 0"
assert_dir_exists "$LOCK" "lock dir created"
assert_eq "$(cat "$LOCK/owner" 2>/dev/null || true)" "demo.sh-start-lock" "owner tag is 'demo.sh-start-lock'"
# pid file holds an integer
pid_in_lock="$(cat "$LOCK/pid" 2>/dev/null || true)"
if [[ "$pid_in_lock" =~ ^[0-9]+$ ]]; then
    pass "pid file holds an integer ($pid_in_lock)"
else
    fail "pid file does not hold an integer (got '$pid_in_lock')"
fi

# --------------------------------------------------------------------------
echo
echo "=== Test 3: cleanup hook removes lock when we own it ==="
LOCK="$SCRATCH/t3/.start.lock"
mkdir -p "$SCRATCH/t3"
(
    source "$LOCK_LIB"
    _DEMO_START_LOCK_DIR="$LOCK"
    _demo_register_cleanup _demo_cleanup_start_lock
    _acquire_start_lock "$LOCK"
    # subshell exits cleanly here; EXIT trap should rm the lock
)
assert_dir_missing "$LOCK" "lock dir removed by EXIT trap on normal exit"

# --------------------------------------------------------------------------
echo
echo "=== Test 4: cleanup hook leaves lock alone when PID mismatches ==="
LOCK="$SCRATCH/t4/.start.lock"
mkdir -p "$SCRATCH/t4"
# Pre-seed a lock owned by PID 99999 (almost certainly not us).
mkdir "$LOCK"
echo "99999" > "$LOCK/pid"
echo "demo.sh-start-lock" > "$LOCK/owner"
(
    source "$LOCK_LIB"
    _DEMO_START_LOCK_DIR="$LOCK"
    _demo_register_cleanup _demo_cleanup_start_lock
    # Don't acquire — just exit. Cleanup should see PID mismatch and skip.
)
assert_dir_exists "$LOCK" "lock dir preserved when pid mismatches"
rm -rf "$LOCK"

# --------------------------------------------------------------------------
echo
echo "=== Test 5: concurrent acquire — exactly one winner ==="
LOCK="$SCRATCH/t5/.start.lock"
mkdir -p "$SCRATCH/t5"
RESULTS="$SCRATCH/t5-results"
mkdir "$RESULTS"
N_RACERS=20
for i in $(seq 1 "$N_RACERS"); do
    (
        source "$LOCK_LIB"
        if _acquire_start_lock "$LOCK"; then
            echo "$i" > "$RESULTS/winner.$i"
        else
            echo "$i" > "$RESULTS/loser.$i"
        fi
    ) &
done
wait
winners="$(find "$RESULTS" -name 'winner.*' | wc -l | tr -d ' ')"
losers="$(find "$RESULTS" -name 'loser.*' | wc -l | tr -d ' ')"
assert_eq "$winners" "1" "exactly one winner out of $N_RACERS racers"
assert_eq "$losers" "$((N_RACERS - 1))" "the rest are losers"
# Winner's lock dir holds well-formed metadata.
assert_eq "$(cat "$LOCK/owner" 2>/dev/null || true)" "demo.sh-start-lock" "winner's owner tag is intact"
winner_pid="$(cat "$LOCK/pid" 2>/dev/null || true)"
if [[ "$winner_pid" =~ ^[0-9]+$ ]]; then
    pass "winner's pid file holds an integer ($winner_pid)"
else
    fail "winner's pid file does not hold an integer (got '$winner_pid')"
fi
rm -rf "$LOCK"

# --------------------------------------------------------------------------
echo
echo "=== Test 6: stale-lock detection — dead PID, matching owner ==="
LOCK="$SCRATCH/t6/.start.lock"
mkdir -p "$SCRATCH/t6"
mkdir "$LOCK"
# Find a PID that's definitely not running.
DEAD_PID=99999
while kill -0 "$DEAD_PID" 2>/dev/null; do
    DEAD_PID=$((DEAD_PID + 1))
done
echo "$DEAD_PID" > "$LOCK/pid"
echo "demo.sh-start-lock" > "$LOCK/owner"
# Caller logic (mirrors cmd_start): try acquire (fails), inspect, rm, retry.
(
    source "$LOCK_LIB"
    if _acquire_start_lock "$LOCK"; then
        echo "UNEXPECTED_FIRST_WIN"
        exit 0
    fi
    owner_pid="$(cat "$LOCK/pid" 2>/dev/null || true)"
    owner_tag="$(cat "$LOCK/owner" 2>/dev/null || true)"
    if [[ "$owner_tag" == "demo.sh-start-lock" ]] \
       && [[ -n "$owner_pid" ]] \
       && kill -0 "$owner_pid" 2>/dev/null; then
        echo "ALIVE_REFUSAL"
        exit 0
    fi
    rm -rf "$LOCK"
    if _acquire_start_lock "$LOCK"; then
        echo "RECLAIMED"
    else
        echo "RECLAIM_LOST"
    fi
) > "$SCRATCH/t6.out"
assert_eq "$(cat "$SCRATCH/t6.out")" "RECLAIMED" "dead-PID stale lock is reclaimed"
rm -rf "$LOCK"

# --------------------------------------------------------------------------
echo
echo "=== Test 7: owner-tag mismatch on live PID — treated as stale ==="
# This is the PID-recycle false-positive defense (m7su R5 finding #4).
# Seed lock with $$ (alive) but with WRONG owner tag — caller logic
# must treat as stale, not as a live demo run.
LOCK="$SCRATCH/t7/.start.lock"
mkdir -p "$SCRATCH/t7"
mkdir "$LOCK"
echo "$$" > "$LOCK/pid"
echo "definitely-not-demo-sh" > "$LOCK/owner"
(
    source "$LOCK_LIB"
    if _acquire_start_lock "$LOCK"; then
        echo "UNEXPECTED_FIRST_WIN"
        exit 0
    fi
    owner_pid="$(cat "$LOCK/pid" 2>/dev/null || true)"
    owner_tag="$(cat "$LOCK/owner" 2>/dev/null || true)"
    if [[ "$owner_tag" == "demo.sh-start-lock" ]] \
       && [[ -n "$owner_pid" ]] \
       && kill -0 "$owner_pid" 2>/dev/null; then
        echo "ALIVE_REFUSAL"
        exit 0
    fi
    rm -rf "$LOCK"
    if _acquire_start_lock "$LOCK"; then
        echo "RECLAIMED"
    else
        echo "RECLAIM_LOST"
    fi
) > "$SCRATCH/t7.out"
assert_eq "$(cat "$SCRATCH/t7.out")" "RECLAIMED" "owner-tag mismatch is reclaimed even on live PID"
rm -rf "$LOCK"

# Also test: live PID + MATCHING owner = honest refusal.
LOCK="$SCRATCH/t7b/.start.lock"
mkdir -p "$SCRATCH/t7b"
mkdir "$LOCK"
echo "$$" > "$LOCK/pid"
echo "demo.sh-start-lock" > "$LOCK/owner"
(
    source "$LOCK_LIB"
    if _acquire_start_lock "$LOCK"; then
        echo "UNEXPECTED_FIRST_WIN"
        exit 0
    fi
    owner_pid="$(cat "$LOCK/pid" 2>/dev/null || true)"
    owner_tag="$(cat "$LOCK/owner" 2>/dev/null || true)"
    if [[ "$owner_tag" == "demo.sh-start-lock" ]] \
       && [[ -n "$owner_pid" ]] \
       && kill -0 "$owner_pid" 2>/dev/null; then
        echo "ALIVE_REFUSAL"
        exit 0
    fi
    echo "INCORRECT_RECLAIM"
) > "$SCRATCH/t7b.out"
assert_eq "$(cat "$SCRATCH/t7b.out")" "ALIVE_REFUSAL" "live PID + matching owner = honest refusal"
rm -rf "$LOCK"

# --------------------------------------------------------------------------
echo
echo "=== Test 8: EXIT trap fires on exit 1 ==="
LOCK="$SCRATCH/t8/.start.lock"
mkdir -p "$SCRATCH/t8"
(
    source "$LOCK_LIB"
    _DEMO_START_LOCK_DIR="$LOCK"
    _demo_register_cleanup _demo_cleanup_start_lock
    _acquire_start_lock "$LOCK"
    exit 1
) || true   # absorb the non-zero rc
assert_dir_missing "$LOCK" "lock removed by EXIT trap on exit 1"

# --------------------------------------------------------------------------
echo
echo "=== Test 9: EXIT trap fires on SIGINT mid-acquire ==="
LOCK="$SCRATCH/t9/.start.lock"
mkdir -p "$SCRATCH/t9"
(
    source "$LOCK_LIB"
    _DEMO_START_LOCK_DIR="$LOCK"
    _demo_register_cleanup _demo_cleanup_start_lock
    _acquire_start_lock "$LOCK"
    sleep 5   # simulate mid-start work
) &
child_pid=$!
# Wait until lock appears so we kill AFTER acquire, not before.
for _ in $(seq 1 50); do
    [[ -d "$LOCK" ]] && break
    sleep 0.05
done
kill -INT "$child_pid" 2>/dev/null || true
wait "$child_pid" 2>/dev/null || true
assert_dir_missing "$LOCK" "lock removed by EXIT trap on SIGINT"

# --------------------------------------------------------------------------
echo
echo "=== Test 9b: empty-metadata lock is REFUSED (not reclaimed) ==="
# Pass 1 R5 finding: the bead originally prescribed "reclaim empty-pid
# locks", but that conflates two indistinguishable scenarios — a
# crashed mid-establisher (genuinely stale) and a slow alive holder
# (must not be reclaimed). Caller logic must refuse in that case.
LOCK="$SCRATCH/t9b/.start.lock"
mkdir -p "$SCRATCH/t9b"
mkdir "$LOCK"   # lock dir exists with no metadata — establish window
(
    source "$LOCK_LIB"
    if _acquire_start_lock "$LOCK"; then
        echo "UNEXPECTED_FIRST_WIN"
        exit 0
    fi
    _read_lock_state "$LOCK"
    if [[ "$_LOCK_OWNER" == "demo.sh-start-lock" ]] \
       && [[ -n "$_LOCK_PID" ]] \
       && kill -0 "$_LOCK_PID" 2>/dev/null; then
        echo "ALIVE_REFUSAL"
        exit 0
    fi
    if [[ -d "$LOCK" ]] \
       && { [[ -z "$_LOCK_PID" ]] || [[ -z "$_LOCK_OWNER" ]]; }; then
        echo "ESTABLISHING_REFUSAL"
        exit 0
    fi
    echo "INCORRECT_RECLAIM"
) > "$SCRATCH/t9b.out"
assert_eq "$(cat "$SCRATCH/t9b.out")" "ESTABLISHING_REFUSAL" "empty-metadata lock is refused, not reclaimed"
assert_dir_exists "$LOCK" "lock dir preserved through refusal path"
rm -rf "$LOCK"

# --------------------------------------------------------------------------
echo
echo "=== Test 10: cleanup recovers half-built lock (SIGINT mid-establish) ==="
# Simulates SIGINT landing between mkdir and the pid/owner echos.
# Manually re-creates that state: lock_dir exists, no metadata,
# _DEMO_START_LOCK_ESTABLISHING=1 in our shell.
LOCK="$SCRATCH/t10/.start.lock"
mkdir -p "$SCRATCH/t10"
(
    source "$LOCK_LIB"
    _DEMO_START_LOCK_DIR="$LOCK"
    _DEMO_START_LOCK_ESTABLISHING=1
    mkdir "$LOCK"
    _demo_register_cleanup _demo_cleanup_start_lock
)
assert_dir_missing "$LOCK" "half-built lock removed by EXIT trap (mid-establish recovery)"

# Also: confirm a half-built lock owned by SOMEONE ELSE (no
# establishing sentinel set in our shell) is left alone — i.e. the
# sentinel logic doesn't false-positive on locks we don't own.
LOCK="$SCRATCH/t10b/.start.lock"
mkdir -p "$SCRATCH/t10b"
mkdir "$LOCK"   # half-built foreign lock — no pid, no establishing flag
(
    source "$LOCK_LIB"
    _DEMO_START_LOCK_DIR="$LOCK"
    # establishing flag stays 0; we never called _acquire_start_lock
    _demo_register_cleanup _demo_cleanup_start_lock
)
assert_dir_exists "$LOCK" "foreign half-built lock preserved (no false-positive)"
rm -rf "$LOCK"

# --------------------------------------------------------------------------
echo
echo "==============================================="
echo "  Passed: $pass_count"
echo "  Failed: $fail_count"
echo "==============================================="

if (( fail_count > 0 )); then
    exit 1
fi
exit 0
