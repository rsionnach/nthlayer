# CLI Reference

Complete command-line interface reference.

## Global Options

```bash
nthlayer [--help] [--version] <command>
```

| Option | Description |
|--------|-------------|
| `--help` | Show help message |
| `--version` | Show version number |

## Commands

### apply

Generate reliability configs from service spec.

```bash
nthlayer apply <service.yaml> [options]
```

| Option | Description |
|--------|-------------|
| `--push` | Push dashboard to Grafana |
| `--push-ruler` | Push alerts to Mimir/Cortex Ruler API |
| `--output-dir DIR` | Custom output directory |
| `--dry-run` | Preview without writing |
| `--lint` | Validate generated alerts with pint |

### setup

Interactive first-time setup.

```bash
nthlayer setup [options]
```

| Option | Description |
|--------|-------------|
| `--quick` | Simplified setup (default) |
| `--advanced` | Full configuration wizard |
| `--test` | Test connections only |
| `--skip-service` | Skip first service creation |

### portfolio

View org-wide SLO health.

```bash
nthlayer portfolio [options]
```

| Option | Description |
|--------|-------------|
| `--format FORMAT` | Output: text, json, csv |
| `--services-dir DIR` | Directory to scan |

### slo

SLO management commands.

```bash
nthlayer slo <subcommand> <service.yaml>
```

| Subcommand | Description |
|------------|-------------|
| `show` | Display SLO definitions |
| `list` | Brief SLO listing |
| `collect` | Query live metrics |

Options for `collect`:

| Option | Description |
|--------|-------------|
| `--prometheus-url URL` | Prometheus server |
| `--window DURATION` | Query window |

### config

Configuration management.

```bash
nthlayer config <subcommand>
```

| Subcommand | Description |
|------------|-------------|
| `show` | Show current config |
| `init` | Interactive wizard |
| `set KEY VALUE` | Set config value |

Options for `show`:

| Option | Description |
|--------|-------------|
| `--reveal-secrets` | Show secret values |

### plan

Preview what would be generated.

```bash
nthlayer plan <service.yaml>
```

### validate

Validate service spec.

```bash
nthlayer validate <service.yaml>
```

### generate-dashboard

Generate dashboard only.

```bash
nthlayer generate-dashboard <service.yaml> [options]
```

| Option | Description |
|--------|-------------|
| `--push` | Push to Grafana |

### generate-alerts

Generate alerts only.

```bash
nthlayer generate-alerts <service.yaml>
```

### generate-slo

Generate SLO definitions only.

```bash
nthlayer generate-slo <service.yaml>
```

### generate-recording-rules

Generate recording rules only.

```bash
nthlayer generate-recording-rules <service.yaml>
```

### setup-pagerduty

Configure PagerDuty for service.

```bash
nthlayer setup-pagerduty <service.yaml> [options]
```

| Option | Description |
|--------|-------------|
| `--api-key KEY` | PagerDuty API key |
| `--dry-run` | Preview changes |

### verify

Verify declared metrics exist in Prometheus (contract verification).

```bash
nthlayer verify <service.yaml> [options]
```

| Option | Description |
|--------|-------------|
| `--prometheus-url, -p URL` | Target Prometheus URL |
| `--env ENVIRONMENT` | Environment name |
| `--no-fail` | Don't fail on missing metrics |

Exit codes:
- `0` = All metrics verified
- `1` = Optional metrics missing (warning)
- `2` = Critical SLO metrics missing (block)

### check-deploy

Check deployment gate based on error budget.

```bash
nthlayer check-deploy <service.yaml> [options]
```

| Option | Description |
|--------|-------------|
| `--prometheus-url, -p URL` | Target Prometheus URL |
| `--env ENVIRONMENT` | Environment name |
| `--auto-env` | Auto-detect environment |

Exit codes:
- `0` = Approved (budget healthy)
- `1` = Warning (budget 10-20% remaining)
- `2` = Blocked (budget < 10% for critical tier)

### lint

Lint generated Prometheus rules.

```bash
nthlayer lint <alerts.yaml>
```

Uses [pint](https://cloudflare.github.io/pint/) for validation.

### init

Create new service spec from template.

```bash
nthlayer init [options]
```

| Option | Description |
|--------|-------------|
| `--name NAME` | Service name |
| `--team TEAM` | Team name |
| `--template TEMPLATE` | Template name |

### list-templates

Show available templates.

```bash
nthlayer list-templates
```

### list-services

List available services from demo data.

```bash
nthlayer list-services
```

### list-teams

List available teams from demo data.

```bash
nthlayer list-teams
```

### list-environments

List available environment configurations.

```bash
nthlayer list-environments [options]
```

| Option | Description |
|--------|-------------|
| `--service FILE` | Service YAML file to scope search |
| `--directory DIR` | Directory to search for environments |

### diff-envs

Compare configurations between two environments.

```bash
nthlayer diff-envs <service.yaml> <env1> <env2> [options]
```

| Option | Description |
|--------|-------------|
| `--show-all` | Show all fields, not just differences |

### validate-env

Validate an environment configuration.

```bash
nthlayer validate-env <environment> [options]
```

| Option | Description |
|--------|-------------|
| `--service FILE` | Service file to test against |
| `--directory DIR` | Directory containing environments |
| `--strict` | Treat warnings as errors |

### validate-spec

Validate service.yaml against OPA/Rego policies.

```bash
nthlayer validate-spec <service.yaml> [options]
```

| Option | Description |
|--------|-------------|
| `--policy-dir DIR` | Directory containing .rego policies |
| `--strict` | Treat warnings as errors |

Exit codes:
- `0` = All policies pass
- `1` = Policy violations found

### validate-metadata

Validate Prometheus rule metadata (labels, annotations, URLs).

```bash
nthlayer validate-metadata <alerts.yaml> [options]
```

| Option | Description |
|--------|-------------|
| `--check-urls` | Verify runbook URLs are reachable |
| `--strict` | Treat warnings as errors |

### generate-loki-alerts

Generate Loki LogQL alert rules from service spec.

```bash
nthlayer generate-loki-alerts <service.yaml> [options]
```

| Option | Description |
|--------|-------------|
| `--output-dir DIR` | Output directory |
| `--dry-run` | Preview without writing |

### secrets

Secret management commands.

```bash
nthlayer secrets <subcommand>
```

| Subcommand | Description |
|------------|-------------|
| `list` | List available secrets |
| `verify` | Verify required secrets |
| `set PATH` | Set a secret |
| `get PATH` | Get a secret |
| `migrate SOURCE TARGET` | Migrate secrets |

## Environment Variables

| Variable | Description |
|----------|-------------|
| `PROMETHEUS_URL` | Prometheus server URL (for verify command) |
| `PROMETHEUS_USERNAME` | Prometheus basic auth username |
| `PROMETHEUS_PASSWORD` | Prometheus basic auth password |
| `NTHLAYER_PROMETHEUS_URL` | Prometheus server URL (legacy) |
| `NTHLAYER_GRAFANA_URL` | Grafana server URL |
| `NTHLAYER_GRAFANA_API_KEY` | Grafana API key |
| `NTHLAYER_GRAFANA_ORG_ID` | Grafana organization ID |
| `MIMIR_RULER_URL` | Mimir/Cortex Ruler API URL |
| `MIMIR_TENANT_ID` | Mimir tenant ID (multi-tenant) |
| `MIMIR_API_KEY` | Mimir API key (if auth required) |
| `PAGERDUTY_API_KEY` | PagerDuty API key |
| `NTHLAYER_PROFILE` | Config profile to use |

## Exit Codes

| Code | Meaning |
|------|---------|
| `0` | Success |
| `1` | General error |
| `2` | Invalid arguments |
| `3` | Configuration error |
| `4` | Connection error |
