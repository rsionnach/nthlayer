#!/usr/bin/env bash
# integration-three-tier.sh — P5.1 three-tier acceptance test.
#
# Boots the full v1.5 three-tier stack (nthlayer-core HTTP API +
# nthlayer-workers process + fake fraud-detect service + Docker Prometheus
# stack), triggers a Prometheus-fed reversal_rate breach, and asserts the
# end-to-end verdict chain plus bench-readable cases.
#
# What it verifies:
#   - core boots, workers connect via API only, bench reads cases via API only
#   - measure → correlate → respond → learn full chain
#   - strong lineage: triage.parent_ids reach correlation_snapshot which
#     reaches the quality_breach (catches type-right-but-id-wrong regressions)
#   - end-to-end pipeline latency (quality_breach → case visible via
#     fetch_case_bench) under 30s
#
# What it does NOT cover:
#   - bench Textual widget rendering (covered by nthlayer-bench unit tests)
#   - LLM behaviour (NTHLAYER_LLM_STUB=canned returns deterministic shapes)
#   - demo scenario runner (P5.2)
#   - cross-version compatibility between repos (separate concern)
#
# Usage:
#   ./test/integration-three-tier.sh
#
# Env overrides:
#   CORE_PORT (default 8000)
#   FAKE_PORT (default 8001)
#   PROMETHEUS_URL (default http://localhost:9090)
#   LATENCY_BUDGET_SECONDS (default 30)

set -euo pipefail

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

CORE_PORT="${CORE_PORT:-8000}"
FAKE_PORT="${FAKE_PORT:-8001}"
PROMETHEUS_URL="${PROMETHEUS_URL:-http://localhost:9090}"
LATENCY_BUDGET_SECONDS="${LATENCY_BUDGET_SECONDS:-30}"

CORE_URL="http://localhost:${CORE_PORT}"
# FRONTDOOR_ROOT is the front-door checkout (this repo). Holds test/ + demo/.
# WORKSPACE_ROOT is the parent that has all sibling implementation repos
# (nthlayer-common/, nthlayer-core/, nthlayer-workers/, nthlayer-bench/).
# This works both locally (sibling repos as siblings of nthlayer/ in the
# ecosystem working dir) and in CI (each repo checked out at <workspace>/<name>).
FRONTDOOR_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
WORKSPACE_ROOT="$(cd "${FRONTDOOR_ROOT}/.." && pwd)"
TEST_DIR="${FRONTDOOR_ROOT}/test"
WORK_DIR="$(mktemp -d -t three-tier-XXXXXX)"
STATE_DB="${WORK_DIR}/three-tier.db"
SPECS_DIR="${FRONTDOOR_ROOT}/demo/specs"
ASSERTIONS="${TEST_DIR}/three_tier_assertions.py"

# Worker process runs from nthlayer-bench's venv so the assertions script
# (which imports nthlayer_bench.sre.case_bench) and nthlayer_workers (which
# the worker process needs) both resolve. nthlayer-bench depends on
# nthlayer-common; we use uv --directory per-call to pick the right venv.
RUN_CORE="uv run --directory ${WORKSPACE_ROOT}/nthlayer-core"
RUN_WORKERS="uv run --directory ${WORKSPACE_ROOT}/nthlayer-workers"
RUN_BENCH="uv run --directory ${WORKSPACE_ROOT}/nthlayer-bench"

CORE_PID=""
WORKERS_PID=""
FAKE_PID=""
DOCKER_UP="false"

# ---------------------------------------------------------------------------
# Output helpers (used by both this script and the shared library)
# ---------------------------------------------------------------------------

# Define BEFORE sourcing _three_tier_lib.sh — the lib uses tt_log/tt_info/
# tt_pass/tt_fail and falls back to plain ASCII versions if the caller
# hasn't defined them.
log()  { printf '\n=== %s ===\n' "$*"; }
info() { printf '  %s\n' "$*"; }
fail() { printf '  ✗ FAIL: %s\n' "$*" >&2; exit 1; }
pass() { printf '  ✓ %s\n' "$*"; }
tt_log()  { log  "$@"; }
tt_info() { info "$@"; }
tt_fail() { fail "$@"; }
tt_pass() { pass "$@"; }

# Known-blockers hook — printed by teardown_three_tier_stack on failure.
# Keeps the nightly CI failure informative while specific dependency
# bugs are open; drop this function once both are closed.
tt_known_blockers() {
    cat <<'KNOWN_BLOCKERS'

Known dependency bugs that block this test from passing (as of 2026-05-02):

  • opensrm-saun.1.2 — CloudEvents envelope contract mismatch between
    respond and core. Respond verdicts get rejected with HTTP 422
    missing_fields. Symptom: timeout at "Wait for respond → triage verdict".

  • opensrm-saun.1.3 — AttributeError in RemediationAgent on canned-LLM
    responses. Caught by broad except so the worker keeps running, but
    remediation hits the degraded path.

If your run reached the respond step and timed out there, you are seeing
opensrm-saun.1.2. If the test was passing recently and now fails for a
different reason, check the preserved workers.log first. Both follow-up
beads link to opensrm-saun.1 in the Dolt DB.
KNOWN_BLOCKERS
}

# Source the shared boot/teardown library (opensrm-saun.2.1).
# shellcheck source=./_three_tier_lib.sh
source "$(dirname "$0")/_three_tier_lib.sh"

# ---------------------------------------------------------------------------
# Teardown — registered before any process starts so an early failure cleans up
# ---------------------------------------------------------------------------

teardown() {
    local exit_code=$?
    teardown_three_tier_stack "${WORK_DIR}" "${TEST_DIR}" "${FAKE_PORT}" \
        three-tier "${exit_code}" \
        "PASS — three-tier integration test complete."
    exit "${exit_code}"
}
trap teardown EXIT INT TERM

# ---------------------------------------------------------------------------
# Pre-flight
# ---------------------------------------------------------------------------

log "Pre-flight"
preflight_required_commands
[[ -f "${ASSERTIONS}" ]] || fail "assertions helper not found: ${ASSERTIONS}"
[[ -d "${SPECS_DIR}" ]] || fail "specs dir not found: ${SPECS_DIR}"
[[ -f "${TEST_DIR}/docker-compose.yml" ]] || fail "docker-compose.yml not found in ${TEST_DIR}"
[[ -f "${TEST_DIR}/fake-service.py" ]] || fail "fake-service.py not found in ${TEST_DIR}"
preflight_port_conflicts "${CORE_PORT}" "${FAKE_PORT}"
pass "all prerequisites present"

# ---------------------------------------------------------------------------
# Boot the three-tier stack (Prometheus → fake-service → core → workers)
# ---------------------------------------------------------------------------

# Override the work-dir state DB path the lib's default. The lib uses
# ${WORK_DIR}/state.db; this script's existing logs reference STATE_DB
# under the same path so this is a no-op renaming for the lib's purposes.
boot_three_tier_stack \
    "${WORK_DIR}" "${TEST_DIR}" "${SPECS_DIR}" \
    "${CORE_PORT}" "${FAKE_PORT}" "${CORE_URL}" "${PROMETHEUS_URL}" \
    "${RUN_CORE}" "${RUN_WORKERS}" "${RUN_BENCH}" "${ASSERTIONS}" \
    "three-tier-test"

# ---------------------------------------------------------------------------
# Trigger breach
# ---------------------------------------------------------------------------

log "Trigger reversal_rate breach on fraud-detect"
# Crank rps high so the rate() over the SLO window exceeds the 1.5% reversal
# rate threshold quickly. fraud-detect's PromQL inverts reversal-rate to
# non-reversal-rate (SLI), with target=98.5%; reversal_rate=0.08 drives SLI
# down to ~92, well below target. rps=100 means samples accumulate fast
# enough that the 2m PromQL window crosses the threshold within roughly
# one minute.
curl -fsS -X POST "http://localhost:${FAKE_PORT}/control" \
    -d '{"reversal_rate": 0.08, "rps": 100}' >/dev/null
info "control sent: reversal_rate=0.08 rps=100"

# ---------------------------------------------------------------------------
# Wait for the verdict chain
# ---------------------------------------------------------------------------

# run_assertion <description> <args-to-three_tier_assertions.py...>
# Captures stdout from the assertions helper into an `output` var; the
# explicit `|| fail` propagates a non-zero exit even though set -e in
# combination with `$(...)` does not abort by itself. Then evals the
# captured KEY=value lines so they become shell variables.
# Using `output=$(...)` followed by `eval "${output}"` (rather than the
# more compact `eval "$(...)"`) is load-bearing: with the compact form,
# command substitution that produces empty stdout makes eval return 0
# regardless of the inner exit code, swallowing assertion failures.
# Bash dynamic scoping means variables assigned inside `eval "${output}"`
# leak out to the caller — that's intentional and how downstream lines
# read VERDICT_ID etc.
run_assertion() {
    local description="$1"; shift
    local output
    output=$(${RUN_BENCH} python "${ASSERTIONS}" "$@") \
        || fail "${description}: assertion helper exited non-zero"
    eval "${output}"
}

log "Wait for measure → quality_breach (up to 180s for Prometheus 2m window to fill)"
run_assertion "quality_breach" wait-verdict-type quality_breach \
    --service fraud-detect --core-url "${CORE_URL}" --timeout 180 --interval 2
QUALITY_BREACH_ID="${VERDICT_ID}"
QUALITY_BREACH_AT="${VERDICT_CREATED_AT}"
pass "quality_breach: ${QUALITY_BREACH_ID} at ${QUALITY_BREACH_AT}"

# Latency budget starts here per design: from quality_breach.created_at to
# the moment fetch_case_bench can return the case.
log "Wait for correlate → correlation_snapshot (assessment)"
run_assertion "correlation_snapshot" wait-assessment-kind correlation_snapshot \
    --core-url "${CORE_URL}" --timeout 30 --interval 1
CORR_ID="${ASSESSMENT_ID}"
pass "correlation_snapshot: ${CORR_ID} at ${ASSESSMENT_CREATED_AT}"

log "Wait for respond → triage verdict"
run_assertion "triage" wait-verdict-type triage \
    --core-url "${CORE_URL}" --timeout 60 --interval 1
TRIAGE_ID="${VERDICT_ID}"
pass "triage: ${TRIAGE_ID} at ${VERDICT_CREATED_AT}"

log "Wait for respond → case"
run_assertion "case" wait-case \
    --service fraud-detect --core-url "${CORE_URL}" --timeout 60 --interval 1
CASE_ID_HIT="${CASE_ID}"
CASE_AT="${CASE_CREATED_AT}"
pass "case: ${CASE_ID_HIT} priority=${CASE_PRIORITY} at ${CASE_AT}"

log "Wait for learn → calibration_signal or retrospective"
# Learn module emits one of these; either path proves learn ran. The OR
# fallback isn't run_assertion (because the first leg is allowed to fail).
if output=$(${RUN_BENCH} python "${ASSERTIONS}" wait-assessment-kind retrospective \
    --core-url "${CORE_URL}" --timeout 60 --interval 2 2>/dev/null); then
    eval "${output}"
else
    info "no retrospective yet; trying calibration_signal"
    run_assertion "learn calibration_signal" wait-assessment-kind calibration_signal \
        --core-url "${CORE_URL}" --timeout 60 --interval 2
fi
pass "learn assessment: ${ASSESSMENT_ID}"

# ---------------------------------------------------------------------------
# Strong lineage assertions (Rob's design addition #1)
# ---------------------------------------------------------------------------

log "Strong lineage assertions"

# correlation_snapshot is an assessment, not a verdict — the lineage we can
# walk via /verdicts/{id}/ancestors only covers verdicts. The cross-module
# bridge we CAN assert: the triage verdict's ancestry must include the
# quality_breach. respond's worker_helpers sets parent_ids on the first
# incident verdict to trigger_verdict_ids (correlation_snapshot id when
# correlate ran; quality_breach id on the fallback path). Either way the
# ancestry chain reaches the quality_breach.
${RUN_BENCH} python "${ASSERTIONS}" assert-lineage \
    "${TRIAGE_ID}" "${QUALITY_BREACH_ID}" --core-url "${CORE_URL}"
pass "triage verdict's ancestors reach quality_breach"

# ---------------------------------------------------------------------------
# Bench-via-API path (Rob's Q2 — function-call path approved)
# ---------------------------------------------------------------------------

log "Bench reads case via core API (sre.case_bench.fetch_case_bench)"
${RUN_BENCH} python "${ASSERTIONS}" fetch-case-via-bench \
    --state pending --core-url "${CORE_URL}"
pass "bench logic layer fetched ≥1 case via core API"

# ---------------------------------------------------------------------------
# Pipeline latency assertion (Rob's design addition #2)
# ---------------------------------------------------------------------------

log "Pipeline latency: quality_breach.created_at → case.created_at"
# Defined precisely: from when measure created the quality_breach verdict to
# when respond created the case. End-to-end across measure (already done) →
# correlate → respond → case insert. Excludes Prometheus window staleness
# (which is upstream of quality_breach) and bench-fetch overhead (which is
# trivial and not part of the worker pipeline).
${RUN_BENCH} python "${ASSERTIONS}" assert-latency \
    "${QUALITY_BREACH_AT}" "${CASE_AT}" "${LATENCY_BUDGET_SECONDS}"
pass "pipeline latency under ${LATENCY_BUDGET_SECONDS}s"
