# Package Quality Grades

Last updated: 2026-03-05

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
| deployments | 1 file | Minimal | Good (DeploymentProviderError) | Evolving | C | test_deployment_providers.py added |
| discovery | 3 files | Partial | Good | Stable | B | MetricDiscovery well-covered |
| identity | 2 files | Minimal | Good | Stable | C | Resolver tested |
| loki | 2 files | Minimal | Good | Stable | C | Alert generation tested |
| metrics | 2 files | Minimal | Good | Evolving | C | Basic coverage |
| orchestrator | 1 file | Minimal | Good | Stable | C | Needs more integration tests |
| pagerduty | 6 files | Partial | Good | Stable | B | Good coverage |
| portfolio | 3 files | Minimal | Good | Stable | C | Basic coverage |
| providers | 2 files | Minimal | Good (ProviderError) | Stable | C | Async pattern consistent |
| slos | 9 files | Partial | Good | Stable | B | Solid coverage: ceiling, correlator, deployment, notifiers, storage, CLI |
| validation | 2 files | Minimal | Good | Stable | C | test_validation.py + test_validation_promruval.py |
| cloudwatch | 1 file | Minimal | Good (fail-open flush) | Stable | C | MetricsCollector: emit, timer, flush, singleton tested |
| db | 2 files | Minimal | Good | Stable | C | SQLite in-memory model tests + mock-based repository tests |
| domain | 1 file | Minimal | Good | Stable | C | All Pydantic models tested: construction, roundtrip, defaults |
| generators | 4 files | Minimal | Good | Evolving | C | alerts, sloth, docs, backstage generators tested |
| integrations | 1 file | Minimal | Good | Stable | C | PagerDutyClient: setup, find, create, error paths tested |
| topology | 1 file | Partial | Good | Evolving | C | test_topology.py added with dc1648b; API new |
<!-- /AUTO-MANAGED: quality-grades -->

## Grade History

Track grade changes to see trajectory over time.

<!-- AUTO-MANAGED: grade-history -->
| Date | Package | Change | Reason |
|------|---------|--------|--------|
| 2026-02-12 | all | — | Initial assessment |
| 2026-02-28 | deployments | D → C | test_deployment_providers.py added (dc1648b desloppify sweep) |
| 2026-02-28 | topology | (new) C | New module with test coverage; API evolving |
| 2026-03-05 | slos | D → B | 9 test files discovered (were miscounted as 0) |
| 2026-03-05 | validation | D → C | 2 test files discovered (were miscounted as 0) |
| 2026-03-05 | cloudwatch | F → C | test_cloudwatch.py added (12 tests) |
| 2026-03-05 | db | F → C | test_db_models.py + test_db_repositories.py added (24 tests) |
| 2026-03-05 | domain | F → C | test_domain_models.py added (21 tests) |
| 2026-03-05 | generators | F → C | 4 test files added: alerts, sloth, docs, backstage (60 tests) |
| 2026-03-05 | integrations | F → C | test_integrations_pagerduty.py added (12 tests) |
<!-- /AUTO-MANAGED: grade-history -->

## Improvement Priorities

Packages graded D or F should have active Beads issues for improvement.
Run `/project:audit-codebase` to identify specific gaps.
