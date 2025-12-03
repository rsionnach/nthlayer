# Import NthLayer Dashboard to Grafana Cloud

**Task:** trellis-oh2  
**Status:** Ready to Import  
**Dashboard:** `generated/payment-api/dashboard.json`

---

## Step-by-Step Instructions

### 1. Prepare Dashboard File

The dashboard is already generated at:
```
/Users/robfox/trellis/generated/payment-api/dashboard.json
```

Open this file in your editor to copy the contents, or use:
```bash
cat generated/payment-api/dashboard.json | pbcopy
# Copies to clipboard on macOS
```

### 2. Import to Grafana Cloud

In your Grafana Cloud instance:

1. Click **Dashboards** (four squares icon in left sidebar)
2. Click **New** button (top-right)
3. Select **Import**
4. In the import screen, you have two options:

**Option A: Paste JSON**
- Click **"Import via panel json"** or **"Upload JSON file"**
- Paste the contents of `dashboard.json`
- Click **Load**

**Option B: Upload File**
- Click **"Upload JSON file"**
- Select `generated/payment-api/dashboard.json`
- Click **Open**

### 3. Configure Import Settings

You'll see an import configuration screen:

**Name:** 
```
NthLayer Demo - Payment API
```

**Folder:**
- Select: **General** or create new folder: **"NthLayer Demos"**

**UID:**
- Leave as auto-generated or use: `nthlayer-payment-api`

**Prometheus Data Source:**
- Select your Prometheus data source
- Should be: **"grafanacloud-yourorg-prom"** or **"Prometheus"**
- This is CRITICAL - must match your data source name

### 4. Click Import

Click the **Import** button

**Expected result:**
- Dashboard appears with 12 panels
- Some panels may show "No data" initially (normal if metrics just started)
- Within 1-2 minutes, panels should populate with real data

### 5. Make Dashboard Public

To embed in your demo site:

1. Click **Share** button (share icon, top-right of dashboard)
2. Select **Public dashboard** tab
3. Toggle **"Enabled"** to ON
4. Click **Save sharing configuration**
5. Copy the **Public dashboard URL**

**Public URL format:**
```
https://yourorg.grafana.net/public-dashboards/abc123def456...
```

This URL can be embedded in iframes without authentication.

### 6. Test Public Access

Open the public URL in an **incognito/private browser window**:
- Should show dashboard without login
- Should update with live data
- Should be embeddable in iframe

### 7. Get Embed Code

In the Share dialog:

1. Go to **Public dashboard** tab
2. Look for **Embed** section
3. Copy the iframe code:
   ```html
   <iframe 
     src="https://yourorg.grafana.net/public-dashboards/abc123..." 
     width="100%" 
     height="600px"
     frameborder="0">
   </iframe>
   ```

---

## What the Dashboard Shows

The NthLayer-generated dashboard includes **12 panels**:

### SLO Tracking (3 panels)
1. **Availability SLO** - Gauge showing 99.9% target vs current
2. **Latency p95 SLO** - Time series showing 500ms target
3. **Latency p99 SLO** - Time series showing 1000ms target

### Service Health (3 panels)
4. **Request Rate** - Requests per second
5. **Error Rate** - 4xx and 5xx percentage
6. **Response Time** - p50, p95, p99 latencies

### PostgreSQL Metrics (3 panels)
7. **Connection Pool** - Active connections / max
8. **Query Duration** - Average query time
9. **Slow Queries** - Count of queries > 1s

### Redis Metrics (3 panels)
10. **Cache Hit Rate** - Hits / (hits + misses)
11. **Memory Usage** - Current vs max
12. **Operations/sec** - Get, set, del rates

---

## Troubleshooting

### Issue: No data in panels

**Causes:**
1. **Wrong data source selected** during import
   - Fix: Edit dashboard → Settings → Variables → Update data source
   
2. **Metrics just started flowing**
   - Wait 2-3 minutes for data to accumulate
   
3. **Metric names don't match**
   - Fix: Check query in panel edit mode
   - Verify metric exists: Go to Explore, run query

### Issue: Some panels show "No data"

**This is expected for:**
- Database query duration (no actual database queries in demo)
- Slow queries (demo generates fast queries only)
- Some cache metrics (depending on traffic pattern)

**Working panels should be:**
- Request rate (definitely has data)
- Error rate (has 5% errors)
- Response time (has latency data)
- Error budget gauge (has ratio data)

### Issue: Can't make dashboard public

**Requirements:**
- Must be on Grafana Cloud (not self-hosted Grafana)
- Must have permissions (Admin or Editor role)
- Some orgs disable public dashboards (check org settings)

**If disabled:**
- Ask org admin to enable public dashboards
- Or use sharing link (requires login, but still works)

### Issue: Dashboard looks empty/broken

**Check:**
```bash
# Verify metrics exist in Explore
# Go to Explore, run:
http_requests_total{service="payment-api"}

# Should return data
# If not, wait 2-3 more minutes
```

---

## Expected Dashboard Appearance

### Top Row (SLO Gauges)
```
┌─────────────┐  ┌─────────────┐  ┌─────────────┐
│ Availability│  │ Latency p95 │  │ Latency p99 │
│   99.92%    │  │   485ms     │  │   987ms     │
│  Target:    │  │  Target:    │  │  Target:    │
│   99.9%     │  │   500ms     │  │   1000ms    │
│  ✅ PASS    │  │  ✅ PASS    │  │  ✅ PASS    │
└─────────────┘  └─────────────┘  └─────────────┘
```

### Middle Row (Service Health Time Series)
```
┌──────────────────────────────────────────────────┐
│ Request Rate                                     │
│ [Line graph showing requests/sec over time]      │
└──────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────┐
│ Error Rate (%)                                   │
│ [Line graph showing 5% error rate]               │
└──────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────┐
│ Response Time (p50, p95, p99)                    │
│ [Three lines showing latency percentiles]        │
└──────────────────────────────────────────────────┘
```

### Bottom Rows (Dependencies)
PostgreSQL panels, Redis panels (may show "No data" for demo)

---

## After Import

Once dashboard is imported and public:

1. ✅ Copy the public dashboard URL
2. ✅ Close trellis-oh2:
   ```bash
   bd close trellis-oh2 --reason "Dashboard imported to Grafana Cloud as 'NthLayer Demo - Payment API'. Made public. URL: https://yourorg.grafana.net/public-dashboards/..."
   ```

3. ✅ Update beads with URL:
   ```bash
   bd comment trellis-oh2 "Public dashboard URL: https://yourorg.grafana.net/public-dashboards/abc123"
   ```

4. ✅ Check what's ready next:
   ```bash
   bd ready
   # Will show: trellis-tl4 (Enable GitHub Pages) - now unblocked!
   ```

---

## Quick Start

**Right now, do this:**

1. Open Grafana Cloud
2. Go to Dashboards → New → Import
3. Upload: `/Users/robfox/trellis/generated/payment-api/dashboard.json`
4. Select Prometheus data source
5. Click Import
6. Click Share → Public dashboard → Enable
7. Copy public URL

Then close trellis-oh2 and move to GitHub Pages setup!

**Time:** 5 minutes
