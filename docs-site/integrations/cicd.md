# CI/CD Integration

Integrate NthLayer into your deployment pipeline for automated reliability validation.

## The Reliability Pipeline

```
┌──────────┐    ┌──────────┐    ┌──────────┐    ┌──────────┐
│ Generate │ → │ Validate │ → │  Protect │ → │  Deploy  │
└──────────┘    └──────────┘    └──────────┘    └──────────┘
  apply          validate-spec   check-deploy    kubectl
                 verify                          argocd
                 --lint
```

## Recommended: GitOps Mode

NthLayer supports two deployment patterns:

| Mode | Description | When to Use |
|------|-------------|-------------|
| **GitOps** (Recommended) | Generate artifacts to repo, deploy via CD | Production workflows |
| **Push** | Direct push to Grafana/Prometheus APIs | Bootstrap, demos |

### Why GitOps is Recommended

1. **Audit trail** - All changes are PR-reviewed and committed
2. **Rollback** - `git revert` undoes any change
3. **Separation of concerns** - NthLayer generates, CD deploys
4. **No API credentials in NthLayer** - CD handles deployment auth

### GitOps Workflow

```yaml
# CI: Generate and validate
- name: Generate configs
  run: nthlayer apply services/*.yaml --output-dir generated/

- name: Commit generated configs
  run: |
    git add generated/
    git commit -m "chore: regenerate reliability configs"
    git push

# CD (ArgoCD/Flux): Deploy from generated/ directory
```

### Push Mode (Bootstrap Only)

Push mode is useful for initial setup or demos:

```bash
# Push dashboards directly to Grafana
nthlayer apply services/*.yaml --push

# Push alert rules to Prometheus ruler API
nthlayer apply services/*.yaml --push-ruler
```

!!! warning "Not recommended for production"
    Push mode bypasses code review and has no audit trail.
    Use GitOps for production deployments.

---

## GitHub Actions

### Complete Workflow

```yaml
name: Deploy with Reliability Gates

on:
  push:
    branches: [main]
    paths:
      - 'services/**'

jobs:
  validate:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Install NthLayer
        run: pip install nthlayer

      - name: Validate Service Specs
        run: nthlayer validate-spec services/

      - name: Generate Configs
        run: nthlayer apply services/*.yaml --lint

      - name: Upload Artifacts
        uses: actions/upload-artifact@v4
        with:
          name: generated-configs
          path: generated/

  verify:
    needs: validate
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Install NthLayer
        run: pip install nthlayer

      - name: Verify Metrics Exist
        run: |
          nthlayer verify services/*.yaml \
            --prometheus-url ${{ secrets.STAGING_PROMETHEUS_URL }}
        env:
          PROMETHEUS_USERNAME: ${{ secrets.PROMETHEUS_USERNAME }}
          PROMETHEUS_PASSWORD: ${{ secrets.PROMETHEUS_PASSWORD }}

  gate:
    needs: verify
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Install NthLayer
        run: pip install nthlayer

      - name: Check Deployment Gate
        id: gate
        run: |
          nthlayer check-deploy services/*.yaml \
            --prometheus-url ${{ secrets.PROD_PROMETHEUS_URL }}
          echo "exit_code=$?" >> $GITHUB_OUTPUT
        continue-on-error: true

      - name: Block on Budget Exhausted
        if: steps.gate.outputs.exit_code == '2'
        run: |
          echo "::error::Deployment blocked - error budget exhausted"
          exit 1

  deploy:
    needs: gate
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Download Configs
        uses: actions/download-artifact@v4
        with:
          name: generated-configs
          path: generated/

      - name: Deploy to Kubernetes
        run: kubectl apply -f generated/
```

### Reusable Action (Coming Soon)

```yaml
- uses: nthlayer/action@v1
  with:
    command: check-deploy
    service-file: services/api.yaml
    prometheus-url: ${{ secrets.PROMETHEUS_URL }}
```

## GitLab CI

```yaml
stages:
  - validate
  - verify
  - gate
  - deploy

variables:
  PIP_CACHE_DIR: "$CI_PROJECT_DIR/.pip-cache"

.nthlayer:
  image: python:3.11
  before_script:
    - pip install nthlayer

validate:
  extends: .nthlayer
  stage: validate
  script:
    - nthlayer validate-spec services/
    - nthlayer apply services/*.yaml --lint
  artifacts:
    paths:
      - generated/

verify:
  extends: .nthlayer
  stage: verify
  script:
    - nthlayer verify services/*.yaml --prometheus-url $STAGING_PROMETHEUS_URL

gate:
  extends: .nthlayer
  stage: gate
  script:
    - |
      nthlayer check-deploy services/*.yaml \
        --prometheus-url $PROD_PROMETHEUS_URL
      EXIT_CODE=$?
      if [ $EXIT_CODE -eq 2 ]; then
        echo "Deployment blocked - error budget exhausted"
        exit 1
      fi
  only:
    - main

deploy:
  stage: deploy
  script:
    - kubectl apply -f generated/
  only:
    - main
  when: on_success
```

## ArgoCD

### PreSync Hook

Block ArgoCD sync when error budget is exhausted:

```yaml
apiVersion: batch/v1
kind: Job
metadata:
  name: nthlayer-gate
  annotations:
    argocd.argoproj.io/hook: PreSync
    argocd.argoproj.io/hook-delete-policy: HookSucceeded
spec:
  template:
    spec:
      containers:
        - name: check-deploy
          image: ghcr.io/nthlayer/nthlayer:latest
          command:
            - nthlayer
            - check-deploy
            - /config/service.yaml
            - --prometheus-url
            - $(PROMETHEUS_URL)
          envFrom:
            - secretRef:
                name: prometheus-credentials
          volumeMounts:
            - name: service-config
              mountPath: /config
      volumes:
        - name: service-config
          configMap:
            name: service-yaml
      restartPolicy: Never
  backoffLimit: 0
```

### Application Manifest

```yaml
apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
  name: payment-api
spec:
  source:
    repoURL: https://github.com/org/repo
    path: services/payment-api
  syncPolicy:
    automated:
      prune: true
      selfHeal: true
    syncOptions:
      - CreateNamespace=true
```

When the PreSync hook fails (exit code 2), ArgoCD blocks the sync.

## Tekton

### Task Definition

```yaml
apiVersion: tekton.dev/v1
kind: Task
metadata:
  name: nthlayer-check-deploy
spec:
  params:
    - name: service-file
      type: string
    - name: prometheus-url
      type: string
  steps:
    - name: check
      image: ghcr.io/nthlayer/nthlayer:latest
      script: |
        nthlayer check-deploy $(params.service-file) \
          --prometheus-url $(params.prometheus-url)

        EXIT_CODE=$?
        if [ $EXIT_CODE -eq 2 ]; then
          echo "Deployment blocked"
          exit 1
        fi
```

### Pipeline

```yaml
apiVersion: tekton.dev/v1
kind: Pipeline
metadata:
  name: deploy-with-gates
spec:
  params:
    - name: service-file
      type: string
    - name: prometheus-url
      type: string

  tasks:
    - name: validate
      taskRef:
        name: nthlayer-validate

    - name: generate
      taskRef:
        name: nthlayer-apply
      runAfter: [validate]

    - name: verify
      taskRef:
        name: nthlayer-verify
      runAfter: [generate]

    - name: gate
      taskRef:
        name: nthlayer-check-deploy
      runAfter: [verify]
      params:
        - name: service-file
          value: $(params.service-file)
        - name: prometheus-url
          value: $(params.prometheus-url)

    - name: deploy
      taskRef:
        name: kubectl-apply
      runAfter: [gate]
```

## Jenkins

```groovy
pipeline {
    agent any

    environment {
        PROMETHEUS_URL = credentials('prometheus-url')
    }

    stages {
        stage('Validate') {
            steps {
                sh 'pip install nthlayer'
                sh 'nthlayer validate-spec services/'
                sh 'nthlayer apply services/*.yaml --lint'
            }
        }

        stage('Verify') {
            steps {
                sh """
                    nthlayer verify services/*.yaml \
                        --prometheus-url ${PROMETHEUS_URL}
                """
            }
        }

        stage('Gate') {
            steps {
                script {
                    def exitCode = sh(
                        script: """
                            nthlayer check-deploy services/*.yaml \
                                --prometheus-url ${PROMETHEUS_URL}
                        """,
                        returnStatus: true
                    )
                    if (exitCode == 2) {
                        error('Deployment blocked - error budget exhausted')
                    }
                }
            }
        }

        stage('Deploy') {
            steps {
                sh 'kubectl apply -f generated/'
            }
        }
    }
}
```

## Environment Variables

All CI/CD integrations support these environment variables:

| Variable | Description |
|----------|-------------|
| `PROMETHEUS_URL` | Prometheus server URL |
| `PROMETHEUS_USERNAME` | Basic auth username |
| `PROMETHEUS_PASSWORD` | Basic auth password |
| `GRAFANA_URL` | Grafana server URL |
| `GRAFANA_API_KEY` | Grafana API key |

## Best Practices

### 1. Validate Early, Protect Late

```
commit → validate-spec → apply --lint → verify → check-deploy → deploy
           ↑                               ↑           ↑
       No Prometheus              Staging Prom   Prod Prom
```

### 2. Use Staging for Verification

Verify metrics exist in staging before checking production gates:

```yaml
- name: Verify in Staging
  run: nthlayer verify services/*.yaml --prometheus-url $STAGING_URL

- name: Gate in Production
  run: nthlayer check-deploy services/*.yaml --prometheus-url $PROD_URL
```

### 3. Cache NthLayer Installation

```yaml
- uses: actions/cache@v4
  with:
    path: ~/.cache/pip
    key: ${{ runner.os }}-pip-nthlayer
```

### 4. Fail Fast

Put validation early in your pipeline to catch issues quickly.

## See Also

- [Deployment Gates](../commands/check-deploy.md)
- [Contract Verification](../commands/verify.md)
- [Validation Overview](../validate/index.md)
