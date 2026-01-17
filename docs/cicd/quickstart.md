# CI/CD Quickstart

Get NthLayer running in your CI/CD pipeline in 5 minutes.

## GitHub Actions (Recommended)

Add this workflow to `.github/workflows/nthlayer.yml`:

```yaml
name: NthLayer Reliability Check

on:
  pull_request:
    branches: [main]

jobs:
  reliability-check:
    runs-on: ubuntu-latest
    permissions:
      contents: read
      pull-requests: write
      security-events: write

    steps:
      - uses: actions/checkout@v4

      - uses: rsionnach/nthlayer@v1
        with:
          command: plan
          service: service.yaml
```

That's it! NthLayer will now:

- Validate your service configuration on every PR
- Post a comment with the results
- Upload findings to GitHub Security tab

## Docker

Run NthLayer in any CI system using Docker:

```bash
docker run -v $(pwd):/workspace ghcr.io/rsionnach/nthlayer plan service.yaml
```

### GitLab CI

```yaml
nthlayer:
  image: ghcr.io/rsionnach/nthlayer:latest
  script:
    - nthlayer plan service.yaml --format junit --output report.xml
  artifacts:
    reports:
      junit: report.xml
```

### CircleCI

```yaml
jobs:
  nthlayer:
    docker:
      - image: ghcr.io/rsionnach/nthlayer:latest
    steps:
      - checkout
      - run:
          name: Run NthLayer Check
          command: nthlayer plan service.yaml --format junit --output report.xml
      - store_test_results:
          path: report.xml
```

## Output Formats

NthLayer supports multiple output formats for CI/CD integration:

| Format | Flag | Use Case |
|--------|------|----------|
| Table | `--format table` | Human-readable console output (default) |
| JSON | `--format json` | Machine-readable structured output |
| SARIF | `--format sarif` | GitHub Code Scanning integration |
| JUnit | `--format junit` | CI test result integration |
| Markdown | `--format markdown` | PR comments |

## Next Steps

- [Full GitHub Actions Reference](github-actions.md)
- [GitLab CI Integration](gitlab.md)
- [Required Checks Setup](required-checks.md)
