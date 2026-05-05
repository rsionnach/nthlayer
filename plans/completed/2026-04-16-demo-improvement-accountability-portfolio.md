# Plan: Demo Improvement — Accountability & Portfolio Story

**Source specs:** `DEMO-IMPROVEMENT-SPEC.md`, `REACT-FLOW-MIGRATION-SPEC.md`
**Beads epic:** `opensrm-42y`
**Created:** 2026-04-16
**Status:** active

## Requirements

Extracted from the spec. Each requirement maps to one or more Beads issues.

- [ ] Verify all nthlayer-observe commands work against demo infrastructure before modifying anything -> `opensrm-42y.1`
- [ ] Wire ASSESSMENT_STORE, OBSERVE command, and color prefix into demo.sh scenario -> `opensrm-42y.2`
- [ ] Add OpenSRM specs for all services shown in portfolio output -> `opensrm-42y.8`
- [ ] Step 1: Baseline portfolio collection before degradation -> `opensrm-42y.3`
- [ ] Step 4: Budget explanation after breach detection -> `opensrm-42y.4`
- [ ] Step 7: Deployment gate check (BLOCKED, exit code 2) after incident -> `opensrm-42y.5`
- [ ] Step 8: Post-incident portfolio showing budget consumed -> `opensrm-42y.6`
- [ ] Content-addressed hashes visible throughout demo output -> `opensrm-42y.7`
- [ ] Full CLI E2E validation against all 7 acceptance criteria -> `opensrm-42y.9`

### Track B: React Flow Migration (REACT-FLOW-MIGRATION-SPEC.md)

- [ ] Phase 1: Scaffold + static topology (Vite, React, @xyflow/react, ServiceNode, PlatformGroup, edges, Nord palette) -> `opensrm-42y.10`
- [ ] Phase 2: Live data + health polling (useHealthPolling, node/edge health colours, real-time mode) -> `opensrm-42y.11`
- [ ] Phase 3: Guided step-through (useGuidedMode, GuidedBar, viewport animation, dimming, VerdictCard, panels, keyboard) -> `opensrm-42y.12`
- [ ] Phase 4: Integration — wire panels to real observe/verdict data from demo.sh output -> `opensrm-42y.13`
- [ ] Phase 5: Polish (MiniMap, Controls, transitions, loading/error states, vite build) -> `opensrm-42y.14`
- [ ] Full E2E: demo.sh scenario drives React Flow topology through all 8 guided steps -> `opensrm-42y.15`

## Dependency Chain

Two parallel tracks converging at Phase 4 integration:

```
TRACK A (CLI — demo.sh)              TRACK B (Visual — React Flow)
========================              ============================
opensrm-42y.1 (preflight)            opensrm-42y.10 (Phase 1: scaffold)
├── opensrm-42y.2 (plumbing)              │
│   └─┐                                   └── opensrm-42y.11 (Phase 2: live data)
│     opensrm-42y.3 (Step 1)                   │
│       └── opensrm-42y.4 (Step 4)             └── opensrm-42y.12 (Phase 3: guided)
│           └── opensrm-42y.5 (Step 7)              │
│               └── opensrm-42y.6 (Step 8)          │
│                   └── opensrm-42y.7 (hashes)       │
│                       └── opensrm-42y.9 (CLI E2E)  │
│                                │                    │
└── opensrm-42y.8 (demo specs)  └────────┬───────────┘
    └── opensrm-42y.3 (also)             │
                                 opensrm-42y.13 (Phase 4: integration)
                                          │
                                 opensrm-42y.14 (Phase 5: polish)
                                          │
                                 opensrm-42y.15 (full E2E: CLI + topology)
```

## Key Implementation Notes

### Track A (CLI)
- Steps 2, 3, 5, 6 (degrade, detect, correlate, respond+learn) are UNCHANGED
- Only `demo/demo.sh` `cmd_scenario` function changes significantly
- `nthlayer-observe` commands are already built — this is integration work
- `check-deploy` returns exit 2 (BLOCKED) — must use `set +e` in bash script
- Total demo runtime target: under 5 minutes including metric propagation waits

### Track B (React Flow)
- Replaces bespoke Canvas2D/SVG topology in demo/index.html with @xyflow/react
- Three modes: live (real-time health), guided (8-step walkthrough), static (screenshots/embed)
- Parallel track — does NOT block CLI beads; can start immediately
- Converges at Phase 4 (.13) where guided panels consume real CLI output
- Data handoff design (how demo.sh feeds data to React Flow) is the key Phase 4 decision
- Particle animations deferred — single dot animateMotion is the simpler alternative
- Manual node positions (no auto-layout) — matches current topology aesthetic

## Decision Log

| Date | Decision | Rationale |
|------|----------|-----------|
| | | |

## Deviation Log

| Date | Specified | Implemented | Reason |
|------|-----------|-------------|--------|
| 2026-04-17 | Step 7 check-deploy targets fraud-detect | Step 7 check-deploy targets payment-api | fraud-detect's reversal_rate SLO has a 2m window that heals before Step 7 runs (0.3% consumed). payment-api has 4226% consumed from the cascade phase. Targeting payment-api tells a stronger cascade story: model regression in fraud-detect → budget exhaustion in downstream payment-api → deploy blocked across service boundaries. |

## Completion Summary

_To be filled when plan is completed._
