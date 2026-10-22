# opensrm/v1 reject-and-migrate Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** NthLayer rejects `apiVersion: opensrm/v1` with an actionable error and `nthlayer migrate-manifest` converts it to `opensrm.nthlayer.io/v2`, reporting every field with no v2 home instead of dropping it.

**Architecture:** A pure converter `nthlayer_common.manifest.opensrm_v1.convert_opensrm_v1_to_v2` returns `MigrationResult(manifest, unmapped)`; `load_manifest` rejects `opensrm/v1` before format dispatch; common's v2 parser learns `resource:` dependency refs; nthlayer-generate's `migrate-manifest` dispatches on apiVersion and refuses lossy conversions unless `--allow-lossy`.

**Tech Stack:** Python 3.11+, uv, pytest, ruff, jsonschema (common dev extra), release-please.

**Spec:** `nthlayer/docs/superpowers/specs/2026-10-22-pnmv-opensrm-v1-migration-design.md` (approved; Revision 1 included). Read it before any task.

## Global Constraints

- Worktrees MUST be siblings: `.claude/bin/eco-worktree.sh <repo> pnmv`, giving `<ecosystem>/<repo>-pnmv`. Never `claude --worktree` or agent `isolation: worktree` on common/generate/core/workers/bench.
- Shared repo first: Checkpoint B (nthlayer-common) is gated, merged and released (5.3.0) before Checkpoint C starts.
- Never merge before the R5 gate. Ask Rob before every push, merge and release.
- Commit format: `<type>(<scope>): <description> (opensrm-pnmv)` plus the trailer `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`. New behaviour in unshipped code is `feat`, never `fix`.
- Run `uv run ruff check src/ tests/` and check its exit code directly — never pipe it. Never chain a command after a `sed`/edit with `&&` without checking it succeeded.
- v1 targets in `opensrm/v1` are 0–1 ratios. The converter never multiplies by 100 (that is the parser's job when it reads v2).
- Never invent a target. The only defaulted value is calibration `bins: 10` (same as the srm/v1 lift's `_SRM_V1_CALIBRATION_BINS`), and it is always reported.
- Fixtures come from `opensrm/examples/*.yaml` and `opensrm/spec/v1/schema.json` via the sibling path `Path(__file__).resolve().parents[2] / "opensrm"`, with an assertion-style presence test (no `skipif`). Expected unmapped lists are derived from the example's keys and the spec's §4 table, never from running the converter.
- After merging any PR: `gh pr merge N --merge --body ""` (an empty body keeps release-please from listing the change twice). Squash release PRs.

## Review Focus

1. A service whose name contains a type-hint word (`error-tracker`, `latency-api`): common's OpenSLO parser infers `slo_type` from the SLO name, so `error-tracker-availability` would be typed `error_rate`. Expected: the converter raises `ValueError` naming the SLO, rather than emitting a document that parses as the wrong type. Test in Task 4.
2. A non-`ai-gate` manifest with `slos.judgment.calibration`: v2 rejects `judgment_threshold` unless the service type is `ai-gate`. Expected: the whole judgment block is reported unmapped and the output parses. Test in Task 5.
3. `metadata.team` and `ownership.team` disagree, or an ownership annotation collides with an existing `metadata.annotations` key with a different value. Expected: `ValueError` naming both values. Tests in Tasks 3 and 6.
4. `--service-type` (the `service_type` argument) supplied for a manifest that already declares a different `spec.type`. Expected: `ValueError`; the same type is accepted. Test in Task 3.
5. A v1 error-rate SLO with a 7d window. Expected: OpenSLO `timeWindow` 7d (the parser would otherwise default to 30d) and target 0.999 from 0.001. Test in Task 4.

---

## Checkpoint A — front door (nthlayer, branch `docs/pnmv-opensrm-v1`)

### Task 1: Decision document

**Files:**
- Create: `nthlayer/docs/superpowers/decisions/opensrm-v1-support.md`
- Modify: `nthlayer/docs/superpowers/decisions/README.md` (the "Current decisions" table: add a row)

**Interfaces:** Produces the doc path cited by code comments in Tasks 3 and 7: `See docs/superpowers/decisions/opensrm-v1-support.md`.

- [ ] **Step 1: Write the decision doc** with the README's required headings:

```markdown
# Decision: opensrm/v1 is migrate-only; srm/v1 is NthLayer's v1 dialect

**Status:** Active.
**Date decided:** 2026-10-22 (opensrm-pnmv).
**Context:** `apiVersion: opensrm/v1` — the published OpenSRM v1 schema
(`opensrm/spec/v1/schema.json`) and every example in `opensrm/examples/` —
fell through `load_manifest` to the legacy parser and failed with
"service.name is required". NthLayer's v1 parser reads `srm/v1`, which differs
from the published schema in nearly every section: judgment SLO nesting,
contract judgment keys, dependency keys, instrumentation, deployment gate keys,
`feedback_latency` bounds, and target units (0–1 ratios vs 0–100).

## Decision

- NthLayer loads two formats: `opensrm.nthlayer.io/v2` (the target) and
  `srm/v1` (NthLayer's own v1 dialect, kept for existing manifests).
- `opensrm/v1` is rejected by `load_manifest` with an error that names the
  supported formats and the migrate command.
- `nthlayer migrate-manifest` converts `opensrm/v1` to v2 following
  `opensrm/spec/v2/AUTHORING.md` §7. Fields with no v2 home are listed; the
  conversion refuses unless `--allow-lossy` is given.

## Canonical alternative (rejected)

A faithful `opensrm/v1` parser. Rejected: it would be a second v1 dialect,
disagreeing with `srm/v1` on units and keys, for a format v2 already
supersedes and that nothing in the ecosystem produces except the spec's own
examples.

## What's routed to no-ops

Unmapped in the conversion (reported, never dropped): v1 judgment SLOs
(`reversal_rate`, `high_confidence_failure` — AUTHORING §7.7 step 8, and
opensrm-a742); throughput SLOs (a rate, not a ratio); SLO types common's
parser cannot type (opensrm-47tt) and maximum-only SLOs; `notifications`,
`deployment`, `observability`, dependency `critical` and `manifest`, and the
other rows the spec's §4 table marks unmapped.

## When the decision unwinds

When opensrm-a742 lands (a v2 judgment-SLO shape both the schema and the parser
accept), v1 judgment SLOs can be converted: move `reversal_rate` and
`high_confidence_failure` from the unmapped table to converted in
`nthlayer_common/manifest/opensrm_v1.py`. When opensrm-47tt lands, the same for
`success_rate`, `processing_time` and `lag`.

## Cross-references

- Spec: `docs/superpowers/specs/2026-10-22-pnmv-opensrm-v1-migration-design.md`
- Code: `nthlayer-common/src/nthlayer_common/manifest/opensrm_v1.py`,
  `parser/loader.py`; `nthlayer-generate/src/nthlayer_generate/cli/migrate_manifest.py`
- Spec map: `opensrm/spec/v2/AUTHORING.md` §7
- Beads: opensrm-pnmv, opensrm-a742, opensrm-47tt
```

- [ ] **Step 2: Add the README row** to the "Current decisions" table:
`| opensrm-v1-support.md | Active | opensrm/v1 is migrate-only; srm/v1 is NthLayer's v1 dialect |`

- [ ] **Step 3: Commit**

```bash
git add docs/superpowers/decisions/opensrm-v1-support.md docs/superpowers/decisions/README.md
git commit -m "docs: opensrm/v1 is migrate-only (opensrm-pnmv)"
```

**Checkpoint A:** push the docs branch and open the PR held (spec, plan, decision doc); merge it with Checkpoint C.

---

## Checkpoint B — nthlayer-common 5.3.0 (worktree `nthlayer-common-pnmv`, branch `feat/pnmv-opensrm-v1`)

### Task 2: The v2 parser accepts `resource:` dependency refs

**Files:**
- Modify: `nthlayer-common/src/nthlayer_common/manifest/parser/v2.py` (`_resolve_backstage_ref` ~line 355; the dependency loop ~line 889)
- Test: `nthlayer-common/tests/test_v2_dependency_refs.py` (create)

**Interfaces:**
- Produces: `_resolve_backstage_ref(ref: str, expected_kind: str | tuple[str, ...]) -> str` (a tuple accepts any listed kind); dependencies accept `component:` and `resource:`.

- [ ] **Step 1: Write the failing tests**

```python
"""spec.dependencies[].service accepts resource: refs (opensrm-pnmv).

The v2 spec's own migration reference (opensrm/spec/v2/examples/migration/
api-full-v2.yaml) declares databases and caches as resource: entities, and
spec/v2/schema.json's EntityRef allows any kind.
"""
import pytest

from nthlayer_common.manifest.parser.v2 import OpenSRMV2ParseError, parse_opensrm_v2


def _manifest(service_ref: str) -> dict:
    return {
        "apiVersion": "opensrm.nthlayer.io/v2",
        "kind": "ServiceManifest",
        "metadata": {"name": "payment-api", "labels": {"tier": "critical"}},
        "spec": {
            "owner": {"group": "group:default/payments"},
            "service": {"name": "payment-api", "type": "api"},
            "dependencies": [{"service": service_ref, "expected_availability": 0.9995}],
        },
    }


@pytest.mark.parametrize("ref, name", [
    ("resource:default/postgresql", "postgresql"),
    ("component:default/user-service", "user-service"),
    ("component:external/stripe-api", "stripe-api"),
])
def test_dependency_accepts_component_and_resource_refs(ref, name):
    (dep,) = parse_opensrm_v2(_manifest(ref)).dependencies
    assert dep.name == name


@pytest.mark.parametrize("ref", ["group:default/payments", "user:default/alice", "system:default/x"])
def test_dependency_rejects_other_kinds(ref):
    with pytest.raises(OpenSRMV2ParseError, match="reference"):
        parse_opensrm_v2(_manifest(ref))


def test_owner_escalation_still_requires_a_group_ref():
    m = _manifest("component:default/user-service")
    m["spec"]["owner"]["escalation"] = "resource:default/pager"
    with pytest.raises(OpenSRMV2ParseError):
        parse_opensrm_v2(m)
```

- [ ] **Step 2: Run, expect the resource case to FAIL** — `uv run pytest -q tests/test_v2_dependency_refs.py` → `Expected component reference, got 'resource'`.

- [ ] **Step 3: Implement.** In `_resolve_backstage_ref`, accept a tuple:

```python
def _resolve_backstage_ref(ref: str, expected_kind: str | tuple[str, ...]) -> str:
    """Extract the name from a Backstage entity reference.

    Format: "kind:namespace/name" or "kind:name" (default namespace).
    *expected_kind* is one kind or a tuple of accepted kinds.
    Raises OpenSRMV2ParseError on invalid format.
    """
    kinds = (expected_kind,) if isinstance(expected_kind, str) else expected_kind
    if ":" not in ref:
        raise OpenSRMV2ParseError(
            f"Invalid Backstage entity reference: '{ref}'. "
            f"Expected format: '{kinds[0]}:namespace/name'"
        )

    kind, rest = ref.split(":", 1)
    if kind not in kinds:
        raise OpenSRMV2ParseError(
            f"Expected {' or '.join(kinds)} reference, got '{kind}' in '{ref}'"
        )
```

(keep the rest of the function unchanged), and in the dependency loop:

```python
        # A dependency is a component (a service) or a resource (a database,
        # cache or queue) — the spec's migration reference uses both
        # (opensrm-pnmv).
        name = _resolve_backstage_ref(service_ref, ("component", "resource"))
```

- [ ] **Step 4: Run the new tests, then the full suite** — `uv run pytest -q` (currently 1827 passed, 7 xfailed) and ruff.

- [ ] **Step 5: Commit** — `feat(manifest): v2 dependencies accept resource: entity refs (opensrm-pnmv)`.

### Task 3: `opensrm_v1` module — envelope, metadata, owner, service type

**Files:**
- Create: `nthlayer-common/src/nthlayer_common/manifest/opensrm_v1.py`
- Test: `nthlayer-common/tests/test_opensrm_v1_envelope.py` (create)

**Interfaces:**
- Consumes: `resolve_service_type`, `valid_service_types_phrase` (`nthlayer_common.manifest.models`); `VALID_TIERS` (`nthlayer_common.tiers`).
- Produces (all in `nthlayer_common.manifest.opensrm_v1`):
  - `OPENSRM_V1_API_VERSION = "opensrm/v1"`
  - `is_opensrm_v1_format(data: object) -> bool`
  - `@dataclass(frozen=True) UnmappedField(path: str, reason: str)`
  - `@dataclass(frozen=True) MigrationResult(manifest: dict[str, Any], unmapped: tuple[UnmappedField, ...])`
  - `convert_opensrm_v1_to_v2(data: dict[str, Any], *, service_type: str | None = None) -> MigrationResult`
  - `OPENSRM_V1_REJECTION: str` — a `str.format` template with `{path}` (used by Task 7)
  - module-private `_SECTIONS: dict[str, tuple[frozenset[str], dict[str, str]]]` — per v1 schema definition, (converted keys, {unmapped key: reason}); Tasks 4–6 add entries and Task 8 tests it against the schema.
  - module-private `_Ctx` carrying `service`, `unmapped: list[UnmappedField]`, `annotations: dict[str, str]`.

- [ ] **Step 1: Write the failing tests**

```python
"""opensrm/v1 → v2: envelope, metadata, owner, service type (opensrm-pnmv).

Shapes follow opensrm/spec/v1/schema.json (Metadata: name/team/tier required;
name ^[a-z0-9-]+$; tier critical|high|standard|low) and AUTHORING.md §7.1-7.2.
"""
import pytest

from nthlayer_common.manifest.opensrm_v1 import (
    MigrationResult,
    UnmappedField,
    convert_opensrm_v1_to_v2,
    is_opensrm_v1_format,
)


def _v1(**spec) -> dict:
    return {
        "apiVersion": "opensrm/v1",
        "kind": "ServiceReliabilityManifest",
        "metadata": {"name": "payment-api", "team": "payments", "tier": "critical",
                     "description": "Handles payments"},
        "spec": {"type": "api", **spec},
    }


def test_detects_only_opensrm_v1():
    assert is_opensrm_v1_format(_v1())
    assert not is_opensrm_v1_format({"apiVersion": "srm/v1"})
    assert not is_opensrm_v1_format([])


def test_envelope_metadata_owner_and_service():
    r = convert_opensrm_v1_to_v2(_v1())
    assert isinstance(r, MigrationResult) and r.unmapped == ()
    m = r.manifest
    assert (m["apiVersion"], m["kind"]) == ("opensrm.nthlayer.io/v2", "ServiceManifest")
    assert m["metadata"] == {"name": "payment-api", "labels": {"tier": "critical"}}
    assert m["spec"]["owner"] == {"group": "group:default/payments"}
    assert m["spec"]["service"] == {"name": "payment-api", "type": "api",
                                    "description": "Handles payments"}


def test_labels_and_annotations_are_copied_and_tier_joins_labels():
    d = _v1()
    d["metadata"]["labels"] = {"domain": "payments"}
    d["metadata"]["annotations"] = {"backstage.io/techdocs-ref": "dir:."}
    m = convert_opensrm_v1_to_v2(d).manifest
    assert m["metadata"]["labels"] == {"domain": "payments", "tier": "critical"}
    assert m["metadata"]["annotations"] == {"backstage.io/techdocs-ref": "dir:."}


def test_template_is_reported_unmapped():
    d = _v1()
    d["metadata"]["template"] = "standard-api"
    assert [f.path for f in convert_opensrm_v1_to_v2(d).unmapped] == ["metadata.template"]


@pytest.mark.parametrize("mutate, match", [
    (lambda d: d.update(apiVersion="srm/v1"), "opensrm/v1"),
    (lambda d: d.update(kind="Template"), "ServiceReliabilityManifest"),
    (lambda d: d["metadata"].pop("name"), "metadata.name"),
    (lambda d: d["metadata"].update(name="-payment-api"), "metadata.name"),
    (lambda d: d["metadata"].pop("team"), "team"),
    (lambda d: d["metadata"].update(team="pay ments"), "team"),
    (lambda d: d["spec"].update(type="mainframe"), "spec.type"),
    (lambda d: d["metadata"].update(tier="gold"), "tier"),
    (lambda d: d["metadata"].update(labels={"tier": "low"}), "tier"),
])
def test_unconvertible_documents_raise(mutate, match):
    d = _v1()
    mutate(d)
    with pytest.raises(ValueError, match=match):
        convert_opensrm_v1_to_v2(d)


def test_missing_type_needs_service_type():
    d = _v1()
    del d["spec"]["type"]
    with pytest.raises(ValueError, match="service-type"):
        convert_opensrm_v1_to_v2(d)
    assert convert_opensrm_v1_to_v2(d, service_type="api").manifest["spec"]["service"]["type"] == "api"


def test_supplied_type_must_agree_with_a_declared_one():
    assert convert_opensrm_v1_to_v2(_v1(), service_type="api").manifest["spec"]["service"]["type"] == "api"
    with pytest.raises(ValueError, match="spec.type"):
        convert_opensrm_v1_to_v2(_v1(), service_type="worker")


def test_unknown_spec_keys_are_reported_not_dropped():
    r = convert_opensrm_v1_to_v2(_v1(sla={"x": 1}))
    assert r.unmapped == (UnmappedField("spec.sla", "not part of the opensrm/v1 schema"),)
```

- [ ] **Step 2: Run, expect ModuleNotFoundError.**

- [ ] **Step 3: Implement** the module skeleton. Tasks 4–6 add the section handlers; here `spec.slos`, `contract`, `dependencies`, `ownership`, `observability`, `instrumentation`, `notifications` and `deployment` are already listed in `_SECTIONS["Spec"]` but only `type` is handled — the others route to stub handlers that Task 4–6 replace. To keep this task green on its own, the stubs report the key unmapped with reason `"not yet converted"`; no test in this task uses those keys.

```python
"""opensrm/v1 → opensrm.nthlayer.io/v2 migration (opensrm-pnmv).

``opensrm/v1`` is the published OpenSRM v1 schema (opensrm/spec/v1/schema.json).
NthLayer does not load it — its own v1 dialect is ``srm/v1`` (parser/v1.py),
which differs from the schema in nearly every section. This module converts a
schema-shaped ``opensrm/v1`` document to v2 following
opensrm/spec/v2/AUTHORING.md §7, and never drops a field silently: anything
with no v2 home is returned in ``MigrationResult.unmapped`` for the caller to
refuse or accept. Targets are 0–1 ratios on both sides; nothing here
multiplies by 100. See docs/superpowers/decisions/opensrm-v1-support.md in the
nthlayer front door.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from nthlayer_common.manifest.models import resolve_service_type, valid_service_types_phrase
from nthlayer_common.tiers import VALID_TIERS

OPENSRM_V1_API_VERSION = "opensrm/v1"
_V1_KIND = "ServiceReliabilityManifest"
_V2_NAME = re.compile(r"^[a-z0-9]([a-z0-9-]*[a-z0-9])?$")
_ENTITY_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
_NOT_IN_SCHEMA = "not part of the opensrm/v1 schema"

OPENSRM_V1_REJECTION = (
    "{path}: apiVersion 'opensrm/v1' is the published OpenSRM v1 schema, which "
    "NthLayer does not load. NthLayer reads opensrm.nthlayer.io/v2 (and srm/v1, "
    "its own v1 dialect). Convert it with: nthlayer migrate-manifest {path}"
)

# Per opensrm/spec/v1/schema.json definition: (keys converted, {key: why not}).
# tests/test_opensrm_v1_schema_completeness.py checks every definition's
# properties are covered, both ways.
_SECTIONS: dict[str, tuple[frozenset[str], dict[str, str]]] = {
    "Metadata": (
        frozenset({"name", "team", "tier", "description", "labels", "annotations"}),
        {"template": "v2 templates are a different mechanism (AUTHORING §4.9); re-declare by hand"},
    ),
    "Spec": (
        frozenset({"type", "slos", "contract", "dependencies", "ownership",
                   "observability", "instrumentation"}),
        {
            "notifications": "no v2 equivalent (AUTHORING §7.6)",
            "deployment": "no v2 equivalent (AUTHORING §7.6)",
        },
    ),
}


@dataclass(frozen=True)
class UnmappedField:
    """A v1 field with no v2 home. *path* is dotted into the v1 document."""

    path: str
    reason: str


@dataclass(frozen=True)
class MigrationResult:
    manifest: dict[str, Any]
    unmapped: tuple[UnmappedField, ...]


@dataclass
class _Ctx:
    service: str
    unmapped: list[UnmappedField] = field(default_factory=list)
    annotations: dict[str, str] = field(default_factory=dict)

    def skip(self, path: str, reason: str) -> None:
        self.unmapped.append(UnmappedField(path, reason))


def is_opensrm_v1_format(data: object) -> bool:
    return isinstance(data, dict) and data.get("apiVersion") == OPENSRM_V1_API_VERSION


def _mapping(path: str, value: object) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{path} must be a mapping, got {type(value).__name__}")
    return value


def _entity_name(path: str, value: object) -> str:
    if not isinstance(value, str) or not _ENTITY_NAME.fullmatch(value):
        raise ValueError(
            f"{path} must be a name usable in an entity ref ([A-Za-z0-9._-], "
            f"starting alphanumeric), got {value!r}"
        )
    return value


def _string_map(path: str, value: object) -> dict[str, str]:
    m = _mapping(path, value)
    for k, v in m.items():
        if not isinstance(k, str) or not isinstance(v, str):
            raise ValueError(f"{path} must map strings to strings, got {k!r}: {v!r}")
    return dict(m)


def _service_type(declared: object, supplied: str | None) -> str:
    if declared is None:
        if supplied is None:
            raise ValueError(
                "spec.type is absent: it is optional in opensrm/v1 but required in "
                "v2 (spec.service.type). Supply it (migrate-manifest --service-type). "
                f"Must be one of: {valid_service_types_phrase()}."
            )
        declared_type = supplied
    else:
        declared_type = declared
        if supplied is not None and resolve_service_type(supplied) != resolve_service_type(declared):
            raise ValueError(
                f"spec.type is {declared!r} but {supplied!r} was supplied; "
                "a supplied service type only fills an absent spec.type"
            )
    resolved = resolve_service_type(declared_type) if isinstance(declared_type, str) else None
    if resolved is None:
        raise ValueError(
            f"spec.type {declared_type!r} is not a valid v2 service type. "
            f"Must be one of: {valid_service_types_phrase()}."
        )
    return resolved


def convert_opensrm_v1_to_v2(
    data: dict[str, Any], *, service_type: str | None = None
) -> MigrationResult:
    """Convert an ``opensrm/v1`` document to an ``opensrm.nthlayer.io/v2`` dict.

    Raises ValueError only for a document that cannot be converted at all
    (wrong apiVersion or kind, unusable name/team/tier/type, a malformed value on
    a field that is converted). Fields with no v2 home are reported in
    ``unmapped``, never raised and never dropped.
    """
    if not is_opensrm_v1_format(data):
        raise ValueError(f"expects apiVersion {OPENSRM_V1_API_VERSION!r}, got {data.get('apiVersion')!r}")
    if data.get("kind") != _V1_KIND:
        raise ValueError(
            f"only kind {_V1_KIND!r} converts, got {data.get('kind')!r} "
            "(a v1 Template has no v2 equivalent)"
        )
    metadata = _mapping("metadata", data.get("metadata"))
    spec = _mapping("spec", data.get("spec", {}))

    name = metadata.get("name")
    if not isinstance(name, str) or not _V2_NAME.fullmatch(name):
        raise ValueError(
            f"metadata.name must match ^[a-z0-9]([a-z0-9-]*[a-z0-9])?$ in v2, got {name!r}"
        )
    ctx = _Ctx(service=name)

    tier = metadata.get("tier")
    if tier not in VALID_TIERS:
        raise ValueError(f"metadata.tier must be one of {sorted(VALID_TIERS)}, got {tier!r}")
    labels = _string_map("metadata.labels", metadata.get("labels", {}))
    if labels.get("tier", tier) != tier:
        raise ValueError(f"metadata.labels.tier {labels['tier']!r} disagrees with metadata.tier {tier!r}")
    labels["tier"] = tier
    if "annotations" in metadata:
        ctx.annotations.update(_string_map("metadata.annotations", metadata["annotations"]))

    for key in metadata:
        converted, unmapped = _SECTIONS["Metadata"]
        if key in unmapped:
            ctx.skip(f"metadata.{key}", unmapped[key])
        elif key not in converted:
            ctx.skip(f"metadata.{key}", _NOT_IN_SCHEMA)

    team = _entity_name("metadata.team", metadata.get("team"))
    service: dict[str, Any] = {"name": name, "type": _service_type(spec.get("type"), service_type)}
    if "description" in metadata:
        service["description"] = metadata["description"]

    out_spec: dict[str, Any] = {"owner": {"group": f"group:default/{team}"}, "service": service}
    _convert_spec(spec, out_spec, ctx)

    out_metadata: dict[str, Any] = {"name": name, "labels": labels}
    if ctx.annotations:
        out_metadata["annotations"] = ctx.annotations
    manifest = {
        "apiVersion": "opensrm.nthlayer.io/v2",
        "kind": "ServiceManifest",
        "metadata": out_metadata,
        "spec": out_spec,
    }
    return MigrationResult(manifest=manifest, unmapped=tuple(ctx.unmapped))


def _convert_spec(spec: dict[str, Any], out: dict[str, Any], ctx: _Ctx) -> None:
    converted, unmapped = _SECTIONS["Spec"]
    for key, value in spec.items():
        if key == "type":
            continue
        if key in unmapped:
            ctx.skip(f"spec.{key}", unmapped[key])
        elif key not in converted:
            ctx.skip(f"spec.{key}", _NOT_IN_SCHEMA)
        else:
            _SPEC_HANDLERS[key](value, out, ctx)


def _not_yet(key: str):
    def handler(value: object, out: dict[str, Any], ctx: _Ctx) -> None:
        ctx.skip(f"spec.{key}", "not yet converted")
    return handler


# Tasks 4-6 replace each stub with the real handler.
_SPEC_HANDLERS = {
    key: _not_yet(key)
    for key in ("slos", "contract", "dependencies", "ownership", "observability", "instrumentation")
}
```

Note: `metadata.team` and `metadata.tier` are required by the v1 schema; the team becomes `spec.owner.group` here and Task 6's ownership handler checks `ownership.team` agrees.

- [ ] **Step 4: Run the tests, full suite, ruff.**

- [ ] **Step 5: Commit** — `feat(manifest): opensrm/v1 converter envelope, metadata and owner (opensrm-pnmv)`.

### Task 4: Classical SLOs → OpenSLO documents

**Files:**
- Modify: `nthlayer-common/src/nthlayer_common/manifest/opensrm_v1.py`
- Test: `nthlayer-common/tests/test_opensrm_v1_slos.py` (create)

**Interfaces:**
- Consumes: `_Ctx`, `_SECTIONS`, `_SPEC_HANDLERS`, `_mapping` (Task 3); `is_duration` (`nthlayer_common.manifest.thresholds`); `_infer_openslo_type(name, target, indicator_query, total_query, good_query, objective)` (`nthlayer_common.manifest.openslo.parser` — read its current signature first; if it differs, call it the way `_parse_openslo_document` does).
- Produces: `_SPEC_HANDLERS["slos"]` (fills `out["slo"]`; hands `slos.judgment` to `_convert_judgment`, which Task 5 implements — until then it reports `spec.slos.judgment` unmapped with reason `"not yet converted"`); `_SECTIONS` entries `SLOs`, `LatencySLO`, and one per converted classical definition.

- [ ] **Step 1: Write the failing tests**

```python
"""opensrm/v1 classical SLOs → OpenSLO (opensrm-pnmv).

Expected values follow opensrm/spec/v1/schema.json (targets are 0-1 ratios;
ErrorRateSLO.target is a MAXIMUM error ratio; window defaults are 30d for the
converted types) and AUTHORING.md §7.3, whose reference output
(spec/v2/examples/migration/api-full-v2.yaml) names SLOs <service>-<key>.
"""
import pytest

from nthlayer_common.manifest.opensrm_v1 import convert_opensrm_v1_to_v2
from nthlayer_common.manifest.parser.v2 import parse_opensrm_v2


def _v1(slos: dict, name: str = "payment-api", stype: str = "api") -> dict:
    return {"apiVersion": "opensrm/v1", "kind": "ServiceReliabilityManifest",
            "metadata": {"name": name, "team": "payments", "tier": "critical"},
            "spec": {"type": stype, "slos": slos}}


def _slo(result, key):
    (doc,) = [d for d in result.manifest["spec"]["slo"] if d["metadata"]["name"].endswith(key)]
    return doc


def test_availability_keeps_target_and_window():
    r = convert_opensrm_v1_to_v2(_v1({"availability": {"target": 0.9995, "window": "30d"}}))
    doc = _slo(r, "availability")
    assert doc["metadata"]["name"] == "payment-api-availability"
    assert doc["spec"]["service"] == "payment-api"
    assert doc["spec"]["timeWindow"] == [{"duration": "30d", "isRolling": True}]
    assert doc["spec"]["objectives"][0]["target"] == 0.9995
    assert "indicator" not in doc["spec"]
    assert r.unmapped == ()


def test_error_rate_is_complemented_and_keeps_a_7d_window():
    r = convert_opensrm_v1_to_v2(_v1({"error_rate": {"target": 0.001, "window": "7d"}}))
    doc = _slo(r, "error-rate")
    assert doc["spec"]["objectives"][0]["target"] == 0.999
    assert doc["spec"]["timeWindow"] == [{"duration": "7d", "isRolling": True}]
    (slo,) = parse_opensrm_v2(r.manifest).slos
    assert (slo.slo_type, slo.window) == ("error_rate", "7d")


def test_absent_window_uses_the_v1_schema_default():
    r = convert_opensrm_v1_to_v2(_v1({"availability": {"target": 0.999}}))
    assert _slo(r, "availability")["spec"]["timeWindow"] == [{"duration": "30d", "isRolling": True}]


def test_latency_percentiles_go_to_display_name_and_are_reported():
    r = convert_opensrm_v1_to_v2(_v1({"latency": {"p50": "50ms", "p99": "200ms", "target": 0.99}}))
    obj = _slo(r, "latency")["spec"]["objectives"][0]
    assert obj["target"] == 0.99 and "p50 under 50ms" in obj["displayName"] and "p99 under 200ms" in obj["displayName"]
    assert [f.path for f in r.unmapped] == ["spec.slos.latency.p50", "spec.slos.latency.p99"]


@pytest.mark.parametrize("key, expected_type", [
    ("duration", "latency"), ("query_latency", "latency"),
    ("connection_availability", "availability"),
])
def test_other_converted_types_parse_as_intended(key, expected_type):
    r = convert_opensrm_v1_to_v2(_v1({key: {"target": 0.99}}, stype="database"))
    (slo,) = parse_opensrm_v2(r.manifest).slos
    assert slo.slo_type == expected_type


@pytest.mark.parametrize("key, cfg", [
    ("throughput", {"target": 1000, "unit": "rps"}),
    ("success_rate", {"target": 0.995}),
    ("processing_time", {"target": 0.95, "p95": "5m"}),
    ("lag", {"target": 0.99, "max": "1m"}),
    ("schedule_adherence", {"max_delay": "10m"}),
    ("data_freshness", {"max_age": "2h"}),
    ("replication_lag", {"max_lag": "1s"}),
])
def test_unconvertible_slo_types_are_reported_not_dropped(key, cfg):
    r = convert_opensrm_v1_to_v2(_v1({key: cfg}, stype="batch"))
    assert "slo" not in r.manifest["spec"]
    assert [f.path for f in r.unmapped] == [f"spec.slos.{key}"]


def test_custom_is_reported_and_openslo_paths_become_refs():
    r = convert_opensrm_v1_to_v2(_v1({"custom": [{"name": "x"}], "openslo": [{"path": "slos/a.yaml"}]}))
    assert r.manifest["spec"]["slo"] == [{"$ref": "slos/a.yaml"}]
    assert [f.path for f in r.unmapped] == ["spec.slos.custom"]


@pytest.mark.parametrize("cfg, match", [
    ({"target": 1.5}, "target"), ({"target": "0.99"}, "target"), ({"target": True}, "target"),
    ({"target": 0.99, "window": "30 days"}, "window"), ({}, "target"),
])
def test_malformed_converted_slos_raise(cfg, match):
    with pytest.raises(ValueError, match=match):
        convert_opensrm_v1_to_v2(_v1({"availability": cfg}))


def test_a_type_hint_word_in_the_service_name_raises_instead_of_mistyping():
    # "error-tracker-availability" would be typed error_rate by the parser.
    with pytest.raises(ValueError, match="error-tracker-availability"):
        convert_opensrm_v1_to_v2(_v1({"availability": {"target": 0.999}}, name="error-tracker"))
```

- [ ] **Step 2: Run, expect failures** (stub reports `spec.slos` unmapped).

- [ ] **Step 3: Implement.** Add to `opensrm_v1.py`:

```python
from nthlayer_common.manifest.openslo.parser import _infer_openslo_type
from nthlayer_common.manifest.thresholds import is_duration

# v1 classical SLO key → the slo_type common's OpenSLO parser must infer.
_CLASSICAL = {
    "availability": "availability", "connection_availability": "availability",
    "error_rate": "error_rate",
    "latency": "latency", "duration": "latency", "query_latency": "latency",
}
# spec/v1/schema.json window defaults for the converted types (all 30d).
_WINDOW_DEFAULT = dict.fromkeys(_CLASSICAL, "30d")
_PERCENTILES = ("p50", "p90", "p95", "p99", "p999")
_PERCENTILE_WHY = ("kept only in the OpenSLO displayName: an objective without an "
                   "indicator carries no machine-readable percentile")

_SECTIONS["SLOs"] = (
    frozenset({*_CLASSICAL, "openslo", "judgment"}),
    {
        "throughput": "v1 declares a rate (e.g. 1000 rps); an OpenSLO objective needs a ratio target (AUTHORING §7.3)",
        "success_rate": "common's v2 parser cannot infer this SLO's type (opensrm-47tt)",
        "processing_time": "common's v2 parser cannot infer this SLO's type (opensrm-47tt)",
        "lag": "common's v2 parser cannot infer this SLO's type (opensrm-47tt)",
        "schedule_adherence": "maximum-only SLO (max_delay) with no target; an OpenSLO objective needs one",
        "data_freshness": "maximum-only SLO (max_age) with no target; an OpenSLO objective needs one",
        "replication_lag": "maximum-only SLO (max_lag) with no target; an OpenSLO objective needs one",
        "custom": "custom SLOs have no v2 mapping",
    },
)
_SECTIONS["LatencySLO"] = (frozenset({"target", "window"}), dict.fromkeys(_PERCENTILES, _PERCENTILE_WHY))
for _defn in ("AvailabilitySLO", "ErrorRateSLO", "ConnectionAvailabilitySLO"):
    _SECTIONS[_defn] = (frozenset({"target", "window"}), {})
for _defn in ("DurationSLO", "QueryLatencySLO"):
    _SECTIONS[_defn] = (frozenset({"target", "window"}), dict.fromkeys(_PERCENTILES, _PERCENTILE_WHY))


def _ratio(path: str, value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not 0.0 <= value <= 1.0:
        raise ValueError(f"{path} must be a ratio in [0, 1], got {value!r}")
    return float(value)


def _duration(path: str, value: object) -> str:
    if not is_duration(value):
        raise ValueError(f"{path} must be a duration like '30d' or '200ms', got {value!r}")
    return value


def _pct(ratio: float) -> str:
    return f"{ratio * 100:g}%"


def _openslo(key: str, cfg: object, ctx: _Ctx) -> dict[str, Any]:
    path = f"spec.slos.{key}"
    cfg = _mapping(path, cfg)
    target = _ratio(f"{path}.target", cfg.get("target"))
    window = _duration(f"{path}.window", cfg.get("window", _WINDOW_DEFAULT[key]))
    kind = _CLASSICAL[key]
    if kind == "error_rate":
        # v1 ErrorRateSLO.target is a MAXIMUM error ratio; OpenSLO targets are
        # good-ratios (the spec's reference output turns 0.001 into 0.999).
        good = round(1.0 - target, 12)
        display = f"Error rate under {_pct(target)} over {window}"
    elif kind == "latency":
        pcts = [(p, _duration(f"{path}.{p}", cfg[p])) for p in _PERCENTILES if p in cfg]
        for p, _ in pcts:
            ctx.skip(f"{path}.{p}", _PERCENTILE_WHY)
        good = target
        bits = ", ".join(f"{p} under {v}" for p, v in pcts)
        display = f"{_pct(target)} of requests {bits} over {window}" if bits else f"{_pct(target)} {key.replace('_', ' ')} over {window}"
    else:
        good = target
        display = f"{_pct(target)} {key.replace('_', ' ')} over {window}"
    for extra in cfg:
        if extra not in ("target", "window", *_PERCENTILES):
            ctx.skip(f"{path}.{extra}", _NOT_IN_SCHEMA)

    slo_name = f"{ctx.service}-{key.replace('_', '-')}"
    objective = {"displayName": display, "target": good}
    inferred = _infer_openslo_type(slo_name, good * 100, None, None, None, objective)
    if inferred != kind:
        raise ValueError(
            f"SLO '{slo_name}' would be read as {inferred!r}, not {kind!r}: common's v2 "
            "parser infers the type from the SLO name and the service name contains "
            "another type's word (opensrm-47tt). Rename the service or migrate this SLO by hand."
        )
    return {
        "apiVersion": "openslo/v1",
        "kind": "SLO",
        "metadata": {"name": slo_name},
        "spec": {
            "service": ctx.service,
            "timeWindow": [{"duration": window, "isRolling": True}],
            "objectives": [objective],
        },
    }


def _convert_slos(value: object, out: dict[str, Any], ctx: _Ctx) -> None:
    slos = _mapping("spec.slos", value)
    converted, unmapped = _SECTIONS["SLOs"]
    docs: list[dict[str, Any]] = []
    for key, cfg in slos.items():
        if key in unmapped:
            ctx.skip(f"spec.slos.{key}", unmapped[key])
        elif key not in converted:
            ctx.skip(f"spec.slos.{key}", _NOT_IN_SCHEMA)
        elif key == "openslo":
            for i, item in enumerate(cfg if isinstance(cfg, list) else []):
                ref = _mapping(f"spec.slos.openslo[{i}]", item).get("path")
                if not isinstance(ref, str) or not ref:
                    raise ValueError(f"spec.slos.openslo[{i}].path must be a non-empty string")
                docs.append({"$ref": ref})
        elif key == "judgment":
            _convert_judgment(cfg, out, ctx)
        else:
            docs.append(_openslo(key, cfg, ctx))
    if docs:
        out["slo"] = docs


def _convert_judgment(value: object, out: dict[str, Any], ctx: _Ctx) -> None:
    ctx.skip("spec.slos.judgment", "not yet converted")   # Task 5


_SPEC_HANDLERS["slos"] = _convert_slos
```

Before writing `_infer_openslo_type`'s call, open `nthlayer_common/manifest/openslo/parser.py`, confirm its signature and that it raises (not returns None) for an untypeable name; if it raises, wrap the call: `try: inferred = ... except OpenSLOParseError: inferred = None`.

- [ ] **Step 4: Run, full suite, ruff.** — **Step 5: Commit** — `feat(manifest): opensrm/v1 classical SLOs become OpenSLO documents (opensrm-pnmv)`.

### Task 5: Judgment block → judgment thresholds; judgment SLOs unmapped

**Files:**
- Modify: `nthlayer-common/src/nthlayer_common/manifest/opensrm_v1.py` (`_convert_judgment`)
- Test: `nthlayer-common/tests/test_opensrm_v1_judgment.py` (create)

**Interfaces:**
- Consumes: `JudgmentThreshold`, `ThresholdMeasurement` (`nthlayer_common.manifest.models`), `threshold_to_v2_entry`, `_SRM_V1_CALIBRATION_BINS` (`nthlayer_common.manifest.thresholds`); `_ratio`, `_duration`, `_mapping` (Tasks 3–4).
- Produces: `_SECTIONS["JudgmentSLOs"]`; `out["judgment_threshold"]` entries.

- [ ] **Step 1: Write the failing tests**

```python
"""opensrm/v1 slos.judgment (opensrm-pnmv).

Shapes: spec/v1/schema.json JudgmentSLOs — calibration {target, window}
(FlatCalibrationSLO, both required), feedback_latency {p50, p90} durations,
reversal_rate / high_confidence_failure. Mapping: AUTHORING.md §7.6 (calibration
and feedback_latency → judgment_threshold) and §7.7 step 8 (judgment_slo is not
migration). v2 allows judgment blocks only on ai-gate (§3.1).
"""
import pytest

from nthlayer_common.manifest.opensrm_v1 import convert_opensrm_v1_to_v2
from nthlayer_common.manifest.parser.v2 import parse_opensrm_v2


def _v1(judgment: dict, stype: str = "ai-gate") -> dict:
    return {"apiVersion": "opensrm/v1", "kind": "ServiceReliabilityManifest",
            "metadata": {"name": "pr-review-agent", "team": "platform", "tier": "critical"},
            "spec": {"type": stype, "slos": {"judgment": judgment}}}


def test_calibration_and_feedback_latency_become_thresholds():
    r = convert_opensrm_v1_to_v2(_v1({
        "calibration": {"target": 0.10, "window": "30d"},
        "feedback_latency": {"p50": "48h", "p90": "168h"},
    }))
    assert r.manifest["spec"]["judgment_threshold"] == [
        {"type": "calibration", "bounds": {"maximum_expected_calibration_error": 0.10},
         "measurement": {"bins": 10, "window": "30d"}},
        {"type": "feedback_latency", "bounds": {"maximum_p50": "48h", "maximum_p90": "168h"}},
    ]
    # bins is a value v1 never declares: reported so the author checks it.
    assert [f.path for f in r.unmapped] == ["spec.slos.judgment.calibration"]
    parse_opensrm_v2(r.manifest)


@pytest.mark.parametrize("key", ["reversal_rate", "high_confidence_failure"])
def test_judgment_slos_are_reported_unmapped(key):
    r = convert_opensrm_v1_to_v2(_v1({key: {"target": 0.03, "window": "30d"}}))
    assert "judgment_slo" not in r.manifest["spec"]
    assert [f.path for f in r.unmapped] == [f"spec.slos.judgment.{key}"]
    assert "a742" in r.unmapped[0].reason


def test_a_non_ai_gate_manifest_reports_the_whole_judgment_block():
    r = convert_opensrm_v1_to_v2(_v1({"calibration": {"target": 0.1, "window": "30d"}}, stype="api"))
    assert "judgment_threshold" not in r.manifest["spec"]
    assert [f.path for f in r.unmapped] == ["spec.slos.judgment"]
    parse_opensrm_v2(r.manifest)


@pytest.mark.parametrize("cfg, match", [
    ({"calibration": {"window": "30d"}}, "target"),
    ({"calibration": {"target": 0.1}}, "window"),
    ({"calibration": {"target": 2, "window": "30d"}}, "target"),
    ({"feedback_latency": {"p50": "two days"}}, "p50"),
])
def test_malformed_converted_judgment_fields_raise(cfg, match):
    with pytest.raises(ValueError, match=match):
        convert_opensrm_v1_to_v2(_v1(cfg))


def test_feedback_latency_without_bounds_is_reported():
    r = convert_opensrm_v1_to_v2(_v1({"feedback_latency": {}}))
    assert [f.path for f in r.unmapped] == ["spec.slos.judgment.feedback_latency"]
```

- [ ] **Step 2: Run, expect failures.**

- [ ] **Step 3: Implement** (replace the Task 4 stub):

```python
from nthlayer_common.manifest.models import JudgmentThreshold, ThresholdMeasurement
from nthlayer_common.manifest.thresholds import _SRM_V1_CALIBRATION_BINS, threshold_to_v2_entry

_JUDGMENT_SLO_WHY = (
    "judgment_slo is new capability, not migration (AUTHORING §7.7 step 8), and no "
    "v2 judgment-SLO shape passes both the schema and common's parser (opensrm-a742)"
)
_SECTIONS["JudgmentSLOs"] = (
    frozenset({"calibration", "feedback_latency"}),
    {"reversal_rate": _JUDGMENT_SLO_WHY, "high_confidence_failure": _JUDGMENT_SLO_WHY},
)
_SECTIONS["FlatCalibrationSLO"] = (frozenset({"target", "window"}), {})
_SECTIONS["FeedbackLatencySLO"] = (frozenset({"p50", "p90"}), {})


def _convert_judgment(value: object, out: dict[str, Any], ctx: _Ctx) -> None:
    judgment = _mapping("spec.slos.judgment", value)
    if out["service"]["type"] != "ai-gate":
        ctx.skip("spec.slos.judgment",
                 "v2 allows judgment blocks only on spec.service.type ai-gate (AUTHORING §3.1)")
        return
    converted, unmapped = _SECTIONS["JudgmentSLOs"]
    entries: list[dict[str, Any]] = []
    for key, cfg in judgment.items():
        path = f"spec.slos.judgment.{key}"
        if key in unmapped:
            ctx.skip(path, unmapped[key])
        elif key not in converted:
            ctx.skip(path, _NOT_IN_SCHEMA)
        elif key == "calibration":
            cfg = _mapping(path, cfg)
            threshold = JudgmentThreshold(
                type="calibration",
                bounds={"maximum_expected_calibration_error": _ratio(f"{path}.target", cfg.get("target"))},
                measurement=ThresholdMeasurement(
                    window=_duration(f"{path}.window", cfg.get("window")),
                    bins=_SRM_V1_CALIBRATION_BINS,
                ),
            )
            entries.append(threshold_to_v2_entry(threshold))
            ctx.skip(path, f"converted with measurement.bins: {_SRM_V1_CALIBRATION_BINS}, "
                           "a value opensrm/v1 does not declare; check it")
        else:  # feedback_latency
            cfg = _mapping(path, cfg)
            bounds = {f"maximum_{p}": _duration(f"{path}.{p}", cfg[p]) for p in ("p50", "p90") if p in cfg}
            if not bounds:
                ctx.skip(path, "declares neither p50 nor p90, so there is no bound to convert")
                continue
            entries.append(threshold_to_v2_entry(JudgmentThreshold(type="feedback_latency", bounds=bounds)))
    if entries:
        out["judgment_threshold"] = entries
```

`out["service"]` exists because Task 3 builds `out_spec` with `service` before calling `_convert_spec`. Check `JudgmentThreshold`'s constructor (models.py) for required fields and a default `measurement`; adapt the call if `measurement` is required (pass `ThresholdMeasurement()`), and confirm `threshold_to_v2_entry` emits exactly the dicts the test expects — if it emits a different but parser-equivalent shape, change the test's expected dicts to match the parser's own `threshold_to_v2_entry` output and record that in the report.

- [ ] **Step 4: Run, full suite, ruff.** — **Step 5: Commit** — `feat(manifest): opensrm/v1 judgment block becomes judgment thresholds (opensrm-pnmv)`.

### Task 6: Contract, dependencies, ownership, observability, instrumentation

**Files:**
- Modify: `nthlayer-common/src/nthlayer_common/manifest/opensrm_v1.py`
- Test: `nthlayer-common/tests/test_opensrm_v1_sections.py` (create)

**Interfaces:**
- Consumes: Tasks 3–5 helpers.
- Produces: `_SPEC_HANDLERS` for `contract`, `dependencies`, `ownership`, `observability`, `instrumentation`; `_SECTIONS` entries `Contract`, `ContractLatency`, `ContractThroughput`, `Dependency`, `Ownership`, `Observability`, `Instrumentation`.

- [ ] **Step 1: Write the failing tests**

```python
"""opensrm/v1 contract / dependencies / ownership / observability /
instrumentation (opensrm-pnmv). Shapes: spec/v1/schema.json; mapping:
AUTHORING.md §7.2 (ownership → owner + annotations), §7.4 (contract →
contracts), §7.5 (dependencies), §7.6 (homeless blocks).
"""
import pytest

from nthlayer_common.manifest.opensrm_v1 import convert_opensrm_v1_to_v2
from nthlayer_common.manifest.parser.v2 import parse_opensrm_v2


def _v1(**spec) -> dict:
    return {"apiVersion": "opensrm/v1", "kind": "ServiceReliabilityManifest",
            "metadata": {"name": "payment-api", "team": "payments", "tier": "critical"},
            "spec": {"type": "api", **spec}}


def _paths(r):
    return [f.path for f in r.unmapped]


def test_contract_becomes_contracts():
    r = convert_opensrm_v1_to_v2(_v1(contract={
        "availability": 0.9995, "latency": {"p99": "300ms"}, "throughput": {"max_rps": 5000}}))
    assert r.manifest["spec"]["contracts"] == [{
        "name": "payment-api",
        "promise": {"availability": 0.9995, "latency_p99": "300ms", "throughput": "5000rps"},
        "contract_owner": "group:default/payments",
    }]
    assert r.unmapped == ()
    parse_opensrm_v2(r.manifest)


def test_contract_fields_with_no_promise_slot_are_reported():
    r = convert_opensrm_v1_to_v2(_v1(contract={
        "latency": {"p50": "50ms", "p999": "1s"}, "throughput": {"burst": 100},
        "judgment": {"max_reversal_rate": 0.05}}))
    assert "contracts" not in r.manifest["spec"]
    assert _paths(r) == ["spec.contract.latency.p50", "spec.contract.latency.p999",
                         "spec.contract.throughput.burst", "spec.contract.judgment"]


@pytest.mark.parametrize("dtype, ref", [
    ("database", "resource:default/postgresql"), ("cache", "resource:default/postgresql"),
    ("queue", "resource:default/postgresql"), ("external", "component:external/postgresql"),
    ("service", "component:default/postgresql"), (None, "component:default/postgresql"),
])
def test_dependency_ref_kind_follows_the_v1_type(dtype, ref):
    dep = {"service": "postgresql", "expects": {"availability": 0.9995, "latency": {"p99": "20ms"}}}
    if dtype:
        dep["type"] = dtype
    r = convert_opensrm_v1_to_v2(_v1(dependencies=[dep]))
    assert r.manifest["spec"]["dependencies"] == [
        {"service": ref, "expected_availability": 0.9995, "expected_latency_p99": "20ms"}]
    parse_opensrm_v2(r.manifest)


def test_dependency_critical_and_manifest_are_reported():
    r = convert_opensrm_v1_to_v2(_v1(dependencies=[
        {"service": "user-service", "type": "service", "critical": True,
         "manifest": "https://example.com/user-service.yaml"}]))
    assert _paths(r) == ["spec.dependencies[0].critical", "spec.dependencies[0].manifest"]


def test_ownership_becomes_owner_and_annotations():
    r = convert_opensrm_v1_to_v2(_v1(ownership={
        "team": "payments", "slack": "#payments-team", "email": "p@example.com",
        "escalation": "payments-oncall", "runbook": "https://wiki/rb", "documentation": "https://docs",
        "pagerduty": {"service_id": "PXXXXXX", "escalation_policy_id": "PYYY"},
        "oncall_required": True}))
    m = r.manifest
    assert m["spec"]["owner"] == {"group": "group:default/payments",
                                  "escalation": "group:default/payments-oncall"}
    assert m["metadata"]["annotations"] == {
        "slack.com/channel": "#payments-team",
        "opensrm.nthlayer.io/runbook": "https://wiki/rb",
        "opensrm.nthlayer.io/documentation": "https://docs",
        "pagerduty.com/service-id": "PXXXXXX",
    }
    assert _paths(r) == ["spec.ownership.email", "spec.ownership.pagerduty.escalation_policy_id",
                         "spec.ownership.oncall_required"]
    parse_opensrm_v2(m)


def test_ownership_team_must_agree_with_metadata_team():
    with pytest.raises(ValueError, match="ownership.team"):
        convert_opensrm_v1_to_v2(_v1(ownership={"team": "billing"}))


def test_an_annotation_collision_raises():
    d = _v1(ownership={"team": "payments", "slack": "#new"})
    d["metadata"]["annotations"] = {"slack.com/channel": "#old"}
    with pytest.raises(ValueError, match="slack.com/channel"):
        convert_opensrm_v1_to_v2(d)


def test_observability_notifications_and_deployment_are_reported():
    r = convert_opensrm_v1_to_v2(_v1(
        observability={"metrics": {"required": ["x"]}, "dashboards": {"required": True},
                       "alerts": {"required": True}, "tracing": {"required": True}},
        notifications={"slack": {"channel": "#x"}}, deployment={"gates": {}}))
    assert _paths(r) == ["spec.observability.metrics", "spec.observability.dashboards",
                         "spec.observability.alerts", "spec.observability.tracing",
                         "spec.notifications", "spec.deployment"]


def test_instrumentation_events_become_required_events():
    r = convert_opensrm_v1_to_v2(_v1(instrumentation={
        "events": {"decision": {}, "reversal": {}}, "attributes": {"decision_id": "string"}}))
    assert r.manifest["spec"]["instrumentation"] == {
        "required_events": [{"type": "decision"}, {"type": "reversal"}]}
    assert _paths(r) == ["spec.instrumentation.attributes"]
```

Before writing `test_instrumentation_events_become_required_events`, open `spec/v1/schema.json`'s `Instrumentation.events` definition: if each event's value is an object that names the event (e.g. `{name: ...}`), use that name as `type` and adjust the test's fixture and expected list to the schema's shape — the fixture must be schema-valid.

- [ ] **Step 2: Run, expect failures.**

- [ ] **Step 3: Implement** the five handlers:

```python
_SECTIONS["Contract"] = (frozenset({"availability", "latency", "throughput"}),
                         {"judgment": "v2 contracts[].promise has availability, latency_p99 and throughput only (AUTHORING §7.4)"})
_SECTIONS["ContractLatency"] = (frozenset({"p99"}), dict.fromkeys(
    ("p50", "p999"), "v2 contracts[].promise has latency_p99 only (AUTHORING §7.4)"))
_SECTIONS["ContractThroughput"] = (frozenset({"max_rps"}),
                                   {"burst": "v2 contracts[].promise.throughput is a single rate (AUTHORING §7.4)"})
_SECTIONS["Dependency"] = (frozenset({"service", "type", "expects"}), {
    "critical": "v2 expresses this as a fallback, which only the author can choose (AUTHORING §7.5)",
    "manifest": "v2 resolves dependencies through the catalogue (AUTHORING §7.5)"})
_SECTIONS["Ownership"] = (frozenset({"team", "slack", "escalation", "pagerduty", "runbook", "documentation"}), {
    "email": "no v2 field or AUTHORING §7.2 annotation key",
    "oncall_required": "no v2 field"})
_SECTIONS["Observability"] = (frozenset(), {
    "metrics": "v2 instrumentation needs a type per metric (AUTHORING §7.7 step 6)",
    "dashboards": "no v2 equivalent (AUTHORING §7.6)",
    "alerts": "no v2 equivalent (AUTHORING §7.6)",
    "tracing": "no v2 equivalent (AUTHORING §7.6)"})
_SECTIONS["Instrumentation"] = (frozenset({"events"}), {"attributes": "v2 instrumentation has no attribute list"})

_RESOURCE_TYPES = ("database", "cache", "queue")
_OWNERSHIP_ANNOTATIONS = {   # AUTHORING §7.2
    "slack": "slack.com/channel",
    "runbook": "opensrm.nthlayer.io/runbook",
    "documentation": "opensrm.nthlayer.io/documentation",
}


def _keys(section: str, path: str, value: dict[str, Any], ctx: _Ctx) -> list[str]:
    """Report the unmapped and unknown keys of *value*; return the converted ones, in order."""
    converted, unmapped = _SECTIONS[section]
    keep = []
    for key in value:
        if key in unmapped:
            ctx.skip(f"{path}.{key}", unmapped[key])
        elif key not in converted:
            ctx.skip(f"{path}.{key}", _NOT_IN_SCHEMA)
        else:
            keep.append(key)
    return keep


def _annotate(ctx: _Ctx, key: str, value: object, path: str) -> None:
    if not isinstance(value, str):
        raise ValueError(f"{path} must be a string, got {value!r}")
    if ctx.annotations.get(key, value) != value:
        raise ValueError(f"{path} would set annotation {key} to {value!r}, but metadata.annotations has {ctx.annotations[key]!r}")
    ctx.annotations[key] = value


def _convert_contract(value: object, out: dict[str, Any], ctx: _Ctx) -> None:
    contract = _mapping("spec.contract", value)
    promise: dict[str, Any] = {}
    for key in _keys("Contract", "spec.contract", contract, ctx):
        if key == "availability":
            promise["availability"] = _ratio("spec.contract.availability", contract[key])
        elif key == "latency":
            latency = _mapping("spec.contract.latency", contract[key])
            if "p99" in _keys("ContractLatency", "spec.contract.latency", latency, ctx):
                promise["latency_p99"] = _duration("spec.contract.latency.p99", latency["p99"])
        else:  # throughput
            throughput = _mapping("spec.contract.throughput", contract[key])
            if "max_rps" in _keys("ContractThroughput", "spec.contract.throughput", throughput, ctx):
                rps = throughput["max_rps"]
                if isinstance(rps, bool) or not isinstance(rps, int) or rps < 0:
                    raise ValueError(f"spec.contract.throughput.max_rps must be a non-negative integer, got {rps!r}")
                promise["throughput"] = f"{rps}rps"
    if promise:
        out["contracts"] = [{"name": ctx.service, "promise": promise,
                             "contract_owner": out["owner"]["group"]}]


def _convert_dependencies(value: object, out: dict[str, Any], ctx: _Ctx) -> None:
    if not isinstance(value, list):
        raise ValueError(f"spec.dependencies must be a list, got {type(value).__name__}")
    deps = []
    for i, raw in enumerate(value):
        path = f"spec.dependencies[{i}]"
        dep = _mapping(path, raw)
        keys = _keys("Dependency", path, dep, ctx)
        name = _entity_name(f"{path}.service", dep.get("service"))
        dtype = dep.get("type", "service")
        if dtype in _RESOURCE_TYPES:
            ref = f"resource:default/{name}"
        elif dtype == "external":
            ref = f"component:external/{name}"
        elif dtype == "service":
            ref = f"component:default/{name}"
        else:
            raise ValueError(f"{path}.type must be one of service, database, cache, queue, external; got {dtype!r}")
        entry: dict[str, Any] = {"service": ref}
        if "expects" in keys:
            expects = _mapping(f"{path}.expects", dep["expects"])
            for key in expects:
                if key == "availability":
                    entry["expected_availability"] = _ratio(f"{path}.expects.availability", expects[key])
                elif key == "latency":
                    latency = _mapping(f"{path}.expects.latency", expects[key])
                    for lk in latency:
                        if lk == "p99":
                            entry["expected_latency_p99"] = _duration(f"{path}.expects.latency.p99", latency[lk])
                        else:
                            ctx.skip(f"{path}.expects.latency.{lk}", _NOT_IN_SCHEMA)
                else:
                    ctx.skip(f"{path}.expects.{key}", _NOT_IN_SCHEMA)
        deps.append(entry)
    if deps:
        out["dependencies"] = deps


def _convert_ownership(value: object, out: dict[str, Any], ctx: _Ctx) -> None:
    own = _mapping("spec.ownership", value)
    for key in _keys("Ownership", "spec.ownership", own, ctx):
        path = f"spec.ownership.{key}"
        if key == "team":
            team = _entity_name(path, own[key])
            if f"group:default/{team}" != out["owner"]["group"]:
                raise ValueError(f"spec.ownership.team {team!r} disagrees with metadata.team ({out['owner']['group']})")
        elif key == "escalation":
            out["owner"]["escalation"] = f"group:default/{_entity_name(path, own[key])}"
        elif key == "pagerduty":
            pd = _mapping(path, own[key])
            for pk in pd:
                if pk == "service_id":
                    _annotate(ctx, "pagerduty.com/service-id", pd[pk], f"{path}.service_id")
                elif pk == "escalation_policy_id":
                    ctx.skip(f"{path}.escalation_policy_id", "no AUTHORING §7.2 annotation key")
                else:
                    ctx.skip(f"{path}.{pk}", _NOT_IN_SCHEMA)
        else:
            _annotate(ctx, _OWNERSHIP_ANNOTATIONS[key], own[key], path)


def _convert_observability(value: object, out: dict[str, Any], ctx: _Ctx) -> None:
    _keys("Observability", "spec.observability", _mapping("spec.observability", value), ctx)


def _convert_instrumentation(value: object, out: dict[str, Any], ctx: _Ctx) -> None:
    inst = _mapping("spec.instrumentation", value)
    if "events" in _keys("Instrumentation", "spec.instrumentation", inst, ctx):
        events = _mapping("spec.instrumentation.events", inst["events"])
        if events:
            out["instrumentation"] = {"required_events": [{"type": name} for name in events]}


_SPEC_HANDLERS.update(
    contract=_convert_contract, dependencies=_convert_dependencies, ownership=_convert_ownership,
    observability=_convert_observability, instrumentation=_convert_instrumentation,
)
```

Make `_convert_slos` (Task 4) use `_keys("SLOs", ...)` too if that simplifies it, and delete the `_not_yet` stub once no key routes to it.

- [ ] **Step 4: Run, full suite, ruff.** — **Step 5: Commit** — `feat(manifest): opensrm/v1 contract, dependencies, ownership and instrumentation (opensrm-pnmv)`.

### Task 7: Loader rejection, public API, docs

**Files:**
- Modify: `nthlayer-common/src/nthlayer_common/manifest/parser/loader.py` (`load_manifest`, after the non-dict check)
- Modify: `nthlayer-common/src/nthlayer_common/manifest/__init__.py` (re-exports + `__all__` group `# opensrm/v1 migration`)
- Modify: `nthlayer-common/CLAUDE.md` (hard rule 1: one line — opensrm/v1 targets are ratios, converted as ratios, never ÷100), `nthlayer-common/docs/architecture.md` (`manifest/` layout block and the Manifest section's format list + a bullet for `opensrm_v1.py`), `nthlayer-common/docs/upgrading-5.0.md` (a `- **New in 5.3.0:**` bullet after 5.2.0's)
- Test: `nthlayer-common/tests/test_opensrm_v1_loader.py` (create)

**Interfaces:**
- Consumes: `is_opensrm_v1_format`, `OPENSRM_V1_REJECTION` (Task 3).
- Produces: `load_manifest` raises `ManifestLoadError` for any `opensrm/v1` document, whatever `format=` says; `nthlayer_common.manifest` re-exports `convert_opensrm_v1_to_v2`, `is_opensrm_v1_format`, `MigrationResult`, `UnmappedField`, `OPENSRM_V1_API_VERSION`.

- [ ] **Step 1: Write the failing tests**

```python
"""load_manifest rejects opensrm/v1 clearly (opensrm-pnmv)."""
import warnings

import pytest
import yaml

from nthlayer_common import manifest
from nthlayer_common.manifest import LegacyFormatWarning, ManifestLoadError, load_manifest

_DOC = {"apiVersion": "opensrm/v1", "kind": "ServiceReliabilityManifest",
        "metadata": {"name": "my-service", "team": "t", "tier": "standard"},
        "spec": {"type": "api"}}


@pytest.mark.parametrize("fmt", ["auto", "srm_v1", "opensrm_v2", "legacy", None])
def test_opensrm_v1_is_rejected_with_the_migrate_command(tmp_path, fmt):
    path = tmp_path / "svc.yaml"
    path.write_text(yaml.safe_dump(_DOC))
    with warnings.catch_warnings():
        warnings.simplefilter("error", LegacyFormatWarning)   # never reaches the legacy branch
        with pytest.raises(ManifestLoadError) as exc:
            load_manifest(path, format=fmt)
    msg = str(exc.value)
    assert "opensrm/v1" in msg and "nthlayer migrate-manifest" in msg
    assert "service.name is required" not in msg


def test_migration_api_is_public():
    for name in ("convert_opensrm_v1_to_v2", "is_opensrm_v1_format", "MigrationResult",
                 "UnmappedField", "OPENSRM_V1_API_VERSION"):
        assert name in manifest.__all__ and hasattr(manifest, name), name
```

- [ ] **Step 2: Run, expect FAIL** ("service.name is required").

- [ ] **Step 3: Implement.** In `load_manifest`, immediately after the `Expected YAML object` check and before `_detect_format`:

```python
    # The published OpenSRM v1 schema is migrate-only: NthLayer's v1 dialect is
    # srm/v1. Rejected before format dispatch so no explicit format= can push it
    # into a parser that misreads it (opensrm-pnmv). See
    # docs/superpowers/decisions/opensrm-v1-support.md in the nthlayer front door.
    if is_opensrm_v1_format(data):
        raise ManifestLoadError(OPENSRM_V1_REJECTION.format(path=file_path))
```

Add the import, the `__init__` re-exports and `__all__` group, and the three doc edits. The upgrading bullet: "**New in 5.3.0:** `load_manifest` rejects `apiVersion: opensrm/v1` (the published v1 schema) with an error naming `nthlayer migrate-manifest`, instead of 'service.name is required'. `convert_opensrm_v1_to_v2(data, *, service_type=None) -> MigrationResult(manifest, unmapped)` converts it to v2 following AUTHORING §7; `unmapped` lists every field with no v2 home. v2 `spec.dependencies[].service` now accepts `resource:` refs."

- [ ] **Step 4: Run, full suite, ruff.** — **Step 5: Commit** — `feat(manifest): load_manifest rejects opensrm/v1 and names the migrate command (opensrm-pnmv)`.

### Task 8: The spec's own examples and schema as fixtures

**Files:**
- Create: `nthlayer-common/tests/test_opensrm_v1_against_spec.py`
- Create: `nthlayer-common/tests/test_opensrm_v1_schema_completeness.py`

**Interfaces:** Consumes everything above; `jsonschema` (common dev extra).

- [ ] **Step 1: Write the example tests.** The expected unmapped lists below are derived from each example's keys and the spec's §4 table. Before running anything, open each example under `opensrm/examples/` and confirm every listed path exists in it and that no other key in it is unmapped by §4 — if the file differs from this list, fix the list to the file (and say so in the report); never fix it to the converter's output.

```python
"""The spec's own opensrm/v1 examples convert, validate and parse (opensrm-pnmv)."""
import json
from pathlib import Path

import jsonschema
import pytest
import yaml

from nthlayer_common.manifest import ManifestLoadError, load_manifest
from nthlayer_common.manifest.opensrm_v1 import convert_opensrm_v1_to_v2
from nthlayer_common.manifest.parser.v2 import parse_opensrm_v2

# parents: [0]=tests/ [1]=nthlayer-common/ [2]=<ecosystem>/
OPENSRM = Path(__file__).resolve().parents[2] / "opensrm"
EXAMPLES = OPENSRM / "examples"
V2_SCHEMA = OPENSRM / "spec" / "v2" / "schema.json"
REFERENCE = OPENSRM / "spec" / "v2" / "examples" / "migration" / "api-full-v2.yaml"

_OBS = ["spec.observability.metrics", "spec.observability.dashboards", "spec.observability.alerts"]
EXPECTED: dict[str, tuple[str | None, list[str]]] = {
    # file: (service_type to supply, unmapped paths in document order)
    "ai-gate-full.yaml": (None, [
        "spec.contract.judgment", "spec.slos.latency.p99",
        "spec.slos.judgment.reversal_rate", "spec.slos.judgment.high_confidence_failure",
        "spec.slos.judgment.calibration", "spec.instrumentation.attributes",
        "spec.dependencies[0].critical", "spec.dependencies[1].critical", "spec.dependencies[2].critical",
        *_OBS]),
    "ai-gate-minimal.yaml": (None, ["spec.observability.metrics", "spec.slos.judgment.reversal_rate"]),
    "ai-gate-security-scanner.yaml": (None, [
        "spec.observability.metrics", "spec.slos.judgment.reversal_rate",
        "spec.slos.judgment.high_confidence_failure", "spec.instrumentation.attributes"]),
    "api-full.yaml": ("api", [
        "spec.slos.latency.p50", "spec.slos.latency.p99", "spec.slos.throughput",
        "spec.dependencies[0].critical", "spec.dependencies[1].critical",
        "spec.dependencies[2].critical", "spec.dependencies[2].manifest", "spec.dependencies[3].critical",
        "spec.ownership.email", "spec.ownership.pagerduty.escalation_policy_id",
        "spec.notifications", *_OBS, "spec.observability.tracing", "spec.deployment"]),
    "api-internal.yaml": ("api", [
        "spec.slos.latency.p95", "spec.dependencies[0].critical", "spec.dependencies[1].critical",
        "spec.ownership.email", *_OBS, "spec.observability.tracing", "spec.deployment"]),
    "api-minimal.yaml": (None, ["spec.observability.metrics"]),
    "batch-etl.yaml": (None, [
        "spec.slos.success_rate", "spec.slos.duration.p95", "spec.slos.schedule_adherence",
        "spec.slos.data_freshness", "spec.slos.throughput",
        "spec.dependencies[0].critical", "spec.dependencies[1].critical", "spec.dependencies[2].critical",
        "spec.ownership.email", *_OBS, "spec.deployment"]),
    "database-mysql.yaml": (None, [
        "spec.slos.query_latency.p50", "spec.slos.query_latency.p99", "spec.slos.replication_lag",
        "spec.slos.throughput", "spec.dependencies[0].critical", "spec.dependencies[1].critical",
        "spec.ownership.email", "spec.ownership.pagerduty.escalation_policy_id", *_OBS, "spec.deployment"]),
}


def test_the_spec_examples_are_present():
    found = sorted(p.name for p in EXAMPLES.glob("*.yaml")
                   if yaml.safe_load(p.read_text()).get("apiVersion") == "opensrm/v1")
    assert found == sorted(EXPECTED), "the opensrm sibling is missing or its v1 examples changed"
    assert V2_SCHEMA.is_file() and REFERENCE.is_file()


@pytest.mark.parametrize("name", sorted(EXPECTED))
def test_example_converts_validates_and_parses(name):
    service_type, unmapped = EXPECTED[name]
    doc = yaml.safe_load((EXAMPLES / name).read_text())
    r = convert_opensrm_v1_to_v2(doc, service_type=service_type)
    assert sorted(f.path for f in r.unmapped) == sorted(unmapped)
    jsonschema.validate(r.manifest, json.loads(V2_SCHEMA.read_text()))
    parse_opensrm_v2(r.manifest)


@pytest.mark.parametrize("name", sorted(EXPECTED))
def test_load_manifest_rejects_every_example(name):
    with pytest.raises(ManifestLoadError, match="nthlayer migrate-manifest"):
        load_manifest(EXAMPLES / name)


def test_api_full_matches_the_spec_reference_on_mapped_fields():
    """Excluded (the reference author's decisions or inventions, or unmapped by
    §4): fallback, api_ref, technical_contact, the backstage.io/component-ref
    annotation, metadata.namespace, instrumentation, displayName wording, and
    the throughput SLO."""
    got = convert_opensrm_v1_to_v2(yaml.safe_load((EXAMPLES / "api-full.yaml").read_text()),
                                   service_type="api").manifest
    ref = yaml.safe_load(REFERENCE.read_text())
    assert (got["apiVersion"], got["kind"]) == (ref["apiVersion"], ref["kind"])
    assert got["metadata"]["name"] == ref["metadata"]["name"]
    assert got["metadata"]["labels"] == ref["metadata"]["labels"]
    ref_ann = {k: v for k, v in ref["metadata"]["annotations"].items() if k != "backstage.io/component-ref"}
    assert got["metadata"]["annotations"] == ref_ann
    assert {k: got["spec"]["owner"][k] for k in ("group", "escalation")} == \
           {k: ref["spec"]["owner"][k] for k in ("group", "escalation")}
    assert got["spec"]["service"] == ref["spec"]["service"]

    def targets(slos):
        return {d["metadata"]["name"]: d["spec"]["objectives"][0]["target"]
                for d in slos if not d["metadata"]["name"].endswith("throughput")}
    assert targets(got["spec"]["slo"]) == targets(ref["spec"]["slo"])
    (c,) = got["spec"]["contracts"]
    (rc,) = ref["spec"]["contracts"]
    assert (c["name"], c["promise"], c["contract_owner"]) == (rc["name"], rc["promise"], rc["contract_owner"])
    strip = lambda deps: [{k: v for k, v in d.items() if k != "fallback"} for d in deps]
    assert got["spec"]["dependencies"] == strip(ref["spec"]["dependencies"])
```

Note the reference's annotations include `pagerduty.com/service-id: "PXXXXXX"` and `slack.com/channel` — the v1 file's values must produce exactly those; if the reference uses a placeholder the v1 file does not contain, exclude that key from the comparison and list it in the docstring.

- [ ] **Step 2: Write the schema-completeness test** (the test this bead owns):

```python
"""Every opensrm/v1 schema property is converted or reported (opensrm-pnmv).

Read from opensrm/spec/v1/schema.json, so a field the schema gains is caught
here rather than dropped silently by the converter. Both ways: the converter
may not claim a key the schema does not define.
"""
import json
from pathlib import Path

import pytest

from nthlayer_common.manifest.opensrm_v1 import _SECTIONS

V1_SCHEMA = Path(__file__).resolve().parents[2] / "opensrm" / "spec" / "v1" / "schema.json"
DEFINITIONS = json.loads(V1_SCHEMA.read_text())["definitions"] if V1_SCHEMA.is_file() else {}


def test_the_v1_schema_is_present_and_every_section_is_a_real_definition():
    assert V1_SCHEMA.is_file()
    assert sorted(_SECTIONS) and set(_SECTIONS) <= set(DEFINITIONS)
    assert len(_SECTIONS) >= 20


@pytest.mark.parametrize("definition", sorted(_SECTIONS))
def test_section_covers_the_schema_both_ways(definition):
    converted, unmapped = _SECTIONS[definition]
    assert not converted & set(unmapped)
    assert converted | set(unmapped) == set(DEFINITIONS[definition].get("properties", {})), definition


@pytest.mark.parametrize("definition", ["Spec", "Metadata", "SLOs", "JudgmentSLOs", "Contract",
                                        "Dependency", "Ownership", "Observability", "Instrumentation"])
def test_the_sections_the_spec_names_are_covered(definition):
    assert definition in _SECTIONS
```

`len(_SECTIONS) >= 20` is the non-vacuity floor: count the entries Tasks 3–6 define and set the floor to that exact count.

- [ ] **Step 3: Run.** Any failure is a real gap: fix the converter (or the expected list, if it disagrees with the example file), never the assertion's direction. — **Step 4: Full suite, ruff.** — **Step 5: Commit** — `test(manifest): the spec's opensrm/v1 examples and schema pin the converter (opensrm-pnmv)`.

**Checkpoint B:** R5-gate nthlayer-common (base = branch point, head = Task 8; correctness → clarity → edge-cases → provenance, then advisory excellence). Push, open the PR, hold. On Rob's approval: merge (`--merge --body ""`), squash the release PR (5.3.0), verify on PyPI, then sync the local checkout.

---

## Checkpoint C — consumers (worktrees `nthlayer-generate-pnmv`, then the four floor repos)

### Task 9: `migrate-manifest` converts opensrm/v1

**Files:**
- Modify: `nthlayer-generate/src/nthlayer_generate/cli/migrate_manifest.py`
- Modify: `nthlayer-generate/pyproject.toml` (floor `nthlayer-common>=5.3.0,<6.0.0` with a `WHY 5.3.0 (opensrm-pnmv)` line), `uv.lock` (relock)
- Modify: the migrate-manifest docs page if one exists (`grep -rln "migrate-manifest" nthlayer-generate/docs-site nthlayer-generate/README.md`): document `opensrm/v1`, `--allow-lossy`, `--service-type`.
- Test: `nthlayer-generate/tests/test_cli_migrate_manifest.py` (extend)

**Interfaces:**
- Consumes: `convert_opensrm_v1_to_v2`, `is_opensrm_v1_format` (nthlayer-common 5.3.0, `nthlayer_common.manifest.opensrm_v1`).
- Produces: `migrate_manifest_command(manifest_path, output_path=None, dry_run=False, force=False, allow_lossy=False, service_type=None) -> int`; flags `--allow-lossy`, `--service-type`.

- [ ] **Step 1: Write the failing tests** (add a class to the existing file; reuse its fixtures' style — they assert exit codes and file state, never stdout text):

```python
class TestOpensrmV1:
    """opensrm/v1 → v2 (opensrm-pnmv). Fixture: the shape of the spec's
    opensrm/examples/api-minimal.yaml, which converts without loss."""

    def _write(self, tmp_path, **spec):
        doc = {"apiVersion": "opensrm/v1", "kind": "ServiceReliabilityManifest",
               "metadata": {"name": "my-service", "team": "platform", "tier": "standard"},
               "spec": {"type": "api", "slos": {"availability": {"target": 0.999, "window": "30d"}}, **spec}}
        p = tmp_path / "svc.yaml"
        p.write_text(yaml.safe_dump(doc))
        return p

    def test_lossless_converts(self, tmp_path):
        p = self._write(tmp_path)
        assert migrate_manifest_command(str(p)) == 0
        out = yaml.safe_load((tmp_path / "svc.v2.yaml").read_text())
        assert out["apiVersion"] == "opensrm.nthlayer.io/v2"

    def test_lossy_refuses_without_the_flag(self, tmp_path):
        p = self._write(tmp_path, deployment={"gates": {}})
        assert migrate_manifest_command(str(p)) == 1
        assert not (tmp_path / "svc.v2.yaml").exists()

    def test_lossy_writes_with_the_flag(self, tmp_path):
        p = self._write(tmp_path, deployment={"gates": {}})
        assert migrate_manifest_command(str(p), allow_lossy=True) == 0
        assert "deployment" not in yaml.safe_load((tmp_path / "svc.v2.yaml").read_text())["spec"]

    def test_missing_type_needs_service_type(self, tmp_path):
        p = self._write(tmp_path)
        doc = yaml.safe_load(p.read_text())
        del doc["spec"]["type"]
        p.write_text(yaml.safe_dump(doc))
        assert migrate_manifest_command(str(p)) == 1
        assert migrate_manifest_command(str(p), service_type="api") == 0

    def test_unconvertible_document_returns_1(self, tmp_path):
        p = self._write(tmp_path)
        doc = yaml.safe_load(p.read_text())
        doc["metadata"]["tier"] = "gold"
        p.write_text(yaml.safe_dump(doc))
        assert migrate_manifest_command(str(p), allow_lossy=True) == 1

    def test_flags_are_wired(self):
        parser = build_parser()   # import from nthlayer_generate.demo
        args = parser.parse_args(["migrate-manifest", "x.yaml", "--allow-lossy", "--service-type", "api"])
        assert (args.allow_lossy, args.service_type) == (True, "api")
```

Keep `test_unsupported_input_apiversion_returns_1` passing (an unknown apiVersion still exits 1).

- [ ] **Step 2: Bump the floor and relock first** (`uv lock`), run the tests — expect the new ones to FAIL.

- [ ] **Step 3: Implement.** Register `--allow-lossy` (`action="store_true"`, help "Write the v2 manifest even though some opensrm/v1 fields have no v2 equivalent (they are listed)") and `--service-type` (help "spec.service.type to use when an opensrm/v1 manifest has no spec.type"); pass both through `handle_migrate_manifest_command`. In `migrate_manifest_command`, replace the single `convert_v1_to_v2` call with:

```python
    api_version = data.get("apiVersion")
    if is_opensrm_v1_format(data):
        source = "opensrm/v1"
        try:
            result = convert_opensrm_v1_to_v2(data, service_type=service_type)
        except ValueError as exc:
            error(f"Cannot convert {manifest_path}: {exc}")
            return 1
        for field in result.unmapped:
            warning(f"Not migrated: {field.path} — {field.reason}")
        if result.unmapped and not allow_lossy:
            error(
                f"{len(result.unmapped)} field(s) in {manifest_path} have no v2 equivalent; "
                "nothing written. Re-run with --allow-lossy to write the v2 manifest without them."
            )
            return 1
        v2_data = result.manifest
    elif api_version == "srm/v1":
        source = "srm/v1"
        try:
            v2_data = convert_v1_to_v2(data)
        except ValueError as exc:
            error(f"Cannot convert {manifest_path}: {exc}")
            return 1
    else:
        error(f"Cannot convert {manifest_path}: apiVersion {api_version!r} is not srm/v1 or opensrm/v1")
        return 1
```

Then call `parse_opensrm_v2(v2_data, base_dir=in_path.parent)` (so an `openslo[]` `$ref` resolves next to the input) and use `source` in the header comment (`# OpenSRM v2 manifest (migrated from {source})`). Import `warning` from `nthlayer_generate.cli.ux`. Keep the `srm/v1` path's behaviour identical.

- [ ] **Step 4: Run the CLI tests, the full suite (`uv run pytest -p no:cacheprovider -o addopts= -q`), ruff, and the dependency guards.** — **Step 5: Commit** — `feat: migrate-manifest converts opensrm/v1 manifests (opensrm-pnmv)` (floor bump and relock in the same commit, or a preceding `deps: require nthlayer-common 5.3.0 (opensrm-pnmv)`).

### Task 10: Floor bumps in core, bench, workers, override-adapter

**Files (each repo, batched in one dispatch):** `pyproject.toml` (floor `nthlayer-common>=5.3.0,<6.0.0`; replace the `WHY 5.2.0 (opensrm-g35i)` line with `WHY 5.3.0 (opensrm-pnmv)` keeping the "bump on every minor" sentence), `uv.lock` (relock).

- [ ] **Step 1:** In each repo (main checkout is fine: one branch `chore/pnmv-common-5.3` per repo), edit the floor, `uv lock`, run the dependency guard (`tests/test_dependency_declarations.py`) and the full suite, ruff.
- [ ] **Step 2:** Commit `deps: require nthlayer-common 5.3.0 (opensrm-pnmv)` in each.

**Checkpoint C:** R5-gate generate (Task 9) and the four floor commits. Push, open PRs held (generate, core, bench, workers, adapter, plus the front-door docs PR from Checkpoint A). On Rob's approval: merge, squash the five release PRs, verify each on PyPI with a clean co-install of all six packages, run eco-doctor, close opensrm-pnmv, and file the follow-up beads:

- workers' measure manifest loader reads a third v1 shape (`measure/manifest.py`);
- the srm/v1 lift (`convert_v1_to_v2`) silently drops fields;
- convert v1 judgment SLOs once opensrm-a742 lands; convert success_rate/processing_time/lag once opensrm-47tt lands;
- v2 dependency `type` for `resource:` refs is still inferred as `api` (`parser/v2.py` dependency loop);
- nthlayer-generate's README and docs-site advertise `opensrm/v1` examples.
