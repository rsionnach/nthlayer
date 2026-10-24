# nthlayer-generate on nthlayer-common's manifest model — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** nthlayer-generate loads every manifest through `nthlayer_common.manifest.load_manifest` and consumes common's `ReliabilityManifest`; its own `specs/manifest.py`, `specs/loader.py` and `specs/opensrm_parser.py` are deleted; no rule it emits today disappears; v2 manifests load.

**Architecture:** common 5.4.0 first (an `authored_type` field; srm/v1 top-level `query:`). Then, in generate, goldens pinned on unchanged code, then the switch: imports move to common, generate-only behaviour (alerting parse, contracts, service-context and migrate helpers, generate's service-name rule) stays in generate, and the calibration/feedback_latency recording rules are rebuilt from `JudgmentThreshold` with identical names.

**Tech Stack:** Python 3.11+, uv, pytest, ruff, mypy (generate), release-please.

**Spec:** `nthlayer/docs/superpowers/specs/2026-10-24-wo62-1-generate-on-common-manifest-design.md`. Read it before any task; its `Ruling:` lines need Rob's yes before Task 1.

## Global Constraints

- Worktrees MUST be siblings: `.claude/bin/eco-worktree.sh <repo> wo62`, giving `<ecosystem>/<repo>-wo62`. Never `claude --worktree` or agent `isolation: worktree` on common or generate — the golden corpus reads `../opensrm` and `uv` resolves `../nthlayer-common`.
- Shared repo first: Checkpoint A (common 5.4.0) is gated, merged, released and verified on PyPI, and the five consumer floors are bumped, before Checkpoint B starts.
- Never merge before the R5 gate (correctness → clarity → edge-cases → provenance, then advisory excellence). Ask Rob before every push, merge and release.
- Commit format: `<type>(<scope>): <description> (opensrm-wo62.1)` + blank line + `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`. New behaviour in unshipped code is `feat`, never `fix`. Generate's switch commit carries `BREAKING CHANGE:` (spec §5.5).
- Run `uv run ruff check src/ tests/` and check its exit code directly — never pipe it. Never chain a command after a `sed`/edit with `&&` without checking it succeeded. Full suites: `uv run pytest -p no:cacheprovider -o addopts= -q`.
- Fixtures come from shipped examples and the spec, never from the code under test: generate's `examples/`, `opensrm/spec/v2/examples/` via `Path(__file__).resolve().parents[2] / "opensrm"` with an assertion-style presence test (no `skipif`). A fixture copied into a test carries a provenance comment naming its source path and commit.
- Goldens are never regenerated to make a test pass. In Checkpoint B they are written once from unchanged code; in Checkpoint C every changed golden is listed and approved by Rob before the gate (Task 14).
- `git status --short` before every commit; nothing under `generated/`, `htmlcov/` or `.claude/` is committed.
- After merging any PR: `gh pr merge N --merge --body ""`. Squash release PRs.

## Review Focus

1. **A manifest declaring both `indicator.query` and a different top-level `query`.** Expected: `ManifestLoadError` naming the SLO, not a silent precedence. Identical values load. Test in Task 2.
2. **`authored_type` through the v2 parser.** The v2 parser resolves the type before constructing the manifest (`parser/v2.py:164-170`); without an explicit `authored_type=` it would record the resolved spelling and reopen opensrm-z3ab for v2. Test in Task 1.
3. **A v2 judgment SLO whose `metadata.name` is not its type** (`triage-agent-reversal-rate`, `judgment_type: reversal_rate`, in the spec's own example). Expected: reversal-rate rules emitted (dispatch on `judgment_type`). Today's dispatch on `slo.name` would emit nothing. Test in Task 11.
4. **Calibration with only `maximum_brier_score`, feedback_latency with only `maximum_p90`.** Expected: no `ai_gate:calibration:*` rules and no `:bucket` rule respectively, and no exception; `:p50/:p95/:p99` still emitted. Test in Task 11.
5. **A v2 manifest given to `nthlayer migrate`.** Expected: "already OpenSRM", exit 0, nothing written (spec Ruling on `source_format`). Test in Task 12.
6. **A manifest with a malformed `alerting:` block.** Expected: `alerts evaluate` fails on it; `docs` and `backstage` now succeed (load no longer parses alerting). The behaviour change is in the golden list. Test in Task 9.
7. **The golden harness passing vacuously** — an empty corpus, a missing `../opensrm`, a mask that hides everything, or update mode left on. Each must fail. Tests in Task 5.

---

## Checkpoint A — nthlayer-common 5.4.0 (worktree `nthlayer-common-wo62`, branch `feat/wo62-1-authored-type-query`)

### Task 1: `ReliabilityManifest.authored_type`

**Files:**
- Modify: `nthlayer-common/src/nthlayer_common/manifest/models.py` (`ReliabilityManifest`, field list ends at `raw_data` ~line 1007; `__post_init__` ~1009-1048)
- Modify: `nthlayer-common/src/nthlayer_common/manifest/parser/v2.py` (manifest construction after the type resolution at ~164-170)
- Test: `nthlayer-common/tests/test_manifest_authored_type.py` (create)

**Interfaces:**
- Produces: `ReliabilityManifest.authored_type: str | None` — after construction always a `str`: the type exactly as written. `type` keeps its meaning (resolved). Consumed by generate's sloth `${type}` substitution and `specs/context.py` (Task 9).

- [ ] **Step 1: Write the failing tests**

```python
"""ReliabilityManifest.authored_type keeps the spelling the author wrote.

The invariant is opensrm-z3ab's (nthlayer-generate specs/models.py:74-92):
`type` is resolved for internal comparisons; `authored_type` is what `${type}`
substitutes into generated PromQL, where rewriting `web` to `x-web` selects
zero series in the operator's Prometheus. Alias spellings are common's
SERVICE_TYPE_ALIASES (models.py:75), the documented input conveniences; the
extension spelling is opensrm/spec/v2/examples/x-service-type.yaml's.
"""
import dataclasses
from pathlib import Path

import pytest
import yaml

from nthlayer_common.manifest import ReliabilityManifest, load_manifest
from nthlayer_common.manifest.parser.v1 import parse_srm_v1
from nthlayer_common.manifest.parser.v2 import parse_opensrm_v2

OPENSRM = Path(__file__).resolve().parents[2] / "opensrm"
X_TYPE_EXAMPLE = OPENSRM / "spec" / "v2" / "examples" / "x-service-type.yaml"
ALIASES = [("web", "x-web"), ("background-job", "worker"), ("pipeline", "batch")]


def _v1(service_type: str) -> dict:
    return {"apiVersion": "srm/v1", "kind": "ServiceReliabilityManifest",
            "metadata": {"name": "shop", "team": "t", "tier": "critical"},
            "spec": {"type": service_type}}


def _v2(service_type: str) -> dict:
    return {"apiVersion": "opensrm.nthlayer.io/v2", "kind": "ServiceManifest",
            "metadata": {"name": "shop", "labels": {"tier": "critical"}},
            "spec": {"owner": {"group": "group:default/t"},
                     "service": {"name": "shop", "type": service_type}}}


@pytest.mark.parametrize("authored, resolved", ALIASES)
def test_srm_v1_keeps_the_authored_alias(authored, resolved):
    m = parse_srm_v1(_v1(authored))
    assert (m.type, m.authored_type) == (resolved, authored)


@pytest.mark.parametrize("authored, resolved", ALIASES)
def test_v2_keeps_the_authored_alias(authored, resolved):
    m = parse_opensrm_v2(_v2(authored))
    assert (m.type, m.authored_type) == (resolved, authored)


@pytest.mark.parametrize("authored, resolved", ALIASES)
def test_legacy_keeps_the_authored_alias(tmp_path, authored, resolved):
    p = tmp_path / "svc.yaml"
    p.write_text(yaml.safe_dump({"service": {"name": "shop", "team": "t",
                                             "tier": "critical", "type": authored}}))
    m = load_manifest(p, suppress_deprecation_warning=True)
    assert (m.type, m.authored_type) == (resolved, authored)


def test_the_spec_extension_example_is_present_and_unchanged():
    assert X_TYPE_EXAMPLE.is_file(), "the opensrm sibling is missing"
    m = load_manifest(X_TYPE_EXAMPLE)
    declared = yaml.safe_load(X_TYPE_EXAMPLE.read_text())["spec"]["service"]["type"]
    assert m.authored_type == m.type == declared


def test_authored_type_survives_dataclasses_replace():
    m = ReliabilityManifest(name="s", team="t", tier="critical", type="web")
    assert dataclasses.replace(m, tier="high").authored_type == "web"


def test_explicit_authored_type_is_not_overwritten():
    m = ReliabilityManifest(name="s", team="t", tier="critical", type="x-web", authored_type="web")
    assert (m.type, m.authored_type) == ("x-web", "web")
```

- [ ] **Step 2: Run, expect FAIL** — `uv run pytest -q tests/test_manifest_authored_type.py` → `TypeError: unexpected keyword argument 'authored_type'` / `AttributeError`.

- [ ] **Step 3: Implement.** Add the field after `raw_data`, with a comment citing opensrm-z3ab and opensrm-wo62.1:

```python
    # The service type exactly as authored, before alias resolution
    # (opensrm-z3ab, opensrm-wo62.1). `type` is resolved for comparisons;
    # this is what `${type}` substitutes into user-authored PromQL, where
    # `web` -> `x-web` would select zero series. Declared, not set as a bare
    # attribute, so dataclasses.replace() keeps it. None = "derive from type".
    authored_type: str | None = None
```

In `__post_init__`, as the first statement (before the alias rewrite at ~line 1025):

```python
        if self.authored_type is None:
            self.authored_type = self.type
```

In `parser/v2.py`, keep the raw value before resolution (`authored_type = service_type` immediately before `resolved_type = resolve_service_type(service_type)`) and pass `authored_type=authored_type` to `ReliabilityManifest(...)`.

- [ ] **Step 4: Run the file, the full suite, ruff.** — **Step 5: Commit** — `feat(manifest): ReliabilityManifest.authored_type keeps the authored service type (opensrm-wo62.1)`.

### Task 2: srm/v1 reads a top-level SLO `query:`

**Files:**
- Modify: `nthlayer-common/src/nthlayer_common/manifest/parser/v1.py` (`_extract_indicator_query` :196-213; callers `_infer_slo_type` :241 and `_parse_slos` :343)
- Modify: `nthlayer-common/src/nthlayer_common/manifest/v1_compat.py` (`_v1_slo_to_openslo` :352-353)
- Modify: `nthlayer-common/src/nthlayer_common/manifest/parser/_shared.py` (new home of the reader)
- Test: `nthlayer-common/tests/test_srm_v1_top_level_query.py` (create)

**Interfaces:**
- Produces: `parser._shared.srm_v1_indicator_query(name: str, config: dict) -> str | None` (replaces `parser.v1._extract_indicator_query`; lives in `_shared.py` because `parser/v1.py:52` imports `v1_compat`, so `v1_compat` importing `parser.v1` would cycle; package-internal, not re-exported). Raises `ValueError` when both spellings are present and differ; `_parse_slos` wraps it as `OpenSRMParseError`, `convert_v1_to_v2` lets the `ValueError` through (its documented error type).

- [ ] **Step 1: Write the failing tests.** The fixture SLO block is copied verbatim from `nthlayer-generate/examples/uat/payment-api.reliability.yaml` (lines 17-41 at generate commit ebf484c) — put that provenance in the module docstring.

```python
"""srm/v1 SLOs may declare their PromQL as a top-level `query:` (opensrm-wo62.1).

opensrm-0i5h dropped the top-level read as "not in any spec or example". It is
in one: nthlayer-generate examples/uat/payment-api.reliability.yaml (lines 17-41
at generate ebf484c), copied verbatim below, which generate's own parser read.
"""
import pytest
import yaml

from nthlayer_common.manifest.parser.v1 import OpenSRMParseError, parse_srm_v1
from nthlayer_common.manifest.parser.v2 import parse_opensrm_v2
from nthlayer_common.manifest.v1_compat import convert_v1_to_v2

UAT_SLOS = yaml.safe_load('''
availability:
  target: 99.9
  window: 30d
  type: availability
  description: "99.9% availability over 30 days"
  query: |
    sum(rate(http_requests_total{service="payment-api",status=~"[1234].."}[5m]))
    /
    sum(rate(http_requests_total{service="payment-api"}[5m]))

latency-p95:
  target: 99.0
  window: 30d
  type: latency
  percentile: p95
  unit: ms
  description: "99% of requests under 500ms at p95"
  query: |
    histogram_quantile(0.95,
      sum(rate(http_request_duration_seconds_bucket{service="payment-api"}[5m])) by (le)
    )
''')


def _doc(slos: dict) -> dict:
    return {"apiVersion": "srm/v1", "kind": "ServiceReliabilityManifest",
            "metadata": {"name": "payment-api", "team": "payments-team", "tier": "critical"},
            "spec": {"type": "api", "slos": slos}}


def test_top_level_query_is_the_indicator_query():
    m = parse_srm_v1(_doc(UAT_SLOS))
    assert {s.name: s.indicator_query for s in m.slos} == \
           {n: c["query"] for n, c in UAT_SLOS.items()}


def test_nested_form_is_unchanged():
    slo = {"target": 99.9, "indicator": {"query": UAT_SLOS["availability"]["query"]}}
    (s,) = parse_srm_v1(_doc({"availability": slo})).slos
    assert s.indicator_query == UAT_SLOS["availability"]["query"]


def test_both_spellings_agreeing_load():
    q = UAT_SLOS["availability"]["query"]
    (s,) = parse_srm_v1(_doc({"availability": {"target": 99.9, "query": q,
                                                "indicator": {"query": q}}})).slos
    assert s.indicator_query == q


def test_both_spellings_disagreeing_is_an_error_naming_the_slo():
    slo = {"target": 99.9, "query": "a", "indicator": {"query": "b"}}
    with pytest.raises(OpenSRMParseError, match="availability"):
        parse_srm_v1(_doc({"availability": slo}))


def test_top_level_query_drives_type_inference():
    # No type, no name hint: only the query can type it (parser/v1.py:241).
    slo = {"target": 99.0, "query": UAT_SLOS["latency-p95"]["query"]}
    (s,) = parse_srm_v1(_doc({"checkout-p95": slo})).slos
    assert s.slo_type == "latency"


def test_migration_carries_a_top_level_query():
    v2 = convert_v1_to_v2(_doc(UAT_SLOS))
    m = parse_opensrm_v2(v2)
    assert {s.name.removeprefix("payment-api-"): s.indicator_query for s in m.slos} == \
           {n: c["query"] for n, c in UAT_SLOS.items()}
```

Before running, check how `convert_v1_to_v2` names the OpenSLO documents (`v1_compat.py` `_v1_slo_to_openslo`) and adjust only the key mapping in the last test to that naming — never the expected queries.

- [ ] **Step 2: Run, expect the top-level, inference and migration tests to FAIL.**

- [ ] **Step 3: Implement.** Replace `parser/v1.py`'s `_extract_indicator_query` with, in `parser/_shared.py`:

```python
def srm_v1_indicator_query(name: str, config: dict[str, Any]) -> str | None:
    """The SLO's PromQL: ``indicator.query`` or a top-level ``query``.

    Both spellings are srm/v1: the nested form is the documented one, the
    top-level form is what nthlayer-generate's parser read and its UAT example
    (examples/uat/payment-api.reliability.yaml) uses. opensrm-0i5h dropped the
    top-level read believing no example used it (opensrm-wo62.1 restored it).
    Declaring both with different values is an error rather than a precedence
    rule: either choice would silently discard a query the author wrote.
    Raises ValueError.
    """
    indicator = config.get("indicator")
    nested = indicator.get("query") if isinstance(indicator, dict) else None
    nested = nested if isinstance(nested, str) and nested else None
    top = config.get("query")
    top = top if isinstance(top, str) and top else None
    if nested is not None and top is not None and nested != top:
        raise ValueError(
            f"SLO '{name}' declares both indicator.query and a top-level query, "
            f"and they differ; keep one"
        )
    return nested if nested is not None else top
```

`_infer_slo_type(name, config, ...)` and `_parse_slos` call it with the SLO name; `_parse_slos` wraps `ValueError` in `OpenSRMParseError` (its existing pattern at :330-334). In `v1_compat._v1_slo_to_openslo`, replace the two-line nested read with `query = srm_v1_indicator_query(slo_name, v1_slo)`; both modules import it from `parser/_shared.py`. Update the existing `test_v1_to_v2_migration.py` only if a test there asserted the drop.

- [ ] **Step 4: Run, full suite, ruff.** — **Step 5: Commit** — `feat(manifest): srm/v1 reads an SLO's top-level query (opensrm-wo62.1)`.

### Task 3: Documentation

**Files:**
- Modify: `nthlayer-common/docs/architecture.md` (manifest section, near the judgment-threshold bullet ~line 340)
- Modify: `nthlayer-common/README.md` only if it documents the manifest model fields (grep `ReliabilityManifest`).

- [ ] **Step 1:** Add two bullets: "`ReliabilityManifest.authored_type` — the service type as written, before alias resolution (opensrm-z3ab invariant; set by every parser). Use it for `${type}` substitution into user PromQL; compare against `type`." and "srm/v1 SLO PromQL: `indicator.query` or a top-level `query` (both are srm/v1; differing values are a parse error); `convert_v1_to_v2` carries either (opensrm-wo62.1)."
- [ ] **Step 2: Commit** — `docs(manifest): authored_type and srm/v1 top-level query (opensrm-wo62.1)`.

**Checkpoint A (common):** R5-gate nthlayer-common (base = branch point, head = Task 3). Push, open the PR, hold. On Rob's approval: merge, squash the release PR (5.4.0), verify on PyPI (`uv pip install nthlayer-common==5.4.0` into a scratch venv; `python -c "from nthlayer_common.manifest import ReliabilityManifest as R; print(R(name='s',team='t',tier='low',type='web').authored_type)"` → `web`), sync the local checkout.

### Task 4: Floor bumps to 5.4.0 in generate, core, bench, workers, override-adapter

**Files (each repo):** `pyproject.toml` (floor `nthlayer-common>=5.4.0,<6.0.0`; replace the newest `WHY` line with `WHY 5.4.0 (opensrm-wo62.1): <one sentence: what this repo uses, or "floor rule 10: the floor is the installed sibling">`, keeping the "bump on every minor" sentence), `uv.lock` (relock).

- [ ] **Step 1:** In each repo, branch `chore/wo62-1-common-5.4`, edit the floor, `uv lock`, run the dependency guard (`tests/test_dependency_declarations.py` where present) and the full suite, ruff.
- [ ] **Step 2:** Commit `deps: require nthlayer-common 5.4.0 (opensrm-wo62.1)` in each.

**Checkpoint A (consumers):** R5-gate the five floor commits as one batched gate (same shape as opensrm-pnmv Task 10). Push, PRs held; on Rob's approval merge and squash the five patch release PRs; verify each on PyPI with a clean co-install of all six packages; run `.claude/bin/eco-doctor.sh --fetch` — no range finding.

- Committed: common 5.4.0 (3 commits + release); five `deps:` commits + releases.
- Tests green: common full suite; each consumer's full suite and dependency guard.
- Memory: update `project_release_pipeline.md` only if the release exposed something new; add nothing otherwise.
- **Stop and ask Rob:** "common 5.4.0 is on PyPI and all five floors are 5.4.0. Start Checkpoint B (generate goldens)?"

---

## Checkpoint B — goldens on unchanged generate (worktree `nthlayer-generate-wo62`, branch `feat/wo62-1-common-manifest`, from main after Task 4)

No `src/` change in this checkpoint. Every golden is written from the code as it is.

### Task 5: Golden harness, corpus and load records

**Files:**
- Create: `nthlayer-generate/tests/golden/__init__.py`, `tests/golden/_corpus.py`, `tests/golden/_golden.py`, `tests/golden/test_golden_harness.py`, `tests/golden/test_golden_load.py`
- Create: `nthlayer-generate/tests/golden/data/` (written by update mode)

**Interfaces:**
- Produces: `_corpus.SRM_V1`, `_corpus.LEGACY`, `_corpus.NON_MANIFESTS` (`tuple[Path, ...]`), `_corpus.V2` (spec examples whose `kind` is `ServiceManifest`), `_corpus.manifest_id(path) -> str` (e.g. `opensrm__ai-gate`); `_golden.check(cell: str, manifest_id: str, value: object) -> None` (compares JSON-normalised `value` with `data/<cell>/<manifest_id>.json`; in update mode writes it and fails the test); `_golden.MASK: frozenset[str]` (dict keys whose values are replaced by `"<masked>"`).

- [ ] **Step 1: Corpus.** Explicit lists (spec §6.1): 7 srm/v1, 20 legacy, 12 non-manifests; V2 from `OPENSRM / "spec" / "v2" / "examples"` recursively, filtered on `kind == "ServiceManifest"`.

```python
# parents: [0]=golden/ [1]=tests/ [2]=nthlayer-generate/ [3]=<ecosystem>/
REPO = Path(__file__).resolve().parents[2]
OPENSRM = Path(__file__).resolve().parents[3] / "opensrm"
EX = REPO / "examples"
SRM_V1 = tuple(EX / p for p in (
    "opensrm/ai-gate.reliability.yaml", "opensrm/api-basic.reliability.yaml",
    "opensrm/api-critical.reliability.yaml", "opensrm/batch.reliability.yaml",
    "opensrm/stream.reliability.yaml", "opensrm/worker.reliability.yaml",
    "uat/payment-api.reliability.yaml"))
LEGACY = tuple(sorted((EX / "services").glob("*.yaml"))) + tuple(EX / "uat" / n for n in (
    "payment-api.yaml", "payment-api-with-slas.yaml", "payment-api-partial-slas.yaml"))
NON_MANIFESTS = tuple(sorted((EX / "environments").glob("*.yaml"))
                      + sorted((EX / "services" / "environments").glob("*.yaml"))
                      + sorted((EX / "slos").glob("*.yaml")))
```

(`LEGACY` globs `examples/services/*.yaml`; the presence test below pins the count at 17 + 3 so a new file must be classified.)

- [ ] **Step 2: The harness tests** (`test_golden_harness.py`), written first and expected to pass only once `_golden.py` exists:
  - every `examples/**/*.yaml` is in exactly one of `SRM_V1`, `LEGACY`, `NON_MANIFESTS` (`examples/policies.yaml`, `examples/cicd/`, `examples/workflows/` listed as an explicit `NOT_MANIFESTS_BY_DESIGN` tuple with a one-line reason each);
  - `len(SRM_V1) == 7`, `len(LEGACY) == 20`, `len(NON_MANIFESTS) == 12`;
  - `OPENSRM.is_dir()` and `len(V2) >= 1` — an assertion, never a skip (CI checks the sibling out: `.github/workflows/ci.yml:27-37`);
  - update mode is off: `os.environ.get("NTHLAYER_UPDATE_GOLDENS") is None` — so a run that wrote goldens cannot pass;
  - every key in `MASK` occurs in at least one stored golden (`"<masked>"` present under that key) — the mask is not vacuous;
  - `data/` holds no golden whose cell or manifest id is not produced by some test (no orphans).

- [ ] **Step 3: `_golden.py`.** `normalise(value)`: dataclasses → `asdict`, enums → `.value`, `Path` → path relative to `REPO` (or `<tmp>` for tmp paths), YAML/JSON strings parsed, dicts with `MASK` keys masked, then `json.dumps(..., sort_keys=True, indent=2)`. `check()` raises `AssertionError` with a unified diff on mismatch, and on a missing golden (no skip).

- [ ] **Step 4: Load records** (`test_golden_load.py`), cell `load`, parametrised over `SRM_V1 + LEGACY + NON_MANIFESTS + V2`: call today's `nthlayer_generate.specs.loader.load_manifest(path, suppress_deprecation_warning=True)` under `warnings.catch_warnings(record=True)` with `simplefilter("always")`; record `{"ok": bool, "error": [type name, message] | None, "warnings": [[category name, message], ...], "source_format": ..., "type": ..., "slos": [[name, slo_type, target, window, bool(indicator_query)], ...], "judgment_thresholds": [...] if present, "dependencies": [[name, type, critical], ...]}`. Absolute paths in messages are normalised by `normalise()`.

- [ ] **Step 5: Write the goldens** — `NTHLAYER_UPDATE_GOLDENS=1 uv run pytest -q tests/golden` (fails by design), then `uv run pytest -q tests/golden` passes. Check the expected baseline by eye: `analytics-stream` and the 12 non-manifests fail; every V2 file fails with `service.name is required`.

- [ ] **Step 6: Commit** — `test(golden): pin manifest load records for the example corpus (opensrm-wo62.1)`.

### Task 6: Library-generator cells

**Files:** Create `nthlayer-generate/tests/golden/test_golden_generators.py`.

**Interfaces:** Consumes Task 5. Each cell is one test function parametrised over the loadable manifests of `SRM_V1 + LEGACY` (ids from the load goldens where `ok` is true — read from the corpus by loading, not hard-coded).

- [ ] **Step 1: Cells** (spec §6.2), each passing its output through `check(cell, id, value)`:
  - `recording_rules` — `create_rule_groups(build_recording_rules_from_manifest(m))` parsed;
  - `sloth` — `generate_sloth_from_manifest(m, tmp)`: the written file, or `{"error": result.error}`;
  - `alerts` — `generate_alerts_from_manifest(m, output_file=tmp/"alerts.yaml", quiet=True)`: the written file;
  - `dashboard` — `build_dashboard_from_manifest(m)`;
  - `loki` — `generate_loki_alerts_from_manifest(m, tmp)`: the ruler file;
  - `metrics` — `recommend_metrics_from_manifest(m).to_dict()`;
  - `backstage` — `generate_backstage_entity(path, tmp)`: the written JSON (`generatedAt` masked);
  - `docs` — `generate_service_docs(path, tmp, include_adr=True, include_api=True)`: `{relative path: text}` for every file written;
  - `policies` — `asdict(PolicyEngine.from_yaml(EX/"policies.yaml").evaluate(m))`;
  - `validate` — `validate_manifest(path, contract_registry=ContractRegistry.from_directory(EX/"opensrm"))` (`valid`, `errors`, `warnings`); check the real signature of `validate_manifest` in `specs/validator.py:60-100` first;
  - `pipeline` — `AlertPipeline().evaluate_service(m, simulate_burn_pct=50.0).to_dict()`;
  - `simulate` — `build_failure_models([m])`, `build_dependency_models([m])` and `run_simulation(..., num_runs=200, horizon_days=90, seed=42).to_dict()` (check `SimulationResult` has `to_dict`; `simulate/models.py:211`);
  - `topology` — `build_topology(graph, manifests=[m]).to_dict()` where `graph` is a `DependencyGraph` holding the service and one edge per declared dependency (construct it from `topology`'s own model types; it is input, not a manifest fixture).
- [ ] **Step 2: Find the mask mechanically.** Run every cell twice in one process with `time.sleep(1.1)` between; any leaf that differs must be added to `MASK` by key name, with a comment naming the cell. Expect `generatedAt` and the pipeline's time-derived fields (`slos/alerts.py:142,191,258`; `slos/pipeline.py:212`). If a differing leaf has no stable key name, stop and report it — do not mask by path wildcard.
- [ ] **Step 3: Write goldens (update mode), rerun clean, run twice more to prove stability.** — **Step 4: Commit** — `test(golden): pin every manifest-path generator over the example corpus (opensrm-wo62.1)`.

### Task 7: CLI cells

**Files:** Create `nthlayer-generate/tests/golden/test_golden_cli.py`.

- [ ] **Step 1: Cells** — exit codes and written files only, never console text (memory: feedback_test_assertions). Drive each command's Python entry (`*_command(...)` functions; for flags, `nthlayer_generate.demo.build_parser().parse_args([...])` + the handler):
  - `migrate` — `migrate_command(path, output_dir=tmp)`: exit code + the written file (none for srm/v1);
  - `validate` — `validate_command(path)` and `validate_command(path, strict=True)` exit codes; plus `--policies examples/policies.yaml`;
  - `alerts` — `alerts evaluate`, `alerts show`, `alerts test` exit codes; `evaluate --format json` writes JSON to stdout — capture via `capsys` and `json.loads` it (structure, not text);
  - `docs`, `backstage` — exit codes + written files (`generatedAt` masked);
  - `simulate` — `simulate_command(path, seed=42, num_runs=200, output_format="json")` exit code + parsed JSON;
  - `topology` — `topology_export_command(path)` exit code (2 without a provider; the load step is what is pinned);
  - `policy_handler` — `PolicyHandler().generate(ctx)` count with a minimal `OrchestratorContext` whose detector returns `examples/policies.yaml`'s rules (read `orchestration/handlers.py:455-490` for the shape).
- [ ] **Step 2: Write goldens, rerun clean.** — **Step 3: Commit** — `test(golden): pin the manifest-path CLI commands (opensrm-wo62.1)`.

### Task 8: Kill check and coverage report

- [ ] **Step 1: Kill checks** — one at a time, revert after each, record the red test: rename `ai_gate:calibration:ece` (`recording_rules/manifest_builder.py:471`) → `recording_rules` golden red; make `get_judgment_slos` return `[]` → recording-rules and docs goldens red; change `${type}` substitution to `manifest.type` in `generators/sloth.py:264` → no golden goes red (no example uses `${type}`) — that is expected and is why Task 9's z3ab test exists; note it. `git status --short` clean after.
- [ ] **Step 2: Coverage report** for Rob in the PR draft and the session handoff: the matrix (cells × manifests) with counts, the mask and its justification, the baseline failures, and the `${type}` gap.

**Checkpoint B:** no gate and no merge yet — the goldens ride the Checkpoint C branch so the switch's diff is reviewable against them (C's gate covers B's tests; base = branch point).

- Committed: Tasks 5–7 on `feat/wo62-1-common-manifest` (local; push only on Rob's word).
- Tests green: full generate suite including `tests/golden` on unchanged `src/`.
- Memory: none (session-scoped; the handoff carries the coverage report).
- **Stop and ask Rob:** "Golden coverage is <N> cells over <M> manifests (matrix attached); baseline failures and the mask are listed. Approve coverage and start Checkpoint C?"

---

## Checkpoint C — the switch (same worktree and branch)

### Task 9: Generate-owned helpers (names, service context, alerting, migrate)

**Files:**
- Create: `nthlayer-generate/src/nthlayer_generate/specs/names.py` (move `SERVICE_NAME_PATTERN`, `_SERVICE_NAME_RE`, `is_valid_service_name` and their full comment block from `specs/manifest.py:49-100`, unchanged except the stale "no opensrm/ checkout" sentence, which is deleted with a note that CI checks it out)
- Create: `nthlayer-generate/src/nthlayer_generate/specs/context.py`
- Modify: `nthlayer-generate/src/nthlayer_generate/specs/alerting.py` (add `manifest_alerting`)
- Modify: `nthlayer-generate/src/nthlayer_generate/cli/migrate.py` (private `_legacy_to_srm_v1`)
- Modify: `cli/init.py:22`, `cli/setup.py:51`, `specs/validator.py:29` (import from `specs.names`; `VALID_TIERS` from `nthlayer_common.manifest`)
- Test: `nthlayer-generate/tests/test_specs_context.py` (create); extend `tests/test_alerting_config.py`

**Interfaces:**
- Produces: `service_context_from_manifest(manifest: nthlayer_common.manifest.ReliabilityManifest) -> ServiceContext` — name, team, tier, `type`, `authored_type`, support_model, language, framework, environment, and `PagerDutyConfig(escalation_policy=ownership.pagerduty.escalation_policy_id)` when present (the mapping of `specs/manifest.py:653-686`).
- Produces: `manifest_alerting(manifest) -> AlertingConfig | None` = `parse_alerting_config(manifest.alerting)`.
- Produces: `cli.migrate._legacy_to_srm_v1(manifest) -> dict` — a port of `specs/manifest.py:839-931` for the fields the legacy parser populates (name, team, tier, resolved `type`, description, labels, annotations, slos, dependencies, ownership).

- [ ] **Step 1: Failing tests.** z3ab through common: load `examples/opensrm/api-basic.reliability.yaml` with `spec.type` rewritten to `web` into `tmp_path` (the alias from common's table), assert `service_context_from_manifest(m).authored_type == "web"` and `.type == "x-web"`; PagerDuty from `examples/opensrm/api-critical.reliability.yaml` (`escalation_policy_id: P456DEF`) → `ServiceContext.pagerduty.escalation_policy == "P456DEF"`. Alerting: a legacy example with an `Alerts` resource (find one with `grep -l "kind: Alerts" examples/services/*.yaml`; if none, take the `alerting:` block from `docs-site` and cite it) → `manifest_alerting(m).channels` equals what `parse_alerting_config` gives for that block; malformed `alerting: [1]` → `alerts evaluate` exit 1 and `generate_service_docs` success (Review Focus 6).
- [ ] **Step 2: Implement; the helpers import `ReliabilityManifest` from `nthlayer_common.manifest` only.** — **Step 3: Run, ruff, mypy (`make typecheck`).** — **Step 4: Commit** — `feat(specs): generate-owned helpers over common's manifest model (opensrm-wo62.1)`.

### Task 10: Contracts on `manifest.contracts`

**Files:**
- Modify: `nthlayer-generate/src/nthlayer_generate/specs/contracts.py`
- Test: `nthlayer-generate/tests/test_contract_validation.py`

**Interfaces:**
- Produces: `ContractRegistry.register(manifest)` stores `manifest.contracts` (skips an empty list); `get_contracts(name) -> list[ReliabilityContract]`; `promised_availability(name) -> float | None` = min `promise.availability` over the service's contracts that declare one; `has_contract(name)` unchanged in meaning. `get_contract` is removed (breaking, covered by 3.0.0).
- `validate_dependency_expectations` compares against `promised_availability`; `validate_transitive_feasibility` checks each contract with availability — message text unchanged for a single contract, `contract '<name>'` appended when there are several (spec §5.2).

- [ ] **Step 1: Failing tests** from shipped files: registry from `examples/opensrm/` → `promised_availability("payment-api") == 0.999` (`api-critical.reliability.yaml` `contract.availability`); `fraud-detector` → `0.999`. Multi-contract: `opensrm/spec/v2/examples/service-manifest-full.yaml` if it declares several contracts (check; otherwise a v2 example that does, or state that no spec example has two and build the second contract by copying the first with a different `name` and `availability`, commented as such).
- [ ] **Step 2: Implement.** — **Step 3: Run, ruff.** — **Step 4: Commit** — `feat(specs): contract registry reads common's contracts list (opensrm-wo62.1)`.

### Task 11: Judgment recording rules from `JudgmentThreshold`

**Files:**
- Modify: `nthlayer-generate/src/nthlayer_generate/recording_rules/manifest_builder.py` (`build` :31-73, `_build_judgment_slo_rules` :333-357, `_build_calibration_rules` :457, `_build_feedback_latency_rules` :499)
- Test: `nthlayer-generate/tests/test_recording_rules_judgment.py` (create)

**Interfaces:**
- Consumes: `ReliabilityManifest.get_judgment_slos()`, `get_judgment_thresholds()`, `JudgmentThreshold.bounds`, `nthlayer_common.manifest.duration_seconds`.
- Produces: `_build_judgment_threshold_rules(threshold: JudgmentThreshold) -> list[RecordingRule]`; `_build_calibration_rules(service: str, target: float)` and `_build_feedback_latency_rules(service: str, target_seconds: float | None)` (window parameters dropped — neither used it).

- [ ] **Step 1: Failing tests.**
  - ai-gate example: the judgment group's rules (record, expr, labels) equal the Checkpoint B `recording_rules` golden's judgment group exactly — read the golden file, do not restate it.
  - `opensrm/spec/v2/examples/judgment-thresholds/feedback-latency-p50-only.yaml` → `:p50/:p95/:p99` and a `:bucket` rule whose `le` and `target` are `str(duration_seconds(<the file's maximum_p50>))`.
  - `.../calibration-both-bounds.yaml` → `ai_gate:calibration:ece` with `target == str(<the file's maximum_expected_calibration_error>)` plus the three bucket rules.
  - `.../all-five-types.yaml` (Brier-only calibration, p50+p90 feedback) → no `ai_gate:calibration:*` record; feedback rules present; segments/stability/audit_backlog emit nothing and raise nothing (wo62.2).
  - A v2 judgment SLO whose name is not its type: take `opensrm/spec/v2/examples/judgment-slos/01-reversal-rate.yaml` (its SLO is named `triage-agent-reversal-rate`, `judgment_type: reversal_rate`), assert the name differs from the type, expect `ai_gate:reversal_rate:ratio`.
- [ ] **Step 2: Implement.** `build()` collects judgment rules when `is_ai_gate()` from `get_judgment_slos()` (dispatch on `slo.judgment_type`) then `get_judgment_thresholds()`; the group is added if it has rules. Threshold rules per spec §5.3. Keep every record name, expr and label byte-identical.
- [ ] **Step 3: Run, ruff, mypy.** — **Step 4: Commit** — `feat(recording-rules): judgment threshold rules from common's JudgmentThreshold (opensrm-wo62.1)`.

### Task 12: Switch every consumer and delete the stack

**Files:**
- Modify (imports → `nthlayer_common.manifest`): `cli/{migrate,topology,docs,backstage,alerts,simulate,validate}.py`, `orchestration/handlers.py:468`, `generators/{sloth,alerts,backstage,docs}.py`, `dashboards/manifest_builder.py`, `loki/generator.py`, `recording_rules/manifest_builder.py`, `metrics/recommender.py`, `topology/enrichment.py`, `simulate/graph.py`, `policies/{rules,engine}.py`, `slos/pipeline.py`, `specs/{helpers,contracts,validator,templates}.py`, the four package `__init__.py` docstrings that mention the "new API".
- Modify: `dashboards/manifest_builder.py:78` and `metrics/recommender.py:39` → `service_context_from_manifest`; `slos/pipeline.py:117`, `generators/alerts.py:128`, `cli/alerts.py:75` → `manifest_alerting(manifest)`; `generators/sloth.py:264` → `manifest.authored_type` (now common's; drop the `or manifest.type` comment's premise only if mypy agrees the field is `str` after construction — it is typed `str | None`, so keep the fallback and its comment); `cli/migrate.py:92` → `!= SourceFormat.LEGACY`, `:101` → `_legacy_to_srm_v1`.
- Modify: `specs/validator.py:107-118` → manifest path when `is_srm_v1_format(data) or is_opensrm_v2_format(data)` (from `nthlayer_common.manifest.parser.v1` / `.v2`), and filter common's `LegacyFormatWarning`.
- Modify: `specs/__init__.py` — drop the manifest re-exports; keep the legacy API; docstring points to `nthlayer_common.manifest`.
- Delete: `specs/manifest.py`, `specs/loader.py`, `specs/opensrm_parser.py`.

- [ ] **Step 1:** `grep -rnE "specs\.(manifest|loader|opensrm_parser)|from nthlayer_generate\.specs import (load_manifest|ReliabilityManifest|SLODefinition|ManifestLoadError)" src` must print nothing at the end of this task.
- [ ] **Step 2: Tests first for the two behaviour rulings:** `migrate_command` on `opensrm/spec/v2/examples/minimal.yaml` → exit 0, nothing written (Review Focus 5); `validate_manifest` on the same file → takes the manifest path (`resource_count` from `manifest.slos` + dependencies), not `parse_service_file`.
- [ ] **Step 3: Run the full suite.** Failures in tests that import the retired modules are Task 13's; any other failure is a real regression — fix `src`, never the golden.
- [ ] **Step 4: Commit** — message:

```
feat!: consume nthlayer-common's manifest model; retire generate's own (opensrm-wo62.1)

BREAKING CHANGE: nthlayer_generate.specs no longer exports load_manifest,
ReliabilityManifest, SLODefinition or ManifestLoadError, and the modules
specs.manifest, specs.loader and specs.opensrm_parser are removed. Import
them from nthlayer_common.manifest. Every *_from_manifest function takes
nthlayer_common's ReliabilityManifest. ContractRegistry.get_contract is
replaced by get_contracts / promised_availability.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
```

### Task 13: Migrate the test suite

**Files:** the 21 files from `grep -rlE "ReliabilityManifest|SLODefinition|load_manifest|specs\.manifest|specs\.loader|opensrm_parser" tests`; delete `tests/uat_opensrm.py` (spec Ruling).

- [ ] **Step 1:** For each file: import from `nthlayer_common.manifest`; hand-built `SLODefinition(...)` gains `slo_type` taken from the example or spec shape the test claims to model (name it in a comment), never from what makes the test pass; `contract=Contract(...)` becomes `contracts=[...]` built via `nthlayer_common.manifest.v1_compat.convert_v1_contract` from the srm/v1 contract block the test models; calibration/feedback_latency "SLOs" become `JudgmentThreshold`s via an srm/v1 manifest dict parsed with `parse_srm_v1`.
- [ ] **Step 2:** Tests of the retired stack itself (`test_opensrm.py` parser/loader units, `to_dict`, `as_resources`, `to_service_context`, `is_manifest_file`) are deleted where common's own suite covers the behaviour; list each deleted test and the common test that covers it in the commit body. Keep and port the z3ab tests (`tests/test_service_type_agreement.py:296-340`) to common's model + `service_context_from_manifest`.
- [ ] **Step 3:** Full suite, ruff, mypy. — **Step 4: Commit** — `test: move the suite onto common's manifest model (opensrm-wo62.1)`.

### Task 14: Goldens after the switch — the list for Rob

- [ ] **Step 1:** Extend the cells in Tasks 5–7 to `V2` manifests that load (new goldens).
- [ ] **Step 2:** `NTHLAYER_UPDATE_GOLDENS=1 uv run pytest -q tests/golden`, then `git diff --stat tests/golden/data` and `git diff tests/golden/data`.
- [ ] **Step 3: Write the list** (PR body draft + handoff): one row per changed golden — cell, manifest, what changed, and the spec §6.3 prediction it matches (G1–G8) or **UNPREDICTED**; then every manifest whose load record went ok → fail (**newly failing**, expected none); then new V2 goldens summarised per cell. Do not commit the regenerated goldens until Rob approves.
- [ ] **Step 4 (after approval): Commit** — `test(golden): re-pin goldens on common's manifest model (opensrm-wo62.1)` with the approved list in the body.

### Task 15: Docs

**Files:** `nthlayer-generate/README.md`, `docs-site/` pages that show `from nthlayer_generate.specs import load_manifest` or describe the specs API (`grep -rn "specs import\|load_manifest\|ReliabilityManifest" README.md docs-site`), `CLAUDE.md`/`AGENTS.md` lines describing `specs/manifest.py`/`loader.py`/`opensrm_parser.py`.

- [ ] **Step 1:** Point them at `nthlayer_common.manifest`; state that v2 manifests are accepted; one upgrading paragraph for 3.0.0 (the BREAKING CHANGE text).
- [ ] **Step 2: Commit** — `docs: generate reads manifests through nthlayer-common (opensrm-wo62.1)`.

**Checkpoint C:** Rob approves the Task 14 list → R5-gate generate (base = branch point, so Checkpoint B's goldens are in scope; the provenance pass's kill checks include Task 8's three plus: drop the threshold branch in Task 11, revert Task 12's `source_format` ruling). Push, PR held; on Rob's approval merge, squash the release PR (3.0.0), verify on PyPI with a clean co-install of all six packages, sync local.

- Committed: Tasks 9–15 + goldens; release 3.0.0.
- Tests green: generate full suite (incl. `tests/golden`), ruff, mypy, dependency guard.
- Memory: add `project_generate_on_common.md` (generate consumes common's manifest model from 3.0.0; goldens live in `tests/golden`, update only via `NTHLAYER_UPDATE_GOLDENS=1` and a listed approval) and its MEMORY.md line.
- **Stop and ask Rob:** "generate 3.0.0 is on PyPI on common's manifest model. File the follow-up beads and close wo62.1 (Checkpoint D)?"

---

## Checkpoint D — follow-ups and close (opensrm, front door)

### Task 16: File the follow-up beads

- [ ] **Step 1:** `cd opensrm` and `bd create` each, `--parent opensrm-wo62` where it belongs to the epic, with the deferred work named in the description:
  1. Route the legacy `parse_service_file`/`ServiceContext` CLI (12 commands) and plan/apply through common (decision 1).
  2. Rewrite `examples/opensrm/ai-gate.reliability.yaml` judgment targets in the 0–100 convention or migrate it to v2.
  3. common: `TargetConventionWarning` false positives on `error_rate` targets.
  4. Add to wo62.2's notes: Brier-only calibration, p90 feedback rules (spec §5.3).
  5. Add to wo62.3's notes: `ai_gate_*` source metrics vs `THRESHOLD_SERIES` `gen_ai_*`; `target` label units differ srm/v1 vs v2.
  6. `cli/migrate.py:169-171` dead alias branch.
  7. Anything UNPREDICTED from Task 14 that Rob deferred.
- [ ] **Step 2:** Tag each with the same phase as wo62.1 (memory: feedback_scope_down_beads).

### Task 17: eco-doctor, close

- [ ] **Step 1:** `.claude/bin/eco-doctor.sh --fetch` — no range finding.
- [ ] **Step 2:** `bd close opensrm-wo62.1` with the release versions (common 5.4.0, generate 3.0.0) and the follow-up bead ids.
- [ ] **Step 3:** Merge the front-door docs PR holding this spec and plan (`docs/wo62-1-design`) on Rob's approval.
- [ ] **Step 4:** `/handoff`.

- Committed: beads; front-door docs merged.
- Tests green: n/a (eco-doctor clean).
- Memory: none beyond Checkpoint C's entry.
- **Stop and ask Rob:** "wo62.1 closed; wo62.2 is unblocked. Start it?"
