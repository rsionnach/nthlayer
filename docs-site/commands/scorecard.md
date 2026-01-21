# nthlayer scorecard

Calculate per-service reliability scores with weighted components and team aggregation.

## Synopsis

```bash
nthlayer scorecard [options]
```

## Description

The `scorecard` command provides quantitative reliability metrics across your organization. Each service receives a score from 0-100 based on weighted components:

| Component | Weight | Description |
|-----------|--------|-------------|
| **SLO Compliance** | 40% | Percentage of SLOs meeting targets |
| **Incident Score** | 30% | Inverse score based on incident count |
| **Deploy Success Rate** | 20% | Percentage of successful deployments |
| **Error Budget Remaining** | 10% | Percentage of budget still available |

Scores are aggregated at the team level using tier-based weighting, ensuring critical services have proportionally higher impact on team scores.

## Exit Codes

| Code | Band | Score Range |
|------|------|-------------|
| 0 | Excellent/Good | 75-100 |
| 1 | Fair | 50-74 |
| 2 | Poor/Critical | 0-49 |

## Options

| Option | Description |
|--------|-------------|
| `--format FORMAT` | Output format: `table` (default), `json`, `csv` |
| `--path PATH` | Additional paths to search for service files |
| `--prometheus-url URL` | Prometheus URL for live data (or set `NTHLAYER_PROMETHEUS_URL`) |
| `--by-team` | Group and display scores by team |
| `--top N` | Number of top/bottom services to highlight (default: 5) |

## Examples

### Basic Scorecard

```bash
nthlayer scorecard --prometheus-url http://prometheus:9090
```

Output:
```
╭──────────────────────────────────────────────────────────────────────────────╮
│ Reliability Scorecard                                                        │
╰──────────────────────────────────────────────────────────────────────────────╯

╭───────────────────────────── Organization Score ─────────────────────────────╮
│ ✓ 82  GOOD                                                                   │
╰──────────────────────────────────────────────────────────────────────────────╯

                            Service Scores
┏━━━━━━━━━━━━━━━┳━━━━━━┳━━━━━━━━━━━━━━━┳━━━━━━━┳━━━━━━┳━━━━━┳━━━━━━━━┓
┃ Service       ┃ Tier ┃ Team          ┃ Score ┃ Band ┃ SLO ┃ Budget ┃
┡━━━━━━━━━━━━━━━╇━━━━━━╇━━━━━━━━━━━━━━━╇━━━━━━━╇━━━━━━╇━━━━━╇━━━━━━━━┩
│ payment-api   │  1   │ payments-team │    95 │ ✓    │ 2/2 │    92% │
│ user-service  │  1   │ platform-team │    88 │ ✓    │ 2/2 │    85% │
│ order-service │  1   │ commerce-team │    76 │ ✓    │ 2/2 │    68% │
│ search-api    │  2   │ search-team   │    62 │ !    │ 1/2 │    45% │
│ analytics-api │  3   │ data-eng      │    58 │ !    │ 1/2 │    32% │
└───────────────┴──────┴───────────────┴───────┴──────┴─────┴────────┘

────────────────────────────────────────────────────────────────────────────────
Total: 5 services, 5 teams
```

### Team View

```bash
nthlayer scorecard --by-team
```

Output:
```
╭──────────────────────────────────────────────────────────────────────────────╮
│ Reliability Scorecard - By Team                                              │
╰──────────────────────────────────────────────────────────────────────────────╯

╭───────────────────────────── Organization Score ─────────────────────────────╮
│ ✓ 82  GOOD                                                                   │
╰──────────────────────────────────────────────────────────────────────────────╯

                             Team Scores
┏━━━━━━━━━━━━━━━┳━━━━━━━┳━━━━━━┳━━━━━━━━━━┳━━━━━━━━┳━━━━━━━━┳━━━━━━━━┓
┃ Team          ┃ Score ┃ Band ┃ Services ┃ Tier 1 ┃ Tier 2 ┃ Tier 3 ┃
┡━━━━━━━━━━━━━━━╇━━━━━━━╇━━━━━━╇━━━━━━━━━━╇━━━━━━━━╇━━━━━━━━╇━━━━━━━━┩
│ payments-team │    95 │ ✓    │        1 │     95 │      - │      - │
│ platform-team │    88 │ ✓    │        2 │     88 │     82 │      - │
│ commerce-team │    76 │ ✓    │        1 │     76 │      - │      - │
│ search-team   │    62 │ !    │        1 │      - │     62 │      - │
│ data-eng      │    58 │ !    │        1 │      - │      - │     58 │
└───────────────┴───────┴──────┴──────────┴────────┴────────┴────────┘
```

### JSON Export

```bash
nthlayer scorecard --format json
```

```json
{
  "timestamp": "2026-01-18T21:10:26.045633+00:00",
  "period": "30d",
  "summary": {
    "org_score": 82.0,
    "org_band": "good",
    "total_services": 5,
    "total_teams": 5
  },
  "services": [
    {
      "service": "payment-api",
      "tier": 1,
      "team": "payments-team",
      "score": 95.0,
      "band": "excellent",
      "components": {
        "slo_compliance": 100.0,
        "incident_score": 100,
        "deploy_success_rate": 100,
        "error_budget_remaining": 92
      }
    }
  ],
  "teams": [...],
  "rankings": {
    "top_services": [...],
    "bottom_services": [...]
  }
}
```

### CSV Export

```bash
nthlayer scorecard --format csv > reliability-report.csv
```

```csv
service,tier,team,type,score,band,slo_compliance,incident_score,deploy_success_rate,error_budget_remaining
payment-api,1,payments-team,api,95.0,excellent,100.0,100,100,92
user-service,1,platform-team,api,88.0,good,100.0,90,100,85
```

## Score Bands

| Band | Score Range | Icon | Description |
|------|-------------|------|-------------|
| **Excellent** | 90-100 | ✓ (bold) | Exceptional reliability |
| **Good** | 75-89 | ✓ | Meeting expectations |
| **Fair** | 50-74 | ! | Needs attention |
| **Poor** | 25-49 | !! | Significant issues |
| **Critical** | 0-24 | ✗ | Immediate action required |

## Tier Weighting

Team and organization scores use tier-based weighting to ensure critical services have proportionally higher impact:

| Tier | Weight | Description |
|------|--------|-------------|
| Tier 1 (Critical) | 3x | Revenue-critical, customer-facing |
| Tier 2 (Standard) | 2x | Important internal services |
| Tier 3 (Low) | 1x | Non-critical, batch jobs |

**Example calculation:**
```
Team with:
  - Tier 1 service scoring 90
  - Tier 2 service scoring 70

Team Score = (90 × 3 + 70 × 2) / (3 + 2)
           = (270 + 140) / 5
           = 82
```

## CI/CD Integration

### Deployment Gate

```bash
#!/bin/bash
nthlayer scorecard --format json > scorecard.json
exit_code=$?

if [ $exit_code -eq 2 ]; then
  echo "Reliability score is POOR/CRITICAL - deploy blocked"
  exit 1
fi
```

### GitHub Actions

```yaml
jobs:
  reliability-check:
    steps:
      - name: Check Reliability Score
        run: |
          nthlayer scorecard \
            --prometheus-url ${{ secrets.PROMETHEUS_URL }} \
            --format json > scorecard.json

          # Extract org score
          score=$(jq '.summary.org_score' scorecard.json)
          echo "Organization reliability score: $score"

          # Fail if below threshold
          if (( $(echo "$score < 50" | bc -l) )); then
            echo "::error::Reliability score below threshold"
            exit 1
          fi
```

### Weekly Reports

```yaml
name: Weekly Reliability Report

on:
  schedule:
    - cron: '0 9 * * 1'  # Monday 9am

jobs:
  report:
    runs-on: ubuntu-latest
    steps:
      - name: Generate Scorecard
        run: |
          nthlayer scorecard \
            --prometheus-url ${{ secrets.PROMETHEUS_URL }} \
            --format csv > reliability-$(date +%Y%m%d).csv
```

## Environment Variables

| Variable | Description |
|----------|-------------|
| `NTHLAYER_PROMETHEUS_URL` | Default Prometheus URL |

## See Also

- [nthlayer portfolio](portfolio.md) - SLO portfolio health
- [nthlayer drift](drift.md) - Reliability trend analysis
- [Service Tiers](../concepts/tiers.md) - Understanding tier classification
- [SLOs & Error Budgets](../concepts/slos.md) - SLO fundamentals
