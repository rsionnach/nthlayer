# Mocking classification — where to patch

This document defines the single rule for choosing the patch target in `unittest.mock.patch(...)` calls across the NthLayer ecosystem, and the descriptive taxonomy we use to talk about patched names. It is the shared discipline applied per-site by the per-repo test-suite cleanups (`opensrm-fljv`, `opensrm-u71c`, `opensrm-cevd`, `opensrm-in3m`).

> **Scope.** Every active Python repo with mocking: `nthlayer-common`, `nthlayer-bench`, `nthlayer-workers`, `nthlayer-generate`. `nthlayer-core` is exempt by reference-architecture design (zero `patch()` sites; see [testing.md §Reference architecture](testing.md#reference-architecture)).
>
> The rule table below governs **string-target patches**: `unittest.mock.patch(target_string)` and `pytest_mock`'s `mocker.patch(target_string)`. The underlying principle — *patch the name where the consumer looks it up* — also applies to **object-target patches** (`unittest.mock.patch.object(obj, attr)`, `pytest.MonkeyPatch.setattr(obj, attr, value)`), but the table doesn't decide them: the caller supplies the object directly, so the question becomes "is `obj` the consumer's module (correct) or the canonical source (silent failure)?" — same principle, different mechanic. The `grep` enumeration step in §Application procedure only catches `patch(target_string)` strings; `patch.object` and `monkeypatch.setattr(obj, ...)` sites must be enumerated separately if present.

> **Permanence.** This discipline is not bead-scoped. It governs new tests authored after the cohort cleanup completes; the inventory snapshot ([`vxl0-inventory.md`](superpowers/specs/test-suite-maintenance/vxl0-inventory.md)) is point-in-time and may drift, but this rule does not.

## The rule

**Patch the name at the use site's lookup path — determined by import style, not by where the name is defined.**

| Import style in the code under test | Patch target |
|---|---|
| Module-level `from mod import Name; Name(...)` | `consumer_module.Name` (the consumer's local re-binding) |
| Module-level `from mod import Name as alias; alias(...)` | `consumer_module.alias` (the alias is a new name in the consumer; the bound callable is the same object as `mod.Name`) |
| Module-level `import mod; mod.Name(...)` | `mod.Name` (the source) — see "convention" note below |
| Module-level `import mod as alias; alias.Name(...)` | `mod.Name` (the source) — see "convention" note below |
| Function-body `from mod import Name; Name(...)` inside a `def` | `mod.Name` (the source) — no module-level binding exists |

Confirm the import style per site. Don't assume.

**Why `import mod` and `import mod as alias` share a row.** `import mod` binds the name `mod` in the consumer to the module object held in `sys.modules["mod"]`. `import mod as alias` binds the name `alias` in the consumer to the **same** module object — there is no separate copy. Patching `mod.Name`, `consumer.mod.Name`, or `consumer.alias.Name` all mutate the same `sys.modules["mod"]` object's `Name` attribute, with identical effect. **Codebase convention** is to patch at the consumer's binding (`consumer.mod.Name` or `consumer.alias.Name`) to make scope explicit, but the canonical source form (`mod.Name`) is mechanically equivalent. This is unlike `from mod import Name`, where the consumer's namespace holds an independent binding distinct from `mod.Name`.

The function-body case looks like the module-level `from` case but resolves differently. A `from x import Name` *inside a function body* binds `Name` as a local variable in each call frame; there is no `consumer_module.Name` at module level to patch. The patch must intercept at `x.Name` so the next `from x import Name` lookup picks up the mock. Patching `consumer_module.Name` in this case **raises `AttributeError` at patch time** — `mock.patch()` refuses to patch attributes that don't exist (silent creation requires `create=True`). The failure is loud, not silent. Where you see lazy imports (used to break circular dependencies or defer expensive imports), patch at the source.

## The taxonomy (descriptive labels)

The labels below are descriptive, not prescriptive. They classify what the bound name *is*, not where to patch. The rule above is universal.

### Class A — bound-to-third-party

The name in the consuming module's namespace was imported from a third-party (or stdlib) package.

Examples from the cohort:
- Class: `nthlayer_generate.discovery.client.httpx.get` ← `discovery/client.py: import httpx`
- Stdlib fn: `nthlayer_common.llm.time.sleep` ← `llm.py: import time`
- Module object: `nthlayer_common.telemetry.trace` ← `telemetry.py: from opentelemetry import trace` (the bound name is the `opentelemetry.trace` module itself, not a class on it)
- Instance: `nthlayer_workers.respond.agents.remediation.logger` ← `remediation.py: logger = structlog.get_logger(__name__)` (a `structlog.BoundLogger` instance bound at module scope)

### Class A-flag — optional-dependency boolean

Own-defined module-level boolean that exists because of a `try: from <3p> import ...; FLAG = True / except ImportError: FLAG = False` pattern. Structurally a class-B name (defined in the module), but it exists because of an A-class import. Treat as a separate descriptive class because A-flags co-occur with A-class patches in tests of optional-dependency code paths.

Examples:
- `nthlayer_generate.dependencies.providers.zookeeper.KAZOO_AVAILABLE`
- `nthlayer_workers.measure.telemetry._HAS_OTEL`
- `nthlayer_common.telemetry._otel_available`

### Class B — own-defined-in-same-module

The name is `def`, `class`, or module-level assignment inside the consuming module itself.

Examples:
- `nthlayer_generate.cli.ux.has_gum` ← `cli/ux.py: def has_gum():`
- `nthlayer_common.llm_structured._get_anthropic_client` ← `llm_structured.py:29: def _get_anthropic_client():`
- `nthlayer_workers.measure.calibration.loop.OverrideCalibration` ← `loop.py:31: class OverrideCalibration:`

### Class C — bound-to-other-own-module

The name was imported from another `nthlayer_*` module — same package or sibling package — via `from nthlayer_X.foo import Z`.

Examples:
- Intra-package: `nthlayer_bench.widgets.case_brief.build_paging_brief` ← `widgets/case_brief.py: from nthlayer_bench.sre.brief import build_paging_brief`
- Cross-package: `nthlayer_workers.observe.slo.collector.PrometheusProvider` ← `collector.py: from nthlayer_common.providers import PrometheusProvider`

Cross-package C uses identical mechanics to intra-package C. The presence of a PyPI boundary is irrelevant — the import created a binding in the consumer's namespace, and the rule says patch there.

**Re-exports via `__init__.py`** count as C. When `observe/drift/__init__.py:3` does `from nthlayer_workers.observe.drift.analyzer import DriftAnalyzer`, the `__init__.py` is the consumer — its namespace holds the binding. Patches use the package-level path (`nthlayer_workers.observe.drift.DriftAnalyzer`), not the submodule where the class is defined.

## Why this rule

The patch target answers one question: **where does Python look this name up at call time?**

When code under test does `from nthlayer_common.providers import PrometheusProvider`, the name `PrometheusProvider` is bound into the consumer module's namespace. Calls to `PrometheusProvider(...)` in that module look the name up there, not at `nthlayer_common.providers`. Patching the canonical source leaves the consumer's reference untouched — the production class still runs, the test asserts on a mock that wasn't reached, and the test passes having mocked nothing. **A green test that patched air is the worst outcome on the menu.**

The package boundary is irrelevant to this mechanic. Whether the source lives in the same module, a sibling module, the same PyPI package, or a different PyPI package has nothing to do with where the name resolves at call time. The only thing that matters is how the consumer module imported it.

## Worked examples

### `from x import Y` (module level)

```python
# src/nthlayer_workers/observe/slo/collector.py
from nthlayer_common.providers import PrometheusProvider

class SLOMetricCollector:
    def __init__(self):
        self._provider = PrometheusProvider(...)  # ← look up: collector.PrometheusProvider
```

```python
# tests/observe/test_slo_collector.py
with patch("nthlayer_workers.observe.slo.collector.PrometheusProvider") as mock_p:
    collector = SLOMetricCollector()
    mock_p.assert_called_once()
```

`PrometheusProvider` is defined in `nthlayer_common` — a different PyPI package — but the patch target is still the consumer's binding. The fact that `nthlayer_common.providers.PrometheusProvider` is the canonical source doesn't matter: `collector.py` never looks the name up there.

### `import x; x.Y(...)` (module level)

```python
# src/nthlayer_common/slack.py
import httpx

async def send_message(...):
    async with httpx.AsyncClient() as client:  # ← look up: slack.httpx.AsyncClient
        ...
```

```python
# tests/test_slack.py
with patch("nthlayer_common.slack.httpx.AsyncClient") as mock_client:
    await send_message(...)
```

Both `patch("nthlayer_common.slack.httpx.AsyncClient")` and `patch("httpx.AsyncClient")` work mechanically — `httpx` is one object in `sys.modules`, and patching its `AsyncClient` attribute through either path produces the same result. **Codebase convention** is the first form (`consumer_module.imported_module.Name`), because it makes the patch's scope explicit and matches what we do for `from x import Name` sites. Don't churn existing sites without reason; both forms are correct.

### Function-body `from x import Y`

```python
# src/nthlayer_generate/cli/apply.py
def apply_command(...):
    from nthlayer_generate.providers.prometheus import PrometheusProvider  # ← imported INSIDE the def
    provider = PrometheusProvider(...)  # ← look up: local frame variable
```

```python
# tests/test_cli_apply.py
with patch("nthlayer_generate.providers.prometheus.PrometheusProvider") as mock_p:
    apply_command(...)
```

`apply.py` has no module-level `PrometheusProvider` name — the import only fires when `apply_command` runs. Each call re-imports from `nthlayer_generate.providers.prometheus`, which is the only stable lookup path. Patching `nthlayer_generate.cli.apply.PrometheusProvider` would **raise `AttributeError` at patch time**: the attribute doesn't exist on `cli.apply` at module level, so `mock.patch()` refuses the patch before the test body runs. The error is loud, but it tells you exactly the wrong thing if you don't understand the rule — that the patch target is wrong, not that the test is fundamentally OK. The right answer is to patch the source.

This pattern is common in the generate cohort where modules defer imports to break circular dependencies or avoid loading optional providers at startup. The `providers.{prometheus,grafana,mimir}` re-export shims in nthlayer-generate are all consumed this way.

## Edge cases

### Depth-2 attribute patches

When the patched target is `module.Class.method`, the outer name (`Class`) is resolved by the rule above, then `.method` is attribute-accessed on the resolved class.

Example: `nthlayer_generate.cli.init.CustomTemplateLoader.load_all_templates` — `CustomTemplateLoader` is a C-class re-binding (imported from `specs.custom_templates`), `load_all_templates` is a method on that class. The patch replaces the method on the re-bound class. The rule still applies — confirm the outer name's lookup path; the leaf is attribute access on the resolved object.

### Optional-dependency exception fallbacks

When a `try: from <3p> import SomeError / except ImportError: SomeError = Exception` pattern produces a name that *exists* in both the available and unavailable code paths but with different runtime types, patching it is path-sensitive.

Example: `nthlayer_generate.dependencies.providers.zookeeper.NoNodeError` — when kazoo is installed, `NoNodeError` is `kazoo.exceptions.NoNodeError`; when not, `NoNodeError = Exception`. Patching in the kazoo-available path replaces the third-party type in the module's namespace (intended). Patching in the kazoo-unavailable path replaces the `NoNodeError` binding — which at that point *is* `Exception` — with a mock. The builtin `Exception` is unaffected globally, but every `except NoNodeError:` clause in that module (which at runtime resolves to `except Exception:` because `NoNodeError = Exception`) now catches the mock instead of the real exception. The danger is local to that module, not global, but it's still load-bearing because the unavailable-path code typically uses bare `except NoNodeError:` to swallow optional-dependency errors.

**Convention:** tests that patch an optional-dependency fallback name must also mock the corresponding A-flag to `True` (forcing the kazoo-available code path). The brittle path is the one we don't test.

### Module objects as patch targets

Patching a third-party module reference (e.g. `nthlayer_workers.measure.telemetry.trace` where `trace` is the `opentelemetry.trace` module imported via `from opentelemetry import trace`) replaces the module object in the consumer's namespace. Tests then call e.g. `mock_trace.get_current_span()` to assert behaviour. Mechanically identical to class A; the descriptive note is that the bound name happens to be a module rather than a class or function.

### Instances bound at module scope

`logger = structlog.get_logger(__name__)` binds a `structlog.BoundLogger` instance at module scope. Patching `module.logger` replaces the instance. The rule still applies cleanly: the name lives in the consuming module's namespace.

### Patching a `@property`

`@property` decorators wrap attribute access — replacing them with a plain `Mock` won't intercept the getter. Use `new_callable=PropertyMock`:

```python
with patch("module.Class.some_property", new_callable=PropertyMock) as mock_prop:
    mock_prop.return_value = "fake"
```

The target string still follows the rule; only the replacement type changes. Out of scope for the cohort cleanup (no current sites), but worth knowing for new tests.

### Two valid patch locations

When the same class is patched in two different test files — one patching at the definition module, one at a consumer module — both are correct, but they answer different questions.

Example: `nthlayer_generate.dashboards.validator.DashboardValidator` (class B, patches the definition site) vs `nthlayer_generate.cli.dashboard_validate.DashboardValidator` (class C, patches the consumer's re-binding). Both work. Tests should pick the lookup path closest to where the code under test actually calls the name — i.e. patch at the consumer if the test exercises `cli.dashboard_validate`, patch at the definition if the test exercises `dashboards.validator`.

### Stale patches (`create=True` or non-existent names)

Patches sometimes target names that don't exist in the named module (no `import`, no `def`, no module-level assignment). This is either:

1. **Intentional**: the test uses `mock.patch(..., create=True)`, which lets you patch a non-existent name. Legal but unusual; usually a smell that the test is mocking out a name that should exist.
2. **Stale**: the test was written against an older module shape and never updated.

**Action per site:** check whether the name exists at any of the locations the consumer might look it up. If it doesn't, the test is either using `create=True` (verify intent in the diff) or stale. Then check whether **any assertion in the test body references the mock handle**. A mock that is created and never asserted is vestigial regardless of whether `create=True` is intentional — delete the patch and inspect the test for redundancy.

**Caveat: skipped tests.** Before acting on a vestigial-looking patch, check whether the enclosing test is `@pytest.mark.skip`'d. The discipline applies to runtime lookup; tests that don't run can't have wrong patch targets, and patches inside a skipped block are inert by construction. They are intent-documentation for a deferred code path, and modifying them risks losing semantics nobody is currently exercising. Leave skipped-test patches alone until the test is re-enabled — at which point the patches should be re-evaluated against the rule.

Surfaced anomaly from `opensrm-vxl0` Phase 1: `nthlayer_workers.correlate.cli.write_decision_verdict_fn` (`create=True` patch inside a `@pytest.mark.skip`'d test pending `opensrm-saun.1.2.1`). The patch target doesn't exist in `correlate/cli.py`, but the skip block means the rule does not apply to this site. No action taken in `opensrm-cevd`; flagged for re-evaluation if/when the test re-enables.

## Application procedure (for per-repo cleanup beads)

1. **Enumerate.** Run `grep -rEho "patch\(['\"]nthlayer_<pkg>[^'\"]*['\"]" tests/ | sort -u` to list unique `patch(...)` string targets. If the repo also uses `patch.object(...)` or `monkeypatch.setattr(...)`, enumerate those separately — the grep recipe above only catches string-target patches.
2. **Classify each target descriptively.** Open the source file at the path implied by the patch target, read imports, and assign A / A-flag / B / C. Record file:line evidence per target. The vxl0 inventory has this done already for the cohort as of 2026-06-07 — use it as the starting point, verify drift before applying.
3. **Confirm the import style at every consumer site, including scope.**
   - 3a. For class A patches that look like `module.x.Name`, confirm whether `module` does `from x import Name` (no alias / with alias) or `import x; x.Name` (no alias / with alias). Each variant has its own row in the rule table.
   - 3b. For class C patches, confirm whether the `from nthlayer_*.foo import Name` is at module level or **inside a function body**. Function-body imports have no module-level binding, so patch at the source (`nthlayer_*.foo.Name`), not at the consumer (`consumer_module.Name`).
4. **Verify the patch actually patches.** A patch site that targets a name not present in the named module is the anomaly case above — investigate per the "Stale patches" guidance, including whether any assertion references the mock.
5. **Apply the universal rule.** Where a site patches at the wrong lookup path (typically: patching at the canonical source when the consumer did `from x import Name`), correct it. Where a site already follows the rule, leave it.
6. **Where the rule doesn't decide cleanly** (two valid locations, depth-2 attributes, optional-dependency edge cases, `@property` patches), apply the corresponding edge-case section above.

### Writing new tests

The same rule applies prospectively. Before writing a `patch(...)` call:
1. Open the source file under test.
2. Find how it imports or defines the name you intend to mock. Pay specific attention to (a) whether the import uses `as alias` — the alias is the binding name in the consumer — and (b) whether the import is inside a function body, which has no module-level binding.
3. Pick the patch target by reading the rule table top to bottom for the matching import style.

New tests written against the wrong lookup path will either fail with `AttributeError` (function-body case — loud, annoying) or silently mock nothing (module-level `from x import Name` case — green test, no mock applied). The second is the failure mode this whole document exists to prevent.

### Enforcement

No automated check exists today. Adherence relies on review. A pre-commit hook or pytest plugin that could catch wrong-target patches is conceivable but not currently planned — track it in the CI-standardisation work (`opensrm-314j`) if interest grows.

## Reference

- Phase 1 inventory dataset: [`superpowers/specs/test-suite-maintenance/vxl0-inventory.md`](superpowers/specs/test-suite-maintenance/vxl0-inventory.md) — 145 unique targets / 612 sites / 53 files across the cohort, with per-target classification and 1 anomaly.
- Cohort summary: [`superpowers/specs/test-suite-maintenance/summary-2026-06-06.md`](superpowers/specs/test-suite-maintenance/summary-2026-06-06.md) — Daisy's §3c row 4 Option A produced this shared bead.
- Reference architecture: [`testing.md §Reference architecture`](testing.md#reference-architecture) — why nthlayer-core has zero patch sites.

Sibling beads applying this discipline: `opensrm-fljv` (common), `opensrm-u71c` (bench), `opensrm-cevd` (workers), `opensrm-in3m` (generate).
