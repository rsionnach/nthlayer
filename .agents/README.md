# NthLayer Agent Collaboration System

This directory implements the [agents.md](https://agents.md/) protocol for AI agent collaboration and context preservation.

## Purpose

The NthLayer project has:
- Complex multi-session work spanning weeks
- Recurring dashboard data issues requiring systematic debugging
- Multiple interconnected systems (SDK integration, metric discovery, dashboard generation)
- Critical tracking via GitHub issues (beads)

The agents.md system helps maintain context, track decisions, and prevent repeated mistakes.

## Directory Structure

```
.agents/
├── README.md                 # This file
├── sessions/                 # Session logs
│   ├── 2025-12-02-week2.md  # Current session
│   └── ...
├── decisions/                # Decision logs (ADRs)
│   ├── 001-sdk-integration.md
│   ├── 002-metric-discovery.md
│   └── ...
└── knowledge/               # Persistent knowledge base
    ├── dashboard-issues.md
    ├── metrics-catalog.md
    └── troubleshooting.md
```

## Usage

### For AI Agents

1. **Start of session**: Read recent session logs and relevant decision logs
2. **During work**: Update session log with actions, findings, and blockers
3. **Major decisions**: Create decision log documenting context, options, and chosen approach
4. **End of session**: Summarize outcomes, blockers, and next steps

### For Humans

- Review `.agents/sessions/` to see what's been tried
- Check `.agents/decisions/` to understand architectural choices
- Reference `.agents/knowledge/` for troubleshooting patterns

## Current State

**Project**: NthLayer - Observability as Code  
**Phase**: Week 2 - Foundation SDK Integration  
**Status**: Debugging dashboard data display issues  
**Critical Issue**: [#10](https://github.com/rsionnach/nthlayer/issues/10) - 57.5% of panels showing no data

## Key Learnings

1. **Dashboard queries must match metric types**: API services use `http_requests_total`, stream processors use `events_processed_total`, workers use `notifications_sent_total`

2. **Template variables are essential**: Without `$service` variable definition, queries fail silently

3. **RefId conflicts break multi-query panels**: Each query in a panel needs unique RefId (A, B, C...)

4. **Service type matters for dashboards**: checkout-service uses MySQL not PostgreSQL, analytics-stream doesn't emit HTTP metrics

5. **Advanced metrics require exporters**: Redis panels like "Evicted Keys" need Redis Exporter, not basic Prometheus metrics

## Session Conventions

Each session log should include:
- **Date and context**: When work started, what was the goal
- **Actions taken**: What was tried (with code/tool references)
- **Findings**: What worked, what didn't, why
- **Blockers**: Unresolved issues requiring attention
- **Next steps**: Clear handoff for next session

## Decision Log Format

Decision logs follow Architectural Decision Record (ADR) format:
- **Status**: Proposed | Accepted | Deprecated | Superseded
- **Context**: What problem needed solving
- **Options Considered**: Alternative approaches
- **Decision**: What was chosen and why
- **Consequences**: Positive and negative outcomes
