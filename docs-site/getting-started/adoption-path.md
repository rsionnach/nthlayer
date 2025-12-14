# Adoption Path

NthLayer can be adopted incrementally. You don't need to enable all features on day one. This guide walks through a proven three-phase approach that lets teams build confidence before enabling enforcement.

## Overview

| Phase | What You Do | Risk Level | Time to Value |
|-------|-------------|------------|---------------|
| **1. Generate** | Run locally, review output | None | 1 day |
| **2. Validate** | Add to CI, warnings only | Low | 1 week |
| **3. Protect** | Enable gates, block deploys | Medium | 2-4 weeks |

---

## Phase 1: Generate Only

**Goal**: See what NthLayer produces without any CI/CD integration.

**Duration**: 1-3 days

### Steps

1. **Install NthLayer**
   ```bash
   pip install nthlayer
   ```

2. **Create a service spec**
   ```bash
   nthlayer init
   # Or manually create service.yaml
   ```

3. **Generate artifacts locally**
   ```bash
   nthlayer apply services/checkout-api.yaml --output-dir ./generated
   ```

4. **Review the output**
   ```
   generated/
   └── checkout-api/
       ├── dashboard.json      # Grafana dashboard
       ├── alerts.yaml         # Prometheus alert rules
       ├── recording_rules.yaml
       └── slo.yaml            # SLO definitions
   ```

5. **Compare to your existing setup**
   - Are the generated alerts better than what you have?
   - Does the dashboard cover what you need?
   - Are SLO targets reasonable for this service?

### Success Criteria

- [ ] Generated artifacts look correct
- [ ] You understand what each file does
- [ ] You've identified any customizations needed

### What You Learn

- How tier affects defaults
- What NthLayer generates vs what you need to customize
- Whether your service.yaml needs adjustments

---

## Phase 2: Validate in CI

**Goal**: Run NthLayer in CI to catch issues early, but don't block deploys yet.

**Duration**: 1-2 weeks

### Steps

1. **Add NthLayer to your CI pipeline**

   ```yaml
   # .github/workflows/ci.yml
   - name: Generate and validate reliability config
     run: |
       pip install nthlayer
       nthlayer apply services/${{ matrix.service }}.yaml --lint
   ```

2. **Enable verification in warning mode**

   ```yaml
   - name: Verify metrics exist (warnings only)
     run: |
       nthlayer verify services/${{ matrix.service }}.yaml --no-fail
     env:
       PROMETHEUS_URL: ${{ secrets.PROMETHEUS_URL }}
   ```

3. **Commit generated artifacts**

   ```yaml
   - name: Check for uncommitted changes
     run: |
       git diff --exit-code generated/
   ```

### What to Watch For

- **Lint failures**: Invalid PromQL in generated alerts
- **Verification warnings**: Missing metrics in Prometheus
- **Drift**: Generated files that weren't committed

### Success Criteria

- [ ] CI runs NthLayer on every PR
- [ ] Team reviews NthLayer output in PRs
- [ ] No unexpected lint failures
- [ ] Verification warnings are understood (not necessarily fixed)

### What You Learn

- Which services are missing required metrics
- Whether your Prometheus setup works with NthLayer
- Team comfort level with the generated artifacts

---

## Phase 3: Protect in CD

**Goal**: Enable deployment gates that block risky deploys.

**Duration**: 2-4 weeks (gradual rollout)

### Steps

1. **Start with non-critical services**

   Pick 2-3 `standard` or `low` tier services first:
   ```yaml
   # service.yaml
   tier: standard  # Start here, not critical
   ```

2. **Enable check-deploy in warning mode**

   ```yaml
   # CD pipeline
   - name: Check deployment gate
     run: |
       nthlayer check-deploy services/${{ matrix.service }}.yaml || echo "Gate warning (not blocking)"
     env:
       PROMETHEUS_URL: ${{ secrets.PROMETHEUS_URL }}
   ```

3. **Monitor for false positives**

   Track:
   - How often would deploys have been blocked?
   - Were those blocks justified?
   - Any false positives?

4. **Graduate to blocking mode**

   ```yaml
   - name: Check deployment gate
     run: |
       nthlayer check-deploy services/${{ matrix.service }}.yaml
     # Now exit code 2 will fail the pipeline
   ```

5. **Expand to critical services**

   Only after confidence is built:
   ```yaml
   tier: critical  # Now enable for high-stakes services
   ```

### Rollout Schedule

| Week | Services | Mode |
|------|----------|------|
| 1 | 2-3 low tier | Warning only |
| 2 | All low tier | Blocking |
| 3 | Standard tier | Warning only |
| 4 | Standard tier | Blocking |
| 5+ | Critical tier | Warning, then blocking |

### Success Criteria

- [ ] Gates correctly block deploys with exhausted error budgets
- [ ] No false positives blocking valid deploys
- [ ] Team trusts the gate decisions
- [ ] Escalation path exists for gate overrides

### What You Learn

- Whether your SLO targets are realistic
- How often services are actually at risk
- Team response to automated enforcement

---

## Common Adoption Patterns

### Pattern A: Platform Team Drives

1. Platform team adopts NthLayer
2. Creates org-wide service templates
3. Onboards service teams one by one
4. Mandates adoption for new services

**Best for**: Organizations with strong platform teams

### Pattern B: Service Team Experiments

1. One service team tries NthLayer
2. Shares results with other teams
3. Organic adoption spreads
4. Platform team eventually standardizes

**Best for**: Bottom-up engineering cultures

### Pattern C: Incident-Driven

1. Major incident reveals monitoring gaps
2. NthLayer adopted for affected services
3. Expanded based on incident learnings
4. Eventually becomes standard

**Best for**: Organizations learning from failures

---

## Rollback Plan

If adoption isn't working:

### Phase 3 → Phase 2
- Remove `check-deploy` from CD
- Keep `verify --no-fail` in CI
- Investigate why gates were problematic

### Phase 2 → Phase 1
- Remove NthLayer from CI
- Continue using generated artifacts manually
- Investigate lint/verify issues

### Phase 1 → Nothing
- Stop using NthLayer
- Keep existing monitoring setup
- Document what didn't work for future reference

---

## Timeline Summary

| Milestone | Typical Duration |
|-----------|------------------|
| First service.yaml created | Day 1 |
| First generated artifacts reviewed | Day 1-3 |
| NthLayer running in CI | Week 1 |
| First service with blocking gate | Week 3-4 |
| All services with blocking gates | Month 2-3 |
| Full org standardization | Month 3-6 |

The key is **incremental confidence**: each phase proves value before the next adds risk.
