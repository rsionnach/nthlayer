#!/usr/bin/env python3
"""
fake-service.py — Prometheus metrics exporter that simulates a microservice.
One instance per service. Controllable at runtime via HTTP.

Usage:
    python test/fake-service.py --name fraud-detect --type ai-gate --port 8001
    python test/fake-service.py --name payment-api --type api --port 8002

Control:
    curl -X POST localhost:8001/control -d '{"error_rate": 0.1, "reversal_rate": 0.08}'
    curl -X POST localhost:8001/reset
    curl localhost:8001/metrics | grep http_requests_total
"""

import argparse
import json
import math
import random
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer

from prometheus_client import CONTENT_TYPE_LATEST, Counter, Histogram, generate_latest

# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

parser = argparse.ArgumentParser(description="Fake microservice Prometheus exporter")
parser.add_argument("--name", required=True, help="Service name (used as 'service' label)")
parser.add_argument("--type", dest="svc_type", default="api", choices=["api", "ai-gate"],
                    help="Service type (default: api)")
parser.add_argument("--port", type=int, default=8001, help="HTTP server port (default: 8001)")
parser.add_argument("--rps", type=int, default=10, help="Baseline requests per second (default: 10)")
args = parser.parse_args()

SERVICE_NAME = args.name
SERVICE_TYPE = args.svc_type
PORT = args.port
BASELINE_RPS = args.rps

# ---------------------------------------------------------------------------
# Prometheus metrics
# ---------------------------------------------------------------------------

http_requests_total = Counter(
    "http_requests_total",
    "Total HTTP requests",
    ["service", "status"],
)

http_request_duration_seconds = Histogram(
    "http_request_duration_seconds",
    "HTTP request duration in seconds",
    ["service"],
)

# ai-gate only
if SERVICE_TYPE == "ai-gate":
    gen_ai_decisions_total = Counter(
        "gen_ai_decisions_total",
        "Total AI gate decisions",
        ["service", "action"],
    )
    gen_ai_overrides_total = Counter(
        "gen_ai_overrides_total",
        "Total AI gate overrides",
        ["service"],
    )
    gen_ai_overrides_hcf_total = Counter(
        "gen_ai_overrides_hcf_total",
        "Total AI gate high-confidence failure overrides",
        ["service"],
    )

# ---------------------------------------------------------------------------
# Runtime state (module-level, protected by a lock)
# ---------------------------------------------------------------------------

state_lock = threading.Lock()

# Current operative values
state = {
    "rps": BASELINE_RPS,
    "error_rate": 0.0,
    "latency_p99": 0.2,   # seconds
    "reversal_rate": 0.0,
}

# Baseline values (restored on /reset)
baseline = {
    "rps": BASELINE_RPS,
    "error_rate": 0.0,
    "latency_p99": 0.2,
    "reversal_rate": 0.0,
}

# Target values (we ramp toward these)
target = dict(state)

# Ramp tracking: list of (key, steps_remaining, step_delta)
_ramp_steps: dict = {}   # key -> {"remaining": int, "delta": float}

# ---------------------------------------------------------------------------
# Smooth transition helpers
# ---------------------------------------------------------------------------

RAMP_STEPS = 3
RAMP_INTERVAL = 5.0  # seconds between steps


def _schedule_ramp(key: str, new_value: float) -> None:
    """Set up a ramp from current state[key] toward new_value over ~15 s."""
    current = state[key]
    delta = (new_value - current) / RAMP_STEPS
    _ramp_steps[key] = {"remaining": RAMP_STEPS, "delta": delta, "target": new_value}
    target[key] = new_value


def _apply_ramp_step() -> None:
    """Called every RAMP_INTERVAL seconds to advance all pending ramps by one step."""
    with state_lock:
        done = []
        for key, ramp in _ramp_steps.items():
            state[key] = state[key] + ramp["delta"]
            ramp["remaining"] -= 1
            if ramp["remaining"] <= 0:
                state[key] = ramp["target"]   # snap to exact final value
                done.append(key)
        for key in done:
            del _ramp_steps[key]


def _ramp_thread() -> None:
    while True:
        time.sleep(RAMP_INTERVAL)
        _apply_ramp_step()


# ---------------------------------------------------------------------------
# Latency sampling
# ---------------------------------------------------------------------------

def _sample_latency(p99: float) -> float:
    """
    Sample a request duration such that ~99% of values are below p99.
    We model latency as log-normal; derive mu/sigma from p99 and an assumed p50.
    p50 ≈ p99 / 5  (rough heuristic).
    """
    p50 = max(p99 / 5.0, 0.001)
    # log-normal: P99 = exp(mu + 2.326*sigma), P50 = exp(mu)
    sigma = math.log(p99 / p50) / 2.326
    mu = math.log(p50)
    return random.lognormvariate(mu, sigma)


# ---------------------------------------------------------------------------
# Background traffic generation
# ---------------------------------------------------------------------------

def _generate_traffic() -> None:
    """Increment metrics at the configured RPS rate."""
    while True:
        with state_lock:
            rps = max(state["rps"], 0)
            error_rate = state["error_rate"]
            latency_p99 = state["latency_p99"]
            reversal_rate = state["reversal_rate"]

        sleep_interval = 1.0 / rps if rps > 0 else 1.0

        # Determine HTTP status
        roll = random.random()
        if roll < error_rate * 0.7:
            status = "500"
        elif roll < error_rate:
            status = "400"
        else:
            status = "200"

        http_requests_total.labels(service=SERVICE_NAME, status=status).inc()
        duration = _sample_latency(latency_p99)
        http_request_duration_seconds.labels(service=SERVICE_NAME).observe(duration)

        if SERVICE_TYPE == "ai-gate":
            # Distribute decisions: 80% approve, 15% reject, 5% escalate (baseline)
            decision_roll = random.random()
            if decision_roll < 0.80:
                action = "approve"
            elif decision_roll < 0.95:
                action = "reject"
            else:
                action = "escalate"
            gen_ai_decisions_total.labels(service=SERVICE_NAME, action=action).inc()

            # Overrides driven by reversal_rate
            if random.random() < reversal_rate:
                gen_ai_overrides_total.labels(service=SERVICE_NAME).inc()
                # ~20% of overrides are high-confidence failures
                if random.random() < 0.20:
                    gen_ai_overrides_hcf_total.labels(service=SERVICE_NAME).inc()

        time.sleep(sleep_interval)


# ---------------------------------------------------------------------------
# HTTP request handler
# ---------------------------------------------------------------------------

class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):  # suppress default access log noise
        pass

    def _cors_headers(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")

    def do_OPTIONS(self):
        self.send_response(204)
        self._cors_headers()
        self.end_headers()

    # --- routing ---

    def do_GET(self):
        if self.path == "/metrics" or self.path.startswith("/metrics?"):
            self._handle_metrics()
        elif self.path == "/health":
            self._handle_health()
        else:
            self._send(404, {"error": "not found"})

    def do_POST(self):
        if self.path == "/control":
            self._handle_control()
        elif self.path == "/reset":
            self._handle_reset()
        else:
            self._send(404, {"error": "not found"})

    # --- handlers ---

    def _handle_metrics(self):
        output = generate_latest()
        self.send_response(200)
        self.send_header("Content-Type", CONTENT_TYPE_LATEST)
        self.send_header("Content-Length", str(len(output)))
        self._cors_headers()
        self.end_headers()
        self.wfile.write(output)

    def _handle_health(self):
        self._send(200, {"status": "ok", "service": SERVICE_NAME})

    def _handle_control(self):
        body = self._read_json()
        if body is None:
            return
        with state_lock:
            for key in ("error_rate", "latency_p99", "reversal_rate", "rps"):
                if key in body:
                    val = body[key]
                    try:
                        val = float(val) if key != "rps" else int(val)
                    except (TypeError, ValueError):
                        self._send(400, {"error": f"invalid value for {key}"})
                        return
                    _schedule_ramp(key, val)
        self._send(200, {"status": "ok", "queued": list(body.keys())})

    def _handle_reset(self):
        with state_lock:
            for key, val in baseline.items():
                _schedule_ramp(key, val)
        self._send(200, {"status": "ok", "reset": True})

    # --- helpers ---

    def _read_json(self):
        length = int(self.headers.get("Content-Length", 0))
        if length == 0:
            self._send(400, {"error": "empty body"})
            return None
        raw = self.rfile.read(length)
        try:
            return json.loads(raw)
        except json.JSONDecodeError as exc:
            self._send(400, {"error": f"invalid JSON: {exc}"})
            return None

    def _send(self, code: int, payload: dict):
        body = json.dumps(payload).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self._cors_headers()
        self.end_headers()
        self.wfile.write(body)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print(f"[fake-service] name={SERVICE_NAME} type={SERVICE_TYPE} port={PORT} rps={BASELINE_RPS}")

    # Background threads
    threading.Thread(target=_generate_traffic, daemon=True).start()
    threading.Thread(target=_ramp_thread, daemon=True).start()

    # Single HTTP server for both /metrics and control endpoints
    server = HTTPServer(("0.0.0.0", PORT), Handler)
    print(f"[fake-service] Listening on port {PORT}  (/metrics, /control, /reset, /health)")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print(f"\n[fake-service] {SERVICE_NAME} shutting down.")
