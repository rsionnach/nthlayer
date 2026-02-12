# Package Quality Grades

Last updated: 2026-02-12

## Grading Criteria

| Grade | Meaning |
|-------|---------|
| A | Test coverage >80%, docs complete, error handling complete, API stable |
| B | Test coverage >60%, docs partial, minor error handling gaps, API stable |
| C | Test coverage >40%, docs minimal, notable gaps, API evolving |
| D | Test coverage <40%, docs absent, significant gaps |
| F | Untested, undocumented, known bugs unaddressed |

## Current Grades

<!-- AUTO-MANAGED: quality-grades -->
| Package | Tests | Docs | Error Handling | API Stability | Grade | Notes |
|---------|-------|------|----------------|---------------|-------|-------|
| alerts | 5 files | Partial | Good (NthLayerError) | Stable | B | Solid coverage, minor doc gaps |
| api | 2 files | Minimal | Good | Evolving | C | Webhook routes tested, needs more |
| cli | 33 files | Minimal | Good (ux.py helpers) | Stable | B | Best test coverage in project |
| config | 6 files | Partial | Good | Stable | B | Well-tested config loading |
| core | 1 file | Minimal | Good (error base) | Stable | C | Error hierarchy well-defined |
| dashboards | 4 files | Partial | Good | Stable | B | Intent system well-tested |
| dependencies | 2 files | Minimal | Good (ProviderError) | Stable | C | Provider pattern solid |
| deployments | 0 files | Minimal | Good (DeploymentProviderError) | New | D | No tests yet, recently added |
| discovery | 3 files | Partial | Good | Stable | B | MetricDiscovery well-covered |
| identity | 2 files | Minimal | Good | Stable | C | Resolver tested |
| loki | 2 files | Minimal | Good | Stable | C | Alert generation tested |
| metrics | 2 files | Minimal | Good | Evolving | C | Basic coverage |
| orchestrator | 1 file | Minimal | Good | Stable | C | Needs more integration tests |
| pagerduty | 6 files | Partial | Good | Stable | B | Good coverage |
| portfolio | 3 files | Minimal | Good | Stable | C | Basic coverage |
| providers | 2 files | Minimal | Good (ProviderError) | Stable | C | Async pattern consistent |
| slos | 0 files | Minimal | Good | Stable | D | Needs test coverage |
| validation | 0 files | Minimal | Good | Stable | D | Needs test coverage |
| cloudwatch | 0 files | Absent | Unknown | New | F | No tests, no docs |
| db | 0 files | Absent | Unknown | New | F | No tests, no docs |
| domain | 0 files | Absent | Unknown | New | F | No tests, no docs |
| generators | 0 files | Absent | Unknown | Evolving | F | No tests, no docs |
| integrations | 0 files | Absent | Unknown | New | F | No tests, no docs |
<!-- /AUTO-MANAGED: quality-grades -->

## Grade History

Track grade changes to see trajectory over time.

<!-- AUTO-MANAGED: grade-history -->
| Date | Package | Change | Reason |
|------|---------|--------|--------|
| 2026-02-12 | all | — | Initial assessment |
<!-- /AUTO-MANAGED: grade-history -->

## Improvement Priorities

Packages graded D or F should have active Beads issues for improvement.
Run `/project:audit-codebase` to identify specific gaps.
