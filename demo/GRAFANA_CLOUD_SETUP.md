# Grafana Cloud Metrics Endpoint Setup

**Date:** December 1, 2025  
**Status:** Ready to Configure  
**Method:** Metrics Endpoint Integration (Agentless)

---

## Step-by-Step Instructions

### 1. Navigate to Metrics Endpoint Integration

In your Grafana Cloud instance:

1. Click **Home** (top-left)
2. Go to **Connections** → **Add new connection**
3. Search for: **"Metrics Endpoint"**
4. Click on the **Metrics Endpoint** integration

### 2. Configure Scrape Job

Fill in these details:

**Job Name (if prompted):**
```
nthlayer-demo
```

**Scrape Job URL:**
```
https://nthlayer-demo.fly.dev/metrics
```

**Type of Authentication Credentials:**
- Select: **Basic**

**Username:**
```
nthlayer
```

**Password:**
Get from Fly.io secrets:
```bash
flyctl secrets list | grep METRICS_PASSWORD
```

The password is stored in Fly.io secrets. To reveal it, you'll need to:

**Option A: Use the secret directly from Grafana Cloud**
Since Grafana Cloud is asking for credentials, enter:
- Username: `nthlayer`
- Password: Check the secret value that was set earlier

**Option B: Reset with a known password**
```bash
flyctl secrets set METRICS_PASSWORD="your-secure-password-here"
```

Then use that password in Grafana Cloud.

### 3. Test Connection

Click **"Test Connection"** button

**Expected result:**
```
✓ Connection successful
✓ Found 15+ metrics
✓ Metrics include: http_requests_total, error_budget_remaining_ratio, etc.
```

**If test fails:**
- Verify URL is correct (https://nthlayer-demo.fly.dev/metrics)
- Verify username is: `nthlayer`
- Verify password matches Fly.io secret
- Test manually:
  ```bash
  curl -u nthlayer:YOUR_PASSWORD https://nthlayer-demo.fly.dev/metrics
  # Should return Prometheus metrics, not 401
  ```

### 4. Save Scrape Job

Click **"Save Scrape Job"**

**Result:**
- Grafana Cloud will scrape your endpoint every 60 seconds
- Metrics will start appearing in 1-2 minutes

### 5. Wait for Metrics (1-2 minutes)

Grafana Cloud needs time to start scraping and ingesting metrics.

Wait 2-3 minutes, then proceed to verification.

### 6. Verify Metrics in Explore

1. Go to **Explore** in Grafana Cloud (compass icon in left sidebar)
2. Select data source: **"grafanacloud-yourorg-prom"** (dropdown at top)
3. Switch to **Code** mode
4. Run this query:
   ```promql
   http_requests_total
   ```

**Expected result:**
```
http_requests_total{endpoint="/api/payment", method="POST", service="payment-api", status="200"} 384
http_requests_total{endpoint="/api/payment", method="POST", service="payment-api", status="500"} 17
```

### 7. Verify Additional Metrics

Try these queries to confirm all metrics are flowing:

```promql
# Error budget
error_budget_remaining_ratio

# Database metrics
database_connections_total

# Cache metrics
cache_hits_total
cache_misses_total

# Service health
up{service="payment-api"}

# All metrics from this job
{job="nthlayer-demo"}
```

---

## Authentication Details

### Why Basic Auth?

Grafana Cloud's Metrics Endpoint integration requires authentication to scrape remote endpoints. We added Basic Auth to the Fly.io app's `/metrics` endpoint.

### Credentials

**Username:** `nthlayer` (fixed)  
**Password:** Stored in Fly.io secrets as `METRICS_PASSWORD`

**To get the password:**
```bash
# List secrets (shows digest only, not actual value)
flyctl secrets list

# To use a known password
flyctl secrets set METRICS_PASSWORD="your-password-here"
```

### Testing Locally

```bash
# Without auth (should fail with 401)
curl https://nthlayer-demo.fly.dev/metrics

# With auth (should return metrics)
curl -u nthlayer:YOUR_PASSWORD https://nthlayer-demo.fly.dev/metrics
```

---

## Troubleshooting

### Issue: Test connection fails with 401

**Solution:** Password doesn't match
```bash
# Reset password to known value
flyctl secrets set METRICS_PASSWORD="MySecurePassword123"

# Wait 30 seconds for app to restart

# Test
curl -u nthlayer:MySecurePassword123 https://nthlayer-demo.fly.dev/metrics

# Use same password in Grafana Cloud
```

### Issue: Test connection fails with timeout

**Solution:** Fly.io app might be down
```bash
# Check app status
flyctl status

# Check logs
flyctl logs

# Restart if needed
flyctl deploy
```

### Issue: No metrics appear in Explore after 5 minutes

**Solution 1:** Check scrape job status
- Go back to Connections → Metrics Endpoint
- Look for your "nthlayer-demo" job
- Check status (should be active/green)

**Solution 2:** Verify endpoint is working
```bash
curl -u nthlayer:PASSWORD https://nthlayer-demo.fly.dev/metrics | head -20
# Should return valid Prometheus metrics
```

**Solution 3:** Check data source
- Go to Connections → Data sources
- Find "grafanacloud-yourorg-prom"
- Click "Save & Test"
- Should show: "Data source is working"

---

## Security Best Practices

### 1. Strong Password
```bash
# Generate secure password
openssl rand -base64 24

# Set in Fly.io
flyctl secrets set METRICS_PASSWORD="<generated-password>"
```

### 2. Rotate Regularly
```bash
# Every 90 days, generate new password
openssl rand -base64 24

# Update in Fly.io
flyctl secrets set METRICS_PASSWORD="<new-password>"

# Update in Grafana Cloud
# Go to Metrics Endpoint → Edit scrape job → Update password
```

### 3. Restrict to Metrics Only
The authentication is ONLY on `/metrics` endpoint. Other endpoints (`/health`, `/api/*`) remain public for demo purposes.

---

## Next Steps

Once metrics are flowing:

1. ✅ Close beads issue:
   ```bash
   bd close trellis-948 --reason "Grafana Cloud Metrics Endpoint configured with Basic Auth. Scraping https://nthlayer-demo.fly.dev/metrics every 60s."
   ```

2. ✅ Check what's ready next:
   ```bash
   bd ready
   # Should show: trellis-oh2 (Import dashboard) - now unblocked!
   ```

3. ✅ Proceed to dashboard import:
   ```bash
   # Generate dashboard
   nthlayer apply examples/services/payment-api.yaml
   
   # Import to Grafana Cloud
   # (Next step in demo deployment)
   ```

---

## Summary

**What was done:**
- ✅ Added Basic Auth to Fly.io app (username: nthlayer)
- ✅ Deployed updated app to Fly.io
- ✅ Set credentials in Fly.io secrets

**What you need to do:**
1. Go to Grafana Cloud → Connections → Metrics Endpoint
2. Configure scrape job:
   - URL: https://nthlayer-demo.fly.dev/metrics
   - Auth: Basic
   - Username: nthlayer
   - Password: (from Fly.io secrets)
3. Test connection
4. Save scrape job
5. Wait 2 minutes
6. Verify in Explore

**Time:** 5 minutes

**Once working:** Close trellis-948 and move to dashboard import!

---

**Status:** ✅ READY - Follow steps above to complete Grafana Cloud configuration
