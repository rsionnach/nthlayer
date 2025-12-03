"""
NthLayer Demo Application with Mock PostgreSQL and Kubernetes metrics

Generates realistic metrics for demonstration purposes including:
- HTTP service metrics
- PostgreSQL database metrics
- Kubernetes pod metrics
"""

import os
import random
import time
import threading
from datetime import datetime
from functools import wraps

from flask import Flask, jsonify, request, Response
from prometheus_client import (
    Counter,
    Histogram,
    Gauge,
    generate_latest,
    CollectorRegistry,
    CONTENT_TYPE_LATEST
)

app = Flask(__name__)

# Basic auth for metrics endpoint
def check_auth(username, password):
    """Check if username/password is valid."""
    expected_user = os.environ.get('METRICS_USERNAME', 'nthlayer')
    expected_pass = os.environ.get('METRICS_PASSWORD', 'demo-metrics')
    return username == expected_user and password == expected_pass

def authenticate():
    """Send 401 response for authentication."""
    return Response(
        'Authentication required',
        401,
        {'WWW-Authenticate': 'Basic realm="Metrics"'}
    )

def requires_auth(f):
    """Decorator for endpoints requiring basic auth."""
    @wraps(f)
    def decorated(*args, **kwargs):
        auth = request.authorization
        if not auth or not check_auth(auth.username, auth.password):
            return authenticate()
        return f(*args, **kwargs)
    return decorated

# Create custom registry
registry = CollectorRegistry()

# === HTTP Service Metrics ===
http_requests_total = Counter(
    'http_requests_total',
    'Total HTTP requests',
    ['service', 'method', 'endpoint', 'status'],
    registry=registry
)

http_request_duration_seconds = Histogram(
    'http_request_duration_seconds',
    'HTTP request duration in seconds',
    ['service', 'method', 'endpoint'],
    registry=registry,
    buckets=(0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0)
)

error_budget_remaining_ratio = Gauge(
    'error_budget_remaining_ratio',
    'Remaining error budget as ratio (0-1)',
    ['service', 'slo'],
    registry=registry
)

service_up = Gauge(
    'up',
    'Service is up',
    ['service', 'instance'],
    registry=registry
)

# === PostgreSQL Mock Metrics ===
pg_stat_database_numbackends = Gauge(
    'pg_stat_database_numbackends',
    'Number of backends currently connected',
    ['service', 'datname'],
    registry=registry
)

pg_settings_max_connections = Gauge(
    'pg_settings_max_connections',
    'Maximum number of connections',
    ['service'],
    registry=registry
)

pg_stat_database_blks_hit = Counter(
    'pg_stat_database_blks_hit',
    'Number of disk blocks found in buffer cache',
    ['service', 'datname'],
    registry=registry
)

pg_stat_database_blks_read = Counter(
    'pg_stat_database_blks_read',
    'Number of disk blocks read from disk',
    ['service', 'datname'],
    registry=registry
)

pg_stat_statements_mean_exec_time_seconds = Histogram(
    'pg_stat_statements_mean_exec_time_seconds',
    'Mean query execution time in seconds',
    ['service'],
    registry=registry,
    buckets=(0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0)
)

# === Kubernetes Mock Metrics ===
kube_pod_status_phase = Gauge(
    'kube_pod_status_phase',
    'Pod status phase (1 if in this phase)',
    ['service', 'phase', 'pod'],
    registry=registry
)

container_cpu_usage_seconds_total = Counter(
    'container_cpu_usage_seconds_total',
    'Cumulative CPU usage in seconds',
    ['service', 'pod', 'container'],
    registry=registry
)

container_memory_working_set_bytes = Gauge(
    'container_memory_working_set_bytes',
    'Current working set memory in bytes',
    ['service', 'pod', 'container'],
    registry=registry
)

# Configuration
SERVICE_NAME = 'payment-api'
ERROR_RATE = 0.05  # 5%
PODS = [
    'payment-api-7d4f8b9c5-abc12',
    'payment-api-7d4f8b9c5-def34',
    'payment-api-7d4f8b9c5-ghi56'
]

# Initialize service as up
service_up.labels(service=SERVICE_NAME, instance='demo-1').set(1)
pg_settings_max_connections.labels(service=SERVICE_NAME).set(100)


def simulate_background_traffic():
    """Background thread generating continuous metrics."""
    while True:
        try:
            # === HTTP Traffic ===
            for _ in range(random.randint(10, 20)):
                endpoint = '/api/payment'
                method = 'POST'
                status = '200' if random.random() > ERROR_RATE else '500'
                duration = random.gauss(0.3, 0.1) if status == '200' else random.gauss(0.5, 0.2)
                duration = max(0.01, duration)
                
                http_requests_total.labels(
                    service=SERVICE_NAME,
                    method=method,
                    endpoint=endpoint,
                    status=status
                ).inc()
                
                if status == '200':
                    http_request_duration_seconds.labels(
                        service=SERVICE_NAME,
                        method=method,
                        endpoint=endpoint
                    ).observe(duration)
            
            # === Error Budget ===
            error_budget_remaining_ratio.labels(
                service=SERVICE_NAME,
                slo='availability'
            ).set(random.uniform(0.96, 0.99))
            
            error_budget_remaining_ratio.labels(
                service=SERVICE_NAME,
                slo='latency-p95'
            ).set(random.uniform(0.92, 0.98))
            
            # === PostgreSQL Metrics ===
            # Active connections (varies between 25-45)
            pg_stat_database_numbackends.labels(
                service=SERVICE_NAME,
                datname='payment_db'
            ).set(random.randint(25, 45))
            
            # Buffer cache activity (98-99% hit ratio)
            for _ in range(random.randint(950, 990)):
                pg_stat_database_blks_hit.labels(
                    service=SERVICE_NAME,
                    datname='payment_db'
                ).inc()
            
            for _ in range(random.randint(10, 50)):
                pg_stat_database_blks_read.labels(
                    service=SERVICE_NAME,
                    datname='payment_db'
                ).inc()
            
            # Query execution times (mostly fast, occasional slow)
            for _ in range(random.randint(15, 30)):
                if random.random() < 0.95:
                    # Fast query (5-30ms)
                    query_time = random.uniform(0.005, 0.030)
                else:
                    # Slow query (100-500ms)
                    query_time = random.uniform(0.100, 0.500)
                
                pg_stat_statements_mean_exec_time_seconds.labels(
                    service=SERVICE_NAME
                ).observe(query_time)
            
            # === Kubernetes Metrics ===
            for pod in PODS:
                # All pods running (no pending/failed)
                kube_pod_status_phase.labels(
                    service=SERVICE_NAME,
                    phase='Running',
                    pod=pod
                ).set(1)
                
                kube_pod_status_phase.labels(
                    service=SERVICE_NAME,
                    phase='Pending',
                    pod=pod
                ).set(0)
                
                kube_pod_status_phase.labels(
                    service=SERVICE_NAME,
                    phase='Failed',
                    pod=pod
                ).set(0)
                
                # CPU usage (increment by small amounts to simulate usage)
                for _ in range(random.randint(8, 15)):
                    container_cpu_usage_seconds_total.labels(
                        service=SERVICE_NAME,
                        pod=pod,
                        container='payment-api'
                    ).inc(random.uniform(0.002, 0.008))
                
                # Memory usage (250-450 MB per pod)
                container_memory_working_set_bytes.labels(
                    service=SERVICE_NAME,
                    pod=pod,
                    container='payment-api'
                ).set(random.randint(250_000_000, 450_000_000))
            
            time.sleep(2)
            
        except Exception as e:
            print(f"Background traffic error: {e}")
            time.sleep(5)


# Start background traffic
threading.Thread(target=simulate_background_traffic, daemon=True).start()


@app.route('/')
def home():
    """Home page."""
    return jsonify({
        "service": "NthLayer Demo API",
        "version": "2.0.0",
        "description": "Demo with PostgreSQL and Kubernetes mock metrics",
        "endpoints": {
            "/health": "Health check",
            "/metrics": "Prometheus metrics (auth required)",
            "/api/payment": "POST - Simulate payment"
        },
        "metrics": {
            "http": "Service metrics (requests, latency, errors)",
            "postgresql": "Database metrics (connections, queries, cache hits)",
            "kubernetes": "Pod metrics (status, CPU, memory)"
        }
    })


@app.route('/health')
def health():
    """Health check."""
    return jsonify({
        "status": "healthy",
        "service": SERVICE_NAME,
        "timestamp": datetime.utcnow().isoformat()
    }), 200


@app.route('/metrics')
@requires_auth
def metrics():
    """Prometheus metrics endpoint."""
    return generate_latest(registry), 200, {'Content-Type': CONTENT_TYPE_LATEST}


@app.route('/api/payment', methods=['POST'])
def create_payment():
    """Simulate payment creation."""
    start = time.time()
    
    try:
        # Simulate database query
        time.sleep(random.uniform(0.01, 0.03))
        
        # Simulate error
        if random.random() < ERROR_RATE:
            http_requests_total.labels(
                service=SERVICE_NAME,
                method='POST',
                endpoint='/api/payment',
                status='500'
            ).inc()
            return jsonify({"error": "Payment failed"}), 500
        
        duration = time.time() - start
        
        http_requests_total.labels(
            service=SERVICE_NAME,
            method='POST',
            endpoint='/api/payment',
            status='200'
        ).inc()
        
        http_request_duration_seconds.labels(
            service=SERVICE_NAME,
            method='POST',
            endpoint='/api/payment'
        ).observe(duration)
        
        return jsonify({
            "payment_id": f"pay_{int(time.time() * 1000)}",
            "status": "completed",
            "duration_ms": int(duration * 1000)
        }), 200
        
    except Exception as e:
        return jsonify({"error": str(e)}), 500


if __name__ == '__main__':
    print(f"🚀 NthLayer Demo App (with PostgreSQL & K8s mocks)")
    print(f"📊 Service: {SERVICE_NAME}")
    print(f"📈 Metrics: /metrics")
    print(f"💚 Health: /health")
    print(f"🗄️  PostgreSQL metrics: ENABLED")
    print(f"☸️  Kubernetes metrics: ENABLED")
    
    app.run(host='0.0.0.0', port=8080, debug=False)
