# NthLayer Architecture Diagrams

Visual diagrams using Mermaid (renders automatically on GitHub).

---

## High-Level Architecture

```mermaid
architecture-beta
   group sources(mdi:folder-multiple) [Service Catalogs]
   group engine(mdi:cog) [NthLayer Engine]
   group targets(mdi:bullseye-arrow) [Operational Tools]

   service backstage(logos:backstage-icon) [Backstage] in sources
   service cortex(mdi:hexagon-outline) [Cortex] in sources
   service port(mdi:gate) [Port] in sources
   service ymlfile(mdi:file-code) [NthLayer Config] in sources

   service api(logos:fastapi) [FastAPI API] in engine
   service wf(mdi:workflow) [LangGraph Workflows] in engine
   service db(logos:postgresql) [PostgreSQL] in engine
   service cache(logos:redis) [Redis Cache] in engine

   service pd(logos:pagerduty) [PagerDuty] in targets
   service dd(logos:datadog) [Datadog] in targets
   service gf(logos:grafana) [Grafana] in targets
   service sl(logos:slack-icon) [Slack] in targets

   backstage:R --> L:api
   cortex:R --> L:api
   port:R --> L:api
   ymlfile:R --> L:api

   api:R --> L:wf
   wf:B --> T:db
   wf:B --> T:cache

   wf:R --> L:pd
   wf:R --> L:dd
   wf:R --> L:gf
   wf:R --> L:sl
```

---

## Team Reconciliation Workflow

```mermaid
sequenceDiagram
    participant User
    participant API as NthLayer API
    participant Queue as SQS Queue
    participant Worker as LangGraph Worker
    participant Cortex
    participant PagerDuty
    participant DB as PostgreSQL
    participant Slack

    User->>API: POST /v1/teams/reconcile
    API->>DB: Check idempotency key
    API->>Queue: Enqueue job
    API-->>User: 202 Accepted (job_id)

    Queue->>Worker: Trigger workflow

    Worker->>Cortex: GET team metadata
    Cortex-->>Worker: team data

    Worker->>PagerDuty: GET current config
    PagerDuty-->>Worker: current state

    Worker->>Worker: Compute diff

    alt Changes detected
        Worker->>PagerDuty: POST update (idempotent)
        PagerDuty-->>Worker: success

        Worker->>DB: Store audit trail
        Worker->>Slack: Send notification
    else No changes
        Worker->>DB: Store "no changes"
    end

    Worker->>DB: Update job status
```

---

## Service Operationalization Flow

```mermaid
architecture-beta
   group inputgrp(mdi:file-document) [Input]
   group analysis(mdi:magnify) [Analysis]
   group generation(mdi:cog) [Generation]
   group applygrp(mdi:check-circle) [Apply]

   service svc(mdi:file-code) [Service Definition] in inputgrp

   service tier(mdi:layers-triple) [Determine Tier] in analysis
   service deps(mdi:connection) [Check Dependencies] in analysis
   service team(mdi:account-group) [Find Team] in analysis

   service alertgen(mdi:bell-alert) [Generate Alerts] in generation
   service escgen(mdi:arrow-up-bold) [Generate Escalations] in generation
   service dashgenr(mdi:view-dashboard) [Generate Dashboards] in generation
   service rbook(mdi:book-open) [Generate Runbooks] in generation

   service dda(logos:datadog) [Datadog Monitors] in applygrp
   service pda(logos:pagerduty) [PagerDuty Policies] in applygrp
   service gfa(logos:grafana) [Grafana Dashboards] in applygrp
   service docgen(logos:git-icon) [Documentation] in applygrp

   svc:R --> L:tier
   svc:R --> L:deps
   svc:R --> L:team

   tier:R --> L:alertgen
   team:R --> L:escgen
   deps:R --> L:dashgenr
   tier:R --> L:rbook

   alertgen:R --> L:dda
   escgen:R --> L:pda
   dashgenr:R --> L:gfa
   rbook:R --> L:docgen
```

---

## Development Environment

```mermaid
architecture-beta
   group local(mdi:laptop) [Local Development]
   group docker(logos:docker-icon) [Docker Containers]
   group mockgrp(mdi:drama-masks) [Mock Server]
   group nthlayergrp(mdi:rocket-launch) [NthLayer]

   service dev(mdi:account) [Developer] in local
   service venv(logos:python) [Python venv] in local

   service pg(logos:postgresql) [PostgreSQL 5432] in docker
   service rd(logos:redis) [Redis 6379] in docker

   service mockapi(mdi:server) [Mock API 8001] in mockgrp
   service statemem(mdi:memory) [InMemory State] in mockgrp

   service apit(logos:fastapi) [API Server 8000] in nthlayergrp
   service democli(mdi:console) [Demo CLI] in nthlayergrp
   service testsuite(mdi:test-tube) [Test Suite] in nthlayergrp

   dev:R --> L:venv
   venv:R --> L:apit
   venv:R --> L:democli
   venv:R --> L:testsuite

   apit:B --> T:pg
   apit:B --> T:rd
   apit:R --> L:mockapi

   testsuite:R --> L:mockapi
   mockapi:B --> T:statemem
```

---

## Testing Modes

```mermaid
graph LR
    subgraph Mode1["1️⃣ Unit Tests"]
        UT[pytest]
        RESPX[respx mocks]
        UT -->|uses| RESPX
    end

    subgraph Mode2["2️⃣ Mock Server"]
        MS[Mock Server]
        INT[Integration Tests]
        INT -->|calls| MS
    end

    subgraph Mode3["3️⃣ Demo Mode"]
        DEMO_C[Demo CLI]
        VIS[Visual Output]
        DEMO_C -->|shows| VIS
    end

    subgraph Mode4["4️⃣ Real Services"]
        REAL[Real APIs]
        VALID[Validation Tests]
        VALID -->|calls| REAL
    end

    Mode1 -.->|5 seconds| Mode2
    Mode2 -.->|30 seconds| Mode3
    Mode3 -.->|immediate| Mode4

    style Mode1 fill:#c8e6c9
    style Mode2 fill:#fff9c4
    style Mode3 fill:#e1bee7
    style Mode4 fill:#ffccbc
```

---

## Data Flow: Service Catalog to Operations

```mermaid
flowchart TD
    START([Service Definition])

    READ[Read from Catalog]
    VALIDATE[Validate Metadata]
    ENRICH[Enrich with Defaults]

    GEN_ALERTS[Generate Alert Rules]
    GEN_ESC[Generate Escalation Policy]
    GEN_DASH[Generate Dashboard]
    GEN_RBOOK[Generate Runbook]

    APPLY_DD[Apply to Datadog]
    APPLY_PD[Apply to PagerDuty]
    APPLY_GF[Apply to Grafana]
    APPLY_DOC[Commit to Git]

    AUDIT[Store Audit Trail]
    NOTIFY[Send Notifications]

    END([Operationalized Service])

    START --> READ
    READ --> VALIDATE
    VALIDATE --> ENRICH

    ENRICH --> GEN_ALERTS
    ENRICH --> GEN_ESC
    ENRICH --> GEN_DASH
    ENRICH --> GEN_RBOOK

    GEN_ALERTS --> APPLY_DD
    GEN_ESC --> APPLY_PD
    GEN_DASH --> APPLY_GF
    GEN_RBOOK --> APPLY_DOC

    APPLY_DD --> AUDIT
    APPLY_PD --> AUDIT
    APPLY_GF --> AUDIT
    APPLY_DOC --> AUDIT

    AUDIT --> NOTIFY
    NOTIFY --> END

    style START fill:#4CAF50,color:#fff
    style END fill:#2196F3,color:#fff
    style AUDIT fill:#FF9800,color:#fff
```

---

## Component Architecture

```mermaid
architecture-beta
   group apigrp(mdi:api) [API Layer]
   group business(mdi:cog) [Business Logic]
   group clients(mdi:web) [HTTP Clients]
   group datagrp(mdi:database) [Data Layer]

   service rest(mdi:routes) [REST Endpoints] in apigrp
   service auth(mdi:lock) [Authentication] in apigrp
   service valid(mdi:check-decagram) [Validation] in apigrp

   service wf(mdi:workflow) [Workflows] in business
   service recon(mdi:sync) [Reconciliation Engine] in business
   service diffcalc(mdi:compare) [Diff Calculator] in business

   service baseclient(mdi:server) [Base Client] in clients
   service pdc(logos:pagerduty) [PagerDuty Client] in clients
   service ddc(logos:datadog) [Datadog Client] in clients
   service gfc(logos:grafana) [Grafana Client] in clients
   service cxc(mdi:hexagon-outline) [Cortex Client] in clients

   service repo(mdi:folder-table) [Repositories] in datagrp
   service models(mdi:file-tree) [ORM Models] in datagrp
   service cachel(mdi:cached) [Cache Layer] in datagrp

   auth:R --> L:rest
   valid:R --> L:rest
   rest:R --> L:wf

   wf:R --> L:recon
   recon:R --> L:diffcalc
   diffcalc:R --> L:baseclient

   wf:B --> T:repo
   repo:R --> L:models
   repo:R --> L:cachel
```

---

## Deployment Architecture (Production)

```mermaid
architecture-beta
   group internet(mdi:web) [Internet]
   group aws(logos:aws) [AWS Cloud]
   group apilayer(mdi:api) [API Layer] in aws
   group queue(mdi:tray-full) [Message Queue] in aws
   group workers(mdi:cogs) [Worker Layer] in aws
   group storageaws(mdi:database) [Storage Layer] in aws
   group observaws(mdi:chart-line) [Observability] in aws
   group secretsaws(mdi:key) [Secrets] in aws
   group external(mdi:connection) [External APIs]

   service useraws(mdi:account-group) [Users and CLI] in internet

   service agw(logos:aws-api-gateway) [API Gateway] in apilayer
   service lambdaapi(logos:aws-lambda) [Lambda FastAPI] in apilayer

   service sqsqueue(logos:aws-sqs) [SQS Queue] in queue
   service dlq(mdi:tray-remove) [Dead Letter Queue] in queue

   service lambdaw(logos:aws-lambda) [Lambda Worker] in workers
   service ecsfargate(logos:aws-ecs) [ECS Fargate] in workers

   service rdsdb(logos:aws-rds) [RDS PostgreSQL] in storageaws
   service elasticache(logos:aws-elasticache) [ElastiCache Redis] in storageaws

   service cwlogs(logos:aws-cloudwatch) [CloudWatch] in observaws
   service xraytrace(mdi:radar) [XRay Tracing] in observaws

   service secretsmgr(logos:aws-secrets-manager) [Secrets Manager] in secretsaws

   service pde(logos:pagerduty) [PagerDuty] in external
   service dde(logos:datadog) [Datadog] in external
   service gfe(logos:grafana) [Grafana] in external
   service sle(logos:slack-icon) [Slack] in external

   useraws:R --> L:agw
   agw:R --> L:lambdaapi
   lambdaapi:B --> T:sqsqueue
   sqsqueue:R --> L:dlq

   sqsqueue:B --> T:lambdaw
   sqsqueue:B --> T:ecsfargate

   lambdaapi:B --> T:rdsdb
   lambdaw:B --> T:rdsdb
   lambdaapi:B --> T:elasticache

   lambdaw:R --> L:pde
   lambdaw:R --> L:dde
   lambdaw:R --> L:gfe
   lambdaw:R --> L:sle

   lambdaapi:B --> T:cwlogs
   lambdaw:B --> T:cwlogs

   lambdaapi:B --> T:secretsmgr
   lambdaw:B --> T:secretsmgr
```

---

## State Transitions

```mermaid
stateDiagram-v2
    [*] --> Pending: Job Created

    Pending --> InProgress: Worker Starts

    InProgress --> FetchingData: Get Current State
    FetchingData --> ComputingDiff: Analyze Changes
    ComputingDiff --> ApplyingChanges: Changes Detected
    ComputingDiff --> NoChanges: No Changes

    ApplyingChanges --> Success: Apply Succeeded
    ApplyingChanges --> Failed: Apply Failed

    NoChanges --> Success: Record Status

    Failed --> Retry: Retryable Error
    Retry --> InProgress: Retry Attempt

    Failed --> PermanentFailure: Non-Retryable Error

    Success --> [*]
    PermanentFailure --> [*]

    note right of InProgress
        Worker logs:
        - job_id
        - correlation_id
        - timestamp
    end note

    note right of ApplyingChanges
        Idempotent operations:
        - Includes idempotency key
        - Safe to retry
    end note
```

---

## How to Use These Diagrams

### In Documentation
Copy the Mermaid code blocks into any markdown file. GitHub will automatically render them.

### In Presentations
1. View on GitHub (renders automatically)
2. Take screenshots
3. Or export from [Mermaid Live Editor](https://mermaid.live)

### Customize
Edit the Mermaid code to:
- Add/remove components
- Change colors (see `style` commands)
- Adjust layout
- Add more details

### Learn More
- [Mermaid Documentation](https://mermaid.js.org/)
- [Mermaid Live Editor](https://mermaid.live) - Preview and export

---

## Next Steps

Want more diagrams? I can create:
- Detailed workflow state machines
- Error handling flows
- Database schema diagrams
- API endpoint maps
- Class diagrams
- Sequence diagrams for specific features

Just ask! 🎨
