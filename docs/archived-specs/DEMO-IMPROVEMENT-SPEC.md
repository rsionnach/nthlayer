> **Status: Archived.** The work this spec proposed shipped via opensrm-42y on 2026-04-26 (consolidation milestone). Preserved as historical record.

# Demo Improvement: Accountability & Portfolio Story

**Status:** Proposal  
**Date:** 2026-04-15  
**Depends on:** Content-addressed decision records (done), nthlayer-observe portfolio/scorecard/check-deploy/explain (done)  
**Scope:** Enhance existing demo with 4 new narrative beats using already-built features

---

## Current Demo Flow (4 steps)

```
1. scenario-runner degrades fraud-detect
2. measure evaluate-once detects breach
3. correlate identifies root cause
4. respond opens incident → learn produces retrospective
```

Linear trigger chain with stdout output. Works. Proven. Not changing this — layering on top.

## Enhanced Demo Flow (8 steps)

```
1. PORTFOLIO    → Show healthy state: all services nominal, budgets healthy
2. DEGRADE      → Scenario runner breaks fraud-detect (existing)
3. DETECT       → measure evaluate-once detects breach (existing)
4. EXPLAIN      → Budget explanation in human-readable prose
5. CORRELATE    → correlate identifies root cause (existing)
6. RESPOND      → respond opens incident, learn produces retrospective (existing)
7. GATE         → check-deploy blocks redeployment of bad version
8. PORTFOLIO    → Show post-incident state: budget consumed, service recovering
```

Steps 2, 3, 5, 6 are unchanged. Steps 1, 4, 7, 8 are new. The trigger chain is the same — we're adding bookends and a mid-incident explanation.

Throughout all steps: every verdict and assessment shows its content-addressed hash and input references. The accountability story is visible in every output.

---

## Step 1: Portfolio Health (Before)

**What the audience sees:**

```
$ nthlayer-observe portfolio --store ./demo-output/assessments.db

NthLayer Portfolio Health — 2026-04-15T09:40:00Z

SERVICE             STATUS    SLOs   BUDGET
─────────────────────────────────────────────
fraud-detect        HEALTHY   3/3    98.2% remaining
payment-api         HEALTHY   2/2    96.1% remaining
checkout-svc        HEALTHY   2/2    99.4% remaining
order-service       HEALTHY   2/2    97.8% remaining

Summary: 4 services, 9 SLOs, all healthy. Error budget period: 22 days remaining.
```

**Implementation:**

The scenario runner needs a "collect baseline" step before degradation:

```bash
# In demo.sh scenario, BEFORE degrading services:
echo "Collecting baseline portfolio..."
nthlayer-observe collect \
  --specs-dir "$SPECS_DIR" \
  --prometheus-url "$PROMETHEUS_URL" \
  --store "$ASSESSMENT_STORE"

nthlayer-observe portfolio --store "$ASSESSMENT_STORE" --format table
echo ""
echo "All services healthy. Triggering incident..."
sleep 3
```

**What to verify:** `nthlayer-observe collect` and `nthlayer-observe portfolio` work against the demo's Prometheus and fake services. The output is meaningful (not all zeros, not all errors).

---

## Step 4: Budget Explanation (Mid-Incident)

**What the audience sees:**

```
$ nthlayer-observe explain --store ./demo-output/assessments.db --service fraud-detect

Budget Explanation: fraud-detect

AVAILABILITY SLO (target: 99.9%)
  Current SLI: 95.8% — BREACHING
  Error budget: 72% consumed in 14 minutes (normally takes 30 days)
  Burn rate: 154x normal
  At this rate, budget exhausts in ~4 minutes.
  
  Contributing factors:
  • Error rate spiked from 0.1% to 4.2% at 09:27 UTC
  • Coincides with deployment d-4521 (canary, 25% traffic)

REVERSAL RATE SLO (target: < 5%)
  Current: 18.4% — BREACHING
  14 of 76 model decisions reversed by humans in the last 30 minutes.
  
  Recommendation: Investigate model version v2.4 deployed in d-4521.
```

**Implementation:**

Add to the scenario runner, after measure detects the breach:

```bash
# After measure evaluate-once:
echo ""
echo "Explaining budget impact..."
nthlayer-observe collect \
  --specs-dir "$SPECS_DIR" \
  --prometheus-url "$PROMETHEUS_URL" \
  --store "$ASSESSMENT_STORE"

nthlayer-observe explain \
  --store "$ASSESSMENT_STORE" \
  --service fraud-detect
echo ""
sleep 3
```

**What to verify:** `nthlayer-observe explain` produces meaningful output for the breaching service. The explanation references actual assessment data, not generic text.

---

## Step 7: Deployment Gate (Post-Incident)

**What the audience sees:**

```
$ nthlayer-observe check-deploy --service fraud-detect --store ./demo-output/assessments.db

Deployment Gate: fraud-detect

  Status:     BLOCKED
  Reason:     Error budget exhausted (72% consumed, threshold: 50%)
  SLO:        availability (99.9% target, current 95.8%)
  Burn rate:  154x normal
  
  The service cannot deploy until error budget recovers below 50% consumed.
  Estimated recovery: ~2 hours at current trajectory.

  Assessment: asm-2026-04-15-a8f2c1e3-00012 (hash: a8f2c1e3...)
  
Exit code: 2 (BLOCKED)
```

**Implementation:**

Add to the scenario runner, after the incident resolves but before the final portfolio:

```bash
# After respond + learn, before final portfolio:
echo ""
echo "Checking deployment gate..."
nthlayer-observe check-deploy \
  --service fraud-detect \
  --store "$ASSESSMENT_STORE"
echo ""
echo "Deploy blocked. Error budget must recover before next release."
sleep 3
```

**What to verify:** `nthlayer-observe check-deploy` reads from the assessment store (not Prometheus directly), correctly identifies the budget as exhausted, and returns exit code 2.

---

## Step 8: Portfolio Health (After)

**What the audience sees:**

```
$ nthlayer-observe portfolio --store ./demo-output/assessments.db

NthLayer Portfolio Health — 2026-04-15T09:58:00Z

SERVICE             STATUS    SLOs   BUDGET
─────────────────────────────────────────────
fraud-detect        WARNING   1/3    28.0% remaining  ← was 98.2%
payment-api         HEALTHY   2/2    94.3% remaining
checkout-svc        HEALTHY   2/2    99.1% remaining
order-service       HEALTHY   2/2    97.2% remaining

Summary: 4 services, 9 SLOs, 1 warning. Error budget period: 22 days remaining.
```

**Implementation:**

```bash
# Final step in scenario runner:
echo ""
echo "Post-incident portfolio..."
nthlayer-observe collect \
  --specs-dir "$SPECS_DIR" \
  --prometheus-url "$PROMETHEUS_URL" \
  --store "$ASSESSMENT_STORE"

nthlayer-observe portfolio --store "$ASSESSMENT_STORE" --format table
echo ""
echo "fraud-detect budget consumed. All other services unaffected."
```

The before/after comparison is the payoff. "Here's what the incident cost you" is more visceral than "incident resolved."

---

## Content-Addressed Hashes (Throughout)

This isn't a separate step — it's visible in every output.

**What changes:** Every verdict and assessment the demo produces should include its hash in the output. The audience sees the chain forming in real time.

**Implementation options (pick one):**

**Option A: Modify CLI output formatters.** Each command's table/text output includes a `Hash` column or an inline hash reference. This is the cleanest but requires changes to observe and respond CLI formatters.

**Option B: Post-process with a wrapper.** The scenario runner queries the assessment/verdict store after each step and prints the latest record's hash and input references:

```bash
# Helper function for scenario runner
show_latest_record() {
  local store="$1"
  local type="$2"
  python3 -c "
from nthlayer_observe.sqlite_store import SQLiteAssessmentStore
from nthlayer_observe.assessment import AssessmentFilter
store = SQLiteAssessmentStore('$store')
results = store.query(AssessmentFilter(assessment_type='$type', limit=1))
if results:
    r = results[0]
    print(f'  Record: {r.id}')
    print(f'  Hash:   {r.hash[:12]}...')
    if hasattr(r, 'input_hashes') and r.input_hashes:
        print(f'  Inputs: {[h[:12] + \"...\" for h in r.input_hashes]}')
"
}
```

**Option C: Verbose flag.** Add `--verbose` to CLI commands that includes hash information. Default output stays clean, demo runs with `--verbose`.

**Recommendation:** Option C. Least invasive, doesn't clutter default output, gives the demo presenter control over when hashes are visible.

---

## Scenario Runner Changes

The scenario runner (`demo/scenario-runner.py` or `demo.sh scenario`) is the only file that changes significantly. The trigger chain (measure → correlate → respond → learn) is unchanged.

### Updated scenario flow:

```bash
scenario() {
  ASSESSMENT_STORE="$OUTPUT_DIR/assessments.db"
  
  # Step 1: Baseline portfolio
  echo "━━━ STEP 1: Portfolio Health (Baseline) ━━━"
  nthlayer-observe collect --specs-dir "$SPECS_DIR" --prometheus-url "$PROMETHEUS_URL" --store "$ASSESSMENT_STORE"
  nthlayer-observe portfolio --store "$ASSESSMENT_STORE"
  sleep 3
  
  # Step 2: Degrade (existing)
  echo "━━━ STEP 2: Triggering Incident ━━━"
  curl -s -X POST "http://localhost:8001/control" -d '{"reversal_rate": 0.18, "error_rate": 0.042}'
  echo "fraud-detect degraded. Waiting for metrics to propagate..."
  sleep 30
  
  # Step 3: Detect (existing)
  echo "━━━ STEP 3: Breach Detection ━━━"
  nthlayer-observe collect --specs-dir "$SPECS_DIR" --prometheus-url "$PROMETHEUS_URL" --store "$ASSESSMENT_STORE"
  nthlayer measure --evaluate-once --specs-dir "$SPECS_DIR" --prometheus-url "$PROMETHEUS_URL" --verdict-store "$VERDICT_STORE"
  
  # Step 4: Explain (new)
  echo "━━━ STEP 4: Budget Explanation ━━━"
  nthlayer-observe explain --store "$ASSESSMENT_STORE" --service fraud-detect
  sleep 3
  
  # Step 5: Correlate (existing)
  echo "━━━ STEP 5: Root Cause Correlation ━━━"
  # (trigger chain handles this — measure invokes correlate)
  
  # Step 6: Respond + Learn (existing)
  echo "━━━ STEP 6: Incident Response ━━━"
  # (trigger chain handles this — correlate invokes respond, then learn)
  
  # Step 7: Deployment gate (new)
  echo "━━━ STEP 7: Deployment Gate ━━━"
  nthlayer-observe check-deploy --service fraud-detect --store "$ASSESSMENT_STORE"
  echo "Deploy BLOCKED. Error budget must recover."
  sleep 3
  
  # Step 8: Post-incident portfolio (new)
  echo "━━━ STEP 8: Portfolio Health (Post-Incident) ━━━"
  nthlayer-observe collect --specs-dir "$SPECS_DIR" --prometheus-url "$PROMETHEUS_URL" --store "$ASSESSMENT_STORE"
  nthlayer-observe portfolio --store "$ASSESSMENT_STORE"
  echo ""
  echo "Demo complete. fraud-detect budget consumed. Deploy gate blocking. All other services unaffected."
}
```

---

## Pre-requisites (Verify Before Starting)

Before implementing, verify these commands work against the demo infrastructure:

```bash
# 1. Docker stack is up, fake services exporting metrics
docker compose up -d
curl -sf http://localhost:9090/-/ready

# 2. Observe collect works against demo Prometheus
nthlayer-observe collect --specs-dir ./demo/specs --prometheus-url http://localhost:9090 --store /tmp/test.db

# 3. Portfolio shows real data
nthlayer-observe portfolio --store /tmp/test.db

# 4. Explain produces output (may need breach data — test after degrading)
curl -X POST http://localhost:8001/control -d '{"error_rate": 0.05}'
sleep 15
nthlayer-observe collect --specs-dir ./demo/specs --prometheus-url http://localhost:9090 --store /tmp/test.db
nthlayer-observe explain --store /tmp/test.db --service fraud-detect

# 5. Check-deploy reads from store
nthlayer-observe check-deploy --service fraud-detect --store /tmp/test.db

# 6. Existing trigger chain still works
# (run the current demo.sh scenario and verify measure → correlate → respond → learn)
```

If any of these fail, fix the command before modifying the demo. The demo should use working commands, not paper over broken ones.

---

## What This Does NOT Change

- The trigger chain (measure → correlate → respond → learn) is untouched
- The fake services are untouched
- The Docker Compose stack is untouched
- The React topology view is untouched (future enhancement)
- No Slack integration (future — needs respond comms)
- No approval workflow (future — needs serve modes)

---

## Acceptance Criteria

1. Demo runs end-to-end with 8 steps visible in terminal output
2. Portfolio shows meaningful before/after comparison (budget numbers change)
3. Explain produces human-readable budget narrative for breaching service
4. check-deploy returns exit code 2 (BLOCKED) after incident
5. All assessments in the store have content-addressed hashes
6. Existing trigger chain (steps 2, 3, 5, 6) works identically to current demo
7. Total demo runtime under 5 minutes (including wait times for metric propagation)

---

## Effort

2-3 days. Mostly integration work — the commands exist, the demo infrastructure exists. The work is wiring them together in the scenario runner and verifying the output is meaningful against real (fake) metrics.
