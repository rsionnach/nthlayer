# GitLab CI Integration

Run NthLayer in GitLab CI/CD pipelines using Docker.

## Basic Setup

Add to `.gitlab-ci.yml`:

```yaml
stages:
  - validate

nthlayer:
  stage: validate
  image: ghcr.io/rsionnach/nthlayer:latest
  script:
    - nthlayer plan service.yaml --format junit --output report.xml
  artifacts:
    reports:
      junit: report.xml
  rules:
    - if: $CI_PIPELINE_SOURCE == "merge_request_event"
```

## Full Pipeline

```yaml
stages:
  - validate
  - deploy

variables:
  PROMETHEUS_URL: ${PROMETHEUS_URL}

# PR Check
nthlayer-validate:
  stage: validate
  image: ghcr.io/rsionnach/nthlayer:latest
  script:
    - nthlayer plan service.yaml --format junit --output report.xml
    - nthlayer plan service.yaml --format markdown > comment.md
  artifacts:
    reports:
      junit: report.xml
    paths:
      - comment.md
  rules:
    - if: $CI_PIPELINE_SOURCE == "merge_request_event"

# Deployment Gate
nthlayer-gate:
  stage: validate
  image: ghcr.io/rsionnach/nthlayer:latest
  script:
    - nthlayer check-deploy service.yaml --prometheus-url $PROMETHEUS_URL
  rules:
    - if: $CI_COMMIT_BRANCH == "main"

# Deploy after gate passes
deploy:
  stage: deploy
  needs: [nthlayer-gate]
  script:
    - ./deploy.sh
  rules:
    - if: $CI_COMMIT_BRANCH == "main"
```

## Output Formats

### JUnit (Test Results)

```yaml
nthlayer:
  script:
    - nthlayer plan service.yaml --format junit --output report.xml
  artifacts:
    reports:
      junit: report.xml
```

JUnit results appear in the **Tests** tab of merge requests.

### JSON (Machine Readable)

```yaml
nthlayer:
  script:
    - nthlayer plan service.yaml --format json --output result.json
    - |
      STATUS=$(cat result.json | jq -r '.summary.status')
      if [ "$STATUS" = "fail" ]; then
        exit 1
      fi
```

### SARIF (Security Scanning)

GitLab supports SARIF via the Security Dashboard:

```yaml
nthlayer:
  script:
    - nthlayer plan service.yaml --format sarif --output gl-sast-report.json
  artifacts:
    reports:
      sast: gl-sast-report.json
```

## Environment Variables

Configure NthLayer via environment variables:

```yaml
variables:
  PROMETHEUS_URL: ${PROMETHEUS_URL}
  PROMETHEUS_USERNAME: ${PROMETHEUS_USERNAME}
  PROMETHEUS_PASSWORD: ${PROMETHEUS_PASSWORD}
  GRAFANA_URL: ${GRAFANA_URL}
  GRAFANA_API_KEY: ${GRAFANA_API_KEY}
```

Set these in **Settings** → **CI/CD** → **Variables**.

## Merge Request Comments

Use GitLab's MR note API to post comments:

```yaml
nthlayer-comment:
  stage: validate
  image: ghcr.io/rsionnach/nthlayer:latest
  script:
    - nthlayer plan service.yaml --format markdown > comment.md
    - |
      curl --request POST \
        --header "PRIVATE-TOKEN: ${GITLAB_TOKEN}" \
        --form "body=$(cat comment.md)" \
        "${CI_API_V4_URL}/projects/${CI_PROJECT_ID}/merge_requests/${CI_MERGE_REQUEST_IID}/notes"
  rules:
    - if: $CI_PIPELINE_SOURCE == "merge_request_event"
```

## Scheduled Audits

Run weekly drift detection:

```yaml
nthlayer-audit:
  stage: validate
  image: ghcr.io/rsionnach/nthlayer:latest
  script:
    - nthlayer drift service.yaml --prometheus-url $PROMETHEUS_URL --format markdown
  rules:
    - if: $CI_PIPELINE_SOURCE == "schedule"
```

Schedule in **CI/CD** → **Schedules**.
