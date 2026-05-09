#!/usr/bin/env bash
# _three_tier_lib.sh — shared boot/teardown helpers for the three-tier test scripts.
#
# Sourced by:
#   - test/integration-three-tier.sh  (P5.1 acceptance test)
#   - test/e2e-test.sh                (P5.2 9-step walk-through)
#
# Goal: keep the boot/teardown boilerplate that both scripts share in one
# place. When a fix lands (new pre-flight check, changed Prometheus
# readiness deadline, debug-log preservation policy) it lands once.
#
# Origin: opensrm-saun.2.1. Discovered during the saun.2 R5 review when
# both scripts had ~70 lines of near-identical pre-flight + boot + trap
# code. Extraction surfaced two minor inconsistencies (e2e disarmed the
# trap to avoid recursive teardown, integration-three-tier did not;
# integration-three-tier emitted known-blocker text on failure, e2e did
# not). The library normalises on the e2e behaviour for trap disarm and
# leaves the known-blocker text to each caller via a `tt_known_blockers`
# pre-trap hook.
#
# Contract:
#   - The library does NOT set `set -euo pipefail` — that's the caller's
#     concern. We assume the caller ran `set -euo pipefail` before
#     sourcing.
#   - Functions communicate via documented globals (CORE_PID, WORKERS_PID,
#     FAKE_PID, DOCKER_UP) so the trap function can clean up regardless of
#     where in the boot sequence the failure happened.
#   - All stdout/stderr writes use `printf` (no `echo -e` portability
#     trap on macOS); colour and emoji are the caller's choice.

# ---------------------------------------------------------------------------
# Output helpers (intentionally minimal — callers can override)
# ---------------------------------------------------------------------------

# Callers that want richer output (per-step logging, fancy colours) should
# define their own `tt_log` / `tt_info` / `tt_pass` / `tt_fail` BEFORE
# sourcing this library. The fallbacks below are plain ASCII.
type tt_log  >/dev/null 2>&1 || tt_log()  { printf '\n=== %s ===\n' "$*"; }
type tt_info >/dev/null 2>&1 || tt_info() { printf '  %s\n' "$*"; }
type tt_pass >/dev/null 2>&1 || tt_pass() { printf '  ✓ %s\n' "$*"; }
type tt_fail >/dev/null 2>&1 || tt_fail() { printf '  ✗ FAIL: %s\n' "$*" >&2; exit 1; }

# ---------------------------------------------------------------------------
# Globals shared with the caller
# ---------------------------------------------------------------------------

# These are intentionally exposed (not local) so the teardown trap can
# read them from any process state without the caller having to thread
# them through. Callers should declare them as empty strings before
# sourcing or before the first boot call.
CORE_PID="${CORE_PID:-}"
WORKERS_PID="${WORKERS_PID:-}"
FAKE_PID="${FAKE_PID:-}"
DOCKER_UP="${DOCKER_UP:-false}"

# ---------------------------------------------------------------------------
# Pre-flight: required commands
# ---------------------------------------------------------------------------

# preflight_required_commands [extra_cmd ...]
#
# Verify the standard six commands the three-tier stack needs are on
# PATH. Callers can append extra commands as positional arguments.
# Exits non-zero via tt_fail if any are missing.
preflight_required_commands() {
    local cmd
    for cmd in docker uv curl python3 jq lsof "$@"; do
        command -v "${cmd}" >/dev/null 2>&1 \
            || tt_fail "missing required command: ${cmd}"
    done
}

# ---------------------------------------------------------------------------
# Pre-flight: TCP port conflict check
# ---------------------------------------------------------------------------

# preflight_port_conflicts CORE_PORT FAKE_PORT
#
# Exit cleanly with a clear error if either port is already bound on
# localhost. This surfaces EADDRINUSE up front rather than letting core
# or fake-service hang on the health-check loops with the real cause
# buried in the log file. Skips Prometheus's 9090 — that's inside Docker
# and the binding race is handled by the docker compose health poll.
preflight_port_conflicts() {
    local core_port="$1"
    local fake_port="$2"
    local port_pair name port
    for port_pair in "core:${core_port}" "fake-service:${fake_port}"; do
        name="${port_pair%%:*}"
        port="${port_pair##*:}"
        if lsof -nP -iTCP:"${port}" -sTCP:LISTEN >/dev/null 2>&1; then
            tt_fail "port ${port} (${name}) is already in use — free it before running this script"
        fi
    done
}

# ---------------------------------------------------------------------------
# Boot
# ---------------------------------------------------------------------------

# boot_three_tier_stack WORK_DIR TEST_DIR SPECS_DIR \
#                       CORE_PORT FAKE_PORT CORE_URL PROMETHEUS_URL \
#                       RUN_CORE RUN_WORKERS RUN_BENCH ASSERTIONS \
#                       [INSTANCE_ID]
#
# Brings up the full stack:
#   1. docker compose up -d prometheus → poll /-/ready (60s deadline).
#   2. fake-service.py for fraud-detect → poll /health (15s deadline).
#   3. nthlayer serve (core) on CORE_PORT → poll /health (30s deadline)
#      and sanity-check /manifests returns ≥1.
#   4. nthlayer-workers serve with NTHLAYER_LLM_STUB=canned and 5s cycles
#      → wait for first heartbeat via three_tier_assertions.py (30s).
#
# Sets the globals CORE_PID / WORKERS_PID / FAKE_PID / DOCKER_UP so the
# teardown trap can clean up regardless of which step failed.
#
# Argument names mirror the variables both consumer scripts already
# define; positional rather than keyword so this works on bash 3.2
# (macOS default) without associative arrays.
boot_three_tier_stack() {
    local work_dir="$1"
    local test_dir="$2"
    local specs_dir="$3"
    local core_port="$4"
    local fake_port="$5"
    local core_url="$6"
    local prometheus_url="$7"
    local run_core="$8"
    local run_workers="$9"
    local run_bench="${10}"
    local assertions="${11}"
    local instance_id="${12:-three-tier}"

    local state_db="${work_dir}/state.db"
    local deadline

    tt_log "Bring up Docker (Prometheus only)"
    (cd "${test_dir}" && docker compose up -d prometheus >/dev/null)
    DOCKER_UP="true"

    deadline=$(( $(date +%s) + 60 ))
    until curl -fsS "${prometheus_url}/-/ready" >/dev/null 2>&1; do
        [[ $(date +%s) -lt ${deadline} ]] || tt_fail "Prometheus did not become ready in 60s"
        sleep 1
    done
    tt_pass "Prometheus ready"

    tt_log "Start fake-service (fraud-detect on ${fake_port})"
    python3 "${test_dir}/fake-service.py" --name fraud-detect --type ai-gate --port "${fake_port}" \
        >"${work_dir}/fake.log" 2>&1 &
    FAKE_PID=$!
    deadline=$(( $(date +%s) + 15 ))
    until curl -fsS "http://localhost:${fake_port}/health" >/dev/null 2>&1; do
        [[ $(date +%s) -lt ${deadline} ]] || tt_fail "fake-service did not start in 15s; see ${work_dir}/fake.log"
        sleep 0.5
    done
    tt_pass "fake-service ready (pid ${FAKE_PID})"

    tt_log "Start nthlayer-core on ${core_port}"
    NTHLAYER_STORE_PATH="${state_db}" \
    NTHLAYER_MANIFESTS_DIR="${specs_dir}" \
    ${run_core} nthlayer serve --host 127.0.0.1 --port "${core_port}" \
        >"${work_dir}/core.log" 2>&1 &
    CORE_PID=$!
    deadline=$(( $(date +%s) + 30 ))
    until curl -fsS "${core_url}/health" >/dev/null 2>&1; do
        [[ $(date +%s) -lt ${deadline} ]] || tt_fail "core did not become healthy in 30s; see ${work_dir}/core.log"
        sleep 0.5
    done
    tt_pass "core ready (pid ${CORE_PID})"

    local manifest_count
    manifest_count=$(curl -fsS "${core_url}/manifests" | jq 'length')
    [[ "${manifest_count}" -ge 1 ]] || tt_fail "core /manifests returned ${manifest_count} manifests (expected ≥1)"
    tt_pass "core has loaded ${manifest_count} manifests from ${specs_dir}"

    tt_log "Start nthlayer-workers (NTHLAYER_LLM_STUB=canned, all intervals 5s)"
    NTHLAYER_LLM_STUB=canned \
    ${run_workers} nthlayer-workers serve \
        --core-url "${core_url}" \
        --instance-id "${instance_id}" \
        --prometheus-url "${prometheus_url}" \
        --collect-interval 5 \
        --measure-interval 5 \
        --correlate-interval 5 \
        --respond-interval 5 \
        --retrospective-interval 5 \
        --outcome-interval 10 \
        >"${work_dir}/workers.log" 2>&1 &
    WORKERS_PID=$!

    tt_log "Wait for first worker heartbeat"
    ${run_bench} python "${assertions}" wait-heartbeat \
        --core-url "${core_url}" --timeout 30 --interval 1 >/dev/null \
        || tt_fail "no heartbeat in 30s; see ${work_dir}/workers.log"
    tt_pass "workers ready (pid ${WORKERS_PID})"
}

# ---------------------------------------------------------------------------
# Teardown
# ---------------------------------------------------------------------------

# teardown_three_tier_stack WORK_DIR TEST_DIR FAKE_PORT \
#                           SAVE_PREFIX [SUCCESS_MESSAGE] [PRESERVE_FILE_FN]
#
# Trap handler. Reads the global CORE_PID / WORKERS_PID / FAKE_PID /
# DOCKER_UP and the caller-provided exit code (via $? captured at the
# top of the wrapper), then:
#   1. disarms INT/TERM to prevent recursive teardown if a signal
#      arrives during cleanup,
#   2. best-effort POST /reset to fake-service (idempotent, safe to skip
#      when fake-service is already down),
#   3. SIGTERMs workers → core → fake-service in that order, waiting on
#      each so reaped pids don't pollute jobs(),
#   4. brings docker compose down with --remove-orphans,
#   5. on success: removes WORK_DIR and prints SUCCESS_MESSAGE if given;
#      on failure: moves WORK_DIR to /tmp/${SAVE_PREFIX}-debug-<ts> so
#      the operator can read core.log / workers.log / fake.log post-mortem.
#
# Callers should call this from their trap function with the captured
# exit code as the first positional after the standard set:
#
#     teardown() {
#         local rc=$?
#         teardown_three_tier_stack "${WORK_DIR}" "${TEST_DIR}" \
#             "${FAKE_PORT}" three-tier "${rc}"
#     }
#     trap teardown EXIT INT TERM
#
# Pass an extra success-message string if the caller wants something
# other than the default. For the integration script's known-blockers
# message, define a `tt_known_blockers` function — the helper calls it
# on failure with no arguments.
teardown_three_tier_stack() {
    local work_dir="$1"
    local test_dir="$2"
    local fake_port="$3"
    local save_prefix="$4"
    local exit_code="${5:-0}"
    local success_msg="${6:-}"

    # Disarm the trap to avoid recursive teardown if a SIGINT/SIGTERM
    # arrives during cleanup (otherwise the second invocation re-enters
    # `wait` on already-reaped PIDs and re-runs the work-dir mv).
    trap - INT TERM

    tt_log "Teardown"

    # Best-effort fake-service reset before stopping it. Errors (already
    # gone, port refused) are expected during partial-boot teardowns.
    curl -sf -X POST "http://localhost:${fake_port}/reset" >/dev/null 2>&1 || true

    if [[ -n "${WORKERS_PID}" ]]; then
        tt_info "stopping workers (pid ${WORKERS_PID})"
        kill -TERM "${WORKERS_PID}" 2>/dev/null || true
        wait "${WORKERS_PID}" 2>/dev/null || true
    fi
    if [[ -n "${CORE_PID}" ]]; then
        tt_info "stopping core (pid ${CORE_PID})"
        kill -TERM "${CORE_PID}" 2>/dev/null || true
        wait "${CORE_PID}" 2>/dev/null || true
    fi
    if [[ -n "${FAKE_PID}" ]]; then
        tt_info "stopping fake-service (pid ${FAKE_PID})"
        kill -TERM "${FAKE_PID}" 2>/dev/null || true
        wait "${FAKE_PID}" 2>/dev/null || true
    fi
    if [[ "${DOCKER_UP}" == "true" ]]; then
        tt_info "stopping docker compose stack"
        (cd "${test_dir}" && docker compose down --remove-orphans >/dev/null 2>&1) || true
    fi

    if [[ ${exit_code} -eq 0 ]]; then
        tt_info "removing work dir ${work_dir}"
        rm -rf "${work_dir}"
        if [[ -n "${success_msg}" ]]; then
            printf '\n%s\n' "${success_msg}"
        fi
    else
        local saved_dir="/tmp/${save_prefix}-debug-$(date +%s)"
        tt_info "preserving work dir for debug → ${saved_dir}"
        mv "${work_dir}" "${saved_dir}" 2>/dev/null || true
        printf '\nFAIL — exit %d. Logs preserved at %s\n' "${exit_code}" "${saved_dir}" >&2

        # Caller-supplied known-blockers note (optional) — keeps the
        # nightly CI failure informative while specific dependency bugs
        # are open. Drop the function definition once those are closed.
        if type tt_known_blockers >/dev/null 2>&1; then
            tt_known_blockers >&2
        fi
    fi
}
