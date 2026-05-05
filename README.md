<div align="center">
  <a href="https://github.com/rsionnach/nthlayer">
    <img src="presentations/public/nthlayer_dark_banner.png" alt="NthLayer" width="400">
  </a>
</div>

# NthLayer

**An open-source reliability platform for SREs.** NthLayer compiles your service reliability requirements — SLOs, alerts, dashboards, deployment gates, dependency graphs — into observable production infrastructure, then runs an autonomous reliability runtime that observes those services, judges their health, correlates incidents, responds to breaches, and learns from outcomes. Built on the [OpenSRM specification][opensrm].

[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![Status: v1.5 in development](https://img.shields.io/badge/Status-v1.5%20in%20development-orange.svg)](#current-status)

This repository is the **project front door + ecosystem hub**. Implementation lives in the per-tier ecosystem repos described below; ecosystem-spanning artefacts (integration tests, demo materials, specifications, design docs, the GitHub Action, and the PyPI meta-package) live here.

## What's in this repo

Beyond project documentation, this front-door hosts ecosystem-spanning artefacts:

- **GitHub Action** (`action.yml`) — wraps `nthlayer-generate` for CI/CD pipelines via `uses: rsionnach/nthlayer@<tag>`
- **PyPI meta-package** (`meta-package/`) — source for `pip install nthlayer`. Dependency-only; pins the four sub-packages at matching versions (e.g. `==1.0.0`).
- **Integration tests** (`test/`) — three-tier integration test infrastructure (`integration-three-tier.sh`, fake-service exporters, docker-compose stack with Prometheus/Grafana/AlertManager) verifying the runtime architecture end-to-end
- **Demo materials** (`demo/`) — runnable cascading-failure scenario, demo orchestrator (`demo.sh`), and example OpenSRM specifications
- **Specifications** (`docs/specs/`) — current NthLayer architectural specs (Spec Index, Serve Mode v2.1, Bench v2.1, Common, Telemetry Envelope, Learn, Measure, Correlate)
- **Roadmap** (`docs/roadmap/`) — proposed/upcoming features (Discovery, Drift Detection, Execution & Change Events, Missing Capabilities)
- **Archived specs** (`docs/archived-specs/`) — historical record of superseded or shipped designs (see `docs/archived-specs/README.md` for archival criteria)
- **Architectural design docs** (`docs/superpowers/`) — per-phase plans and per-component design specs
- **Operational docs** (`docs/`) — testing conventions, cost optimisation, metrics contract
- **Project-level Claude Code context** (`CLAUDE.md`) — ecosystem orientation for AI-assisted development
- **CI workflows** (`.github/workflows/`) — docs site build, meta-package release, nightly cross-repo three-tier integration test, Docker image publish

## The ecosystem

NthLayer spans seven active repositories: this front-door + ecosystem hub plus six implementation repos — one specification, one shared library, one compiler, and three runtime tiers:

| Repo | Role |
|---|---|
| [`opensrm`][opensrm] | The OpenSRM specification — the manifest format and language for declaring reliability. |
| [`nthlayer-common`][common] | Shared library: verdict model, manifest parser, LLM wrapper, error hierarchy, CoreAPIClient. Imported by every other repo. |
| [`nthlayer-generate`][generate] | The deterministic compiler: specs → SLOs, alerts, dashboards, recording rules, Backstage entities. CI/CD gate via GitHub Action. |
| [`nthlayer-core`][core] | **Tier 1** — reliability-critical state. HTTP API server, verdict store, case management, manifest catalogue. |
| [`nthlayer-workers`][workers] | **Tier 2** — background computation. Five worker modules: `observe` (SLO assessment), `measure` (judgment SLO eval), `correlate` (session-window event correlation), `respond` (incident response coordinator), `learn` (outcome resolution + retrospectives). All communicate with core via HTTP. |
| [`nthlayer-bench`][bench] | **Tier 3** — operator interface. Textual TUI for SREs: situation board, case bench, approval flows, on-call status. |

## Where to start

**You want to evaluate NthLayer for your organisation.** Start at [`opensrm`][opensrm] for the architectural model, then read [`nthlayer-generate`'s README][generate] for the build-time experience and walk through the example service definitions there.

**You want to use NthLayer's GitHub Action in your CI pipeline.** This repo's `action.yml` is the entry point — add `uses: rsionnach/nthlayer@v1` (or pin to a specific tag) to your workflow. The action delegates to [`nthlayer-generate`][generate]; see its README for the supported subcommands.

**You want to contribute to a specific component.** Each implementation repo has its own contributor guide, test suite, and CLAUDE.md. Pick the tier or layer relevant to your interest and open a PR there.

**You want to understand the design decisions.** Architectural decisions, RFCs, and migration plans live in [`docs/superpowers/`](docs/superpowers/). Notable: the [three-tier architecture decision (2026-04-21)][tier-decision] and the [six-repo consolidation rationale (2026-04-21)][consol].

## Current status

NthLayer is in **v1.5 development**. The three-tier architecture is being actively built; the six-repo consolidation completed 2026-04-26. Production-ready usage today centres on `nthlayer-generate` (the compiler — stable surface, CI/CD-ready) plus the OpenSRM spec.

The runtime tiers (`nthlayer-core`, `nthlayer-workers`, `nthlayer-bench`) are implemented and under integration testing for v1.5. Incremental release notes will land in each repo's CHANGELOG as the runtime layers stabilise.

## Licence

MIT. See [LICENSE](LICENSE).

[opensrm]: https://github.com/rsionnach/opensrm
[common]: https://github.com/rsionnach/nthlayer-common
[generate]: https://github.com/rsionnach/nthlayer-generate
[core]: https://github.com/rsionnach/nthlayer-core
[workers]: https://github.com/rsionnach/nthlayer-workers
[bench]: https://github.com/rsionnach/nthlayer-bench
[tier-decision]: docs/superpowers/specs/2026-04-21-spec-revision-summary.md
[consol]: docs/superpowers/specs/2026-04-21-repo-consolidation-recommendation.md
