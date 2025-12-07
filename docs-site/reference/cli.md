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
| `--output-dir DIR` | Custom output directory |
| `--dry-run` | Preview without writing |

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
| `NTHLAYER_PROMETHEUS_URL` | Prometheus server URL |
| `NTHLAYER_GRAFANA_URL` | Grafana server URL |
| `NTHLAYER_GRAFANA_API_KEY` | Grafana API key |
| `NTHLAYER_GRAFANA_ORG_ID` | Grafana organization ID |
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
