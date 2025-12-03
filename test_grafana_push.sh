#!/bin/bash
# Minimal test to push one dashboard

set -e
cd "$(dirname "$0")"

# Load .env
if [ -f .env ]; then
    echo "📝 Loading .env..."
    set -a
    source .env
    set +a
else
    echo "❌ .env not found"
    exit 1
fi

# Check vars are set
echo "Checking environment variables:"
echo "  NTHLAYER_GRAFANA_URL: $NTHLAYER_GRAFANA_URL"
echo "  NTHLAYER_GRAFANA_API_KEY: ${NTHLAYER_GRAFANA_API_KEY:0:15}..."
echo ""

# Test Python can see them
echo "Testing Python can see environment:"
.venv/bin/python << 'PYEOF'
import os
url = os.getenv('NTHLAYER_GRAFANA_URL')
key = os.getenv('NTHLAYER_GRAFANA_API_KEY')
print(f"  URL: {url}")
print(f"  Key: {key[:15] if key else 'NOT SET'}...")
if not url or not key:
    print("❌ Python cannot see environment variables!")
    exit(1)
print("✅ Python can see environment variables")
PYEOF

echo ""
echo "Generating payment-api dashboard with push..."
.venv/bin/python -m nthlayer.demo apply \
    examples/services/payment-api.yaml \
    --push-grafana

echo ""
echo "Done!"
