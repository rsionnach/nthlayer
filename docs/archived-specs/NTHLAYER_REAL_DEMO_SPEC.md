# NthLayer Real Demo — Terminal + Live Topology Spec

## Overview

The real demo is two windows side by side: a browser showing the live topology visualisation connected to real Prometheus, and a terminal (tmux + Charm tools) showing the NthLayer CLI operating in real time. Both views update from the same data sources (Prometheus + verdict store), so they stay in sync naturally — not through orchestration, but because they're reading the same truth.

One command starts everything. One command runs the scenario. The audience watches a real incident unfold across both views simultaneously.

## Colour Palette

The terminal must use the same Nord-based palette as nthlayer.io. Every tmux pane border, gum output, Lip Gloss styled text, and status indicator uses these exact colours.

```
Background:     #0B1120
Border:         #1E2A3A
Accent (teal):  #88c0d0
Text primary:   #F0F0F3
Text secondary: #9CA3AF
Text muted:     #4A5568

Component colours (used for verdict types and phase indicators):
  generate:   #88c0d0  (frost teal)
  measure:    #b48ead  (purple)
  correlate:  #ebcb8b  (gold)
  respond:    #bf616a  (red)
  learn:      #a3be8c  (green)

Domain colours (used for service labels in verdict stream):
  platform:   #81a1c1
  payments:   #ebcb8b
  orders:     #a3be8c
  ml:         #b48ead
  data:       #5e81ac
  external:   #8fbcbb

Incident colours:
  AI incident:     #bf616a
  Infra incident:  #88c0d0
  Healthy:         #a3be8c
  Warning:         #ebcb8b
```

## Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                         DATA SOURCES                                 │
│                                                                      │
│   Prometheus (:9090)          Verdict Store (verdicts.db)            │
│   ← scraped from fake         ← written by measure,                 │
│     services every 5s           correlate, respond, learn            │
│                                                                      │
└─────────┬──────────────────────────────┬────────────────────────────┘
          │                              │
    ┌─────▼─────┐                  ┌─────▼─────┐
    │  BROWSER   │                  │ TERMINAL   │
    │            │                  │ (tmux)     │
    │ Live       │                  │            │
    │ Topology   │  same data,     │ Verdict    │
    │ (HTML)     │  same timing,   │ Stream,    │
    │            │  natural sync   │ Metrics,   │
    │ reads from │                  │ Scenario   │
    │ Prometheus │                  │ Runner     │
    │ HTTP API   │                  │            │
    └───────────┘                  └────────────┘
```

The sync is automatic because both views poll the same Prometheus and read the same verdict store. When the scenario runner degrades fraud-detect, Prometheus scrapes the new metrics within 5 seconds. The topology polls Prometheus and updates node colours. The terminal's metric watch updates. nthlayer-measure detects the breach and writes a verdict. The terminal's verdict stream shows it. The topology's event feed shows it (if connected to the verdict store). No message passing between the two views. Just shared state.

## Live Topology Changes

The existing nthlayer.io/demo topology runs on mock data with scripted phases. For the real demo, it needs a second mode that reads from live Prometheus.

### New: Real-time data mode

Add a `?mode=live&prometheus=http://localhost:9090` query parameter (or equivalent configuration) that switches the topology from mock phases to live polling.

In live mode:
- **Node health:** Poll Prometheus every 5 seconds for each service's SLO state. Map to the existing health colour scale (green > 0.75, amber 0.45-0.75, red < 0.45). For ai-gate services, use the judgment SLO state (reversal rate vs target) as the primary health signal. For traditional services, use error budget remaining.
- **Node health query:** For each service, query the recording rules nthlayer-generate produced (the metric names from the A8 metrics contract). Fall back to raw `ALERTS{service="..."}` if recording rules aren't loaded.
- **Traffic particles:** Continue animating particles along dependency edges. Particle speed/density can optionally reflect request rate from Prometheus, but static animation is fine for v1.
- **Trace lines:** Disabled in live mode (traces are a mock demo concept). In live mode, the visual signal is node colour changing.
- **Event feed:** Instead of scripted phase events, display verdicts from the verdict store. Poll a lightweight API endpoint or read from a shared JSON file that a sidecar process maintains.
- **NthLayer ecosystem panel:** Highlight the active component based on verdict types appearing in the store. When an evaluation verdict appears, nthlayer-measure lights up. When a correlation verdict appears, nthlayer-correlate lights up. When an incident verdict appears, nthlayer-respond lights up.
- **Phase labels and overlay:** Removed in live mode. The topology is continuous, not phase-based. The status label in the top-right shows the real portfolio state (e.g. "6/8 SLOs HEALTHY" or "INCIDENT ACTIVE: INC-4821").

### Verdict feed endpoint

The topology needs access to recent verdicts. Options (in order of preference):

**Option A: Static JSON file.** A tiny sidecar script (`verdict-feed.sh`) runs `nthlayer-learn list --db ./verdicts.db --latest 20 --format json > ./verdict-feed.json` every 2 seconds. The topology polls this file via HTTP (served by a simple static file server or by the existing dev server). Zero new infrastructure.

**Option B: Lightweight API.** A small Python/Node HTTP server that queries the verdict store on each request and returns the latest N verdicts as JSON. More responsive but another process to manage.

**Option C: WebSocket.** Overkill for a demo. Skip.

Recommend Option A for simplicity.

### Layout for live mode

The live topology should use the reduced service set (8 services matching the Docker stack) rather than the full 21. Either auto-detect from Prometheus targets or accept a `?services=fraud-detect,payment-api,...` parameter. The NthLayer ecosystem panel stays in the same position.

---

## Terminal Layout (tmux)

Four panes in a 2x2 grid:

```
┌──────────────────────────────────┬──────────────────────────────────┐
│                                  │                                  │
│  PANE 1: Scenario Runner         │  PANE 2: Verdict Stream          │
│  (interactive, gum-styled)       │  (live tail, colour-coded)       │
│                                  │                                  │
│  Shows: phase progression,       │  Shows: verdicts appearing in    │
│  what's happening, narration     │  real time as components fire    │
│                                  │                                  │
├──────────────────────────────────┼──────────────────────────────────┤
│                                  │                                  │
│  PANE 3: Prometheus Metrics      │  PANE 4: NthLayer CLI Output     │
│  (auto-refreshing)               │  Shows: actual CLI commands      │
│                                  │  being invoked by the trigger    │
│  Shows: reversal rate,           │  chain (measure, correlate,      │
│  error budget, alert state       │  respond) with their output      │
│                                  │                                  │
└──────────────────────────────────┴──────────────────────────────────┘
```

### Pane 1: Scenario Runner

The scenario runner drives the fake services and narrates what's happening. Built with gum for styled output.

```bash
# Phase header (gum style)
gum style \
  --foreground "#88c0d0" \
  --border-foreground "#1E2A3A" \
  --border rounded \
  --padding "0 2" \
  --margin "1 0" \
  "PHASE 1 — STEADY STATE"

# Phase description
gum style \
  --foreground "#9CA3AF" \
  --width 50 \
  "All services healthy. NthLayer monitoring generated from OpenSRM specs."

# Phase progress (gum spin or custom progress)
gum spin --spinner dot \
  --spinner.foreground "#a3be8c" \
  --title "Steady state — 15s" \
  -- sleep 15
```

Phase progression for the scenario:

1. **Steady State** (15s) — "#a3be8c" green. "All services healthy. Monitoring generated from specs."
2. **Bad Model Deploy** (45s) — "#b48ead" purple. "Model v2.3 deployed to fraud-detect. Reversal rate climbing." Shows the curl command hitting `/control` (briefly).
3. **Cascade** (30s) — "#bf616a" red. "Degradation cascading to payment-api. Error rate climbing."
4. **Detection & Correlation** (30s) — "#ebcb8b" gold. "nthlayer-measure detected judgment SLO breach. Correlate identifying root cause." (This phase waits for verdicts to appear in the store rather than using a fixed timer.)
5. **Response** (20s) — "#bf616a" red. "INC-4821 opened. Severity 2. Payments-ml paged."
6. **Recovery** (20s) — "#a3be8c" green. "fraud-detect rolled back. Services recovering."
7. **Learn** (15s) — "#a3be8c" green. "Retrospective captured. Spec recommendation generated."
8. **Deploy Gate** (15s) — "#88c0d0" teal. "Model v2.4 attempts deploy. Judgment SLO gate blocks it. Loop closed."

### Pane 2: Verdict Stream

A continuously-updating display of verdicts from the verdict store, styled with Lip Gloss or gum. Each verdict type gets its component colour.

```bash
# This runs as a watch loop, polling the verdict store
while true; do
  clear
  # Header
  gum style \
    --foreground "#F0F0F3" \
    --bold \
    "VERDICT STREAM"

  # Fetch latest verdicts and render each with colour based on type
  nthlayer-learn list --db ./verdicts.db --latest 10 --format json | \
    python3 verdict-renderer.py

  sleep 2
done
```

The `verdict-renderer.py` script reads JSON verdicts and outputs gum-styled cards:

```
┌─ EVALUATION ──────────────────────── 14:22:01 ─┐
│ fraud-detect reversal rate 3.1%                 │
│ target <1.5% · BREACH · consecutive: 3          │
│ ▶ MEASURE · confidence 0.91                     │
└─────────────────────────────────────────────────┘

┌─ CORRELATION ─────────────────────── 14:22:05 ─┐
│ Root cause: fraud-detect model regression       │
│ Blast radius: fraud-detect, payment-api         │
│ ▶ CORRELATE · confidence 0.88                   │
└─────────────────────────────────────────────────┘

┌─ INCIDENT ────────────────────────── 14:22:06 ─┐
│ INC-4821 opened · Severity 2                    │
│ Root cause: fraud-detect · model_regression     │
│ ▶ RESPOND · notified payments-ml                │
└─────────────────────────────────────────────────┘
```

Border colours per verdict type:
- evaluation: `#b48ead`
- correlation: `#ebcb8b`
- incident/triage/investigation/remediation: `#bf616a`
- retrospective: `#a3be8c`
- decision: `#81a1c1`

### Pane 3: Prometheus Metrics

A live-updating view of the key metrics the audience should watch. Refreshes every 2 seconds.

```bash
while true; do
  clear
  gum style --foreground "#F0F0F3" --bold "PROMETHEUS METRICS"
  echo ""

  # Reversal rate
  REVERSAL=$(curl -s 'localhost:9090/api/v1/query' \
    --data-urlencode 'query=gen_ai_overrides_total{service="fraud-detect"} / gen_ai_decisions_total{service="fraud-detect"}' \
    | python3 -c "import sys,json; r=json.load(sys.stdin)['data']['result']; print(f'{float(r[0][\"value\"][1]):.3f}' if r else 'N/A')")

  # Colour based on threshold
  if (( $(echo "$REVERSAL > 0.015" | bc -l 2>/dev/null) )); then
    gum style --foreground "#bf616a" "  REVERSAL RATE:  $REVERSAL  (target <0.015) ⚠"
  else
    gum style --foreground "#a3be8c" "  REVERSAL RATE:  $REVERSAL  (target <0.015) ✓"
  fi

  # Error budget (similar pattern)
  # Alert state (similar pattern)
  # Active alerts count

  ALERTS=$(curl -s 'localhost:9090/api/v1/alerts' \
    | python3 -c "import sys,json; alerts=json.load(sys.stdin)['data']['alerts']; print(len(alerts))")
  if [ "$ALERTS" -gt 0 ]; then
    gum style --foreground "#bf616a" "  ACTIVE ALERTS:  $ALERTS"
  else
    gum style --foreground "#a3be8c" "  ACTIVE ALERTS:  $ALERTS"
  fi

  sleep 2
done
```

### Pane 4: NthLayer CLI Output

This pane shows the actual NthLayer commands being invoked by the trigger chain. When measure writes an evaluation verdict and invokes correlate, the command and its output appear here. When correlate invokes respond, that appears too.

Implementation: the trigger chain (measure invoking correlate, correlate invoking respond) writes its subprocess output to a log file. This pane tails that log.

```bash
gum style --foreground "#F0F0F3" --bold "NTHLAYER CLI"
echo ""
tail -f ./demo-output/trigger-chain.log | while read line; do
  # Colour the line based on which component produced it
  if echo "$line" | grep -q "measure"; then
    gum style --foreground "#b48ead" "$line"
  elif echo "$line" | grep -q "correlate"; then
    gum style --foreground "#ebcb8b" "$line"
  elif echo "$line" | grep -q "respond"; then
    gum style --foreground "#bf616a" "$line"
  elif echo "$line" | grep -q "learn"; then
    gum style --foreground "#a3be8c" "$line"
  else
    gum style --foreground "#9CA3AF" "$line"
  fi
done
```

---

## tmux Configuration

```bash
# tmux theme matching NthLayer palette
# Save as demo/.tmux-nthlayer.conf

# Status bar
set -g status-style "bg=#0B1120,fg=#9CA3AF"
set -g status-left "#[fg=#88c0d0,bold] NTHLAYER "
set -g status-right "#[fg=#4A5568]%H:%M:%S"
set -g status-left-length 20

# Pane borders
set -g pane-border-style "fg=#1E2A3A"
set -g pane-active-border-style "fg=#88c0d0"

# Window/pane background
set -g window-style "bg=#0B1120"
set -g window-active-style "bg=#0B1120"

# Message style
set -g message-style "bg=#1E2A3A,fg=#88c0d0"
```

---

## Startup Script

```bash
#!/bin/bash
# demo.sh — NthLayer real demo
# Usage:
#   ./demo.sh start     — bring up infrastructure
#   ./demo.sh demo      — open browser + tmux, ready to run scenario
#   ./demo.sh scenario  — trigger the incident (run from within tmux pane 1)
#   ./demo.sh teardown  — clean up everything

set -euo pipefail

DEMO_DIR="$(cd "$(dirname "$0")" && pwd)"
SPECS_DIR="$DEMO_DIR/specs"
VERDICT_STORE="$DEMO_DIR/verdicts.db"
OUTPUT_DIR="$DEMO_DIR/demo-output"
PROMETHEUS_URL="http://localhost:9090"
TOPOLOGY_URL="http://localhost:8080/demo?mode=live&prometheus=$PROMETHEUS_URL"

case "${1:-help}" in

  start)
    echo "Starting infrastructure..."
    mkdir -p "$OUTPUT_DIR"

    # Start Docker stack (Prometheus, Grafana, AlertManager)
    cd "$DEMO_DIR"
    docker compose up -d
    echo "Waiting for Prometheus..."
    until curl -sf "$PROMETHEUS_URL/-/ready" > /dev/null 2>&1; do sleep 1; done

    # Start fake services
    python3 "$DEMO_DIR/fake-service.py" \
      --name fraud-detect --type ai-gate --port 8001 &
    echo $! > "$OUTPUT_DIR/fake-fraud.pid"
    python3 "$DEMO_DIR/fake-service.py" \
      --name payment-api --type api --port 8002 &
    echo $! > "$OUTPUT_DIR/fake-payment.pid"
    python3 "$DEMO_DIR/fake-service.py" \
      --name checkout-svc --type api --port 8003 &
    echo $! > "$OUTPUT_DIR/fake-checkout.pid"
    python3 "$DEMO_DIR/fake-service.py" \
      --name order-service --type api --port 8004 &
    echo $! > "$OUTPUT_DIR/fake-order.pid"
    python3 "$DEMO_DIR/fake-service.py" \
      --name user-service --type api --port 8005 &
    echo $! > "$OUTPUT_DIR/fake-user.pid"
    python3 "$DEMO_DIR/fake-service.py" \
      --name auth-service --type api --port 8006 &
    echo $! > "$OUTPUT_DIR/fake-auth.pid"
    python3 "$DEMO_DIR/fake-service.py" \
      --name stripe-api --type api --port 8007 &
    echo $! > "$OUTPUT_DIR/fake-stripe.pid"
    python3 "$DEMO_DIR/fake-service.py" \
      --name analytics-api --type api --port 8008 &
    echo $! > "$OUTPUT_DIR/fake-analytics.pid"

    # Wait for fake services to be scrapeable
    echo "Waiting for fake services..."
    sleep 3

    # Generate monitoring from specs
    echo "Generating monitoring from OpenSRM specs..."
    nthlayer generate --portfolio "$SPECS_DIR" --output "$OUTPUT_DIR/generated"

    # Load rules into Prometheus
    cp "$OUTPUT_DIR"/generated/prometheus/*.yml ./prometheus/rules/
    curl -sf -X POST "$PROMETHEUS_URL/-/reload"

    # Start verdict feed sidecar (for topology event feed)
    while true; do
      nthlayer-learn list --db "$VERDICT_STORE" --latest 20 --format json \
        > "$OUTPUT_DIR/verdict-feed.json" 2>/dev/null || echo "[]" > "$OUTPUT_DIR/verdict-feed.json"
      sleep 2
    done &
    echo $! > "$OUTPUT_DIR/verdict-feed.pid"

    echo ""
    gum style \
      --foreground "#a3be8c" \
      --border-foreground "#1E2A3A" \
      --border rounded \
      --padding "0 2" \
      "Infrastructure ready. Run: ./demo.sh demo"
    ;;

  demo)
    # Open browser to live topology
    if command -v open &> /dev/null; then
      open "$TOPOLOGY_URL"
    elif command -v xdg-open &> /dev/null; then
      xdg-open "$TOPOLOGY_URL"
    fi

    # Create tmux session with NthLayer theme
    tmux -f "$DEMO_DIR/.tmux-nthlayer.conf" new-session -d -s nthlayer -x 220 -y 55

    # Pane 1 (top-left): Scenario runner — starts with a welcome message, waits for user
    tmux send-keys -t nthlayer "cd $DEMO_DIR && bash demo/pane-scenario.sh" Enter

    # Pane 2 (top-right): Verdict stream
    tmux split-window -h -t nthlayer
    tmux send-keys -t nthlayer "cd $DEMO_DIR && bash demo/pane-verdicts.sh" Enter

    # Pane 3 (bottom-left): Prometheus metrics
    tmux split-window -v -t nthlayer.0
    tmux send-keys -t nthlayer "cd $DEMO_DIR && bash demo/pane-metrics.sh" Enter

    # Pane 4 (bottom-right): NthLayer CLI output
    tmux split-window -v -t nthlayer.1
    tmux send-keys -t nthlayer "cd $DEMO_DIR && bash demo/pane-cli.sh" Enter

    # Balance panes
    tmux select-layout -t nthlayer tiled

    # Attach
    tmux attach -t nthlayer
    ;;

  scenario)
    # This is run from within pane 1 (the scenario runner)
    # Delegates to the scenario runner script
    python3 "$DEMO_DIR/demo/scenario-runner.py" \
      --scenario "$DEMO_DIR/demo/scenario-cascading-failure.yaml" \
      --verdict-store "$VERDICT_STORE" \
      --prometheus-url "$PROMETHEUS_URL" \
      --specs-dir "$SPECS_DIR" \
      --output-dir "$OUTPUT_DIR" \
      --trigger-chain
    ;;

  teardown)
    echo "Cleaning up..."

    # Kill tmux session
    tmux kill-session -t nthlayer 2>/dev/null || true

    # Kill fake services
    for pidfile in "$OUTPUT_DIR"/fake-*.pid; do
      [ -f "$pidfile" ] && kill "$(cat "$pidfile")" 2>/dev/null || true
    done

    # Kill verdict feed sidecar
    [ -f "$OUTPUT_DIR/verdict-feed.pid" ] && kill "$(cat "$OUTPUT_DIR/verdict-feed.pid")" 2>/dev/null || true

    # Stop Docker
    cd "$DEMO_DIR" && docker compose down

    # Clean output
    rm -rf "$OUTPUT_DIR"

    gum style --foreground "#a3be8c" "Clean."
    ;;

  *)
    echo "Usage: ./demo.sh {start|demo|scenario|teardown}"
    ;;
esac
```

---

## Pane Scripts

Each tmux pane runs its own bash script. These live in `demo/`.

### demo/pane-scenario.sh

The scenario runner pane. Shows phase progression with gum styling. Waits for user input before starting.

```bash
#!/bin/bash
set -euo pipefail

DEMO_DIR="$(cd "$(dirname "$0")/.." && pwd)"

# Welcome
gum style \
  --foreground "#88c0d0" \
  --border-foreground "#1E2A3A" \
  --border rounded \
  --padding "1 3" \
  --margin "1 0" \
  --bold \
  "NTHLAYER — REAL DEMO"

gum style \
  --foreground "#9CA3AF" \
  --width 60 \
  "8 services across Prometheus. Monitoring generated from OpenSRM specs.
A bad model will deploy. NthLayer will detect, correlate, respond, learn,
and block the next bad deploy."

echo ""
gum style --foreground "#4A5568" "Browser: live topology · Terminal: NthLayer CLI"
echo ""

# Wait for user
gum confirm "Ready to start the scenario?" && {
  # Run the scenario
  "$DEMO_DIR/demo.sh" scenario
}

# After scenario completes
echo ""
gum style \
  --foreground "#a3be8c" \
  --border-foreground "#a3be8c" \
  --border rounded \
  --padding "0 2" \
  "SCENARIO COMPLETE"

gum style --foreground "#9CA3AF" \
  "The verdict chain in the store tells the full story.
The topology shows all services green.
The deploy gate blocked model v2.4.
The loop is closed."
```

### demo/pane-verdicts.sh

Continuously polls the verdict store and renders styled verdict cards.

```bash
#!/bin/bash
set -euo pipefail

DEMO_DIR="$(cd "$(dirname "$0")/.." && pwd)"
VERDICT_STORE="$DEMO_DIR/verdicts.db"

gum style --foreground "#F0F0F3" --bold "VERDICT STREAM"
gum style --foreground "#4A5568" "Waiting for verdicts..."
echo ""

LAST_COUNT=0

while true; do
  CURRENT_COUNT=$(nthlayer-learn list --db "$VERDICT_STORE" --format json 2>/dev/null \
    | python3 -c "import sys,json; print(len(json.load(sys.stdin)))" 2>/dev/null || echo "0")

  if [ "$CURRENT_COUNT" -gt "$LAST_COUNT" ]; then
    # New verdicts arrived — re-render
    clear
    gum style --foreground "#F0F0F3" --bold "VERDICT STREAM"
    echo ""

    nthlayer-learn list --db "$VERDICT_STORE" --latest 8 --format json 2>/dev/null \
      | python3 "$DEMO_DIR/demo/verdict-renderer.py"

    LAST_COUNT="$CURRENT_COUNT"
  fi

  sleep 2
done
```

### demo/pane-metrics.sh

Live Prometheus metrics display.

```bash
#!/bin/bash
set -euo pipefail

PROMETHEUS_URL="http://localhost:9090"

while true; do
  clear
  gum style --foreground "#F0F0F3" --bold "PROMETHEUS METRICS"
  echo ""

  # Reversal rate
  REVERSAL=$(curl -s "$PROMETHEUS_URL/api/v1/query" \
    --data-urlencode 'query=gen_ai_overrides_total{service="fraud-detect"} / gen_ai_decisions_total{service="fraud-detect"}' \
    2>/dev/null | python3 -c "
import sys,json
try:
    r=json.load(sys.stdin)['data']['result']
    print(f'{float(r[0][\"value\"][1]):.4f}' if r else 'N/A')
except: print('N/A')" 2>/dev/null || echo "N/A")

  if [ "$REVERSAL" != "N/A" ] && (( $(echo "$REVERSAL > 0.015" | bc -l 2>/dev/null || echo 0) )); then
    gum style --foreground "#bf616a" "  REVERSAL RATE    $REVERSAL   target <0.015  ⚠ BREACH"
  else
    gum style --foreground "#a3be8c" "  REVERSAL RATE    $REVERSAL   target <0.015  ✓ OK"
  fi

  # Error rate (payment-api)
  ERROR_RATE=$(curl -s "$PROMETHEUS_URL/api/v1/query" \
    --data-urlencode 'query=rate(http_server_requests_total{service="payment-api",status=~"5.."}[1m]) / rate(http_server_requests_total{service="payment-api"}[1m])' \
    2>/dev/null | python3 -c "
import sys,json
try:
    r=json.load(sys.stdin)['data']['result']
    print(f'{float(r[0][\"value\"][1]):.4f}' if r else '0.0000')
except: print('N/A')" 2>/dev/null || echo "N/A")

  if [ "$ERROR_RATE" != "N/A" ] && (( $(echo "$ERROR_RATE > 0.01" | bc -l 2>/dev/null || echo 0) )); then
    gum style --foreground "#bf616a" "  ERROR RATE (pay)  $ERROR_RATE   target <0.01   ⚠ ELEVATED"
  else
    gum style --foreground "#a3be8c" "  ERROR RATE (pay)  $ERROR_RATE   target <0.01   ✓ OK"
  fi

  # Active alerts
  ALERTS=$(curl -s "$PROMETHEUS_URL/api/v1/alerts" 2>/dev/null \
    | python3 -c "
import sys,json
try: print(len(json.load(sys.stdin)['data']['alerts']))
except: print('0')" 2>/dev/null || echo "0")

  if [ "$ALERTS" -gt 0 ]; then
    gum style --foreground "#ebcb8b" "  ACTIVE ALERTS    $ALERTS"
  else
    gum style --foreground "#a3be8c" "  ACTIVE ALERTS    $ALERTS"
  fi

  echo ""
  gum style --foreground "#4A5568" "  Polling every 2s from Prometheus :9090"

  sleep 2
done
```

### demo/pane-cli.sh

Tails the trigger chain log with colour-coded output.

```bash
#!/bin/bash
set -euo pipefail

DEMO_DIR="$(cd "$(dirname "$0")/.." && pwd)"
LOG_FILE="$DEMO_DIR/demo-output/trigger-chain.log"

gum style --foreground "#F0F0F3" --bold "NTHLAYER CLI"
gum style --foreground "#4A5568" "Waiting for trigger chain activity..."
echo ""

# Create log file if it doesn't exist
touch "$LOG_FILE"

# Tail with colour coding
tail -f "$LOG_FILE" | while IFS= read -r line; do
  if echo "$line" | grep -qi "measure\|evaluate"; then
    gum style --foreground "#b48ead" "$line"
  elif echo "$line" | grep -qi "correlate"; then
    gum style --foreground "#ebcb8b" "$line"
  elif echo "$line" | grep -qi "respond\|incident"; then
    gum style --foreground "#bf616a" "$line"
  elif echo "$line" | grep -qi "learn\|retro"; then
    gum style --foreground "#a3be8c" "$line"
  elif echo "$line" | grep -qi "generate\|deploy\|gate\|block"; then
    gum style --foreground "#88c0d0" "$line"
  elif echo "$line" | grep -qi "error\|fail"; then
    gum style --foreground "#bf616a" --bold "$line"
  else
    gum style --foreground "#9CA3AF" "$line"
  fi
done
```

### demo/verdict-renderer.py

Reads JSON verdicts from stdin and renders styled cards using gum subprocess calls.

```python
#!/usr/bin/env python3
"""Render verdict JSON as styled terminal cards using gum."""
import json
import subprocess
import sys

COLOURS = {
    "evaluation": "#b48ead",
    "correlation": "#ebcb8b",
    "triage": "#bf616a",
    "investigation": "#bf616a",
    "remediation": "#bf616a",
    "communication": "#bf616a",
    "retrospective": "#a3be8c",
    "decision": "#81a1c1",
}

def render_verdict(v):
    vtype = v.get("subject", {}).get("type", "unknown")
    colour = COLOURS.get(vtype, "#9CA3AF")
    timestamp = v.get("timestamp", "")[:19].replace("T", " ")
    service = v.get("subject", {}).get("service", "unknown")
    confidence = v.get("confidence", {}).get("score", 0)

    # Build content from metadata.custom
    custom = v.get("metadata", {}).get("custom", {})
    lines = []

    if vtype == "evaluation":
        slo_name = custom.get("slo_name", "")
        current = custom.get("current_value", "")
        target = custom.get("target", "")
        breach = custom.get("breach", False)
        lines.append(f"{service} {slo_name} {current}")
        lines.append(f"target <{target} · {'BREACH' if breach else 'OK'}")
    elif vtype == "correlation":
        root_causes = custom.get("root_causes", [])
        for rc in root_causes:
            lines.append(f"Root cause: {rc.get('service', '?')} ({rc.get('type', '?')})")
        blast = custom.get("blast_radius", [])
        if blast:
            lines.append(f"Blast radius: {', '.join(b.get('service','?') for b in blast)}")
    elif vtype in ("triage", "investigation", "remediation", "communication"):
        incident_id = custom.get("incident_id", "")
        severity = custom.get("severity", "")
        lines.append(f"{incident_id} · Severity {severity}")
        lines.append(f"Root cause: {service}")
    elif vtype == "retrospective":
        duration = custom.get("duration_minutes", "")
        decisions = custom.get("decisions_affected", "")
        lines.append(f"Duration: {duration}m · {decisions} decisions affected")
        financial = custom.get("financial_impact", {})
        if financial:
            lines.append(f"Impact: {financial.get('currency','')}{financial.get('estimated','')}")
    else:
        lines.append(json.dumps(custom)[:80])

    # Render with gum
    header = f" {vtype.upper():<16} {timestamp} "
    body = "\n".join(f" {l}" for l in lines)
    footer = f" ▶ {vtype.upper()} · confidence {confidence:.2f}"

    content = f"{header}\n{body}\n{footer}"

    subprocess.run([
        "gum", "style",
        "--foreground", colour,
        "--border-foreground", colour,
        "--border", "rounded",
        "--padding", "0 1",
        "--margin", "0 0 1 0",
        content
    ])

try:
    verdicts = json.load(sys.stdin)
    if isinstance(verdicts, list):
        for v in reversed(verdicts):  # Newest at bottom
            render_verdict(v)
except (json.JSONDecodeError, KeyError, TypeError):
    pass
```

---

## Scenario Runner Changes

The existing scenario runner needs two modifications:

1. **`--trigger-chain` flag:** When set, after degrading fraud-detect (phase 2), the scenario runner invokes `nthlayer measure --evaluate-once` repeatedly (every 30s) until an evaluation verdict with `breach=true` appears in the verdict store. This triggers the automatic chain (measure → correlate → respond). The scenario runner does not invoke correlate or respond directly; it lets the trigger chain handle it. All subprocess output is written to `demo-output/trigger-chain.log` so pane 4 can display it.

2. **Phase timing based on verdicts:** Instead of fixed sleep timers, phases 4-6 (detection, correlation, response) wait for the corresponding verdict types to appear in the verdict store. This ensures the tmux display and the topology are in sync with what's actually happening, not racing ahead of or behind the real system.

3. **Learn and deploy gate phases:** After recovery (services reset), the scenario runner invokes `nthlayer-learn retrospective --incident-verdict <id>` and then `nthlayer check-deploy --service fraud-detect` directly, logging output to the trigger chain log.

---

## Sync Between Browser and Terminal

The sync is natural, not engineered:

| Event | Browser (topology) sees | Terminal sees |
|-------|------------------------|---------------|
| fraud-detect degraded | Node turns amber/red (Prometheus poll) | Pane 3: reversal rate climbing |
| nthlayer-measure fires | Ecosystem panel: measure lights up | Pane 2: evaluation verdict appears. Pane 4: measure CLI output |
| nthlayer-correlate fires | Ecosystem panel: correlate lights up | Pane 2: correlation verdict appears. Pane 4: correlate CLI output |
| nthlayer-respond fires | Ecosystem panel: respond lights up | Pane 2: incident verdict appears. Pane 4: respond CLI output |
| Services recover | Nodes return to green | Pane 3: reversal rate drops. Pane 2: recovery verdicts |
| nthlayer-learn fires | Ecosystem panel: learn lights up | Pane 2: retrospective verdict. Pane 4: learn CLI output |
| Deploy gate blocks | Status label updates | Pane 1: "BLOCKED" output. Pane 4: check-deploy output |

Both views are reading the same Prometheus and the same verdict store. They don't need to communicate with each other. They're in sync because reality is in sync.

---

## Dependencies

Tools the demo requires on the host:

- **gum** (`brew install gum` or `go install github.com/charmbracelet/gum@latest`)
- **tmux** (`brew install tmux`)
- **docker** and **docker compose**
- **python3** with `prometheus_client` (`pip install prometheus_client`)
- **bc** (for bash arithmetic in metric comparison)
- **curl**, **jq** (standard tools)
- **nthlayer**, **nthlayer-measure**, **nthlayer-correlate**, **nthlayer-respond**, **nthlayer-learn** (the NthLayer ecosystem, installed and on PATH)

A pre-flight check at the start of `demo.sh start` should verify all dependencies are present and print clear error messages for anything missing.

---

## Implementation Order

1. **Live topology mode** — add `?mode=live` to the existing topology HTML. Poll Prometheus for node health. Poll verdict-feed.json for event feed. This is the biggest change.
2. **Verdict renderer** — the Python script that turns verdict JSON into styled gum output.
3. **Pane scripts** — the four bash scripts for each tmux pane.
4. **tmux config** — the NthLayer-themed tmux configuration.
5. **Startup script** — `demo.sh` with start/demo/scenario/teardown commands.
6. **Scenario runner changes** — `--trigger-chain` flag, verdict-based phase timing.
7. **Pre-flight checks** — dependency verification in `demo.sh start`.
8. **VHS tape** (optional) — a `.tape` file for Charm's VHS tool to record a perfectly-timed demo GIF/MP4 for nthlayer.io and LinkedIn.

---

## Notes for Claude Code

- The live topology mode is the highest-value change. Start there. The terminal panes are bash scripts that can be iterated quickly.
- gum must be installed on the host. The pane scripts shell out to gum for styling. If gum is not available, fall back to plain echo with ANSI colour codes.
- The verdict-renderer.py reads from the existing nthlayer-learn verdict schema. Audit the actual JSON output of `nthlayer-learn list --format json` before assuming field paths. The field names in this spec (subject.type, confidence.score, metadata.custom) are based on the audit from Part A but verify against the actual output.
- The tmux pane layout uses `tiled` for simplicity. If more control is needed, use explicit `-p` percentage splits.
- All demo scripts live in `demo/` directory. Not in the core package.
- The trigger chain log (`demo-output/trigger-chain.log`) is the bridge between the trigger chain (which runs in the background) and pane 4 (which displays it). Make sure measure/correlate/respond write to this log when invoked via the trigger chain.
- The verdict-feed sidecar is a simple while loop, not a service. It writes a JSON file every 2 seconds. The topology polls this file. If the sidecar dies, the topology just shows stale data. No crash.
