# Technical Debt Inventory

Known technical debt, tracked as a living document. Items here should have
corresponding Beads issues. Updated by GC sweep and audit agents.

<!-- AUTO-MANAGED: tech-debt -->
| ID | Package | Description | Severity | Beads | Filed |
|----|---------|-------------|----------|-------|-------|
<!-- Populated by audit/GC agents -->
<!-- /AUTO-MANAGED: tech-debt -->

## Debt Reduction Policy

- GC sweep agent files small refactoring PRs for low-severity items
- High-severity items get dedicated Beads issues and planned work
- Items older than 90 days without progress should be re-evaluated:
  either schedule them or accept the debt and remove from this list
