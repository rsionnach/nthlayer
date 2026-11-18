#!/usr/bin/env bash
# integration-thresholds.sh — judgment thresholds end to end (opensrm-x0r9).
#
# core serves a manifest's judgment_threshold through GET /manifests, the
# workers' measure loop evaluates it (opensrm-g32d) against a gauge Prometheus
# really scraped, and the result lands on core's API. Follow-up to g32d's
# spec section 2.
#
# Boot: the shared three-tier stack (_three_tier_lib.sh: Prometheus + OTel
# Collector, fake-service, core, workers), with core reading
# test/fixtures/thresholds/specs instead of demo/specs, plus one extra
# process: a static exposition (test/fixtures/thresholds/exposition/metrics)
# on EXPOSITION_PORT, one of the host.docker.internal ports
# test/prometheus.yml's fake-services job scrapes. fake-service (fraud-detect)
# is part of the shared boot; no manifest here names it.
#
# Two ai-gate manifests, shape from opensrm spec/v2/examples/
# judgment-thresholds/calibration-both-bounds.yaml (CORE-v2 section 5.5.3):
#   calibration-breach-gate  ECE 0.12 > 0.03 (breach), Brier 0.02 <= 0.05
#   calibration-within-gate  both within: the negative control
#
# Asserts, from core's HTTP API only:
#   1. a judgment_threshold_evaluation for calibration-breach-gate whose
#      maximum_expected_calibration_error row is breach, measured 0.12;
#   2. a quality_breach for it with data.threshold_type calibration,
#      severity high, breaching_bounds naming exactly that bound (Brier is
#      within), a summary naming it, and parent_ids naming a breaching
#      evaluation of the same threshold_key;
#   3. a within evaluation for calibration-within-gate (ECE 0.01), and no
#      quality_breach for that service.
#
# The gauges are gen_ai_calibration_ece / gen_ai_calibration_brier, what
# nthlayer-common's THRESHOLD_SERIES (and so workers) reads today. Addendum
# A1 section 4.5 renames them to nthlayer_calibration_*; moving to that name
# is future work in common and workers, and this fixture follows them.
#
# Workers run with MEASURE_THRESHOLD_INTERVAL=5 (default 900), so a first
# run that precedes the first scrape (not evaluable) is retried within
# seconds. MEASURE_THRESHOLD_AUTONOMY is left at its default (off): the
# quality_breach is emitted either way; the toggle only feeds governance.
#
# Usage:
#   ./test/integration-thresholds.sh
#
# Env overrides (defaults chosen not to collide with
# integration-three-tier.sh, so the two can run on one host; not beside the
# demo, which holds 8001-8008, the only ports prometheus.yml scrapes):
#   CORE_PORT (default 8100)
#   FAKE_PORT (default 8006; must be one prometheus.yml scrapes, 8001-8008)
#   EXPOSITION_PORT (default 8007; same constraint)
#   NTHLAYER_TEST_PROMETHEUS_PORT (default 9190)
#   NTHLAYER_TEST_OTLP_GRPC_PORT / _OTLP_HTTP_PORT / _OTEL_METRICS_PORT
#     (defaults 4417 / 4418 / 8989)
#   COMPOSE_PROJECT_NAME (default nthlayer-thresholds)
#   THRESHOLD_TIMEOUT_SECONDS (default 90)

set -euo pipefail

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

CORE_PORT="${CORE_PORT:-8100}"
FAKE_PORT="${FAKE_PORT:-8006}"
EXPOSITION_PORT="${EXPOSITION_PORT:-8007}"
THRESHOLD_TIMEOUT_SECONDS="${THRESHOLD_TIMEOUT_SECONDS:-90}"
export NTHLAYER_TEST_PROMETHEUS_PORT="${NTHLAYER_TEST_PROMETHEUS_PORT:-9190}"
export NTHLAYER_TEST_OTLP_GRPC_PORT="${NTHLAYER_TEST_OTLP_GRPC_PORT:-4417}"
export NTHLAYER_TEST_OTLP_HTTP_PORT="${NTHLAYER_TEST_OTLP_HTTP_PORT:-4418}"
export NTHLAYER_TEST_OTEL_METRICS_PORT="${NTHLAYER_TEST_OTEL_METRICS_PORT:-8989}"
# docker compose reads this for up and for the teardown's down alike.
export COMPOSE_PROJECT_NAME="${COMPOSE_PROJECT_NAME:-nthlayer-thresholds}"
# Read by MeasureModule at construction (nthlayer-workers measure/worker.py).
export MEASURE_THRESHOLD_INTERVAL=5
unset MEASURE_THRESHOLD_AUTONOMY

PROMETHEUS_URL="http://localhost:${NTHLAYER_TEST_PROMETHEUS_PORT}"
CORE_URL="http://localhost:${CORE_PORT}"
FRONTDOOR_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
WORKSPACE_ROOT="$(cd "${FRONTDOOR_ROOT}/.." && pwd)"
TEST_DIR="${FRONTDOOR_ROOT}/test"
FIXTURES_DIR="${TEST_DIR}/fixtures/thresholds"
SPECS_DIR="${FIXTURES_DIR}/specs"
EXPOSITION_DIR="${FIXTURES_DIR}/exposition"
WORK_DIR="$(mktemp -d -t thresholds-XXXXXX)"
ASSERTIONS="${TEST_DIR}/three_tier_assertions.py"

RUN_CORE="uv run --directory ${WORKSPACE_ROOT}/nthlayer-core"
RUN_WORKERS="uv run --directory ${WORKSPACE_ROOT}/nthlayer-workers"
# The assertion helper needs only nthlayer_common (none of these subcommands
# imports nthlayer_bench), so it runs in the workers environment and this
# test needs no bench checkout.
RUN_ASSERT="${RUN_WORKERS}"

BREACH_SERVICE="calibration-breach-gate"
WITHIN_SERVICE="calibration-within-gate"
ECE_BOUND="maximum_expected_calibration_error"

CORE_PID=""
WORKERS_PID=""
FAKE_PID=""
EXPOSITION_PID=""
DOCKER_UP="false"

log()  { printf '\n=== %s ===\n' "$*"; }
info() { printf '  %s\n' "$*"; }
fail() { printf '  ✗ FAIL: %s\n' "$*" >&2; exit 1; }
pass() { printf '  ✓ %s\n' "$*"; }
tt_log()  { log  "$@"; }
tt_info() { info "$@"; }
tt_fail() { fail "$@"; }
tt_pass() { pass "$@"; }

# shellcheck source=./_three_tier_lib.sh
source "$(dirname "$0")/_three_tier_lib.sh"

teardown() {
    local exit_code=$?
    if [[ -n "${EXPOSITION_PID}" ]]; then
        kill -TERM "${EXPOSITION_PID}" 2>/dev/null || true
        wait "${EXPOSITION_PID}" 2>/dev/null || true
    fi
    teardown_three_tier_stack "${WORK_DIR}" "${TEST_DIR}" "${FAKE_PORT}" \
        thresholds "${exit_code}" \
        "PASS — judgment-threshold integration test complete."
    exit "${exit_code}"
}
trap teardown EXIT INT TERM

# ---------------------------------------------------------------------------
# Pre-flight
# ---------------------------------------------------------------------------

log "Pre-flight"
preflight_required_commands
[[ -f "${ASSERTIONS}" ]] || fail "assertions helper not found: ${ASSERTIONS}"
[[ -f "${EXPOSITION_DIR}/metrics" ]] || fail "exposition fixture not found: ${EXPOSITION_DIR}/metrics"
for f in "${BREACH_SERVICE}" "${WITHIN_SERVICE}"; do
    [[ -f "${SPECS_DIR}/${f}.yaml" ]] || fail "manifest fixture not found: ${SPECS_DIR}/${f}.yaml"
done
preflight_port_conflicts "${CORE_PORT}" "${FAKE_PORT}"
for port in "${EXPOSITION_PORT}" "${NTHLAYER_TEST_PROMETHEUS_PORT}" \
        "${NTHLAYER_TEST_OTLP_GRPC_PORT}" "${NTHLAYER_TEST_OTLP_HTTP_PORT}" \
        "${NTHLAYER_TEST_OTEL_METRICS_PORT}"; do
    if lsof -nP -iTCP:"${port}" -sTCP:LISTEN >/dev/null 2>&1; then
        fail "port ${port} is already in use — free it or override it (see header)"
    fi
done
pass "all prerequisites present"

# ---------------------------------------------------------------------------
# Exposition (before Prometheus, so its first scrape can already find it)
# ---------------------------------------------------------------------------

log "Serve the calibration exposition on ${EXPOSITION_PORT}"
# 0.0.0.0: Prometheus reaches it from Docker via host.docker.internal.
python3 -m http.server "${EXPOSITION_PORT}" --bind 0.0.0.0 --directory "${EXPOSITION_DIR}" \
    >"${WORK_DIR}/exposition.log" 2>&1 &
EXPOSITION_PID=$!
deadline=$(( $(date +%s) + 15 ))
until curl -fsS "http://localhost:${EXPOSITION_PORT}/metrics" >/dev/null 2>&1; do
    [[ $(date +%s) -lt ${deadline} ]] || fail "exposition did not serve in 15s; see ${WORK_DIR}/exposition.log"
    sleep 0.5
done
pass "exposition serving (pid ${EXPOSITION_PID})"

# ---------------------------------------------------------------------------
# Boot the shared stack (Prometheus → fake-service → core → workers)
# ---------------------------------------------------------------------------

boot_three_tier_stack \
    "${WORK_DIR}" "${TEST_DIR}" "${SPECS_DIR}" \
    "${CORE_PORT}" "${FAKE_PORT}" "${CORE_URL}" "${PROMETHEUS_URL}" \
    "${RUN_CORE}" "${RUN_WORKERS}" "${RUN_ASSERT}" "${ASSERTIONS}" \
    "thresholds-test"

served=$(curl -fsS "${CORE_URL}/manifests/${BREACH_SERVICE}" \
    | jq -cS '[.judgment_thresholds[] | select(.type == "calibration") | .bounds]')
[[ "${served}" == "[{\"maximum_brier_score\":0.05,\"${ECE_BOUND}\":0.03}]" ]] \
    || fail "core serves ${BREACH_SERVICE} calibration bounds ${served}, expected [{\"maximum_brier_score\":0.05,\"${ECE_BOUND}\":0.03}]"
pass "core serves ${BREACH_SERVICE}'s calibration threshold: ${served}"

# ---------------------------------------------------------------------------
# Assertions (core API only)
# ---------------------------------------------------------------------------

# Same two-step capture as integration-three-tier.sh: `eval "$(...)"` would
# swallow a non-zero exit when the helper prints nothing.
run_assertion() {
    local description="$1"; shift
    local output
    output=$(${RUN_ASSERT} python "${ASSERTIONS}" "$@") \
        || fail "${description}: assertion helper exited non-zero"
    eval "${output}"
}

log "Wait for a breaching ${ECE_BOUND} evaluation of ${BREACH_SERVICE}"
run_assertion "breach evaluation" wait-threshold-evaluation \
    --service "${BREACH_SERVICE}" --bound "${ECE_BOUND}" --status breach --measured 0.12 \
    --core-url "${CORE_URL}" --timeout "${THRESHOLD_TIMEOUT_SECONDS}" --interval 2
pass "judgment_threshold_evaluation ${THRESHOLD_ASSESSMENT_ID}: ${ECE_BOUND} measured ${THRESHOLD_MEASURED} > ${THRESHOLD_LIMIT} (outcome ${THRESHOLD_OVERALL_STATUS})"

log "Wait for the threshold quality_breach of ${BREACH_SERVICE}"
run_assertion "threshold quality_breach" wait-threshold-breach \
    --service "${BREACH_SERVICE}" --bound "${ECE_BOUND}" --measured 0.12 \
    --severity high --expect-breaching "${ECE_BOUND}" \
    --core-url "${CORE_URL}" --timeout 30 --interval 1
pass "quality_breach ${THRESHOLD_BREACH_ID}: severity ${THRESHOLD_BREACH_SEVERITY}, names ${ECE_BOUND} (limit ${THRESHOLD_BREACH_LIMIT}), parent ${THRESHOLD_BREACH_PARENT}"

log "Negative control: ${WITHIN_SERVICE} is evaluated within and does not breach"
run_assertion "within evaluation" wait-threshold-evaluation \
    --service "${WITHIN_SERVICE}" --bound "${ECE_BOUND}" --status within --measured 0.01 \
    --core-url "${CORE_URL}" --timeout 30 --interval 1
[[ "${THRESHOLD_OVERALL_STATUS}" == "within" ]] \
    || fail "${WITHIN_SERVICE} outcome is ${THRESHOLD_OVERALL_STATUS}, expected within (Brier too)"
pass "judgment_threshold_evaluation ${THRESHOLD_ASSESSMENT_ID}: ${ECE_BOUND} measured ${THRESHOLD_MEASURED} (outcome ${THRESHOLD_OVERALL_STATUS})"
# Workers post a key's assessment before its quality_breach, so seeing the
# control's evaluation does not prove a breach of it is not still in flight:
# wait one more threshold interval before asserting there is none.
sleep $((MEASURE_THRESHOLD_INTERVAL + 1))
run_assertion "no breach for the control" assert-no-verdict quality_breach \
    --service "${WITHIN_SERVICE}" --core-url "${CORE_URL}"
pass "no quality_breach for ${WITHIN_SERVICE}"
