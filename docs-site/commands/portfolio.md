# nthlayer portfolio

View SLO health across your entire organization.

## Usage

```bash
nthlayer portfolio [options]
```

## Options

| Option | Description |
|--------|-------------|
| `--format FORMAT` | Output format: `text` (default), `json`, `csv` |
| `--services-dir DIR` | Directory to scan for services |

## Example Output

```bash
nthlayer portfolio
```

```
================================================================================
  NthLayer SLO Portfolio
================================================================================

Organization Health: 78% (14/18 services meeting SLOs)

By Tier:
  Tier 1 (Critical):     83%  ████████░░░░░░░░░░░░  5/6 services
  Tier 2 (Standard):     75%  ███████░░░░░░░░░░░░░  6/8 services
  Tier 3 (Low):          75%  ███████░░░░░░░░░░░░░  3/4 services

--------------------------------------------------------------------------------
Services Needing Attention:
--------------------------------------------------------------------------------

  payment-api (Tier 1)
    availability: 156% budget burned - EXHAUSTED
    Remaining: -12.5 hours

  search-api (Tier 2)
    latency-p99: 95% budget burned - WARNING
    Remaining: 1.2 hours

--------------------------------------------------------------------------------
Insights:
--------------------------------------------------------------------------------
  - 2 services have no SLOs defined: legacy-api, internal-tools
  - payment-api has aggressive targets (99.99%) - consider 99.95%

--------------------------------------------------------------------------------
Total: 18 services, 16 with SLOs, 45 SLOs
```

## JSON Export

For integration with other tools:

```bash
nthlayer portfolio --format json
```

```json
{
  "timestamp": "2024-12-06T10:30:00Z",
  "total_services": 18,
  "services_with_slos": 16,
  "total_slos": 45,
  "healthy_services": 14,
  "org_health_percent": 77.78,
  "by_tier": [
    {
      "tier": 1,
      "tier_name": "Critical",
      "total_services": 6,
      "healthy_services": 5,
      "health_percent": 83.33
    }
  ],
  "services": [
    {
      "name": "payment-api",
      "tier": 1,
      "overall_status": "exhausted",
      "slos": [
        {
          "name": "availability",
          "status": "exhausted",
          "budget_consumed_percent": 156.0
        }
      ]
    }
  ]
}
```

## CSV Export

For spreadsheet analysis:

```bash
nthlayer portfolio --format csv
```

```csv
service,tier,slo,status,budget_consumed,budget_remaining_hours
payment-api,1,availability,exhausted,156.0,-12.5
payment-api,1,latency-p99,healthy,45.0,18.2
search-api,2,availability,healthy,32.0,22.1
search-api,2,latency-p99,warning,95.0,1.2
```

## Health Status Levels

| Status | Budget Consumed | Description |
|--------|-----------------|-------------|
| **Healthy** | < 80% | On track |
| **Warning** | 80-100% | Approaching limit |
| **Critical** | 100-150% | Over budget |
| **Exhausted** | > 150% | Severely over budget |

## Scanning Multiple Directories

```bash
nthlayer portfolio --services-dir ./services --services-dir ./legacy
```

Default search paths:
- `./services`
- `./examples/services`

## Use Cases

### Weekly SLO Review

```bash
nthlayer portfolio --format json > slo-report-$(date +%Y%m%d).json
```

### CI/CD Gate

```bash
# Fail if any critical service is exhausted
nthlayer portfolio --format json | jq -e '.services[] | select(.tier == 1 and .overall_status == "exhausted") | empty'
```

### Stakeholder Reports

```bash
nthlayer portfolio --format csv > monthly-slo-report.csv
```

## See Also

- [SLOs & Error Budgets](../concepts/slos.md) - Understanding SLOs
- [nthlayer slo](slo.md) - Per-service SLO commands
