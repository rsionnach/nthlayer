# NthLayer Live Demo Infrastructure

Public demo infrastructure for showcasing NthLayer-generated observability.

---

## Quick Links

**📚 Setup Guides:**
- [**Zero-Cost Setup**](ZERO_COST_SETUP.md) - FREE forever ($0/month) - **START HERE**
- [**Low-Cost Setup**](hetzner/LOW_COST_SETUP.md) - Full stack (€3.49/month)
- [**Implementation Summary**](DEMO_COMPLETE.md) - Technical details

**🚀 Demo Resources:**
- [Fly.io App](fly-app/) - Demo application with metrics
- [GitHub Pages Site](../docs/) - Interactive demo website

---

## Overview

This directory contains everything needed to deploy a publicly accessible live demo of NthLayer.

### Two Deployment Options

#### Option 1: Zero-Cost Path (Recommended)

**What:** Grafana Cloud + Fly.io + GitHub Pages  
**Cost:** $0/month forever  
**Setup Time:** ~4 hours  
**Best For:** README embedding, documentation, public showcase

**What You Get:**
- ✅ Public Grafana dashboards (embeddable)
- ✅ Demo app generating live metrics
- ✅ Interactive demo website
- ✅ 99.9% uptime
- ✅ No maintenance

**Limitations:**
- ⚠️ No Prometheus UI access
- ⚠️ No AlertManager UI
- ⚠️ Dashboard customization limited

**→ [Start Zero-Cost Setup](ZERO_COST_SETUP.md)**

#### Option 2: Low-Cost Path

**What:** Complete stack on Hetzner VPS  
**Cost:** €3.49/month ($4.49 USD)  
**Setup Time:** ~5 hours  
**Best For:** Sales demos, presentations, full feature showcase

**What You Get:**
- ✅ Everything from zero-cost path
- ✅ + Full Prometheus UI
- ✅ + Full Grafana UI with branding
- ✅ + AlertManager UI
- ✅ + PostgreSQL/Redis monitoring
- ✅ + Custom domain with SSL
- ✅ + SSH access
- ✅ + Complete control

**→ [Start Low-Cost Setup](hetzner/LOW_COST_SETUP.md)**

---

## Architecture

### Zero-Cost Path

```
GitHub Repo
    ↓
GitHub Pages (Static Site)
    ↓
Grafana Cloud (Dashboards) ← Fly.io (Demo App)
```

**Services:**
- **GitHub Pages:** Interactive demo site (free)
- **Grafana Cloud:** Public dashboards (free tier: 10K series)
- **Fly.io:** Demo app (free tier: 3 VMs, 160GB bandwidth)

### Low-Cost Path

```
Hetzner VPS (€3.49/month)
├── Prometheus (full UI)
├── Grafana (full UI)
├── AlertManager (full UI)
├── Demo App
├── PostgreSQL + exporter
├── Redis + exporter
└── Nginx + SSL
```

**One VPS runs everything** with Docker Compose.

---

## Quick Start

### Prerequisites

- GitHub account
- Terminal access
- Git installed
- Python 3.9+ installed

### Deploy Zero-Cost Demo (90 minutes)

```bash
# 1. Setup Grafana Cloud (30 min)
# Sign up: https://grafana.com/auth/sign-up
# Get remote_write credentials

# 2. Deploy Fly.io app (30 min)
cd demo/fly-app
flyctl launch --name nthlayer-demo
flyctl secrets set \
  GRAFANA_REMOTE_WRITE_URL="https://..." \
  GRAFANA_CLOUD_USER="..." \
  GRAFANA_CLOUD_KEY="..."
flyctl deploy

# 3. Import dashboard to Grafana Cloud (15 min)
nthlayer apply examples/services/payment-api.yaml
# Import generated/payment-api/dashboard.json
# Make dashboard public

# 4. Enable GitHub Pages (5 min)
# Repo Settings → Pages → Source: /docs

# 5. Update URLs (10 min)
# Replace placeholder URLs in:
# - docs/index.html
# - README.md
git add .
git commit -m "Add live demo infrastructure"
git push
```

**Done!** Your demo is live at:
- Demo site: `https://yourorg.github.io/nthlayer`
- Dashboard: `https://yourorg.grafana.net/public-dashboards/abc123`
- Demo app: `https://nthlayer-demo.fly.dev`

---

## Directory Structure

```
demo/
├── README.md                    # This file
├── DEMO_COMPLETE.md             # Implementation summary
├── ZERO_COST_SETUP.md          # Zero-cost setup guide
├── fly-app/                     # Fly.io demo application
│   ├── Dockerfile               # Container definition
│   ├── app.py                   # Flask app (374 lines)
│   ├── fly.toml                 # Fly.io config
│   └── README.md                # Deployment guide
└── hetzner/                     # Low-cost VPS setup
    └── LOW_COST_SETUP.md       # Hetzner setup guide
```

---

## What Gets Deployed

### Demo Application (Fly.io)

**Endpoints:**
- `GET /` - API documentation
- `GET /health` - Health check
- `GET /metrics` - Prometheus metrics
- `POST /api/payment` - Create payment (generates metrics)
- `GET /api/payments/<id>` - Retrieve payment
- `POST /api/trigger-error` - Trigger error burst
- `POST /api/trigger-slow` - Trigger slow requests

**Metrics Generated:**
- `http_requests_total` - Request counter by status
- `http_request_duration_seconds` - Latency histogram
- `error_budget_remaining_ratio` - SLO tracking
- `database_connections_total` - DB connection gauge
- `database_query_duration_seconds` - Query latency
- `cache_hits_total` / `cache_misses_total` - Cache metrics

**Background Activity:**
- Simulates realistic traffic patterns
- 5% error rate (configurable)
- 10% slow request rate
- Continuous metric generation

### Demo Website (GitHub Pages)

**Sections:**
- Hero with badges and value proposition
- Stats showcase (84/84 tests, 86% fewer commands)
- 4-step workflow demonstration
- Live embedded Grafana dashboard
- Generated files showcase
- Installation instructions

**Features:**
- Modern dark theme
- Responsive design
- Smooth animations
- Professional appearance
- SEO optimized

---

## Maintenance

### Zero-Cost Path

**Monthly (~15 minutes):**
- ✅ Check Fly.io app status: `flyctl status`
- ✅ Verify metrics in Grafana Cloud
- ✅ Test public dashboard access
- ✅ Test GitHub Pages site

**As Needed:**
- Update demo when NthLayer changes
- Regenerate and re-import dashboard
- Update documentation

### Low-Cost Path

**Monthly (~30 minutes):**
- ✅ Check VPS resource usage
- ✅ Update Docker images
- ✅ Check SSL certificate expiry
- ✅ Review logs for errors
- ✅ Test all endpoints

**Quarterly:**
- Full system update
- Backup configurations
- Review and optimize

---

## Troubleshooting

### Common Issues

**Fly.io app not starting:**
```bash
flyctl logs
# Check for errors in output
# Verify Dockerfile builds locally: docker build -t test .
```

**Metrics not in Grafana Cloud:**
```bash
# Check remote_write credentials
flyctl secrets list

# Test metrics endpoint
curl https://nthlayer-demo.fly.dev/metrics
```

**GitHub Pages not updating:**
```bash
# Check GitHub Actions: Repo → Actions
# Verify /docs folder exists in branch
# Try: git commit --allow-empty -m "Rebuild" && git push
```

**Dashboard shows no data:**
- Verify Prometheus data source selected in Grafana
- Check metric names match: Go to Explore → Query metrics
- Ensure time range includes recent data

### Getting Help

1. Check setup guides for detailed troubleshooting
2. Review logs: `flyctl logs` or `docker-compose logs`
3. Test components individually
4. Open GitHub issue with details

---

## Cost Analysis

### Zero-Cost Path

| Service | Free Tier | Usage | Cost |
|---------|-----------|-------|------|
| **Grafana Cloud** | 10K series, 50GB logs | ~50-100 series | $0 |
| **Fly.io** | 3 VMs, 160GB bandwidth | 1 VM, <1GB/month | $0 |
| **GitHub Pages** | 100GB bandwidth | <1GB/month | $0 |
| **Total** | - | - | **$0/month** |

**Overage Risk:** Very low (using <1% of limits)

### Low-Cost Path

| Item | Specs | Cost/Month | Annual |
|------|-------|------------|--------|
| **Hetzner CX22** | 2 vCPU, 4GB RAM, 40GB SSD | €3.49 | €41.88 |
| **Domain** (optional) | yourname.com | ~€1.00 | ~€12.00 |
| **SSL** | Let's Encrypt | €0 | €0 |
| **Total** | - | **€4.49** | **€53.88** |

**Annual:** ~$60/year for complete stack

---

## Comparison

| Feature | Zero-Cost | Low-Cost |
|---------|-----------|----------|
| **Public Dashboards** | ✅ | ✅ |
| **Embedded Dashboards** | ✅ | ✅ |
| **Demo App** | ✅ | ✅ |
| **Prometheus UI** | ❌ | ✅ |
| **AlertManager UI** | ❌ | ✅ |
| **Custom Domain** | ❌ | ✅ |
| **SSH Access** | ❌ | ✅ |
| **Complete Control** | ❌ | ✅ |
| **Monthly Cost** | $0 | €3.49 |
| **Setup Time** | 4 hours | 5 hours |
| **Maintenance** | 15 min/month | 30 min/month |

**Recommendation:** Start with zero-cost, upgrade to low-cost when you need full stack access.

---

## Next Steps

1. **Read the appropriate setup guide:**
   - [Zero-Cost Setup](ZERO_COST_SETUP.md) - **Start here for most cases**
   - [Low-Cost Setup](hetzner/LOW_COST_SETUP.md) - When you need full stack

2. **Follow the step-by-step instructions**
   - Each guide is complete and tested
   - Includes troubleshooting
   - Expected time clearly stated

3. **Deploy and test**
   - Verify each component works
   - Use provided checklists
   - Test public access

4. **Share your demo!**
   - Update README with URLs
   - Share on social media
   - Use in presentations

---

## Support

- **Setup Guides:** Detailed step-by-step instructions in this directory
- **Demo Implementation:** See [DEMO_COMPLETE.md](DEMO_COMPLETE.md)
- **GitHub Issues:** Report problems or ask questions
- **Documentation:** Full docs in main [README.md](../README.md)

---

**Ready to deploy? Start with [ZERO_COST_SETUP.md](ZERO_COST_SETUP.md)** 🚀
