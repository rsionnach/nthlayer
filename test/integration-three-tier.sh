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
# Output helpers
# ---------------------------------------------------------------------------

log()  { printf '\n=== %s ===\n' "$*"; }
info() { printf '  %s\n' "$*"; }
fail() { printf '  ✗ FAIL: %s\n' "$*" >&2; exit 1; }
pass() { printf '  ✓ %s\n' "$*"; }

# ---------------------------------------------------------------------------
# Teardown — registered before any process starts so an early failure cleans up
# ---------------------------------------------------------------------------

teardown() {
    local exit_code=$?
    log "Teardown"
    if [[ -n "${WORKERS_PID}" ]]; then
        info "stopping workers (pid ${WORKERS_PID})"
        kill -TERM "${WORKERS_PID}" 2>/dev/null || true
        wait "${WORKERS_PID}" 2>/dev/null || true
    fi
    if [[ -n "${CORE_PID}" ]]; then
        info "stopping core (pid ${CORE_PID})"
        kill -TERM "${CORE_PID}" 2>/dev/null || true
        wait "${CORE_PID}" 2>/dev/null || true
    fi
    if [[ -n "${FAKE_PID}" ]]; then
        info "stopping fake-service (pid ${FAKE_PID})"
        kill -TERM "${FAKE_PID}" 2>/dev/null || true
        wait "${FAKE_PID}" 2>/dev/null || true
    fi
    if [[ "${DOCKER_UP}" == "true" ]]; then
        info "stopping docker compose stack"
        (cd "${TEST_DIR}" && docker compose down --remove-orphans >/dev/null 2>&1) || true
    fi
    if [[ ${exit_code} -eq 0 ]]; then
        info "removing work dir ${WORK_DIR}"
        rm -rf "${WORK_DIR}"
        printf '\nPASS — three-tier integration test complete.\n'
    else
        # Preserve logs on failure for diagnosis. The work dir contains
        # core.log, workers.log, fake.log + the SQLite store snapshot.
        local saved_dir="/tmp/three-tier-debug-$(date +%s)"
        info "preserving work dir for debug → ${saved_dir}"
        mv "${WORK_DIR}" "${saved_dir}" 2>/dev/null || true
        printf '\nFAIL — three-tier integration test failed (exit %d).\n' "${exit_code}" >&2
        printf 'Logs preserved at %s\n' "${saved_dir}" >&2
        # Known-blockers note: keeps the nightly CI failure informative
        # while these dependency bugs are open. Drop this block once both
        # are closed.
        cat >&2 <<'KNOWN_BLOCKERS'

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
    fi
    exit "${exit_code}"
}
trap teardown EXIT INT TERM

# ---------------------------------------------------------------------------
# Pre-flight
# ---------------------------------------------------------------------------

log "Pre-flight"
for cmd in docker uv curl python3 jq lsof; do
    command -v "${cmd}" >/dev/null 2>&1 || fail "missing required command: ${cmd}"
done
[[ -f "${ASSERTIONS}" ]] || fail "assertions helper not found: ${ASSERTIONS}"
[[ -d "${SPECS_DIR}" ]] || fail "specs dir not found: ${SPECS_DIR}"
[[ -f "${TEST_DIR}/docker-compose.yml" ]] || fail "docker-compose.yml not found in ${TEST_DIR}"
[[ -f "${TEST_DIR}/fake-service.py" ]] || fail "fake-service.py not found in ${TEST_DIR}"

# Port conflict check: surfaces EADDRINUSE up front instead of letting
# core/fake-service hang on the health-check loops with the real cause
# buried in the log file. Skip 9090 — that's Prometheus inside Docker, the
# binding race is handled by the docker compose health poll later.
for port_pair in "core:${CORE_PORT}" "fake-service:${FAKE_PORT}"; do
    name="${port_pair%%:*}"
    port="${port_pair##*:}"
    if lsof -nP -iTCP:"${port}" -sTCP:LISTEN >/dev/null 2>&1; then
        fail "port ${port} (${name}) is already in use — free it before running this test"
    fi
done

pass "all prerequisites present"

# ---------------------------------------------------------------------------
# Boot Prometheus stack
# ---------------------------------------------------------------------------

log "Bring up Docker (Prometheus only — test doesn't query Grafana/AlertManager)"
# Selective up: the test reads from Prometheus directly. Grafana provisioning
# has a flaky file-mount on some Docker Desktop setups, and AlertManager
# isn't queried by any assertion. Bring up just Prometheus to minimise blast
# radius. Teardown still runs the full `down` so we don't leave orphans.
(cd "${TEST_DIR}" && docker compose up -d prometheus >/dev/null)
DOCKER_UP="true"

# Poll Prometheus /-/ready
deadline=$(( $(date +%s) + 60 ))
until curl -fsS "${PROMETHEUS_URL}/-/ready" >/dev/null 2>&1; do
    [[ $(date +%s) -lt ${deadline} ]] || fail "Prometheus did not become ready in 60s"
    sleep 1
done
pass "Prometheus ready"

# ---------------------------------------------------------------------------
# Start fake-service
# ---------------------------------------------------------------------------

log "Start fake-service (fraud-detect on ${FAKE_PORT})"
python3 "${TEST_DIR}/fake-service.py" --name fraud-detect --type ai-gate --port "${FAKE_PORT}" \
    >"${WORK_DIR}/fake.log" 2>&1 &
FAKE_PID=$!

deadline=$(( $(date +%s) + 15 ))
until curl -fsS "http://localhost:${FAKE_PORT}/health" >/dev/null 2>&1; do
    [[ $(date +%s) -lt ${deadline} ]] || fail "fake-service did not start in 15s; see ${WORK_DIR}/fake.log"
    sleep 0.5
done
pass "fake-service ready (pid ${FAKE_PID})"

# ---------------------------------------------------------------------------
# Start nthlayer-core
# ---------------------------------------------------------------------------

log "Start nthlayer-core on ${CORE_PORT}"
NTHLAYER_STORE_PATH="${STATE_DB}" \
NTHLAYER_MANIFESTS_DIR="${SPECS_DIR}" \
${RUN_CORE} nthlayer serve --host 127.0.0.1 --port "${CORE_PORT}" \
    >"${WORK_DIR}/core.log" 2>&1 &
CORE_PID=$!

deadline=$(( $(date +%s) + 30 ))
until curl -fsS "${CORE_URL}/health" >/dev/null 2>&1; do
    [[ $(date +%s) -lt ${deadline} ]] || fail "core did not become healthy in 30s; see ${WORK_DIR}/core.log"
    sleep 0.5
done
pass "core ready (pid ${CORE_PID})"

# Sanity check manifests are loaded
manifest_count=$(curl -fsS "${CORE_URL}/manifests" | jq 'length')
[[ "${manifest_count}" -ge 1 ]] || fail "core /manifests returned ${manifest_count} manifests (expected ≥1)"
pass "core has loaded ${manifest_count} manifests from ${SPECS_DIR}"

# ---------------------------------------------------------------------------
# Start nthlayer-workers (with LLM stub)
# ---------------------------------------------------------------------------

log "Start nthlayer-workers (NTHLAYER_LLM_STUB=canned, all intervals 5s)"
NTHLAYER_LLM_STUB=canned \
${RUN_WORKERS} nthlayer-workers serve \
    --core-url "${CORE_URL}" \
    --instance-id "three-tier-test" \
    --prometheus-url "${PROMETHEUS_URL}" \
    --collect-interval 5 \
    --measure-interval 5 \
    --correlate-interval 5 \
    --respond-interval 5 \
    >"${WORK_DIR}/workers.log" 2>&1 &
WORKERS_PID=$!

# Wait for at least one heartbeat to land in core. We don't filter by
# component — any registered worker module heartbeating proves the worker
# process can talk to core.
log "Wait for first worker heartbeat"
${RUN_BENCH} python "${ASSERTIONS}" wait-heartbeat \
    --core-url "${CORE_URL}" --timeout 30 --interval 1
pass "workers heartbeating into core"

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
