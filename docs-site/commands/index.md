# Commands Overview

NthLayer provides a comprehensive CLI for managing your reliability stack.

## Core Commands

| Command | Description |
|---------|-------------|
| [`nthlayer apply`](apply.md) | Generate all configs from service spec |
| [`nthlayer setup`](setup.md) | Interactive first-time setup |
| [`nthlayer portfolio`](portfolio.md) | View org-wide SLO health |
| [`nthlayer slo`](slo.md) | Query and manage SLOs |
| [`nthlayer config`](config.md) | Manage configuration |

## Quick Reference

```bash
# Generate configs
nthlayer apply service.yaml

# Interactive setup
nthlayer setup

# View portfolio
nthlayer portfolio

# Check SLO status
nthlayer slo show service.yaml
nthlayer slo collect service.yaml

# Manage config
nthlayer config show
nthlayer config init
```

## Getting Help

```bash
nthlayer --help
nthlayer <command> --help
```
