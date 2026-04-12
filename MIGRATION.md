# Migration Guide: NthLayer Runtime → nthlayer-observe

**As of v0.1.0a20**, NthLayer is a **pure deterministic compiler**: it reads OpenSRM manifests and generates monitoring artifacts (Prometheus rules, Grafana dashboards, alert configurations, topology exports). All runtime infrastructure has moved to [nthlayer-observe](https://github.com/rsionnach/nthlayer-observe).

If you were using any of the runtime commands listed below, install nthlayer-observe:

```bash
pip install nthlayer-observe
```

## Command Migration

| What you used | Old command | New command |
|--------------|------------|------------|
| SLO collection | `nthlayer collect` | `nthlayer-observe collect` |
| Drift detection | `nthlayer drift` | `nthlayer-observe drift` |
| Metric verification | `nthlayer verify` | `nthlayer-observe verify` |
| Deployment gates | `nthlayer check-deploy` | `nthlayer-observe check-deploy` |
| Budget explanations | `nthlayer explain` | `nthlayer-observe explain` |
| Dependency discovery | `nthlayer deps` | `nthlayer-observe dependencies` |
| Blast radius analysis | `nthlayer blast-radius` | `nthlayer-observe blast-radius` |
| Portfolio health | `nthlayer portfolio` | `nthlayer-observe portfolio` |
| Service scorecard | `nthlayer scorecard` | `nthlayer-observe scorecard` |

## What stays in NthLayer

These commands are unchanged and still work in `nthlayer`:

- `nthlayer validate` — validate OpenSRM manifests
- `nthlayer validate-spec` — OPA policy validation
- `nthlayer validate-slo` — verify PromQL metrics exist
- `nthlayer apply` / `nthlayer plan` — generate monitoring artifacts
- `nthlayer generate-*` — generate alerts, dashboards, recording rules, docs
- `nthlayer topology export` — export dependency graph
- `nthlayer slo show` / `slo list` — display SLO definitions

## Code Migration

If you imported from NthLayer's Python API:

| Old import | New import |
|-----------|-----------|
| `from nthlayer.slos.collector import SLOMetricCollector` | `from nthlayer_observe.slo import SLOMetricCollector` |
| `from nthlayer.slos.gates import DeploymentGate` | `from nthlayer_observe.gate import check_deploy` |
| `from nthlayer.drift import DriftAnalyzer` | `from nthlayer_observe.drift import DriftAnalyzer` |
| `from nthlayer.policies.evaluator import PolicyEvaluator` | Moved to nthlayer-observe |
| `from nthlayer.db import ...` | Removed — nthlayer-observe uses SQLite assessments |
| `from nthlayer.api import ...` | Removed — nthlayer-observe will provide its own API |

## Removed Dependencies

These are no longer required by NthLayer (they were runtime-only):

`fastapi`, `uvicorn`, `sqlalchemy`, `alembic`, `psycopg`, `redis`, `aws-xray-sdk`, `PyJWT`, `jwcrypto`, `python-json-logger`, `orjson`, `tenacity`, `circuitbreaker`

## Architecture

```
Before (v0.1.0a19 and earlier):
  nthlayer = compiler + runtime (mixed)

After (v0.1.0a20+):
  nthlayer         = pure compiler (specs → artifacts, stateless, no runtime)
  nthlayer-observe = runtime infrastructure (live state → assessments, stateful, no LLM)
```

The compiler and runtime layers are now cleanly separated. `nthlayer` has zero runtime state, zero database dependencies, and zero long-running processes.

## Questions?

- [nthlayer-observe README](https://github.com/rsionnach/nthlayer-observe)
- [OpenSRM ecosystem overview](https://github.com/rsionnach/opensrm)
