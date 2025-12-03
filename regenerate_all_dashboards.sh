#!/bin/bash
set -e

echo "======================================================================"
echo "  Week 1 Task 3: Regenerate All 5 Dashboards with Validation"
echo "======================================================================"
echo

# Source environment variables
source .env

services=("payment-api" "checkout-service" "notification-worker" "analytics-stream" "identity-service")

total_panels_before=0
total_panels_after=0
total_warnings=0

for service in "${services[@]}"; do
    echo "----------------------------------------------------------------------"
    echo "Processing: $service"
    echo "----------------------------------------------------------------------"
    
    # Generate WITH validation
    echo "🔍 Generating with validation..."
    NTHLAYER_METRICS_URL="${NTHLAYER_METRICS_URL}" \
    NTHLAYER_METRICS_USER="${NTHLAYER_METRICS_USER}" \
    NTHLAYER_METRICS_PASSWORD="${NTHLAYER_METRICS_PASSWORD}" \
    NTHLAYER_GRAFANA_URL="${NTHLAYER_GRAFANA_URL}" \
    NTHLAYER_GRAFANA_API_KEY="${NTHLAYER_GRAFANA_API_KEY}" \
    .venv/bin/python -m nthlayer.demo apply "examples/services/${service}.yaml" --push-grafana 2>&1 | tee "generated/${service}/validation.log"
    
    echo "✅ $service complete"
    echo
done

echo "======================================================================"
echo "  All Dashboards Regenerated"
echo "======================================================================"
echo
echo "Check validation logs in generated/*/validation.log"
