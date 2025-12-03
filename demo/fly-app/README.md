# NthLayer Demo App - Fly.io Deployment

This demo application generates realistic Prometheus metrics for showcasing NthLayer-generated dashboards.

## Quick Deploy

```bash
# 1. Install flyctl
curl -L https://fly.io/install.sh | sh

# 2. Login
flyctl auth login

# 3. Deploy (from this directory)
cd demo/fly-app
flyctl launch --name nthlayer-demo --region sjc

# 4. Set Grafana Cloud secrets (after getting them from Grafana Cloud)
flyctl secrets set \
  GRAFANA_REMOTE_WRITE_URL=https://prometheus-xxx.grafana.net/api/prom/push \
  GRAFANA_CLOUD_USER=123456 \
  GRAFANA_CLOUD_KEY=glc_xxxxx

# 5. Deploy
flyctl deploy

# 6. Get URL
flyctl info
# Your app: https://nthlayer-demo.fly.dev
```

## Endpoints

- `GET /` - API documentation
- `GET /health` - Health check
- `GET /metrics` - Prometheus metrics
- `POST /api/payment` - Create payment (generates metrics)
- `GET /api/payments/<id>` - Retrieve payment
- `POST /api/trigger-error` - Trigger error burst (demo)
- `POST /api/trigger-slow` - Trigger slow requests (demo)

## Grafana Cloud Setup

### 1. Create Grafana Cloud Account

1. Sign up: https://grafana.com/auth/sign-up (free)
2. Create workspace: "nthlayer-demo"
3. Go to: Administration → Connections → Add new connection → Prometheus

### 2. Get Remote Write Credentials

In Prometheus data source configuration:
- **Remote Write URL:** `https://prometheus-xxx.grafana.net/api/prom/push`
- **Username:** Your instance ID (e.g., `123456`)
- **Password:** API token (starts with `glc_`)

### 3. Configure Fly.io App

```bash
flyctl secrets set \
  GRAFANA_REMOTE_WRITE_URL=<your-url> \
  GRAFANA_CLOUD_USER=<your-username> \
  GRAFANA_CLOUD_KEY=<your-api-key>
```

### 4. Import Dashboard

1. Go to Grafana Cloud
2. Import dashboard from: `../../generated/examples/payment-api/dashboard.json`
3. Select Prometheus data source
4. Save

### 5. Make Dashboard Public

1. Open dashboard
2. Click Share → Public dashboard
3. Enable public access
4. Copy public URL: `https://yourorg.grafana.net/public-dashboards/abc123`
5. Use this URL in README and GitHub Pages

## Testing Locally

```bash
# Build and run
docker build -t nthlayer-demo .
docker run -p 8080:8080 nthlayer-demo

# Test endpoints
curl http://localhost:8080/health
curl http://localhost:8080/metrics

# Generate traffic
for i in {1..100}; do
  curl -X POST http://localhost:8080/api/payment
done
```

## Monitoring

```bash
# View logs
flyctl logs

# Check status
flyctl status

# SSH into VM
flyctl ssh console

# Scale (if needed - costs money)
flyctl scale count 1
```

## Free Tier Limits

**Fly.io Free Tier:**
- 3 shared-cpu-1x VMs (256MB RAM each)
- 160GB outbound bandwidth/month
- **Perfect for demo** - no credit card required

**What happens if over limit:**
- App stops
- Need to upgrade to paid plan

**Tips to stay within free tier:**
- Keep to 1 VM
- Use resource.limits in fly.toml
- Monitor bandwidth usage

## Troubleshooting

**App not starting:**
```bash
flyctl logs
# Check for Python errors
```

**Metrics not appearing in Grafana Cloud:**
```bash
# Verify secrets are set
flyctl secrets list

# Check app logs
flyctl logs | grep -i grafana

# Test metrics endpoint
curl https://nthlayer-demo.fly.dev/metrics
```

**Free tier exceeded:**
```bash
# Check usage
flyctl dashboard

# Scale down if needed
flyctl scale count 1
```

## Cost Monitoring

```bash
# View usage
flyctl dashboard

# Stay in free tier:
# - 1 VM only
# - Monitor bandwidth
# - No volumes (persistent storage costs money)
```

---

**Deployed URL:** https://nthlayer-demo.fly.dev  
**Metrics Endpoint:** https://nthlayer-demo.fly.dev/metrics  
**Cost:** $0/month (free tier)
