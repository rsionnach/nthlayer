#!/usr/bin/env bash
# e2e-test.sh — End-to-end integration test (three-tier model).
#
# Tests the full NthLayer chain against a live Docker Prometheus stack:
#   real Prometheus metrics → measure → correlate → respond → learn retrospective
# All work happens inside the worker process; this script only triggers and
# observes via the core HTTP API.
#
# Updated for opensrm-saun.2 (P5.2): the legacy version invoked nthlayer-*
# CLI tools and queried SQLiteVerdictStore directly. The three-tier rewrite
# starts core + workers and observes via core's REST API.
#
# Sibling tests:
#   - test/integration-three-tier.sh — minimal CI smoke test (saun.1).
#     Same boot/teardown pattern; this script is the demo-flavoured 9-step
#     walk-through with per-step narrative output.
#
# Usage:
#   ./test/e2e-test.sh [--prometheus-url URL] [--specs-dir DIR]
#
# Acceptance (saun.2): 9 steps pass, total runtime < 5 min.

set -euo pipefail

# ---------------------------------------------------------------------------
# Defaults / argument parsing
# ---------------------------------------------------------------------------

ECOSYSTEM_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
TEST_DIR="${ECOSYSTEM_ROOT}/test"
PROMETHEUS_URL="${PROMETHEUS_URL:-http://localhost:9090}"
SPECS_DIR="${SPECS_DIR:-${ECOSYSTEM_ROOT}/demo/specs}"
CORE_PORT="${CORE_PORT:-8000}"
FAKE_PORT="${FAKE_PORT:-8001}"
CORE_URL="http://localhost:${CORE_PORT}"

while [[ $# -gt 0 ]]; do
    case "$1" in
        --prometheus-url) PROMETHEUS_URL="$2"; shift 2 ;;
        --specs-dir)      SPECS_DIR="$2";      shift 2 ;;
        *) echo "Unknown argument: $1" >&2; exit 1 ;;
    esac
done

WORK_DIR="$(mktemp -d -t e2e-XXXXXX)"
STATE_DB="${WORK_DIR}/e2e.db"
ASSERTIONS="${TEST_DIR}/three_tier_assertions.py"

RUN_CORE="uv run --directory ${ECOSYSTEM_ROOT}/nthlayer-core"
RUN_WORKERS="uv run --directory ${ECOSYSTEM_ROOT}/nthlayer-workers"
RUN_BENCH="uv run --directory ${ECOSYSTEM_ROOT}/nthlayer-bench"

CORE_PID=""
WORKERS_PID=""
FAKE_PID=""
DOCKER_UP="false"

STEP=0; PASSED=0; FAILED=0

log()  { echo -e "\n=== Step $STEP: $1 ==="; }
info() { printf '  %s\n' "$*"; }
pass() { echo "  ✓ PASS"; PASSED=$((PASSED + 1)); }
fail() { echo "  ✗ FAIL: $1" >&2; FAILED=$((FAILED + 1)); }

# Adapter helpers for the shared boot/teardown library (opensrm-saun.2.1).
# The lib's tt_log/tt_info/tt_pass/tt_fail names sidestep e2e's step
# counters (which are tied to its 9-step narrative) and emit plain log
# lines for the boot/teardown phases.
tt_log()  { printf '\n=== %s ===\n' "$*"; }
tt_info() { printf '  %s\n' "$*"; }
tt_pass() { printf '  ✓ %s\n' "$*"; }
tt_fail() { printf '  ✗ FAIL: %s\n' "$*" >&2; exit 1; }

# Source the shared library AFTER tt_* are defined so the lib picks them up.
# shellcheck source=./_three_tier_lib.sh
source "$(dirname "$0")/_three_tier_lib.sh"

# Run a step function and capture pass/fail without aborting the script.
# A step body must call ``pass`` or ``fail`` before returning; if neither
# happens (or the body exits non-zero through a bare $(...) failure that
# bypasses the explicit guards) the wrapper accounts for it as a failure
# rather than a silent pass — keeps the summary tally honest.
run_step() {
    local step_num="$1"
    local step_desc="$2"
    local step_fn="$3"
    STEP="$step_num"
    log "$step_desc"
    local before_pass=${PASSED}
    local before_fail=${FAILED}
    set +e
    "$step_fn"
    local rc=$?
    set -e
    if [[ ${PASSED} -eq ${before_pass} && ${FAILED} -eq ${before_fail} ]]; then
        # Step body neither passed nor failed explicitly — record a failure
        # so the summary tally is honest.
        fail "step body returned without pass/fail (rc=${rc})"
    fi
}

# ---------------------------------------------------------------------------
# Teardown
# ---------------------------------------------------------------------------

teardown() {
    local exit_code=$?
    # Treat any failed step as a failure for log-preservation purposes,
    # even when the script exits 0 overall (the e2e summary may report
    # FAILED>0 without bubbling a non-zero exit). The library's
    # success-path branch only runs when exit_code == 0.
    if [[ ${FAILED} -gt 0 && ${exit_code} -eq 0 ]]; then
        exit_code=1
    fi
    teardown_three_tier_stack "${WORK_DIR}" "${TEST_DIR}" "${FAKE_PORT}" \
        e2e "${exit_code}"
}
trap teardown EXIT INT TERM

# ---------------------------------------------------------------------------
# Boot
# ---------------------------------------------------------------------------

boot_stack() {
    tt_log "Pre-flight"
    preflight_required_commands
    [[ -f "${ASSERTIONS}" ]] || tt_fail "assertions helper not found: ${ASSERTIONS}"
    [[ -d "${SPECS_DIR}" ]]  || tt_fail "specs dir not found: ${SPECS_DIR}"
    preflight_port_conflicts "${CORE_PORT}" "${FAKE_PORT}"

    boot_three_tier_stack \
        "${WORK_DIR}" "${TEST_DIR}" "${SPECS_DIR}" \
        "${CORE_PORT}" "${FAKE_PORT}" "${CORE_URL}" "${PROMETHEUS_URL}" \
        "${RUN_CORE}" "${RUN_WORKERS}" "${RUN_BENCH}" "${ASSERTIONS}" \
        "e2e-test"
}

# ---------------------------------------------------------------------------
# Step 1: baseline verification
# ---------------------------------------------------------------------------

step1() {
    info "Checking Prometheus at ${PROMETHEUS_URL} ..."
    if ! curl -fsS "${PROMETHEUS_URL}/-/healthy" >/dev/null 2>&1; then
        fail "Prometheus not reachable"; return
    fi
    info "Prometheus: healthy"

    info "Checking fake-service on localhost:${FAKE_PORT} ..."
    curl -fsS "http://localhost:${FAKE_PORT}/health" >/dev/null \
        || { fail "fake-service unreachable"; return; }
    info "Fake service: healthy"

    info "Checking core /health ..."
    curl -fsS "${CORE_URL}/health" >/dev/null \
        || { fail "core unreachable"; return; }
    info "Core: healthy"

    info "Verifying core has loaded manifests from ${SPECS_DIR} ..."
    local manifest_count
    manifest_count=$(curl -fsS "${CORE_URL}/manifests" | jq 'length')
    [[ "${manifest_count}" -ge 1 ]] || { fail "core has no manifests"; return; }
    info "Core: ${manifest_count} manifest(s) loaded"

    pass
}

# ---------------------------------------------------------------------------
# Step 2: Generate alert rules and reload Prometheus (best-effort)
# ---------------------------------------------------------------------------
#
# In v1.5 the legacy `nthlayer` generator is split into `nthlayer-generate`
# and the alerts referenced by tests are checked into test/rules/. Step 2
# preserves the legacy gesture (operators want the rules path exercised)
# but is best-effort: a failing or absent generator does not fail the test.

step2() {
    local rules_dir="${TEST_DIR}/rules"
    mkdir -p "${rules_dir}"

    if command -v nthlayer-generate >/dev/null 2>&1; then
        info "Running nthlayer-generate ..."
        if nthlayer-generate --specs-dir "${SPECS_DIR}" --output-dir "${rules_dir}" >"${WORK_DIR}/generate.out" 2>&1; then
            local count
            count=$(ls "${rules_dir}"/*.yml "${rules_dir}"/*.yaml 2>/dev/null | wc -l | tr -d ' ')
            info "Generated ${count} rule file(s)"
        else
            info "nthlayer-generate produced no output (non-fatal)"
        fi
    else
        info "nthlayer-generate not on PATH — skipping"
    fi

    info "Hot-reloading Prometheus ..."
    if curl -fsS -X POST "${PROMETHEUS_URL}/-/reload" >/dev/null 2>&1; then
        info "Prometheus reloaded"
    else
        info "Prometheus reload returned non-2xx (non-fatal)"
    fi

    pass
}

# ---------------------------------------------------------------------------
# Step 3: Degrade fraud-detect
# ---------------------------------------------------------------------------

step3() {
    info "Posting degradation params to localhost:${FAKE_PORT}/control ..."
    curl -fsS -X POST "http://localhost:${FAKE_PORT}/control" \
        -H "Content-Type: application/json" \
        -d '{"reversal_rate": 0.08, "rps": 100}' >"${WORK_DIR}/control.out" \
        || { fail "POST /control failed"; return; }
    info "Response: $(cat "${WORK_DIR}/control.out")"
    pass
}

# ---------------------------------------------------------------------------
# Step 4: Wait for measure to detect breach
# ---------------------------------------------------------------------------
#
# In the legacy script this ran nthlayer-measure evaluate-once x3 with
# hysteresis. The worker module already runs evaluate cycles every 5s; we
# just wait for the resulting quality_breach verdict to land in core.

QUALITY_BREACH_ID=""

step4() {
    # eval-pattern: the assertions helper prints `KEY=value` lines on
    # stdout (e.g. `VERDICT_ID=...`, `VERDICT_CREATED_AT=...`); eval'ing
    # them here surfaces them as bash globals for subsequent steps.
    local output
    output=$(${RUN_BENCH} python "${ASSERTIONS}" wait-verdict-type quality_breach \
        --service fraud-detect --core-url "${CORE_URL}" \
        --timeout 180 --interval 2) \
        || { fail "no quality_breach in 180s"; return; }
    eval "${output}"
    QUALITY_BREACH_ID="${VERDICT_ID}"
    [[ -n "${QUALITY_BREACH_ID}" ]] || { fail "empty quality_breach id"; return; }
    info "quality_breach: ${QUALITY_BREACH_ID} at ${VERDICT_CREATED_AT}"
    pass
}

# ---------------------------------------------------------------------------
# Step 5: Verify quality_breach details
# ---------------------------------------------------------------------------

step5() {
    [[ -n "${QUALITY_BREACH_ID}" ]] || { fail "QUALITY_BREACH_ID not set"; return; }
    info "Inspecting quality_breach via core API ..."
    local body
    body=$(curl -fsS "${CORE_URL}/verdicts/${QUALITY_BREACH_ID}")
    local svc
    svc=$(echo "${body}" | jq -r '.service')
    [[ "${svc}" == "fraud-detect" ]] || { fail "unexpected service: ${svc}"; return; }
    info "service: ${svc}"
    info "type:    $(echo "${body}" | jq -r '.type')"
    pass
}

# ---------------------------------------------------------------------------
# Step 6: Wait for correlate to produce snapshot
# ---------------------------------------------------------------------------

CORRELATION_SNAPSHOT_ID=""

step6() {
    local output
    output=$(${RUN_BENCH} python "${ASSERTIONS}" wait-assessment-kind correlation_snapshot \
        --core-url "${CORE_URL}" --timeout 60 --interval 1) \
        || { fail "no correlation_snapshot in 60s"; return; }
    eval "${output}"
    CORRELATION_SNAPSHOT_ID="${ASSESSMENT_ID}"
    [[ -n "${CORRELATION_SNAPSHOT_ID}" ]] || { fail "empty snapshot id"; return; }
    info "correlation_snapshot: ${CORRELATION_SNAPSHOT_ID}"
    pass
}

# ---------------------------------------------------------------------------
# Step 7: Wait for respond → triage + case
# ---------------------------------------------------------------------------

TRIAGE_ID=""
CASE_ID=""

step7() {
    local output
    output=$(${RUN_BENCH} python "${ASSERTIONS}" wait-verdict-type triage \
        --core-url "${CORE_URL}" --timeout 60 --interval 1) \
        || { fail "no triage verdict in 60s"; return; }
    eval "${output}"
    TRIAGE_ID="${VERDICT_ID}"
    info "triage verdict: ${TRIAGE_ID}"

    output=$(${RUN_BENCH} python "${ASSERTIONS}" wait-case \
        --service fraud-detect --core-url "${CORE_URL}" \
        --timeout 30 --interval 1) \
        || { fail "no case in 30s"; return; }
    eval "${output}"
    [[ -n "${CASE_ID}" ]] || { fail "empty case id"; return; }
    info "case: ${CASE_ID} priority=${CASE_PRIORITY}"

    info "Lineage check: triage ancestors must reach quality_breach"
    ${RUN_BENCH} python "${ASSERTIONS}" assert-lineage \
        "${TRIAGE_ID}" "${QUALITY_BREACH_ID}" --core-url "${CORE_URL}" >/dev/null \
        || { fail "lineage assertion failed"; return; }
    pass
}

# ---------------------------------------------------------------------------
# Step 8: Restore service
# ---------------------------------------------------------------------------

step8() {
    info "Posting reset to localhost:${FAKE_PORT}/reset ..."
    curl -fsS -X POST "http://localhost:${FAKE_PORT}/reset" >"${WORK_DIR}/reset.out" \
        || { fail "POST /reset failed"; return; }
    info "Response: $(cat "${WORK_DIR}/reset.out")"
    pass
}

# ---------------------------------------------------------------------------
# Step 9: Wait for retrospective + walk lineage
# ---------------------------------------------------------------------------

RETRO_ID=""

step9() {
    local output
    if output=$(${RUN_BENCH} python "${ASSERTIONS}" wait-assessment-kind retrospective \
        --core-url "${CORE_URL}" --timeout 60 --interval 2 2>/dev/null); then
        eval "${output}"
        RETRO_ID="${ASSESSMENT_ID}"
        info "retrospective: ${RETRO_ID}"
    else
        # Some learn cycles emit calibration_signal first; that's also acceptable
        # evidence learn ran. Fall back to that if no retrospective lands.
        info "no retrospective in 60s; trying calibration_signal as evidence learn ran ..."
        output=$(${RUN_BENCH} python "${ASSERTIONS}" wait-assessment-kind calibration_signal \
            --core-url "${CORE_URL}" --timeout 30 --interval 2) \
            || { fail "no learn assessment in fallback window"; return; }
        eval "${output}"
        info "calibration_signal: ${ASSESSMENT_ID}"
    fi

    info "Walking lineage from triage upward via core API ..."
    local ancestors
    ancestors=$(curl -fsS "${CORE_URL}/verdicts/${TRIAGE_ID}/ancestors" | jq -r '.[].id')
    if ! echo "${ancestors}" | grep -q "${QUALITY_BREACH_ID}"; then
        fail "triage ancestors do not include quality_breach"
        return
    fi
    info "Lineage chain types reachable from triage:"
    curl -fsS "${CORE_URL}/verdicts/${TRIAGE_ID}/ancestors" | jq -r '[.[].type] | unique | .[]' | sed 's/^/    /'

    pass
}

# ---------------------------------------------------------------------------
# Run all steps
# ---------------------------------------------------------------------------

boot_stack

run_step 1 "Verify baseline (Prometheus + fake-service + core healthy)" step1
run_step 2 "Generate alert rules and reload Prometheus (best-effort)"   step2
run_step 3 "Degrade fraud-detect (reversal_rate=0.08, rps=100)"         step3
run_step 4 "Wait for measure → quality_breach"                          step4
run_step 5 "Verify quality_breach details via core API"                 step5
run_step 6 "Wait for correlate → correlation_snapshot"                  step6
run_step 7 "Wait for respond → triage verdict + case"                   step7
run_step 8 "Restore fraud-detect to baseline"                           step8
run_step 9 "Wait for learn → retrospective and walk lineage"            step9

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------

echo -e "\n=============================="
echo "E2E Test Results"
echo "=============================="
echo "  Passed: ${PASSED} / $((PASSED + FAILED))"
echo "  Failed: ${FAILED}"

if [[ "${FAILED}" -gt 0 ]]; then
    echo "FAIL — E2E test did not pass." >&2
    exit 1
fi
echo "PASS — E2E integration test complete."
echo "Verdict chain: quality_breach → correlation_snapshot → triage → case → retrospective"
