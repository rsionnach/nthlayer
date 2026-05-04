# NthLayer Demo — Interactive Step-Through Mode

## Problem

The current demo runs in real time. All verdicts appear in 2-3 minutes. The verdict stream panel is too small to read while also watching the topology. The audience can't keep up, and the presenter can't pause to explain what's happening. The topology — the most visually impressive part — is underused as a storytelling surface.

## Solution

Add a step-through mode to the live demo. Verdicts appear as overlays anchored to the relevant node on the topology (not just in the side panel). The demo pauses at each verdict, allowing the presenter to talk. A "Next" control advances to the next verdict. The topology becomes the presentation canvas.

## Two Modes

The live topology page supports two demo modes:

**Real-time mode** (`?mode=live`) — the current behaviour. Verdicts stream in as they're produced. No pausing. Good for showing the system running autonomously after the audience has seen the step-through.

**Step-through mode** (`?mode=guided`) — new. The scenario runs in the background but the UI buffers verdicts and presents them one at a time. Each verdict appears as an overlay at the relevant node. The presenter clicks "Next" to advance. Good for first-time audiences, investor demos, and detailed technical walkthroughs.

The step-through mode reads from the same verdict feed as real-time mode. The difference is purely in the UI — it queues verdicts instead of displaying them immediately.

## Layout

```
Step-through mode:
┌──────────────────────────────────────────────────────────────────────┐
│ ● GUIDED DEMO                              Step 3 of 8    [▶ Next] │
│ Measure detected a judgment SLO breach                              │
│                                                                      │
│  ┌─OBSERVABILITY─┐   ┌─ON-PREM──────────┐    ┌─AWS──────────────┐  │
│  │ ...           │   │                  │    │                  │  │
│  └────────────────┘   │   (services)     │    │    (services)    │  │
│  ┌─NTHLAYER──────┐   └──────────────────┘    └──────────────────┘  │
│  │ generate      │                                                  │
│  │ ●measure ◄────┤   ┌─GCP──────────────────────────────────┐      │
│  │ correlate     │   │                                      │      │
│  │ respond       │   │  analytics    ┌─────────────────┐    │      │
│  │ learn         │   │               │  EVALUATION      │    │      │
│  └────────────────┘   │  feat-store   │  reversal_rate   │    │      │
│                       │         ◉fraud│  0.026 > 0.015   │    │      │
│                       │               │  BREACH · cons:2 │    │      │
│                       │     search    │  conf 0.85       │    │      │
│                       │               └─────────────────┘    │      │
│                       │          rec                         │      │
│                       └──────────────────────────────────────┘      │
│                                                                      │
│ NTHLAYER · Prometheus · Verdict Store              SERVICES 21      │
│ [◀ Prev]  [▶ Next]  [▶▶ Play All]  [↻ Restart]                    │
└──────────────────────────────────────────────────────────────────────┘
```

The verdict overlay appears as a card anchored to the fraud-detect node with a visual connector (line or arrow from the card to the node). The node itself is highlighted (pulsing ring, brighter colour). All other nodes are dimmed to 30% opacity. The NthLayer ecosystem panel highlights the active component (measure in this example).

## Verdict Overlay Cards

Each verdict gets an overlay card positioned near the relevant node on the topology. The card is larger and more readable than the side panel cards — this is the primary reading surface now.

### Card design:

```
┌─ EVALUATION ──────────────────────────────────────┐
│                                                    │
│  fraud-detect · reversal_rate                      │
│                                                    │
│  Current: 2.6%   Target: <1.5%   Status: BREACH   │
│                                                    │
│  Consecutive breaches: 2 (threshold: 2)            │
│  NthLayer-measure evaluated this judgment SLO      │
│  against live Prometheus data.                     │
│                                                    │
│  ▸ nthlayer-measure · confidence 0.85              │
│                                                    │
└────────────────────────────────────────────────────┘
```

The card is:
- Positioned near the relevant node (fraud-detect is in GCP cluster)
- Connected to the node with a subtle line or arrow
- Colour-coded by verdict type (measure purple, correlate gold, respond red, learn green)
- Semi-transparent dark background (`rgba(11,17,32,0.95)`) so the topology is visible behind it
- Dismissible by clicking "Next" (which also shows the next verdict)

### Card content per verdict type:

**EVALUATION (at the affected service node):**
- Service name and SLO name
- Current value vs target
- Breach status and consecutive count
- One-line explanation: "NthLayer-measure evaluated this judgment SLO against live Prometheus data."

**CORRELATION (positioned between affected services, with lines to each):**
- Root cause service and failure type
- Blast radius (list of affected services, each highlighted on the topology)
- Causal reasoning (from the reasoning layer): "Reversal rate breach on fraud-detect with downstream dependency to payment-api. No recent change events — model quality degradation pattern."
- Confidence score

**TRIAGE (at the NthLayer respond diamond):**
- Severity assessment with reasoning
- Team assignment
- Affected SLOs
- "NthLayer-respond's triage agent assessed this using Claude with the OpenSRM spec context."

**INVESTIGATION (at the NthLayer respond diamond or at the root cause node):**
- Root cause with confidence
- Top 2-3 hypotheses with evidence
- "The investigation agent identified this as an AI model quality issue, not infrastructure."

**COMMUNICATION (at the NthLayer respond diamond):**
- Status page title and summary
- Customer impact assessment
- "A status update was drafted for stakeholder communication."

**REMEDIATION (at the affected service node):**
- Recommended action (rollback, scale_up, etc.)
- Rationale
- Approval status
- "The remediation agent recommended rollback based on the OpenSRM spec context identifying this as a judgment SLO breach."

**RETROSPECTIVE (spanning the full blast radius with lines to all affected nodes):**
- Duration, verdict count, decisions affected
- Recommendation with counterfactual
- "NthLayer-learn walked the verdict chain from evaluation through remediation to produce this retrospective."

## Step Sequence

The guided demo has a fixed sequence of steps, each corresponding to a verdict type. The steps are:

| Step | Verdict Type | Anchored To | What Highlights |
|------|-------------|-------------|-----------------|
| 1 | (intro) | — | Full topology, all healthy, "21/21 SLOs HEALTHY" |
| 2 | EVALUATION (OK) | fraud-detect node | fraud-detect pulses, measure diamond lights up |
| 3 | EVALUATION (BREACH) | fraud-detect node | fraud-detect turns amber/red, measure diamond active |
| 4 | CORRELATION | between fraud-detect and payment-api | Both nodes highlight, correlate diamond active, line between them |
| 5 | TRIAGE | respond diamond | respond diamond active, severity badge appears |
| 6 | INVESTIGATION | fraud-detect node | fraud-detect highlighted, hypotheses listed |
| 7 | COMMUNICATION | respond diamond | respond diamond active, status page preview |
| 8 | REMEDIATION | fraud-detect node | fraud-detect highlighted, "rollback" action displayed |
| 9 | RETROSPECTIVE | fraud-detect + payment-api | Both nodes, learn diamond, recommendation displayed |
| 10 | (resolution) | — | All nodes return to healthy, "21/21 SLOs HEALTHY", panel shows summary |

Steps 2-9 each pause and wait for the presenter to click "Next."

## Top Bar

In guided mode, the top of the page shows:

```
● GUIDED DEMO                                    Step 3 of 8    [▶ Next]
Measure detected a judgment SLO breach on fraud-detect
```

- Left: mode indicator (green dot + "GUIDED DEMO")
- Center: step description in plain English (not technical jargon — this is the presenter's narration prompt)
- Right: step counter and Next button

The step descriptions:

| Step | Description |
|------|-------------|
| 1 | "All services healthy. NthLayer monitoring from OpenSRM specs." |
| 2 | "Measure evaluating fraud-detect judgment SLO — reversal rate climbing." |
| 3 | "Judgment SLO breach detected. Reversal rate exceeds target." |
| 4 | "Correlate identified root cause and blast radius across dependency graph." |
| 5 | "Triage assessed severity: AI model quality degradation." |
| 6 | "Investigation identified root cause with 85% confidence." |
| 7 | "Communication agent drafted status page update." |
| 8 | "Remediation recommended rollback — awaiting human approval." |
| 9 | "Retrospective captured. Spec recommendation generated. Loop closed." |
| 10 | "Services recovered. All SLOs healthy." |

These descriptions serve as teleprompter text for the presenter. They're phrased as talking points, not verdict summaries.

## Bottom Controls

```
[◀ Prev]  [▶ Next]  [▶▶ Play All]  [↻ Restart]
```

- **Prev:** Go back one step. The overlay reverts to the previous verdict. Useful for "let me show you that again."
- **Next:** Advance to the next step. If the verdict hasn't arrived yet (the scenario runner hasn't produced it), show a subtle "waiting for next verdict..." indicator. This handles timing mismatches between the scenario runner and the UI.
- **Play All:** Switch to real-time mode from the current step. All remaining verdicts stream in without pausing. Useful for the end of the demo: "now let me show you it running autonomously."
- **Restart:** Clear all verdicts, reset to step 1, re-run the scenario. Useful for "let me run that again."

Keyboard shortcuts:
- Right arrow or Space: Next
- Left arrow: Prev
- P: Play All
- R: Restart

## How It Works Technically

### Verdict buffering

In guided mode, the verdict feed polling continues as normal (every 2 seconds). But instead of rendering verdicts immediately, they're pushed into a queue:

```javascript
const [verdictQueue, setVerdictQueue] = useState([]);
const [currentStep, setCurrentStep] = useState(0);
const [displayedVerdicts, setDisplayedVerdicts] = useState([]);

// On each poll, add new verdicts to the queue
useEffect(() => {
  const newVerdicts = fetchedVerdicts.filter(v => !seenIds.has(v.id));
  if (newVerdicts.length > 0) {
    setVerdictQueue(prev => [...prev, ...newVerdicts]);
  }
}, [fetchedVerdicts]);

// "Next" advances by moving the next verdict from queue to displayed
const handleNext = () => {
  if (currentStep < verdictQueue.length) {
    setDisplayedVerdicts(prev => [...prev, verdictQueue[currentStep]]);
    setCurrentStep(prev => prev + 1);
  }
};
```

### Node anchoring

Each verdict type maps to a node ID (or set of node IDs) on the topology:

```javascript
function getAnchorNodes(verdict) {
  const type = verdict.subject?.type;
  const service = verdict.subject?.ref;

  switch (type) {
    case "evaluation":
      return [service];  // e.g. ["fraud-detect"]
    case "correlation":
      const blast = verdict.metadata?.custom?.blast_radius || [];
      return blast.map(b => b.service || b);  // e.g. ["fraud-detect", "payment-api"]
    case "triage":
    case "communication":
      return ["nthlayer-respond"];  // NthLayer ecosystem panel
    case "investigation":
      return [service, "nthlayer-respond"];
    case "remediation":
      return [service];
    case "retrospective":
      const retro_blast = verdict.metadata?.custom?.blast_radius || [];
      return retro_blast;
    default:
      return [service];
  }
}
```

### Overlay positioning

The overlay card is positioned relative to the anchor node's position on the canvas. Each node already has x,y coordinates in the topology layout. The card is offset to avoid covering the node:

```javascript
function getOverlayPosition(nodePosition, canvasSize) {
  // Position card to the right of the node, or above if near the right edge
  const cardWidth = 400;
  const cardHeight = 200;

  let x = nodePosition.x + 60;  // 60px right of node center
  let y = nodePosition.y - cardHeight / 2;

  // If too far right, position to the left
  if (x + cardWidth > canvasSize.width - 50) {
    x = nodePosition.x - cardWidth - 60;
  }

  // If too far down, shift up
  if (y + cardHeight > canvasSize.height - 100) {
    y = canvasSize.height - cardHeight - 100;
  }

  // If too far up, shift down
  if (y < 80) {
    y = 80;
  }

  return { x, y };
}
```

A line is drawn from the card to the node center using SVG or a CSS border/connector.

### Node highlighting

When a step is active, the anchor nodes are highlighted and all other nodes are dimmed:

```javascript
function getNodeOpacity(nodeId, activeNodes) {
  if (activeNodes.length === 0) return 1.0;  // No active step = all visible
  return activeNodes.includes(nodeId) ? 1.0 : 0.2;
}

function getNodePulse(nodeId, activeNodes) {
  return activeNodes.includes(nodeId);  // CSS animation: pulsing ring
}
```

### Side panel in guided mode

The side verdict stream panel can optionally stay visible in guided mode as a compact timeline showing which steps have been completed:

```
VERDICT TIMELINE
  ✓ 1. Evaluation (OK)
  ✓ 2. Evaluation (BREACH)
  → 3. Correlation          ← current
    4. Triage
    5. Investigation
    6. Communication
    7. Remediation
    8. Retrospective
```

This gives the audience a sense of where they are in the lifecycle. Clicking any completed step jumps back to it.

If the panel real estate is a concern, this can be a thin strip (200px) rather than the full 360px panel.

## Integration with Scenario Runner

The scenario runner doesn't change. It runs the same way in both modes. The difference is:

- **Real-time mode:** The browser polls the verdict feed and renders immediately.
- **Guided mode:** The browser polls the verdict feed, queues verdicts, and waits for the presenter to advance.

The timing works because the scenario runner produces all verdicts within ~90 seconds, and the guided mode buffers them. The presenter can take 10 minutes to step through 8 verdicts — the scenario runner finished long ago.

**One timing consideration:** If the presenter clicks "Next" before the next verdict has arrived in the feed, the UI should show a brief "Waiting for NthLayer..." indicator. This can happen if the presenter is fast or the scenario runner is slow. The indicator disappears when the next verdict arrives.

To avoid this, the presenter should start the scenario (`./demo.sh scenario` in the terminal) and wait about 90 seconds for it to complete before beginning the step-through. All verdicts are in the store. The guided mode just presents them one at a time. Alternatively, the step-through could start automatically once all expected verdict types are in the feed.

## URL Parameters

```
?mode=live        — real-time mode (current behaviour)
?mode=guided      — step-through mode (new)
?mode=guided&auto — step-through mode, auto-advance every 10 seconds (for recordings)
?step=5           — start at step 5 (for jumping to specific moments)
```

## Implementation Order

1. **Verdict queue and step state** — buffer verdicts instead of rendering immediately
2. **Top bar with step descriptions** — mode indicator, step counter, Next button
3. **Bottom controls** — Prev, Next, Play All, Restart with keyboard shortcuts
4. **Node highlighting and dimming** — activeNodes opacity, pulsing ring animation
5. **Overlay cards** — positioned near anchor nodes, connected with lines, styled per verdict type
6. **Overlay positioning logic** — edge detection, responsive placement
7. **Timeline sidebar** — compact step progress indicator
8. **Auto-advance mode** — for recording demos as videos

## What This Replaces

The side verdict stream panel in guided mode becomes optional (collapsed by default, available via the ≡ toggle). The overlay cards are the primary verdict display. The panel is still useful in real-time mode for monitoring, but in guided mode the overlays do the storytelling.

## Files Changed

- Live topology HTML (wherever the demo page lives) — all changes are in the React component
- No changes to the scenario runner, verdict feed, or any NthLayer component
- No new backend infrastructure

## Notes for Claude Code

- The overlay cards must be readable at a glance. Minimum font size 14px for the main content. The card is the presentation surface — it needs to be large enough to read from 2 metres away on a shared screen.
- The connector line from the card to the node should be subtle (1px, `#1E2A3A` or `#88c0d030`) — it's a visual anchor, not a diagram element.
- The pulsing ring animation on highlighted nodes should be smooth and subtle — a gentle opacity oscillation, not a strobe.
- The "Play All" button switching to real-time mode should be a smooth transition, not a jarring mode switch. The current overlay fades out, remaining verdicts stream into the side panel.
- Test with the full 21-service topology to ensure overlay cards don't overlap with nodes in dense areas (especially the AWS cluster).
