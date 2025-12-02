"""
NthLayer Demo Application

Generates realistic metrics for demonstration purposes.
Pushes metrics to Grafana Cloud via Prometheus remote_write.
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

# Metrics (matching NthLayer generated SLOs)
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

# Database metrics
db_connections_total = Gauge(
    'database_connections_total',
    'Total database connections',
    ['service', 'database'],
    registry=registry
)

db_query_duration_seconds = Histogram(
    'database_query_duration_seconds',
    'Database query duration',
    ['service', 'database', 'query_type'],
    registry=registry
)

# Cache metrics
cache_hits_total = Counter(
    'cache_hits_total',
    'Total cache hits',
    ['service', 'cache'],
    registry=registry
)

cache_misses_total = Counter(
    'cache_misses_total',
    'Total cache misses',
    ['service', 'cache'],
    registry=registry
)

# Service health
service_up = Gauge(
    'up',
    'Service is up',
    ['service', 'instance'],
    registry=registry
)

# Configuration
SERVICE_NAME = 'payment-api'
ERROR_RATE = float(os.environ.get('ERROR_RATE', '0.05'))  # 5% default
SLOW_REQUEST_RATE = float(os.environ.get('SLOW_REQUEST_RATE', '0.10'))  # 10% default

# Initialize service as up
service_up.labels(service=SERVICE_NAME, instance='demo-1').set(1)


def simulate_background_traffic():
    """Background thread that generates traffic to simulate real usage."""
    while True:
        try:
            # Simulate some requests
            for _ in range(random.randint(5, 15)):
                # Simulate successful request
                if random.random() > ERROR_RATE:
                    duration = random.uniform(0.05, 0.3)
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
                else:
                    # Simulate error
                    http_requests_total.labels(
                        service=SERVICE_NAME,
                        method='POST',
                        endpoint='/api/payment',
                        status='500'
                    ).inc()
                
                time.sleep(random.uniform(0.5, 2.0))
            
            # Update error budget
            availability_budget = max(0, 1.0 - (ERROR_RATE * 1.5))
            latency_budget = 0.92
            
            error_budget_remaining_ratio.labels(
                service=SERVICE_NAME,
                slo='availability'
            ).set(availability_budget)
            
            error_budget_remaining_ratio.labels(
                service=SERVICE_NAME,
                slo='latency-p95'
            ).set(latency_budget)
            
            # Simulate database metrics
            db_connections_total.labels(
                service=SERVICE_NAME,
                database='postgresql'
            ).set(random.randint(10, 50))
            
            db_query_duration_seconds.labels(
                service=SERVICE_NAME,
                database='postgresql',
                query_type='SELECT'
            ).observe(random.uniform(0.001, 0.05))
            
            # Simulate cache metrics
            if random.random() < 0.7:
                cache_hits_total.labels(service=SERVICE_NAME, cache='redis').inc()
            else:
                cache_misses_total.labels(service=SERVICE_NAME, cache='redis').inc()
            
        except Exception as e:
            print(f"Background traffic error: {e}")
        
        time.sleep(5)


# Start background traffic
threading.Thread(target=simulate_background_traffic, daemon=True).start()


@app.route('/')
def home():
    """Home page with API documentation."""
    return jsonify({
        "service": "NthLayer Demo API",
        "version": "1.0.0",
        "description": "Demo application generating metrics for NthLayer showcase",
        "endpoints": {
            "/health": "Health check",
            "/metrics": "Prometheus metrics",
            "/api/payment": "POST - Create payment (generates metrics)",
            "/api/payments/<id>": "GET - Retrieve payment",
            "/api/trigger-error": "POST - Trigger error scenario",
            "/api/trigger-slow": "POST - Trigger slow request scenario"
        },
        "demo": {
            "grafana": "https://yourorg.grafana.net",
            "documentation": "https://github.com/yourorg/nthlayer"
        }
    })


@app.route('/health')
def health():
    """Health check endpoint."""
    return jsonify({
        "status": "healthy",
        "service": SERVICE_NAME,
        "timestamp": datetime.utcnow().isoformat(),
        "metrics": {
            "requests_total": "available at /metrics",
            "error_rate": f"{ERROR_RATE * 100}%",
            "error_budget": "85-95% remaining"
        }
    }), 200


@app.route('/metrics')
@requires_auth
def metrics():
    """Prometheus metrics endpoint (requires basic auth)."""
    return generate_latest(registry), 200, {'Content-Type': CONTENT_TYPE_LATEST}


@app.route('/api/payment', methods=['POST'])
def create_payment():
    """Simulate payment creation."""
    start = time.time()
    
    try:
        # Simulate database query
        time.sleep(random.uniform(0.01, 0.05))
        db_query_duration_seconds.labels(
            service=SERVICE_NAME,
            database='postgresql',
            query_type='INSERT'
        ).observe(random.uniform(0.01, 0.05))
        
        # Simulate cache lookup
        if random.random() < 0.7:
            cache_hits_total.labels(service=SERVICE_NAME, cache='redis').inc()
        else:
            cache_misses_total.labels(service=SERVICE_NAME, cache='redis').inc()
            time.sleep(random.uniform(0.02, 0.08))
        
        # Simulate errors
        if random.random() < ERROR_RATE:
            http_requests_total.labels(
                service=SERVICE_NAME,
                method='POST',
                endpoint='/api/payment',
                status='500'
            ).inc()
            return jsonify({"error": "Internal Server Error", "code": "PAYMENT_FAILED"}), 500
        
        # Simulate slow requests
        if random.random() < SLOW_REQUEST_RATE:
            time.sleep(random.uniform(0.5, 1.5))
        
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
        
        payment_id = f"pay_{int(time.time() * 1000)}"
        
        return jsonify({
            "payment_id": payment_id,
            "status": "completed",
            "amount": 100.00,
            "duration_ms": int(duration * 1000)
        }), 200
        
    except Exception as e:
        http_requests_total.labels(
            service=SERVICE_NAME,
            method='POST',
            endpoint='/api/payment',
            status='500'
        ).inc()
        return jsonify({"error": str(e)}), 500


@app.route('/api/payments/<payment_id>')
def get_payment(payment_id):
    """Simulate payment retrieval."""
    start = time.time()
    
    # Fast read operation
    time.sleep(random.uniform(0.005, 0.02))
    
    # Check cache first
    if random.random() < 0.9:
        cache_hits_total.labels(service=SERVICE_NAME, cache='redis').inc()
    else:
        cache_misses_total.labels(service=SERVICE_NAME, cache='redis').inc()
        db_query_duration_seconds.labels(
            service=SERVICE_NAME,
            database='postgresql',
            query_type='SELECT'
        ).observe(random.uniform(0.01, 0.03))
    
    duration = time.time() - start
    
    http_requests_total.labels(
        service=SERVICE_NAME,
        method='GET',
        endpoint='/api/payments/:id',
        status='200'
    ).inc()
    
    http_request_duration_seconds.labels(
        service=SERVICE_NAME,
        method='GET',
        endpoint='/api/payments/:id'
    ).observe(duration)
    
    return jsonify({
        "payment_id": payment_id,
        "amount": 100.00,
        "status": "completed",
        "created_at": datetime.utcnow().isoformat()
    }), 200


@app.route('/api/trigger-error', methods=['POST'])
def trigger_error():
    """Trigger a burst of errors for demo purposes."""
    for _ in range(20):
        http_requests_total.labels(
            service=SERVICE_NAME,
            method='POST',
            endpoint='/api/payment',
            status='500'
        ).inc()
    
    return jsonify({
        "message": "Triggered 20 errors",
        "check": "Prometheus alerts in 2-3 minutes"
    }), 200


@app.route('/api/trigger-slow', methods=['POST'])
def trigger_slow():
    """Trigger slow requests for demo purposes."""
    for _ in range(10):
        duration = random.uniform(2.0, 5.0)
        http_request_duration_seconds.labels(
            service=SERVICE_NAME,
            method='POST',
            endpoint='/api/payment'
        ).observe(duration)
        http_requests_total.labels(
            service=SERVICE_NAME,
            method='POST',
            endpoint='/api/payment',
            status='200'
        ).inc()
    
    return jsonify({
        "message": "Triggered 10 slow requests (2-5s each)",
        "check": "Dashboard latency panels"
    }), 200


if __name__ == '__main__':
    print(f"🚀 NthLayer Demo App starting...")
    print(f"📊 Service: {SERVICE_NAME}")
    print(f"⚠️  Error rate: {ERROR_RATE * 100}%")
    print(f"🐌 Slow request rate: {SLOW_REQUEST_RATE * 100}%")
    print(f"📈 Metrics endpoint: /metrics")
    print(f"💚 Health endpoint: /health")
    
    app.run(host='0.0.0.0', port=8080, debug=False)
