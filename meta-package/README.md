# nthlayer

**NthLayer is an ecosystem of components for AI-augmented operations governance.** This package is a meta-package that installs all four tiers:

- **`nthlayer-core`** (Tier 1) — reliability-critical state, verdicts, assessments, manifests, change-freezes (HTTP API server)
- **`nthlayer-workers`** (Tier 2) — observe / measure / correlate / respond / learn worker modules
- **`nthlayer-bench`** (Tier 3) — operator interface (Textual TUI)
- **`nthlayer-generate`** — manifest compiler and CI/CD generator (specs → Grafana dashboards, Prometheus alerts, SLOs, recording rules, Backstage entities)

## Installation

```bash
pip install nthlayer==1.0.0
```

This installs all four sub-packages pinned to their matching `1.0.0` releases.

## When to install the meta-package vs. individual components

For most production deployments, install the **specific tier(s) you need** rather than the meta-package:

```bash
pip install nthlayer-core      # Tier 1 only
pip install nthlayer-workers   # Tier 2 only
pip install nthlayer-bench     # Tier 3 only
pip install nthlayer-generate  # Compiler only
```

The meta-package is a friendly entry point for **evaluators, demos, and local development** where you want the full ecosystem available with a single command.

## CLI binaries

Sub-packages provide their own console scripts:

- `nthlayer` / `nthlayer-generate` — compile manifests (from `nthlayer-generate`; the two names are aliases)
- `nthlayer-core serve` — start the Tier 1 HTTP API server (from `nthlayer-core` >= 4.0.0; earlier releases named this script `nthlayer`; this meta-package currently pins an older core, pin update pending bead opensrm-lt91)
- `nthlayer-workers serve` — start the worker runtime (from `nthlayer-workers`)
- `nthlayer-learn` — verdict-learning CLI (from `nthlayer-workers`)
- `nthlayer-bench` — launch the operator TUI (from `nthlayer-bench`)
- `nthlayer-override-adapter` — override-event sidecar (from `nthlayer-override-adapter`; not a dependency of this meta-package, install it separately)

The meta-package itself contributes no Python modules and no console scripts.

## Documentation

See https://github.com/rsionnach/nthlayer for the project front door, architecture overview, and links to each component repo.

## Licence

MIT.
