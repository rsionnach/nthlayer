<div align="center">
  <a href="https://github.com/rsionnach/nthlayer">
    <img src="presentations/public/nthlayer_dark_banner.png" alt="NthLayer" width="400">
  </a>
</div>

# NthLayer

**An open-source reliability platform for SREs.** NthLayer compiles your service reliability requirements — SLOs, alerts, dashboards, deployment gates, dependency graphs — into observable production infrastructure, then runs an autonomous reliability runtime that observes those services, judges their health, correlates incidents, responds to breaches, and learns from outcomes. Built on the [OpenSRM specification][opensrm].

[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![Status: v1.5 in development](https://img.shields.io/badge/Status-v1.5%20in%20development-orange.svg)](#current-status)

This repository is the **project front door**. The implementation lives in the per-tier ecosystem repos described below.

## The ecosystem

NthLayer is a six-repo system. One specification, one shared library, one compiler, three runtime tiers:

| Repo | Role |
|---|---|
| [`opensrm`][opensrm] | The OpenSRM specification — the manifest format and language for declaring reliability. |
| [`nthlayer-common`][common] | Shared library: verdict model, manifest parser, LLM wrapper, error hierarchy, CoreAPIClient. Imported by every other repo. |
| [`nthlayer-generate`][generate] | The deterministic compiler: specs → SLOs, alerts, dashboards, recording rules, Backstage entities. CI/CD gate via GitHub Action. |
| [`nthlayer-core`][core] | **Tier 1** — reliability-critical state. HTTP API server, verdict store, case management, manifest catalogue. `pip install nthlayer`. |
| [`nthlayer-workers`][workers] | **Tier 2** — background computation. Five worker modules: `observe` (SLO assessment), `measure` (judgment SLO eval), `correlate` (session-window event correlation), `respond` (incident response coordinator), `learn` (outcome resolution + retrospectives). All communicate with core via HTTP. |
| [`nthlayer-bench`][bench] | **Tier 3** — operator interface. Textual TUI for SREs: situation board, case bench, approval flows, on-call status. |

## Where to start

**You want to evaluate NthLayer for your organisation.** Start at [`opensrm`][opensrm] for the architectural model, then read [`nthlayer-generate`'s README][generate] for the build-time experience and walk through the example service definitions there.

**You want to use NthLayer's GitHub Action in your CI pipeline.** This repo's `action.yml` is the entry point — add `uses: rsionnach/nthlayer@v1` (or pin to a specific tag) to your workflow. The action delegates to [`nthlayer-generate`][generate]; see its README for the supported subcommands.

**You want to contribute to a specific component.** Each implementation repo has its own contributor guide, test suite, and CLAUDE.md. Pick the tier or layer relevant to your interest and open a PR there.

**You want to understand the design decisions.** Architectural decisions, RFCs, and migration plans live in [`opensrm/docs/superpowers/`][opensrm-docs]. Notable: the [three-tier architecture decision (2026-04-21)][tier-decision] and the [six-repo consolidation rationale (2026-04-21)][consol].

## Reading list

<!-- TODO: Rob to insert dev.to article series link here. Series introduces NthLayer's ZFC (Zero Framework Cognition) model, the OpenSRM spec, and the v1.5 architecture. -->

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
[opensrm-docs]: https://github.com/rsionnach/opensrm/tree/main/docs/superpowers
[tier-decision]: https://github.com/rsionnach/opensrm/blob/main/docs/superpowers/specs/2026-04-21-spec-revision-summary.md
[consol]: https://github.com/rsionnach/opensrm/blob/main/docs/superpowers/specs/2026-04-21-repo-consolidation-recommendation.md
