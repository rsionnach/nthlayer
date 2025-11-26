# NthLayer Architecture Diagrams

Visual diagrams using Mermaid (renders automatically on GitHub).

---

## High-Level Architecture

```mermaid
graph TB
    subgraph Sources["📚 Service Catalogs (Optional)"]
        BS[Backstage]
        CX[Cortex]
        PT[Port]
        YML[nthlayer.yaml]
    end
    
    subgraph Engine["⚙️ NthLayer Engine"]
        API[FastAPI API]
        WF[LangGraph Workflows]
        DB[(PostgreSQL)]
        CACHE[(Redis Cache)]
    end
    
    subgraph Targets["🎯 Operational Tools"]
        PD[PagerDuty]
        DD[Datadog]
        GF[Grafana]
        SL[Slack]
    end
    
    BS -->|reads metadata| API
    CX -->|reads metadata| API
    PT -->|reads metadata| API
    YML -->|reads metadata| API
    
    API -->|enqueues jobs| WF
    WF -->|stores state| DB
    WF -->|caches| CACHE
    
    WF -->|generates configs| PD
    WF -->|generates configs| DD
    WF -->|generates configs| GF
    WF -->|sends notifications| SL
    
    style Sources fill:#e1f5ff
    style Engine fill:#fff4e1
    style Targets fill:#e8f5e9
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
graph LR
    subgraph Input["📋 Input"]
        SVC[Service Definition]
    end
    
    subgraph Analysis["🔍 Analysis"]
        TIER[Determine Tier]
        DEPS[Check Dependencies]
        TEAM[Find Team]
    end
    
    subgraph Generation["⚙️ Generation"]
        ALERT[Generate Alerts]
        ESC[Generate Escalations]
        DASH[Generate Dashboards]
        RBOOK[Generate Runbooks]
    end
    
    subgraph Apply["✅ Apply"]
        DD_A[Datadog Monitors]
        PD_A[PagerDuty Policies]
        GF_A[Grafana Dashboards]
        DOC[Documentation]
    end
    
    SVC --> TIER
    SVC --> DEPS
    SVC --> TEAM
    
    TIER --> ALERT
    TEAM --> ESC
    DEPS --> DASH
    TIER --> RBOOK
    
    ALERT --> DD_A
    ESC --> PD_A
    DASH --> GF_A
    RBOOK --> DOC
    
    style Input fill:#e3f2fd
    style Analysis fill:#fff3e0
    style Generation fill:#f3e5f5
    style Apply fill:#e8f5e9
```

---

## Development Environment

```mermaid
graph TB
    subgraph Local["💻 Local Development"]
        DEV[Developer]
        VENV[Python venv]
    end
    
    subgraph Docker["🐳 Docker Containers"]
        PG[(PostgreSQL<br/>port 5432)]
        RD[(Redis<br/>port 6379)]
    end
    
    subgraph Mock["🎭 Mock Server"]
        MOCK[Mock API Server<br/>port 8001]
        STATE[In-Memory State]
    end
    
    subgraph NthLayer["🚀 NthLayer"]
        API_T[API Server<br/>port 8000]
        DEMO[Demo CLI]
        TESTS[Test Suite]
    end
    
    DEV -->|develops| VENV
    VENV -->|runs| API_T
    VENV -->|runs| DEMO
    VENV -->|runs| TESTS
    
    API_T -->|connects| PG
    API_T -->|connects| RD
    API_T -->|calls| MOCK
    
    TESTS -->|calls| MOCK
    MOCK -->|stores| STATE
    
    style Local fill:#e1f5ff
    style Docker fill:#e8f5e9
    style Mock fill:#fff4e1
    style NthLayer fill:#f3e5f5
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
graph TB
    subgraph API["API Layer"]
        REST[REST Endpoints]
        AUTH[Authentication]
        VALID[Validation]
    end
    
    subgraph Business["Business Logic"]
        WF[Workflows]
        RECON[Reconciliation Engine]
        DIFF[Diff Calculator]
    end
    
    subgraph Clients["HTTP Clients"]
        BASE[Base Client<br/>retry + circuit breaker]
        PD_C[PagerDuty Client]
        DD_C[Datadog Client]
        GF_C[Grafana Client]
        CX_C[Cortex Client]
        
        BASE -.->|inherits| PD_C
        BASE -.->|inherits| DD_C
        BASE -.->|inherits| GF_C
        BASE -.->|inherits| CX_C
    end
    
    subgraph Data["Data Layer"]
        REPO[Repositories]
        MODELS[ORM Models]
        CACHE_L[Cache Layer]
        
        REPO -->|uses| MODELS
        REPO -->|uses| CACHE_L
    end
    
    REST --> WF
    AUTH --> REST
    VALID --> REST
    
    WF --> RECON
    RECON --> DIFF
    DIFF --> Clients
    
    WF --> Data
    
    style API fill:#e3f2fd
    style Business fill:#fff3e0
    style Clients fill:#f3e5f5
    style Data fill:#e8f5e9
```

---

## Deployment Architecture (Production)

```mermaid
graph TB
    subgraph Internet["🌐 Internet"]
        USER[Users/CLI]
    end
    
    subgraph AWS["☁️ AWS Cloud"]
        subgraph API_Layer["API Layer"]
            AGW[API Gateway]
            LAMBDA_API[Lambda<br/>FastAPI]
        end
        
        subgraph Queue["Message Queue"]
            SQS[SQS Queue]
            DLQ[Dead Letter Queue]
        end
        
        subgraph Workers["Worker Layer"]
            LAMBDA_W[Lambda Worker<br/>LangGraph]
            ECS[ECS Fargate<br/>Long Jobs]
        end
        
        subgraph Storage["Storage Layer"]
            RDS[(RDS PostgreSQL)]
            ELASTICACHE[(ElastiCache Redis)]
        end
        
        subgraph Observability["Observability"]
            CW[CloudWatch Logs/Metrics]
            XRAY[X-Ray Tracing]
        end
        
        subgraph Secrets["Secrets"]
            SM[Secrets Manager]
        end
    end
    
    subgraph External["🔌 External APIs"]
        PD_E[PagerDuty]
        DD_E[Datadog]
        GF_E[Grafana]
        SL_E[Slack]
    end
    
    USER -->|HTTPS| AGW
    AGW --> LAMBDA_API
    LAMBDA_API -->|enqueue| SQS
    SQS -->|failed| DLQ
    
    SQS -->|trigger| LAMBDA_W
    SQS -->|long jobs| ECS
    
    LAMBDA_API --> RDS
    LAMBDA_W --> RDS
    ECS --> RDS
    
    LAMBDA_API --> ELASTICACHE
    LAMBDA_W --> ELASTICACHE
    
    LAMBDA_W -->|API calls| PD_E
    LAMBDA_W -->|API calls| DD_E
    LAMBDA_W -->|API calls| GF_E
    LAMBDA_W -->|API calls| SL_E
    
    LAMBDA_API -->|logs/metrics| CW
    LAMBDA_W -->|logs/metrics| CW
    LAMBDA_API -->|traces| XRAY
    LAMBDA_W -->|traces| XRAY
    
    LAMBDA_API -->|get tokens| SM
    LAMBDA_W -->|get tokens| SM
    
    style AWS fill:#FF9900,color:#fff
    style External fill:#4CAF50,color:#fff
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
