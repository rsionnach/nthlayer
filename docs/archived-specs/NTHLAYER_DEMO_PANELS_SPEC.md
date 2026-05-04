# NthLayer Demo & Dashboard Specs

Two specs in one document. Option 1 is the immediate demo need. Option 2 is the future product feature.

---

# OPTION 1: Browser-Based Demo Panels

Add a collapsible right-side panel to the existing live topology page. The topology remains the primary view. The panel provides supporting context: verdict stream, key metrics, and CLI activity. One browser window, one URL, correct colours guaranteed.

## Layout

```
Default state (no activity):
┌──────────────────────────────────────────────────────────────────────┐
│ ● 21/21 SLOs HEALTHY                                          [≡]  │
│ LIVE · polling localhost:9090 · verdict store active                 │
│                                                                      │
│  ┌─OBSERVABILITY─┐   ┌─ON-PREM──────────┐    ┌─AWS──────────────┐  │
│  │ Prometheus     │   │                  │    │                  │  │
│  │ Grafana        │   │   (services)     │    │    (services)    │  │
│  │ Other          │   │                  │    │                  │  │
│  └────────────────┘   └──────────────────┘    └──────────────────┘  │
│  ┌─NTHLAYER──────┐   ┌─GCP──────────────┐                          │
│  │ generate      │   │                  │                          │
│  │ measure       │   │   (services)     │                          │
│  │ correlate     │   │                  │                          │
│  │ respond       │   └──────────────────┘                          │
│  │ learn         │                                                  │
│  └────────────────┘                                                  │
│                                                                      │
│ NTHLAYER · Prometheus localhost:9090 · Verdict Store    SERVICES 21  │
└──────────────────────────────────────────────────────────────────────┘

Panel open (verdict activity):
┌─────────────────────────────────────────────┬────────────────────────┐
│ ● 18/21 SLOs HEALTHY                  [≡]  │  VERDICT STREAM    [×] │
│ LIVE · INCIDENT ACTIVE: INC-4821            │                        │
│                                             │  ┌─ EVALUATION ───┐   │
│  ┌─OBSERVABILITY─┐   ┌─ON-PREM────┐        │  │ fraud-detect    │   │
│  │ ...           │   │            │  ┌AWS┐  │  │ reversal 3.1%   │   │
│  └────────────────┘   │ (services) │  │   │  │  │ BREACH          │   │
│  ┌─NTHLAYER──────┐   │            │  │   │  │  └─────────────────┘   │
│  │ generate      │   └────────────┘  │   │  │  ┌─ CORRELATION ──┐   │
│  │ ●measure      │   ┌─GCP────┐     │   │  │  │ root cause:     │   │
│  │ ●correlate    │   │        │     │   │  │  │ fraud-detect    │   │
│  │ respond       │   │        │     └───┘  │  │ model v2.3      │   │
│  │ learn         │   └────────┘            │  └─────────────────┘   │
│  └────────────────┘                         │                        │
│                                             │  ── METRICS ────────── │
│                                             │  Reversal: 3.1% ⚠     │
│                                             │  Error:    0.05  ⚠     │
│                                             │  Alerts:   2 active    │
│                                             │                        │
│ NTHLAYER · Prometheus · Verdict Store       │  ── CLI ────────────── │
│                                             │  measure: breach       │
│                                             │  correlate: running... │
└─────────────────────────────────────────────┴────────────────────────┘
```

## Panel Behaviour

**Toggle button [≡]:** Top-right corner of the topology area. Clicking it opens/closes the panel. Keyboard shortcut: `p` to toggle.

**Auto-open:** When the first verdict with `breach: true` appears in the verdict feed, the panel slides open automatically. This creates the visual moment: calm topology → panel appears → incident unfolds. The audience sees NthLayer activating.

**Auto-close:** When all SLOs return to healthy and no incidents are open, the panel can optionally auto-close after 30 seconds of quiet. Or it stays open until manually closed.

**Panel width:** 320-360px fixed. The topology area shrinks from `100vw` to `calc(100vw - 360px)`. The topology's internal layout should handle this gracefully — the nodes are positioned as percentages of the canvas, so they'll redistribute. If the nodes overlap or get too compressed, add a CSS transition that scales the topology slightly on panel open.

## Panel Sections

The panel has three stacked sections. Each has a small header. They share the available vertical space.

### Section 1: Verdict Stream (top, largest section, ~60% of panel height)

Scrollable list of verdict cards, newest at top. Each card shows:

```
┌─ EVALUATION ──────────────── 14:22:01 ─┐
│ fraud-detect reversal rate 3.1%         │
│ target <1.5% · BREACH · consecutive: 3  │
│ ▶ MEASURE · confidence 0.91            │
└─────────────────────────────────────────┘
```

Card border colour matches the verdict type:
- evaluation: `#b48ead` (measure)
- correlation: `#ebcb8b` (correlate)
- triage/investigation/remediation/communication: `#bf616a` (respond)
- retrospective: `#a3be8c` (learn)
- decision: `#81a1c1` (spec)

**Data source:** Polls `verdict-feed.json` (written by the verdict feed sidecar) every 2 seconds. Same data source the topology's ecosystem panel uses to highlight active components.

**Max visible cards:** 6-8 depending on panel height. Scrollable for more.

### Section 2: Metrics (middle, ~25% of panel height)

Live metrics table, auto-refreshing every 2 seconds. Queries Prometheus HTTP API directly from the browser (same as the topology's health polling).

```
── METRICS ──────────────────────────────
  REVERSAL RATE    3.1%    target <1.5%  ⚠
  ERROR RATE (pay) 0.05    target <0.01  ⚠
  ACTIVE ALERTS    2
  ERROR BUDGET     12% remaining
```

Each row is colour-coded: green (`#a3be8c`) if within target, red (`#bf616a`) if breached, amber (`#ebcb8b`) if within 20% of target.

The metrics shown are:
- fraud-detect reversal rate (judgment SLO)
- payment-api error rate (traditional SLO)
- Active alerts count (from `ALERTS{}` query)
- Error budget remaining (from recording rule)

These are hardcoded for the demo scenario. A production version would dynamically show metrics for the most degraded services.

### Section 3: CLI Output (bottom, ~15% of panel height)

Shows the last 5-8 lines of NthLayer CLI activity. Styled as a mini terminal with monospace font on dark background.

```
── CLI ──────────────────────────────────
  14:22:01 measure  evaluate-once → breach
  14:22:05 correlate trigger → fraud-detect
  14:22:06 respond  INC-4821 opened sev 2
```

Each line is colour-coded by component (same colours as verdict cards).

**Data source:** Polls a `trigger-chain-feed.json` file (written by the trigger chain, same pattern as verdict-feed.json). Each entry is a line of CLI output with a timestamp and component tag.

## Panel Styling

All styling uses the existing NthLayer palette. The panel is part of the same React app, using the same inline styles:

```javascript
// Panel container
{
  position: "fixed",
  right: 0,
  top: 0,
  bottom: 0,
  width: panelOpen ? 360 : 0,
  background: "#0B1120",
  borderLeft: "1px solid #1E2A3A",
  transition: "width 0.3s ease",
  overflow: "hidden",
  zIndex: 30,
  display: "flex",
  flexDirection: "column",
}

// Verdict card
{
  margin: "8px 12px",
  padding: "10px 14px",
  borderRadius: "6px",
  border: `1px solid ${verdictColor}30`,
  borderLeft: `3px solid ${verdictColor}`,
  background: "rgba(11,17,32,0.6)",
}

// Metrics row
{
  fontFamily: "'JetBrains Mono', monospace",
  fontSize: 12,
  color: withinTarget ? "#a3be8c" : "#bf616a",
  padding: "4px 14px",
}

// CLI line
{
  fontFamily: "'JetBrains Mono', monospace",
  fontSize: 11,
  color: componentColor,
  padding: "2px 14px",
  whiteSpace: "nowrap",
  overflow: "hidden",
  textOverflow: "ellipsis",
}
```

## How to Trigger the Demo

The audience sees one browser window. You (the presenter) run commands in a terminal that can be off-screen, on a second display, or in a small terminal window below the browser.

```bash
# 1. Infrastructure is already running (pre-warmed)
#    docker compose up -d was run earlier
#    fake services are running
#    nthlayer generate has loaded rules into Prometheus

# 2. Open the demo in a browser
open "http://localhost:8080/demo?mode=live"

# 3. Wait for the audience to see the healthy topology
#    All nodes green. Panel closed. "21/21 SLOs HEALTHY"

# 4. Trigger the scenario
./demo.sh scenario

# The scenario runner:
#   - Degrades fraud-detect (reversal rate climbs)
#   - Waits for nthlayer-measure to detect (trigger chain fires)
#   - The cascade propagates to payment-api
#   - nthlayer-correlate identifies root cause
#   - nthlayer-respond opens incident
#   - Services recover
#   - nthlayer-learn produces retrospective
#   - Deploy gate blocks model v2.4

# The audience sees (in the browser, automatically):
#   - fraud-detect node turns amber, then red
#   - Panel slides open with first evaluation verdict
#   - Verdict cards stack as measure, correlate, respond fire
#   - Metrics section shows reversal rate climbing
#   - Status changes to "INCIDENT ACTIVE: INC-4821"
#   - NthLayer ecosystem panel highlights active components
#   - After recovery, nodes return to green
#   - Retrospective verdict appears in panel
#   - Status returns to healthy
```

The presenter can narrate over the browser. The terminal is infrastructure, not presentation.

## Trigger Chain Log Feed

The trigger chain (measure invoking correlate, correlate invoking respond) already writes to `demo-output/trigger-chain.log`. Add a small sidecar alongside the verdict feed sidecar that converts the log to JSON:

```bash
# In demo.sh start, alongside the verdict feed sidecar:
while true; do
  tail -20 "$OUTPUT_DIR/trigger-chain.log" 2>/dev/null | \
    python3 -c "
import sys, json, re
lines = []
for line in sys.stdin:
    line = re.sub(r'\x1b\[[0-9;]*m', '', line.strip())  # Strip ANSI
    if line:
        lines.append(line)
json.dump(lines[-8:], open('$OUTPUT_DIR/trigger-chain-feed.json', 'w'))
" 2>/dev/null
  sleep 2
done &
```

The panel's CLI section polls this file every 2 seconds.

## What the Bottom Bar Becomes

The current footer stays as the connection status indicator, but gains a second row showing live infrastructure health. This is how the audience knows the demo is backed by real services, not mock data. The proof is subtle and discoverable, not shouted.

**Row 1 (existing, keep as-is):**
```
NTHLAYER · Prometheus localhost:9090 · Verdict Store          SERVICES 21  ECOSYSTEM 5
```

**Row 2 (new, infrastructure health indicators):**
```
Prometheus ● localhost:9090    Grafana ● localhost:3000    Services ● 8/8    Scrape 5s
```

Each indicator polls its health endpoint every 10 seconds:

- **Prometheus:** `GET {prometheus_url}/-/ready` — green dot (`#a3be8c`) if 200, red dot (`#bf616a`) if unreachable
- **Grafana:** `GET {grafana_url}/api/health` — green dot if 200, red dot if unreachable
- **Services:** count of fake services responding to `/metrics` — green if all healthy, amber (`#ebcb8b`) if some down, red if majority down
- **Scrape:** shows the Prometheus scrape interval (informational, static from config)

The dots are small circles (`8px`, rendered as inline SVG or CSS border-radius circles). Labels are `JetBrains Mono` 10px in `#4A5568`. The row is only visible in `?mode=live`, not in the mock demo.

**Make "Grafana" a clickable link** that opens `localhost:3000` in a new tab. This gives the presenter a one-click path to "want to see this in Grafana?" during the demo. The Grafana dashboards were generated by nthlayer-generate from the same OpenSRM specs — seeing the same incident data in Grafana panels is undeniable proof that the infrastructure is real.

**Styling:**

```javascript
// Infrastructure health row
{
  display: "flex",
  gap: 24,
  padding: "4px 16px",
  fontFamily: "'JetBrains Mono', monospace",
  fontSize: 10,
  color: "#4A5568",
}

// Health dot
{
  width: 8,
  height: 8,
  borderRadius: "50%",
  display: "inline-block",
  marginRight: 6,
  background: isHealthy ? "#a3be8c" : "#bf616a",
}

// Grafana link
{
  color: "#4A5568",
  textDecoration: "none",
  cursor: "pointer",
  transition: "color 0.2s",
}
// On hover: color: "#88c0d0"
```

**Health polling implementation:**

```javascript
// Poll infrastructure health every 10s (separate from the 5s Prometheus metrics poll)
useEffect(() => {
  if (mode !== "live") return;
  const interval = setInterval(async () => {
    const promHealth = await fetch(`${prometheusUrl}/-/ready`)
      .then(r => r.ok).catch(() => false);
    const grafanaHealth = await fetch(`${grafanaUrl}/api/health`)
      .then(r => r.ok).catch(() => false);
    // Service health is already tracked by the node health polling
    setInfraHealth({ prometheus: promHealth, grafana: grafanaHealth });
  }, 10000);
  return () => clearInterval(interval);
}, [mode]);
```

## Implementation

All changes are in the single live topology HTML file. No new files needed (except the trigger-chain-feed sidecar line in demo.sh).

1. Add React state for panel: `const [panelOpen, setPanelOpen] = useState(false)`
2. Add verdict feed polling (already exists for ecosystem panel highlighting — extend it)
3. Add trigger-chain-feed polling (new, same pattern)
4. Add the panel component with three sections
5. Add the toggle button
6. Add auto-open logic: when a verdict with `breach: true` in metadata.custom arrives, `setPanelOpen(true)`
7. Add Prometheus metrics polling for the metrics section (can reuse the existing health polling, just display the raw values in the panel)
8. Adjust the topology container width: `width: panelOpen ? "calc(100% - 360px)" : "100%"` with a CSS transition
9. Add infrastructure health row to the bottom bar (Prometheus, Grafana, Services health dots) — only visible in `?mode=live`
10. Make Grafana label a clickable link opening `{grafana_url}` in a new tab

## Files Changed

- `demo/index.html` (or wherever the live topology lives in nthlayer-site) — add panel component, toggle, auto-open logic
- `demo/demo.sh` — add trigger-chain-feed sidecar to the `start` command

---

# OPTION 2: Textual Dashboard (Future Product Feature)

A terminal-based dashboard for SREs who want to monitor NthLayer without opening a browser. Invoked as `nthlayer dashboard`. Built on Textual. This is a product feature, not demo infrastructure. Build it when there's demand from terminal-native users.

## Positioning

The web dashboard (Option 1 evolved into a full product) is for VP Engineering and platform teams who work in browsers. The Textual dashboard is for the SRE on call who has 6 terminal tabs open and wants NthLayer status in one of them. Both read from the same data sources. Different interface, same truth.

Think: `kubectl` vs Kubernetes Dashboard. `lazydocker` vs Docker Desktop. `k9s` vs Lens. The terminal version is for power users. The web version is for everyone else. Both should exist eventually.

## Architecture

```
nthlayer dashboard \
  --prometheus-url http://localhost:9090 \
  --verdict-store ./verdicts.db \
  --specs-dir ./specs/
```

Single Python process. No tmux. No subprocess. Textual manages the layout, panes, live updates, and keyboard navigation within one terminal window.

## Layout

```
┌─ NthLayer Dashboard ─────────────────────────────────────────────────┐
│                                                                       │
│  ┌─ SLO STATUS ──────────────────────────────────────────────────┐   │
│  │ ● fraud-detect    reversal: 1.1%  budget: 72%  ✓ HEALTHY     │   │
│  │ ● payment-api     error:    0.1%  budget: 89%  ✓ HEALTHY     │   │
│  │ ● checkout-svc    latency:  142ms budget: 65%  ✓ HEALTHY     │   │
│  │ ○ order-service   error:    0.8%  budget: 34%  ⚠ WARNING     │   │
│  │ ● user-service    latency:  23ms  budget: 95%  ✓ HEALTHY     │   │
│  │ ...                                                           │   │
│  └───────────────────────────────────────────────────────────────┘   │
│                                                                       │
│  ┌─ VERDICT STREAM ──────────────┐ ┌─ INCIDENTS ────────────────┐   │
│  │ 14:22:01 EVALUATION           │ │ INC-4821  sev 2  OPEN     │   │
│  │   fraud-detect reversal 3.1%  │ │   fraud-detect model_reg  │   │
│  │   BREACH · confidence 0.91    │ │   blast: fraud, payment   │   │
│  │                               │ │   duration: 12m           │   │
│  │ 14:21:55 CORRELATION          │ │                           │   │
│  │   root: fraud-detect          │ │ INC-4820  sev 3  CLOSED  │   │
│  │   model_regression 0.88       │ │   config-service OOM      │   │
│  │                               │ │   duration: 8m            │   │
│  │ 14:21:30 EVALUATION           │ │                           │   │
│  │   payment-api latency ok      │ │                           │   │
│  └───────────────────────────────┘ └─────────────────────────────┘   │
│                                                                       │
│  ┌─ LIFECYCLE ───────────────────────────────────────────────────┐   │
│  │ spec(21) → generate(47 rules) → measure(●) → correlate(●)   │   │
│  │ → respond(1 active) → learn(3 retros)                        │   │
│  └───────────────────────────────────────────────────────────────┘   │
│                                                                       │
│  q quit  r refresh  / search  d details  i incidents  ? help        │
└───────────────────────────────────────────────────────────────────────┘
```

## Components (Textual Widgets)

### SLOStatusTable

A live-updating table showing all services and their SLO state. Each row shows service name, primary SLO metric and current value, error budget remaining, and status (healthy/warning/breached). Rows are colour-coded: green for healthy, amber for warning (budget < 40%), red for breached. Sortable by status (worst first), name, or budget remaining.

**Data source:** Polls Prometheus HTTP API every 5 seconds. Queries recording rule outputs for each service in the specs.

### VerdictStream

A scrollable log of recent verdicts, styled as cards with component colours. Each verdict shows timestamp, type, service, key detail, and confidence. New verdicts appear at the top with a brief highlight animation.

**Data source:** Queries the verdict store directly (SQLite read) every 2 seconds.

### IncidentPanel

Shows open incidents with their root cause, blast radius, severity, and duration. Closed incidents appear below with final duration. Clicking an incident (or pressing Enter) opens a detail view showing the full verdict chain: evaluation → correlation → response → retrospective.

**Data source:** Reads incident verdicts from the verdict store.

### LifecycleBar

A single-line status showing the NthLayer lifecycle state: how many specs exist, how many rules are generated, which components are currently active (polling/evaluating), how many incidents are open, how many retrospectives have been produced. This is the at-a-glance "is NthLayer working?" indicator.

**Data source:** Combination of specs directory listing, Prometheus rule count, verdict store query.

### KeyBindings

- `q` — quit
- `r` — force refresh all panels
- `/` — search services
- `d` — detail view for selected service (show SLO history, recent verdicts, dependency graph as a text tree)
- `i` — focus incidents panel
- `v` — focus verdict stream
- `?` — help

## What the Dashboard Does NOT Include

**No topology visualisation.** The terminal cannot render a 2D node graph that competes with the browser canvas. The dashboard shows the same data in structured form: SLO tables, verdict lists, incident panels. If the user wants the topology, they open the browser. The dashboard can include a command (`t` key) that opens the live topology in the default browser.

**No scenario runner.** The dashboard is a monitoring view, not a demo driver. The scenario runner stays as a separate CLI command.

**No deploy gate.** `nthlayer check-deploy` is a CLI command, not a dashboard feature. The dashboard can show the result of a recent deploy check in the verdict stream, but it doesn't trigger one.

## Textual Specifics

### CSS Styling

Textual uses TCSS (Textual CSS) for styling. The NthLayer palette maps directly:

```tcss
/* nthlayer-dashboard.tcss */

Screen {
    background: #0B1120;
}

#slo-table {
    background: #0B1120;
    border: solid #1E2A3A;
    height: 40%;
}

#slo-table > .datatable--header {
    background: #1E2A3A;
    color: #88c0d0;
}

#verdict-stream {
    background: #0B1120;
    border: solid #1E2A3A;
    width: 60%;
    height: 50%;
}

#incidents {
    background: #0B1120;
    border: solid #1E2A3A;
    width: 40%;
    height: 50%;
}

#lifecycle-bar {
    background: #1E2A3A;
    color: #9CA3AF;
    height: 3;
    dock: bottom;
}

.verdict-card {
    margin: 0 1;
    padding: 0 1;
    background: #0B1120;
}

.verdict-evaluation {
    border-left: tall #b48ead;
}

.verdict-correlation {
    border-left: tall #ebcb8b;
}

.verdict-incident {
    border-left: tall #bf616a;
}

.verdict-retrospective {
    border-left: tall #a3be8c;
}

.healthy {
    color: #a3be8c;
}

.warning {
    color: #ebcb8b;
}

.breached {
    color: #bf616a;
}
```

### App Structure

```python
from textual.app import App, ComposeResult
from textual.containers import Horizontal, Vertical
from textual.widgets import Header, Footer, DataTable, Static, Log
from textual.timer import Timer

class NthLayerDashboard(App):
    CSS_PATH = "nthlayer-dashboard.tcss"
    BINDINGS = [
        ("q", "quit", "Quit"),
        ("r", "refresh", "Refresh"),
        ("/", "search", "Search"),
        ("d", "details", "Details"),
        ("i", "focus_incidents", "Incidents"),
        ("v", "focus_verdicts", "Verdicts"),
        ("t", "open_topology", "Topology"),
        ("?", "help", "Help"),
    ]

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        yield SLOStatusTable(id="slo-table")
        with Horizontal():
            yield VerdictStream(id="verdict-stream")
            yield IncidentPanel(id="incidents")
        yield LifecycleBar(id="lifecycle-bar")
        yield Footer()

    def on_mount(self):
        # Start polling timers
        self.set_interval(5.0, self.refresh_slos)
        self.set_interval(2.0, self.refresh_verdicts)
        self.set_interval(10.0, self.refresh_incidents)

    async def refresh_slos(self):
        # Query Prometheus, update SLO table
        ...

    async def refresh_verdicts(self):
        # Query verdict store, update stream
        ...

    def action_open_topology(self):
        import webbrowser
        webbrowser.open("http://localhost:8080/demo?mode=live")
```

### Dependencies

```
pip install textual httpx
```

Textual includes Rich internally (same author). No additional dependencies for styling.

## Build Priority

This is not urgent. Build it when:
- The core integration (Part A) is stable
- The browser demo (Option 1) is working
- A real user requests terminal-based monitoring
- You want to differentiate from Nobl9 (who has a web UI but no CLI dashboard)

The estimated effort is 3-5 days for a functional v1 with SLO table, verdict stream, and incident panel. The lifecycle bar and detail views add another 2-3 days.

## What Textual-Web Enables Later

Textual apps can be served as web apps via `textual-web`. This means the same Python dashboard code could eventually serve as both a terminal UI and a browser-accessible dashboard without maintaining two separate codebases. This is a longer-term consideration, not an immediate concern. The browser demo (Option 1) uses React because the live topology is already React. The Textual dashboard is a separate entry point for a different audience.

---

## Cleanup: Remove tmux-Based Demo Artifacts

The previous tmux + Rich/gum approach is being replaced entirely by the browser-based panel. All tmux demo artifacts must be removed to avoid confusion, dead code, and maintenance burden.

**Delete these files:**

- `demo/pane-scenario.py` — tmux pane script (replaced by browser panel)
- `demo/pane-scenario.sh` — original bash version if it still exists
- `demo/pane-verdicts.py` — tmux pane script (replaced by browser verdict stream)
- `demo/pane-verdicts.sh` — original bash version if it still exists
- `demo/pane-metrics.py` — tmux pane script (replaced by browser metrics section)
- `demo/pane-metrics.sh` — original bash version if it still exists
- `demo/pane-cli.py` — tmux pane script (replaced by browser CLI section)
- `demo/pane-cli.sh` — original bash version if it still exists
- `demo/.tmux-nthlayer.conf` — tmux theme config (no longer needed)
- `demo/verdict-renderer.py` — standalone verdict renderer (replaced by in-browser rendering)

**Remove from `demo/demo.sh`:**

- The `demo)` case that creates a tmux session, splits panes, and sends commands to them. Replace with a simpler command that just opens the browser to the live topology URL.
- Any references to tmux (`tmux new-session`, `tmux split-window`, `tmux send-keys`, `tmux kill-session`, `tmux attach`)
- Any PID management for pane scripts
- Any gum or Rich dependency checks in the pre-flight

**The revised `demo.sh` commands should be:**

- `start` — Docker stack + fake services + generate rules + verdict feed sidecar + trigger-chain-feed sidecar (unchanged)
- `demo` — Opens the browser to `http://localhost:8080/demo?mode=live`. That's it. No tmux.
- `scenario` — Runs the scenario runner (unchanged)
- `teardown` — Kills Docker, fake services, sidecar processes (remove tmux kill-session)

**Remove dependencies:**

- `gum` is no longer required. Remove from pre-flight checks and from any documentation.
- `rich` is no longer required for the demo (it may still be used elsewhere in NthLayer). Remove from demo-specific requirements if it was added.
- `tmux` is no longer required for the demo. Remove from pre-flight checks.

**Verify after cleanup:**

- `ls demo/pane-*` returns nothing
- `ls demo/.tmux*` returns nothing
- `grep -r "tmux" demo/` returns nothing
- `grep -r "gum" demo/` returns nothing
- `demo/demo.sh start` still works
- `demo/demo.sh demo` opens the browser
- `demo/demo.sh scenario` still runs the scenario
- `demo/demo.sh teardown` cleans up without tmux errors

---

## Implementation Order

1. **Cleanup first:** Remove all tmux demo artifacts listed above. Verify nothing breaks.
2. **Option 1:** Add the collapsible right panel to the live topology. This completes the demo experience.
3. **Option 2 (future):** Build `nthlayer dashboard` as a Textual app when there's product demand.

For Option 1, the changes are entirely within the existing live topology HTML file. No new frameworks. No new dependencies. Just React components using the same inline styles that already work on the page. Claude Code should be able to implement this in one session.
