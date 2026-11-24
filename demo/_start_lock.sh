#!/usr/bin/env bash
# Demo start-lock primitives. Sourced by demo/demo.sh and by
# test/test_demo_start_lock.sh (opensrm-36es regression test).
#
# Extracted from demo.sh so the lock primitives are exercisable in
# isolation — mirrors the _paths.sh / test_demo_paths.sh split from
# opensrm-oey5.
#
# Owns:
#   - _demo_cleanup / _demo_register_cleanup : append-only EXIT-trap
#     registry. Generic but currently used only by the start-lock; lift
#     to _cleanup.sh if more hooks emerge.
#   - _DEMO_START_LOCK_DIR : script-global the cleanup hook reads from.
#   - _demo_cleanup_start_lock : the EXIT hook itself.
#   - _acquire_start_lock <lock_dir> : the mutex (mkdir, then an
#     exclusive create of the pid file, which decides the winner).
#   - _read_lock_state <lock_dir> : sets _LOCK_PID / _LOCK_OWNER from
#     the lock metadata, tolerating the brief establish window.
#
# Sourcing this file registers the EXIT trap. Callers that need
# multiple cleanup hooks should _demo_register_cleanup their own
# functions; _demo_cleanup_start_lock is NOT registered automatically
# (cmd_start registers it after setting _DEMO_START_LOCK_DIR).

# ---------------------------------------------------------------------------
# Cleanup registry
# ---------------------------------------------------------------------------
#
# Why this pattern (m7su R5 finding #3): a naked `trap "rm -rf X" EXIT`
# silently replaces any prior EXIT handler. The registry composes
# instead — each subsystem appends its hook and they all run in
# registration order, with per-hook errors swallowed so one bad hook
# can't strand the others.

_DEMO_CLEANUP_HOOKS=()

_demo_register_cleanup() {
    _DEMO_CLEANUP_HOOKS+=("$1")
}

_demo_cleanup() {
    local hook
    for hook in "${_DEMO_CLEANUP_HOOKS[@]:-}"; do
        [[ -n "$hook" ]] || continue
        "$hook" 2>/dev/null || true
    done
}

# Registered at sourcing time so a SIGINT mid-cmd_start (between
# lock_dir mkdir and the metadata-write that follows) cannot strand
# the lock on disk (m7su R5 finding #5).
trap _demo_cleanup EXIT

# ---------------------------------------------------------------------------
# Start-lock cleanup hook
# ---------------------------------------------------------------------------
#
# Removes the lock dir only if WE own it: the recorded PID matches, or
# we were mid-establish and there is no pid file yet. Mid-establish with
# a pid file present means we lost the pid create (or are about to), and
# the lock is theirs (opensrm-s41c). That holds for an EMPTY pid file
# too: the winner's noclobber create makes the file and then writes it,
# so empty means "created, not yet written", not "no holder"
# (opensrm-1c0f).
#
# The cost: if we are the winner and die between our own create and
# write, the lock is left with an empty pid, and the next start refuses
# it with the manual-cleanup hint rather than reclaiming.
#
# Prefers $BASHPID (bash 4+, unique per subshell) with $$ fallback
# (bash 3.2 default on macOS doesn't define BASHPID). In a top-level
# demo.sh process the two are equal; the BASHPID preference matters
# only when the lock is exercised inside a `( … )` subshell, e.g.
# from the test harness.

_DEMO_START_LOCK_DIR=""
# Flipped to 1 by _acquire_start_lock before the mkdir, then back
# to 0 once pid and owner are written (or the acquire is lost). If
# the EXIT trap fires while this is 1 and the lock dir has no pid
# file, the cleanup hook treats the half-built lock dir as ours and
# rms it — fixes the SIGINT-mid-setup orphan (m7su R5 #5).
_DEMO_START_LOCK_ESTABLISHING=0

_demo_cleanup_start_lock() {
    [[ -n "$_DEMO_START_LOCK_DIR" ]] || return 0
    [[ -d "$_DEMO_START_LOCK_DIR" ]] || return 0
    local recorded_pid
    recorded_pid="$(cat "$_DEMO_START_LOCK_DIR/pid" 2>/dev/null || true)"
    if [[ "$recorded_pid" == "${BASHPID:-$$}" ]] \
       || { [[ "$_DEMO_START_LOCK_ESTABLISHING" == "1" ]] \
            && [[ ! -e "$_DEMO_START_LOCK_DIR/pid" ]]; }; then
        rm -rf "$_DEMO_START_LOCK_DIR" 2>/dev/null || true
    fi
}

# ---------------------------------------------------------------------------
# Atomic acquire primitive
# ---------------------------------------------------------------------------
#
# Two steps, and the second one is the mutex (opensrm-s41c):
#
#   1. mkdir the lock dir. A failure means contended. A success does
#      NOT mean we hold the lock: uutils mkdir (Ubuntu 26.04) checks
#      for the path first and then reports a failed create as success
#      when the path is a directory, so several racers can all be told
#      their mkdir succeeded. CI saw 3 winners of 20 that way.
#   2. Create the pid file under noclobber. bash opens a missing file
#      with O_CREAT|O_EXCL itself, no external binary involved, so
#      exactly one racer gets past this line.
#
# The owner file is written immediately after — a concurrent reader
# that arrives in the small window between the pid create and the
# owner echo uses _read_lock_state below to poll for the metadata
# before making a stale-lock decision.
#
# The noclobber create runs in a subshell so the option does not leak
# into the caller, which is why the pid is read before it: BASHPID
# inside the subshell would be the subshell's.
#
# Returns: 0 on acquire, 1 on contended.

_acquire_start_lock() {
    local lock_dir="$1"
    local holder_pid="${BASHPID:-$$}"
    _DEMO_START_LOCK_ESTABLISHING=1
    if ! mkdir "$lock_dir" 2>/dev/null; then
        _DEMO_START_LOCK_ESTABLISHING=0
        return 1
    fi
    if ! ( set -o noclobber; echo "$holder_pid" > "$lock_dir/pid" ) 2>/dev/null; then
        _DEMO_START_LOCK_ESTABLISHING=0
        return 1
    fi
    echo "demo.sh-start-lock" > "$lock_dir/owner"
    _DEMO_START_LOCK_ESTABLISHING=0
    return 0
}

# ---------------------------------------------------------------------------
# Compare-and-rm stale lock (concurrent-reclaim race defense)
# ---------------------------------------------------------------------------
#
# Re-reads $lock_dir/pid right before the rm. Rms only if the
# recorded pid still matches the value the caller observed when it
# decided "stale". If two reclaimers both decide stale at the same
# time, the slower one's compare-pid check will see the faster one's
# fresh-holder pid and refuse the rm — preventing the slower
# reclaimer from destroying a fresh live lock (36es R5 Pass 3).
#
# An empty expected pid names no stale holder, so nothing is removed
# (opensrm-1c0f). cmd_start passes one when the lock dir was gone at
# its check; a lock dir that has appeared since belongs to a fresh
# holder whose pid file is missing or not yet written, and
# empty-equals-empty would remove it.
#
# The remaining window between this cat-and-if and the rm is
# microseconds; not zero, but small enough to swallow without a
# heavier primitive. Returns 0 always; the rm is best-effort.

_compare_and_rm_stale_lock() {
    local lock_dir="$1"
    local expected_stale_pid="$2"
    local current_pid_now
    [[ -n "$expected_stale_pid" ]] || return 0
    current_pid_now="$(cat "$lock_dir/pid" 2>/dev/null || true)"
    if [[ "$current_pid_now" == "$expected_stale_pid" ]]; then
        rm -rf "$lock_dir"
    fi
}

# ---------------------------------------------------------------------------
# Read lock state with metadata-establish tolerance
# ---------------------------------------------------------------------------
#
# Sets _LOCK_PID and _LOCK_OWNER globals from $lock_dir/pid and
# $lock_dir/owner. Tolerates the brief window after mkdir but before
# the establishing holder finishes the echos (m7su R5 #2): polls up
# to ~200ms before giving up and returning whatever's on disk
# (empty if the establisher died mid-write — caller treats as stale).

_LOCK_PID=""
_LOCK_OWNER=""

_read_lock_state() {
    local lock_dir="$1"
    local pid_file="$lock_dir/pid"
    local owner_file="$lock_dir/owner"
    local attempt
    _LOCK_PID=""
    _LOCK_OWNER=""
    for attempt in 1 2 3 4 5 6 7 8 9 10; do
        if [[ -s "$pid_file" ]] && [[ -s "$owner_file" ]]; then
            break
        fi
        sleep 0.02
    done
    _LOCK_PID="$(cat "$pid_file" 2>/dev/null || true)"
    _LOCK_OWNER="$(cat "$owner_file" 2>/dev/null || true)"
}
