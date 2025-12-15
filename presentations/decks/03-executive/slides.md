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

**Reliability Requirements as Code**

<div class="mt-6 text-lg">
Prevent production incidents by enforcing reliability before deployment
</div>

---
layout: default
---

# The Business Problem

<div class="text-center mt-8">

### Reliability Decisions Happen Too Late

<div class="grid grid-cols-3 gap-6 mt-8">

<div class="p-4 border-2 border-red-500 rounded">

### After Incidents
Alerts created **after** the first outage

Dashboards built **after** users complain

SLOs defined **after** budget is exhausted

</div>

<div class="p-4 border-2 border-yellow-500 rounded">

### Inconsistently
Each team invents their own standards

No enforcement mechanism

"Production-ready" = opinion

</div>

<div class="p-4 border-2 border-orange-500 rounded">

### Repeatedly
Same configs rebuilt per service

Platform team becomes bottleneck

20+ hours of toil per service

</div>

</div>

</div>

<div class="text-center mt-8 text-xl font-bold text-red-400">
Result: Reactive reliability, repeated incidents, inconsistent standards
</div>

---
layout: default
---

# The Solution: Shift Left

<div class="text-center mt-6">

### Move Reliability to Build Time

<div class="text-2xl font-bold my-6 text-green-400">
Define requirements before deployment, not after incidents
</div>

</div>

<div class="grid grid-cols-2 gap-8 mt-4">

<div>

### How It Works

1. **Define** reliability requirements in YAML
2. **Generate** dashboards, alerts, SLOs automatically
3. **Validate** that metrics exist before deploy
4. **Gate** deployments based on error budget

### The Key Insight

Generation is just the mechanism.

**The value is prevention.**

</div>

<div>

### Pipeline Integration

```
service.yaml
    ↓
Generate artifacts (dashboards, alerts)
    ↓
Lint (validate PromQL syntax)
    ↓
Verify (confirm metrics exist)
    ↓
Gate (check error budget)
    ↓
Deploy (only if all pass)
```

</div>

</div>

---
layout: default
---

# Business Value

<div class="grid grid-cols-2 gap-8 mt-6">

<div>

### Prevent Incidents

**Before NthLayer:**
- Deploy → Incident → Create alerts
- Cycle repeats for every new service
- Reactive mode is the default

**With NthLayer:**
- Define requirements → Validate → Deploy
- Missing metrics = blocked deployment
- Budget exhausted = blocked deployment

<div class="mt-4 p-4 bg-green-900/30 rounded text-center">
<div class="text-2xl font-bold">Incidents prevented</div>
<div class="text-sm mt-2">Not just faster response—actual prevention</div>
</div>

</div>

<div>

### Operational Efficiency

| Metric | Before | After |
|--------|--------|-------|
| Time per service | 20+ hours | 5 minutes |
| Config consistency | Variable | 100% |
| Production readiness | Opinion | Enforced |
| Platform team bottleneck | Yes | No |

<div class="mt-4 p-4 bg-blue-900/30 rounded text-center">
<div class="text-2xl font-bold">4,000 hours saved</div>
<div class="text-sm mt-2">At 200 services × 20 hours each</div>
</div>

</div>

</div>

---
layout: default
---

# What Makes This Different

<div class="grid grid-cols-2 gap-8 mt-8">

<div>

### What NthLayer Is

**A reliability specification**
- Define what "production-ready" means
- Tier-based defaults (critical, standard, low)

**A compiler**
- YAML → dashboards, alerts, SLOs
- Consistent output from simple input

**A CI/CD enforcement layer**
- Exit codes for pipeline integration
- Blocks deploys that violate requirements

</div>

<div>

### What NthLayer Is NOT

❌ **Not a service catalog**
<div class="text-sm text-gray-400 ml-6">Catalogs document; NthLayer enforces</div>

❌ **Not an observability platform**
<div class="text-sm text-gray-400 ml-6">Grafana/Datadog observe; NthLayer generates for them</div>

❌ **Not incident management**
<div class="text-sm text-gray-400 ml-6">PagerDuty responds; NthLayer prevents</div>

<div class="mt-6 p-4 bg-blue-900/30 rounded">
NthLayer operates <strong>before</strong> these systems—deciding what is allowed to reach production.
</div>

</div>

</div>

---
layout: default
---

# Competitive Positioning

<div class="mt-6">

| Solution | Focus | Prevents Incidents? | Works Day 1? |
|----------|-------|---------------------|--------------|
| **Service Catalogs** (Backstage) | Documentation | ❌ No gates | ❌ Requires adoption |
| **Observability** (Datadog, Grafana) | Monitoring | ❌ Post-deploy | ✅ Yes |
| **Incident Mgmt** (PagerDuty) | Response | ❌ After the fact | ✅ Yes |
| **SLO Tools** (Nobl9) | Tracking | ❌ No enforcement | ✅ Yes |
| **NthLayer** | **Requirements + Enforcement** | ✅ **Pre-deploy gates** | ✅ **Yes** |

</div>

<div class="text-center mt-8">

<div class="text-xl font-bold text-green-400">
Key differentiator: Enforcement happens at build time
</div>

<div class="mt-2 text-gray-400">
They respond to incidents. NthLayer prevents them.
</div>

</div>

---
layout: default
---

# ROI Analysis

<div class="grid grid-cols-3 gap-4 mt-6">

<div class="p-4 border-2 border-green-500 rounded">

### 50 Services

**Time Savings:**
- Before: 1,000 hours
- After: 4 hours
- Saved: 996 hours

**Value:**
- ~$200K in eng time
- 6 months → 1 week

<div class="text-green-400 font-bold mt-4">
ROI: 99%+ time reduction
</div>

</div>

<div class="p-4 border-2 border-blue-500 rounded">

### 200 Services

**Time Savings:**
- Before: 4,000 hours (2 FTEs)
- After: 100 hours (0.2 FTE)
- Saved: 3,900 hours

**Value:**
- ~$400K/year
- 1.8 engineers freed

<div class="text-blue-400 font-bold mt-4">
ROI: $400K annually
</div>

</div>

<div class="p-4 border-2 border-purple-500 rounded">

### 1,000 Services

**Time Savings:**
- Before: 20,000 hours (10 FTEs)
- After: 500 hours (0.5 FTE)
- Saved: 19,500 hours

**Value:**
- ~$2M/year
- 9.5 engineers freed

<div class="text-purple-400 font-bold mt-4">
ROI: $2M annually
</div>

</div>

</div>

<div class="text-center mt-6 text-sm text-gray-400">
*Based on $100/hour fully-loaded engineer cost
</div>

---
layout: default
---

# Beyond Time Savings: Prevention Value

<div class="grid grid-cols-2 gap-8 mt-8">

<div>

### Incidents Prevented

The harder-to-measure but higher-impact value:

**Deploy Gates:**
- Error budget exhausted = deploy blocked
- Bad deploys caught before production
- No more "we should have waited"

**Contract Verification:**
- Missing metrics = deploy blocked
- No more "dashboard shows no data"
- Instrumentation guaranteed

**Consistent Standards:**
- Every service has proper alerting
- No more "we forgot to add alerts"
- Platform team standards enforced

</div>

<div>

### Cost of an Incident

| Factor | Cost |
|--------|------|
| Engineer time (5 people × 4 hours) | $2,000 |
| Lost revenue (1 hour downtime) | $10,000+ |
| Customer trust | Unmeasurable |
| Post-incident process | $1,000 |

**Total per incident: $13,000+**

<div class="mt-6 p-4 bg-green-900/30 rounded">
<div class="text-lg font-bold">Prevent 10 incidents/year</div>
<div class="mt-2">= $130,000+ in avoided costs</div>
<div class="mt-2 text-sm text-gray-400">Plus: better customer experience, less engineer burnout</div>
</div>

</div>

</div>

---
layout: default
---

# Risk Mitigation

<div class="grid grid-cols-2 gap-6 mt-6">

<div>

### "What if it generates wrong configs?"

✅ **Dry-run mode** previews all changes

✅ **Git-based workflow** enables PR review

✅ **Rollback via git revert** if needed

✅ **Override any default** in YAML

</div>

<div>

### "What about vendor lock-in?"

✅ **OpenSLO standard** output

✅ **Works with existing tools** (Prometheus, Grafana, PagerDuty)

✅ **Export configs anytime**

✅ **Open source planned**

</div>

<div>

### "Will this disrupt operations?"

✅ **Incremental adoption** - one service at a time

✅ **No rip-and-replace** required

✅ **Works alongside manual configs**

✅ **Pilot with 5 services in 1 week**

</div>

<div>

### "What if we need custom logic?"

✅ **Override tier defaults** per service

✅ **Custom YAML fields** supported

✅ **Technology templates** extensible

✅ **API access** for automation

</div>

</div>

---
layout: default
---

# Implementation Timeline

<div class="grid grid-cols-4 gap-4 mt-8">

<div class="p-4 border-2 border-green-500 rounded">

### Week 1
**Pilot**

- Install NthLayer
- 5-10 services
- Validate output
- Team training

<div class="text-green-400 mt-2 font-bold">
Quick win
</div>

</div>

<div class="p-4 border-2 border-blue-500 rounded">

### Week 2-3
**Validate**

- Add to CI pipeline
- Lint all specs
- Verify in warning mode
- Build confidence

<div class="text-blue-400 mt-2 font-bold">
Low risk
</div>

</div>

<div class="p-4 border-2 border-purple-500 rounded">

### Week 4
**Protect**

- Enable deploy gates
- Start with non-critical
- Graduate to blocking
- Full enforcement

<div class="text-purple-400 mt-2 font-bold">
Full value
</div>

</div>

<div class="p-4 border-2 border-yellow-500 rounded">

### Ongoing
**Optimize**

- Fine-tune thresholds
- Add more services
- Measure impact
- Expand coverage

<div class="text-yellow-400 mt-2 font-bold">
Continuous ROI
</div>

</div>

</div>

<div class="text-center mt-6">
<strong>Time to value: 1 month</strong> from pilot to full enforcement
</div>

---
layout: default
---

# Next Steps

<div class="grid grid-cols-3 gap-8 mt-8">

<div class="text-center">

### 1. Pilot

**1 week, no commitment**

- 5-10 services
- Proof of value
- Team feedback

</div>

<div class="text-center">

### 2. Business Case

**You provide:**
- Service count
- Current eng hours

**We provide:**
- Custom ROI analysis
- Implementation plan

</div>

<div class="text-center">

### 3. Decision

**Your options:**
- Full rollout
- Phased adoption
- Pass (no pressure)

</div>

</div>

<div class="text-center mt-8">

**Ready to see it in action?**

Schedule a 30-minute technical demo with your platform team

</div>

---
layout: center
---

# Reliability Requirements as Code

<div class="text-center mt-8">

<div class="text-2xl mb-6">
Define what "production-ready" means.<br/>
Generate, validate, and enforce automatically.
</div>

<div class="text-xl font-bold text-blue-400 mb-8">
Define once. Generate everything. Block bad deploys.
</div>

**Contact:** hello@nthlayer.dev

**GitHub:** github.com/rsionnach/nthlayer

**Docs:** rsionnach.github.io/nthlayer

</div>
