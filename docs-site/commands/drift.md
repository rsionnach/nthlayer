# drift

Analyze reliability drift for a service by detecting degradation trends over time.

<div align="center">
  <img src="../assets/drift-demo.gif" alt="nthlayer drift demo" width="700">
</div>

## Synopsis

```bash
nthlayer drift <service-file> [options]
```

## Description

The `drift` command queries Prometheus for historical SLO metrics, analyzes trends using linear regression, and detects patterns that indicate reliability degradation.

This enables **proactive reliability management** - identifying issues before they become incidents by detecting gradual budget erosion, sudden drops, or volatile patterns.

## Exit Codes

| Code | Severity | Meaning |
|------|----------|---------|
| 0 | None/Info | No significant drift or improving trend |
| 1 | Warning | Drift detected, investigate soon |
| 2 | Critical | Severe drift, immediate action needed |

## Options

| Option | Description |
|--------|-------------|
| `--prometheus-url URL` | Prometheus server URL (or use `NTHLAYER_PROMETHEUS_URL` env var) |
| `--environment ENV` | Environment name (dev, staging, prod) |
| `--window WINDOW` | Analysis window (e.g., `30d`, `14d`). Uses tier default if not specified |
| `--slo SLO` | SLO to analyze (default: `availability`) |
| `--format FORMAT` | Output format: `table` or `json` |
| `--demo` | Show demo output with sample data |

## Examples

### Basic Analysis

```bash
nthlayer drift services/payment-api.yaml \
  --prometheus-url http://prometheus:9090
```

Output:
```
╭──────────────────────────────────────────────────────────────╮
│  Drift Analysis: payment-api                                 │
╰──────────────────────────────────────────────────────────────╯

SLO: availability
Window: 30d
Data Range: 2024-12-09 → 2025-01-08

┏━━━━━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━┓
┃ Metric               ┃         Value ┃
┡━━━━━━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━━┩
│ Current Budget       │        72.34% │
│ Trend                │   -0.523%/week│
│ Pattern              │ Gradual Decline│
│ Fit Quality (R²)     │         0.847 │
│ Data Points          │           720 │
└──────────────────────┴───────────────┘

Projection:
  Days to Exhaustion   138 days
  Budget in 30d        70.25%
  Budget in 60d        68.17%
  Confidence           85%

⚠ Severity: WARN
Error budget declining at 0.52% per week with high confidence (R²=0.85).

Recommendation: Investigate recent changes. Common causes: increased traffic,
dependency degradation, or configuration drift. Run `nthlayer verify` to check
metric coverage.
```

### JSON Output for CI/CD

```bash
nthlayer drift services/api.yaml \
  --prometheus-url http://prometheus:9090 \
  --format json
```

### Custom Analysis Window

```bash
# Analyze last 14 days instead of tier default
nthlayer drift services/api.yaml \
  --prometheus-url http://prometheus:9090 \
  --window 14d
```

### Analyze Specific SLO

```bash
nthlayer drift services/api.yaml \
  --prometheus-url http://prometheus:9090 \
  --slo latency_p99
```

## Drift Patterns

The analyzer classifies drift into six patterns:

| Pattern | Description | Typical Cause |
|---------|-------------|---------------|
| **Stable** | No significant trend | Healthy service |
| **Gradual Decline** | Slow, steady budget erosion | Creeping technical debt |
| **Gradual Improvement** | Slow, steady recovery | Recent fixes taking effect |
| **Step Change Down** | Sudden budget drop | Incident, bad deploy |
| **Step Change Up** | Sudden improvement | Fix deployed, incident resolved |
| **Volatile** | High variance, no clear trend | Intermittent issues |

## Tier-Based Defaults

Default analysis windows and thresholds vary by service tier:

| Tier | Default Window | Warn Threshold | Critical Threshold |
|------|----------------|----------------|-------------------|
| Critical | 30d | -0.2%/week | -0.5%/week |
| Standard | 30d | -0.5%/week | -1.0%/week |
| Low | 14d | Disabled by default | Disabled by default |

## Integration with check-deploy

Combine drift analysis with deployment gates:

```bash
nthlayer check-deploy services/api.yaml \
  --prometheus-url http://prometheus:9090 \
  --include-drift
```

This adds drift analysis to the deployment gate check, blocking deploys if critical drift is detected.

## Integration with portfolio

View drift across all services:

```bash
nthlayer portfolio --drift --prometheus-url http://prometheus:9090
```

Output includes a drift analysis table showing trends, patterns, and exhaustion projections for each service.

## CI/CD Integration

### GitHub Actions

```yaml
jobs:
  check-reliability:
    steps:
      - name: Check for Drift
        run: |
          nthlayer drift services/api.yaml \
            --prometheus-url ${{ secrets.PROMETHEUS_URL }} \
            --format json > drift-report.json

          # Fail on critical drift
          if [ $? -eq 2 ]; then
            echo "::error::Critical drift detected - investigate before deploying"
            exit 1
          fi
```

### Weekly Drift Reports

```yaml
# .github/workflows/drift-report.yml
name: Weekly Drift Report

on:
  schedule:
    - cron: '0 9 * * 1'  # Monday 9am

jobs:
  report:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Generate Drift Report
        run: |
          nthlayer portfolio --drift \
            --prometheus-url ${{ secrets.PROMETHEUS_URL }} \
            --format markdown > drift-report.md

      - name: Post to Slack
        uses: slackapi/slack-github-action@v1
        with:
          payload-file-path: drift-report.md
```

## Environment Variables

| Variable | Description |
|----------|-------------|
| `NTHLAYER_PROMETHEUS_URL` | Prometheus server URL |
| `NTHLAYER_METRICS_USER` | Basic auth username |
| `NTHLAYER_METRICS_PASSWORD` | Basic auth password |

## Algorithm Details

### Trend Calculation

Drift uses linear regression (least squares) on time-series data:

1. Query Prometheus for `slo:error_budget_remaining:ratio` over the analysis window
2. Calculate slope (budget change per week) and R² (fit quality)
3. Project days until budget exhaustion based on current trend

### Severity Classification

Priority order for severity assignment:

1. Projected exhaustion within critical window → **CRITICAL**
2. Step change down detected → **CRITICAL**
3. Slope exceeds critical threshold → **CRITICAL**
4. Projected exhaustion within warn window → **WARN**
5. Slope exceeds warn threshold → **WARN**
6. Any negative slope → **INFO**
7. Otherwise → **NONE**

## See Also

- [Deployment Gates](./check-deploy.md) - Error budget gates
- [SLO Portfolio](./portfolio.md) - Organization-wide view
- [SLOs & Error Budgets](../concepts/slos.md) - Understanding SLOs
