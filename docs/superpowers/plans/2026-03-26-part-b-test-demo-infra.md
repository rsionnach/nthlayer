# Part B: Test & Demo Infrastructure Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the infrastructure that proves Part A works end-to-end against real Prometheus and enables the live demo.

**Architecture:** Fake services export Prometheus metrics matching the A8 metrics contract. Docker Compose runs Prometheus + Grafana + fake services. An E2E test script degrades a fake service, runs the full NthLayer chain, and verifies verdicts. A scenario runner drives the demo.

**Tech Stack:** Python `prometheus_client`, Docker Compose, Prometheus, Grafana, bash scripting.

**All files live in:** `/Users/robfox/Documents/GitHub/nthlayer-ecosystem/test/` and `/Users/robfox/Documents/GitHub/nthlayer-ecosystem/demo/`

---

## File Structure

```
test/
├── integration-chain.sh          # EXISTING — Part A acceptance test (verdict store seeding)
├── fake-service.py               # B1 — single-file Prometheus exporter with /control
├── docker-compose.yml            # B2 — Prometheus + Grafana + AlertManager + fake services
├── prometheus.yml                # B2 — Prometheus scrape config
├── alertmanager.yml              # B2 — AlertManager config
├── grafana/
│   └── datasources.yml           # B2 — Grafana auto-provisioned Prometheus datasource
├── e2e-test.sh                   # B3 — end-to-end integration test against live stack
└── webhook-receiver.py           # B2 — simple HTTP server that logs POST payloads

demo/
├── scenario-runner.py            # B4 — drives fake services through scripted incidents
└── scenario-cascading-failure.yaml  # B4 — scenario definition
```

---

## Task 1: B1 — Fake Service

**Files:**
- Create: `test/fake-service.py`

A single Python script that acts as a Prometheus exporter. One instance per service. Controlled at runtime via HTTP.

- [ ] **Step 1: Create fake-service.py with baseline metrics**

```python
#!/usr/bin/env python3
"""Fake service — Prometheus exporter with runtime-controllable metrics.

Usage:
  python fake-service.py --name fraud-detect --type ai-gate --port 8001
  python fake-service.py --name payment-api --type api --port 8002

Control at runtime:
  curl -X POST localhost:8001/control -d '{"error_rate": 0.05, "latency_p99": 0.8}'
  curl -X POST localhost:8001/reset
"""
```

Implements:
- `--name` (service name label), `--type` (api or ai-gate), `--port`
- Standard API metrics: `http_requests_total{service,status}`, `http_request_duration_seconds_bucket{service}`
- AI-gate metrics (when `--type ai-gate`): `gen_ai_decisions_total{service,action}`, `gen_ai_overrides_total{service}`, `gen_ai_overrides_hcf_total{service}`
- Background thread generating metrics at ~10 RPS baseline
- `GET /metrics` — standard prometheus_client exposition
- `POST /control` — JSON body with keys: `error_rate`, `latency_p99`, `reversal_rate`, `rps`
- `POST /reset` — return to baseline values
- `GET /health` — 200 OK
- Smooth transitions: metric changes ramp over 3 scrape intervals (~15s at 5s scrape)

- [ ] **Step 2: Test locally**

```bash
pip install prometheus_client
python test/fake-service.py --name fraud-detect --type ai-gate --port 8001 &
curl localhost:8001/metrics | grep http_requests_total
curl localhost:8001/metrics | grep gen_ai_decisions_total
curl -X POST localhost:8001/control -d '{"error_rate": 0.1}'
sleep 5
curl localhost:8001/metrics | grep 'status="500"'
curl -X POST localhost:8001/reset
kill %1
```

- [ ] **Step 3: Commit**

```bash
git add test/fake-service.py
git commit -m "feat(B1): fake service with controllable Prometheus metrics"
```

---

## Task 2: B2 — Docker Compose Stack

**Files:**
- Create: `test/docker-compose.yml`
- Create: `test/prometheus.yml`
- Create: `test/alertmanager.yml`
- Create: `test/grafana/datasources.yml`
- Create: `test/webhook-receiver.py`

- [ ] **Step 1: Create prometheus.yml**

5s scrape interval. Scrape targets: 8 fake services on ports 8001-8008. Lifecycle API enabled.

```yaml
global:
  scrape_interval: 5s
  evaluation_interval: 5s

rule_files:
  - /etc/prometheus/rules/*.yaml

scrape_configs:
  - job_name: fake-services
    static_configs:
      - targets:
        - host.docker.internal:8001  # fraud-detect (ai-gate)
        - host.docker.internal:8002  # payment-api
        - host.docker.internal:8003  # checkout-svc
        - host.docker.internal:8004  # order-service
        - host.docker.internal:8005  # user-service
        - host.docker.internal:8006  # auth-service
        - host.docker.internal:8007  # inventory-svc
        - host.docker.internal:8008  # notification-svc
```

- [ ] **Step 2: Create alertmanager.yml**

Route all alerts to webhook receiver.

- [ ] **Step 3: Create grafana/datasources.yml**

Auto-provision Prometheus datasource. Anonymous viewer access.

- [ ] **Step 4: Create webhook-receiver.py**

Minimal HTTP server on port 9999 that logs POST payloads to stdout. Single file, no dependencies beyond stdlib.

- [ ] **Step 5: Create docker-compose.yml**

Services:
- `prometheus:v2.51.0` — ports 9090, mounts prometheus.yml + rules dir, lifecycle API enabled (`--web.enable-lifecycle`)
- `grafana:11.0.0` — port 3000, anonymous auth, auto-provisioned datasource
- `alertmanager:v0.27.0` — port 9093, mounts alertmanager.yml

NthLayer components and fake services run on the **host**, not in Docker. Prometheus scrapes them via `host.docker.internal`.

- [ ] **Step 6: Test the stack**

```bash
cd test/
# Start fake services
for i in 1 2 3 4 5 6 7 8; do
  python fake-service.py --name svc-$i --type api --port 800$i &
done
# Override fraud-detect as ai-gate
kill %1
python fake-service.py --name fraud-detect --type ai-gate --port 8001 &

# Start infra
docker compose up -d

# Verify
curl localhost:9090/-/healthy
curl localhost:3000/api/health
curl localhost:9090/api/v1/targets | jq '.data.activeTargets | length'  # should be 8
```

- [ ] **Step 7: Commit**

```bash
git add test/docker-compose.yml test/prometheus.yml test/alertmanager.yml test/grafana/ test/webhook-receiver.py
git commit -m "feat(B2): Docker Compose stack with Prometheus, Grafana, AlertManager"
```

---

## Task 3: B3 — End-to-End Integration Test

**Files:**
- Create: `test/e2e-test.sh`

This is the real acceptance test — runs against the live Docker stack with real Prometheus. Replaces `integration-chain.sh` (which seeds verdicts directly) with a test that generates verdicts from actual metric breaches.

- [ ] **Step 1: Create e2e-test.sh**

9-step script per the integration spec:

1. Verify baseline — `curl prometheus:9090/api/v1/alerts` returns no firing alerts
2. Run `nthlayer generate` against specs, load rules into Prometheus via `curl -X POST prometheus:9090/-/reload`
3. Degrade fraud-detect: `curl -X POST localhost:8001/control -d '{"reversal_rate": 0.08}'`
4. Wait for hysteresis (3 evaluation cycles × 30s = ~90s), run `nthlayer-measure evaluate-once` 3 times
5. Verify evaluation verdict in store with `breach: true`
6. Run `nthlayer-correlate correlate --trigger-verdict <id>`
7. Run `nthlayer-respond respond --trigger-verdict <id>`
8. Restore service: `curl -X POST localhost:8001/reset`
9. Run `nthlayer-learn retrospective --incident-verdict <id>`, verify full lineage chain

Expected runtime: ~4-5 minutes (dominated by hysteresis wait).

- [ ] **Step 2: Test against running stack**

```bash
cd test/
./e2e-test.sh --prometheus-url http://localhost:9090 --specs-dir ../nthlayer/examples/opensrm --verdict-store /tmp/e2e-verdicts.db
```

- [ ] **Step 3: Commit**

```bash
git add test/e2e-test.sh
git commit -m "feat(B3): end-to-end integration test against live Prometheus stack"
```

---

## Task 4: B4 — Scenario Runner

**Files:**
- Create: `demo/scenario-runner.py`
- Create: `demo/scenario-cascading-failure.yaml`

Drives fake services through a scripted incident for demos. Only manipulates fake services via `/control`. NthLayer detects and responds via the trigger chain — the scenario runner does NOT invoke NthLayer commands.

- [ ] **Step 1: Create scenario YAML format**

```yaml
scenario:
  name: cascading-failure
  description: "AI model regression cascades through payment flow"
  services:
    fraud-detect: {port: 8001, type: ai-gate}
    payment-api: {port: 8002, type: api}
  phases:
    - name: baseline
      duration: 10s
      actions: []
    - name: model-regression
      duration: 30s
      actions:
        - service: fraud-detect
          control: {reversal_rate: 0.08, latency_p99: 0.3}
    - name: cascade
      duration: 30s
      actions:
        - service: payment-api
          control: {error_rate: 0.05, latency_p99: 0.8}
    - name: recovery
      duration: 20s
      actions:
        - service: fraud-detect
          control: reset
        - service: payment-api
          control: reset
```

- [ ] **Step 2: Create scenario-runner.py**

Reads scenario YAML, iterates through phases, sends `/control` and `/reset` requests to fake services. Prints phase transitions to stdout. Does NOT invoke NthLayer.

- [ ] **Step 3: Test**

```bash
# With fake services and Docker stack running:
python demo/scenario-runner.py --scenario demo/scenario-cascading-failure.yaml
# In parallel, NthLayer trigger chain detects the incident
```

- [ ] **Step 4: Commit**

```bash
git add demo/
git commit -m "feat(B4): scenario runner for demo incidents"
```

---

## Task 5: B5 — Live Topology Connection (Future)

**Files:**
- Modify: `/Users/robfox/Documents/GitHub/nthlayer-site/demo/index.html`

**This task is scoped but not fully specified.** The topology visualization currently uses hardcoded data. Connecting it to live Prometheus + verdict store requires:

1. A lightweight API that reads Prometheus service health and verdict store events
2. The React app polling that API instead of using hardcoded PHASES
3. WebSocket or SSE for real-time verdict feed

**NOT implemented in this plan.** This is the last item and depends on B1-B4 being stable. Document as a follow-up task.

- [ ] **Step 1: Create a bead for B5 tracking**

```bash
bd create --title "B5: Live topology connection to Prometheus + verdict store" \
  --description "Connect demo topology visualization to real Prometheus data and verdict store. Requires lightweight API + React polling/SSE." \
  --priority 3 --type feature
```

---

## Verification

After Tasks 1-4, the following sequence proves Part B works:

```bash
# 1. Start fake services
cd test/
python fake-service.py --name fraud-detect --type ai-gate --port 8001 &
python fake-service.py --name payment-api --type api --port 8002 &
# ... (6 more)

# 2. Start Docker stack
docker compose up -d

# 3. Wait for Prometheus to scrape (~10s)
sleep 10

# 4. Run E2E test
./e2e-test.sh --prometheus-url http://localhost:9090 \
  --specs-dir ../nthlayer/examples/opensrm \
  --verdict-store /tmp/e2e-verdicts.db

# 5. (Optional) Run scenario for visual demo
python ../demo/scenario-runner.py --scenario ../demo/scenario-cascading-failure.yaml

# 6. Cleanup
docker compose down
kill $(jobs -p)
```

**Pass criteria:** E2E test completes with all steps passing, producing a full verdict chain (evaluation → correlation → incident → retrospective) from real Prometheus metrics.
