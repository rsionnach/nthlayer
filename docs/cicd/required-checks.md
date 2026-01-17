# Required Checks Setup

Make NthLayer a required check for merging PRs.

## GitHub Branch Protection

1. Go to **Settings** → **Branches**
2. Click **Add rule** or edit existing rule for `main`
3. Enable **Require status checks to pass before merging**
4. Search for and select `NthLayer Reliability Check`
5. Click **Save changes**

Now PRs cannot be merged until NthLayer passes.

## Workflow Configuration

Ensure your workflow has a consistent name:

```yaml
name: NthLayer Reliability Check  # This name appears in branch protection

jobs:
  reliability-check:  # Job name doesn't matter
    runs-on: ubuntu-latest
    steps:
      - uses: rsionnach/nthlayer@v1
        with:
          service: service.yaml
```

## Failure Behavior

Control when the check fails with `fail-on`:

```yaml
- uses: rsionnach/nthlayer@v1
  with:
    service: service.yaml
    fail-on: error  # Only fail on errors (default)
```

| `fail-on` | Behavior |
|-----------|----------|
| `error` | Block merge on errors only |
| `warning` | Block merge on warnings or errors |
| `none` | Never block (informational only) |

## Multiple Services

For repositories with multiple services, run checks in parallel:

```yaml
jobs:
  api-check:
    runs-on: ubuntu-latest
    steps:
      - uses: rsionnach/nthlayer@v1
        with:
          service: services/api.yaml

  worker-check:
    runs-on: ubuntu-latest
    steps:
      - uses: rsionnach/nthlayer@v1
        with:
          service: services/worker.yaml
```

Each job appears as a separate required check.

## Matrix Strategy

For many services, use a matrix:

```yaml
jobs:
  nthlayer:
    runs-on: ubuntu-latest
    strategy:
      matrix:
        service:
          - services/api.yaml
          - services/worker.yaml
          - services/scheduler.yaml
    steps:
      - uses: rsionnach/nthlayer@v1
        with:
          service: ${{ matrix.service }}
```

## Allow Warnings

To allow warnings but block errors:

```yaml
- uses: rsionnach/nthlayer@v1
  with:
    service: service.yaml
    fail-on: error  # Warnings don't block
```

Warnings still appear in the PR comment and GitHub Security tab.

## Override for Emergencies

For emergency deployments, repository admins can bypass required checks:

1. Enable **Allow specified actors to bypass required pull requests** in branch protection
2. Add admin users or teams
3. Admins can merge without passing checks

Use sparingly and document the override.

## GitLab Protected Branches

In GitLab:

1. Go to **Settings** → **Repository** → **Protected branches**
2. Set **Allowed to merge** to **Maintainers**
3. Enable **Pipeline must succeed** for `main`

Your `.gitlab-ci.yml` jobs become required checks automatically.
