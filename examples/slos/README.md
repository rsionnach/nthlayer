# OpenSLO Examples

This directory contains example SLO definitions using the [OpenSLO specification](https://github.com/OpenSLO/OpenSLO).

## SLO Files

- `payment-api-availability.yaml` - Tier 1 service, 99.95% availability target
- `payment-api-latency.yaml` - Tier 1 service, P95 latency < 500ms
- `search-api-availability.yaml` - Tier 2 service, 99.9% availability target

## Usage

```bash
# Load SLO definition
nthlayer reslayer init payment-api examples/slos/payment-api-availability.yaml

# Check error budget status
nthlayer reslayer status payment-api

# View error budget history
nthlayer reslayer history payment-api --days 7
```

## SLO Structure

Each SLO file defines:

- **Service**: Which service this SLO applies to
- **Target**: Reliability goal (e.g., 99.95% uptime)
- **Time Window**: Evaluation period (e.g., rolling 30 days)
- **Query**: Prometheus query to measure the SLI (Service Level Indicator)
- **Metadata**: Owner, team, tier, labels

## Error Budget Calculation

Error budget is the inverse of the SLO target:

- **SLO Target**: 99.95% availability
- **Error Budget**: 0.05% downtime allowed
- **Over 30 days**: 0.05% × 30 days × 24 hours × 60 minutes = **21.6 minutes**

If you have 3 incidents totaling 15 minutes of downtime, you've burned:
- 15 / 21.6 = 69.4% of your error budget
- Status: ⚠️ WARNING

## Tier-Based SLO Targets

**Tier 1** (Critical services):
- Availability: 99.95% (21.6 min/30d)
- Latency: P95 < 500ms

**Tier 2** (Important services):
- Availability: 99.9% (43.2 min/30d)
- Latency: P95 < 1000ms

**Tier 3** (Standard services):
- Availability: 99.5% (3.6 hours/30d)
- Latency: P95 < 2000ms
