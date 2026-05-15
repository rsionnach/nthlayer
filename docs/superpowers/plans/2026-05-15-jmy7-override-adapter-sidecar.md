# Override Adapter Sidecar Implementation Plan (opensrm-jmy.7)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build `nthlayer-override-adapter`, a standalone HTTP sidecar that accepts override events via canonical JSON, batch JSON, or generic webhook payloads and emits them as unparented `gen_ai.override` OTel spans.

**Architecture:** New top-level sibling repo at `nthlayer-ecosystem/nthlayer-override-adapter/`. Starlette + uvicorn, matching nthlayer-core / nthlayer-workers/respond. Reuses `nthlayer-common` overrides foundation (jmy.4 + jmy.11) — `OverrideEvent`, `OverridePrivacyConfig`, `map_webhook_to_override`, `hash_reviewer`. Privacy hashing applied at emission boundary, before OTel attributes are set. Test strategy: Starlette `TestClient` + `InMemorySpanExporter` + cardinality-match invariant.

**Tech Stack:** Python 3.11+, Starlette 0.40+, uvicorn 0.30+, opentelemetry-sdk 1.28+, pyyaml 6.0+, structlog 24.1+. Dev: pytest 8.2+, pytest-asyncio 0.23+, httpx 0.27+, ruff 0.8+.

**Spec source:** `nthlayer/docs/superpowers/specs/2026-05-15-jmy7-override-adapter-sidecar-design.md`.

**Follow-up beads filed:** `opensrm-jmy.17` (Slack adapter, Wave B), `opensrm-jmy.18` (OTel consumer in workers/measure for verdict-binding).

**Repo root for all relative paths below:** `nthlayer-ecosystem/nthlayer-override-adapter/`. Paths outside the repo (e.g., ecosystem-root `pyproject.toml`) are called out explicitly.

---

## File map

```
nthlayer-override-adapter/                          (NEW — git init)
  pyproject.toml                                    (Task 0)
  uv.lock                                           (Task 0 — generated)
  .gitignore                                        (Task 0)
  README.md                                         (Task 11)
  CLAUDE.md                                         (Task 11)
  Dockerfile                                        (Task 12)
  release-please-config.json                        (Task 12)
  .release-please-manifest.json                     (Task 12)
  .github/
    dependabot.yml                                  (Task 12)
    workflows/
      test.yml                                      (Task 12)
      release.yml                                   (Task 12)
      dependabot-automerge.yml                      (Task 12)
  src/nthlayer_override_adapter/
    __init__.py                                     (Task 0)
    metrics.py                                      (Task 2)
    response.py                                     (Task 3)
    emission.py                                     (Task 4)
    config.py                                       (Task 1)
    routes/
      __init__.py                                   (Task 5)
      canonical.py                                  (Task 5 / Task 6)
      webhook.py                                    (Task 7)
    app.py                                          (Task 8)
    cli.py                                          (Task 9)
  tests/
    __init__.py                                     (Task 0)
    conftest.py                                     (Task 4)
    test_config.py                                  (Task 1)
    test_metrics.py                                 (Task 2)
    test_response.py                                (Task 3)
    test_emission.py                                (Task 4)
    test_routes_canonical_single.py                 (Task 5)
    test_routes_canonical_batch.py                  (Task 6)
    test_routes_webhook.py                          (Task 7)
    test_app.py                                     (Task 8)
    test_cli.py                                     (Task 9)
    fixtures/
      adapter_config_minimal.yaml                   (Task 1)
      adapter_config_jira.yaml                      (Task 1)
    smoke/
      __init__.py                                   (Task 10)
      test_imports.py                               (Task 10)
      test_cli.py                                   (Task 10)
```

External edit (ecosystem-root, local-only, NOT committed anywhere):
- `nthlayer-ecosystem/pyproject.toml` — add `nthlayer-override-adapter` to the workspace members. Done once in Task 0.

---

## Task 0: Bootstrap repo skeleton

**Files:**
- Create: `nthlayer-override-adapter/.gitignore`
- Create: `nthlayer-override-adapter/pyproject.toml`
- Create: `nthlayer-override-adapter/src/nthlayer_override_adapter/__init__.py`
- Create: `nthlayer-override-adapter/tests/__init__.py`
- Modify (local-only): `nthlayer-ecosystem/pyproject.toml`

- [ ] **Step 1: Create the repo directory, initialise git, set initial branch to `main`**

```bash
cd /Users/robfox/Documents/GitHub/nthlayer-ecosystem
mkdir -p nthlayer-override-adapter/src/nthlayer_override_adapter/routes
mkdir -p nthlayer-override-adapter/tests/fixtures
mkdir -p nthlayer-override-adapter/tests/smoke
mkdir -p nthlayer-override-adapter/.github/workflows
cd nthlayer-override-adapter
git init -b main
```

Expected: `Initialized empty Git repository in ...nthlayer-override-adapter/.git/`.

- [ ] **Step 2: Write `.gitignore`**

```gitignore
__pycache__/
*.py[cod]
*.egg-info/
.venv/
.pytest_cache/
.ruff_cache/
dist/
build/
.mypy_cache/
.coverage
```

- [ ] **Step 3: Write `pyproject.toml`**

```toml
[build-system]
requires = ["setuptools>=61"]
build-backend = "setuptools.build_meta"

[project]
name = "nthlayer-override-adapter"
version = "0.1.0"
description = "NthLayer override-event sidecar — HTTP → gen_ai.override OTel span bridge"
readme = "README.md"
requires-python = ">=3.11"
dependencies = [
    "nthlayer-common>=1.5.0,<2.0.0",
    "starlette>=0.40",
    "uvicorn>=0.30",
    "opentelemetry-api>=1.28",
    "opentelemetry-sdk>=1.28",
    "opentelemetry-exporter-otlp>=1.28",
    "pyyaml>=6.0",
    "structlog>=24.1.0",
    "prometheus-client>=0.21",
]

[project.scripts]
nthlayer-override-adapter = "nthlayer_override_adapter.cli:main"

[project.optional-dependencies]
dev = [
    "pytest>=8.2",
    "pytest-asyncio>=0.23",
    "httpx>=0.27",
    "ruff>=0.8",
]

[tool.uv.sources]
nthlayer-common = { path = "../nthlayer-common", editable = true }

[tool.setuptools.packages.find]
where = ["src"]

[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]

[tool.ruff]
line-length = 100
target-version = "py311"

[tool.ruff.lint]
select = ["E", "F", "I", "W", "UP", "B"]
```

- [ ] **Step 4: Create package and test `__init__.py` stubs**

`src/nthlayer_override_adapter/__init__.py`:
```python
"""Override-event sidecar — HTTP → gen_ai.override OTel span bridge."""

__version__ = "0.1.0"
```

`src/nthlayer_override_adapter/routes/__init__.py`:
```python
```

`tests/__init__.py`:
```python
```

- [ ] **Step 5: Add the new repo to the ecosystem-root workspace (local-only)**

Modify `/Users/robfox/Documents/GitHub/nthlayer-ecosystem/pyproject.toml` — add `nthlayer-override-adapter` to the workspace members list. Read the file first to find the exact members array, then add the new entry alphabetically.

This file is local-only (never committed); the edit is just so `uv sync` from the ecosystem root installs the new package editable alongside the other members.

- [ ] **Step 6: Run `uv sync` from the new repo to verify it resolves**

```bash
cd /Users/robfox/Documents/GitHub/nthlayer-ecosystem/nthlayer-override-adapter
uv sync --extra dev
```

Expected: `Resolved N packages`, `Installed N packages`, no errors. `uv.lock` is created.

- [ ] **Step 7: Initial commit**

```bash
git add .gitignore pyproject.toml uv.lock src/nthlayer_override_adapter/__init__.py src/nthlayer_override_adapter/routes/__init__.py tests/__init__.py
git commit -m "chore: bootstrap nthlayer-override-adapter package skeleton

Initial pyproject.toml, package layout, dev-dep lockfile. No HTTP
routes or OTel emission yet — those land in subsequent tasks.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 1: Config dataclasses + YAML loader

**Files:**
- Create: `src/nthlayer_override_adapter/config.py`
- Create: `tests/test_config.py`
- Create: `tests/fixtures/adapter_config_minimal.yaml`
- Create: `tests/fixtures/adapter_config_jira.yaml`

- [ ] **Step 1: Write the failing tests**

`tests/fixtures/adapter_config_minimal.yaml`:
```yaml
adapters: []
privacy:
  plaintext_reviewer: false
  exclude_reason: false
otel:
  exporter: otlp
  endpoint: "http://localhost:4317"
```

`tests/fixtures/adapter_config_jira.yaml`:
```yaml
adapters:
  - source: jira
    webhook_path: /webhook/jira
    field_mapping:
      decision_id: "issue.customfield_10042"
      corrected_action: "issue.resolution.name"
      reviewer: "issue.assignee.emailAddress"
      timestamp: "issue.updated"
      reason: "issue.resolution.description"
    defaults:
      source_system: jira
      service: fraud-detect

privacy:
  plaintext_reviewer: false
  exclude_reason: false

otel:
  exporter: otlp
  endpoint: "http://localhost:4317"
```

`tests/test_config.py`:
```python
from pathlib import Path

import pytest

from nthlayer_common.overrides import OverridePrivacyConfig
from nthlayer_override_adapter.config import (
    AdapterConfig,
    ConfigError,
    WebhookAdapter,
    load_config,
)

FIXTURES = Path(__file__).parent / "fixtures"


class TestLoadMinimal:
    def test_empty_adapters_is_legal(self) -> None:
        cfg = load_config(FIXTURES / "adapter_config_minimal.yaml")
        assert cfg.adapters == []

    def test_defaults_when_privacy_absent(self, tmp_path: Path) -> None:
        target = tmp_path / "cfg.yaml"
        target.write_text("adapters: []\n")
        cfg = load_config(target)
        assert cfg.privacy.plaintext_reviewer is False
        assert cfg.privacy.exclude_reason is False

    def test_otel_endpoint_optional(self, tmp_path: Path) -> None:
        target = tmp_path / "cfg.yaml"
        target.write_text("adapters: []\n")
        cfg = load_config(target)
        assert cfg.otel_endpoint is None


class TestLoadJira:
    def test_full_jira_adapter_parses(self) -> None:
        cfg = load_config(FIXTURES / "adapter_config_jira.yaml")
        assert len(cfg.adapters) == 1
        jira = cfg.adapters[0]
        assert jira.source == "jira"
        assert jira.webhook_path == "/webhook/jira"
        assert jira.field_mapping["reviewer"] == "issue.assignee.emailAddress"
        assert jira.defaults["source_system"] == "jira"

    def test_privacy_round_trips(self) -> None:
        cfg = load_config(FIXTURES / "adapter_config_jira.yaml")
        assert isinstance(cfg.privacy, OverridePrivacyConfig)
        assert cfg.privacy.plaintext_reviewer is False

    def test_otel_endpoint_round_trips(self) -> None:
        cfg = load_config(FIXTURES / "adapter_config_jira.yaml")
        assert cfg.otel_endpoint == "http://localhost:4317"


class TestValidation:
    def test_missing_source_raises(self, tmp_path: Path) -> None:
        target = tmp_path / "bad.yaml"
        target.write_text(
            "adapters:\n"
            "  - webhook_path: /x\n"
            "    field_mapping: {decision_id: a, corrected_action: b, reviewer: c}\n"
        )
        with pytest.raises(ConfigError, match="source"):
            load_config(target)

    def test_missing_webhook_path_raises(self, tmp_path: Path) -> None:
        target = tmp_path / "bad.yaml"
        target.write_text(
            "adapters:\n"
            "  - source: x\n"
            "    field_mapping: {decision_id: a, corrected_action: b, reviewer: c}\n"
        )
        with pytest.raises(ConfigError, match="webhook_path"):
            load_config(target)

    def test_duplicate_webhook_paths_raise(self, tmp_path: Path) -> None:
        target = tmp_path / "bad.yaml"
        target.write_text(
            "adapters:\n"
            "  - source: a\n"
            "    webhook_path: /webhook/x\n"
            "    field_mapping: {decision_id: i, corrected_action: c, reviewer: r}\n"
            "  - source: b\n"
            "    webhook_path: /webhook/x\n"
            "    field_mapping: {decision_id: i, corrected_action: c, reviewer: r}\n"
        )
        with pytest.raises(ConfigError, match="duplicate webhook_path"):
            load_config(target)

    def test_missing_file_raises(self, tmp_path: Path) -> None:
        with pytest.raises(ConfigError, match="not found"):
            load_config(tmp_path / "absent.yaml")
```

- [ ] **Step 2: Run tests, confirm they fail**

```bash
uv run pytest tests/test_config.py -v
```

Expected: `ModuleNotFoundError: No module named 'nthlayer_override_adapter.config'`.

- [ ] **Step 3: Implement `config.py`**

`src/nthlayer_override_adapter/config.py`:
```python
"""Adapter configuration — YAML-shaped, dataclass-backed.

Loaded once at process start by ``cli.py``. Hot-reload is intentionally
out of scope for v1.5 (see design doc § 10).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from nthlayer_common.overrides import OverridePrivacyConfig


class ConfigError(ValueError):
    """Adapter configuration is malformed or unreadable."""


@dataclass(frozen=True)
class WebhookAdapter:
    """One configured webhook source — registered as ``POST {webhook_path}``."""

    source: str
    webhook_path: str
    field_mapping: dict[str, str]
    defaults: dict[str, Any] = field(default_factory=dict)


@dataclass
class AdapterConfig:
    """Top-level adapter config — adapters, privacy posture, OTel target."""

    adapters: list[WebhookAdapter]
    privacy: OverridePrivacyConfig
    otel_endpoint: str | None = None


def load_config(path: str | Path) -> AdapterConfig:
    """Parse a YAML config file into an ``AdapterConfig``.

    Raises ``ConfigError`` on any structural problem — missing required
    fields, duplicate webhook_paths, file-not-found. Empty ``adapters``
    is legal (canonical endpoints still register).
    """
    cfg_path = Path(path)
    if not cfg_path.is_file():
        raise ConfigError(f"config file not found: {cfg_path}")

    try:
        raw = yaml.safe_load(cfg_path.read_text()) or {}
    except yaml.YAMLError as exc:
        raise ConfigError(f"YAML parse error in {cfg_path}: {exc}") from exc

    if not isinstance(raw, dict):
        raise ConfigError(f"top-level config must be a mapping, got {type(raw).__name__}")

    adapters = _parse_adapters(raw.get("adapters") or [])
    privacy = _parse_privacy(raw.get("privacy") or {})
    otel_endpoint = (raw.get("otel") or {}).get("endpoint")

    return AdapterConfig(adapters=adapters, privacy=privacy, otel_endpoint=otel_endpoint)


def _parse_adapters(raw_adapters: list[Any]) -> list[WebhookAdapter]:
    seen_paths: set[str] = set()
    adapters: list[WebhookAdapter] = []
    for idx, entry in enumerate(raw_adapters):
        if not isinstance(entry, dict):
            raise ConfigError(f"adapter[{idx}] must be a mapping, got {type(entry).__name__}")
        for required in ("source", "webhook_path", "field_mapping"):
            if required not in entry:
                raise ConfigError(f"adapter[{idx}] missing required field '{required}'")
        path = entry["webhook_path"]
        if path in seen_paths:
            raise ConfigError(f"adapter[{idx}] duplicate webhook_path: {path}")
        seen_paths.add(path)
        adapters.append(
            WebhookAdapter(
                source=entry["source"],
                webhook_path=path,
                field_mapping=dict(entry["field_mapping"]),
                defaults=dict(entry.get("defaults") or {}),
            )
        )
    return adapters


def _parse_privacy(raw_privacy: dict[str, Any]) -> OverridePrivacyConfig:
    return OverridePrivacyConfig(
        plaintext_reviewer=bool(raw_privacy.get("plaintext_reviewer", False)),
        exclude_reason=bool(raw_privacy.get("exclude_reason", False)),
    )
```

- [ ] **Step 4: Run tests, confirm they pass**

```bash
uv run pytest tests/test_config.py -v
uv run ruff check src/ tests/
```

Expected: 9 passed, 0 failed; ruff clean.

- [ ] **Step 5: Commit**

```bash
git add src/nthlayer_override_adapter/config.py tests/test_config.py tests/fixtures/
git commit -m "feat: add adapter config dataclasses + YAML loader

AdapterConfig + WebhookAdapter dataclasses. load_config() parses
override-adapter-config.yaml; raises ConfigError on missing fields,
duplicate webhook_paths, or file-not-found. Privacy posture maps to
nthlayer-common's OverridePrivacyConfig.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 2: Self-observability metrics module

**Files:**
- Create: `src/nthlayer_override_adapter/metrics.py`
- Create: `tests/test_metrics.py`

- [ ] **Step 1: Write the failing tests**

`tests/test_metrics.py`:
```python
from nthlayer_override_adapter.metrics import (
    collector_errors_total,
    emission_total,
    emit_duration_seconds,
    requests_total,
    validation_errors_total,
)


class TestCounters:
    def test_requests_total_has_endpoint_and_status_labels(self) -> None:
        sample = requests_total.labels(endpoint="canonical", status="accepted")
        sample.inc()  # smoke — exercising the label tuple

    def test_emission_total_has_result_label(self) -> None:
        emission_total.labels(result="emitted").inc()

    def test_validation_errors_has_reason_label(self) -> None:
        validation_errors_total.labels(reason="missing_field").inc()

    def test_collector_errors_unlabelled(self) -> None:
        collector_errors_total.inc()

    def test_emit_duration_is_histogram(self) -> None:
        emit_duration_seconds.observe(0.001)
```

- [ ] **Step 2: Run tests, confirm they fail**

```bash
uv run pytest tests/test_metrics.py -v
```

Expected: `ModuleNotFoundError`.

- [ ] **Step 3: Implement `metrics.py`**

`src/nthlayer_override_adapter/metrics.py`:
```python
"""Prometheus self-observability metrics for the override-adapter sidecar.

Mirrors ``nthlayer_common.metrics`` conventions: stable label sets, low
cardinality, scrape-friendly names. Exposed via ``GET /metrics`` in the
Starlette app.
"""
from __future__ import annotations

from prometheus_client import Counter, Histogram

requests_total = Counter(
    "override_requests_total",
    "Override HTTP requests received, by endpoint and outcome.",
    ["endpoint", "status"],
)

emission_total = Counter(
    "override_emission_total",
    "Override events emitted to OTel collector.",
    ["result"],
)

validation_errors_total = Counter(
    "override_validation_errors_total",
    "Input validation failures, by canonical reason.",
    ["reason"],
)

collector_errors_total = Counter(
    "override_collector_errors_total",
    "OTel exporter failures observed by the adapter.",
)

emit_duration_seconds = Histogram(
    "override_emit_duration_seconds",
    "Time from HTTP receipt to OTel span emitted, seconds.",
    buckets=(0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0),
)
```

- [ ] **Step 4: Run tests, confirm they pass**

```bash
uv run pytest tests/test_metrics.py -v
uv run ruff check src/ tests/
```

Expected: 5 passed; ruff clean.

- [ ] **Step 5: Commit**

```bash
git add src/nthlayer_override_adapter/metrics.py tests/test_metrics.py
git commit -m "feat: add adapter Prometheus self-observability counters

requests_total / emission_total / validation_errors_total /
collector_errors_total counters + emit_duration_seconds histogram.
Exposed via /metrics in the Starlette app (later task).

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 3: Response shape helpers

**Files:**
- Create: `src/nthlayer_override_adapter/response.py`
- Create: `tests/test_response.py`

- [ ] **Step 1: Write the failing tests**

`tests/test_response.py`:
```python
from nthlayer_override_adapter.response import (
    BatchResult,
    accepted_single,
    build_batch_response,
)


class TestSingleResponse:
    def test_accepted_single_shape(self) -> None:
        body = accepted_single("dec_001")
        assert body == {"decision_id": "dec_001", "emitted_to_otel": True}


class TestBatchResponse:
    def test_all_accepted_no_duplicates(self) -> None:
        result = BatchResult(
            accepted=["dec_001", "dec_002"],
            rejected=[],
            duplicates=[],
            errors=[],
        )
        body = build_batch_response(result)
        assert body == {
            "accepted": ["dec_001", "dec_002"],
            "rejected": [],
            "duplicates": [],
            "errors": [],
        }

    def test_rejected_entries_carry_index_and_reason(self) -> None:
        result = BatchResult(
            accepted=[],
            rejected=[{"index": 3, "reason": "missing field 'reviewer'"}],
            duplicates=[],
            errors=[],
        )
        body = build_batch_response(result)
        assert body["rejected"] == [{"index": 3, "reason": "missing field 'reviewer'"}]

    def test_duplicates_carry_decision_id_and_indices(self) -> None:
        result = BatchResult(
            accepted=["dec_002"],
            rejected=[],
            duplicates=[
                {"decision_id": "dec_002", "applied_at_index": 5, "discarded_indices": [1, 3]}
            ],
            errors=[],
        )
        body = build_batch_response(result)
        dup = body["duplicates"][0]
        assert dup["decision_id"] == "dec_002"
        assert dup["applied_at_index"] == 5
        assert dup["discarded_indices"] == [1, 3]
```

- [ ] **Step 2: Run tests, confirm they fail**

```bash
uv run pytest tests/test_response.py -v
```

Expected: `ModuleNotFoundError`.

- [ ] **Step 3: Implement `response.py`**

`src/nthlayer_override_adapter/response.py`:
```python
"""Response body shapes for the override-adapter HTTP endpoints.

Plain dicts on the wire. Dataclasses internally so the batch builder
can carry typed state through the route handler without touching JSON
until the final return.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class BatchResult:
    """Per-batch accumulator threaded through the batch route handler."""

    accepted: list[str] = field(default_factory=list)
    rejected: list[dict[str, Any]] = field(default_factory=list)
    duplicates: list[dict[str, Any]] = field(default_factory=list)
    errors: list[dict[str, Any]] = field(default_factory=list)


def accepted_single(decision_id: str) -> dict[str, Any]:
    """Body for a successful single-override POST."""
    return {"decision_id": decision_id, "emitted_to_otel": True}


def build_batch_response(result: BatchResult) -> dict[str, Any]:
    """Final JSON body for a batch POST. Always populated keys."""
    return {
        "accepted": list(result.accepted),
        "rejected": list(result.rejected),
        "duplicates": list(result.duplicates),
        "errors": list(result.errors),
    }
```

- [ ] **Step 4: Run tests, confirm they pass**

```bash
uv run pytest tests/test_response.py -v
uv run ruff check src/ tests/
```

Expected: 3 passed; ruff clean.

- [ ] **Step 5: Commit**

```bash
git add src/nthlayer_override_adapter/response.py tests/test_response.py
git commit -m "feat: add response shape helpers (single + batch)

BatchResult dataclass accumulates per-batch state; build_batch_response
emits the spec-§4 shape with decision_ids in accepted/duplicates (not
just counts) so callers can reconcile their submission with emitted
state. accepted_single is the single-POST 201 body.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 4: Emission module (unparented span + privacy)

**Files:**
- Create: `src/nthlayer_override_adapter/emission.py`
- Create: `tests/conftest.py`
- Create: `tests/test_emission.py`

- [ ] **Step 1: Write the shared OTel test fixture**

`tests/conftest.py`:
```python
from collections.abc import Iterator

import pytest
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import (
    InMemorySpanExporter,
)


@pytest.fixture
def span_exporter() -> Iterator[InMemorySpanExporter]:
    """In-memory exporter wired to a fresh TracerProvider for each test.

    Ensures each test sees only its own spans regardless of OTel global
    state from other tests.
    """
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    trace.set_tracer_provider(provider)
    try:
        yield exporter
    finally:
        exporter.clear()
```

- [ ] **Step 2: Write the failing emission tests**

`tests/test_emission.py`:
```python
from datetime import datetime, timezone

from nthlayer_common.overrides import (
    OverrideEvent,
    OverridePrivacyConfig,
    hash_reviewer,
)
from nthlayer_override_adapter.emission import emit_override


def _make_event(**overrides: object) -> OverrideEvent:
    base = {
        "decision_id": "vrd-001",
        "service": "fraud-detect",
        "corrected_action": "escalate",
        "reviewer": "analyst-047",
        "reason": "model regression",
        "confidence_at_decision": 0.71,
        "source_system": "internal-ui",
        "timestamp": datetime(2026, 5, 15, 12, 0, tzinfo=timezone.utc),
    }
    base.update(overrides)
    return OverrideEvent(**base)


class TestEmissionShape:
    def test_emits_one_span_named_gen_ai_override(self, span_exporter) -> None:
        emit_override(_make_event(), OverridePrivacyConfig())
        spans = span_exporter.get_finished_spans()
        assert len(spans) == 1
        assert spans[0].name == "gen_ai.override"

    def test_span_carries_required_attributes(self, span_exporter) -> None:
        emit_override(_make_event(), OverridePrivacyConfig())
        attrs = span_exporter.get_finished_spans()[0].attributes
        assert attrs["gen_ai.override.decision_id"] == "vrd-001"
        assert attrs["gen_ai.override.service"] == "fraud-detect"
        assert attrs["gen_ai.override.corrected_action"] == "escalate"

    def test_span_is_unparented(self, span_exporter) -> None:
        emit_override(_make_event(), OverridePrivacyConfig())
        span = span_exporter.get_finished_spans()[0]
        assert span.parent is None


class TestPrivacy:
    def test_reviewer_hashed_by_default(self, span_exporter) -> None:
        emit_override(_make_event(reviewer="analyst-047"), OverridePrivacyConfig())
        attrs = span_exporter.get_finished_spans()[0].attributes
        assert attrs["gen_ai.override.reviewer"] == hash_reviewer("analyst-047")

    def test_reviewer_plaintext_when_opted_in(self, span_exporter) -> None:
        privacy = OverridePrivacyConfig(plaintext_reviewer=True)
        emit_override(_make_event(reviewer="analyst-047"), privacy)
        attrs = span_exporter.get_finished_spans()[0].attributes
        assert attrs["gen_ai.override.reviewer"] == "analyst-047"

    def test_reason_dropped_when_excluded(self, span_exporter) -> None:
        privacy = OverridePrivacyConfig(exclude_reason=True)
        emit_override(_make_event(reason="sensitive"), privacy)
        attrs = span_exporter.get_finished_spans()[0].attributes
        assert "gen_ai.override.reason" not in attrs


class TestOptionalFields:
    def test_none_fields_dropped(self, span_exporter) -> None:
        emit_override(
            _make_event(reason=None, original_action=None, source_system=None),
            OverridePrivacyConfig(),
        )
        attrs = span_exporter.get_finished_spans()[0].attributes
        assert "gen_ai.override.reason" not in attrs
        assert "gen_ai.override.original_action" not in attrs
        assert "gen_ai.override.source_system" not in attrs
```

- [ ] **Step 3: Run tests, confirm they fail**

```bash
uv run pytest tests/test_emission.py -v
```

Expected: `ModuleNotFoundError: No module named 'nthlayer_override_adapter.emission'`.

- [ ] **Step 4: Implement `emission.py`**

`src/nthlayer_override_adapter/emission.py`:
```python
"""OTel emission for override events — unparented gen_ai.override spans.

Privacy is applied here, at the emission boundary, not at the consumer
side: once the payload reaches the OTel pipeline it's observable
downstream, so reviewer hashing must happen before ``to_otel_attributes``.

Rationale for unparented spans: overrides are operator decisions not
bound to any service trace. Treating each as a standalone span
preserves the semantic that 'an override is its own thing'; collectors
route span → metric via spanmetricsconnector following standard OTel
patterns. Do not "fix" this to inherit a trace context.
"""
from __future__ import annotations

import time

import structlog
from opentelemetry import context as otel_context
from opentelemetry import trace

from nthlayer_common.overrides import (
    OverrideEvent,
    OverridePrivacyConfig,
    hash_reviewer,
)

from nthlayer_override_adapter.metrics import (
    collector_errors_total,
    emission_total,
    emit_duration_seconds,
)

logger = structlog.get_logger(__name__)

_SPAN_NAME = "gen_ai.override"
_TRACER_NAME = "nthlayer-override-adapter"


def emit_override(event: OverrideEvent, privacy: OverridePrivacyConfig) -> None:
    """Emit one unparented ``gen_ai.override`` span for this override.

    Privacy is applied to a shallow copy of the event so the caller's
    instance is not mutated. Exporter failures are logged + counted but
    do not raise — fail-open posture matches the rest of the ecosystem
    (caller still treats the HTTP request as accepted).
    """
    started = time.perf_counter()
    masked = _apply_privacy(event, privacy)
    tracer = trace.get_tracer(_TRACER_NAME)
    empty = otel_context.Context()
    try:
        with tracer.start_as_current_span(_SPAN_NAME, context=empty) as span:
            for key, value in masked.to_otel_attributes().items():
                span.set_attribute(key, value)
        emission_total.labels(result="emitted").inc()
    except Exception as exc:  # noqa: BLE001 — fail-open is intentional
        emission_total.labels(result="failed").inc()
        collector_errors_total.inc()
        logger.warning(
            "override_emission_failed",
            decision_id=event.decision_id,
            error=str(exc),
        )
    finally:
        emit_duration_seconds.observe(time.perf_counter() - started)


def _apply_privacy(
    event: OverrideEvent, privacy: OverridePrivacyConfig,
) -> OverrideEvent:
    reviewer = (
        event.reviewer
        if privacy.plaintext_reviewer
        else hash_reviewer(event.reviewer)
    )
    reason = None if privacy.exclude_reason else event.reason
    return OverrideEvent(
        decision_id=event.decision_id,
        service=event.service,
        corrected_action=event.corrected_action,
        reviewer=reviewer,
        original_action=event.original_action,
        reason=reason,
        confidence_at_decision=event.confidence_at_decision,
        source_system=event.source_system,
        timestamp=event.timestamp,
    )
```

- [ ] **Step 5: Run tests, confirm they pass**

```bash
uv run pytest tests/test_emission.py -v
uv run ruff check src/ tests/
```

Expected: 7 passed; ruff clean.

- [ ] **Step 6: Commit**

```bash
git add src/nthlayer_override_adapter/emission.py tests/conftest.py tests/test_emission.py
git commit -m "feat: emit unparented gen_ai.override OTel spans with privacy applied

emit_override(event, privacy) opens one unparented span per override,
sets gen_ai.override.* attributes from OverrideEvent.to_otel_attributes
on a shallow copy with hashed reviewer (default) / dropped reason (when
exclude_reason). Fail-open on exporter errors — logged + counted, never
raises. Test fixture wires a fresh InMemorySpanExporter per test.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 5: Canonical single-override endpoint

**Files:**
- Create: `src/nthlayer_override_adapter/routes/canonical.py`
- Create: `tests/test_routes_canonical_single.py`

- [ ] **Step 1: Write the failing tests**

`tests/test_routes_canonical_single.py`:
```python
import pytest
from starlette.applications import Starlette
from starlette.testclient import TestClient

from nthlayer_common.overrides import OverridePrivacyConfig
from nthlayer_override_adapter.routes.canonical import register_canonical_routes


@pytest.fixture
def client(span_exporter) -> TestClient:
    app = Starlette()
    register_canonical_routes(app, privacy=OverridePrivacyConfig())
    return TestClient(app)


def _valid_body(**overrides: object) -> dict[str, object]:
    base = {
        "decision_id": "vrd-001",
        "service": "fraud-detect",
        "corrected_action": "escalate",
        "reviewer": "analyst-047",
        "reason": "model regression",
        "confidence_at_decision": 0.71,
        "timestamp": "2026-05-15T12:00:00Z",
        "source_system": "internal-ui",
    }
    base.update(overrides)
    return base


class TestSingleOverride:
    def test_happy_path_201(self, client, span_exporter) -> None:
        resp = client.post("/api/v1/overrides", json=_valid_body())
        assert resp.status_code == 201
        assert resp.json() == {"decision_id": "vrd-001", "emitted_to_otel": True}
        assert len(span_exporter.get_finished_spans()) == 1

    def test_cardinality_one_response_one_span(self, client, span_exporter) -> None:
        client.post("/api/v1/overrides", json=_valid_body(decision_id="dec-a"))
        client.post("/api/v1/overrides", json=_valid_body(decision_id="dec-b"))
        assert len(span_exporter.get_finished_spans()) == 2

    def test_missing_required_field_400(self, client) -> None:
        body = _valid_body()
        del body["reviewer"]
        resp = client.post("/api/v1/overrides", json=body)
        assert resp.status_code == 400
        assert "reviewer" in resp.json()["detail"]

    def test_invalid_confidence_400(self, client) -> None:
        resp = client.post(
            "/api/v1/overrides", json=_valid_body(confidence_at_decision=1.5),
        )
        assert resp.status_code == 400
        assert "confidence" in resp.json()["detail"]

    def test_naive_timestamp_400(self, client) -> None:
        resp = client.post(
            "/api/v1/overrides", json=_valid_body(timestamp="2026-05-15T12:00:00"),
        )
        assert resp.status_code == 400
        assert "tz-aware" in resp.json()["detail"] or "timezone" in resp.json()["detail"]

    def test_malformed_json_400(self, client) -> None:
        resp = client.post(
            "/api/v1/overrides",
            content=b"not json",
            headers={"content-type": "application/json"},
        )
        assert resp.status_code == 400
```

- [ ] **Step 2: Run tests, confirm they fail**

```bash
uv run pytest tests/test_routes_canonical_single.py -v
```

Expected: `ModuleNotFoundError` for `routes.canonical`.

- [ ] **Step 3: Implement `routes/canonical.py` (single endpoint only — batch in Task 6)**

`src/nthlayer_override_adapter/routes/canonical.py`:
```python
"""Canonical POST /api/v1/overrides and /batch route handlers."""
from __future__ import annotations

import json
from datetime import datetime

from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route

from nthlayer_common.overrides import OverrideEvent, OverridePrivacyConfig

from nthlayer_override_adapter.emission import emit_override
from nthlayer_override_adapter.metrics import (
    requests_total,
    validation_errors_total,
)
from nthlayer_override_adapter.response import accepted_single


def register_canonical_routes(
    app: Starlette, *, privacy: OverridePrivacyConfig,
) -> None:
    """Mount /api/v1/overrides on the given Starlette app."""

    async def post_single(request: Request) -> JSONResponse:
        try:
            payload = await request.json()
        except json.JSONDecodeError as exc:
            return _validation_response("malformed_json", str(exc))

        try:
            event = _event_from_payload(payload)
        except ValueError as exc:
            return _validation_response("invalid_body", str(exc))

        emit_override(event, privacy)
        requests_total.labels(endpoint="canonical", status="accepted").inc()
        return JSONResponse(accepted_single(event.decision_id), status_code=201)

    app.routes.append(Route("/api/v1/overrides", post_single, methods=["POST"]))


def _event_from_payload(payload: object) -> OverrideEvent:
    if not isinstance(payload, dict):
        raise ValueError(f"override body must be a JSON object, got {type(payload).__name__}")
    kwargs = dict(payload)
    if "timestamp" in kwargs and isinstance(kwargs["timestamp"], str):
        kwargs["timestamp"] = _parse_iso_timestamp(kwargs["timestamp"])
    return OverrideEvent(**kwargs)


def _parse_iso_timestamp(value: str) -> datetime:
    raw = value[:-1] + "+00:00" if value.endswith("Z") else value
    parsed = datetime.fromisoformat(raw)
    if parsed.tzinfo is None:
        raise ValueError(
            f"timestamp must be tz-aware (got naive: {value!r}); "
            "include a 'Z' or '+HH:MM' offset"
        )
    return parsed


def _validation_response(reason: str, detail: str) -> JSONResponse:
    validation_errors_total.labels(reason=reason).inc()
    requests_total.labels(endpoint="canonical", status="rejected").inc()
    return JSONResponse({"detail": detail}, status_code=400)
```

- [ ] **Step 4: Run tests, confirm they pass**

```bash
uv run pytest tests/test_routes_canonical_single.py -v
uv run ruff check src/ tests/
```

Expected: 6 passed; ruff clean.

- [ ] **Step 5: Commit**

```bash
git add src/nthlayer_override_adapter/routes/canonical.py tests/test_routes_canonical_single.py
git commit -m "feat: canonical POST /api/v1/overrides route

Validates body via OverrideEvent.__post_init__, parses ISO timestamps
(rejects naive), emits exactly one gen_ai.override span per accepted
request, returns 201 with {decision_id, emitted_to_otel: true}.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 6: Canonical batch endpoint (scenarios 3 + 4 + cardinality)

**Files:**
- Modify: `src/nthlayer_override_adapter/routes/canonical.py`
- Create: `tests/test_routes_canonical_batch.py`

- [ ] **Step 1: Write the failing tests**

`tests/test_routes_canonical_batch.py`:
```python
import pytest
from starlette.applications import Starlette
from starlette.testclient import TestClient

from nthlayer_common.overrides import OverridePrivacyConfig
from nthlayer_override_adapter.routes.canonical import register_canonical_routes


@pytest.fixture
def client(span_exporter) -> TestClient:
    app = Starlette()
    register_canonical_routes(app, privacy=OverridePrivacyConfig())
    return TestClient(app)


def _entry(decision_id: str, **overrides: object) -> dict[str, object]:
    base = {
        "decision_id": decision_id,
        "service": "fraud-detect",
        "corrected_action": "escalate",
        "reviewer": "analyst-047",
        "timestamp": "2026-05-15T12:00:00Z",
    }
    base.update(overrides)
    return base


class TestBatchHappyPath:
    def test_scenario_3_one_hundred_overrides_all_accepted(self, client, span_exporter) -> None:
        body = {"overrides": [_entry(f"dec-{i:04d}") for i in range(100)]}
        resp = client.post("/api/v1/overrides/batch", json=body)

        assert resp.status_code == 200
        data = resp.json()
        assert len(data["accepted"]) == 100
        assert data["accepted"][0] == "dec-0000"
        assert data["accepted"][-1] == "dec-0099"
        assert data["rejected"] == []
        assert data["duplicates"] == []
        assert data["errors"] == []
        assert len(span_exporter.get_finished_spans()) == 100


class TestBatchDuplicates:
    def test_scenario_4_last_in_array_wins(self, client, span_exporter) -> None:
        # dec-002 appears at indices 1, 3, and 5 — last wins (idx 5).
        body = {
            "overrides": [
                _entry("dec-001"),                              # 0
                _entry("dec-002", corrected_action="approve"),  # 1 — discarded
                _entry("dec-003"),                              # 2
                _entry("dec-002", corrected_action="reject"),   # 3 — discarded
                _entry("dec-004"),                              # 4
                _entry("dec-002", corrected_action="escalate"), # 5 — applied
            ],
        }
        resp = client.post("/api/v1/overrides/batch", json=body)
        data = resp.json()

        assert set(data["accepted"]) == {"dec-001", "dec-002", "dec-003", "dec-004"}
        assert data["duplicates"] == [
            {"decision_id": "dec-002", "applied_at_index": 5, "discarded_indices": [1, 3]}
        ]
        # Cardinality: 4 unique accepted decision_ids → 4 spans, NOT 6.
        spans = span_exporter.get_finished_spans()
        assert len(spans) == 4
        # The dec-002 span carries the LAST corrected_action ("escalate").
        dec_002 = [s for s in spans if s.attributes["gen_ai.override.decision_id"] == "dec-002"]
        assert len(dec_002) == 1
        assert dec_002[0].attributes["gen_ai.override.corrected_action"] == "escalate"


class TestBatchRejected:
    def test_invalid_entry_recorded_other_entries_accepted(self, client, span_exporter) -> None:
        bad = _entry("dec-002")
        del bad["reviewer"]
        body = {"overrides": [_entry("dec-001"), bad, _entry("dec-003")]}

        resp = client.post("/api/v1/overrides/batch", json=body)
        data = resp.json()

        assert data["accepted"] == ["dec-001", "dec-003"]
        assert data["rejected"] == [{"index": 1, "reason": "OverrideEvent.reviewer is required (spec § 4)"}]
        assert len(span_exporter.get_finished_spans()) == 2


class TestCardinalityInvariant:
    def test_response_counts_match_emission_cardinality(self, client, span_exporter) -> None:
        body = {
            "overrides": [
                _entry("dec-a"),                          # 0 — accepted
                _entry("dec-b"),                          # 1 — accepted
                _entry("dec-a", corrected_action="r2"),   # 2 — dup of 0
                _entry("dec-c"),                          # 3 — accepted
            ],
        }
        resp = client.post("/api/v1/overrides/batch", json=body)
        data = resp.json()

        emitted_ids = {
            s.attributes["gen_ai.override.decision_id"]
            for s in span_exporter.get_finished_spans()
        }

        # Response claims about cardinality:
        assert set(data["accepted"]) == emitted_ids
        assert len(span_exporter.get_finished_spans()) == len(data["accepted"])


class TestBatchMalformed:
    def test_top_level_not_a_dict_400(self, client) -> None:
        resp = client.post("/api/v1/overrides/batch", json=[1, 2, 3])
        assert resp.status_code == 400

    def test_overrides_key_missing_400(self, client) -> None:
        resp = client.post("/api/v1/overrides/batch", json={"foo": []})
        assert resp.status_code == 400
```

- [ ] **Step 2: Run tests, confirm they fail**

```bash
uv run pytest tests/test_routes_canonical_batch.py -v
```

Expected: All fail — batch route not yet wired.

- [ ] **Step 3: Rewrite `routes/canonical.py` to also mount the batch route**

Replace the file in full. The batch route computes winning entries per `decision_id` BEFORE emitting any spans, so the cardinality-match invariant holds (one span per unique accepted decision_id, even when N input entries reference the same id).

`src/nthlayer_override_adapter/routes/canonical.py`:
```python
"""Canonical POST /api/v1/overrides and /api/v1/overrides/batch route handlers."""
from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route

from nthlayer_common.overrides import OverrideEvent, OverridePrivacyConfig

from nthlayer_override_adapter.emission import emit_override
from nthlayer_override_adapter.metrics import (
    requests_total,
    validation_errors_total,
)
from nthlayer_override_adapter.response import (
    BatchResult,
    accepted_single,
    build_batch_response,
)


def register_canonical_routes(
    app: Starlette, *, privacy: OverridePrivacyConfig,
) -> None:
    """Mount /api/v1/overrides and /api/v1/overrides/batch on the app."""

    async def post_single(request: Request) -> JSONResponse:
        try:
            payload = await request.json()
        except json.JSONDecodeError as exc:
            return _validation_response("malformed_json", str(exc))

        try:
            event = _event_from_payload(payload)
        except ValueError as exc:
            return _validation_response("invalid_body", str(exc))

        emit_override(event, privacy)
        requests_total.labels(endpoint="canonical", status="accepted").inc()
        return JSONResponse(accepted_single(event.decision_id), status_code=201)

    async def post_batch(request: Request) -> JSONResponse:
        try:
            payload = await request.json()
        except json.JSONDecodeError as exc:
            return _validation_response("malformed_json", str(exc))

        if not isinstance(payload, dict) or "overrides" not in payload:
            return _validation_response(
                "invalid_body",
                "batch body must be a JSON object with an 'overrides' array",
            )
        entries = payload["overrides"]
        if not isinstance(entries, list):
            return _validation_response(
                "invalid_body", "'overrides' must be an array",
            )

        result = _process_batch(entries, privacy=privacy)
        requests_total.labels(endpoint="batch", status="accepted").inc()
        return JSONResponse(build_batch_response(result), status_code=200)

    app.routes.append(Route("/api/v1/overrides", post_single, methods=["POST"]))
    app.routes.append(
        Route("/api/v1/overrides/batch", post_batch, methods=["POST"]),
    )


def _process_batch(
    entries: list[Any], *, privacy: OverridePrivacyConfig,
) -> BatchResult:
    """Walk entries in array order. Last-in-array wins on duplicate decision_id.

    Two-pass: first resolve the winning entry per decision_id without
    emitting anything, then emit only the winners. This meets the
    cardinality-match invariant (one emitted span per unique accepted
    decision_id), which a one-pass emit-as-you-go approach would violate
    by emitting N spans for N occurrences of the same id.
    """
    result = BatchResult()
    winners: dict[str, tuple[int, OverrideEvent]] = {}
    superseded: dict[str, list[int]] = {}

    for idx, entry in enumerate(entries):
        try:
            event = _event_from_payload(entry)
        except ValueError as exc:
            result.rejected.append({"index": idx, "reason": str(exc)})
            continue

        prev = winners.get(event.decision_id)
        if prev is not None:
            superseded.setdefault(event.decision_id, []).append(prev[0])
        winners[event.decision_id] = (idx, event)

    for decision_id, (winning_idx, event) in winners.items():
        emit_override(event, privacy)
        result.accepted.append(decision_id)
        if decision_id in superseded:
            result.duplicates.append(
                {
                    "decision_id": decision_id,
                    "applied_at_index": winning_idx,
                    "discarded_indices": sorted(superseded[decision_id]),
                }
            )
    return result


def _event_from_payload(payload: object) -> OverrideEvent:
    if not isinstance(payload, dict):
        raise ValueError(f"override body must be a JSON object, got {type(payload).__name__}")
    kwargs = dict(payload)
    if "timestamp" in kwargs and isinstance(kwargs["timestamp"], str):
        kwargs["timestamp"] = _parse_iso_timestamp(kwargs["timestamp"])
    return OverrideEvent(**kwargs)


def _parse_iso_timestamp(value: str) -> datetime:
    raw = value[:-1] + "+00:00" if value.endswith("Z") else value
    parsed = datetime.fromisoformat(raw)
    if parsed.tzinfo is None:
        raise ValueError(
            f"timestamp must be tz-aware (got naive: {value!r}); "
            "include a 'Z' or '+HH:MM' offset"
        )
    return parsed


def _validation_response(reason: str, detail: str) -> JSONResponse:
    validation_errors_total.labels(reason=reason).inc()
    requests_total.labels(endpoint="canonical", status="rejected").inc()
    return JSONResponse({"detail": detail}, status_code=400)
```

- [ ] **Step 4: Run tests, confirm they pass (both single and batch suites)**

```bash
uv run pytest tests/test_routes_canonical_single.py tests/test_routes_canonical_batch.py -v
uv run ruff check src/ tests/
```

Expected: 6 (single) + 6 (batch) = 12 passed; ruff clean.

- [ ] **Step 5: Commit**

```bash
git add src/nthlayer_override_adapter/routes/canonical.py tests/test_routes_canonical_batch.py
git commit -m "feat: canonical POST /api/v1/overrides/batch with last-in-array-wins

Walks entries to compute winners per decision_id first, then emits
exactly one span per unique accepted ID. Duplicates report carries
decision_id + applied_at_index + discarded_indices so callers can
reconcile their submission. Cardinality-match invariant: response
'accepted' set == emitted-span decision_id set.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 7: Webhook endpoint with dynamic registration

**Files:**
- Create: `src/nthlayer_override_adapter/routes/webhook.py`
- Create: `tests/test_routes_webhook.py`

- [ ] **Step 1: Write the failing tests**

`tests/test_routes_webhook.py`:
```python
import pytest
from starlette.applications import Starlette
from starlette.testclient import TestClient

from nthlayer_common.overrides import OverridePrivacyConfig
from nthlayer_override_adapter.config import WebhookAdapter
from nthlayer_override_adapter.routes.webhook import register_webhook_routes


@pytest.fixture
def jira_adapter() -> WebhookAdapter:
    return WebhookAdapter(
        source="jira",
        webhook_path="/webhook/jira",
        field_mapping={
            "decision_id": "issue.customfield_10042",
            "corrected_action": "issue.resolution.name",
            "reviewer": "issue.assignee.emailAddress",
            "timestamp": "issue.updated",
            "reason": "issue.resolution.description",
        },
        defaults={"source_system": "jira", "service": "fraud-detect"},
    )


@pytest.fixture
def client(span_exporter, jira_adapter) -> TestClient:
    app = Starlette()
    register_webhook_routes(app, adapters=[jira_adapter], privacy=OverridePrivacyConfig())
    return TestClient(app)


JIRA_PAYLOAD: dict[str, object] = {
    "issue": {
        "customfield_10042": "vrd-001",
        "resolution": {
            "name": "escalate",
            "description": "Model regression — escalate to senior analyst",
        },
        "assignee": {"emailAddress": "analyst-047@example.com"},
        "updated": "2026-05-15T12:00:00Z",
    },
}


class TestJiraWebhook:
    def test_jira_shaped_payload_produces_span(self, client, span_exporter) -> None:
        resp = client.post("/webhook/jira", json=JIRA_PAYLOAD)
        assert resp.status_code == 201
        body = resp.json()
        assert body["decision_id"] == "vrd-001"
        assert body["emitted_to_otel"] is True
        spans = span_exporter.get_finished_spans()
        assert len(spans) == 1
        attrs = spans[0].attributes
        assert attrs["gen_ai.override.decision_id"] == "vrd-001"
        assert attrs["gen_ai.override.service"] == "fraud-detect"
        assert attrs["gen_ai.override.corrected_action"] == "escalate"

    def test_missing_required_path_400(self, client) -> None:
        bad = {"issue": {"customfield_10042": "vrd-002"}}  # no reviewer / corrected_action
        resp = client.post("/webhook/jira", json=bad)
        assert resp.status_code == 400

    def test_unconfigured_path_404(self, client) -> None:
        resp = client.post("/webhook/notexist", json={})
        assert resp.status_code == 404


class TestEmptyAdaptersList:
    def test_no_routes_registered(self, span_exporter) -> None:
        app = Starlette()
        register_webhook_routes(app, adapters=[], privacy=OverridePrivacyConfig())
        client = TestClient(app)
        resp = client.post("/webhook/jira", json={})
        assert resp.status_code == 404
```

- [ ] **Step 2: Run tests, confirm they fail**

```bash
uv run pytest tests/test_routes_webhook.py -v
```

Expected: `ModuleNotFoundError` for `routes.webhook`.

- [ ] **Step 3: Implement `routes/webhook.py`**

`src/nthlayer_override_adapter/routes/webhook.py`:
```python
"""Dynamic webhook routes — one POST endpoint per configured source.

Each configured ``WebhookAdapter`` registers ``POST {webhook_path}``.
The handler runs ``map_webhook_to_override`` with the adapter's field
mapping + defaults, then emits via the shared emission path. Required-
field failures from the mapper surface as 400.
"""
from __future__ import annotations

import json

from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route

from nthlayer_common.overrides import (
    OverridePrivacyConfig,
    map_webhook_to_override,
)

from nthlayer_override_adapter.config import WebhookAdapter
from nthlayer_override_adapter.emission import emit_override
from nthlayer_override_adapter.metrics import (
    requests_total,
    validation_errors_total,
)
from nthlayer_override_adapter.response import accepted_single


def register_webhook_routes(
    app: Starlette,
    *,
    adapters: list[WebhookAdapter],
    privacy: OverridePrivacyConfig,
) -> None:
    """Mount one POST {webhook_path} route per configured adapter."""
    for adapter in adapters:
        app.routes.append(
            Route(
                adapter.webhook_path,
                _make_handler(adapter, privacy=privacy),
                methods=["POST"],
            )
        )


def _make_handler(adapter: WebhookAdapter, *, privacy: OverridePrivacyConfig):
    async def handle(request: Request) -> JSONResponse:
        try:
            payload = await request.json()
        except json.JSONDecodeError as exc:
            return _validation_response("malformed_json", str(exc))

        if not isinstance(payload, dict):
            return _validation_response(
                "invalid_body",
                f"webhook body must be a JSON object, got {type(payload).__name__}",
            )

        try:
            event = map_webhook_to_override(
                payload,
                mapping=adapter.field_mapping,
                defaults=adapter.defaults,
            )
        except ValueError as exc:
            return _validation_response("mapper_error", str(exc))

        emit_override(event, privacy)
        requests_total.labels(endpoint="webhook", status="accepted").inc()
        return JSONResponse(accepted_single(event.decision_id), status_code=201)

    return handle


def _validation_response(reason: str, detail: str) -> JSONResponse:
    validation_errors_total.labels(reason=reason).inc()
    requests_total.labels(endpoint="webhook", status="rejected").inc()
    return JSONResponse({"detail": detail}, status_code=400)
```

- [ ] **Step 4: Run tests, confirm they pass**

```bash
uv run pytest tests/test_routes_webhook.py -v
uv run ruff check src/ tests/
```

Expected: 4 passed; ruff clean.

- [ ] **Step 5: Commit**

```bash
git add src/nthlayer_override_adapter/routes/webhook.py tests/test_routes_webhook.py
git commit -m "feat: dynamic /webhook/{source} routes per YAML adapter

Each WebhookAdapter registers POST {webhook_path}; handler runs
map_webhook_to_override with the adapter's field_mapping + defaults
and emits via the shared emit_override path. Required-field failures
surface as 400.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 8: App composition + /healthz + /metrics

**Files:**
- Create: `src/nthlayer_override_adapter/app.py`
- Create: `tests/test_app.py`

- [ ] **Step 1: Write the failing tests**

`tests/test_app.py`:
```python
import pytest
from starlette.testclient import TestClient

from nthlayer_common.overrides import OverridePrivacyConfig
from nthlayer_override_adapter.app import build_app
from nthlayer_override_adapter.config import AdapterConfig, WebhookAdapter


@pytest.fixture
def cfg() -> AdapterConfig:
    return AdapterConfig(
        adapters=[
            WebhookAdapter(
                source="jira",
                webhook_path="/webhook/jira",
                field_mapping={
                    "decision_id": "issue.id",
                    "corrected_action": "issue.action",
                    "reviewer": "issue.who",
                },
                defaults={"service": "fraud-detect"},
            ),
        ],
        privacy=OverridePrivacyConfig(),
    )


@pytest.fixture
def client(span_exporter, cfg) -> TestClient:
    return TestClient(build_app(cfg))


class TestHealthAndMetrics:
    def test_healthz_returns_200(self, client) -> None:
        resp = client.get("/healthz")
        assert resp.status_code == 200
        assert resp.json() == {"status": "ok"}

    def test_metrics_returns_prometheus_text(self, client) -> None:
        resp = client.get("/metrics")
        assert resp.status_code == 200
        assert "override_requests_total" in resp.text
        assert resp.headers["content-type"].startswith("text/plain")


class TestAllRoutesWired:
    def test_canonical_single_present(self, client) -> None:
        resp = client.post("/api/v1/overrides", json={"bad": "body"})
        # 400 means route exists and reached validation; 404 would mean
        # the route wasn't registered.
        assert resp.status_code == 400

    def test_canonical_batch_present(self, client) -> None:
        resp = client.post("/api/v1/overrides/batch", json={"bad": "body"})
        assert resp.status_code == 400

    def test_webhook_present(self, client) -> None:
        resp = client.post("/webhook/jira", json={"bad": "body"})
        assert resp.status_code == 400
```

- [ ] **Step 2: Run tests, confirm they fail**

```bash
uv run pytest tests/test_app.py -v
```

Expected: `ModuleNotFoundError: No module named 'nthlayer_override_adapter.app'`.

- [ ] **Step 3: Implement `app.py`**

`src/nthlayer_override_adapter/app.py`:
```python
"""Starlette app factory — wires canonical + webhook routes + health + metrics."""
from __future__ import annotations

from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.routing import Route

from nthlayer_common.metrics import metrics_content_type, render_metrics

from nthlayer_override_adapter.config import AdapterConfig
from nthlayer_override_adapter.routes.canonical import register_canonical_routes
from nthlayer_override_adapter.routes.webhook import register_webhook_routes


def build_app(config: AdapterConfig) -> Starlette:
    """Construct the Starlette app from a loaded ``AdapterConfig``."""
    app = Starlette()
    app.routes.append(Route("/healthz", _healthz, methods=["GET"]))
    app.routes.append(Route("/metrics", _metrics, methods=["GET"]))
    register_canonical_routes(app, privacy=config.privacy)
    register_webhook_routes(
        app, adapters=config.adapters, privacy=config.privacy,
    )
    return app


async def _healthz(request: Request) -> JSONResponse:
    return JSONResponse({"status": "ok"})


async def _metrics(request: Request) -> Response:
    return Response(render_metrics(), media_type=metrics_content_type())
```

- [ ] **Step 4: Run tests, confirm they pass**

```bash
uv run pytest tests/test_app.py -v
uv run pytest -q  # full suite still passes
uv run ruff check src/ tests/
```

Expected: 5 (test_app) passed; full suite 39+ passed; ruff clean.

- [ ] **Step 5: Commit**

```bash
git add src/nthlayer_override_adapter/app.py tests/test_app.py
git commit -m "feat: Starlette app factory wiring routes + health + metrics

build_app(config) mounts /healthz (JSON ok) + /metrics (Prometheus
text via nthlayer_common.metrics.render_metrics) + canonical routes
+ one /webhook/{source} per configured adapter.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 9: CLI `serve` entry

**Files:**
- Create: `src/nthlayer_override_adapter/cli.py`
- Create: `tests/test_cli.py`

- [ ] **Step 1: Write the failing tests**

`tests/test_cli.py`:
```python
from pathlib import Path

import pytest

from nthlayer_override_adapter.cli import build_parser, load_app


def _write_minimal_config(tmp_path: Path) -> Path:
    p = tmp_path / "cfg.yaml"
    p.write_text("adapters: []\n")
    return p


class TestArgParse:
    def test_serve_subcommand_defaults(self) -> None:
        parser = build_parser()
        ns = parser.parse_args(["serve"])
        assert ns.command == "serve"
        assert ns.host == "0.0.0.0"  # noqa: S104 — default bind for a sidecar
        assert ns.port == 8090
        assert ns.config is None

    def test_serve_subcommand_overrides(self) -> None:
        parser = build_parser()
        ns = parser.parse_args(
            ["serve", "--host", "127.0.0.1", "--port", "9000", "--config", "/x.yaml"]
        )
        assert ns.host == "127.0.0.1"
        assert ns.port == 9000
        assert ns.config == "/x.yaml"


class TestLoadApp:
    def test_load_app_from_explicit_config(self, tmp_path: Path) -> None:
        cfg = _write_minimal_config(tmp_path)
        app = load_app(str(cfg))
        assert app is not None
        paths = {r.path for r in app.routes if hasattr(r, "path")}
        assert "/healthz" in paths
        assert "/api/v1/overrides" in paths

    def test_load_app_missing_config_exits(self, tmp_path: Path) -> None:
        with pytest.raises(SystemExit):
            load_app(str(tmp_path / "absent.yaml"))
```

- [ ] **Step 2: Run tests, confirm they fail**

```bash
uv run pytest tests/test_cli.py -v
```

Expected: `ModuleNotFoundError`.

- [ ] **Step 3: Implement `cli.py`**

`src/nthlayer_override_adapter/cli.py`:
```python
"""nthlayer-override-adapter — CLI entry."""
from __future__ import annotations

import argparse
import os
import sys

import structlog
import uvicorn
from starlette.applications import Starlette

from nthlayer_override_adapter.app import build_app
from nthlayer_override_adapter.config import ConfigError, load_config

logger = structlog.get_logger(__name__)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="nthlayer-override-adapter")
    subs = parser.add_subparsers(dest="command", required=True)

    serve = subs.add_parser("serve", help="run the override-adapter HTTP server")
    serve.add_argument(
        "--config",
        default=None,
        help="path to override-adapter-config.yaml "
             "(default: $NTHLAYER_OVERRIDE_ADAPTER_CONFIG)",
    )
    serve.add_argument("--host", default="0.0.0.0")  # noqa: S104
    serve.add_argument("--port", type=int, default=8090)
    return parser


def load_app(config_path: str | None) -> Starlette:
    """Load config from path (or env) and build the Starlette app.

    Exits via ``SystemExit`` on config-not-found / config-invalid so
    the process fails loudly at startup rather than serving with an
    incomplete adapter set.
    """
    resolved = config_path or os.environ.get("NTHLAYER_OVERRIDE_ADAPTER_CONFIG")
    if resolved is None:
        sys.stderr.write(
            "error: --config or $NTHLAYER_OVERRIDE_ADAPTER_CONFIG required\n",
        )
        raise SystemExit(2)
    try:
        cfg = load_config(resolved)
    except ConfigError as exc:
        sys.stderr.write(f"error: {exc}\n")
        raise SystemExit(2) from exc
    return build_app(cfg)


def main() -> int:
    args = build_parser().parse_args()
    if args.command == "serve":
        app = load_app(args.config)
        logger.info(
            "override_adapter_serving",
            host=args.host,
            port=args.port,
            config=args.config,
        )
        uvicorn.run(app, host=args.host, port=args.port, log_config=None)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Run tests, confirm they pass**

```bash
uv run pytest tests/test_cli.py -v
uv run ruff check src/ tests/
```

Expected: 4 passed; ruff clean.

- [ ] **Step 5: Confirm the console script is wired**

```bash
uv run nthlayer-override-adapter --help
uv run nthlayer-override-adapter serve --help
```

Expected: both exit 0 with usage text.

- [ ] **Step 6: Commit**

```bash
git add src/nthlayer_override_adapter/cli.py tests/test_cli.py
git commit -m "feat: nthlayer-override-adapter serve CLI entry

argparse-based; serve subcommand reads --config (or env), defaults
host=0.0.0.0 port=8090, runs uvicorn. Exits non-zero on config-not-
found or invalid YAML so the process fails loudly at startup rather
than serving with an incomplete adapter set.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 10: Smoke tests (for release-time gate)

**Files:**
- Create: `tests/smoke/__init__.py`
- Create: `tests/smoke/test_imports.py`
- Create: `tests/smoke/test_cli.py`

- [ ] **Step 1: Write the smoke tests**

`tests/smoke/__init__.py`:
```python
```

`tests/smoke/test_imports.py`:
```python
"""Smoke test: every public module imports without error.

Mirrors nthlayer_common/tests/smoke/test_imports.py. Catches stale
__all__ entries and broken imports before the wheel reaches PyPI.
"""
from __future__ import annotations

import importlib
import pkgutil

import nthlayer_override_adapter


def test_all_submodules_import() -> None:
    pkg = nthlayer_override_adapter
    for info in pkgutil.walk_packages(pkg.__path__, prefix=f"{pkg.__name__}."):
        mod = importlib.import_module(info.name)
        for name in getattr(mod, "__all__", ()):
            assert getattr(mod, name) is not None, (
                f"{info.name}.{name} declared in __all__ but unresolved"
            )
```

`tests/smoke/test_cli.py`:
```python
"""Smoke test: the console script is on PATH and --help works."""
from __future__ import annotations

import shutil
import subprocess


def test_console_script_on_path() -> None:
    binary = shutil.which("nthlayer-override-adapter")
    assert binary is not None, "console script not on PATH after install"


def test_help_exits_zero() -> None:
    result = subprocess.run(
        ["nthlayer-override-adapter", "--help"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0
    assert result.stdout.strip() != ""
```

- [ ] **Step 2: Run the smoke tests**

```bash
uv run pytest tests/smoke/ -v
```

Expected: 3 passed.

- [ ] **Step 3: Commit**

```bash
git add tests/smoke/
git commit -m "test: add smoke tests for release-time Docker gate

Walks every module under nthlayer_override_adapter via pkgutil and
asserts __all__ symbols resolve. Verifies console script lands on
PATH and --help exits 0 with non-empty output. Mirrors the smoke-
suite pattern from nthlayer-common and nthlayer-workers.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 11: README + CLAUDE.md for the new repo

**Files:**
- Create: `README.md`
- Create: `CLAUDE.md`

- [ ] **Step 1: Write `README.md`**

`README.md`:
```markdown
# nthlayer-override-adapter

Standalone HTTP sidecar that accepts human-override events and emits them as `gen_ai.override` OTel spans. Part of the [NthLayer](https://github.com/rsionnach/nthlayer) ecosystem; implements [`opensrm-jmy.7`](https://github.com/rsionnach/opensrm) — § 4 of `NTHLAYER_MISSING_CAPABILITIES_SPEC.md`.

## Why

`nthlayer-measure` computes judgment SLOs from override metrics consumed via OTel. Operators reviewing AI decisions live in heterogeneous tools (Slack, Jira, internal review UIs, email). The override-adapter is the translation layer: HTTP in, canonical OTel `gen_ai.override` events out.

## Endpoints

- `POST /api/v1/overrides` — canonical OverrideEvent JSON in.
- `POST /api/v1/overrides/batch` — `{overrides: [...]}` with last-in-array-wins on duplicate `decision_id`.
- `POST /webhook/{source}` — one route per configured adapter; runs a YAML-declared field mapping on the inbound webhook payload.
- `GET /healthz` — liveness probe.
- `GET /metrics` — Prometheus self-observability.

## Run locally

```bash
uv sync --extra dev
uv run nthlayer-override-adapter serve --config override-adapter-config.yaml
```

See `override-adapter-config.yaml.example` for a Jira-shaped adapter declaration.

## Tests

```bash
uv run pytest -q
uv run ruff check src/ tests/
```

## License

Apache 2.0.
```

- [ ] **Step 2: Write `CLAUDE.md`**

`CLAUDE.md`:
```markdown
# nthlayer-override-adapter

Standalone HTTP sidecar — accepts override events via canonical JSON, batch JSON, or generic webhook payloads; emits each as one unparented `gen_ai.override` OTel span. Implements `opensrm-jmy.7` (Wave A). Slack adapter (`opensrm-jmy.17`) and verdict-binding OTel consumer in `nthlayer-workers/measure` (`opensrm-jmy.18`) are separate beads.

## Architecture

```
src/nthlayer_override_adapter/
  __init__.py     # Package marker
  config.py       # AdapterConfig + WebhookAdapter dataclasses; load_config() reads YAML
  metrics.py      # Prometheus counters: requests_total, emission_total, validation_errors_total, collector_errors_total; emit_duration_seconds histogram
  response.py     # BatchResult dataclass + accepted_single / build_batch_response helpers; response shape per design doc § 3
  emission.py     # emit_override(event, privacy) — opens unparented gen_ai.override span; applies hash_reviewer (default) / drops reason when exclude_reason; fail-open on exporter errors
  app.py          # build_app(config) — Starlette factory; wires /healthz + /metrics + canonical + dynamic webhook routes
  cli.py          # nthlayer-override-adapter serve [--config <path>] [--host <h>] [--port <p>]; exits 2 on config-not-found
  routes/
    canonical.py  # POST /api/v1/overrides + POST /api/v1/overrides/batch (last-in-array-wins on dup decision_id, computes winners then emits exactly one span per unique accepted decision_id)
    webhook.py    # Dynamic POST {webhook_path} per WebhookAdapter; handler runs map_webhook_to_override + emit
```

## Conventions

- **Privacy at emission**, not consumer: hash_reviewer applied before `OverrideEvent.to_otel_attributes()` so plaintext reviewers never enter the OTel pipeline.
- **Unparented spans**: `gen_ai.override` is emitted with an empty OTel `Context()` — overrides are operator decisions not bound to any service trace. Do not "fix" this to inherit a current trace context.
- **Cardinality-match invariant**: response `accepted` set always equals the set of emitted-span `gen_ai.override.decision_id` values. Tests assert this explicitly in `tests/test_routes_canonical_batch.py::TestCardinalityInvariant`.
- **Fail-open on OTel export errors**: HTTP request still returns 201 even if export is degraded; the OTel SDK retries / buffers. `override_collector_errors_total` increments.
- **No auth in v1.5**: matches `nthlayer-core` posture. File a follow-up bead if a real deployment needs it.

## Commands

```bash
uv sync --extra dev
uv run pytest -q                   # full suite + smoke
uv run ruff check src/ tests/
uv run nthlayer-override-adapter serve --config <path>
```

## Dependencies

- `nthlayer-common>=1.5.0,<2.0.0` — overrides foundation (`OverrideEvent`, `OverridePrivacyConfig`, `map_webhook_to_override`, `hash_reviewer`), self-metrics helpers
- `starlette>=0.40`, `uvicorn>=0.30` — ASGI stack, mirrors core / workers/respond
- `opentelemetry-api>=1.28`, `opentelemetry-sdk>=1.28`, `opentelemetry-exporter-otlp>=1.28` — span emission + OTLP export
- `pyyaml>=6.0` — adapter config loading
- `structlog>=24.1.0` — logging
- `prometheus-client>=0.21` — `/metrics`

Dev: `pytest>=8.2`, `pytest-asyncio>=0.23`, `httpx>=0.27` (Starlette TestClient), `ruff>=0.8`.

## Spec + plan references

- Design spec: `nthlayer/docs/superpowers/specs/2026-05-15-jmy7-override-adapter-sidecar-design.md`
- Implementation plan: `nthlayer/docs/superpowers/plans/2026-05-15-jmy7-override-adapter-sidecar.md`
- Capability spec source: `nthlayer/docs/roadmap/NTHLAYER_MISSING_CAPABILITIES_SPEC.md` § 4
```

- [ ] **Step 3: Commit**

```bash
git add README.md CLAUDE.md
git commit -m "docs: add README + CLAUDE.md for nthlayer-override-adapter

Repo-level README with run/test instructions and endpoint summary.
CLAUDE.md captures architecture, conventions (privacy-at-emission,
unparented spans, cardinality invariant, fail-open exporter), and
links back to design spec + implementation plan.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 12: Dockerfile + CI workflows + release-please

**Files:**
- Create: `Dockerfile`
- Create: `release-please-config.json`
- Create: `.release-please-manifest.json`
- Create: `.github/dependabot.yml`
- Create: `.github/workflows/test.yml`
- Create: `.github/workflows/release.yml`
- Create: `.github/workflows/dependabot-automerge.yml`

- [ ] **Step 1: Write `Dockerfile`**

`Dockerfile`:
```dockerfile
FROM python:3.11-slim AS builder

ENV UV_LINK_MODE=copy \
    UV_COMPILE_BYTECODE=1 \
    UV_NO_CACHE=1

RUN pip install --no-cache-dir uv==0.5.0

WORKDIR /build
COPY pyproject.toml uv.lock README.md ./
COPY src ./src

RUN uv sync --no-dev --frozen
RUN uv build --wheel

FROM python:3.11-slim

RUN useradd --create-home --shell /bin/bash adapter
WORKDIR /home/adapter

COPY --from=builder /build/dist/*.whl /tmp/
RUN pip install --no-cache-dir /tmp/*.whl && rm /tmp/*.whl

USER adapter
EXPOSE 8090

ENTRYPOINT ["nthlayer-override-adapter", "serve"]
CMD ["--host", "0.0.0.0", "--port", "8090"]
```

- [ ] **Step 2: Write release-please config**

`release-please-config.json`:
```json
{
  "release-type": "python",
  "packages": {
    ".": {
      "package-name": "nthlayer-override-adapter",
      "changelog-path": "CHANGELOG.md",
      "include-component-in-tag": false,
      "changelog-sections": [
        {"type": "feat", "section": "Features"},
        {"type": "fix", "section": "Bug Fixes"},
        {"type": "perf", "section": "Performance"},
        {"type": "deps", "section": "Dependencies"},
        {"type": "refactor", "section": "Refactors"},
        {"type": "docs", "section": "Documentation"},
        {"type": "chore", "hidden": true},
        {"type": "test", "hidden": true},
        {"type": "ci", "hidden": true},
        {"type": "build", "hidden": true},
        {"type": "style", "hidden": true}
      ]
    }
  }
}
```

`.release-please-manifest.json`:
```json
{
  ".": "0.1.0"
}
```

- [ ] **Step 3: Write CI workflows**

`.github/workflows/test.yml`:
```yaml
name: test

on:
  push:
    branches: [main]
  pull_request:
    branches: [main]

jobs:
  test:
    runs-on: ubuntu-latest
    strategy:
      fail-fast: false
      matrix:
        python-version: ["3.11", "3.12", "3.13"]
    steps:
      - uses: actions/checkout@v4
        with:
          path: nthlayer-override-adapter
      - uses: actions/checkout@v4
        with:
          repository: rsionnach/nthlayer-common
          path: nthlayer-common
      - uses: astral-sh/setup-uv@v7
      - name: uv sync
        working-directory: nthlayer-override-adapter
        run: uv sync --extra dev --python ${{ matrix.python-version }}
      - name: ruff
        working-directory: nthlayer-override-adapter
        run: uv run ruff check src/ tests/
      - name: pytest
        working-directory: nthlayer-override-adapter
        run: uv run pytest -q
```

`.github/workflows/release.yml`:
```yaml
name: release

on:
  push:
    tags: ["v*"]
  workflow_dispatch:

permissions:
  contents: read
  id-token: write  # trusted publishing

jobs:
  release-please:
    if: ${{ github.event_name != 'workflow_dispatch' }}
    runs-on: ubuntu-latest
    steps:
      - uses: googleapis/release-please-action@v4
        with:
          config-file: release-please-config.json
          manifest-file: .release-please-manifest.json

  publish:
    if: ${{ startsWith(github.ref, 'refs/tags/v') || github.event_name == 'workflow_dispatch' }}
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v7
      - name: build
        run: uv build
      - name: twine check
        run: |
          uv pip install --system twine
          twine check dist/*
      - name: smoke gate (Docker)
        run: |
          docker run --rm \
            -v "${{ github.workspace }}/dist:/dist:ro" \
            -v "${{ github.workspace }}/tests/smoke:/smoke:ro" \
            python:3.11-slim bash -c "
              pip install --no-cache-dir /dist/*.whl pytest &&
              pytest /smoke -v
            "
      - name: publish
        uses: pypa/gh-action-pypi-publish@release/v1
```

`.github/workflows/dependabot-automerge.yml`:
```yaml
name: dependabot-automerge

on: pull_request

permissions:
  contents: write
  pull-requests: write

jobs:
  automerge:
    if: github.actor == 'dependabot[bot]'
    runs-on: ubuntu-latest
    steps:
      - id: metadata
        uses: dependabot/fetch-metadata@v2
      - name: enable auto-merge for patch/minor of external deps
        if: |
          steps.metadata.outputs.update-type == 'version-update:semver-patch' ||
          (steps.metadata.outputs.update-type == 'version-update:semver-minor' &&
           steps.metadata.outputs.dependency-type != 'direct:production')
        run: gh pr merge --auto --squash "$PR_URL"
        env:
          PR_URL: ${{ github.event.pull_request.html_url }}
          GH_TOKEN: ${{ secrets.GITHUB_TOKEN }}
```

`.github/dependabot.yml`:
```yaml
version: 2
updates:
  - package-ecosystem: uv
    directory: /
    schedule:
      interval: weekly
      day: monday
      time: "08:00"
      timezone: Europe/Dublin
    groups:
      nthlayer-siblings:
        patterns: ["nthlayer-*"]
      dev:
        dependency-type: development
  - package-ecosystem: github-actions
    directory: /
    schedule:
      interval: weekly
      day: monday
      time: "08:00"
      timezone: Europe/Dublin
```

- [ ] **Step 4: Verify YAML / JSON parse**

```bash
uv run python -c "import yaml, json, pathlib; \
  yaml.safe_load(pathlib.Path('.github/workflows/test.yml').read_text()); \
  yaml.safe_load(pathlib.Path('.github/workflows/release.yml').read_text()); \
  yaml.safe_load(pathlib.Path('.github/workflows/dependabot-automerge.yml').read_text()); \
  yaml.safe_load(pathlib.Path('.github/dependabot.yml').read_text()); \
  json.loads(pathlib.Path('release-please-config.json').read_text()); \
  json.loads(pathlib.Path('.release-please-manifest.json').read_text()); \
  print('ok')"
```

Expected: `ok`.

- [ ] **Step 5: Commit**

```bash
git add Dockerfile release-please-config.json .release-please-manifest.json .github/
git commit -m "ci: add Dockerfile, release-please, test + release workflows, dependabot

Two-stage Dockerfile builds the wheel then installs into a slim
runtime image as a non-root user. Release workflow includes the
Docker-based smoke gate before PyPI publish (same pattern as
nthlayer-common / nthlayer-workers). Dependabot covers uv + GH
Actions on the standard Monday-morning Europe/Dublin schedule.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 13: Local end-to-end live verification

This task is non-TDD — it's the live-stack gate that the 2026-05-15 handoff established as a standing rule for any data-flow / sentinel / pagination change. No commit at the end (the system stays as committed at Task 12).

**Files:** none modified.

- [ ] **Step 1: Start a real OTel collector locally (Docker)**

Write a one-off `otel-collector-config.yaml` in a scratch tmp dir:

```yaml
receivers:
  otlp:
    protocols:
      grpc:
        endpoint: 0.0.0.0:4317

processors:
  batch:

exporters:
  file:
    path: /tmp/otel-out.json

service:
  pipelines:
    traces:
      receivers: [otlp]
      processors: [batch]
      exporters: [file]
```

Run:
```bash
docker run --rm -d --name otel-test \
  -p 4317:4317 \
  -v "$(pwd)/otel-collector-config.yaml:/etc/otel-collector-config.yaml" \
  -v /tmp:/tmp \
  otel/opentelemetry-collector:0.114.0 \
  --config=/etc/otel-collector-config.yaml
```

- [ ] **Step 2: Write a one-off adapter config pointing at the collector**

```bash
cat > /tmp/adapter-config.yaml <<EOF
adapters:
  - source: jira
    webhook_path: /webhook/jira
    field_mapping:
      decision_id: "issue.customfield_10042"
      corrected_action: "issue.resolution.name"
      reviewer: "issue.assignee.emailAddress"
      timestamp: "issue.updated"
    defaults:
      source_system: jira
      service: fraud-detect
privacy:
  plaintext_reviewer: false
  exclude_reason: false
otel:
  exporter: otlp
  endpoint: "http://localhost:4317"
EOF
```

- [ ] **Step 3: Start the adapter**

```bash
cd /Users/robfox/Documents/GitHub/nthlayer-ecosystem/nthlayer-override-adapter
OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4317 \
OTEL_SERVICE_NAME=nthlayer-override-adapter \
uv run nthlayer-override-adapter serve --config /tmp/adapter-config.yaml --port 8090 &
sleep 2
curl -fsS http://localhost:8090/healthz
```

Expected: `{"status":"ok"}`.

- [ ] **Step 4: Post a canonical override + a batch + a Jira webhook**

```bash
curl -fsS -X POST http://localhost:8090/api/v1/overrides \
  -H 'content-type: application/json' \
  -d '{"decision_id":"live-001","service":"fraud-detect","corrected_action":"escalate","reviewer":"analyst-047","timestamp":"2026-05-15T12:00:00Z"}'

curl -fsS -X POST http://localhost:8090/api/v1/overrides/batch \
  -H 'content-type: application/json' \
  -d '{"overrides":[
    {"decision_id":"live-002","service":"fraud-detect","corrected_action":"approve","reviewer":"a","timestamp":"2026-05-15T12:01:00Z"},
    {"decision_id":"live-003","service":"fraud-detect","corrected_action":"reject","reviewer":"b","timestamp":"2026-05-15T12:02:00Z"},
    {"decision_id":"live-002","service":"fraud-detect","corrected_action":"escalate","reviewer":"c","timestamp":"2026-05-15T12:03:00Z"}
  ]}'

curl -fsS -X POST http://localhost:8090/webhook/jira \
  -H 'content-type: application/json' \
  -d '{"issue":{"customfield_10042":"live-004","resolution":{"name":"escalate"},"assignee":{"emailAddress":"analyst-047@example.com"},"updated":"2026-05-15T12:04:00Z"}}'
```

Expected: each returns the appropriate 201 / 200 with `accepted` reflecting the posted decision_ids and `duplicates` showing `live-002` with `applied_at_index: 2, discarded_indices: [0]`.

- [ ] **Step 5: Verify spans landed in the collector's file exporter**

```bash
sleep 3
docker logs otel-test 2>&1 | tail -10
ls -la /tmp/otel-out.json
cat /tmp/otel-out.json | head -200
```

Expected: file contains spans named `gen_ai.override` with `gen_ai.override.decision_id` in {live-001, live-002, live-003, live-004} — exactly **4 unique decision_ids** despite 5 successful POSTs (live-002 deduped via last-in-array-wins). Reviewer attributes are the SHA-256 hex (hashed, since `plaintext_reviewer: false`).

- [ ] **Step 6: Verify the cardinality invariant in live data**

```bash
python3 -c "
import json
spans = []
with open('/tmp/otel-out.json') as f:
    for line in f:
        line = line.strip()
        if not line:
            continue
        try:
            spans.append(json.loads(line))
        except json.JSONDecodeError:
            pass
# Extract decision_ids from gen_ai.override spans only
decision_ids = set()
for batch in spans:
    for rs in batch.get('resourceSpans', []):
        for ss in rs.get('scopeSpans', []):
            for span in ss.get('spans', []):
                if span.get('name') == 'gen_ai.override':
                    for attr in span.get('attributes', []):
                        if attr.get('key') == 'gen_ai.override.decision_id':
                            decision_ids.add(attr['value'].get('stringValue'))
print(f'unique decision_ids in spans: {sorted(decision_ids)}')
assert decision_ids == {'live-001', 'live-002', 'live-003', 'live-004'}, decision_ids
print('cardinality invariant holds in live data')
"
```

Expected: `cardinality invariant holds in live data`.

- [ ] **Step 7: Tear down**

```bash
kill %1                        # stop the adapter (jobspec from step 3)
docker stop otel-test
rm /tmp/otel-out.json /tmp/adapter-config.yaml /tmp/otel-collector-config.yaml
```

- [ ] **Step 8: Note the verification result in the bead**

```bash
cd /Users/robfox/Documents/GitHub/nthlayer-ecosystem/opensrm
bd update opensrm-jmy.7 --append-notes "Live E2E verification 2026-05-15: real OTel collector + Docker; canonical single, batch with last-in-array-wins, and Jira-shaped webhook all produced spans with the expected cardinality (4 unique decision_ids from 5 successful POSTs). Hashed reviewer attribute confirmed in collector file output."
```

If verification surfaces a problem, file it as a follow-up bead, fix in this branch, and re-run before proceeding to R5.

---

## Final gate — ready for R5

At this point the bead is implementation-complete. Hand off to `/r5-supervise opensrm-jmy.7`:

```bash
/r5-supervise opensrm-jmy.7
```

Per the ecosystem-root CLAUDE.md, the supervisor runs the 4-pass sequential R5 (Correctness / Clarity / Edge Cases / Excellence) with a fix-loop between passes. Once all four pass clean, the supervisor stops at "all four clean — confirm bead close?" — confirm and close.

---

## Spec coverage check

| Spec section | Implemented in |
|---|---|
| § 1 Wave A scope | Tasks 0–13 |
| § 2 Architecture / new repo | Task 0 (bootstrap), Task 12 (CI / release) |
| § 3.1 `POST /api/v1/overrides` | Task 5 |
| § 3.2 `POST /api/v1/overrides/batch` (scenarios 3 + 4) | Task 6 |
| § 3.3 `POST /webhook/{source}` | Task 7 |
| § 3.4 `/healthz`, `/metrics` | Task 8 |
| § 4 OTel emission + unparented-span rationale | Task 4 |
| § 5 YAML config shape | Task 1 |
| § 6 Privacy at emission boundary | Task 4 (`_apply_privacy`) |
| § 7 Test strategy (Starlette TestClient + InMemorySpanExporter + cardinality invariant) | Tasks 4–8 |
| § 8 Self-observability | Task 2, exposed in Task 8 |
| § 9.1 Repo bootstrapped | Task 0 |
| § 9.2 Endpoints work end-to-end | Tasks 5, 6, 7 |
| § 9.3 Spec § 4 scenarios 2, 3, 4 pass | Tasks 5, 6 |
| § 9.4 R5 review clean | Final gate |
| § 9.5 Live verification | Task 13 |
| § 9.6 CLAUDE.md + cross-links | Task 11 (this repo's CLAUDE.md); ecosystem-root CLAUDE.md member table is local-only and was already updated by auto-memory after the design doc landed |
