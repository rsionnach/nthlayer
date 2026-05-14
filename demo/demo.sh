#!/usr/bin/env bash
# demo.sh — NthLayer ecosystem demo orchestrator
#
# Usage: ./demo/demo.sh {start|demo|scenario|teardown}
#
# Three-tier rewrite (opensrm-saun.3): start launches nthlayer-core +
# nthlayer-workers rather than the deprecated nthlayer-* CLI components.
# scenario observes the worker pipeline via core's HTTP API while
# preserving the 8-step trigger-chain narrative operators learned from the
# legacy demo.
#
# Note: `set -euo pipefail` is in force. Risky pipelines (e.g. the deploy
# gate output read at Step 7) wrap themselves in `set +e` blocks where
# their non-zero exit is intentional.
set -euo pipefail

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

DEMO_DIR="$(cd "$(dirname "$0")" && pwd)"
# Front-door root (this repo): hosts test/, demo-output/, specs, scripts.
FRONTDOOR_ROOT="$(cd "$DEMO_DIR/.." && pwd)"
# Workspace root: parent of the front-door, where sibling component repos
# (nthlayer-core/-workers/-bench/-common) are cloned. demo.sh launches
# those via `uv run --directory`.
WORKSPACE_ROOT="$(cd "$FRONTDOOR_ROOT/.." && pwd)"
SITE_DIR="${SITE_DIR:-/Users/robfox/Documents/GitHub/nthlayer-site}"
TEST_DIR="$FRONTDOOR_ROOT/test"
OUTPUT_DIR="$FRONTDOOR_ROOT/demo-output"

SCENARIO_FILE="$DEMO_DIR/scenario-cascading-failure.yaml"
VERDICT_FEED_SCRIPT="$DEMO_DIR/verdict-feed.sh"
FAKE_SERVICE_SCRIPT="$TEST_DIR/fake-service.py"
SCENARIO_RUNNER="$DEMO_DIR/scenario-runner.py"
ASSERTIONS="$TEST_DIR/three_tier_assertions.py"
RENDER_EXPLANATION="$DEMO_DIR/render_explanation.py"

HTTP_SERVER_PORT=8080
CORE_PORT="${CORE_PORT:-8000}"
CORE_URL="http://localhost:${CORE_PORT}"
PROMETHEUS_URL="http://localhost:9090"
SPECS_DIR="$DEMO_DIR/specs"

# Three-tier process directories (v1.5)
RUN_CORE="uv run --directory $WORKSPACE_ROOT/nthlayer-core"
RUN_WORKERS="uv run --directory $WORKSPACE_ROOT/nthlayer-workers"
RUN_BENCH="uv run --directory $WORKSPACE_ROOT/nthlayer-bench"

# Persistent state file paths under OUTPUT_DIR
STATE_DB="$OUTPUT_DIR/three-tier.db"
CORE_PID_FILE="$OUTPUT_DIR/core.pid"
WORKERS_PID_FILE="$OUTPUT_DIR/workers.pid"

# ---------------------------------------------------------------------------
# Styled output helpers (plain — no external dependencies)
# ---------------------------------------------------------------------------

info()    { echo "  ▸ $*"; }
success() { echo "  ✓ $*"; }
warn()    { echo "  ⚠ $*" >&2; }
error()   { echo "  ✗ $*" >&2; }

detect_llm_model() {
    # Set NTHLAYER_MODEL from env vars if not already set
    if [[ -n "${NTHLAYER_MODEL:-}" ]]; then
        success "NTHLAYER_MODEL set: ${NTHLAYER_MODEL}"
    elif [[ -n "${ANTHROPIC_API_KEY:-}" ]]; then
        export NTHLAYER_MODEL="anthropic/claude-sonnet-4-20250514"
        success "ANTHROPIC_API_KEY set — using default Anthropic model"
    elif [[ -n "${OPENAI_API_KEY:-}" ]]; then
        export NTHLAYER_MODEL="openai/gpt-4o"
        success "OPENAI_API_KEY set — using default OpenAI model"
    else
        warn "No NTHLAYER_MODEL or LLM API key set."
        warn "Falling back to NTHLAYER_LLM_STUB=canned for deterministic local demo."
        warn "(Set ANTHROPIC_API_KEY or OPENAI_API_KEY for real LLM-driven agent verdicts.)"
        export NTHLAYER_LLM_STUB=canned
    fi
}

header() {
    local text="$*"
    local bar
    bar="$(printf '─%.0s' $(seq 1 $((${#text} + 4))))"
    echo ""
    echo "┌─${bar}─┐"
    echo "│  ${text}  │"
    echo "└─${bar}─┘"
    echo ""
}

# ---------------------------------------------------------------------------
# Pre-flight check
# ---------------------------------------------------------------------------

cmd_start_preflight() {
    header "NthLayer Demo — Pre-flight Check"

    local missing=0

    local -a required_cmds=(docker python3 curl uv jq)
    for cmd in "${required_cmds[@]}"; do
        if command -v "$cmd" &>/dev/null; then
            success "$cmd found"
        else
            error "$cmd not found — install it before running the demo"
            missing=$((missing + 1))
        fi
    done

    # Three-tier package directories (saun.3 — replaces the legacy
    # nthlayer-learn / nthlayer-measure / etc. checks)
    local -a packages=(nthlayer-core nthlayer-workers nthlayer-bench nthlayer-common)
    for pkg in "${packages[@]}"; do
        if [[ -d "$WORKSPACE_ROOT/$pkg" ]]; then
            success "$pkg directory found"
        else
            error "$pkg not found at $WORKSPACE_ROOT/$pkg"
            missing=$((missing + 1))
        fi
    done

    # nthlayer-site (browser demo)
    if [[ -d "$SITE_DIR" ]]; then
        success "nthlayer-site found at $SITE_DIR"
    else
        warn "nthlayer-site not found at $SITE_DIR — browser demo (cmd_demo) will skip"
    fi

    # fake-service.py
    if [[ -f "$FAKE_SERVICE_SCRIPT" ]]; then
        success "fake-service.py found"
    else
        error "fake-service.py not found at $FAKE_SERVICE_SCRIPT"
        missing=$((missing + 1))
    fi

    # three_tier_assertions.py — helper used by cmd_scenario
    if [[ -f "$ASSERTIONS" ]]; then
        success "three_tier_assertions.py found"
    else
        error "three_tier_assertions.py not found at $ASSERTIONS"
        missing=$((missing + 1))
    fi

    # demo specs
    if [[ -d "$SPECS_DIR" ]]; then
        success "demo specs found at $SPECS_DIR"
    else
        error "demo specs not found at $SPECS_DIR"
        missing=$((missing + 1))
    fi

    # LLM provider (warn only — falls back to NTHLAYER_LLM_STUB=canned)
    detect_llm_model

    if [[ $missing -gt 0 ]]; then
        error "$missing required component(s) missing — cannot start"
        exit 1
    fi

    success "Pre-flight passed"
}

# ---------------------------------------------------------------------------
# start — bring up infrastructure
# ---------------------------------------------------------------------------

cmd_start() {
    cmd_start_preflight

    # 0. Reconcile pre-existing state. A previous cmd_start that crashed
    #    (or was Ctrl-C'd) leaves PID files behind whose processes may
    #    still be running. Stop them before binding new processes to the
    #    same ports — otherwise the new fake-services overwrite the old
    #    PID files (orphaning the originals) and the core port-binding
    #    later in this function aborts mid-start.
    if [[ -d "$OUTPUT_DIR" ]]; then
        info "Reconciling pre-existing PID files in $OUTPUT_DIR ..."
        for pid_file in "$OUTPUT_DIR"/fake-*.pid "$WORKERS_PID_FILE" "$CORE_PID_FILE" "$OUTPUT_DIR/http-server.pid"; do
            [[ -f "$pid_file" ]] || continue
            local name
            name="$(basename "$pid_file" .pid)"
            stop_pid_file "$pid_file" "$name"
        done
    fi

    # Port pre-flight (fail fast, before docker compose changes any state)
    if lsof -nP -iTCP:"$CORE_PORT" -sTCP:LISTEN &>/dev/null 2>&1; then
        error "Port $CORE_PORT is already in use — free it before running ./demo/demo.sh start"
        exit 1
    fi

    # 1. Output directory
    info "Creating $OUTPUT_DIR"
    mkdir -p "$OUTPUT_DIR"

    # 2. Docker stack — selective bring-up of prometheus + alertmanager
    #    only. The full test/docker-compose.yml also includes Grafana but
    #    its provisioning bind-mount is flaky on some Docker Desktop
    #    setups. The browser demo's Grafana link still works if a
    #    Grafana instance is running separately; the demo does not depend
    #    on the dashboard's data path.
    header "Starting Docker Stack"
    info "Running: docker compose up -d prometheus alertmanager (in $TEST_DIR)"
    docker compose -f "$TEST_DIR/docker-compose.yml" up -d prometheus alertmanager
    success "Prometheus + AlertManager started"

    # 3. Wait for Prometheus
    header "Waiting for Prometheus"
    info "Polling $PROMETHEUS_URL/-/ready ..."
    local attempts=0
    local max_attempts=30
    until curl -sf "$PROMETHEUS_URL/-/ready" &>/dev/null; do
        attempts=$((attempts + 1))
        if [[ $attempts -ge $max_attempts ]]; then
            error "Prometheus did not become ready after ${max_attempts}s — check Docker logs"
            exit 1
        fi
        info "  waiting... (${attempts}/${max_attempts})"
        sleep 1
    done
    success "Prometheus is ready"

    # 4. Fake services (8 services, ports 8001-8008)
    header "Starting Fake Services"

    local -a services=(
        "fraud-detect:ai-gate:8001"
        "payment-api:api:8002"
        "checkout-svc:api:8003"
        "order-service:api:8004"
        "user-service:api:8005"
        "auth-service:api:8006"
        "stripe-api:api:8007"
        "analytics-api:api:8008"
    )

    for svc in "${services[@]}"; do
        local name type port
        name="${svc%%:*}"
        type="${svc#*:}"; type="${type%:*}"
        port="${svc##*:}"

        info "Starting $name ($type) on port $port"
        python3 "$FAKE_SERVICE_SCRIPT" \
            --name "$name" \
            --type "$type" \
            --port "$port" \
            >> "$OUTPUT_DIR/fake-${name}.log" 2>&1 &
        echo $! > "$OUTPUT_DIR/fake-${name}.pid"
        success "  $name PID $(cat "$OUTPUT_DIR/fake-${name}.pid")"
    done

    info "Waiting 3 seconds for services to register with Prometheus..."
    sleep 3

    # 5. nthlayer-core (saun.3 — replaces direct verdict-store access).
    # Port-conflict check happened at cmd_start entry (fail-fast).
    header "Starting nthlayer-core (HTTP API on $CORE_PORT)"
    NTHLAYER_STORE_PATH="$STATE_DB" \
    NTHLAYER_MANIFESTS_DIR="$SPECS_DIR" \
    $RUN_CORE nthlayer serve --host 127.0.0.1 --port "$CORE_PORT" \
        >> "$OUTPUT_DIR/core.log" 2>&1 &
    echo $! > "$CORE_PID_FILE"
    success "core PID $(cat "$CORE_PID_FILE")"

    info "Waiting for core /health ..."
    local deadline=$(( $(date +%s) + 30 ))
    until curl -fsS "$CORE_URL/health" >/dev/null 2>&1; do
        [[ $(date +%s) -lt $deadline ]] || { error "core not healthy in 30s"; exit 1; }
        sleep 0.5
    done
    success "core ready"

    # 6. nthlayer-workers
    header "Starting nthlayer-workers"
    if [[ "${NTHLAYER_LLM_STUB:-}" == "canned" ]]; then
        info "LLM stub active (NTHLAYER_LLM_STUB=canned) — agents return deterministic canned responses"
    else
        info "LLM model: ${NTHLAYER_MODEL:-default}"
    fi
    $RUN_WORKERS nthlayer-workers serve \
        --core-url "$CORE_URL" \
        --instance-id "demo" \
        --prometheus-url "$PROMETHEUS_URL" \
        --collect-interval 10 \
        --measure-interval 10 \
        --correlate-interval 10 \
        --respond-interval 10 \
        --retrospective-interval 15 \
        --outcome-interval 30 \
        >> "$OUTPUT_DIR/workers.log" 2>&1 &
    echo $! > "$WORKERS_PID_FILE"
    success "workers PID $(cat "$WORKERS_PID_FILE")"

    info "Waiting for first worker heartbeat ..."
    $RUN_BENCH python "$ASSERTIONS" wait-heartbeat \
        --core-url "$CORE_URL" --timeout 30 --interval 1 >/dev/null \
        || { error "workers did not heartbeat in 30s"; exit 1; }
    success "workers heartbeating into core"

    # 7. Verdict feed sidecar (saun.5): polls core's GET /verdicts and writes
    # the response to nthlayer-site/demo/verdict-feed.json so the topology UI
    # can read it same-origin via /demo/verdict-feed.json.
    if [[ -d "$SITE_DIR/demo" ]]; then
        info "Starting verdict-feed sidecar..."
        CORE_URL="$CORE_URL" FEED_FILE="$SITE_DIR/demo/verdict-feed.json" \
            nohup bash "$VERDICT_FEED_SCRIPT" \
            >"$OUTPUT_DIR/verdict-feed.log" 2>&1 &
        echo $! > "$OUTPUT_DIR/verdict-feed.pid"
        success "verdict-feed PID $(cat "$OUTPUT_DIR/verdict-feed.pid") (writes $SITE_DIR/demo/verdict-feed.json)"
    fi

    success "Infrastructure ready (core + workers + fake-services)"
    echo ""
    info "Next step: ./demo/demo.sh demo"
}

# ---------------------------------------------------------------------------
# demo — open browser to live topology
# ---------------------------------------------------------------------------

cmd_demo() {
    header "NthLayer Demo — Browser"

    if [[ ! -d "$SITE_DIR" ]]; then
        warn "nthlayer-site not present — skipping browser open"
        return 0
    fi

    # Start HTTP server from nthlayer-site so topology and verdict feed
    # are same-origin (topology at /demo/, feed at /demo/verdict-feed.json)
    if lsof -iTCP:"$HTTP_SERVER_PORT" -sTCP:LISTEN &>/dev/null 2>&1; then
        warn "Port $HTTP_SERVER_PORT already in use — assuming HTTP server is running"
    else
        info "Starting HTTP server on port $HTTP_SERVER_PORT (serving $SITE_DIR)"
        python3 -m http.server "$HTTP_SERVER_PORT" \
            --directory "$SITE_DIR" \
            >> "$OUTPUT_DIR/http-server.log" 2>&1 &
        echo $! > "$OUTPUT_DIR/http-server.pid"
        success "HTTP server started (PID $(cat "$OUTPUT_DIR/http-server.pid"))"
        sleep 1
    fi

    local base_url="http://localhost:${HTTP_SERVER_PORT}/demo"
    local live_url="${base_url}/?mode=live&prometheus=$PROMETHEUS_URL&verdict-feed=verdict-feed.json"
    local guided_url="${base_url}/?mode=guided"

    info "Opening browser tabs:"
    info "  Live:   $live_url"
    info "  Guided: $guided_url"
    if command -v open &>/dev/null; then
        open "$live_url"
        sleep 0.5
        open "$guided_url"
    elif command -v xdg-open &>/dev/null; then
        xdg-open "$live_url"
        sleep 0.5
        xdg-open "$guided_url"
    else
        warn "Cannot detect a browser opener — navigate manually to:"
        warn "  $live_url"
        warn "  $guided_url"
    fi

    success "Demo running in browser"
}

# ---------------------------------------------------------------------------
# scenario — run the scripted incident (8-step trigger chain)
# ---------------------------------------------------------------------------
#
# Three-tier rewrite (saun.3): the 8-step chain narrative is preserved
# (operators learn the script's output cadence), but each step now
# observes the worker pipeline via core's HTTP API rather than running
# CLI tools. The legacy decision-record content-addressed chain hashes
# are replaced by core's verdict-ancestry chain (queryable via
# GET /verdicts/{id}/ancestors); workers don't currently write decision
# records — that's tracked separately.
#
# Re-running the scenario (opensrm-n5e): each scenario leaves residual
# error/reversal samples in Prometheus's TSDB. Service SLO PromQL uses
# rate() over [5m] windows, so a baseline portfolio captured immediately
# after a recovery can still show degraded services. To get a clean
# baseline between runs: ./demo/demo.sh teardown && ./demo/demo.sh start
# (no Prometheus volume is mounted, so docker compose down wipes the
# TSDB).

cmd_scenario() {
    header "NthLayer Demo — Running Scenario"

    if [[ ! -f "$SCENARIO_FILE" ]]; then
        error "Scenario file not found: $SCENARIO_FILE"
        exit 1
    fi

    local LOG="$OUTPUT_DIR/trigger-chain.log"
    mkdir -p "$OUTPUT_DIR"
    : > "$LOG"

    # Pacing between steps (seconds); override with DEMO_PAUSE=0 for fast runs
    local PAUSE="${DEMO_PAUSE:-3}"

    # Colored output prefixes
    local C_MEASURE=$'\033[35m'   # purple
    local C_CORRELATE=$'\033[33m' # yellow
    local C_RESPOND=$'\033[31m'   # red
    local C_LEARN=$'\033[32m'     # green
    local C_GENERATE=$'\033[36m'  # cyan
    local C_OBSERVE=$'\033[94m'   # bright blue
    local C_RESET=$'\033[0m'

    clog() {
        local color="$1" tag="$2"; shift 2
        local padded
        padded=$(printf '%-12s' "[$tag]")
        echo "${color}${padded}${C_RESET} $*"
        echo "${padded} $*" >> "$LOG"
    }

    # show_lineage_tail prints the last few verdict types in a service's
    # ancestry chain via core's API. Replaces the legacy decision-record
    # show_record_hash function — same accountability narrative
    # (provenance is queryable, chain is auditable) over a different
    # primitive (verdict ancestry instead of content-addressed hash chain).
    show_lineage_tail() {
        local verdict_id="$1"
        if [[ -z "$verdict_id" ]]; then return; fi
        curl -fsS "$CORE_URL/verdicts/${verdict_id}/ancestors" 2>/dev/null \
            | jq -r '. | reverse | .[0:5] | .[] | "  ↳ \(.type): \(.id)"' 2>/dev/null \
            | while IFS= read -r line; do clog "$C_OBSERVE" "observe" "$line"; done
    }

    info "Scenario: $SCENARIO_FILE"
    info "Specs:    $SPECS_DIR"
    info "Core:     $CORE_URL"

    clog "$C_GENERATE" "generate" "monitoring infrastructure loaded from OpenSRM specs"

    # Sanity: workers must be running
    curl -fsS "$CORE_URL/health" >/dev/null 2>&1 \
        || { error "core not reachable at $CORE_URL — run './demo/demo.sh start' first"; exit 1; }

    # ── Step 1: Portfolio Health (Baseline) ─────────────────
    header "Step 1: Portfolio Health (Baseline)"
    clog "$C_OBSERVE" "observe" "polling core for baseline portfolio_status assessment..."
    # The observe.collect worker module emits portfolio_status assessments
    # on its 10s cycle. Wait for one to land before showing it.
    #
    # eval-pattern: three_tier_assertions.py prints `KEY=value` lines on
    # stdout (e.g. ASSESSMENT_ID, VERDICT_ID, CASE_ID, CASE_PRIORITY,
    # VERDICT_CREATED_AT). `eval` surfaces them as bash globals available
    # to the rest of the step. Used throughout cmd_scenario.
    local portfolio
    portfolio=$($RUN_BENCH python "$ASSERTIONS" wait-assessment-kind portfolio_status \
        --core-url "$CORE_URL" --timeout 30 --interval 2 2>/dev/null) \
        || warn "no portfolio_status assessment in 30s — continuing"
    if [[ -n "$portfolio" ]]; then
        eval "$portfolio"
        clog "$C_OBSERVE" "observe" "portfolio assessment: $ASSESSMENT_ID"
    fi

    # Canonical portfolio table per opensrm-42y.3: services × overall status
    # × budget remaining (worst SLO), sourced from the worker-emitted
    # portfolio_status + slo_status assessments. Pattern (b) per the
    # 42y.16 audit — no on-demand CLI invocation.
    #
    # `2>/dev/null` is load-bearing: render-portfolio writes diagnostic
    # notes (slo-fetch failures, unreachable core) to stderr and a clean
    # table to stdout. Suppressing stderr here keeps the demo terminal
    # uncluttered for the audience; the helper exits 0 on any failure
    # so `set -euo pipefail` does not abort the scenario.
    clog "$C_OBSERVE" "observe" "baseline portfolio:"
    $RUN_BENCH python "$ASSERTIONS" render-portfolio --core-url "$CORE_URL" 2>/dev/null \
        | while IFS= read -r line; do clog "$C_OBSERVE" "observe" "$line"; done
    sleep "$PAUSE"

    # ── Step 2: Trigger Incident ───────────────────────────
    header "Step 2: Triggering Incident"
    clog "$C_GENERATE" "generate" "scenario-runner driving fake-services through cascading-failure scenario"
    python3 "$SCENARIO_RUNNER" \
        --scenario "$SCENARIO_FILE" \
        --base-url "http://localhost" >> "$OUTPUT_DIR/scenario-runner.log" 2>&1 &
    local SCENARIO_PID=$!

    info "Waiting for degradation to ramp..."
    sleep 35

    # ── Step 3: Detect Breach ──────────────────────────────
    header "Step 3: Detect Breach"
    clog "$C_MEASURE" "measure" "waiting for measure worker to emit quality_breach for fraud-detect..."
    local breach_out
    breach_out=$($RUN_BENCH python "$ASSERTIONS" wait-verdict-type quality_breach \
        --service fraud-detect --core-url "$CORE_URL" \
        --timeout 180 --interval 2) \
        || { clog "$C_MEASURE" "measure" "no quality_breach after 180s — services may have recovered"; \
             wait $SCENARIO_PID 2>/dev/null || true; return; }
    eval "$breach_out"
    local QUALITY_BREACH_ID="$VERDICT_ID"
    clog "$C_MEASURE" "measure" "BREACH detected — verdict $QUALITY_BREACH_ID at $VERDICT_CREATED_AT"

    # ── Step 4: Budget Explanation ──────────────────────────
    header "Step 4: Budget Explanation"
    # Anchor the engine's render against a real assessment id so the
    # audience sees that the human-readable narrative traces back to a
    # specific record in core (opensrm-42y.7). The latest slo_status
    # for fraud-detect is whichever SLO last cycled — sufficient as a
    # "data lives here" pointer; engine itself joins all slo_status +
    # drift_signal for the service.
    clog "$C_OBSERVE" "observe" "polling core for latest fraud-detect slo_status..."
    local slo_anchor
    slo_anchor=$($RUN_BENCH python "$ASSERTIONS" wait-assessment-kind slo_status \
        --service fraud-detect --core-url "$CORE_URL" \
        --timeout 30 --interval 2 2>/dev/null) || true
    if [[ -n "$slo_anchor" ]]; then
        eval "$slo_anchor"
        clog "$C_OBSERVE" "observe" "latest slo_status in chain: $ASSESSMENT_ID"
    fi
    clog "$C_OBSERVE" "observe" "running ExplanationEngine against fraud-detect's slo_status + drift_signal..."
    # Pattern (b) (audit 42y.16) — engine from 42y.4: ingest worker-emitted
    # assessments from core and run the in-process ExplanationEngine.
    # `$RUN_WORKERS` rather than `$RUN_BENCH` because the engine lives in
    # nthlayer-workers, not in the bench venv used by `$ASSERTIONS`.
    #
    # `2>/dev/null` is load-bearing for the same reason as render-portfolio:
    # the helper writes operator diagnostics to stderr (fetch failures,
    # malformed payloads) and the narrative table to stdout. Suppress
    # stderr to keep the demo terminal clean; the helper exits 0 on any
    # failure so `set -euo pipefail` does not abort the scenario.
    $RUN_WORKERS python "$RENDER_EXPLANATION" \
        --core-url "$CORE_URL" --service fraud-detect 2>/dev/null \
        | while IFS= read -r line; do clog "$C_OBSERVE" "observe" "$line"; done
    sleep "$PAUSE"

    # ── Step 5: Correlate ────────────────────────────────
    header "Step 5: Correlate"
    clog "$C_CORRELATE" "correlate" "waiting for correlation_snapshot from correlate worker..."
    local snap_out
    snap_out=$($RUN_BENCH python "$ASSERTIONS" wait-assessment-kind correlation_snapshot \
        --core-url "$CORE_URL" --timeout 60 --interval 2) \
        || { clog "$C_CORRELATE" "correlate" "no correlation_snapshot in 60s"; \
             wait $SCENARIO_PID 2>/dev/null || true; return; }
    eval "$snap_out"
    local CORR_SNAPSHOT_ID="$ASSESSMENT_ID"
    clog "$C_CORRELATE" "correlate" "snapshot: $CORR_SNAPSHOT_ID"

    # ── Step 6: Respond + Learn ─────────────────────────
    header "Step 6: Respond + Learn"
    clog "$C_RESPOND" "respond" "waiting for triage verdict from respond worker..."
    local triage_out
    triage_out=$($RUN_BENCH python "$ASSERTIONS" wait-verdict-type triage \
        --core-url "$CORE_URL" --timeout 60 --interval 1) \
        || { clog "$C_RESPOND" "respond" "no triage verdict in 60s"; \
             wait $SCENARIO_PID 2>/dev/null || true; return; }
    eval "$triage_out"
    local TRIAGE_ID="$VERDICT_ID"
    clog "$C_RESPOND" "respond" "triage: $TRIAGE_ID"

    # Case (operator queue entry) — created eagerly by respond at incident open
    local case_out
    case_out=$($RUN_BENCH python "$ASSERTIONS" wait-case \
        --service fraud-detect --core-url "$CORE_URL" \
        --timeout 30 --interval 1) \
        || warn "no case visible in 30s"
    if [[ -n "$case_out" ]]; then
        eval "$case_out"
        clog "$C_RESPOND" "respond" "case (bench queue): $CASE_ID  priority=$CASE_PRIORITY"
    fi

    # Wait for scenario-runner to finish — its Recovery phase resets the
    # fake-services so learn's retrospective lands while the breach has
    # closed (matches the legacy demo's narrative). scenario-runner's
    # non-zero exit is acceptable here; the demo continues regardless.
    clog "$C_LEARN" "learn" "waiting for scenario recovery phase..."
    wait $SCENARIO_PID 2>/dev/null || true

    clog "$C_LEARN" "learn" "waiting for retrospective from learn worker..."
    local retro_out
    if retro_out=$($RUN_BENCH python "$ASSERTIONS" wait-assessment-kind retrospective \
        --core-url "$CORE_URL" --timeout 60 --interval 2 2>/dev/null); then
        eval "$retro_out"
        clog "$C_LEARN" "learn" "retrospective: $ASSESSMENT_ID — loop closed"
    else
        clog "$C_LEARN" "learn" "no retrospective in 60s — falling back to calibration_signal"
        retro_out=$($RUN_BENCH python "$ASSERTIONS" wait-assessment-kind calibration_signal \
            --core-url "$CORE_URL" --timeout 30 --interval 2 2>/dev/null) \
            || warn "no learn assessment in fallback window"
        if [[ -n "$retro_out" ]]; then
            eval "$retro_out"
            clog "$C_LEARN" "learn" "calibration_signal: $ASSESSMENT_ID"
        fi
    fi

    # ── Step 7: Deployment Gate ─────────────────────────────
    header "Step 7: Deployment Gate"
    clog "$C_OBSERVE" "observe" "running deploy gate against payment-api (cascade target)..."
    # The workers package ships a `gate` subcommand (CLI-only per design,
    # not a worker module). Targets payment-api because fraud-detect's 2m
    # reversal_rate window heals before this step runs; payment-api carries
    # the cascade budget impact and tells the cross-boundary story.
    local gate_out="$OUTPUT_DIR/gate-result.json"
    set +e
    $RUN_WORKERS nthlayer-workers gate \
        --service payment-api \
        --tier critical \
        --core-url "$CORE_URL" \
        > "$gate_out" 2>/dev/null
    local GATE_EXIT=$?
    set -e

    if [[ -s "$gate_out" ]]; then
        # Read from file directly rather than `cat | while`; under pipefail
        # a broken pipe at the consumer side could otherwise abort.
        while IFS= read -r line; do clog "$C_OBSERVE" "observe" "$line"; done < "$gate_out"
    fi

    if [[ $GATE_EXIT -eq 2 ]]; then
        clog "$C_OBSERVE" "observe" "deploy BLOCKED — fraud-detect regression exhausted payment-api's budget"
    elif [[ $GATE_EXIT -eq 1 ]]; then
        clog "$C_OBSERVE" "observe" "deploy WARNING — error budget low"
    elif [[ $GATE_EXIT -eq 0 ]]; then
        clog "$C_OBSERVE" "observe" "deploy APPROVED"
    else
        clog "$C_OBSERVE" "observe" "deploy gate inconclusive (exit=$GATE_EXIT)"
    fi

    # Surface the deploy_gate assessment id the gate just emitted into
    # core (opensrm-42y.7). The gate CLI's stdout JSON omits the id
    # (gap also flagged in 42y.5's R5); pulling it from core's assessment
    # store keeps the change demo-side without modifying workers.
    local gate_anchor
    gate_anchor=$($RUN_BENCH python "$ASSERTIONS" wait-assessment-kind deploy_gate \
        --service payment-api --core-url "$CORE_URL" \
        --timeout 15 --interval 1 2>/dev/null) || true
    if [[ -n "$gate_anchor" ]]; then
        eval "$gate_anchor"
        clog "$C_OBSERVE" "observe" "deploy_gate assessment: $ASSESSMENT_ID"
    fi
    sleep "$PAUSE"

    # ── Step 8: Portfolio Health (Post-Incident) ────────────
    header "Step 8: Portfolio Health (Post-Incident)"
    clog "$C_OBSERVE" "observe" "polling core for post-incident portfolio_status assessment..."
    # Same renderer as Step 1 (opensrm-42y.3) — pattern (b) per the
    # 42y.16 audit. The audience sees the table again with the same
    # shape, this time reflecting cascade damage: fraud-detect
    # regressed, payment-api's budget exhausted across the service
    # boundary. Before/after comparison is implicit in the matching
    # output format.
    local post_portfolio
    post_portfolio=$($RUN_BENCH python "$ASSERTIONS" wait-assessment-kind portfolio_status \
        --core-url "$CORE_URL" --timeout 30 --interval 2 2>/dev/null) \
        || warn "no portfolio_status assessment in 30s — continuing"
    if [[ -n "$post_portfolio" ]]; then
        eval "$post_portfolio"
        clog "$C_OBSERVE" "observe" "post-incident portfolio assessment: $ASSESSMENT_ID"
    fi
    clog "$C_OBSERVE" "observe" "rendering:"
    $RUN_BENCH python "$ASSERTIONS" render-portfolio --core-url "$CORE_URL" 2>/dev/null \
        | while IFS= read -r line; do clog "$C_OBSERVE" "observe" "$line"; done
    echo ""
    clog "$C_OBSERVE" "observe" "fraud-detect model regression cascaded to payment-api. Budget exhausted across service boundary."

    # Provenance via verdict ancestry chain (replaces legacy
    # decision-record content-addressed hashes).
    clog "$C_OBSERVE" "observe" "verdict ancestry chain from triage upward (provenance):"
    show_lineage_tail "$TRIAGE_ID"

    clog "$C_GENERATE" "generate" "all verdicts produced by real NthLayer workers via core HTTP API"
    success "Scenario and 8-step trigger chain complete"
}

# ---------------------------------------------------------------------------
# teardown — stop everything and clean up
# ---------------------------------------------------------------------------

stop_pid_file() {
    # Stop a process tracked by a PID file. Uses `kill -0` polling rather
    # than `wait` because `wait` only works for children of the current
    # shell; cmd_teardown often runs in a different shell from cmd_start
    # so the PID is not a descendant. Polls for ~5s before giving up.
    local pid_file="$1" name="$2"
    [[ -f "$pid_file" ]] || return 0
    local pid
    pid="$(cat "$pid_file")"
    if kill -0 "$pid" 2>/dev/null; then
        kill -TERM "$pid" 2>/dev/null && success "  Stopped $name (PID $pid)" \
            || warn "  Could not stop $name (PID $pid)"
        local deadline=$(( $(date +%s) + 5 ))
        while kill -0 "$pid" 2>/dev/null; do
            [[ $(date +%s) -lt $deadline ]] || { warn "  $name (PID $pid) did not exit in 5s"; break; }
            sleep 0.2
        done
    else
        info "  $name (PID $pid) already stopped"
    fi
    rm -f "$pid_file"
}

cmd_teardown() {
    header "NthLayer Demo — Teardown"

    # 1. Verdict-feed sidecar — stop first so it stops polling core before
    #    core goes away (avoids spurious connection-error noise in its log).
    info "Stopping verdict-feed sidecar..."
    stop_pid_file "$OUTPUT_DIR/verdict-feed.pid" "verdict-feed"

    # 2. Workers + core (saun.3 — replaces individual CLI component
    #    teardown). Order matters: workers stop first so any in-flight
    #    cycles complete before core's API goes away.
    info "Stopping workers..."
    stop_pid_file "$WORKERS_PID_FILE" "workers"

    info "Stopping core..."
    stop_pid_file "$CORE_PID_FILE" "core"

    # 3. Fake services
    info "Stopping fake services..."
    for pid_file in "$OUTPUT_DIR"/fake-*.pid; do
        [[ -f "$pid_file" ]] || continue
        local name
        name="$(basename "$pid_file" .pid)"
        stop_pid_file "$pid_file" "$name"
    done

    # 4. HTTP server
    stop_pid_file "$OUTPUT_DIR/http-server.pid" "HTTP server"

    # 5. Docker compose down
    if [[ -f "$TEST_DIR/docker-compose.yml" ]]; then
        info "Running docker compose down..."
        docker compose -f "$TEST_DIR/docker-compose.yml" down
        success "Docker stack stopped"
    fi

    # 6. demo-output/ cleanup
    if [[ -d "$OUTPUT_DIR" ]]; then
        info "Removing $OUTPUT_DIR"
        rm -rf "$OUTPUT_DIR"
        success "demo-output/ removed"
    fi

    # 7. Remove feed file from nthlayer-site/demo/ (stale once core is gone)
    local feed_path="$SITE_DIR/demo/verdict-feed.json"
    if [[ -f "$feed_path" ]]; then
        info "Removing $feed_path"
        rm -f "$feed_path"
        success "verdict-feed.json removed from nthlayer-site/demo/"
    fi

    success "Teardown complete"
}

# ---------------------------------------------------------------------------
# Usage
# ---------------------------------------------------------------------------

usage() {
    echo ""
    echo "Usage: $(basename "$0") {start|demo|scenario|teardown}"
    echo ""
    echo "  start     — pre-flight, Docker stack, fake services, core + workers"
    echo "  demo      — HTTP server + open browser (live + guided tabs)"
    echo "  scenario  — run cascading failure scenario (8-step trigger chain)"
    echo "  teardown  — stop everything and clean up"
    echo ""
    echo "Note: to re-run the scenario from a clean baseline, run teardown"
    echo "then start again — Prometheus TSDB is not volume-mounted, so this"
    echo "wipes residual samples that can otherwise degrade the Step 1"
    echo "portfolio baseline (5m PromQL lookback)."
    echo ""
}

# ---------------------------------------------------------------------------
# Dispatch
# ---------------------------------------------------------------------------

COMMAND="${1:-}"

case "$COMMAND" in
    start)    cmd_start ;;
    demo)     cmd_demo ;;
    scenario) cmd_scenario ;;
    teardown) cmd_teardown ;;
    *)
        error "Unknown command: '${COMMAND}'"
        usage
        exit 1
        ;;
esac
