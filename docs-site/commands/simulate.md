# simulate

Monte Carlo SLO simulation — predict the probability of meeting your SLA from OpenSRM manifests and dependency graphs.

## Synopsis

```bash
nthlayer simulate <manifest-file> [options]
```

## Description

The `simulate` command reads one or more OpenSRM manifests, builds the dependency graph, models each service's failure characteristics as probability distributions, and runs thousands of simulated time periods.

The output is a probability distribution over the target SLA: what's the chance you meet it, when does the error budget likely exhaust, what's the weakest link, and what happens if you change something.

This is **pure transport** — no model calls, no AI. It's arithmetic: sample from distributions, multiply probabilities, aggregate results.

## Exit Codes

| Code | Condition | Meaning |
|------|-----------|---------|
| 0 | P(SLA) >= 80% | Likely to meet SLA |
| 1 | 50% <= P(SLA) < 80% | At risk — investigate dependency reliability |
| 2 | P(SLA) < 50% or error | Unlikely to meet SLA — action required |

When `--min-p-sla` is set, exit code 0 if P(SLA) >= threshold, else 1.

## Options

| Option | Description |
|--------|-------------|
| `--manifests-dir DIR` | Directory containing dependency manifests |
| `--runs N`, `-n N` | Number of simulation runs (default: 10,000) |
| `--horizon DAYS` | Simulation horizon in days (default: 90) |
| `--seed SEED` | Random seed for reproducible results |
| `--what-if SCENARIO` | What-if scenario (repeatable, see below) |
| `--format FORMAT`, `-f` | Output format: `table` or `json` |
| `--min-p-sla FLOAT` | Minimum P(SLA) for CI gate |
| `--demo` | Show demo output with sample data |

## Examples

### Basic Simulation

```bash
nthlayer simulate services/checkout-service.yaml \
  --manifests-dir ./manifests/
```

Output:
```
╭──────────────────────────────────────────────────────────────────╮
│ SLA Simulation: checkout-service                                 │
│ 10,000 runs, 90-day horizon                                      │
╰──────────────────────────────────────────────────────────────────╯

  Target SLA:     99.9% availability
  P(meeting SLA): 73.2%

  Weakest link:   payment-api (contributes 68% of downtime)

  Error budget forecast:
    Median exhaustion:      day 71 of 90
    Worst case (p95):       day 34 of 90

                     Per-Service Results
┏━━━━━━━━━━━━━━━━━━┳━━━━━━━━┳━━━━━━━━┳━━━━━━━━━━━┳━━━━━━━━━━━┳━━━━━━━━━━━━┓
┃ Service          ┃ Target ┃ P(SLA) ┃ Avail p50 ┃ Avail p99 ┃ Downtime % ┃
┡━━━━━━━━━━━━━━━━━━╇━━━━━━━━╇━━━━━━━━╇━━━━━━━━━━━╇━━━━━━━━━━━╇━━━━━━━━━━━━┩
│ checkout-service │ 99.90% │  73.2% │   99.870% │   99.230% │      10.0% │
│ database-primary │ 99.99% │  95.1% │   99.997% │   99.962% │      22.0% │
│ payment-api      │ 99.90% │  81.2% │   99.920% │   99.480% │      68.0% │
└──────────────────┴────────┴────────┴───────────┴───────────┴────────────┘
```

### What-If Scenarios

Explore the impact of architectural changes before implementing them:

```bash
nthlayer simulate services/checkout-service.yaml \
  --manifests-dir ./manifests/ \
  --what-if redundant:payment-api \
  --what-if improve:database-primary:availability:0.9999 \
  --what-if remove:cache-redis
```

Output includes:
```
What-if scenarios:
  redundant:payment-api              P(SLA) 73.2% → 94.6%  (+21.4%)
  improve:database-primary:…:0.9999  P(SLA) 73.2% → 82.1%  (+8.9%)
  remove:cache-redis                 P(SLA) 73.2% → 75.8%  (+2.6%)
```

### JSON Output for CI/CD

```bash
nthlayer simulate services/checkout-service.yaml \
  --manifests-dir ./manifests/ \
  --format json
```

### CI/CD Gate

Block launches when the simulator says you can't meet your SLA:

```bash
nthlayer simulate services/checkout-service.yaml \
  --manifests-dir ./manifests/ \
  --min-p-sla 0.80 \
  --format json

# Exit 0 if P(SLA) >= 80%, exit 1 otherwise
```

### Reproducible Results

```bash
nthlayer simulate services/checkout-service.yaml \
  --seed 42 --runs 50000
```

## What-If Scenario Types

| Scenario | Syntax | Effect |
|----------|--------|--------|
| **Redundant** | `redundant:<service>` | Models active-active redundancy. Effective availability = 1 - (1-A)². |
| **Improve** | `improve:<service>:availability:<value>` | Reruns with the service's availability target changed. |
| **Remove** | `remove:<service>` | Removes this dependency from the graph. Shows the impact of decoupling. |
| **Degrade** | `degrade:<service>:<factor>` | Changes a critical dependency to non-critical with a degradation factor (e.g., 0.95 means 5% of requests fail during dependency outage). |

What-if scenarios that **reduce** reliability are flagged with a warning in the output.

## Simulation Model

### Failure Modelling

Each service is modelled as a stochastic process with failures and recoveries:

- **MTBF** (Mean Time Between Failures): Sampled from an exponential distribution (memoryless, constant failure rate)
- **MTTR** (Mean Time To Recovery): Sampled from a lognormal distribution (right-skewed — most recoveries are fast, some are slow)

When MTBF and MTTR are not explicitly declared, they are derived from the availability target:

```
Availability = MTBF / (MTBF + MTTR)
MTBF = MTTR × Availability / (1 - Availability)
```

For a service targeting 99.9% availability with 1-hour MTTR: MTBF ≈ 999 hours ≈ 41.6 days between failures.

### Dependency Cascading

- **Critical dependency**: When a critical dependency is down, the dependent service is down
- **Non-critical dependency**: When a non-critical dependency is down, the dependent service's availability is reduced by the degradation factor (default: 1% of requests fail)

Services are simulated in topological order (leaf dependencies first), so when simulating a service, its dependencies' failure timelines are already generated.

### Statistical Precision

With 10,000 runs (the default), the standard error on a probability estimate is approximately ±0.8 percentage points (95% CI). For higher precision, increase `--runs`. At 100,000 runs, the confidence interval narrows to ±0.25 percentage points.

Each run is fast — a 90-day simulation of 20 services takes microseconds.

## Manifest Requirements

The simulator reads from standard OpenSRM manifest fields:

| Field | Source | Fallback |
|-------|--------|----------|
| Availability target | `spec.slos.availability.target` | **Required** |
| Dependency graph | `spec.dependencies` | Standalone service |
| Criticality | `spec.dependencies[].critical` | Default: `true` |
| Expected dependency availability | `spec.dependencies[].slo.availability` | Dependency's own SLO target |

### Example Manifest

```yaml
apiVersion: opensrm/v1
kind: ServiceReliabilityManifest
metadata:
  name: checkout-service
  team: commerce
  tier: critical
spec:
  type: api
  slos:
    availability:
      target: 0.999
      window: 30d
  dependencies:
    - name: payment-api
      type: api
      critical: true
      slo:
        availability: 0.999
    - name: cache-redis
      type: cache
      critical: false
      slo:
        availability: 0.999
```

## CI/CD Integration

### GitHub Actions

```yaml
jobs:
  reliability-check:
    steps:
      - name: Simulate SLA Probability
        run: |
          nthlayer simulate services/checkout-service.yaml \
            --manifests-dir ./manifests/ \
            --min-p-sla 0.80 \
            --format json > simulation.json

          if [ $? -ne 0 ]; then
            echo "::error::SLA probability below 80% — review dependency reliability"
            exit 1
          fi
```

### Architecture Review Automation

Before adding a new dependency, quantify the impact:

```bash
nthlayer simulate services/checkout-service.yaml \
  --manifests-dir ./manifests/ \
  --what-if add-dep:checkout-service:new-fraud-service:critical:0.995 \
  --format json
```

## See Also

- [Deployment Gates](./check-deploy.md) — Error budget gates
- [Drift Detection](./drift.md) — Detect degradation trends
- [Validate SLO](./validate-slo.md) — Static SLO feasibility check
- [Blast Radius](./blast-radius.md) — Dependency impact analysis
