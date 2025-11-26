# NthLayer Architecture

_Last updated: 2025-10-31_

This document describes NthLayer’s system architecture: components, data flow, and operational concerns. It is intended for engineers implementing the MVP and future hardening/scaling phases.

---

## 1) High-level Overview

NthLayer is a control plane that reconciles metadata between platforms (e.g., Cortex, PagerDuty) and enforces policy/RBAC. The core is a typed API (FastAPI) fronting a worker tier that runs agentic orchestration (LangGraph). Async jobs flow through SQS; periodic tasks are scheduled by EventBridge. Durable state lives in Postgres; Secrets in AWS Secrets Manager; hot paths use Redis.

### ASCII: Platform Topology

```
      ┌──────────────────────────────┐
      │        Engineer / CLI        │
      │   (Typer → Go in future)     │
      └──────────────┬───────────────┘
                     │ HTTPS (JWT)
        ┌────────────▼────────────┐
        │      API Gateway        │
        └────────────┬────────────┘
                     │ Lambda Invoke
        ┌────────────▼────────────┐
        │ FastAPI (Python, async) │  ←→  AWS Secrets Manager (tokens, DB creds)
        │   Mangum adapter        │  ←→  Redis/ElastiCache (cache, rate limits)
        └───────┬────────┬────────┘
                │        │
         OpenAPI│        │SQS Send (idempotent, FIFO opt.)
                │        │
   ┌────────────▼───┐    │          ┌──────────────────────┐
   │ Postgres (RDS) │    │          │  SQS Queue: jobs     │
   │ + pgvector     │    │          │  (DLQ attached)      │
   └──────────────┬─┘    │          └───────────┬──────────┘
                  │      │                      │
                  │  ┌───▼──────────────────────▼───┐
                  │  │ Worker (Lambda or ECS Fargate)│
                  │  │  - LangGraph agent nodes      │
                  │  │  - Retries / backoff          │
                  │  └───────┬───────────┬───────────┘
                  │          │           │
                  │          │           │
                  │          │           │
                  │   ┌──────▼───┐  ┌────▼────┐   ┌───────────┐
                  │   │ PagerDuty│  │ Cortex  │   │ GitHub/CI │
                  │   │   API    │  │   API   │   │ (optional)│
                  │   └──────────┘  └─────────┘   └───────────┘
                  │
                  │     ┌───────────┐
                  └────►│   Slack   │  (notify managers / channels)
                        └───────────┘

                 ┌───────────────────┐
                 │ EventBridge Rules │───► Cron triggers (audits, recons)
                 └───────────────────┘

   Observability: CloudWatch Logs/Metrics + X-Ray tracing (API & Workers)
```

---

## 2) Core Components & Responsibilities

- **FastAPI (Lambda via Mangum)** — Public/internal HTTP interface; JWT verification; validation with Pydantic; OpenAPI contract; idempotency checks; enqueue jobs to SQS; read/write to Postgres when needed.
- **SQS (+ DLQ)** — Durable async queue for reconciliation and audit jobs; native Lambda trigger; redrive to DLQ on repeated failure.
- **Workers (Lambda/ECS Fargate)** — Execute agent graphs; call external APIs; enforce idempotency; write audit trails; emit metrics; optional longer runtime on ECS.
- **LangGraph** — Deterministic orchestration of multi-step workflows and tool calls (PagerDuty, Cortex, Slack, GitHub, etc.).
- **Postgres (RDS) + pgvector** — Durable state (teams, services, roles, runs, findings); vector search for semantic lookup (optional).
- **Redis (ElastiCache)** — Response caching; token/rate-limit buckets; ephemeral coordination.
- **EventBridge** — Schedulers for audits, reconciliations; event bus for internal triggers.
- **AWS Secrets Manager** — Rotation and scoped access to third‑party tokens and DB credentials.
- **GitHub Actions + Terraform** — CI/CD pipeline and IaC for reproducible environments.

---

## 3) Data Contracts (high level)

- **Team**: `id, name, managers[], sources{cortex_id?, pd_id?}, metadata{tier, tags[]}`
- **Service**: `id, name, owner_team_id, tier, dependencies[]`
- **Run (job)**: `job_id, type, requested_by, status, started_at, finished_at, idempotency_key`
- **Finding/Change**: `run_id, entity_ref, before, after, action, api_calls[], outcome`

Contracts are governed by Pydantic v2 models and exposed via OpenAPI.

---

## 4) Sequence — Team Reconciliation (Happy Path)

```
1) CLI → API
   - POST /v1/teams/reconcile { team_id, desired?, source? }
   - Auth: Cognito JWT; Idempotency-Key header recommended.

2) API (FastAPI)
   - Validate payload (Pydantic); verify scopes.
   - Check/record idempotency key in Postgres (unique on team_id+hash).
   - Enqueue SQS message: { job_id, team_id, user_ctx, idem_key }.
   - 202 Accepted { job_id }.

3) Worker Trigger (Lambda/ECS)
   - Pulls from SQS; loads secrets; warms Redis caches.

4) LangGraph Flow
   - Node A: get_cortex_team(team_id)
   - Node B: get_pd_team(team_id)
   - Node C: diff_owners_roles(A,B)
   - Decision: if empty diff → Success; else continue.
   - Node D: apply_pd_changes(diff, idem_key)
   - Node E: write_audit(run_id, before/after, api_calls) → Postgres
   - Node F: notify_slack(team_channel, summary)

5) Completion
   - Ack SQS message; emit metrics (duration, calls, retries).
   - Persist run status in Postgres.
```

### HTTP/API Call Map (example)

```
GET  Cortex  /api/teams/{id}
GET  PagerDuty /teams/{id}; /teams/{id}/members; /users
POST PagerDuty /teams/{id}/users  (add/role update)  [idempotency-key]
POST Slack    /chat.postMessage (optional)
```

---

## 5) Scheduled Audits (EventBridge)

- EventBridge cron (e.g., hourly/nightly) triggers an **enqueue Lambda** that scans Team IDs and publishes audit jobs to SQS.
- Workers run a read-only LangGraph flow to collect divergences without mutating; results are stored and optionally summarized to Slack or email.

---

## 6) Error Handling & Resilience

- **Retries:** Exponential backoff for third‑party API errors; respect rate limits (Redis token bucket).
- **Idempotency:** All mutating calls include an idempotency key; DB enforces uniqueness.
- **DLQ:** After N failures, messages go to DLQ; CloudWatch Alarm → SNS/Slack. Operator can requeue via CLI.
- **Timeouts:** Long or dependency-heavy jobs route to ECS Fargate workers.
- **Observability:** Structured logs (JSON), domain metrics (jobs, diffs, write successes/failures), traces via X‑Ray.

---

## 7) Environments & Deployment

- **Regions:** eu-west-1
- **Envs:** dev, staging, prod (separate AWS accounts recommended)
- **CI/CD:** GitHub Actions with OIDC to AWS; `terraform plan/apply`; Lambda bundling or container images; migrations via job step.

---

## 8) Naming & IAM (brief)

- Resource prefix: `NthLayer-<env>-<component>` (e.g., `NthLayer-prod-api`, `NthLayer-dev-team-reconcile-queue`).
- IAM roles scoped per component (API, workers, enqueueer) with least privilege to Secrets, SQS, RDS, Logs.

---

## 9) Future Options

- **Temporal** for complex, long‑lived workflows and signals.
- **OpenSearch Serverless** for large‑scale vector search if `pgvector` is insufficient.
- **OPA/Rego** for policy at scale.
- **Go CLI** for static single‑binary distribution.

---

## 10) Appendix — Sequence Diagram (ASCII)

```
CLI          API Gateway       FastAPI           SQS           Worker        Cortex       PagerDuty        Slack      Postgres
 | POST /teams/reconcile        |                 |               |              |             |             |
 |----------------------------->|                 |               |              |             |             |
 |                              |  Invoke Lambda  |               |              |             |             |
 |                              |---------------->|               |              |             |             |
 |                              | Validate+Enq    |  Send msg     |              |             |             |
 |                              |---------------->|-------------->|              |             |             |
 | 202 Accepted {job_id}        |                 |               |              |             |             |
 |<-----------------------------|                 |               |              |             |             |
 |                              |                 |  Trigger      |   Start      |             |             |
 |                              |                 |-------------->|------------->|             |             |
 |                              |                 |               |  GET team    |             |             |
 |                              |                 |               |------------->|             |             |
 |                              |                 |               |              |   GET team/members       |
 |                              |                 |               |----------------------------------------->|
 |                              |                 |               |   Diff/Apply (idempotent writes)        |
 |                              |                 |               |----------------------------------------->|
 |                              |                 |               |              |             |  POST msg   |
 |                              |                 |               |------------------------------------------------>|
 |                              |                 |               |  Write audit/changes                                  |
 |                              |                 |               |----------------------------------------------->|
 |                              |                 |  Ack/Delete   |              |             |             |
 |                              |                 |<--------------|              |             |             |
```

---

**Notes**
- All HTTP clients should use circuit breaking, timeouts, and retryable error classification.
- Adopt JSON-structured logging with correlation IDs (propagate job_id and idem_key across all calls).
- Prefer async Python clients (`httpx`, `aioboto3`) where available.

