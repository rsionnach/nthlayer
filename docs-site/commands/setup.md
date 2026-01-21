# nthlayer setup

Interactive first-time setup wizard for NthLayer.

## Usage

```bash
nthlayer setup [options]
```

## Options

| Option | Description |
|--------|-------------|
| `--quick` | Use simplified setup (default) |
| `--advanced` | Use full configuration wizard |
| `--test` | Test connections only |
| `--skip-service` | Skip first service creation prompt |

## Quick Setup Mode

The default mode configures the essentials:

```bash
nthlayer setup
```

```
================================================================================
  Welcome to NthLayer!
  The missing layer of reliability - 20 hours of SRE work in 5 minutes
================================================================================

Quick Setup
----------------------------------------
1. Prometheus Configuration
   Prometheus URL [http://localhost:9090]:
   Does Prometheus require authentication? [y/N]:

2. Grafana Configuration (optional)
   Configure Grafana? [Y/n]: y
   Grafana URL [http://localhost:3000]:
   API Key (press Enter to skip): ****

Testing Connections
----------------------------------------
  Prometheus (http://localhost:9090)
    [OK] Connected (Prometheus 2.45.0)

  Grafana (http://localhost:3000)
    [OK] Connected - Org: Main Org

Configuration saved to: ~/.nthlayer/config.yaml

Create your first service? [Y/n]:
```

## Advanced Setup Mode

For power users with multiple environments:

```bash
nthlayer setup --advanced
```

This includes:

- Multiple Prometheus/Grafana profiles (dev, staging, prod)
- Cloud secret backends (Vault, AWS Secrets Manager, etc.)
- Slack notification configuration

## Test Connections Only

Verify your configuration:

```bash
nthlayer setup --test
```

```
Testing Connections
----------------------------------------
  Prometheus (http://localhost:9090)
    [OK] Connected (Prometheus 2.45.0)

  Grafana (http://localhost:3000)
    [OK] Connected - Org: Main Org

All configured services are operational!
```

## Configuration File

Setup creates `~/.nthlayer/config.yaml`:

```yaml
prometheus:
  default: default
  profiles:
    default:
      url: http://localhost:9090
      type: prometheus

grafana:
  default: default
  profiles:
    default:
      url: http://localhost:3000
      type: grafana
      api_key_secret: grafana/api_key

alerting:
  slack:
    enabled: false
```

## Environment Variables

Alternatively, configure via environment variables:

```bash
export NTHLAYER_PROMETHEUS_URL=http://prometheus:9090
export NTHLAYER_GRAFANA_URL=http://grafana:3000
export NTHLAYER_GRAFANA_API_KEY=glsa_xxxxx
```

## See Also

- [nthlayer config](config.md) - Manual configuration
- [Quick Start](../getting-started/quick-start.md) - Full setup guide
