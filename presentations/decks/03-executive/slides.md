---
theme: the-unnamed
highlighter: shiki
title: NthLayer Executive Overview
themeConfig:
  logoHeader: ''
  eventLogo: ''
  eventUrl: ''
  twitter: ''
  twitterUrl: ''
---

# NthLayer

## The Missing Layer of Reliability

**Automate Operational Setup for Microservices**

<div class="mt-4 text-sm">
Reduce platform team toil by 90%
</div>

---
layout: default
---

<div class="text-sm">

# The Business Problem

<div class="text-center mt-4">

### Your Platform Team Spends

<div class="text-5xl font-bold my-4 text-red-400">
20+ hours
</div>

### Per Service on Manual Operational Setup

<div class="text-orange-400 font-bold mt-2 text-xs">
Including 4 hours just for alert configuration
</div>

</div>

<div class="grid grid-cols-3 gap-4 mt-4 text-left text-sm">

<div>

### 🎯 Reliability
- SLOs
- Error budgets
- Alerts

</div>

<div>

### 📊 Observability
- Dashboards
- Monitors
- Logging

</div>

<div>

### 🚨 Incidents
- Escalations
- Schedules
- Runbooks

</div>

</div>

<div class="mt-3 text-xs">
**Cost at Scale:** 200 services = 3,000 hours = 1.5 engineer-years wasted
</div>

</div>

---
layout: default
---

<div class="text-sm">

# The Solution: Automation

<div class="text-center mt-4">

### NthLayer Auto-Generates Operational Configs

<div class="text-4xl font-bold my-4 text-green-400">
20 hours → 5 minutes
</div>

<div class="text-orange-400 font-bold text-xs">
✨ Including auto-generated alerts for 46 technologies
</div>

### From a Simple YAML File

<div class="text-xs">

```yaml
service: payment-api
tier: 1
team: payments
```

**↓**

SLOs • Alerts • Dashboards • Escalations • Deploy Gates

</div>

</div>

</div>

---
layout: default
---

<div class="text-sm">

# Return on Investment

<div class="grid grid-cols-2 gap-5 mt-1">

<div>

### 💰 Cost Savings

**At 200 services:**
- ⏱️ **Time saved:** 4,000 hours
- 👥 **Engineer-years:** 2 FTEs freed
- 💵 **Annual value:** $400K+
- 🚨 **Alerts alone:** $30K/year

**Ongoing:**
- 📉 **Maintenance:** -90% time
- 🎯 **Consistency:** 100% standardized

</div>

<div>

### 📈 Business Impact

**🚀 Velocity:**
- New service → prod in < 1 day
- No platform bottleneck

**✅ Quality:**
- SRE best practices enforced
- No configuration errors

**🛡️ Risk Reduction:**
- Deploy correlation catches bad releases
- Automatic rollback

</div>

</div>

<div class="mt-1">
**Break-even:** 20 services operationalized
</div>

</div>

---
layout: default
---

<div class="text-xs">

# Real-World Scenarios

<div class="grid grid-cols-3 gap-3 mt-2">

<div class="p-3 border-2 border-green-500 rounded">

### Startup
**50 services**

**Without NthLayer:**
- 1,000 hours manual work
- 6 engineer-months
- $200K in eng time

**With NthLayer:**
- 4 hours automated
- 1 engineer-day
- $800 in eng time

<div class="text-green-400 font-bold mt-1">
ROI: $199K saved (99.6%)
</div>

</div>

<div class="p-3 border-2 border-blue-500 rounded">

### Scale-Up
**200 services**

**Without NthLayer:**
- 4,000 hours ongoing
- 2 FTEs maintaining
- $400K/year

**With NthLayer:**
- 100 hours/year
- 0.2 FTE
- $40K/year

<div class="text-blue-400 font-bold mt-1">
ROI: $400K/year (90% reduction)
</div>

<div class="text-orange-400 text-xs mt-1">
Alert automation: $30K of that savings
</div>

</div>

<div class="p-3 border-2 border-purple-500 rounded">

### Enterprise
**1,000 services**

**Without NthLayer:**
- 20,000 hours
- 10 FTEs
- $2M/year

**With NthLayer:**
- 500 hours/year
- 0.5 FTE
- $100K/year

<div class="text-purple-400 font-bold mt-1">
ROI: $1.9M/year (95% reduction)
</div>

<div class="text-orange-400 text-xs mt-1">
Alert automation: $200K of that savings
</div>

</div>

</div>

</div>

---
layout: default
---

<div class="text-xs">

# Competitive Differentiation

<div class="mt-2">

| Solution | Approach | Auto Alerts | Auto SLOs | Setup Time | Best For |
|----------|----------|-------------|-----------|------------|----------|
| **Service Catalogs**<br/>(Backstage, Cortex, Port) | Top-down platform | ❌ No | ❌ No | Months | Large orgs with platform investment |
| **SLO Platforms**<br/>(Nobl9, Sloth) | Manual SLO entry | ❌ No | ❌ No | Weeks | Teams with SRE resources |
| **DIY Scripts** | Custom glue code | ❌ Manual | ❌ Manual | Ongoing | Small teams initially |
| **⭐ NthLayer** | <span class="text-green-400">Bottom-up automation</span> | <span class="text-orange-400 font-bold">✅ 400+ rules</span> | <span class="text-green-400">✅ Yes</span> | <span class="text-green-400">Days</span> | <span class="text-green-400">Platform teams of any size</span> |

<div class="text-center mt-3 text-orange-400 font-bold">
🚨 NthLayer is the ONLY platform with auto-generated alert rules
</div>

</div>

<div class="mt-3">

**Key Differentiators:**
- ✅ **Zero platform adoption tax** - Works immediately with YAML files
- ✅ **Auto-generates everything** - SLOs, alerts, dashboards, escalations
- ✅ **Opinionated defaults** - SRE best practices baked in
- ✅ **Tool-agnostic** - Works with your existing Prometheus, Grafana, PagerDuty

</div>

</div>

---
layout: default
---

<div class="text-sm">

# Risk Mitigation

<div class="grid grid-cols-2 gap-4 mt-2">

<div>

**"What if it generates wrong configs?"**

✅ Dry-run mode previews changes  
✅ Git-based review process  
✅ Rollback via Git revert  
✅ Override any default  

</div>

<div>

**"What about vendor lock-in?"**

✅ OpenSLO standard output  
✅ Works with existing tools  
✅ Export configs anytime  
✅ Open source (planned)  

</div>

<div>

**"Will this disrupt operations?"**

✅ Incremental adoption  
✅ No rip-and-replace  
✅ Works alongside manual configs  
✅ Pilot with 5 services in 1 week  

</div>

<div>

**"What if we need custom logic?"**

✅ Override tier defaults  
✅ Custom YAML fields  
✅ Plugin system (Q2 2025)  
✅ API for programmatic access  

</div>

</div>

</div>

---
layout: default
---

<div class="text-sm">

# Implementation Timeline

<div class="grid grid-cols-4 gap-3 mt-2">

<div class="p-3 border-2 border-green-500 rounded">

### Week 1
**Pilot**

- Install NthLayer
- Operationalize 5 services
- Validate output
- Team training

<div class="text-green-400 mt-1">
✅ Quick win
</div>

</div>

<div class="p-3 border-2 border-blue-500 rounded">

### Week 2-3
**Scale-Up**

- Operationalize 50 services
- Integrate PagerDuty
- Setup Prometheus
- Monitor error budgets

<div class="text-blue-400 mt-1">
📈 ROI visible
</div>

</div>

<div class="p-3 border-2 border-purple-500 rounded">

### Week 4
**Full Rollout**

- All services automated
- Deploy correlation active
- CI/CD gates enabled
- Documentation complete

<div class="text-purple-400 mt-1">
🎯 Full value
</div>

</div>

<div class="p-3 border-2 border-yellow-500 rounded">

### Ongoing
**Optimize**

- Fine-tune SLOs
- Add custom logic
- Expand integrations
- Measure savings

<div class="text-yellow-400 mt-1">
💰 Continuous ROI
</div>

</div>

</div>

<div class="mt-2">
**Total time to value: 1 month**
</div>

</div>

---
layout: default
---

<div class="text-xs">

# Pricing & Packages (Indicative)

<div class="grid grid-cols-3 gap-4 mt-2">

<div class="p-3 border-2 border-green-500 rounded">

### Starter
**$5K/year**

- Up to 50 services
- Core ResLayer features
- Community support
- Self-hosted

**Best for:**
- Startups
- Small teams
- Pilots

</div>

<div class="p-3 border-2 border-blue-500 rounded bg-blue-900/20">

### Professional
**$20K/year**

- Up to 250 services
- All features
- Email support
- SaaS or self-hosted

**Best for:**
- Scale-ups
- Mid-sized teams

<div class="text-blue-400 mt-1">
👍 Most Popular
</div>

</div>

<div class="p-3 border-2 border-purple-500 rounded">

### Enterprise
**Custom**

- Unlimited services
- Custom integrations
- Dedicated support
- SLA guarantees
- Professional services

**Best for:**
- Large enterprises
- Complex environments

</div>

</div>

<div class="text-center mt-2">
*Pricing subject to change. Contact for custom quotes.*
</div>

</div>

---
layout: default
---

<div class="text-sm">

# Next Steps

<div class="grid grid-cols-3 gap-6 mt-4">

<div>

### 1️⃣ Pilot Program

**1 week**

- 5-10 services
- Proof of value
- No commitment

</div>

<div>

### 2️⃣ Business Case

**You provide:**
- Service count
- Current eng time spent

**We provide:**
- Custom ROI analysis
- Implementation plan
- Timeline

</div>

<div>

### 3️⃣ Decision

**Your options:**
- Full rollout
- Phased adoption
- Pass (no pressure)

</div>

</div>

<div class="mt-6 text-xs">
**Next call:** Schedule 30-min technical demo with your platform team
</div>

</div>

---
layout: center
---

# Thank You

<div class="text-center mt-6 text-sm">

**Let's discuss your specific needs:**

- 📅 **Schedule demo:** calendly.com/nthlayer/demo
- 💬 **Contact:** hello@nthlayer.dev
- 📊 **ROI Calculator:** nthlayer.dev/roi

</div>

<div class="mt-6 text-xl font-bold text-blue-400">
Transform 4,000 hours into 5 minutes
</div>

<div class="mt-2 text-sm text-orange-400">
🚨 400+ auto-generated alerts • 46 technologies • Production-tested
</div>
