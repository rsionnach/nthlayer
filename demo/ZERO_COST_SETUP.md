# Zero-Cost Live Demo Setup Guide

Complete guide to deploying NthLayer's live demo using 100% free services.

**Total Cost:** $0/month forever  
**Setup Time:** ~4 hours  
**Services:** Grafana Cloud + Fly.io + GitHub Pages

---

## Overview

This guide walks you through setting up a publicly accessible demo that showcases NthLayer-generated observability resources.

**What you'll deploy:**
1. **Grafana Cloud** - Public dashboards with live metrics
2. **Fly.io** - Demo app generating realistic metrics
3. **GitHub Pages** - Interactive demo website
4. **GitHub README** - Embedded dashboard

---

## Prerequisites

- GitHub account
- Terminal/command line access
- Git installed
- Python 3.9+ installed

---

## Part 1: Grafana Cloud Setup (30 minutes)

### Step 1.1: Create Account

1. Go to: https://grafana.com/auth/sign-up
2. Sign up with email (free tier, no credit card required)
3. Create organization: `nthlayer-demo` (or your choice)
4. Select region: closest to you

### Step 1.2: Get Prometheus Remote Write Credentials

1. In Grafana Cloud, go to: **My Account → Stack → Details**
2. Find **Prometheus** section
3. Click **Details** → **Remote Write**
4. Copy these values:

```bash
# You'll need these for Fly.io setup:
GRAFANA_REMOTE_WRITE_URL=https://prometheus-xxx.grafana.net/api/prom/push
GRAFANA_CLOUD_USER=123456
GRAFANA_CLOUD_KEY=glc_xxxxxxxxxxxx
```

**Note:** Keep these credentials secure!

### Step 1.3: Create API Token

1. Go to: **Administration → Users and access → API keys**
2. Click **Add API key**
3. Name: `nthlayer-demo`
4. Role: `Editor`
5. Copy the key (starts with `glc_`)

### Step 1.4: Configure Prometheus Data Source

1. Go to: **Connections → Data sources**
2. Prometheus should already be configured
3. Test connection
4. Note the data source name (usually `grafanacloud-<your-org>-prom`)

---

## Part 2: Fly.io Demo App (2 hours)

### Step 2.1: Install Fly CLI

**macOS:**
```bash
curl -L https://fly.io/install.sh | sh
```

**Linux:**
```bash
curl -L https://fly.io/install.sh | sh
```

**Windows:**
```powershell
powershell -Command "iwr https://fly.io/install.ps1 -useb | iex"
```

Verify installation:
```bash
flyctl version
```

### Step 2.2: Login to Fly.io

```bash
flyctl auth login
```

This opens your browser for authentication. **No credit card required** for free tier!

### Step 2.3: Deploy Demo App

```bash
# Navigate to demo app directory
cd demo/fly-app

# Launch app (follow prompts)
flyctl launch --name nthlayer-demo

# Select region: Choose closest to you
# Example: sjc (San Jose), iad (Virginia), fra (Frankfurt)

# Deploy
flyctl deploy
```

**Expected output:**
```
==> Creating app nthlayer-demo
--> App created
==> Building image
--> Building Dockerfile
==> Pushing image
==> Deploying
--> v0 deployed successfully

Visit your newly deployed app at:
https://nthlayer-demo.fly.dev
```

### Step 2.4: Configure Secrets

Set Grafana Cloud credentials from Part 1:

```bash
flyctl secrets set \
  GRAFANA_REMOTE_WRITE_URL="https://prometheus-xxx.grafana.net/api/prom/push" \
  GRAFANA_CLOUD_USER="123456" \
  GRAFANA_CLOUD_KEY="glc_xxxxxxxxxxxx"
```

This restarts the app automatically.

### Step 2.5: Verify Metrics

```bash
# Check app status
flyctl status

# View logs
flyctl logs

# Test metrics endpoint
curl https://nthlayer-demo.fly.dev/metrics

# Test health endpoint
curl https://nthlayer-demo.fly.dev/health
```

**Expected:** Should see Prometheus-formatted metrics

### Step 2.6: Wait for Metrics in Grafana Cloud

1. Go to Grafana Cloud → **Explore**
2. Select Prometheus data source
3. Query: `http_requests_total`
4. Wait 1-2 minutes for metrics to appear
5. Verify you see data

**Troubleshooting:**
- No metrics? Check `flyctl logs` for errors
- Verify secrets: `flyctl secrets list`
- Test remote_write URL: Check credentials

---

## Part 3: Import Dashboard to Grafana Cloud (30 minutes)

### Step 3.1: Generate Example Dashboard

If you haven't already:

```bash
# From repo root
nthlayer apply examples/services/payment-api.yaml

# Dashboard JSON created at:
ls generated/payment-api/dashboard.json
```

### Step 3.2: Import to Grafana Cloud

1. Go to Grafana Cloud → **Dashboards** → **Import**
2. Click **Upload JSON file**
3. Select: `generated/payment-api/dashboard.json`
4. Configure:
   - **Name:** NthLayer Demo - Payment API
   - **Folder:** General
   - **Prometheus:** Select your Grafana Cloud Prometheus data source
5. Click **Import**

### Step 3.3: Adjust Dashboard Variables

The dashboard uses these metrics from the demo app:
- `http_requests_total`
- `http_request_duration_seconds`
- `error_budget_remaining_ratio`
- `database_connections_total`
- `cache_hits_total` / `cache_misses_total`

**Fix any broken panels:**
1. Edit dashboard
2. For each panel with no data:
   - Check the query
   - Ensure metric exists: Go to Explore → query the metric
   - Adjust label selectors to match your app (service="payment-api")

### Step 3.4: Make Dashboard Public

1. Open the dashboard
2. Click **Share** (top right)
3. Go to **Public dashboard** tab
4. Toggle **Enabled**
5. Configure:
   - **Time range picker:** Enabled
   - **Annotations:** Disabled (optional)
   - **Default time range:** Last 6 hours
6. Click **Save public dashboard**
7. **Copy the public URL:**

```
https://yourorg.grafana.net/public-dashboards/abc123xyz
```

**Save this URL!** You'll use it in README and GitHub Pages.

### Step 3.5: Test Public Dashboard

1. Open the public URL in incognito/private window
2. Verify:
   - ✅ Dashboard loads without login
   - ✅ Panels show live data
   - ✅ Data refreshes automatically
   - ✅ Time range selector works

---

## Part 4: GitHub Pages Demo Site (1 hour)

### Step 4.1: Update Demo Site HTML

Edit `docs/index.html` and replace placeholder:

```html
<!-- Find this section (around line 200) -->
<div class="dashboard-placeholder">
    <!-- ... placeholder content ... -->
</div>

<!-- Replace with: -->
<div class="dashboard-embed">
    <iframe 
        src="https://yourorg.grafana.net/public-dashboards/abc123xyz"
        width="100%" 
        height="600"
        frameborder="0">
    </iframe>
</div>
<div class="dashboard-actions">
    <a href="https://yourorg.grafana.net/public-dashboards/abc123xyz" 
       target="_blank" 
       class="button-secondary">
        Open Full Dashboard →
    </a>
</div>
```

### Step 4.2: Update Links

Replace placeholder URLs throughout `docs/index.html`:
- Replace `yourorg` with your GitHub org/username
- Update all GitHub links

### Step 4.3: Enable GitHub Pages

1. Go to GitHub repo → **Settings** → **Pages**
2. Source: **Deploy from a branch**
3. Branch: `main` (or your default branch)
4. Folder: `/docs`
5. Click **Save**

### Step 4.4: Wait for Deployment

- GitHub Actions will deploy (2-3 minutes)
- Check: **Actions** tab for progress
- Site will be live at: `https://yourorg.github.io/nthlayer`

### Step 4.5: Test Demo Site

1. Visit: `https://yourorg.github.io/nthlayer`
2. Verify:
   - ✅ Page loads with styling
   - ✅ Embedded Grafana dashboard works
   - ✅ All links work
   - ✅ Navigation smooth scrolls

---

## Part 5: Update README (30 minutes)

### Step 5.1: Add Live Demo Section

Add this to your `README.md` after the title/description:

```markdown
## 🌐 Live Demo

**See NthLayer-generated observability in action:**

[![Live Dashboard](https://img.shields.io/badge/Live-Dashboard-blue?logo=grafana&style=for-the-badge)](https://yourorg.grafana.net/public-dashboards/abc123)
[![Interactive Demo](https://img.shields.io/badge/Try-Interactive%20Demo-green?style=for-the-badge)](https://yourorg.github.io/nthlayer)

### Quick Preview

<details>
<summary>📊 Click to view live embedded dashboard</summary>

<br>

<iframe 
    src="https://yourorg.grafana.net/public-dashboards/abc123" 
    width="100%" 
    height="600px"
    frameborder="0">
</iframe>

*Live dashboard showing auto-generated SLO tracking, health metrics, and technology-specific monitoring. Data updates in real-time from our demo app.*

</details>

**🎮 Explore More:**
- [Interactive Demo Site](https://yourorg.github.io/nthlayer) - Step-by-step walkthrough
- [Live Grafana Dashboard](https://yourorg.grafana.net/public-dashboards/abc123) - Open in new tab
- [Demo App](https://nthlayer-demo.fly.dev) - API generating live metrics
- [Example Configs](./generated/examples/) - See what NthLayer generates
```

### Step 5.2: Add Demo Section to Table of Contents

Update your README's table of contents:

```markdown
## Table of Contents

- [Live Demo](#-live-demo) ⭐ **NEW**
- [Features](#features)
- [Getting Started](#getting-started)
...
```

### Step 5.3: Commit and Push

```bash
git add docs/ demo/fly-app/ README.md
git commit -m "Add zero-cost live demo infrastructure

- Fly.io demo app with realistic metrics
- GitHub Pages interactive demo site
- Grafana Cloud public dashboard
- Embedded dashboard in README

Co-authored-by: factory-droid[bot] <138933559+factory-droid[bot]@users.noreply.github.com>"

git push origin main
```

---

## Part 6: Verification (15 minutes)

### Checklist

Run through this checklist:

- [ ] **Fly.io app running**
  - Visit: `https://nthlayer-demo.fly.dev/health`
  - Should return: `{"status": "healthy"}`

- [ ] **Metrics flowing to Grafana Cloud**
  - Grafana → Explore
  - Query: `rate(http_requests_total[5m])`
  - Should see data

- [ ] **Public dashboard accessible**
  - Visit public URL in incognito mode
  - No login required
  - Panels show data

- [ ] **GitHub Pages site live**
  - Visit: `https://yourorg.github.io/nthlayer`
  - Embedded dashboard works
  - All sections load

- [ ] **README updated**
  - Badge links work
  - Embedded iframe shows (on GitHub)
  - Links point to correct URLs

---

## Maintenance

### Monthly Checks (15 minutes/month)

**Check Fly.io:**
```bash
flyctl status
flyctl logs --limit 100
```

**Check Grafana Cloud:**
- Verify metrics still flowing
- Check data source status
- Ensure public dashboard still accessible

**Check GitHub Pages:**
- Visit demo site
- Test all links
- Verify embedded dashboard

### Update Demo Content

When you change NthLayer configs:

```bash
# Regenerate
nthlayer apply examples/services/payment-api.yaml

# Re-import dashboard to Grafana Cloud
# (Dashboards → Import → Upload new JSON)

# Commit changes
git add generated/
git commit -m "Update demo configs"
git push
```

---

## Troubleshooting

### Fly.io App Not Starting

```bash
# Check logs
flyctl logs

# Common issues:
# - Missing secrets: flyctl secrets list
# - Build error: Check Dockerfile
# - Port conflict: fly.toml uses port 8080

# Restart app
flyctl apps restart nthlayer-demo
```

### Metrics Not Appearing in Grafana Cloud

```bash
# Test metrics endpoint
curl https://nthlayer-demo.fly.dev/metrics

# Check if remote_write is configured
flyctl secrets list

# View app logs for errors
flyctl logs | grep -i grafana

# Test remote_write manually
curl -X POST \
  -u "$GRAFANA_CLOUD_USER:$GRAFANA_CLOUD_KEY" \
  "$GRAFANA_REMOTE_WRITE_URL" \
  -H "Content-Type: application/x-protobuf" \
  --data-binary @metrics.pb
```

**Fix:** Verify credentials are correct in Fly.io secrets

### Dashboard Panels Empty

1. **Check data source:**
   - Dashboard settings → Variables
   - Ensure Prometheus data source selected

2. **Check metric names:**
   - Explore → Query: `{__name__=~"http.*"}`
   - Verify metric names match dashboard queries

3. **Check label selectors:**
   - Dashboard queries use: `service="payment-api"`
   - Ensure demo app emits this label

### GitHub Pages Not Updating

```bash
# Check GitHub Actions
# Repo → Actions → pages-build-deployment

# Common issues:
# - /docs folder not in branch
# - HTML syntax errors
# - Settings → Pages → Source not set

# Force rebuild
git commit --allow-empty -m "Trigger Pages rebuild"
git push
```

### Public Dashboard Inaccessible

1. **Verify public access enabled:**
   - Dashboard → Share → Public dashboard
   - Toggle should be ON

2. **Check URL format:**
   - Correct: `https://org.grafana.net/public-dashboards/abc123`
   - Wrong: `https://org.grafana.net/d/abc123` (not public)

3. **Test in incognito:**
   - Should load without login
   - If prompted for login, public access not enabled

---

## Cost Monitoring

### Grafana Cloud Free Tier

**Limits:**
- 10,000 Prometheus series
- 50GB logs per month
- 50GB traces per month

**Check usage:**
- Administration → Usage & billing
- Monitor active series count

**Stay within limits:**
- Demo app generates ~50-100 series
- Well within free tier
- Alert if approaching 5,000 series

### Fly.io Free Tier

**Limits:**
- 3 shared-cpu-1x VMs (256MB RAM)
- 160GB outbound bandwidth/month

**Check usage:**
```bash
flyctl dashboard
# View machines and bandwidth
```

**Stay within limits:**
- Use 1 VM only
- Demo traffic is minimal
- Should use <1GB/month bandwidth

### GitHub Pages

**Limits:**
- 100GB bandwidth/month
- 1GB storage

**Check usage:**
- Repo → Settings → Pages
- Static site uses <1MB

---

## Advanced: Custom Domain (Optional)

If you want `demo.nthlayer.com` instead of `yourorg.github.io/nthlayer`:

### For GitHub Pages:

1. Buy domain ($12/year): Namecheap, Cloudflare, etc.
2. Add DNS records:
   ```
   CNAME: demo.nthlayer.com → yourorg.github.io
   ```
3. GitHub: Settings → Pages → Custom domain: `demo.nthlayer.com`
4. Wait for DNS propagation (5-60 minutes)

### For Fly.io:

```bash
# Add certificate
flyctl certs add api.demo.nthlayer.com

# Get DNS instructions
flyctl certs show api.demo.nthlayer.com

# Add DNS records as instructed
```

**Cost:** ~$12/year for domain

---

## Summary

**What you deployed:**

| Component | URL | Purpose |
|-----------|-----|---------|
| **Demo App** | https://nthlayer-demo.fly.dev | Metrics generator |
| **Grafana Dashboard** | https://org.grafana.net/public-dashboards/abc | Live visualization |
| **Demo Site** | https://org.github.io/nthlayer | Interactive walkthrough |
| **GitHub Repo** | https://github.com/org/nthlayer | Docs + source |

**Resources created:**
- ✅ Fly.io application (1 VM)
- ✅ Grafana Cloud workspace
- ✅ Public Grafana dashboard
- ✅ GitHub Pages site
- ✅ Updated README

**Monthly cost:** $0 ✅

---

## Next Steps

1. **Share your demo:**
   - Tweet the live dashboard link
   - Add to blog posts
   - Include in presentations

2. **Monitor usage:**
   - Check Grafana Cloud usage weekly
   - Verify Fly.io app health
   - Watch GitHub Pages bandwidth

3. **Iterate:**
   - Add more example services
   - Create video walkthrough
   - Enhance demo site with more features

4. **Optional: Low-Cost Upgrade:**
   - See `LOW_COST_SETUP.md` for Hetzner VPS option
   - Full Prometheus + Grafana stack
   - Custom domain
   - Only €3.49/month

---

**Congratulations!** 🎉 You now have a publicly accessible NthLayer demo costing $0/month!
