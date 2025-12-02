#!/bin/bash
# Generate and push all demo service dashboards to Grafana Cloud

set -e  # Exit on error

cd "$(dirname "$0")"

# Load .env file if it exists
if [ -f .env ]; then
    echo "📝 Loading environment from .env file..."
    set -a  # Automatically export all variables
    source .env
    set +a
fi

# Check environment variables
if [ -z "$NTHLAYER_GRAFANA_URL" ]; then
    echo "❌ Error: NTHLAYER_GRAFANA_URL not set"
    echo "   Either:"
    echo "   1. Create .env file: echo 'NTHLAYER_GRAFANA_URL=https://nthlayer.grafana.net' >> .env"
    echo "   2. Or export: export NTHLAYER_GRAFANA_URL='https://nthlayer.grafana.net'"
    exit 1
fi

if [ -z "$NTHLAYER_GRAFANA_API_KEY" ]; then
    echo "❌ Error: NTHLAYER_GRAFANA_API_KEY not set"
    echo "   Either:"
    echo "   1. Create .env file: echo 'NTHLAYER_GRAFANA_API_KEY=glsa_...' >> .env"
    echo "   2. Or export: export NTHLAYER_GRAFANA_API_KEY='glsa_...'"
    exit 1
fi

echo "🚀 Generating Demo Dashboards for NthLayer Gallery"
echo "=================================================="
echo ""
echo "Grafana URL: $NTHLAYER_GRAFANA_URL"
echo ""

# Array of services to generate
services=(
    "payment-api"
    "checkout-service"
    "notification-worker"
    "analytics-stream"
    "identity-service"
)

total=${#services[@]}
count=0

for service in "${services[@]}"; do
    count=$((count + 1))
    echo "[$count/$total] Generating $service..."
    echo "────────────────────────────────────────"
    
    if [ ! -f "examples/services/$service.yaml" ]; then
        echo "⚠️  Warning: examples/services/$service.yaml not found, skipping"
        echo ""
        continue
    fi
    
    # Generate and push dashboard
    .venv/bin/python -m nthlayer.demo apply \
        "examples/services/$service.yaml" \
        --push-grafana
    
    echo ""
    echo "✅ $service dashboard pushed"
    echo ""
    
    # Small delay to avoid rate limiting
    sleep 2
done

echo "=================================================="
echo "🎉 All dashboards generated and pushed!"
echo ""
echo "View dashboards at:"
echo "  $NTHLAYER_GRAFANA_URL/dashboards"
echo ""
echo "Dashboard UIDs:"
for service in "${services[@]}"; do
    echo "  - $service-overview"
done
echo ""
echo "Next: Make dashboards public in Grafana Cloud"
