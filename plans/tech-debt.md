# Technical Debt Inventory

Known technical debt, tracked as a living document. Items here should have
corresponding Beads issues. Updated by GC sweep and audit agents.

<!-- AUTO-MANAGED: tech-debt -->
| ID | Package | Description | Severity | Beads | Filed |
|----|---------|-------------|----------|-------|-------|
| TD-001 | cloudwatch | Zero test coverage for MetricsCollector | High | trellis-hlig | 2026-03-05 |
| TD-002 | db | Zero test coverage for models, repositories, session | High | trellis-tfvh | 2026-03-05 |
| TD-003 | domain | Zero test coverage for Pydantic domain models | High | trellis-fncd | 2026-03-05 |
| TD-004 | generators | Zero test coverage for alerts, backstage, docs, sloth | High | trellis-zxqw | 2026-03-05 |
| TD-005 | integrations | Zero test coverage for PagerDutyClient | High | trellis-l1uo | 2026-03-05 |
<!-- /AUTO-MANAGED: tech-debt -->

## Debt Reduction Policy

- GC sweep agent files small refactoring PRs for low-severity items
- High-severity items get dedicated Beads issues and planned work
- Items older than 90 days without progress should be re-evaluated:
  either schedule them or accept the debt and remove from this list
