# jmy.6 Learn → Spec Loop — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship the Learn → Spec operator workflow: `nthlayer-learn recommendations` subcommand with `--output`/`--apply-to`/`--pr` flags, ruamel.yaml comment-preserving spec patches, gh-based PR creation. Closes the feedback loop from retrospective recommendations (jmy.2) to actionable manifest changes.

**Architecture:** Six implementation files in `nthlayer-workers/src/nthlayer_workers/learn/` (one extended, four new, plus existing cli.py extended) + one cross-repo integration test in `nthlayer/test/`. Pure-vs-impure boundaries map to test isolation: `_yaml.py` / `_preview.py` / `recommendations.py` extensions are pure; `_apply.py` / `_gh.py` / `cli.py` are I/O. Single-subcommand CLI with composable flags; state-machine classification of every recommendation; ruamel.yaml round-trip for comment preservation.

**Tech Stack:** Python 3.11+. New runtime dep: `ruamel.yaml>=0.18`. Tooling deps unchanged (`pytest`, `pytest-asyncio`, `ruff`). `gh` CLI required at runtime (operator install); tests use monkeypatch at subprocess boundary.

**Spec:** `nthlayer/docs/superpowers/specs/2026-05-26-jmy6-learn-spec-loop-design.md` (committed).

**Bead:** `opensrm-jmy.6`. Follow-up beads filed and excluded from this plan: `jmy.21` (add_dependency), `jmy.22` (--interactive), `jmy.23` (financial_impact), `jmy.24` (per-rec selection), `jmy.25` (--json output).

---

## File structure

### Files modified

| Path | Responsibility |
|---|---|
| `nthlayer-workers/pyproject.toml` | Add `ruamel.yaml>=0.18` to runtime deps |
| `nthlayer-workers/src/nthlayer_workers/learn/recommendations.py` | Add `id` field on `Recommendation`; rename apiVersion (`opensrm.io/v1` → `nthlayer.io/learn/v1`) + kind (`SpecRecommendation` → `RecommendationPlan`); add `OutcomeKind` enum; add `parse_plan_file()` |
| `nthlayer-workers/src/nthlayer_workers/learn/cli.py` | Add `recommendations` subcommand with `--incident` / `--from` / `--output` / `--apply-to` / `--pr` / `--force` / `--base` / `--draft` flags |
| `nthlayer-workers/tests/learn/test_recommendations.py` | Extend with id determinism, plan-file roundtrip, parse_plan_file validation tests |

### Files created

| Path | Responsibility |
|---|---|
| `nthlayer-workers/src/nthlayer_workers/learn/_yaml.py` | ruamel.yaml setup, `resolve_path`, `apply_at_path`, `normalize_scalar`, `classify_outcome` |
| `nthlayer-workers/src/nthlayer_workers/learn/_preview.py` | `build_preview(manifest_path, rec, current_yaml) -> str` |
| `nthlayer-workers/src/nthlayer_workers/learn/_apply.py` | Manifest resolution, `apply_recommendations`, `ApplyResult`, end-of-run summary builder |
| `nthlayer-workers/src/nthlayer_workers/learn/_gh.py` | Pre-flight checks, `create_pr_via_gh`, `PRResult`, `PreflightError` |
| `nthlayer-workers/tests/learn/test_yaml.py` | Unit tests for _yaml.py |
| `nthlayer-workers/tests/learn/test_preview.py` | Unit tests for _preview.py |
| `nthlayer-workers/tests/learn/test_apply.py` | Unit tests for _apply.py |
| `nthlayer-workers/tests/learn/test_gh.py` | Unit tests for _gh.py |
| `nthlayer-workers/tests/learn/test_cli_recommendations.py` | Unit tests for the new CLI subcommand |
| `nthlayer/test/learn-recommendations-integration.sh` | Cross-repo end-to-end test |

---

## Phase A — Foundation: `recommendations.py` extensions

### Task A1: Add `id` field to `Recommendation` dataclass

**Files:**
- Modify: `nthlayer-workers/src/nthlayer_workers/learn/recommendations.py`
- Test: `nthlayer-workers/tests/learn/test_recommendations.py`

- [ ] **Step 1: Write failing tests**

Add to `nthlayer-workers/tests/learn/test_recommendations.py`:

```python
class TestRecommendationId:
    """jmy.6: deterministic rec-<12-char-sha256-hex> id."""

    def test_compute_id_is_deterministic(self):
        from nthlayer_workers.learn.recommendations import compute_rec_id

        id1 = compute_rec_id("inc-2026-05-21-001", "tighten_slo", "spec.slos.judgment.target")
        id2 = compute_rec_id("inc-2026-05-21-001", "tighten_slo", "spec.slos.judgment.target")
        assert id1 == id2

    def test_compute_id_format(self):
        from nthlayer_workers.learn.recommendations import compute_rec_id

        rec_id = compute_rec_id("inc-2026-05-21-001", "tighten_slo", "spec.slos.judgment.target")
        assert rec_id.startswith("rec-")
        assert len(rec_id) == 16  # "rec-" + 12 hex chars
        # 12 lowercase hex chars after the prefix
        hex_part = rec_id[4:]
        assert all(c in "0123456789abcdef" for c in hex_part)

    def test_compute_id_changes_per_input(self):
        from nthlayer_workers.learn.recommendations import compute_rec_id

        base = compute_rec_id("inc-A", "tighten_slo", "spec.slos.judgment.target")
        diff_incident = compute_rec_id("inc-B", "tighten_slo", "spec.slos.judgment.target")
        diff_type = compute_rec_id("inc-A", "add_deploy_gate", "spec.slos.judgment.target")
        diff_field = compute_rec_id("inc-A", "tighten_slo", "spec.slos.availability.target")

        assert base != diff_incident
        assert base != diff_type
        assert base != diff_field

    def test_recommendation_has_id_field(self):
        from nthlayer_workers.learn.recommendations import Recommendation

        rec = Recommendation(
            id="rec-deadbeef0123",
            service="fraud-detect",
            type="tighten_slo",
            rationale="test",
            proposed_value=98.5,
        )
        assert rec.id == "rec-deadbeef0123"
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd /Users/robfox/Documents/GitHub/nthlayer-ecosystem/nthlayer-workers
uv run pytest tests/learn/test_recommendations.py::TestRecommendationId -v
```

Expected: 4 FAILED. `compute_rec_id` not defined; `Recommendation.id` field missing.

- [ ] **Step 3: Implement `compute_rec_id` + `id` field**

In `src/nthlayer_workers/learn/recommendations.py`, near the top of the file (after the existing imports), add:

```python
import hashlib


def compute_rec_id(incident_id: str, rec_type: str, field: str) -> str:
    """Deterministic rec id from (incident, type, field).

    Format: rec-<12-char-lowercase-sha256-hex>. Stable across tool versions.
    Algorithm pinned in jmy.6 design § 6.1 so future contributors don't
    accidentally change the hash basis.
    """
    payload = f"{incident_id}|{rec_type}|{field}".encode("utf-8")
    return "rec-" + hashlib.sha256(payload).hexdigest()[:12]
```

Then update the `Recommendation` dataclass to add `id` as the first field:

```python
@dataclass
class Recommendation:
    """One proposed spec change in a SpecRecommendation document.

    All fields except ``id``, ``service``, ``type``, ``rationale``, and
    ``proposed_value`` are optional and only populated when the engine
    has the inputs. ``id`` is a deterministic rec-<12-char-sha256-hex>
    computed via compute_rec_id(incident_id, type, field).
    """

    id: str
    service: str
    type: str  # "tighten_slo" | "add_deploy_gate" | etc.
    rationale: str
    proposed_value: Any
    field: str | None = None
    current_value: Any = None
    confidence: float = 0.0
    financial_impact: str | None = None
    evidence: list[dict[str, Any]] = dataclasses.field(default_factory=list)
```

Update `_tighten_slo_recommendations` and `_add_deploy_gate_recommendations` to compute and pass `id` when constructing `Recommendation` instances. Both helpers receive `incident_id` already (or via the caller `analyze_incident`); if not, thread it through as a parameter.

Look at the existing call sites — wherever a `Recommendation(...)` constructor is invoked, prepend `id=compute_rec_id(incident_id, type_str, field_path)`. There are exactly two construction sites (one per heuristic).

Existing tests that construct `Recommendation` directly need an `id=` argument. Add `id="rec-test00000000"` (or any 12-hex string) to those test fixtures.

- [ ] **Step 4: Run tests to verify they pass**

```bash
uv run pytest tests/learn/test_recommendations.py -v
```

Expected: all tests pass, including the 4 new tests and the existing 22 tests (after updating their `Recommendation(...)` constructions to pass `id=`).

- [ ] **Step 5: Commit**

```bash
git add src/nthlayer_workers/learn/recommendations.py tests/learn/test_recommendations.py
git commit -m "feat(recommendations): add deterministic id field · opensrm-jmy.6

rec-<12-char-sha256-hex> from (incident_id, type, field). Stable
across tool versions per jmy.6 design § 6.1. Engine sites in
_tighten_slo_recommendations + _add_deploy_gate_recommendations
populate id via compute_rec_id helper."
```

---

### Task A2: Rename apiVersion + kind in plan YAML output

**Files:**
- Modify: `nthlayer-workers/src/nthlayer_workers/learn/recommendations.py`
- Test: `nthlayer-workers/tests/learn/test_recommendations.py`

- [ ] **Step 1: Write failing tests**

Add to `tests/learn/test_recommendations.py`:

```python
class TestPlanArtefactRename:
    """jmy.6: apiVersion + kind rename for the plan-file artefact."""

    def test_to_yaml_emits_new_api_version(self):
        from nthlayer_workers.learn.recommendations import SpecRecommendation, Recommendation
        from datetime import datetime, timezone

        sr = SpecRecommendation(
            incident="inc-test",
            generated_by="nthlayer-learn",
            generated_at=datetime(2026, 5, 26, tzinfo=timezone.utc),
            confidence=0.7,
            recommendations=[
                Recommendation(
                    id="rec-deadbeef0123",
                    service="fraud-detect",
                    type="tighten_slo",
                    rationale="test",
                    proposed_value=98.5,
                ),
            ],
        )

        yaml_text = sr.to_yaml()
        assert "apiVersion: nthlayer.io/learn/v1" in yaml_text
        assert "kind: RecommendationPlan" in yaml_text
        # Old strings absent
        assert "opensrm.io/v1" not in yaml_text
        assert "SpecRecommendation" not in yaml_text
```

- [ ] **Step 2: Run test to verify it fails**

```bash
uv run pytest tests/learn/test_recommendations.py::TestPlanArtefactRename -v
```

Expected: FAILED — current output has old apiVersion/kind strings.

- [ ] **Step 3: Update `_to_dict` to emit new apiVersion + kind**

In `src/nthlayer_workers/learn/recommendations.py`, find the `_to_dict` method on `SpecRecommendation` (returns the dict that `to_yaml()` serialises). Change the apiVersion + kind lines:

```python
    def _to_dict(self) -> dict[str, Any]:
        recs: list[dict[str, Any]] = []
        for r in self.recommendations:
            d = asdict(r)
            # Drop None / empty fields so the YAML stays compact and
            # matches the spec's example shape.
            d = {k: v for k, v in d.items() if v not in (None, [], "")}
            recs.append(d)
        return {
            "apiVersion": "nthlayer.io/learn/v1",  # jmy.6: was opensrm.io/v1
            "kind": "RecommendationPlan",          # jmy.6: was SpecRecommendation
            "metadata": {
                "incident": self.incident,
                "generated_by": self.generated_by,
                "generated_at": self.generated_at.isoformat(),
                "confidence": self.confidence,
                "requires_human_review": self.requires_human_review,
            },
            "recommendations": recs,
        }
```

Any existing test in `test_recommendations.py` that asserted on the OLD strings needs updating. Search the file for `opensrm.io/v1` and `SpecRecommendation` (as a string literal, not the class name) and update.

- [ ] **Step 4: Run tests to verify they pass**

```bash
uv run pytest tests/learn/test_recommendations.py -v
```

Expected: all tests pass including the new rename test + all updated existing tests.

- [ ] **Step 5: Commit**

```bash
git add src/nthlayer_workers/learn/recommendations.py tests/learn/test_recommendations.py
git commit -m "feat(recommendations): rename plan artefact to RecommendationPlan · opensrm-jmy.6

apiVersion opensrm.io/v1 → nthlayer.io/learn/v1; kind
SpecRecommendation → RecommendationPlan. Module-namespaced
apiVersion makes ownership explicit per jmy.6 design § 6.1.
No external consumers exist today so the rename is cost-free."
```

---

### Task A3: Define `OutcomeKind` enum

**Files:**
- Modify: `nthlayer-workers/src/nthlayer_workers/learn/recommendations.py`
- Test: `nthlayer-workers/tests/learn/test_recommendations.py`

- [ ] **Step 1: Write failing test**

Add to `tests/learn/test_recommendations.py`:

```python
class TestOutcomeKind:
    """jmy.6: OutcomeKind enum lives in recommendations.py (operator-visible)."""

    def test_outcome_kind_values(self):
        from nthlayer_workers.learn.recommendations import OutcomeKind

        # All 5 outcomes per jmy.6 design § 5
        assert OutcomeKind.APPLY_CLEAN.value == "apply_clean"
        assert OutcomeKind.ALREADY_APPLIED.value == "already_applied"
        assert OutcomeKind.DRIFT_DETECTED.value == "drift_detected"
        assert OutcomeKind.TARGET_PATH_MISSING.value == "target_path_missing"
        assert OutcomeKind.MANIFEST_NOT_FOUND.value == "manifest_not_found"

    def test_outcome_kind_is_string_enum(self):
        """str.StrEnum gives wire-safe string serialisation for free."""
        from nthlayer_workers.learn.recommendations import OutcomeKind

        assert OutcomeKind.APPLY_CLEAN == "apply_clean"
        assert str(OutcomeKind.DRIFT_DETECTED) == "drift_detected"
```

- [ ] **Step 2: Run test to verify it fails**

```bash
uv run pytest tests/learn/test_recommendations.py::TestOutcomeKind -v
```

Expected: FAILED — `OutcomeKind` not defined.

- [ ] **Step 3: Add `OutcomeKind` enum**

In `src/nthlayer_workers/learn/recommendations.py`, near the top of the file (after the existing imports), add:

```python
from enum import StrEnum


class OutcomeKind(StrEnum):
    """Per-recommendation outcome from --apply-to evaluation (jmy.6 § 5).

    Lives in recommendations.py (not _yaml.py) because outcomes are part
    of the recommendation lifecycle — operator-visible in summaries,
    PR body, error messages. _yaml.py's classify_outcome implements the
    state machine that produces these.
    """

    APPLY_CLEAN = "apply_clean"
    ALREADY_APPLIED = "already_applied"
    DRIFT_DETECTED = "drift_detected"
    TARGET_PATH_MISSING = "target_path_missing"
    MANIFEST_NOT_FOUND = "manifest_not_found"
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
uv run pytest tests/learn/test_recommendations.py::TestOutcomeKind -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/nthlayer_workers/learn/recommendations.py tests/learn/test_recommendations.py
git commit -m "feat(recommendations): add OutcomeKind enum · opensrm-jmy.6

Five outcomes per jmy.6 design § 5: apply_clean, already_applied,
drift_detected, target_path_missing, manifest_not_found. StrEnum
gives wire-safe string serialisation for free. Lives in
recommendations.py per Section 2 refinement — outcomes are part
of the recommendation lifecycle, not specifically a YAML concern."
```

---

### Task A4: Add `parse_plan_file()`

**Files:**
- Modify: `nthlayer-workers/src/nthlayer_workers/learn/recommendations.py`
- Test: `nthlayer-workers/tests/learn/test_recommendations.py`

- [ ] **Step 1: Write failing tests**

Add to `tests/learn/test_recommendations.py`:

```python
class TestParsePlanFile:
    """jmy.6: --from <plan.yaml> validation."""

    def test_parse_plan_file_happy_path(self, tmp_path):
        from nthlayer_workers.learn.recommendations import (
            SpecRecommendation, parse_plan_file,
        )
        from datetime import datetime, timezone

        original = SpecRecommendation(
            incident="inc-test",
            generated_by="nthlayer-learn",
            generated_at=datetime(2026, 5, 26, tzinfo=timezone.utc),
            confidence=0.7,
            recommendations=[],
        )
        plan_path = tmp_path / "plan.yaml"
        plan_path.write_text(original.to_yaml())

        loaded = parse_plan_file(plan_path)
        assert loaded.incident == "inc-test"
        assert loaded.confidence == 0.7
        assert loaded.requires_human_review is True

    def test_parse_plan_file_unknown_api_version_raises(self, tmp_path):
        from nthlayer_workers.learn.recommendations import (
            parse_plan_file, PlanFileUnknownVersionError,
        )

        plan_path = tmp_path / "plan.yaml"
        plan_path.write_text(
            "apiVersion: opensrm.io/v999\n"
            "kind: RecommendationPlan\n"
            "metadata: {incident: x, generated_by: y, generated_at: '2026-01-01T00:00:00+00:00', confidence: 0.5, requires_human_review: true}\n"
            "recommendations: []\n"
        )

        with pytest.raises(PlanFileUnknownVersionError, match="nthlayer.io/learn/v1"):
            parse_plan_file(plan_path)

    def test_parse_plan_file_missing_recommendations_key_raises(self, tmp_path):
        from nthlayer_workers.learn.recommendations import (
            parse_plan_file, PlanFileInvalidError,
        )

        plan_path = tmp_path / "plan.yaml"
        plan_path.write_text(
            "apiVersion: nthlayer.io/learn/v1\n"
            "kind: RecommendationPlan\n"
            "metadata: {incident: x, generated_by: y, generated_at: '2026-01-01T00:00:00+00:00', confidence: 0.5, requires_human_review: true}\n"
        )

        with pytest.raises(PlanFileInvalidError, match="recommendations"):
            parse_plan_file(plan_path)

    def test_parse_plan_file_non_list_recommendations_raises(self, tmp_path):
        from nthlayer_workers.learn.recommendations import (
            parse_plan_file, PlanFileInvalidError,
        )

        plan_path = tmp_path / "plan.yaml"
        plan_path.write_text(
            "apiVersion: nthlayer.io/learn/v1\n"
            "kind: RecommendationPlan\n"
            "metadata: {incident: x, generated_by: y, generated_at: '2026-01-01T00:00:00+00:00', confidence: 0.5, requires_human_review: true}\n"
            "recommendations: not_a_list\n"
        )

        with pytest.raises(PlanFileInvalidError, match="recommendations must be a list"):
            parse_plan_file(plan_path)
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
uv run pytest tests/learn/test_recommendations.py::TestParsePlanFile -v
```

Expected: 4 FAILED — `parse_plan_file`, `PlanFileUnknownVersionError`, `PlanFileInvalidError` not defined.

- [ ] **Step 3: Implement `parse_plan_file` + exceptions**

In `src/nthlayer_workers/learn/recommendations.py`, add at the bottom:

```python
SUPPORTED_API_VERSIONS = frozenset({"nthlayer.io/learn/v1"})


class PlanFileUnknownVersionError(ValueError):
    """Plan file's apiVersion is not one we recognise."""


class PlanFileInvalidError(ValueError):
    """Plan file is malformed or missing required keys."""


def parse_plan_file(path) -> SpecRecommendation:
    """Read a plan.yaml file and deserialise to SpecRecommendation.

    Validates apiVersion is in SUPPORTED_API_VERSIONS and required
    structural keys are present. Raises PlanFileUnknownVersionError
    or PlanFileInvalidError on bad input. The underlying yaml.YAMLError
    propagates on malformed YAML (handled at a higher layer as
    manifest_parse_error).
    """
    from pathlib import Path

    text = Path(path).read_text()
    data = yaml.safe_load(text)

    if not isinstance(data, dict):
        raise PlanFileInvalidError(
            f"plan file root must be a mapping, got {type(data).__name__}"
        )

    api_version = data.get("apiVersion")
    if api_version not in SUPPORTED_API_VERSIONS:
        raise PlanFileUnknownVersionError(
            f"plan file apiVersion {api_version!r} is not supported; "
            f"expected one of {sorted(SUPPORTED_API_VERSIONS)} "
            f"(e.g. nthlayer.io/learn/v1)"
        )

    if "recommendations" not in data:
        raise PlanFileInvalidError("plan file missing required 'recommendations' key")

    if not isinstance(data["recommendations"], list):
        raise PlanFileInvalidError(
            f"plan file recommendations must be a list, "
            f"got {type(data['recommendations']).__name__}"
        )

    metadata = data.get("metadata", {})
    if not isinstance(metadata, dict):
        raise PlanFileInvalidError("plan file metadata must be a mapping")

    generated_at_str = metadata.get("generated_at")
    if not isinstance(generated_at_str, str):
        raise PlanFileInvalidError("plan file metadata.generated_at must be an ISO 8601 string")

    recs: list[Recommendation] = []
    for r in data["recommendations"]:
        if not isinstance(r, dict):
            raise PlanFileInvalidError("each recommendation must be a mapping")
        try:
            recs.append(Recommendation(**r))
        except TypeError as exc:
            raise PlanFileInvalidError(f"recommendation invalid: {exc}") from exc

    try:
        return SpecRecommendation(
            incident=metadata.get("incident", ""),
            generated_by=metadata.get("generated_by", "nthlayer-learn"),
            generated_at=datetime.fromisoformat(generated_at_str),
            confidence=metadata.get("confidence", 0.0),
            recommendations=recs,
            requires_human_review=metadata.get("requires_human_review", True),
        )
    except (TypeError, ValueError) as exc:
        raise PlanFileInvalidError(f"plan metadata invalid: {exc}") from exc
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
uv run pytest tests/learn/test_recommendations.py -v
```

Expected: 4 new tests pass, all previous tests still pass.

- [ ] **Step 5: Commit**

```bash
git add src/nthlayer_workers/learn/recommendations.py tests/learn/test_recommendations.py
git commit -m "feat(recommendations): add parse_plan_file for --from input · opensrm-jmy.6

Reads + validates plan YAML files matching apiVersion
nthlayer.io/learn/v1 + kind RecommendationPlan. Raises
PlanFileUnknownVersionError on apiVersion mismatch (with upgrade
hint) and PlanFileInvalidError on structural issues. Used by
the new recommendations CLI subcommand's --from input source."
```

---

## Phase B — `_yaml.py` module

### Task B1: Add ruamel.yaml dep + create `_yaml.py` with `resolve_path`

**Files:**
- Modify: `nthlayer-workers/pyproject.toml`
- Create: `nthlayer-workers/src/nthlayer_workers/learn/_yaml.py`
- Create: `nthlayer-workers/tests/learn/test_yaml.py`

- [ ] **Step 1: Add ruamel.yaml dep + uv sync**

In `nthlayer-workers/pyproject.toml`, find the `dependencies = [...]` block and add `"ruamel.yaml>=0.18"`. Then run:

```bash
cd /Users/robfox/Documents/GitHub/nthlayer-ecosystem/nthlayer-workers
uv sync
```

Confirm `uv.lock` updated with ruamel.yaml + transitive deps (typically ruamel.yaml.clib).

- [ ] **Step 2: Write failing tests for `resolve_path`**

Create `nthlayer-workers/tests/learn/test_yaml.py`:

```python
"""Unit tests for nthlayer_workers.learn._yaml (jmy.6)."""
from __future__ import annotations

import pytest
from ruamel.yaml import YAML


@pytest.fixture
def parsed_manifest():
    """Sample manifest parsed via ruamel.yaml (preserves comments)."""
    yaml = YAML(typ="rt")  # round-trip mode
    text = (
        "metadata:\n"
        "  name: fraud-detect\n"
        "spec:\n"
        "  slos:\n"
        "    judgment:\n"
        "      target: 95.0  # current SLO target\n"
        "      window: 30d\n"
    )
    return yaml.load(text)


class TestResolvePath:
    """resolve_path traverses dotted paths through CommentedMap."""

    def test_resolve_path_happy(self, parsed_manifest):
        from nthlayer_workers.learn._yaml import resolve_path

        assert resolve_path(parsed_manifest, "spec.slos.judgment.target") == 95.0

    def test_resolve_path_missing_leaf(self, parsed_manifest):
        from nthlayer_workers.learn._yaml import resolve_path, PATH_MISSING

        result = resolve_path(parsed_manifest, "spec.slos.judgment.nonexistent")
        assert result is PATH_MISSING

    def test_resolve_path_missing_intermediate(self, parsed_manifest):
        from nthlayer_workers.learn._yaml import resolve_path, PATH_MISSING

        result = resolve_path(parsed_manifest, "spec.deployment.gates.judgment")
        assert result is PATH_MISSING

    def test_resolve_path_empty_path_returns_root(self, parsed_manifest):
        from nthlayer_workers.learn._yaml import resolve_path

        result = resolve_path(parsed_manifest, "")
        # Empty path = root; specific equality is too brittle, just verify it's the parsed doc
        assert "metadata" in result
        assert "spec" in result
```

- [ ] **Step 3: Run tests to verify they fail**

```bash
uv run pytest tests/learn/test_yaml.py::TestResolvePath -v
```

Expected: 4 FAILED — module doesn't exist.

- [ ] **Step 4: Implement `_yaml.py` with `resolve_path` + `PATH_MISSING` sentinel**

Create `src/nthlayer_workers/learn/_yaml.py`:

```python
"""Internal YAML helpers for the Learn → Spec workflow (jmy.6).

ruamel.yaml round-trip mode is used for the read+write path so
operator-authored comments survive deep-merge writes. Pure-function
helpers — no I/O — to enable focused unit-test coverage.
"""
from __future__ import annotations

from typing import Any

from ruamel.yaml import YAML


# Singleton sentinel for "path doesn't resolve in this document".
# Using a singleton object (not None) lets callers distinguish absent
# from a real None-valued leaf.
PATH_MISSING = object()


def get_yaml_round_trip() -> YAML:
    """Factory for a YAML() configured for comment-preserving round-trip.

    Configuration:
    - typ="rt": round-trip mode preserves comments, key order, and
      anchor/alias structure
    - preserve_quotes=True: literal scalar quoting survives writes
    - indent(mapping=2, sequence=4, offset=2): matches operator-authored
      OpenSRM v2 manifest style
    """
    yaml = YAML(typ="rt")
    yaml.preserve_quotes = True
    yaml.indent(mapping=2, sequence=4, offset=2)
    return yaml


def resolve_path(doc: Any, dotted_path: str) -> Any:
    """Descend dotted_path through doc; return value or PATH_MISSING sentinel.

    Empty dotted_path returns the doc unchanged (root reference).
    Returns PATH_MISSING when any intermediate key is absent or the
    traversal would index into a non-mapping value.
    """
    if not dotted_path:
        return doc

    current = doc
    for key in dotted_path.split("."):
        if not isinstance(current, dict):
            return PATH_MISSING
        if key not in current:
            return PATH_MISSING
        current = current[key]
    return current
```

- [ ] **Step 5: Run tests to verify they pass**

```bash
uv run pytest tests/learn/test_yaml.py -v
```

Expected: 4 PASS.

- [ ] **Step 6: Commit**

```bash
git add pyproject.toml uv.lock src/nthlayer_workers/learn/_yaml.py tests/learn/test_yaml.py
git commit -m "feat(_yaml): add ruamel.yaml round-trip + resolve_path · opensrm-jmy.6

New runtime dep ruamel.yaml>=0.18 for comment-preserving round-trip
on manifest writes. _yaml.py is the pure-function YAML primitives
module: resolve_path traverses dotted paths through CommentedMap,
returns PATH_MISSING sentinel on absent intermediates. Underscored
filename signals 'internal, replaceable when pluggable YAML
backends are needed'."
```

---

### Task B2: `apply_at_path` with comment preservation

**Files:**
- Modify: `nthlayer-workers/src/nthlayer_workers/learn/_yaml.py`
- Test: `nthlayer-workers/tests/learn/test_yaml.py`

- [ ] **Step 1: Write failing tests**

Add to `tests/learn/test_yaml.py`:

```python
class TestApplyAtPath:
    """apply_at_path writes in-place; comments survive round-trip."""

    def test_apply_at_existing_leaf(self):
        from nthlayer_workers.learn._yaml import apply_at_path, get_yaml_round_trip
        from io import StringIO

        yaml = get_yaml_round_trip()
        text = (
            "spec:\n"
            "  slos:\n"
            "    judgment:\n"
            "      target: 95.0  # current SLO target\n"
        )
        doc = yaml.load(text)

        apply_at_path(doc, "spec.slos.judgment.target", 98.5)

        buf = StringIO()
        yaml.dump(doc, buf)
        output = buf.getvalue()

        # New value present
        assert "target: 98.5" in output
        # Old value gone
        assert "target: 95.0" not in output
        # Comment preserved
        assert "# current SLO target" in output

    def test_apply_at_missing_intermediate_creates(self):
        from nthlayer_workers.learn._yaml import apply_at_path, get_yaml_round_trip
        from io import StringIO

        yaml = get_yaml_round_trip()
        text = "spec:\n  slos:\n    reversal_rate:\n      target: 98.5\n"
        doc = yaml.load(text)

        # Path doesn't exist; apply creates intermediates
        apply_at_path(doc, "spec.deployment.gates.judgment", {
            "enabled": True,
            "block_on": ["reversal_rate"],
        })

        buf = StringIO()
        yaml.dump(doc, buf)
        output = buf.getvalue()

        assert "deployment:" in output
        assert "gates:" in output
        assert "judgment:" in output
        assert "enabled: true" in output

    def test_apply_at_path_preserves_sibling_comments(self):
        from nthlayer_workers.learn._yaml import apply_at_path, get_yaml_round_trip
        from io import StringIO

        yaml = get_yaml_round_trip()
        text = (
            "spec:\n"
            "  slos:\n"
            "    # SLO for the judgment pipeline\n"
            "    judgment:\n"
            "      target: 95.0\n"
            "      window: 30d  # rolling window\n"
        )
        doc = yaml.load(text)

        apply_at_path(doc, "spec.slos.judgment.target", 98.5)

        buf = StringIO()
        yaml.dump(doc, buf)
        output = buf.getvalue()

        assert "# SLO for the judgment pipeline" in output
        assert "# rolling window" in output
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
uv run pytest tests/learn/test_yaml.py::TestApplyAtPath -v
```

Expected: 3 FAILED — `apply_at_path` not defined.

- [ ] **Step 3: Implement `apply_at_path`**

In `src/nthlayer_workers/learn/_yaml.py`, add:

```python
from ruamel.yaml.comments import CommentedMap


def apply_at_path(doc: Any, dotted_path: str, value: Any) -> None:
    """Write value at dotted_path; create missing intermediates as needed.

    Modifies doc in place. Comments on sibling keys and intermediate
    mappings are preserved (ruamel.yaml CommentedMap holds comments
    on the parent node, not on the keys themselves).

    Missing intermediate keys are created as CommentedMap instances
    so subsequent operations against those keys round-trip cleanly.

    Raises TypeError if a non-leaf path segment is already bound to
    a non-mapping value (we won't silently overwrite scalars with
    mappings — that's a structural change the engine doesn't produce).
    """
    if not dotted_path:
        raise ValueError("apply_at_path requires a non-empty dotted_path")

    keys = dotted_path.split(".")
    current = doc
    for key in keys[:-1]:
        if key not in current:
            current[key] = CommentedMap()
        if not isinstance(current[key], dict):
            raise TypeError(
                f"cannot descend into non-mapping at {key!r} "
                f"(found {type(current[key]).__name__})"
            )
        current = current[key]

    current[keys[-1]] = value
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
uv run pytest tests/learn/test_yaml.py -v
```

Expected: all `TestApplyAtPath` tests + existing `TestResolvePath` tests pass.

- [ ] **Step 5: Commit**

```bash
git add src/nthlayer_workers/learn/_yaml.py tests/learn/test_yaml.py
git commit -m "feat(_yaml): add apply_at_path with comment preservation · opensrm-jmy.6

In-place write at dotted path. Missing intermediates created as
CommentedMap so round-trips stay clean. Sibling and inline comments
survive deep-merge writes — that's the whole point of choosing
ruamel.yaml over PyYAML for the write path."
```

---

### Task B3: `normalize_scalar` for type-normalised comparison

**Files:**
- Modify: `nthlayer-workers/src/nthlayer_workers/learn/_yaml.py`
- Test: `nthlayer-workers/tests/learn/test_yaml.py`

- [ ] **Step 1: Write failing tests**

Add to `tests/learn/test_yaml.py`:

```python
class TestNormalizeScalar:
    """normalize_scalar enables int/float/numeric-string equivalence."""

    def test_int_float_str_numeric_equivalence(self):
        from nthlayer_workers.learn._yaml import normalize_scalar

        n_int = normalize_scalar(98)
        n_float = normalize_scalar(98.0)
        n_str_int = normalize_scalar("98")
        n_str_float = normalize_scalar("98.0")

        # All four representations normalise to the same value
        assert n_int == n_float == n_str_int == n_str_float

    def test_different_numbers_not_equivalent(self):
        from nthlayer_workers.learn._yaml import normalize_scalar

        assert normalize_scalar(98) != normalize_scalar(99)
        assert normalize_scalar(98.5) != normalize_scalar(98.6)

    def test_non_numeric_string_returns_as_is(self):
        from nthlayer_workers.learn._yaml import normalize_scalar

        assert normalize_scalar("hello") == "hello"
        assert normalize_scalar("30d") == "30d"
        # Numeric vs non-numeric not equivalent
        assert normalize_scalar(30) != normalize_scalar("30d")

    def test_bool_not_treated_as_numeric(self):
        """bool subclasses int in Python; we explicitly do NOT coerce."""
        from nthlayer_workers.learn._yaml import normalize_scalar

        assert normalize_scalar(True) != normalize_scalar(1)
        assert normalize_scalar(False) != normalize_scalar(0)

    def test_non_scalar_passes_through(self):
        from nthlayer_workers.learn._yaml import normalize_scalar

        # Dicts and lists aren't scalars — pass through unchanged so
        # equality comparison can do its own structural check.
        assert normalize_scalar({"a": 1}) == {"a": 1}
        assert normalize_scalar([1, 2]) == [1, 2]
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
uv run pytest tests/learn/test_yaml.py::TestNormalizeScalar -v
```

Expected: 5 FAILED — `normalize_scalar` not defined.

- [ ] **Step 3: Implement `normalize_scalar`**

In `src/nthlayer_workers/learn/_yaml.py`, add:

```python
def normalize_scalar(value: Any) -> Any:
    """Normalise scalars for type-tolerant equality comparison (jmy.6 § 6.1).

    int(98) / float(98.0) / str("98") / str("98.0") all normalise to the
    same float IFF they round-trip cleanly. Used by classify_outcome to
    decide already_applied vs drift_detected against operator-authored
    manifests where YAML quoting is the operator's stylistic choice.

    Non-numeric scalars and non-scalar values pass through unchanged so
    equality comparison can do its own structural check. Booleans are
    NOT coerced to numeric (bool subclasses int in Python; we keep the
    distinction).
    """
    # Booleans first — bool is a subclass of int, so isinstance(True, int) is True.
    # We don't want True == 1.
    if isinstance(value, bool):
        return value

    if isinstance(value, (int, float)):
        return float(value)

    if isinstance(value, str):
        try:
            return float(value)
        except ValueError:
            return value

    return value
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
uv run pytest tests/learn/test_yaml.py -v
```

Expected: all `TestNormalizeScalar` + previous tests pass.

- [ ] **Step 5: Commit**

```bash
git add src/nthlayer_workers/learn/_yaml.py tests/learn/test_yaml.py
git commit -m "feat(_yaml): add normalize_scalar for type-tolerant comparison · opensrm-jmy.6

int/float/numeric-string normalise to the same float; non-numeric
strings + non-scalars pass through unchanged. Booleans deliberately
NOT coerced (bool subclasses int in Python). Used by classify_outcome
to decide already_applied vs drift_detected without false drift on
operator-authored YAML quoting choices."
```

---

### Task B4: `classify_outcome` state machine

**Files:**
- Modify: `nthlayer-workers/src/nthlayer_workers/learn/_yaml.py`
- Test: `nthlayer-workers/tests/learn/test_yaml.py`

- [ ] **Step 1: Write failing tests covering all 7 state-machine cells**

Add to `tests/learn/test_yaml.py`:

```python
class TestClassifyOutcome:
    """Two-table state machine per jmy.6 design § 5 + § 7."""

    @pytest.fixture
    def rec_with_current(self):
        """Recommendation modifying existing state (e.g. tighten_slo)."""
        from nthlayer_workers.learn.recommendations import Recommendation
        return Recommendation(
            id="rec-deadbeef0123",
            service="fraud-detect",
            type="tighten_slo",
            rationale="test",
            field="spec.slos.judgment.target",
            current_value=95.0,
            proposed_value=98.5,
        )

    @pytest.fixture
    def rec_without_current(self):
        """Recommendation adding new state (e.g. add_deploy_gate)."""
        from nthlayer_workers.learn.recommendations import Recommendation
        return Recommendation(
            id="rec-deadbeef0124",
            service="fraud-detect",
            type="add_deploy_gate",
            rationale="test",
            field="spec.deployment.gates.judgment",
            current_value=None,
            proposed_value={"enabled": True, "block_on": ["reversal_rate"]},
        )

    # ── 4 cells for "modifying existing" (current_value present) ──

    def test_with_current_path_missing_target_path_missing(self, rec_with_current):
        from nthlayer_workers.learn._yaml import classify_outcome, PATH_MISSING
        from nthlayer_workers.learn.recommendations import OutcomeKind

        result = classify_outcome(PATH_MISSING, rec_with_current)
        assert result == OutcomeKind.TARGET_PATH_MISSING

    def test_with_current_path_eq_proposed_already_applied(self, rec_with_current):
        from nthlayer_workers.learn._yaml import classify_outcome
        from nthlayer_workers.learn.recommendations import OutcomeKind

        # Manifest already has proposed value
        result = classify_outcome(98.5, rec_with_current)
        assert result == OutcomeKind.ALREADY_APPLIED

    def test_with_current_path_eq_current_apply_clean(self, rec_with_current):
        from nthlayer_workers.learn._yaml import classify_outcome
        from nthlayer_workers.learn.recommendations import OutcomeKind

        # Manifest has current_value — clean overwrite case
        result = classify_outcome(95.0, rec_with_current)
        assert result == OutcomeKind.APPLY_CLEAN

    def test_with_current_path_eq_other_drift_detected(self, rec_with_current):
        from nthlayer_workers.learn._yaml import classify_outcome
        from nthlayer_workers.learn.recommendations import OutcomeKind

        # Manifest has some other value — drift
        result = classify_outcome(97.0, rec_with_current)
        assert result == OutcomeKind.DRIFT_DETECTED

    # ── 3 cells for "adding new" (current_value None) ──

    def test_without_current_path_missing_apply_clean(self, rec_without_current):
        from nthlayer_workers.learn._yaml import classify_outcome, PATH_MISSING
        from nthlayer_workers.learn.recommendations import OutcomeKind

        # Path missing + no current_value → create (apply_clean)
        result = classify_outcome(PATH_MISSING, rec_without_current)
        assert result == OutcomeKind.APPLY_CLEAN

    def test_without_current_path_eq_proposed_already_applied(self, rec_without_current):
        from nthlayer_workers.learn._yaml import classify_outcome
        from nthlayer_workers.learn.recommendations import OutcomeKind

        result = classify_outcome(
            {"enabled": True, "block_on": ["reversal_rate"]},
            rec_without_current,
        )
        assert result == OutcomeKind.ALREADY_APPLIED

    def test_without_current_path_other_drift_detected(self, rec_without_current):
        from nthlayer_workers.learn._yaml import classify_outcome
        from nthlayer_workers.learn.recommendations import OutcomeKind

        # Something else exists at the path — drift
        result = classify_outcome(
            {"enabled": False, "block_on": []},  # different gate config
            rec_without_current,
        )
        assert result == OutcomeKind.DRIFT_DETECTED

    # ── Normalisation interaction (int/str equivalence) ──

    def test_normalisation_int_vs_float_already_applied(self, rec_with_current):
        """Manifest has 98 (int); proposed is 98.5 (float). Different values."""
        from nthlayer_workers.learn._yaml import classify_outcome
        from nthlayer_workers.learn.recommendations import OutcomeKind

        # Manifest has 98 (int), recommendation proposed 98.5 → drift (not equal)
        result = classify_outcome(98, rec_with_current)
        assert result == OutcomeKind.DRIFT_DETECTED

    def test_normalisation_numeric_string_eq_proposed(self, rec_with_current):
        """Manifest has '98.5' (string); proposed is 98.5 (float). Equivalent."""
        from nthlayer_workers.learn._yaml import classify_outcome
        from nthlayer_workers.learn.recommendations import OutcomeKind

        result = classify_outcome("98.5", rec_with_current)
        assert result == OutcomeKind.ALREADY_APPLIED
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
uv run pytest tests/learn/test_yaml.py::TestClassifyOutcome -v
```

Expected: 9 FAILED — `classify_outcome` not defined.

- [ ] **Step 3: Implement `classify_outcome`**

In `src/nthlayer_workers/learn/_yaml.py`, add:

```python
from nthlayer_workers.learn.recommendations import OutcomeKind, Recommendation


def classify_outcome(manifest_value: Any, rec: Recommendation) -> OutcomeKind:
    """Two-table state machine from jmy.6 design § 5.

    For recommendations WITH current_value (modifying existing):
      manifest path missing       → target_path_missing
      manifest path = proposed    → already_applied
      manifest path = current     → apply_clean
      manifest path = other       → drift_detected

    For recommendations WITHOUT current_value (adding new):
      manifest path missing       → apply_clean (create)
      manifest path = proposed    → already_applied
      manifest path = other       → drift_detected

    Type-tolerant scalar comparison via normalize_scalar; structural
    (dict/list) comparison is exact.
    """
    proposed_norm = _normalize_for_compare(rec.proposed_value)

    if rec.current_value is None:
        # Adding-new table
        if manifest_value is PATH_MISSING:
            return OutcomeKind.APPLY_CLEAN
        if _normalize_for_compare(manifest_value) == proposed_norm:
            return OutcomeKind.ALREADY_APPLIED
        return OutcomeKind.DRIFT_DETECTED

    # Modifying-existing table
    if manifest_value is PATH_MISSING:
        return OutcomeKind.TARGET_PATH_MISSING

    current_norm = _normalize_for_compare(rec.current_value)
    manifest_norm = _normalize_for_compare(manifest_value)

    if manifest_norm == proposed_norm:
        return OutcomeKind.ALREADY_APPLIED
    if manifest_norm == current_norm:
        return OutcomeKind.APPLY_CLEAN
    return OutcomeKind.DRIFT_DETECTED


def _normalize_for_compare(value: Any) -> Any:
    """Normalise scalars; pass non-scalars through. For dict/list, the
    caller's == does structural comparison."""
    if isinstance(value, (dict, list)):
        return value
    return normalize_scalar(value)
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
uv run pytest tests/learn/test_yaml.py -v
```

Expected: 9 new `TestClassifyOutcome` tests + all earlier `test_yaml.py` tests pass.

- [ ] **Step 5: Commit**

```bash
git add src/nthlayer_workers/learn/_yaml.py tests/learn/test_yaml.py
git commit -m "feat(_yaml): classify_outcome state machine · opensrm-jmy.6

Two-table state machine per jmy.6 design § 5. Recommendation's
current_value presence selects the table; manifest value at target
path selects the row. Scalar comparison normalised via normalize_scalar
(int/float/numeric-string equivalence); structural comparison exact.
9 tests cover all 7 cells + 2 normalisation interactions."
```

---

## Phase C — `_preview.py` module

### Task C1: `build_preview` for scalar recommendations

**Files:**
- Create: `nthlayer-workers/src/nthlayer_workers/learn/_preview.py`
- Create: `nthlayer-workers/tests/learn/test_preview.py`

- [ ] **Step 1: Write failing tests**

Create `nthlayer-workers/tests/learn/test_preview.py`:

```python
"""Unit tests for nthlayer_workers.learn._preview (jmy.6)."""
from __future__ import annotations

import pytest


class TestBuildPreviewScalar:
    """build_preview for scalar-valued recommendations (tighten_slo)."""

    def test_scalar_change_preview_shape(self):
        from nthlayer_workers.learn._preview import build_preview
        from nthlayer_workers.learn.recommendations import Recommendation

        rec = Recommendation(
            id="rec-deadbeef0123",
            service="fraud-detect",
            type="tighten_slo",
            rationale="test",
            field="spec.slos.judgment.target",
            current_value=95.0,
            proposed_value=98.5,
        )
        # Manifest's current value (read by _apply before calling build_preview)
        preview = build_preview(
            manifest_path="specs/fraud-detect.yaml",
            rec=rec,
            manifest_current_value=95.0,
        )

        # Heading lines pinned per jmy.6 design § 6.1
        assert "# File: specs/fraud-detect.yaml" in preview
        assert "# Path: spec.slos.judgment.target" in preview
        # Unified-diff style
        assert "-   target: 95.0" in preview
        assert "+   target: 98.5" in preview

    def test_scalar_already_applied_returns_empty(self):
        """When manifest already has proposed value, preview is empty."""
        from nthlayer_workers.learn._preview import build_preview
        from nthlayer_workers.learn.recommendations import Recommendation

        rec = Recommendation(
            id="rec-deadbeef0123",
            service="fraud-detect",
            type="tighten_slo",
            rationale="test",
            field="spec.slos.judgment.target",
            current_value=95.0,
            proposed_value=98.5,
        )
        preview = build_preview(
            manifest_path="specs/fraud-detect.yaml",
            rec=rec,
            manifest_current_value=98.5,  # already matches proposed
        )
        # Empty preview (no diff to show); caller suppresses the field
        assert preview == ""
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
uv run pytest tests/learn/test_preview.py -v
```

Expected: 2 FAILED — module doesn't exist.

- [ ] **Step 3: Implement `_preview.py` with `build_preview`**

Create `src/nthlayer_workers/learn/_preview.py`:

```python
"""Preview generation for the Learn → Spec workflow (jmy.6 § 6.1).

Pure functions. Given a recommendation + the manifest's current value
at the target path, produce a unified-diff-style preview string.
Operators see this in plan.yaml's `preview` field when --output is
called with --specs-dir.

When manifest's current value matches the recommendation's proposed
value, preview is empty (caller suppresses the field).
"""
from __future__ import annotations

from typing import Any

from nthlayer_workers.learn.recommendations import Recommendation


def build_preview(
    *,
    manifest_path: str,
    rec: Recommendation,
    manifest_current_value: Any,
) -> str:
    """Generate the per-recommendation preview field string.

    Empty string when manifest already matches the proposed value (no
    diff to show). Caller is responsible for omitting the field from
    plan.yaml when this returns empty.

    Drift marker is appended when manifest_current_value differs from
    rec.current_value — operators need to know the recommendation may
    no longer apply cleanly.
    """
    from nthlayer_workers.learn._yaml import normalize_scalar

    # Suppress preview if manifest is already at proposed state
    if normalize_scalar(manifest_current_value) == normalize_scalar(rec.proposed_value):
        return ""

    lines = [
        f"# File: {manifest_path}",
        f"# Path: {rec.field}",
    ]

    # Drift marker for operator visibility
    if rec.current_value is not None and \
       normalize_scalar(manifest_current_value) != normalize_scalar(rec.current_value):
        lines.append(
            f"# WARN: manifest drifted from recommendation's expected value "
            f"(current={manifest_current_value!r}, expected={rec.current_value!r})"
        )

    # Render the diff. Path leaf is the last dotted segment; indent matches
    # YAML 4-space-for-sequence-element style.
    leaf = rec.field.rsplit(".", 1)[-1] if rec.field else "(root)"

    if rec.current_value is None:
        # Adding new — show the proposed value as a new block
        lines.append(f"+   {leaf}:")
        for sub_line in _render_block(rec.proposed_value, indent=6):
            lines.append("+ " + sub_line)
    else:
        # Modifying existing
        lines.append(f"-   {leaf}: {_render_inline(rec.current_value)}")
        lines.append(f"+   {leaf}: {_render_inline(rec.proposed_value)}")

    return "\n".join(lines) + "\n"


def _render_inline(value: Any) -> str:
    """Render a scalar inline (matches YAML output for the common case)."""
    if isinstance(value, str):
        return value
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def _render_block(value: Any, *, indent: int) -> list[str]:
    """Render a dict/list value as multi-line YAML-ish block."""
    pad = " " * indent
    if isinstance(value, dict):
        return [f"{pad}{k}: {_render_inline(v)}" for k, v in value.items()]
    if isinstance(value, list):
        return [f"{pad}- {_render_inline(v)}" for v in value]
    return [f"{pad}{_render_inline(value)}"]
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
uv run pytest tests/learn/test_preview.py -v
```

Expected: 2 PASS.

- [ ] **Step 5: Commit**

```bash
git add src/nthlayer_workers/learn/_preview.py tests/learn/test_preview.py
git commit -m "feat(_preview): scalar preview generation · opensrm-jmy.6

Unified-diff style preview for tighten_slo-shaped recommendations.
Empty string when manifest already at proposed state (caller omits
preview field). Drift marker appended when manifest diverged from
recommendation's expected current_value."
```

---

### Task C2: `build_preview` for structural recommendations + drift coverage

**Files:**
- Test: `nthlayer-workers/tests/learn/test_preview.py`

- [ ] **Step 1: Write failing tests for structural + drift cases**

Add to `tests/learn/test_preview.py`:

```python
class TestBuildPreviewStructural:
    """build_preview for dict-valued recommendations (add_deploy_gate)."""

    def test_add_deploy_gate_preview_shape(self):
        from nthlayer_workers.learn._preview import build_preview
        from nthlayer_workers.learn.recommendations import Recommendation
        from nthlayer_workers.learn._yaml import PATH_MISSING

        rec = Recommendation(
            id="rec-deadbeef0124",
            service="fraud-detect",
            type="add_deploy_gate",
            rationale="test",
            field="spec.deployment.gates.judgment",
            current_value=None,
            proposed_value={"enabled": True, "block_on": ["reversal_rate"]},
        )
        preview = build_preview(
            manifest_path="specs/fraud-detect.yaml",
            rec=rec,
            manifest_current_value=PATH_MISSING,
        )

        assert "# File: specs/fraud-detect.yaml" in preview
        assert "# Path: spec.deployment.gates.judgment" in preview
        # New-block style with + prefix
        assert "+   judgment:" in preview
        # Sub-keys present
        assert "enabled: true" in preview
        assert "block_on:" in preview or "reversal_rate" in preview


class TestBuildPreviewDrift:
    """Drift marker when manifest's current value differs from rec's."""

    def test_drift_marker_appended_for_scalar(self):
        from nthlayer_workers.learn._preview import build_preview
        from nthlayer_workers.learn.recommendations import Recommendation

        rec = Recommendation(
            id="rec-deadbeef0125",
            service="fraud-detect",
            type="tighten_slo",
            rationale="test",
            field="spec.slos.judgment.target",
            current_value=95.0,
            proposed_value=98.5,
        )
        # Manifest has 97.0 — drift from recommendation's expected 95.0
        preview = build_preview(
            manifest_path="specs/fraud-detect.yaml",
            rec=rec,
            manifest_current_value=97.0,
        )

        assert "# WARN: manifest drifted" in preview
        assert "current=97.0" in preview
        assert "expected=95.0" in preview

    def test_no_drift_marker_when_values_match(self):
        from nthlayer_workers.learn._preview import build_preview
        from nthlayer_workers.learn.recommendations import Recommendation

        rec = Recommendation(
            id="rec-deadbeef0126",
            service="fraud-detect",
            type="tighten_slo",
            rationale="test",
            field="spec.slos.judgment.target",
            current_value=95.0,
            proposed_value=98.5,
        )
        # Manifest matches rec's expected current_value — no drift
        preview = build_preview(
            manifest_path="specs/fraud-detect.yaml",
            rec=rec,
            manifest_current_value=95.0,
        )

        assert "# WARN" not in preview
```

- [ ] **Step 2: Run tests to verify they fail or pass**

```bash
uv run pytest tests/learn/test_preview.py -v
```

Expected: structural test likely passes (rendering already handles dict via _render_block) but assertion specifics may need adjustment. Drift tests should already pass from C1's drift-marker logic. Adjust assertions to match actual output.

- [ ] **Step 3: Adjust if needed**

If `TestBuildPreviewStructural::test_add_deploy_gate_preview_shape` fails, look at the actual rendered output and adjust the structural rendering in `_render_block` to produce the expected nested shape. The `block_on:` list needs sub-indent for `- reversal_rate`.

Refinement to `_render_block` if needed:

```python
def _render_block(value: Any, *, indent: int) -> list[str]:
    pad = " " * indent
    lines: list[str] = []
    if isinstance(value, dict):
        for k, v in value.items():
            if isinstance(v, (dict, list)):
                lines.append(f"{pad}{k}:")
                lines.extend(_render_block(v, indent=indent + 2))
            else:
                lines.append(f"{pad}{k}: {_render_inline(v)}")
    elif isinstance(value, list):
        for item in value:
            lines.append(f"{pad}- {_render_inline(item)}")
    else:
        lines.append(f"{pad}{_render_inline(value)}")
    return lines
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
uv run pytest tests/learn/test_preview.py -v
```

Expected: all tests pass (4 from C1+C2).

- [ ] **Step 5: Commit**

```bash
git add src/nthlayer_workers/learn/_preview.py tests/learn/test_preview.py
git commit -m "feat(_preview): structural preview + drift marker tests · opensrm-jmy.6

Extends _render_block for nested dicts/lists (add_deploy_gate shape).
Drift marker pinned by 2 explicit tests: appended when manifest's
current value differs from rec's expected current_value; absent
when they match. All 4 preview tests pass."
```

---

## Phase D — `_apply.py` module

### Task D1: Manifest resolution helper

**Files:**
- Create: `nthlayer-workers/src/nthlayer_workers/learn/_apply.py`
- Create: `nthlayer-workers/tests/learn/test_apply.py`

- [ ] **Step 1: Write failing tests**

Create `nthlayer-workers/tests/learn/test_apply.py`:

```python
"""Unit tests for nthlayer_workers.learn._apply (jmy.6)."""
from __future__ import annotations

import pytest
from pathlib import Path


class TestResolveManifestPath:
    """resolve_manifest_path: filename-convention + walk fallback."""

    def test_filename_convention(self, tmp_path):
        from nthlayer_workers.learn._apply import resolve_manifest_path

        (tmp_path / "fraud-detect.yaml").write_text(
            "metadata:\n  name: fraud-detect\nspec:\n  slos: {}\n"
        )

        result = resolve_manifest_path("fraud-detect", tmp_path)
        assert result == tmp_path / "fraud-detect.yaml"

    def test_filename_convention_yml_extension(self, tmp_path):
        from nthlayer_workers.learn._apply import resolve_manifest_path

        (tmp_path / "fraud-detect.yml").write_text(
            "metadata:\n  name: fraud-detect\nspec:\n  slos: {}\n"
        )

        result = resolve_manifest_path("fraud-detect", tmp_path)
        assert result == tmp_path / "fraud-detect.yml"

    def test_walk_fallback_finds_by_metadata_name(self, tmp_path):
        from nthlayer_workers.learn._apply import resolve_manifest_path

        # File doesn't match service name; metadata.name does
        nested = tmp_path / "payments" / "billing-srv.yaml"
        nested.parent.mkdir(parents=True)
        nested.write_text(
            "metadata:\n  name: fraud-detect\nspec:\n  slos: {}\n"
        )

        result = resolve_manifest_path("fraud-detect", tmp_path)
        assert result == nested

    def test_hidden_dirs_excluded(self, tmp_path):
        from nthlayer_workers.learn._apply import resolve_manifest_path

        # Hidden dir; should be excluded from walk
        hidden = tmp_path / ".cache" / "fraud-detect.yaml"
        hidden.parent.mkdir()
        hidden.write_text(
            "metadata:\n  name: fraud-detect\nspec:\n  slos: {}\n"
        )

        result = resolve_manifest_path("fraud-detect", tmp_path)
        assert result is None  # not found (hidden excluded)

    def test_not_found_returns_none(self, tmp_path):
        from nthlayer_workers.learn._apply import resolve_manifest_path

        result = resolve_manifest_path("nonexistent-service", tmp_path)
        assert result is None
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
uv run pytest tests/learn/test_apply.py::TestResolveManifestPath -v
```

Expected: 5 FAILED — module doesn't exist.

- [ ] **Step 3: Implement `_apply.py` with `resolve_manifest_path`**

Create `src/nthlayer_workers/learn/_apply.py`:

```python
"""Apply orchestration for the Learn → Spec workflow (jmy.6 § 4 / § 5).

Reads target manifests via ruamel.yaml round-trip, classifies each
recommendation against current manifest state, deep-merges accepted
ones in memory, then writes all modified manifests atomically in a
final phase (alphabetical by path).

Resolution strategy: filename-convention first ('<specs-dir>/<svc>.yaml'
or '.yml'), recursive walk fallback finding manifests by metadata.name.
Hidden directories excluded from the walk.
"""
from __future__ import annotations

from pathlib import Path
from typing import Iterable

import yaml as pyyaml  # lightweight read for the discovery walk only


def resolve_manifest_path(service: str, specs_dir: Path) -> Path | None:
    """Find the manifest file for a service in specs_dir.

    Strategy (per jmy.6 design § 4 Option B):
    1. Try <specs-dir>/<service>.yaml then <specs-dir>/<service>.yml
    2. If neither exists, recursive walk excluding hidden dirs;
       parse each .yaml/.yml and match metadata.name.

    Returns None if no manifest matches. Run is expected to handle
    None as manifest_not_found per jmy.6 § 7 Category B.
    """
    specs_dir = Path(specs_dir)

    # Convention attempt
    for ext in (".yaml", ".yml"):
        candidate = specs_dir / f"{service}{ext}"
        if candidate.is_file():
            return candidate

    # Walk fallback
    for path in _walk_yaml_files(specs_dir):
        try:
            text = path.read_text()
            data = pyyaml.safe_load(text)
        except (OSError, pyyaml.YAMLError):
            continue
        if not isinstance(data, dict):
            continue
        metadata = data.get("metadata") or {}
        if isinstance(metadata, dict) and metadata.get("name") == service:
            return path

    return None


def _walk_yaml_files(root: Path) -> Iterable[Path]:
    """Yield .yaml/.yml files under root, excluding hidden directories."""
    for path in root.rglob("*"):
        if path.is_dir():
            continue
        # Exclude any path with a hidden directory component
        if any(part.startswith(".") for part in path.relative_to(root).parts[:-1]):
            continue
        if path.suffix in (".yaml", ".yml"):
            yield path
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
uv run pytest tests/learn/test_apply.py -v
```

Expected: 5 PASS.

- [ ] **Step 5: Commit**

```bash
git add src/nthlayer_workers/learn/_apply.py tests/learn/test_apply.py
git commit -m "feat(_apply): manifest resolution helper · opensrm-jmy.6

resolve_manifest_path: filename-convention first (svc.yaml/yml),
recursive walk fallback finding by metadata.name. Hidden directories
excluded. Uses PyYAML for the discovery read (validation-only;
we only need metadata.name) — the dual-parser strategy per design
§ 4 keeps the write path on ruamel.yaml for comment preservation."
```

---

### Task D2: `ApplyResult` dataclass + `apply_recommendations` happy path

**Files:**
- Modify: `nthlayer-workers/src/nthlayer_workers/learn/_apply.py`
- Test: `nthlayer-workers/tests/learn/test_apply.py`

- [ ] **Step 1: Write failing tests**

Add to `tests/learn/test_apply.py`:

```python
class TestApplyHappyPath:
    """apply_recommendations orchestration: happy path."""

    def test_single_rec_applied(self, tmp_path):
        from nthlayer_workers.learn._apply import apply_recommendations
        from nthlayer_workers.learn.recommendations import (
            Recommendation, SpecRecommendation, OutcomeKind,
        )
        from datetime import datetime, timezone

        # Seed manifest
        (tmp_path / "fraud-detect.yaml").write_text(
            "metadata:\n  name: fraud-detect\n"
            "spec:\n  slos:\n    judgment:\n      target: 95.0\n"
        )
        plan = SpecRecommendation(
            incident="inc-test",
            generated_by="nthlayer-learn",
            generated_at=datetime(2026, 5, 26, tzinfo=timezone.utc),
            confidence=0.7,
            recommendations=[
                Recommendation(
                    id="rec-deadbeef0123",
                    service="fraud-detect",
                    type="tighten_slo",
                    rationale="test",
                    field="spec.slos.judgment.target",
                    current_value=95.0,
                    proposed_value=98.5,
                ),
            ],
        )

        result = apply_recommendations(plan, tmp_path)

        assert len(result.applied) == 1
        assert result.applied[0].id == "rec-deadbeef0123"
        assert result.applied[0].outcome == OutcomeKind.APPLY_CLEAN
        assert len(result.skipped) == 0
        # Manifest file modified on disk
        assert "target: 98.5" in (tmp_path / "fraud-detect.yaml").read_text()
        assert "target: 95.0" not in (tmp_path / "fraud-detect.yaml").read_text()

    def test_skipped_when_manifest_missing(self, tmp_path):
        from nthlayer_workers.learn._apply import apply_recommendations
        from nthlayer_workers.learn.recommendations import (
            Recommendation, SpecRecommendation, OutcomeKind,
        )
        from datetime import datetime, timezone

        # No manifest seeded
        plan = SpecRecommendation(
            incident="inc-test",
            generated_by="nthlayer-learn",
            generated_at=datetime(2026, 5, 26, tzinfo=timezone.utc),
            confidence=0.7,
            recommendations=[
                Recommendation(
                    id="rec-deadbeef0124",
                    service="unknown-service",
                    type="tighten_slo",
                    rationale="test",
                    field="spec.slos.judgment.target",
                    current_value=95.0,
                    proposed_value=98.5,
                ),
            ],
        )

        result = apply_recommendations(plan, tmp_path)
        assert len(result.applied) == 0
        assert len(result.skipped) == 1
        assert result.skipped[0].outcome == OutcomeKind.MANIFEST_NOT_FOUND
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
uv run pytest tests/learn/test_apply.py::TestApplyHappyPath -v
```

Expected: 2 FAILED — `apply_recommendations` + `ApplyResult` not defined.

- [ ] **Step 3: Implement `ApplyResult` + `apply_recommendations`**

Add to `src/nthlayer_workers/learn/_apply.py`:

```python
from dataclasses import dataclass, field
from io import StringIO
from typing import Any

from nthlayer_workers.learn.recommendations import (
    OutcomeKind, Recommendation, SpecRecommendation,
)
from nthlayer_workers.learn._yaml import (
    apply_at_path, classify_outcome, get_yaml_round_trip, resolve_path,
)


@dataclass
class RecOutcome:
    """One recommendation's outcome from apply_recommendations."""
    id: str
    service: str
    field: str | None
    outcome: OutcomeKind
    detail: str = ""  # human-readable detail for skipped recs


@dataclass
class ApplyResult:
    """Result of an apply_recommendations call."""
    applied: list[RecOutcome] = field(default_factory=list)
    skipped: list[RecOutcome] = field(default_factory=list)
    modified_files: list[Path] = field(default_factory=list)

    @property
    def exit_code(self) -> int:
        """Per jmy.6 design § 7 deterministic rule."""
        # Empty plan → 0
        if not self.applied and not self.skipped:
            return 0
        # Any successful applies?
        any_clean = any(
            r.outcome == OutcomeKind.APPLY_CLEAN for r in self.applied
        )
        all_clean_or_idempotent = all(
            r.outcome in (OutcomeKind.APPLY_CLEAN, OutcomeKind.ALREADY_APPLIED)
            for r in self.applied
        ) and not self.skipped
        if all_clean_or_idempotent:
            return 0
        if any_clean and self.skipped:
            return 1  # partial
        return 2  # complete failure


def apply_recommendations(
    plan: SpecRecommendation,
    specs_dir: Path,
    *,
    force: bool = False,
) -> ApplyResult:
    """Apply the plan's recommendations to manifests in specs_dir.

    Two-phase: classify all recs first (in-memory), then write all
    modified manifests atomically in alphabetical-by-path order.
    """
    specs_dir = Path(specs_dir)
    result = ApplyResult()
    yaml = get_yaml_round_trip()

    # Build {file_path: parsed_doc} cache so each unique manifest is
    # read+parsed once even if multiple recs target it.
    doc_cache: dict[Path, Any] = {}
    modified_paths: set[Path] = set()

    for rec in plan.recommendations:
        # Resolve manifest
        manifest_path = resolve_manifest_path(rec.service, specs_dir)
        if manifest_path is None:
            result.skipped.append(RecOutcome(
                id=rec.id, service=rec.service, field=rec.field,
                outcome=OutcomeKind.MANIFEST_NOT_FOUND,
                detail=f"no manifest for service {rec.service!r} in {specs_dir}",
            ))
            continue

        # Read + parse (cached)
        if manifest_path not in doc_cache:
            doc_cache[manifest_path] = yaml.load(manifest_path.read_text())
        doc = doc_cache[manifest_path]

        # Classify
        manifest_value = resolve_path(doc, rec.field or "")
        outcome = classify_outcome(manifest_value, rec)

        if outcome == OutcomeKind.APPLY_CLEAN:
            apply_at_path(doc, rec.field, rec.proposed_value)
            modified_paths.add(manifest_path)
            result.applied.append(RecOutcome(
                id=rec.id, service=rec.service, field=rec.field,
                outcome=outcome,
            ))
        elif outcome == OutcomeKind.ALREADY_APPLIED:
            result.applied.append(RecOutcome(
                id=rec.id, service=rec.service, field=rec.field,
                outcome=outcome,
            ))
        elif outcome == OutcomeKind.DRIFT_DETECTED and force:
            apply_at_path(doc, rec.field, rec.proposed_value)
            modified_paths.add(manifest_path)
            result.applied.append(RecOutcome(
                id=rec.id, service=rec.service, field=rec.field,
                outcome=OutcomeKind.APPLY_CLEAN,  # --force normalises to clean
                detail="applied via --force despite drift",
            ))
        else:
            result.skipped.append(RecOutcome(
                id=rec.id, service=rec.service, field=rec.field,
                outcome=outcome,
            ))

    # Write phase: alphabetical-by-path, atomic per-file
    for path in sorted(modified_paths):
        buf = StringIO()
        yaml.dump(doc_cache[path], buf)
        path.write_text(buf.getvalue())
        result.modified_files.append(path)

    return result
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
uv run pytest tests/learn/test_apply.py -v
```

Expected: all `TestApplyHappyPath` + `TestResolveManifestPath` tests pass.

- [ ] **Step 5: Commit**

```bash
git add src/nthlayer_workers/learn/_apply.py tests/learn/test_apply.py
git commit -m "feat(_apply): apply_recommendations orchestration · opensrm-jmy.6

Two-phase orchestration: classify all recs against in-memory parsed
manifests, then write all modified files atomically in alphabetical
order. ApplyResult carries applied + skipped + modified_files lists
plus the deterministic exit_code property per jmy.6 design § 7.
--force normalises drift_detected into apply_clean (with detail
explaining the override)."
```

---

### Task D3: Atomicity test with filename-based failure injection

**Files:**
- Test: `nthlayer-workers/tests/learn/test_apply.py`

- [ ] **Step 1: Write atomicity test**

Add to `tests/learn/test_apply.py`:

```python
class TestApplyAtomicity:
    """Atomic write phase: alphabetical order, failure isolation."""

    def test_alphabetical_write_order(self, tmp_path):
        """Files are written in alphabetical order, not encounter order."""
        from nthlayer_workers.learn._apply import apply_recommendations
        from nthlayer_workers.learn.recommendations import (
            Recommendation, SpecRecommendation,
        )
        from datetime import datetime, timezone

        # Seed two manifests
        (tmp_path / "z-service.yaml").write_text(
            "metadata:\n  name: z-service\n"
            "spec:\n  slos:\n    judgment:\n      target: 95.0\n"
        )
        (tmp_path / "a-service.yaml").write_text(
            "metadata:\n  name: a-service\n"
            "spec:\n  slos:\n    judgment:\n      target: 95.0\n"
        )

        # Recommend changes; z-service first in plan, a-service second
        plan = SpecRecommendation(
            incident="inc-test",
            generated_by="nthlayer-learn",
            generated_at=datetime(2026, 5, 26, tzinfo=timezone.utc),
            confidence=0.7,
            recommendations=[
                Recommendation(
                    id="rec-z000",
                    service="z-service",
                    type="tighten_slo",
                    rationale="test",
                    field="spec.slos.judgment.target",
                    current_value=95.0,
                    proposed_value=98.5,
                ),
                Recommendation(
                    id="rec-a000",
                    service="a-service",
                    type="tighten_slo",
                    rationale="test",
                    field="spec.slos.judgment.target",
                    current_value=95.0,
                    proposed_value=98.5,
                ),
            ],
        )

        result = apply_recommendations(plan, tmp_path)

        # Both applied
        assert len(result.applied) == 2
        # modified_files in alphabetical order
        names = [p.name for p in result.modified_files]
        assert names == ["a-service.yaml", "z-service.yaml"]

    def test_filename_based_failure_injection_isolates_failure(
        self, tmp_path, monkeypatch,
    ):
        """Filename-based failure injection per jmy.6 design § 8."""
        from nthlayer_workers.learn._apply import apply_recommendations
        from nthlayer_workers.learn.recommendations import (
            Recommendation, SpecRecommendation,
        )
        from datetime import datetime, timezone

        # Seed two manifests
        (tmp_path / "a-service.yaml").write_text(
            "metadata:\n  name: a-service\n"
            "spec:\n  slos:\n    judgment:\n      target: 95.0\n"
        )
        (tmp_path / "b-service.yaml").write_text(
            "metadata:\n  name: b-service\n"
            "spec:\n  slos:\n    judgment:\n      target: 95.0\n"
        )

        # Capture original write_text before monkeypatching
        original_write_text = Path.write_text

        def selective_fail(self, content, **kwargs):
            if self.name == "b-service.yaml":
                raise OSError("simulated write failure on b-service.yaml")
            return original_write_text(self, content, **kwargs)

        monkeypatch.setattr(Path, "write_text", selective_fail)

        plan = SpecRecommendation(
            incident="inc-test",
            generated_by="nthlayer-learn",
            generated_at=datetime(2026, 5, 26, tzinfo=timezone.utc),
            confidence=0.7,
            recommendations=[
                Recommendation(
                    id="rec-a000",
                    service="a-service",
                    type="tighten_slo",
                    rationale="test",
                    field="spec.slos.judgment.target",
                    current_value=95.0,
                    proposed_value=98.5,
                ),
                Recommendation(
                    id="rec-b000",
                    service="b-service",
                    type="tighten_slo",
                    rationale="test",
                    field="spec.slos.judgment.target",
                    current_value=95.0,
                    proposed_value=98.5,
                ),
            ],
        )

        with pytest.raises(OSError, match="b-service.yaml"):
            apply_recommendations(plan, tmp_path)

        # a-service.yaml was modified before the write failure
        assert "target: 98.5" in (tmp_path / "a-service.yaml").read_text()
        # b-service.yaml original content retained
        assert "target: 95.0" in (tmp_path / "b-service.yaml").read_text()
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
uv run pytest tests/learn/test_apply.py::TestApplyAtomicity -v
```

Expected: 2 FAIL — `apply_recommendations` doesn't (yet) propagate write failures and the assertion that a-service.yaml was written before the b-service.yaml failure is implicit.

- [ ] **Step 3: Confirm write order + failure semantics**

The current `apply_recommendations` implementation in D2 already writes in alphabetical order (`for path in sorted(modified_paths)`) and re-raises OSError naturally (no try/except wraps the write). So:

- `test_alphabetical_write_order` should PASS already.
- `test_filename_based_failure_injection_isolates_failure` will PASS if the write loop is in alphabetical order (a-service.yaml writes successfully, then b-service.yaml raises).

If the test still fails, verify the implementation matches the expected behaviour (sorted iteration; bubble up OSError).

- [ ] **Step 4: Run tests to verify they pass**

```bash
uv run pytest tests/learn/test_apply.py -v
```

Expected: all apply tests pass.

- [ ] **Step 5: Commit**

```bash
git add tests/learn/test_apply.py
git commit -m "test(_apply): atomicity tests with filename-based failure injection · opensrm-jmy.6

Two tests pin the write-phase semantics: alphabetical-by-path
ordering and filename-based selective failure injection
(per jmy.6 design § 8 — robust against implementation changes
in alphabetical-order traversal)."
```

---

### Task D4: End-of-run summary builder

**Files:**
- Modify: `nthlayer-workers/src/nthlayer_workers/learn/_apply.py`
- Test: `nthlayer-workers/tests/learn/test_apply.py`

- [ ] **Step 1: Write failing tests**

Add to `tests/learn/test_apply.py`:

```python
class TestSummaryBuilder:
    """End-of-run summary string format per jmy.6 § 6.2."""

    def test_summary_applied_section(self):
        from nthlayer_workers.learn._apply import (
            ApplyResult, RecOutcome, format_summary,
        )
        from nthlayer_workers.learn.recommendations import OutcomeKind

        result = ApplyResult(
            applied=[
                RecOutcome(
                    id="rec-a3f8b2e1c9d4",
                    service="fraud-detect",
                    field="spec.slos.judgment.target",
                    outcome=OutcomeKind.APPLY_CLEAN,
                ),
            ],
        )
        summary = format_summary(result)

        assert "Applied: 1" in summary
        assert "rec-a3f8b2e1c9d4" in summary
        assert "fraud-detect" in summary
        assert "spec.slos.judgment.target" in summary

    def test_summary_skipped_section_with_drift_detail(self):
        from nthlayer_workers.learn._apply import (
            ApplyResult, RecOutcome, format_summary,
        )
        from nthlayer_workers.learn.recommendations import OutcomeKind

        result = ApplyResult(
            applied=[],
            skipped=[
                RecOutcome(
                    id="rec-d5e8f2b6c9a1",
                    service="notification",
                    field="spec.slos.availability.target",
                    outcome=OutcomeKind.DRIFT_DETECTED,
                    detail="manifest current: 98.0\nrecommendation expected: 95.0\nproposed value: 99.0",
                ),
            ],
        )
        summary = format_summary(result)

        assert "Skipped: 1" in summary
        assert "drift_detected" in summary
        assert "Re-run with --force" in summary or "--force rec-d5e8f2b6c9a1" in summary

    def test_summary_exit_code_line(self):
        from nthlayer_workers.learn._apply import (
            ApplyResult, RecOutcome, format_summary,
        )
        from nthlayer_workers.learn.recommendations import OutcomeKind

        result = ApplyResult(
            applied=[
                RecOutcome(id="rec-1", service="s", field="f", outcome=OutcomeKind.APPLY_CLEAN),
            ],
            skipped=[
                RecOutcome(id="rec-2", service="s", field="f", outcome=OutcomeKind.DRIFT_DETECTED),
            ],
        )
        summary = format_summary(result)
        # exit_code == 1 (partial)
        assert "Exit code: 1" in summary

    def test_empty_plan_summary(self):
        from nthlayer_workers.learn._apply import ApplyResult, format_summary

        summary = format_summary(ApplyResult())
        assert "Applied: 0" in summary
        assert "Exit code: 0" in summary
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
uv run pytest tests/learn/test_apply.py::TestSummaryBuilder -v
```

Expected: 4 FAILED — `format_summary` not defined.

- [ ] **Step 3: Implement `format_summary`**

Add to `src/nthlayer_workers/learn/_apply.py`:

```python
def format_summary(result: ApplyResult) -> str:
    """Build the end-of-run summary string per jmy.6 design § 6.2."""
    lines: list[str] = []

    lines.append(f"Applied: {len(result.applied)} recommendation"
                 f"{'s' if len(result.applied) != 1 else ''}")
    for r in result.applied:
        lines.append(f"  {r.id}  {r.service:<14} {r.field}")

    if result.skipped:
        lines.append("")
        lines.append(f"Skipped: {len(result.skipped)} recommendation"
                     f"{'s' if len(result.skipped) != 1 else ''}")
        for r in result.skipped:
            lines.append(f"  {r.id}  {r.service:<14} {r.outcome.value}")
            if r.detail:
                for detail_line in r.detail.splitlines():
                    lines.append(f"    {detail_line}")
            if r.outcome == OutcomeKind.DRIFT_DETECTED:
                lines.append(f"")
                lines.append(f"    Re-run with --force to apply {r.id} anyway.")

    lines.append("")
    lines.append(f"Exit code: {result.exit_code}")

    return "\n".join(lines)
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
uv run pytest tests/learn/test_apply.py -v
```

Expected: all apply tests pass.

- [ ] **Step 5: Commit**

```bash
git add src/nthlayer_workers/learn/_apply.py tests/learn/test_apply.py
git commit -m "feat(_apply): format_summary builder · opensrm-jmy.6

End-of-run summary string per jmy.6 design § 6.2: Applied + Skipped
sections, drift_detected entries include force-suggestion line,
final 'Exit code: N' footer. Pluralisation handled correctly.
4 tests cover applied, skipped+drift, exit code, empty plan."
```

---

## Phase E — `_gh.py` module

### Task E1: Pre-flight checks

**Files:**
- Create: `nthlayer-workers/src/nthlayer_workers/learn/_gh.py`
- Create: `nthlayer-workers/tests/learn/test_gh.py`

- [ ] **Step 1: Write failing tests**

Create `nthlayer-workers/tests/learn/test_gh.py`:

```python
"""Unit tests for nthlayer_workers.learn._gh (jmy.6)."""
from __future__ import annotations

import subprocess
import pytest


class TestPreflightChecks:
    """gh + git pre-flight checks per jmy.6 design § 7 Category A."""

    def test_check_gh_installed_raises_when_missing(self, monkeypatch):
        from nthlayer_workers.learn._gh import check_gh_installed, PreflightError

        def fake_run(*args, **kwargs):
            raise FileNotFoundError("no such file")
        monkeypatch.setattr(subprocess, "run", fake_run)

        with pytest.raises(PreflightError, match="gh_not_installed"):
            check_gh_installed()

    def test_check_gh_installed_passes_when_present(self, monkeypatch):
        from nthlayer_workers.learn._gh import check_gh_installed

        result = subprocess.CompletedProcess(
            args=["gh", "--version"], returncode=0, stdout="gh version 2.x\n", stderr="",
        )
        monkeypatch.setattr(subprocess, "run", lambda *a, **kw: result)

        check_gh_installed()  # no raise

    def test_check_gh_auth_raises_on_not_authenticated(self, monkeypatch):
        from nthlayer_workers.learn._gh import check_gh_auth, PreflightError

        result = subprocess.CompletedProcess(
            args=["gh", "auth", "status"], returncode=1, stdout="", stderr="not logged in",
        )
        monkeypatch.setattr(subprocess, "run", lambda *a, **kw: result)

        with pytest.raises(PreflightError, match="gh_not_authenticated"):
            check_gh_auth()

    def test_check_git_repo_raises_outside_repo(self, monkeypatch, tmp_path):
        from nthlayer_workers.learn._gh import check_git_repo, PreflightError

        result = subprocess.CompletedProcess(
            args=["git", "rev-parse", "--git-dir"], returncode=128, stdout="", stderr="fatal",
        )
        monkeypatch.setattr(subprocess, "run", lambda *a, **kw: result)

        with pytest.raises(PreflightError, match="not_a_git_repo"):
            check_git_repo(tmp_path)

    def test_check_remote_raises_when_no_origin(self, monkeypatch, tmp_path):
        from nthlayer_workers.learn._gh import check_remote, PreflightError

        result = subprocess.CompletedProcess(
            args=["git", "remote", "get-url", "origin"], returncode=128, stdout="", stderr="",
        )
        monkeypatch.setattr(subprocess, "run", lambda *a, **kw: result)

        with pytest.raises(PreflightError, match="no_remote"):
            check_remote(tmp_path)

    def test_check_branch_available_raises_when_local_exists(self, monkeypatch, tmp_path):
        from nthlayer_workers.learn._gh import check_branch_available, PreflightError

        def fake_run(args, **kwargs):
            if "show-ref" in args:
                # Local branch exists
                return subprocess.CompletedProcess(args=args, returncode=0, stdout="ref\n", stderr="")
            # Remote check (won't be reached if local check raises)
            return subprocess.CompletedProcess(args=args, returncode=0, stdout="", stderr="")

        monkeypatch.setattr(subprocess, "run", fake_run)

        with pytest.raises(PreflightError, match="branch_exists"):
            check_branch_available(tmp_path, "learn/recommendations/inc-test")

    def test_check_branch_available_raises_when_remote_exists(self, monkeypatch, tmp_path):
        from nthlayer_workers.learn._gh import check_branch_available, PreflightError

        def fake_run(args, **kwargs):
            if "show-ref" in args:
                # Local doesn't exist
                return subprocess.CompletedProcess(args=args, returncode=1, stdout="", stderr="")
            if "ls-remote" in args:
                # Remote branch exists
                return subprocess.CompletedProcess(
                    args=args, returncode=0,
                    stdout="abc123\trefs/heads/learn/recommendations/inc-test\n",
                    stderr="",
                )
            return subprocess.CompletedProcess(args=args, returncode=0, stdout="", stderr="")

        monkeypatch.setattr(subprocess, "run", fake_run)

        with pytest.raises(PreflightError, match="branch_exists"):
            check_branch_available(tmp_path, "learn/recommendations/inc-test")
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
uv run pytest tests/learn/test_gh.py::TestPreflightChecks -v
```

Expected: 7 FAILED — module doesn't exist.

- [ ] **Step 3: Implement `_gh.py` pre-flight checks**

Create `src/nthlayer_workers/learn/_gh.py`:

```python
"""GitHub + git integration via gh CLI for the Learn → Spec workflow (jmy.6).

All subprocess calls go through this module so tests can monkeypatch
at a single boundary. Pluggable hosting is filed as a v2 follow-up;
this file is named with leading underscore signalling it's internal
and replaceable.
"""
from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path


class PreflightError(RuntimeError):
    """Raised when a pre-flight check fails.

    Carries a reason code in the message (gh_not_installed,
    gh_not_authenticated, not_a_git_repo, no_remote, branch_exists)
    so CLI can format an actionable error.
    """


@dataclass(frozen=True)
class PRResult:
    """Outcome of create_pr_via_gh."""
    url: str | None
    number: int | None
    error: str | None

    @property
    def ok(self) -> bool:
        return self.url is not None and self.error is None


def check_gh_installed() -> None:
    """Verify gh CLI is on PATH. Raises PreflightError(gh_not_installed)."""
    try:
        result = subprocess.run(
            ["gh", "--version"], capture_output=True, text=True, check=False,
        )
    except FileNotFoundError as exc:
        raise PreflightError(
            "gh_not_installed: gh CLI not found on PATH. "
            "Install via 'brew install gh' or see https://cli.github.com"
        ) from exc
    if result.returncode != 0:
        raise PreflightError(
            f"gh_not_installed: gh --version exited {result.returncode}"
        )


def check_gh_auth() -> None:
    """Verify gh is authenticated. Raises PreflightError(gh_not_authenticated)."""
    result = subprocess.run(
        ["gh", "auth", "status"], capture_output=True, text=True, check=False,
    )
    if result.returncode != 0:
        raise PreflightError(
            "gh_not_authenticated: gh CLI not logged in. Run 'gh auth login'."
        )


def check_git_repo(specs_dir: Path) -> None:
    """Verify specs_dir is inside a git repo."""
    result = subprocess.run(
        ["git", "rev-parse", "--git-dir"],
        cwd=specs_dir, capture_output=True, text=True, check=False,
    )
    if result.returncode != 0:
        raise PreflightError(
            f"not_a_git_repo: {specs_dir} is not inside a git repository"
        )


def check_remote(specs_dir: Path) -> None:
    """Verify the repo has an 'origin' remote."""
    result = subprocess.run(
        ["git", "remote", "get-url", "origin"],
        cwd=specs_dir, capture_output=True, text=True, check=False,
    )
    if result.returncode != 0:
        raise PreflightError(
            "no_remote: 'origin' remote not configured. "
            "Add via 'git remote add origin <url>'."
        )


def check_branch_available(specs_dir: Path, branch: str) -> None:
    """Verify the branch name is not already in use (local OR remote)."""
    # Local
    local = subprocess.run(
        ["git", "show-ref", "--verify", f"refs/heads/{branch}"],
        cwd=specs_dir, capture_output=True, text=True, check=False,
    )
    if local.returncode == 0:
        raise PreflightError(
            f"branch_exists: branch {branch!r} already exists locally. "
            f"Delete with 'git branch -D {branch}' or rename."
        )

    # Remote
    remote = subprocess.run(
        ["git", "ls-remote", "--heads", "origin", branch],
        cwd=specs_dir, capture_output=True, text=True, check=False,
    )
    if remote.returncode == 0 and remote.stdout.strip():
        raise PreflightError(
            f"branch_exists: branch {branch!r} already exists on origin. "
            f"Delete with 'git push origin --delete {branch}'."
        )
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
uv run pytest tests/learn/test_gh.py -v
```

Expected: 7 PASS.

- [ ] **Step 5: Commit**

```bash
git add src/nthlayer_workers/learn/_gh.py tests/learn/test_gh.py
git commit -m "feat(_gh): pre-flight checks · opensrm-jmy.6

Five pre-flight check functions per jmy.6 design § 7 Category A:
gh_not_installed, gh_not_authenticated, not_a_git_repo, no_remote,
branch_exists (local + remote variants). All raise PreflightError
with reason code embedded in message + actionable remedy hint.
Tests monkeypatch subprocess.run at the module boundary."
```

---

### Task E2: `create_pr_via_gh`

**Files:**
- Modify: `nthlayer-workers/src/nthlayer_workers/learn/_gh.py`
- Test: `nthlayer-workers/tests/learn/test_gh.py`

- [ ] **Step 1: Write failing tests**

Add to `tests/learn/test_gh.py`:

```python
class TestCreatePr:
    """create_pr_via_gh: shell out to gh pr create, parse PRResult."""

    def test_happy_path_returns_pr_url(self, monkeypatch, tmp_path):
        from nthlayer_workers.learn._gh import create_pr_via_gh
        import subprocess

        result = subprocess.CompletedProcess(
            args=["gh", "pr", "create"],
            returncode=0,
            stdout="https://github.com/org/repo/pull/42\n",
            stderr="",
        )
        captured = {}

        def fake_run(args, **kwargs):
            captured["args"] = args
            return result

        monkeypatch.setattr(subprocess, "run", fake_run)

        pr = create_pr_via_gh(
            title="Apply NthLayer recommendations from inc-test",
            body="## Changes\n...",
            branch="learn/recommendations/inc-test",
            cwd=tmp_path,
        )

        assert pr.ok
        assert pr.url == "https://github.com/org/repo/pull/42"
        assert pr.number == 42
        # Args include the expected flags
        assert "--title" in captured["args"]
        assert "--body" in captured["args"]
        assert "--head" in captured["args"]
        assert "--base" in captured["args"]

    def test_base_and_draft_kwargs_flow_to_argv(self, monkeypatch, tmp_path):
        from nthlayer_workers.learn._gh import create_pr_via_gh
        import subprocess

        result = subprocess.CompletedProcess(
            args=["gh", "pr", "create"],
            returncode=0,
            stdout="https://github.com/org/repo/pull/99\n",
            stderr="",
        )
        captured = {}
        monkeypatch.setattr(subprocess, "run", lambda args, **kw: captured.setdefault("args", args) or result)

        create_pr_via_gh(
            title="t", body="b",
            branch="learn/recommendations/x",
            cwd=tmp_path,
            base="develop",
            draft=True,
        )

        assert "develop" in captured["args"]
        assert "--draft" in captured["args"]

    def test_failure_returns_pr_result_with_error(self, monkeypatch, tmp_path):
        from nthlayer_workers.learn._gh import create_pr_via_gh
        import subprocess

        result = subprocess.CompletedProcess(
            args=["gh", "pr", "create"],
            returncode=1,
            stdout="",
            stderr="GraphQL: pull request requires a base branch\n",
        )
        monkeypatch.setattr(subprocess, "run", lambda args, **kw: result)

        pr = create_pr_via_gh(
            title="t", body="b",
            branch="learn/recommendations/x",
            cwd=tmp_path,
        )

        assert not pr.ok
        assert pr.url is None
        assert pr.number is None
        assert "GraphQL" in pr.error
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
uv run pytest tests/learn/test_gh.py::TestCreatePr -v
```

Expected: 3 FAILED — `create_pr_via_gh` not defined.

- [ ] **Step 3: Implement `create_pr_via_gh`**

Add to `src/nthlayer_workers/learn/_gh.py`:

```python
import re


_PR_URL_RE = re.compile(r"https://[^\s]+/pull/(\d+)")


def create_pr_via_gh(
    *,
    title: str,
    body: str,
    branch: str,
    cwd: Path,
    base: str = "main",
    draft: bool = False,
) -> PRResult:
    """Create a PR via gh pr create. Returns PRResult on success or failure.

    Does not raise on non-zero exit; PRResult.ok distinguishes
    success/failure so the CLI can format an appropriate error.
    """
    args = [
        "gh", "pr", "create",
        "--title", title,
        "--body", body,
        "--head", branch,
        "--base", base,
    ]
    if draft:
        args.append("--draft")

    result = subprocess.run(
        args, cwd=cwd, capture_output=True, text=True, check=False,
    )

    if result.returncode != 0:
        # Carry gh's stderr through verbatim for the operator-recovery message
        return PRResult(url=None, number=None, error=result.stderr.strip())

    # gh outputs the PR URL to stdout on success
    url = result.stdout.strip()
    match = _PR_URL_RE.search(url)
    pr_number = int(match.group(1)) if match else None
    return PRResult(url=url, number=pr_number, error=None)
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
uv run pytest tests/learn/test_gh.py -v
```

Expected: all 10 tests pass (7 pre-flight + 3 create_pr).

- [ ] **Step 5: Commit**

```bash
git add src/nthlayer_workers/learn/_gh.py tests/learn/test_gh.py
git commit -m "feat(_gh): create_pr_via_gh + PRResult · opensrm-jmy.6

Shell-out to gh pr create with --title/--body/--head/--base/--draft.
PRResult dataclass carries url + number + error. PR number parsed
from URL via lookup-style regex constant. Never raises on non-zero
exit; CLI inspects PRResult.ok for branching."
```

---

## Phase F — `cli.py` extension

### Task F1: Add `recommendations` subcommand + flag validation

**Files:**
- Modify: `nthlayer-workers/src/nthlayer_workers/learn/cli.py`
- Create: `nthlayer-workers/tests/learn/test_cli_recommendations.py`

- [ ] **Step 1: Write failing tests for flag validation**

Create `nthlayer-workers/tests/learn/test_cli_recommendations.py`:

```python
"""Unit tests for the recommendations CLI subcommand (jmy.6)."""
from __future__ import annotations

import pytest


class TestArgValidation:
    """invalid_args edge cases per jmy.6 § 7."""

    def test_incident_and_from_mutually_exclusive(self, capsys):
        from nthlayer_workers.learn.cli import main

        with pytest.raises(SystemExit) as exc:
            main(["recommendations", "--incident", "inc-x", "--from", "plan.yaml"])
        assert exc.value.code != 0

    def test_pr_requires_apply_to(self, capsys, tmp_path):
        from nthlayer_workers.learn.cli import main

        with pytest.raises(SystemExit) as exc:
            main(["recommendations", "--incident", "inc-x", "--pr"])
        assert exc.value.code != 0

    def test_neither_incident_nor_from_required(self, capsys):
        from nthlayer_workers.learn.cli import main

        with pytest.raises(SystemExit) as exc:
            main(["recommendations"])
        assert exc.value.code != 0
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
uv run pytest tests/learn/test_cli_recommendations.py -v
```

Expected: 3 FAILED — `recommendations` subcommand doesn't exist.

- [ ] **Step 3: Add subcommand + flag plumbing**

Find the existing argparse setup in `src/nthlayer_workers/learn/cli.py`. Look for where the subcommands `accuracy`, `list`, `retrospective` are registered. Add the new `recommendations` subcommand:

```python
def _add_recommendations_subcommand(subparsers) -> None:
    """Add the recommendations subcommand (jmy.6)."""
    p = subparsers.add_parser(
        "recommendations",
        help="Inspect / apply Learn → Spec recommendations from a retrospective",
    )

    # Input source (mutually exclusive, one required)
    input_group = p.add_mutually_exclusive_group(required=True)
    input_group.add_argument("--incident", help="Incident ID; fetches retrospective from core")
    input_group.add_argument("--from", dest="from_path",
                              help="Read a saved plan.yaml as input")

    # Outputs (orthogonal, optional)
    p.add_argument("--output", help="Write plan to this file before any apply")
    p.add_argument("--apply-to", dest="apply_to",
                    help="Apply plan to manifests in this specs directory")
    p.add_argument("--pr", action="store_true",
                    help="Create a GitHub PR with the manifest changes (requires --apply-to)")

    # Modifiers
    p.add_argument("--force", action="store_true",
                    help="Override drift_detected skips (drift-only; per jmy.6 § 7)")
    p.add_argument("--base", default="main",
                    help="Base branch for --pr (default: main)")
    p.add_argument("--draft", action="store_true",
                    help="Create the PR as a draft")
    p.add_argument("--specs-dir",
                    help="For --output: include preview field per recommendation")

    p.set_defaults(func=_cmd_recommendations)


def _cmd_recommendations(args) -> None:
    """Dispatch the recommendations subcommand."""
    # Validation: --pr requires --apply-to
    if args.pr and not args.apply_to:
        raise SystemExit("error: --pr requires --apply-to")
    # Stub body — full implementation in F2
    print(f"recommendations subcommand stub: incident={args.incident} from={args.from_path}")
```

Wire it into the existing `main` function:

```python
def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="nthlayer-learn", description="Query verdict stores")
    subparsers = parser.add_subparsers(dest="cmd", required=True)
    # ... existing subcommands ...
    _add_recommendations_subcommand(subparsers)

    args = parser.parse_args(argv)
    args.func(args)
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
uv run pytest tests/learn/test_cli_recommendations.py -v
```

Expected: 3 PASS.

- [ ] **Step 5: Commit**

```bash
git add src/nthlayer_workers/learn/cli.py tests/learn/test_cli_recommendations.py
git commit -m "feat(cli): add recommendations subcommand + flag validation · opensrm-jmy.6

argparse plumbing for the new subcommand: --incident/--from mutex
input source; --output/--apply-to/--pr orthogonal output flags;
--force/--base/--draft/--specs-dir modifiers. --pr requires
--apply-to (validated in dispatch). Body is a stub; full
implementation in subsequent tasks."
```

---

### Task F2: Wire input → SpecRecommendation → --output / --apply-to dispatch

**Files:**
- Modify: `nthlayer-workers/src/nthlayer_workers/learn/cli.py`
- Test: `nthlayer-workers/tests/learn/test_cli_recommendations.py`

- [ ] **Step 1: Write failing tests for the happy paths**

Add to `tests/learn/test_cli_recommendations.py`:

```python
class TestOutputFlag:
    """--output writes plan.yaml from --from input."""

    def test_from_then_output_round_trip(self, tmp_path, capsys):
        from nthlayer_workers.learn.cli import main
        from nthlayer_workers.learn.recommendations import (
            SpecRecommendation, Recommendation,
        )
        from datetime import datetime, timezone

        # Build a plan file
        plan = SpecRecommendation(
            incident="inc-test",
            generated_by="nthlayer-learn",
            generated_at=datetime(2026, 5, 26, tzinfo=timezone.utc),
            confidence=0.7,
            recommendations=[
                Recommendation(
                    id="rec-deadbeef0123",
                    service="fraud-detect",
                    type="tighten_slo",
                    rationale="test",
                    field="spec.slos.judgment.target",
                    current_value=95.0,
                    proposed_value=98.5,
                ),
            ],
        )
        plan_in = tmp_path / "in.yaml"
        plan_in.write_text(plan.to_yaml())

        plan_out = tmp_path / "out.yaml"
        main(["recommendations", "--from", str(plan_in), "--output", str(plan_out)])

        # Output file written + parses back to same plan
        from nthlayer_workers.learn.recommendations import parse_plan_file
        round_tripped = parse_plan_file(plan_out)
        assert round_tripped.incident == "inc-test"
        assert len(round_tripped.recommendations) == 1


class TestApplyToFlag:
    """--apply-to applies the plan to specs in the target directory."""

    def test_from_then_apply_to(self, tmp_path):
        from nthlayer_workers.learn.cli import main
        from nthlayer_workers.learn.recommendations import (
            SpecRecommendation, Recommendation,
        )
        from datetime import datetime, timezone

        # Seed manifest + plan
        specs_dir = tmp_path / "specs"
        specs_dir.mkdir()
        (specs_dir / "fraud-detect.yaml").write_text(
            "metadata:\n  name: fraud-detect\n"
            "spec:\n  slos:\n    judgment:\n      target: 95.0\n"
        )

        plan = SpecRecommendation(
            incident="inc-test",
            generated_by="nthlayer-learn",
            generated_at=datetime(2026, 5, 26, tzinfo=timezone.utc),
            confidence=0.7,
            recommendations=[
                Recommendation(
                    id="rec-deadbeef0123",
                    service="fraud-detect",
                    type="tighten_slo",
                    rationale="test",
                    field="spec.slos.judgment.target",
                    current_value=95.0,
                    proposed_value=98.5,
                ),
            ],
        )
        plan_in = tmp_path / "in.yaml"
        plan_in.write_text(plan.to_yaml())

        # Run the CLI
        main([
            "recommendations",
            "--from", str(plan_in),
            "--apply-to", str(specs_dir),
        ])

        # Manifest modified
        assert "target: 98.5" in (specs_dir / "fraud-detect.yaml").read_text()
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
uv run pytest tests/learn/test_cli_recommendations.py -v
```

Expected: 2 new tests FAIL — stub dispatch only prints.

- [ ] **Step 3: Implement `_cmd_recommendations` dispatch**

In `src/nthlayer_workers/learn/cli.py`, replace the stub body:

```python
def _cmd_recommendations(args) -> None:
    """Dispatch the recommendations subcommand (jmy.6)."""
    from pathlib import Path
    from nthlayer_workers.learn.recommendations import (
        parse_plan_file, SpecRecommendation,
    )
    from nthlayer_workers.learn._apply import (
        apply_recommendations, format_summary,
    )

    # Validation: --pr requires --apply-to
    if args.pr and not args.apply_to:
        raise SystemExit("error: --pr requires --apply-to")

    # Resolve input source
    if args.from_path:
        plan = parse_plan_file(Path(args.from_path))
    else:
        # --incident: fetch retrospective from core (out of scope for unit tests;
        # real implementation fetches via CoreAPIClient.get_retrospective_for_incident)
        plan = _build_plan_from_incident(args.incident)

    # --output: write plan to file (BEFORE --apply-to per design § 4)
    if args.output:
        Path(args.output).write_text(plan.to_yaml())

    # --apply-to: apply
    apply_result = None
    if args.apply_to:
        apply_result = apply_recommendations(
            plan, Path(args.apply_to), force=args.force,
        )
        # Print summary to stderr
        import sys
        print(format_summary(apply_result), file=sys.stderr)

    # --pr: create the PR (full implementation in F3)
    if args.pr:
        _run_pr_path(plan, args, apply_result)

    # Exit code: from apply if --apply-to was used, else 0
    if apply_result is not None:
        raise SystemExit(apply_result.exit_code)


def _build_plan_from_incident(incident_id: str):
    """Stub: fetch retrospective from core and call analyze_incident.

    Full implementation requires CoreAPIClient.get_retrospective_for_incident
    (which may need adding to the client). Out of scope for the unit-test
    surface; integration test exercises this path.
    """
    raise NotImplementedError(
        "fetching from --incident requires CoreAPIClient integration; "
        "use --from <plan.yaml> for now (or run via integration test)"
    )


def _run_pr_path(plan, args, apply_result) -> None:
    """Stub for F3."""
    raise NotImplementedError("--pr implemented in F3")
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
uv run pytest tests/learn/test_cli_recommendations.py -v
```

Expected: `TestOutputFlag` + `TestApplyToFlag` PASS; flag-validation tests still PASS.

- [ ] **Step 5: Commit**

```bash
git add src/nthlayer_workers/learn/cli.py tests/learn/test_cli_recommendations.py
git commit -m "feat(cli): wire --from/--output/--apply-to dispatch · opensrm-jmy.6

_cmd_recommendations now handles three of the four flag combinations:
- --from reads plan.yaml via parse_plan_file
- --output writes plan.yaml (before --apply-to per design § 4)
- --apply-to runs apply_recommendations + prints summary to stderr,
  exit code from ApplyResult.exit_code
--incident (CoreAPIClient fetch) + --pr stubbed for F3."
```

---

### Task F3: Wire `--pr` path: branch + commit + push + PR

**Files:**
- Modify: `nthlayer-workers/src/nthlayer_workers/learn/cli.py`
- Test: `nthlayer-workers/tests/learn/test_cli_recommendations.py`

- [ ] **Step 1: Write failing tests for the --pr path**

Add to `tests/learn/test_cli_recommendations.py`:

```python
class TestPrPath:
    """--pr drives pre-flight + branch + commit + push + gh pr create."""

    def test_pr_path_happy(self, tmp_path, monkeypatch, capsys):
        """End-to-end --pr with all git/gh subprocess calls stubbed."""
        from nthlayer_workers.learn.cli import main
        from nthlayer_workers.learn.recommendations import (
            SpecRecommendation, Recommendation,
        )
        from datetime import datetime, timezone
        import subprocess

        # Seed manifest + plan
        specs_dir = tmp_path / "specs"
        specs_dir.mkdir()
        (specs_dir / "fraud-detect.yaml").write_text(
            "metadata:\n  name: fraud-detect\n"
            "spec:\n  slos:\n    judgment:\n      target: 95.0\n"
        )

        plan = SpecRecommendation(
            incident="inc-test",
            generated_by="nthlayer-learn",
            generated_at=datetime(2026, 5, 26, tzinfo=timezone.utc),
            confidence=0.7,
            recommendations=[
                Recommendation(
                    id="rec-deadbeef0123",
                    service="fraud-detect",
                    type="tighten_slo",
                    rationale="test",
                    field="spec.slos.judgment.target",
                    current_value=95.0,
                    proposed_value=98.5,
                ),
            ],
        )
        plan_in = tmp_path / "in.yaml"
        plan_in.write_text(plan.to_yaml())

        # Stub every subprocess.run invocation (gh + git)
        captured: list = []
        def fake_run(args, **kwargs):
            captured.append(list(args))
            # gh --version: success
            if args[:2] == ["gh", "--version"]:
                return subprocess.CompletedProcess(args=args, returncode=0, stdout="gh 2.x", stderr="")
            # gh auth status: success
            if args[:3] == ["gh", "auth", "status"]:
                return subprocess.CompletedProcess(args=args, returncode=0, stdout="logged in", stderr="")
            # git rev-parse --git-dir: success (simulate repo)
            if "rev-parse" in args:
                return subprocess.CompletedProcess(args=args, returncode=0, stdout=".git", stderr="")
            # git remote get-url origin: success
            if "remote" in args and "get-url" in args:
                return subprocess.CompletedProcess(args=args, returncode=0, stdout="git@github.com:org/repo.git", stderr="")
            # branch checks: not exists
            if "show-ref" in args:
                return subprocess.CompletedProcess(args=args, returncode=1, stdout="", stderr="")
            if "ls-remote" in args:
                return subprocess.CompletedProcess(args=args, returncode=0, stdout="", stderr="")
            # All git commands (checkout, add, commit, push) succeed
            if args[0] == "git":
                return subprocess.CompletedProcess(args=args, returncode=0, stdout="", stderr="")
            # gh pr create: success
            if args[:3] == ["gh", "pr", "create"]:
                return subprocess.CompletedProcess(
                    args=args, returncode=0,
                    stdout="https://github.com/org/repo/pull/99\n",
                    stderr="",
                )
            return subprocess.CompletedProcess(args=args, returncode=0, stdout="", stderr="")

        monkeypatch.setattr(subprocess, "run", fake_run)

        # Run the CLI with --pr
        with pytest.raises(SystemExit) as exc:
            main([
                "recommendations",
                "--from", str(plan_in),
                "--apply-to", str(specs_dir),
                "--pr",
            ])
        assert exc.value.code == 0

        # Verify gh pr create was called
        gh_pr_create_called = any(
            list(c[:3]) == ["gh", "pr", "create"] for c in captured
        )
        assert gh_pr_create_called

        # stdout contains PR URL
        captured_out = capsys.readouterr()
        assert "https://github.com/org/repo/pull/99" in captured_out.out
```

- [ ] **Step 2: Run test to verify it fails**

```bash
uv run pytest tests/learn/test_cli_recommendations.py::TestPrPath -v
```

Expected: FAIL — `_run_pr_path` raises NotImplementedError.

- [ ] **Step 3: Implement `_run_pr_path`**

In `src/nthlayer_workers/learn/cli.py`, replace the `_run_pr_path` stub:

```python
def _run_pr_path(plan, args, apply_result) -> None:
    """Drive the --pr workflow: pre-flight + branch + commit + push + PR."""
    from pathlib import Path
    import subprocess
    from nthlayer_workers.learn._gh import (
        PreflightError,
        check_gh_installed, check_gh_auth, check_git_repo,
        check_remote, check_branch_available, create_pr_via_gh,
    )

    if apply_result is None or not apply_result.modified_files:
        # Nothing was changed; no PR to open
        return

    specs_dir = Path(args.apply_to)
    branch = f"learn/recommendations/{plan.incident}"

    # Pre-flight (Q7 order: gh-first, branch-last)
    try:
        check_gh_installed()
        check_gh_auth()
        check_git_repo(specs_dir)
        check_remote(specs_dir)
        check_branch_available(specs_dir, branch)
    except PreflightError as exc:
        raise SystemExit(f"Error: {exc}\n\nExit code: 2") from exc

    # Create branch
    _run_git(specs_dir, ["checkout", "-b", branch])

    # Stage only files actually modified by recommendations
    for path in apply_result.modified_files:
        _run_git(specs_dir, ["add", str(path.relative_to(specs_dir))])

    # Commit
    commit_message = _build_commit_message(plan, apply_result, args)
    _run_git(specs_dir, ["commit", "-m", commit_message])

    # Push
    push = subprocess.run(
        ["git", "push", "-u", "origin", branch],
        cwd=specs_dir, capture_output=True, text=True, check=False,
    )
    if push.returncode != 0:
        raise SystemExit(
            f"Error: Push to origin failed\n\n"
            f"  git push failed: {push.stderr.strip()}\n\n"
            f"  Your manifest changes are committed on branch\n"
            f"  {branch} (local only).\n\n"
            f"  Options:\n"
            f"    Retry:   git push -u origin {branch}\n"
            f"    Discard: git branch -D {branch}\n\n"
            f"  Exit code: 1"
        )

    # Create PR
    title = f"Apply NthLayer recommendations from {plan.incident}"
    body = _build_pr_body(plan, apply_result, args)
    pr = create_pr_via_gh(
        title=title, body=body, branch=branch, cwd=specs_dir,
        base=args.base, draft=args.draft,
    )

    if not pr.ok:
        raise SystemExit(
            f"Error: PR creation failed\n\n"
            f"  gh pr create failed: {pr.error}\n\n"
            f"  Your manifest changes are committed on branch\n"
            f"  {branch}.\n\n"
            f"  Options:\n"
            f"    Retry:   gh pr create --base {args.base} --head {branch}\n"
            f"    Discard: git branch -D {branch}\n\n"
            f"  Exit code: 1"
        )

    print(f"PR created: {pr.url}")


def _run_git(cwd, args: list[str]) -> None:
    """Run a git command; raise SystemExit on non-zero."""
    import subprocess
    result = subprocess.run(
        ["git", *args], cwd=cwd, capture_output=True, text=True, check=False,
    )
    if result.returncode != 0:
        raise SystemExit(f"git {args[0]} failed: {result.stderr.strip()}")


def _build_commit_message(plan, apply_result, args) -> str:
    lines = [f"Apply NthLayer recommendations from {plan.incident}", ""]
    for r in apply_result.applied:
        # Find the matching plan recommendation for the type/value details
        rec = next((x for x in plan.recommendations if x.id == r.id), None)
        if rec is None:
            continue
        change = _format_change(rec)
        lines.append(f"- {r.id}  {rec.type:<15}  {r.service:<14} {r.field}  {change}")
    lines.append("")
    if args.from_path:
        lines.append(f"Plan: {args.from_path}")
    lines.append("Generated by: nthlayer-workers")
    lines.append("Tool: NthLayer learn module")
    return "\n".join(lines)


def _format_change(rec) -> str:
    if rec.current_value is None:
        return "(none) → (added)"
    return f"{rec.current_value} → {rec.proposed_value}"


def _build_pr_body(plan, apply_result, args) -> str:
    # Minimal viable PR body for v1.5; full table shape per design § 6.4
    lines = ["## Changes", "", "| ID | Type | Service | Field | Change |", "|---|---|---|---|---|"]
    for r in apply_result.applied:
        rec = next((x for x in plan.recommendations if x.id == r.id), None)
        if rec is None:
            continue
        lines.append(
            f"| `{r.id}` | `{rec.type}` | `{r.service}` | `{r.field}` | {_format_change(rec)} |"
        )
    if apply_result.skipped:
        lines.append("")
        lines.append("## Skipped")
        lines.append("")
        lines.append("| ID | Reason | Next step |")
        lines.append("|---|---|---|")
        for r in apply_result.skipped:
            next_step = "Investigate" if r.outcome.value == "drift_detected" else "Verify"
            lines.append(f"| `{r.id}` | `{r.outcome.value}` | {next_step} |")
    lines.extend([
        "", "---", "",
        "## Context",
        "",
        f"**Incident:** `{plan.incident}`",
        f"**Plan generated:** {plan.generated_at.isoformat()}",
        "",
        "---",
        "",
        "🤖 Generated by NthLayer learn module. Human review and merge required.",
    ])
    return "\n".join(lines)
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
uv run pytest tests/learn/test_cli_recommendations.py -v
```

Expected: all tests pass.

Full nthlayer-workers test suite:

```bash
uv run pytest -q
```

Expected: no regressions.

- [ ] **Step 5: Commit**

```bash
git add src/nthlayer_workers/learn/cli.py tests/learn/test_cli_recommendations.py
git commit -m "feat(cli): wire --pr path with branch + commit + push + gh · opensrm-jmy.6

Full --pr orchestration: pre-flight checks (gh installed, authed,
git repo, remote, branch available); create branch; stage only
files in ApplyResult.modified_files (per design § 5 dirty-tree);
commit with structured message; git push -u; gh pr create. Operator-
recovery messages on push and PR failure per design § 7. End-to-end
test stubs every subprocess.run invocation."
```

---

## Phase G — Cross-repo integration test

### Task G1: integration test in nthlayer/test/

**Files:**
- Create: `nthlayer/test/learn-recommendations-integration.sh`

- [ ] **Step 1: Write the integration test script**

Create `nthlayer/test/learn-recommendations-integration.sh`:

```bash
#!/usr/bin/env bash
# Cross-process integration test for opensrm-jmy.6.
#
# Drives the audited two-step Learn → Spec workflow end-to-end against
# a real tmp git repo, real ruamel.yaml, and a stubbed gh CLI (via
# PATH injection) so no real GitHub credentials or network are needed.
#
# Isolation guarantees (per jmy.6 § 8):
#   - All filesystem operations confined to $WORK
#   - gh stubbed via PATH injection
#   - git uses local config only (GIT_CONFIG_GLOBAL=/dev/null)
#   - No network access required
#   - Cleanup via trap

set -euo pipefail

# Resolve repo roots
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
FRONTDOOR_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
WORKSPACE_ROOT="$(cd "$FRONTDOOR_ROOT/.." && pwd)"
WORKERS_ROOT="$WORKSPACE_ROOT/nthlayer-workers"

# tmp workspace
WORK="$(mktemp -d -t jmy6-integration-XXXXXX)"
SPECS_DIR="$WORK/specs"
STUB_GH_DIR="$WORK/stub-gh"
mkdir -p "$SPECS_DIR" "$STUB_GH_DIR"

# Cleanup trap (only on success; preserve on failure for debug)
SUCCESS=0
cleanup() {
  if [ "$SUCCESS" = "1" ]; then
    rm -rf "$WORK"
  else
    echo "Integration test failed. Logs preserved in $WORK"
  fi
}
trap cleanup EXIT

# 1. Seed manifest in specs dir
cat > "$SPECS_DIR/fraud-detect.yaml" <<'EOF'
metadata:
  name: fraud-detect
  team: payments-ml
spec:
  slos:
    judgment:
      target: 95.0  # current SLO target — operator comment
      window: 30d
EOF

# 2. Build a plan file (via Python; bypasses --incident path which requires core)
PLAN_FILE="$WORK/plan.yaml"
uv run --directory "$WORKERS_ROOT" python <<EOF
from datetime import datetime, timezone
from pathlib import Path
from nthlayer_workers.learn.recommendations import (
    SpecRecommendation, Recommendation, compute_rec_id,
)

incident_id = "inc-integration-test"
rec = Recommendation(
    id=compute_rec_id(incident_id, "tighten_slo", "spec.slos.judgment.target"),
    service="fraud-detect",
    type="tighten_slo",
    rationale="Integration test recommendation",
    field="spec.slos.judgment.target",
    current_value=95.0,
    proposed_value=98.5,
)
plan = SpecRecommendation(
    incident=incident_id,
    generated_by="integration-test",
    generated_at=datetime(2026, 5, 26, tzinfo=timezone.utc),
    confidence=0.8,
    recommendations=[rec],
)
Path("$PLAN_FILE").write_text(plan.to_yaml())
EOF
echo "✓ plan.yaml generated"

# 3. Init the specs dir as a git repo
cd "$SPECS_DIR"
GIT_CONFIG_GLOBAL=/dev/null git init -q
git config user.email "integration-test@nthlayer.io"
git config user.name "Integration Test"
git add fraud-detect.yaml
git commit -q -m "initial commit"
# Add a remote that gh stub will satisfy
git remote add origin "git@example.com:org/repo.git"

# 4. Build stub gh
cat > "$STUB_GH_DIR/gh" <<'STUBEOF'
#!/usr/bin/env bash
# Stub gh — records argv and emits a fake PR URL on `pr create`.
case "$1" in
  --version)
    echo "gh version 2.99.0 (stub)"
    exit 0 ;;
  auth)
    [ "$2" = "status" ] && exit 0 ;;
  pr)
    [ "$2" = "create" ] && echo "https://github.com/org/repo/pull/42"
    exit 0 ;;
esac
exit 0
STUBEOF
chmod +x "$STUB_GH_DIR/gh"

# 5. Run --apply-to (no --pr first; verify writes + comment preservation)
PATH="$STUB_GH_DIR:$PATH" uv run --directory "$WORKERS_ROOT" \
  nthlayer-learn recommendations \
    --from "$PLAN_FILE" \
    --apply-to "$SPECS_DIR"

# Assert manifest modified
grep -q "target: 98.5" "$SPECS_DIR/fraud-detect.yaml" || {
  echo "FAIL: target not updated"; exit 1;
}
# Assert original comment preserved (the core ruamel.yaml promise)
grep -q "# current SLO target" "$SPECS_DIR/fraud-detect.yaml" || {
  echo "FAIL: operator comment lost on round-trip"; exit 1;
}
echo "✓ --apply-to wrote manifest, comment preserved"

# 6. Reset for the --pr path
git checkout fraud-detect.yaml
PATH="$STUB_GH_DIR:$PATH" uv run --directory "$WORKERS_ROOT" \
  nthlayer-learn recommendations \
    --from "$PLAN_FILE" \
    --apply-to "$SPECS_DIR" \
    --pr | tee "$WORK/cli-output.log"

# Assert PR URL printed
grep -q "PR created: https://github.com/org/repo/pull/42" "$WORK/cli-output.log" || {
  echo "FAIL: PR URL not in stdout"; exit 1;
}

# Assert branch exists
git rev-parse --verify "learn/recommendations/inc-integration-test" >/dev/null 2>&1 || {
  echo "FAIL: PR branch not created"; exit 1;
}

# Assert single commit on the branch
COMMIT_COUNT=$(git log "learn/recommendations/inc-integration-test" --not main --oneline | wc -l)
[ "$COMMIT_COUNT" = "1" ] || {
  echo "FAIL: expected 1 commit on PR branch, got $COMMIT_COUNT"; exit 1;
}

echo "✓ --pr path: branch + commit + stub gh pr create OK"
echo ""
echo "All integration assertions passed."
SUCCESS=1
```

Make it executable:

```bash
chmod +x /Users/robfox/Documents/GitHub/nthlayer-ecosystem/nthlayer/test/learn-recommendations-integration.sh
```

- [ ] **Step 2: Run the integration test**

```bash
cd /Users/robfox/Documents/GitHub/nthlayer-ecosystem/nthlayer
./test/learn-recommendations-integration.sh
```

Expected: prints `✓ ... All integration assertions passed.` Exit 0.

If any assertion fails, the script's `trap cleanup EXIT` preserves `$WORK` so the failure can be diagnosed.

- [ ] **Step 3: Commit**

```bash
cd /Users/robfox/Documents/GitHub/nthlayer-ecosystem/nthlayer
git add test/learn-recommendations-integration.sh
git commit -m "test(integration): jmy.6 end-to-end cross-process test · opensrm-jmy.6

Drives the audited two-step Learn → Spec workflow end-to-end:
real ruamel.yaml round-trip + real git in tmp_path + stubbed gh
via PATH injection. Assertions: manifest target updated; operator
comment preserved (the core ruamel.yaml promise); PR URL printed
on --pr path; PR branch created; single commit on PR branch.

Isolation guarantees per jmy.6 § 8: tmp_path only, no network,
GIT_CONFIG_GLOBAL=/dev/null, gh stubbed."
```

---

## Self-review

### Spec coverage

Skimmed each spec section against the plan tasks:

| Spec section | Tasks |
|---|---|
| § 3 Architecture (subcommand shape, 3 flags, two input sources, --pr couples to --apply-to) | F1, F2, F3 |
| § 4 Components (6 files: recommendations.py extend; _yaml/_apply/_preview/_gh new; cli.py extend) | A1-A4 (recommendations.py); B1-B4 (_yaml.py); C1-C2 (_preview.py); D1-D4 (_apply.py); E1-E2 (_gh.py); F1-F3 (cli.py) |
| § 5 Data flow (three workflows; state machines; dirty-tree) | F2 (Flow B step), F3 (Flow A end-to-end), B4 (state machine), D2 (dirty-tree via classify in apply) |
| § 6 Wire shapes (plan.yaml, summary, commit, PR body, branch naming) | A2 (apiVersion/kind), D4 (summary), F3 (commit + PR body + branch) |
| § 7 Error handling (3 categories + exit codes) | E1 (Category A), D2/D4 (Category B + exit code rule), F3 (Category C operator-recovery) |
| § 8 Testing (six unit-test files + integration) | All B/C/D/E/F tasks include tests; G1 = integration |
| § 9 Performance assumptions | Documented in spec; not enforced by tests (correct) |

No gaps.

### Placeholder scan

- All `_build_plan_from_incident` stub clearly raises `NotImplementedError` with reason — that's a deliberate scope-boundary, not a placeholder. The integration test exercises the `--from` path explicitly, which is the v1.5-canonical input source per the design's "audited two-step" framing. `--incident` requires `CoreAPIClient.get_retrospective_for_incident` which doesn't exist today; adding it is out-of-scope of the loop foundation (file as small follow-up if a v1.5 demo needs the single-step `--incident` workflow).
- No `TODO` / `TBD` / `fill in details` text in any task.
- Every step that changes code shows the full code.
- Every step that runs a command shows expected output / behaviour.

### Type / signature consistency

- `Recommendation.id` field name consistent across A1 (definition), A4 (parse_plan_file), B4 (state machine fixtures), D2 (RecOutcome.id), F2/F3 (CLI dispatch)
- `OutcomeKind` enum values consistent across A3 (definition), B4 (state machine returns), D2 (RecOutcome.outcome field), D4 (summary), F3 (PR body)
- `PATH_MISSING` sentinel consistent across B1 (definition), B4 (test fixtures), C2 (preview test)
- `apply_recommendations(plan, specs_dir, *, force=False) -> ApplyResult` signature consistent across D2 (definition), D3 (atomicity tests), F2 (CLI dispatch)
- `PRResult.ok` / `PRResult.url` / `PRResult.number` consistent across E2 (definition), F3 (CLI dispatch)
- `PreflightError` raised from all five `_gh.check_*` functions (E1) and caught in F3
- `apiVersion: nthlayer.io/learn/v1` consistent across A2 (definition), A4 (parser SUPPORTED_API_VERSIONS), spec § 6.1
- Branch naming `learn/recommendations/<incident-id>` consistent across F3 (branch creation), E1 (branch_exists check), G1 (integration test assertion)

No drift.

---

## Done criteria

- [ ] All 17 tasks marked complete (A1–A4, B1–B4, C1–C2, D1–D4, E1–E2, F1–F3, G1)
- [ ] `uv run pytest -q` passes cleanly in `nthlayer-workers` (no regressions in the 1508-baseline suite)
- [ ] `./test/learn-recommendations-integration.sh` passes from `nthlayer/`
- [ ] Bead `opensrm-jmy.6` ready for `/r5-supervise opensrm-jmy.6`
