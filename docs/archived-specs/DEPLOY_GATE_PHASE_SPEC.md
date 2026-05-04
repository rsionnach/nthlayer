# Deploy Gate Phase — Implementation Spec for Live Topology Demo

## Context

The current demo runs 5 phases: Steady State → Bad Deploy → Dual Failure → Correlation → Recovery. The story is reactive: NthLayer detects and resolves incidents after they reach production. Adding a Deploy Gate phase after Recovery closes the loop visually: the system learned from the first incident and prevents the next one. This is the single most important narrative moment for investors because it shows the system improving, not just reacting.

## What to Add

### New Phase: "Deploy Gate" (Phase 6)

Insert after the Recovery phase (currently the last phase at index 4 in the PHASES array). The topology stays fully green throughout this phase. No services degrade. The drama is entirely in the event feed and signals.

**Phase definition to add at the end of the PHASES array (before the closing `]`):**

```javascript
  {
    name: "Deploy Gate", dur: 18000, label: "DEPLOY BLOCKED", color: "#88c0d0",
    desc: "Weeks later, model v2.4 attempts to deploy. The judgment SLO gate — added to the spec after INC-4821 — blocks it before it reaches production.",
    events: [
      { text: "fraud-detect model v2.4 submitted to deploy pipeline · evaluating against judgment SLO gate", tag: "generate", src: "cicd", color: "#88c0d0", nth: true },
      { text: "canary evaluation: reversal rate 2.3% in 15m window (threshold: 2.0%) · judgment SLO error budget insufficient", tag: "generate", src: "gate", color: "#bf616a", nth: true },
      { text: "deploy BLOCKED · model v2.4 rejected · spec recommendation from INC-4821 prevented a repeat incident · the loop is closed", tag: "generate", src: "gate", color: "#a3be8c", nth: true },
    ],
    overrides: {},
    traceAI: false, traceInfra: false,
    signals: [
      { from: "fraud-detect", to: "nthlayer-generate", color: "#88c0d0", delay: 3000 },
      { from: "nthlayer-generate", to: "nthlayer-measure", color: "#b48ead", delay: 6000 },
      { from: "nthlayer-measure", to: "nthlayer-generate", color: "#bf616a", delay: 9000 },
      { from: "nthlayer-learn", to: "nthlayer-generate", color: "#a3be8c", delay: 12000 },
    ],
    ecoActivate: ["nthlayer-generate", "nthlayer-measure", "nthlayer-learn"],
  },
```

**Explanation of the signal flow:**
1. (3s) Signal from fraud-detect to nthlayer-generate: the deploy request arrives
2. (6s) Signal from nthlayer-generate to nthlayer-measure: generate asks measure to evaluate the canary's judgment SLO
3. (9s) Signal from nthlayer-measure back to nthlayer-generate: measure returns the verdict — reversal rate too high, block it (red signal colour)
4. (12s) Signal from nthlayer-learn to nthlayer-generate: the final visual — learn's recommendation flowing back into generate, closing the loop (green signal colour)

**Event timing:** The three events stagger via the existing phase event mechanism. First event appears immediately (deploy submitted). Second event appears mid-phase (canary evaluation fails). Third event appears late (deploy blocked, loop closed). If the current implementation shows all events at once on phase start, the events should be converted to timed signals or the event rendering should be updated to support staggered display.

### Visual Treatment

**The topology stays green.** All service health remains at 1.0 (the default from Recovery). No nodes degrade. No traces fire. This is the visual contrast that makes the phase powerful: the previous phases showed cascading red. This phase shows the system staying green because the bad deploy was blocked.

**fraud-detect should get a brief visual indicator** that a deploy was attempted and blocked. Options (in order of preference):
1. A small shield icon or "✗" badge that appears briefly on the fraud-detect node during the phase, then fades
2. A brief amber pulse on the fraud-detect node (not a health degradation — just a visual "something happened here") that resolves to green
3. The fraud-detect node border briefly flashes the generate colour (#88c0d0) to indicate nthlayer-generate is acting on it

**The ecosystem panel signals are the main visual storytelling.** The signal flow (fraud-detect → generate → measure → generate → learn → generate) shows the closed loop visually. The final learn → generate signal is the money shot: the recommendation from the previous incident flowing back into the generation layer.

### Closing Summary Update

Update the finished overlay's stats array to include the deploy gate. Change from:

```javascript
{[
  { value: "2", label: "INCIDENTS", sub: "detected & separated" },
  { value: "8 min", label: "EARLY WARNING", sub: "before traditional alerts" },
  { value: "0", label: "FALSE CORRELATIONS", sub: "right team, right runbook" },
  { value: "auto", label: "GOVERNANCE", sub: "autonomy reduced for safety" },
].map((s, i) => (
```

To:

```javascript
{[
  { value: "2", label: "INCIDENTS", sub: "detected & separated" },
  { value: "8 min", label: "EARLY WARNING", sub: "before traditional alerts" },
  { value: "0", label: "FALSE CORRELATIONS", sub: "right team, right runbook" },
  { value: "auto", label: "GOVERNANCE", sub: "autonomy reduced for safety" },
  { value: "1", label: "DEPLOY BLOCKED", sub: "loop closed, repeat prevented" },
].map((s, i) => (
```

### Timeline Label

The phase name "Deploy Gate" should appear in the bottom timeline bar alongside the existing phase names. The existing code already handles this dynamically from the PHASES array, so no additional changes are needed beyond adding the phase to the array.

### Phase Duration

18 seconds. This is deliberately generous because:
- The events need time to stagger and be read
- The signal flow has 4 signals that need to be visually distinct
- The audience needs a moment to absorb the implication ("wait, it just prevented the next incident")
- The green topology provides a visual rest after the intensity of the incident phases

### Colour

The phase colour is `#88c0d0` (generate's frost teal). This is deliberate: the deploy gate is a generate function. The spec declared the gate, generate enforces it. Using generate's colour reinforces that the spec is the authority.

## Narrative Arc (Complete)

The full demo now tells this story:

1. **Steady State** (green) — "Here are 21 services. The monitoring was generated from specs."
2. **Bad Deploy** (purple) — "A bad model deployed. NthLayer caught the quality drift 8 minutes before Prometheus."
3. **Dual Failure** (red) — "Two unrelated failures hit simultaneously. Traditional triage would see one wall of alerts."
4. **Correlation** (gold) — "NthLayer separated them. Two root causes. Two teams. Two runbooks."
5. **Recovery** (green) — "Both resolved. The retrospective captured everything. The spec was updated."
6. **Deploy Gate** (teal) — "Weeks later, another bad model tries to deploy. The gate blocks it. The system learned. The loop is closed."

The first five phases show NthLayer reacting. The sixth shows it preventing. That's the difference between monitoring and a reliability platform.

## Notes

- The phase duration brings total demo runtime to approximately 100-105 seconds (from ~83 seconds currently). This is still within the "under two minutes" target for the nthlayer.io embed.
- If the staggered events are not currently supported (i.e. all phase events appear at once), consider implementing a simple timed event queue for this phase specifically, since the narrative depends on the "submitted → evaluated → blocked" sequence being readable.
- The deploy gate phase should work in both simulation mode (nthlayer.io) and live mode (connected to real Prometheus) with the same visual behaviour, since in live mode no actual deploy is happening.
