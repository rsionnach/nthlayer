# vxl0 — mocking-classification inventory

**Bead:** `opensrm-vxl0` · Phase 1 deliverable
**Date:** 2026-06-07
**Scope:** Enumerate every `patch("nthlayer_<pkg>...")` call site across the cohort, classify each unique target by import-resolution evidence, surface anomalies, and identify canonical exemplars for the forthcoming discipline doc at `nthlayer/docs/mocking-classification.md`.

Per `opensrm-vxl0` parent guidance: per-site application happens inside the per-repo cleanup beads (`opensrm-fljv`, `opensrm-u71c`, `opensrm-cevd`, `opensrm-in3m`). This inventory is the input dataset for those beads.

## Cohort totals

| Repo | Unique targets | Sites | Files | A | A-flag | B | C | Anomaly |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| nthlayer-common | 7 | 44 | 5 | 4 | 1 | 2 | 0 | 0 |
| nthlayer-bench | 4 | 10 | 4 | 1 | 0 | 0 | 3 | 0 |
| nthlayer-workers | 25 | 101 | 13 | 4 | 1 | 11 | 8 | 1 |
| nthlayer-generate | 109 | 457 | 31 | 11 | 2 | 43 | 53 | 0 |
| nthlayer-core | 0 | 0 | 0 | — | — | — | — | — |
| **Total** | **145** | **612** | **53** | **20** | **4** | **56** | **64** | **1** |

Counts vs the bead description:
- Bench was 74/10 in the 2026-06-05 audit; live is 10/4 — suite has been partially cleaned since.
- Workers was "~0" in the bead description; live is ~105/13 — bead description was wrong. The cleanup work in `opensrm-cevd` is substantial, not trivial.

## The universal patch-target rule

Classification (A / B / C / A-flag) is **descriptive**, not prescriptive. It labels what the bound name *is*, not where to patch. Per-site test treatment follows one rule, independent of class:

> **Patch the name at the use site's lookup path, determined by import style.**
>
> - `from mod import Name; Name(...)` → patch `consumer_module.Name` (the local re-binding)
> - `import mod; mod.Name(...)` → patch `mod.Name` (the source)

Why: if `collector.py` does `from nthlayer_common.providers import PrometheusProvider`, the name `PrometheusProvider` lives in `collector.py`'s namespace. Patching the canonical source (`nthlayer_common.providers.PrometheusProvider`) leaves `collector.py`'s reference untouched — the test passes having mocked nothing. A green test that patched air is the worst outcome on the menu.

So: confirm import style per site, then patch at the consuming module's binding (for `from ... import`) or at the source (for `import x; x.Name`). The package boundary is irrelevant to the mechanics — same-package vs PyPI has nothing to do with where the name resolves at call time.

## Classification taxonomy (descriptive labels)

- **A · bound-to-third-party** — name in the consuming module's namespace was imported from a third-party (or stdlib) package via `import httpx` or `from opentelemetry import trace`. Includes module objects (`opentelemetry.trace`), classes (`httpx.AsyncClient`), functions (`time.sleep`), and instances (`structlog.get_logger(__name__)` bound to module-level `logger`).
- **A-flag · optional-dependency boolean** — own-defined module-level boolean (`_HAS_OTEL`, `KAZOO_AVAILABLE`, `ETCD3_AVAILABLE`) that exists because of a `try: from <3p> import ...; FLAG = True / except ImportError: FLAG = False` pattern. Structurally B-shaped but exists because of an A-class import.
- **B · own-defined-in-same-module** — name is `def`, `class`, or module-level assignment inside the consuming module itself.
- **C · bound-to-other-own-module** — name was imported from another `nthlayer_*` module (same package or sibling package) via `from nthlayer_X.foo import Z`. Whether that other module is in the same PyPI package or a different one (e.g. `nthlayer_common` re-imported into `nthlayer_workers`) is irrelevant.

---

## nthlayer-common — 7 targets / 44 sites / 5 files

| Class | Target | Sites | Evidence | Notes |
|---|---|---:|---|---|
| A | `nthlayer_common.slack.httpx.AsyncClient` | 5 | `slack.py:11 import httpx` | canonical bound-to-3p |
| A | `nthlayer_common.llm.httpx.post` | 22 | `llm.py:33 import httpx` | highest-weight target in suite |
| A | `nthlayer_common.llm.time.sleep` | 7 | `llm.py:30 import time` | stdlib variant |
| A | `nthlayer_common.telemetry.trace` | 5 | `telemetry.py:24 from opentelemetry import trace` (inside try/except) | the bound name is the `opentelemetry.trace` module object |
| A-flag | `nthlayer_common.telemetry._otel_available` | 1 | `telemetry.py` try-block `_otel_available = True` / except `= False` | co-occurs with `trace` patches |
| B | `nthlayer_common.llm_structured._get_anthropic_client` | 3 | `llm_structured.py:29 def _get_anthropic_client():` | private factory fn, lazy-init singleton |
| B | `nthlayer_common.llm_structured._get_openai_client` | 1 | `llm_structured.py:41 def _get_openai_client():` | same pattern |

No class-C targets present. Files: `test_slack.py`, `test_llm.py`, `test_llm_stub.py`, `test_llm_structured.py`, `test_telemetry.py`.

## nthlayer-bench — 4 targets / 10 sites / 4 files

| Class | Target | Sites | Evidence | Notes |
|---|---|---:|---|---|
| A | `nthlayer_bench.app.httpx.AsyncClient` | 7 | `app.py:12 import httpx` | highest-frequency in repo |
| C | `nthlayer_bench.widgets.case_brief.build_paging_brief` | 1 | `widgets/case_brief.py:19-27 from nthlayer_bench.sre.brief import ... build_paging_brief`; defined at `sre/brief.py:99` | sibling intra-package re-bind |
| C | `nthlayer_bench.widgets.situation_board.fetch_situation_board` | 1 | `widgets/situation_board.py:23-29 from nthlayer_bench.sre.situation_board import ... fetch_situation_board`; defined at `sre/situation_board.py:77` | same pattern |
| C | `nthlayer_bench.widgets.case_review.build_post_incident_review` | 1 | `widgets/case_review.py:20-28 from nthlayer_bench.sre.post_incident import ... build_post_incident_review`; defined at `sre/post_incident.py:366` | same pattern |

No class-B or A-flag targets. Files: `test_widgets_case_brief.py`, `test_widgets_situation_board.py`, `test_widgets_case_review.py`, `test_app.py`.

## nthlayer-workers — 26 targets / ~105 sites / 13 files

Files: `tests/observe/{test_slo_collector.py, test_observe_worker.py}`, `tests/measure/{test_evaluator.py, test_prometheus.py, test_measure_worker.py, test_telemetry.py, test_cli.py, test_calibration_loop.py}`, `tests/correlate/{test_reasoning.py, test_correlate_command.py, test_summary.py}`, `tests/respond/{test_webhook.py, test_respond_command.py, test_remediation.py}`.

### Class A (4 targets)

| Target | Sites | Evidence |
|---|---:|---|
| `nthlayer_workers.measure.adapters.prometheus.httpx.AsyncClient` | 1 | `measure/adapters/prometheus.py:9 import httpx` |
| `nthlayer_workers.measure.telemetry.trace` | 3 | `measure/telemetry.py:15 from opentelemetry import trace` (try-block) |
| `nthlayer_workers.respond.agents.remediation.logger` | 2 | `respond/agents/remediation.py:22 logger = structlog.get_logger(__name__)` (third-party `BoundLogger` instance) |
| `nthlayer_workers.respond.safe_actions.webhook.httpx.AsyncClient` | 12 | `respond/safe_actions/webhook.py:23 import httpx` |

### Class A-flag (1 target)

| Target | Sites | Evidence |
|---|---:|---|
| `nthlayer_workers.measure.telemetry._HAS_OTEL` | 4 | `measure/telemetry.py:18 try: from opentelemetry import trace; _HAS_OTEL = True / except ImportError: _HAS_OTEL = False` |

### Class B (11 targets — own-defined in same module)

| Target | Sites | Evidence |
|---|---:|---|
| `nthlayer_workers.measure.adapters.prometheus.query_prometheus` | 6 | `measure/adapters/prometheus.py:136 async def query_prometheus(...)` |
| `nthlayer_workers.observe.dependencies.providers.prometheus.PrometheusDepProvider` | 1 | `observe/dependencies/providers/prometheus.py:112 class PrometheusDepProvider` |
| `nthlayer_workers.measure.cli._build_evaluator` | 1 | `measure/cli.py:44 def _build_evaluator(...)` |
| `nthlayer_workers.measure.cli._build_store` | 4 | `measure/cli.py:32 def _build_store(...)` |
| `nthlayer_workers.measure.cli._build_tracker` | 1 | `measure/cli.py:38 def _build_tracker(...)` |
| `nthlayer_workers.measure.calibration.loop.OverrideCalibration` | 1 | `measure/calibration/loop.py:31 class OverrideCalibration:` |
| `nthlayer_workers.correlate.prometheus.fetch_alerts` | 10 | `correlate/prometheus.py:15 async def fetch_alerts(...)` — patched at source because consumers use function-body lazy imports |
| `nthlayer_workers.correlate.prometheus.fetch_metric_breaches` | 10 | `correlate/prometheus.py:52 async def fetch_metric_breaches(...)` — same |
| `nthlayer_workers.correlate.reasoning._call_model` | 4 | `correlate/reasoning.py:109 async def _call_model(...)` |
| `nthlayer_workers.correlate.reasoning.reason_about_correlations` | 1 | `correlate/reasoning.py:41 async def reason_about_correlations(...)` |
| `nthlayer_workers.respond.cli._make_coordinator` | 3 | `respond/cli.py:31 def _make_coordinator(...)` |

Total B sites: 42 across 11 targets. Confirmed during Phase 2 validation.

### Class C (8 targets — bound to other own-module)

| Target | Sites | Evidence |
|---|---:|---|
| `nthlayer_workers.observe.slo.collector.PrometheusProvider` | 7 | `observe/slo/collector.py:11 from nthlayer_common.providers import PrometheusProvider` — cross-package re-import |
| `nthlayer_workers.measure.worker.PrometheusProvider` | 11 | `measure/worker.py:22 from nthlayer_common.providers import PrometheusProvider` |
| `nthlayer_workers.measure.pipeline.evaluator.load_prompt` | 3 | `measure/pipeline/evaluator.py:17 from nthlayer_common.prompts import load_prompt` |
| `nthlayer_workers.measure.pipeline.evaluator.structured_call_with_usage` | 3 | `measure/pipeline/evaluator.py:16 from nthlayer_common.llm_structured import structured_call_with_usage` |
| `nthlayer_workers.correlate.summary.structured_call` | 4 | `correlate/summary.py:16 from nthlayer_common.llm_structured import structured_call` |
| `nthlayer_workers.observe.worker.SLOMetricCollector` | 5 | `observe/worker.py:25 from nthlayer_workers.observe.slo.collector import SLOMetricCollector` — intra-package re-bind |
| `nthlayer_workers.observe.drift.DriftAnalyzer` | 2 | `observe/drift/__init__.py:3 from nthlayer_workers.observe.drift.analyzer import DriftAnalyzer` — package-level re-export |
| `nthlayer_workers.observe.dependencies.DependencyDiscovery` | 1 | `observe/dependencies/__init__.py:3 from nthlayer_workers.observe.dependencies.discovery import DependencyDiscovery` — package-level re-export |

## nthlayer-generate — 109 targets / 457 sites / 31 files

> **Post-synthesis correction.** The generate explorer agent classified `nthlayer_generate.providers.{prometheus,grafana,mimir}.{PrometheusProvider,GrafanaProvider,MimirRulerProvider}` (16 sites total) as **class A** on the rationale that nthlayer-common is a separately installed PyPI package, therefore "third-party relative to nthlayer_generate". These targets are **re-classified C** here. The shim file (`providers/prometheus.py` etc.) does `from nthlayer_common.providers.X import X` — structurally identical to workers' `observe/slo/collector.py` doing `from nthlayer_common.providers import PrometheusProvider`, which the workers agent classified C. The classification rule is consistent: definition lives outside the consuming module, regardless of PyPI boundary. Validator confirmed the rule's patch target works correctly (the shim's namespace is the consumer's binding) — see [validation report in commit `nthlayer@a2e0f1a`].

Full per-target table preserved separately. Distribution (post-correction):

- **A** (11 targets): `discovery.client.httpx.get` (20 sites), `integrations.pagerduty.httpx.Client` (4), `config.cli.getpass.getpass` (4), `cli.slo.asyncio.run` (2), `pagerduty.orchestration.RestApiV2Client` (12), `pagerduty.resources.RestApiV2Client` (3), `dependencies.providers.etcd.etcd3` (1), `dependencies.providers.zookeeper.{KazooClient, KazooState, NoNodeError}` (1+3+1), `config.loader.Path.home` (5).
- **A-flag** (2 targets): `dependencies.providers.etcd.ETCD3_AVAILABLE` (3), `dependencies.providers.zookeeper.KAZOO_AVAILABLE` (3).
- **B** (43 targets): dominated by `cli.ux.has_gum` (31 sites), `cli.ux._run_gum` (11), `cli.setup._confirm` (8), `loki.generator.extract_dependencies_from_resources` (8), `specs.parser.parse_service_file` (8), plus 38 lower-frequency CLI command / private helper definitions.
- **C** (53 targets): dominated by `config.cli.get_secret_resolver` (24 sites), `config.cli.{load_config, save_config}` (12 each), `cli.validate_spec.ConftestValidator` (10), `cli.pagerduty.PagerDutyClient` (9), `cli.generate_alerts.generate_alerts_for_service` (9), the 3 re-export shim targets (`providers.{prometheus,grafana,mimir}.*Provider` — 10+2+4 sites; see post-synthesis correction above), plus 45 lower-frequency re-imports.

## Anomalies

1. **`nthlayer_workers.correlate.cli.write_decision_verdict_fn`** — patched in tests, but the name does not exist in `correlate/cli.py` (no `import`, no `def`, no module-level assignment). Either the test uses `mock.patch(..., create=True)` (legal but unusual) or the test is stale. Defer to per-site investigation in `opensrm-cevd`.

2. **`nthlayer_generate.dependencies.providers.zookeeper.NoNodeError`** — fallback `= Exception` (stdlib builtin) on `ImportError`. Patching during the kazoo-available code path replaces the third-party type (intended); patching during the kazoo-absent path would replace `Exception` itself (dangerous). Tests appear to always mock `KAZOO_AVAILABLE = True` alongside, so the dangerous path is not exercised — but the brittleness should be called out in the discipline doc.

3. **`nthlayer_generate.cli.init.CustomTemplateLoader.load_all_templates`** — depth-2 attribute patch. The outer name `CustomTemplateLoader` is C (re-imported from `specs.custom_templates`); the leaf `load_all_templates` is a method on that class. The universal rule still applies — the patch targets the consumer's binding — but the depth-2 form is rare enough to deserve an explicit example.

4. **Generate's `dashboards.validator.DashboardValidator` is patched at two valid locations** in different test files: at the definition module (`dashboards.validator.DashboardValidator`, B-class) and at a consumer module (`cli.dashboard_validate.DashboardValidator`, C-class). Same class, both work. Discipline doc should note: tests should pick the lookup path closest to where the code under test actually calls it.

5. **`structlog.get_logger(__name__)`-bound loggers as Class A.** Examples: `nthlayer_workers.respond.agents.remediation.logger`. The bound name is a third-party `BoundLogger` *instance*, not a class — but the universal rule still applies cleanly (the name lives in the consuming module, patch at the consuming module's binding).

6. **OpenTelemetry `trace` is a module object, not a class.** Examples: `nthlayer_common.telemetry.trace`, `nthlayer_workers.measure.telemetry.trace`. Patches replace the module reference; tests then call e.g. `trace.get_current_span()` on the mock. Mechanically identical to class A.

## Canonical exemplars for the discipline doc

| Class | Best exemplar | Why |
|---|---|---|
| A | `nthlayer_generate.discovery.client.httpx.get` (20 sites) | highest frequency, unambiguous third-party, classic `import httpx` binding |
| A · stdlib variant | `nthlayer_common.llm.time.sleep` (7 sites) | shows the rule applies equally to stdlib |
| A · 3p module | `nthlayer_workers.measure.telemetry.trace` (3 sites) | shows module-object patching pattern |
| A · 3p instance | `nthlayer_workers.respond.agents.remediation.logger` (2 sites) | shows `structlog.get_logger(__name__)` pattern |
| A-flag | `nthlayer_generate.dependencies.providers.zookeeper.KAZOO_AVAILABLE` (3 sites) | textbook `try/except` optional-import flag |
| B | `nthlayer_generate.cli.ux.has_gum` (31 sites) | highest single B count, clean `def` in same module |
| B · private helper | `nthlayer_common.llm_structured._get_anthropic_client` (3 sites) | lazy-init singleton, private factory fn |
| C · intra-package | `nthlayer_bench.widgets.case_brief.build_paging_brief` (1 site) | `from nthlayer_bench.sre.brief import ...` |
| C · cross-package | `nthlayer_workers.observe.slo.collector.PrometheusProvider` (7 sites) | `from nthlayer_common.providers import ...` — same mechanics, different PyPI package |

## Sibling beads receiving this dataset

| Bead | Repo | Sites | Notes |
|---|---|---:|---|
| `opensrm-fljv` | nthlayer-common | 44 | A-heavy (32/44 sites are httpx/time/trace); 4 B sites in `llm_structured`; no C work. |
| `opensrm-u71c` | nthlayer-bench | 10 | Single A pattern (`app.httpx.AsyncClient`, 7 sites) + 3 widget C re-binds (1 each). Smallest cohort. |
| `opensrm-cevd` | nthlayer-workers | 101 | Mix-heavy: 4 A + 1 A-flag + 11 B + 8 C + 1 anomaly. PrometheusProvider cross-package C pattern is the cohort archetype. Anomaly #1 (`write_decision_verdict_fn`) belongs here. |
| `opensrm-in3m` | nthlayer-generate | 457 | Largest by an order of magnitude. C-dominant (53 targets, mostly CLI re-imports from `config.cli`, `cli.setup`). Re-export shims (`providers.{prometheus,grafana,mimir}`) need explicit treatment guidance per the discipline doc's function-body worked example. |

`nthlayer-core` (0 sites) needs no application bead; the reference-architecture pattern sanctioned in `opensrm-5vuz` already explains why.
