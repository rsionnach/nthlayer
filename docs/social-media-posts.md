# NthLayer Launch - Social Media Posts

## Hacker News (Show HN)

**Title:** Show HN: NthLayer – Generate your complete reliability stack from a single YAML file

**Body:**
```
I built NthLayer because I was tired of the manual effort every time a new
service onboards - copying dashboard JSON, writing alert rules, setting up
PagerDuty, defining SLOs. 20 hours of work per service.

Define your service once:

    name: payment-api
    tier: critical
    type: api
    dependencies:
      - postgresql
      - redis
    slos:
      availability: 99.95
      latency_p99_ms: 200

Get automatically:
- Grafana dashboards (12-28 panels based on dependencies)
- Prometheus alerts (400+ battle-tested rules)
- SLO definitions with error budgets
- PagerDuty teams, escalation policies, services
- Recording rules for performance

Plus: Org-wide SLO Portfolio - see reliability health across all services:

    $ nthlayer portfolio
    Overall Health: 78% (14/18 SLOs meeting target)
    Critical: 5/6 healthy
    ! payment-api needs reliability investment

This is the part PagerDuty can't give you - they want vendor lock-in.
NthLayer works across your entire stack.

Live demo: https://rsionnach.github.io/nthlayer
GitHub: https://github.com/rsionnach/nthlayer
Install: pipx install nthlayer

It's early alpha - looking for SRE teams to try it. What reliability toil
would you automate first?
```

---

## Reddit r/devops

**Title:** I built a tool that generates your complete reliability stack from a single YAML file

**Body:**
```
After years of copy-pasting dashboard JSON, writing alerts, setting up
PagerDuty, and defining SLOs for every service, I built NthLayer to automate
all of it.

**What it does:**
- Define service once in YAML (name, tier, dependencies, SLOs)
- Generate: Grafana dashboards, Prometheus alerts, PagerDuty setup, SLOs
- Technology-aware: knows PostgreSQL, Redis, Kafka, etc. have different metrics
- Org-wide SLO Portfolio: see reliability health across ALL services

**Example output for a payment-api service:**
- 12-28 panel Grafana dashboard (based on dependencies)
- 400+ battle-tested Prometheus alerts
- PagerDuty team, escalation policy, service (tier-based defaults)
- SLO definitions with error budget tracking

**The differentiator:** Cross-vendor SLO portfolio. PagerDuty can't give you
this because they want vendor lock-in. NthLayer aggregates across Prometheus,
Grafana, Datadog - whatever you use.

    $ nthlayer portfolio
    Overall Health: 78% (14/18 SLOs meeting target)
    ! payment-api needs reliability investment

**Live demo:** https://rsionnach.github.io/nthlayer

Early alpha - feedback welcome from folks who deal with this toil daily.

GitHub: https://github.com/rsionnach/nthlayer
```

---

## Reddit r/sre

**Title:** Automating the "20 hours of reliability config per service" problem - looking for feedback

**Body:**
```
Every new service at my last job meant:
- Copy dashboard JSON, find-replace service names
- Write alerts, copy from another service, tweak thresholds
- Set up PagerDuty team, escalation policy, service
- Define SLOs, calculate error budgets
- Repeat for every database, cache, message queue

I built NthLayer to generate all of this from a single YAML file.

**The idea:**
Your service YAML declares what you have (postgresql, redis, kafka) and your
SLO targets. NthLayer generates production-ready dashboards, alerts,
PagerDuty config, and tracks error budgets.

**What's working:**
- Grafana dashboards (12-28 panels per service)
- 400+ battle-tested Prometheus alerts
- PagerDuty teams, escalation policies, services (tier-based defaults)
- SLO definitions with error budget tracking
- **Org-wide SLO Portfolio** - this is the differentiator

**The Portfolio:**
PagerDuty charges extra for their "Advance" AI features. Their SLO tools
only work within PagerDuty. NthLayer gives you cross-vendor visibility:

    $ nthlayer portfolio
    Overall Health: 78% (14/18 SLOs meeting target)
    Critical: 5/6 healthy
    ! payment-api needs reliability investment
    * user-api exceeds SLO - consider tier promotion

**What I'm looking for:**
Early adopters to try it on real services. What breaks? What's missing?

Demo: https://rsionnach.github.io/nthlayer
GitHub: https://github.com/rsionnach/nthlayer
```

---

## LinkedIn

**Post:**
```
I've been building something for the past few months and I'm ready to share it.

NthLayer automates the reliability engineering work that every team does manually:
- Grafana dashboards
- Prometheus alerts
- PagerDuty teams, escalation policies, services
- SLO definitions with error budgets
- Org-wide reliability portfolio

One YAML file → complete reliability stack.

The idea came from watching teams spend 15-20 hours configuring monitoring
for each new service. But the bigger problem? No visibility into org-wide
reliability health.

That's why I built the SLO Portfolio:

    $ nthlayer portfolio
    Overall Health: 78% (14/18 SLOs meeting target)
    Critical: 5/6 healthy
    ! payment-api needs reliability investment

PagerDuty charges extra for their "Advance" features and locks you into their
platform. NthLayer gives you cross-vendor visibility - Prometheus, Grafana,
Datadog, whatever you use.

It's in early alpha and I'm looking for SRE/DevOps teams who want to try it.

🔗 Live demo: https://rsionnach.github.io/nthlayer
📦 Install: pipx install nthlayer
💻 GitHub: https://github.com/rsionnach/nthlayer

What reliability work would you automate first?

#SRE #DevOps #Observability #Prometheus #Grafana #PagerDuty #OpenSource
```

---

## Twitter/X Thread

**Tweet 1:**
```
I built NthLayer because I was tired of the 20 hours of reliability config
for every new service.

One YAML file → complete reliability stack:
✅ Grafana dashboards
✅ Prometheus alerts
✅ PagerDuty teams, escalation policies, services
✅ SLO definitions + error budgets
✅ Org-wide reliability portfolio

🔗 https://github.com/rsionnach/nthlayer
```

**Tweet 2:**
```
The problem: Every new service = 15-20 hours of config work

- Copy dashboard JSON, find-replace names
- Write alerts, tweak thresholds
- Set up PagerDuty team, escalation policy, service
- Define SLOs, track error budgets
- Repeat for every dependency

NthLayer generates all of this from a single YAML file.
```

**Tweet 3:**
```
The differentiator: Cross-vendor SLO Portfolio

PagerDuty charges extra for "Advance" features and locks you in.
NthLayer gives you org-wide visibility across ALL your tools:

$ nthlayer portfolio
Overall Health: 78% (14/18 SLOs meeting target)
Critical: 5/6 healthy
! payment-api needs reliability investment
```

**Tweet 4:**
```
What makes it technology-aware:

It knows PostgreSQL, Redis, Kafka, etc. have different metrics.

Define your dependencies, get production-ready monitoring:

name: payment-api
dependencies:
  - postgresql
  - redis

→ 12-28 panels, 400+ alerts, PagerDuty setup, SLOs
```

**Tweet 5:**
```
Live demo with real metrics: https://rsionnach.github.io/nthlayer

Multiple services, each with auto-generated:
- Grafana dashboards
- Prometheus alerts
- PagerDuty config
- SLO definitions

All from YAML. No JSON copy-paste.
```

**Tweet 6:**
```
It's early alpha - I'm looking for SRE teams to try it on real services.

What breaks? What's missing? What would make this useful for your team?

pipx install nthlayer
https://github.com/rsionnach/nthlayer

DMs open for feedback!
```

---

## Timing Recommendations

| Platform | Best Time | Day |
|----------|-----------|-----|
| Hacker News | 9-11am ET | Tuesday or Wednesday |
| Reddit r/devops | Morning ET | Weekday |
| Reddit r/sre | Morning ET | Weekday |
| LinkedIn | 8-10am or 5-6pm | Tuesday-Thursday |
| Twitter/X | 9am or 12pm ET | Any day |

## Key Messages to Emphasize

1. **"20 hours → 5 minutes"** - Concrete time savings
2. **"One YAML file"** - Simplicity
3. **"Cross-vendor SLO Portfolio"** - The differentiator PagerDuty can't offer
4. **"PagerDuty teams, escalation policies, services"** - Be specific, not "routing"
5. **"Technology-aware"** - Not just templates, actual intelligence
6. **"Early alpha, seeking feedback"** - Set expectations, invite collaboration
7. **"Live demo"** - Let them see before installing

## Differentiator Talking Points

- PagerDuty charges extra for "Advance" AI features
- PagerDuty/Datadog SLO tools only work within their platform (vendor lock-in)
- NthLayer gives cross-vendor visibility: Prometheus, Grafana, Datadog - whatever you use
- Org-wide reliability health in one command: `nthlayer portfolio`
