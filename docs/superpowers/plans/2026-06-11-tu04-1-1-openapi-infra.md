# tu04.1.1 OpenAPI infrastructure + `/health` worked example — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Land the OpenAPI 3.1 framework for nthlayer-core: a structured Python dict as source of truth, twin artefacts (runtime endpoint + checked-in JSON), four parity/validity/match/serve tests, and `/health` as the one fully-documented endpoint. Phases 2/3/4 (tu04.1.2/3/4) plug into this framework with one new file each.

**Architecture:**
- `src/nthlayer_core/openapi_spec.py` aggregates the spec from per-group modules and exposes `OPENAPI`, `_route_spec_pairs()`, `_spec_path_method_pairs()`, `assert_parity()`.
- `src/nthlayer_core/_openapi/` (new subpackage) holds one module per path group: `paths_health.py` ships in this beadlet; `paths_verdicts.py` / `paths_assessments_cases.py` / `paths_other.py` ship in tu04.1.2-4.
- Each group module exports `PATHS: dict` and `SCHEMAS: dict`; the aggregator merges them. Parallel fan-out agents create disjoint files — no merge conflict on the new code, only a single-line addition to `openapi_spec.py`'s import list.
- `docs/api/openapi.json` is the checked-in artefact; `scripts/regen_openapi.py` regenerates it; a test asserts the file matches the dict.

**Tech Stack:** Python 3.11, Starlette, pytest + pytest-asyncio + httpx (existing), `openapi-spec-validator>=0.7` (new dev dep).

**Spec:** `nthlayer/docs/superpowers/specs/2026-06-11-tu04-1-openapi-design.md` (commit `93ee789` in nthlayer).

---

### Task 1: Add `openapi-spec-validator` to nthlayer-core's dev deps

**Files:**
- Modify: `nthlayer-core/pyproject.toml`

- [ ] **Step 1: Confirm clean starting state**

```bash
cd /Users/robfox/Documents/GitHub/nthlayer-ecosystem/nthlayer-core
git status
git log --oneline -3
```
Expected: working tree clean, tip is the most recent nthlayer-core commit.

- [ ] **Step 2: Edit pyproject.toml's dev-deps block**

Open `/Users/robfox/Documents/GitHub/nthlayer-ecosystem/nthlayer-core/pyproject.toml`. Find the block:

```toml
[project.optional-dependencies]
dev = [
    "pytest>=8.2",
    "pytest-asyncio>=0.23",
    "httpx>=0.27",
]
```

Replace with:

```toml
[project.optional-dependencies]
dev = [
    "pytest>=8.2",
    "pytest-asyncio>=0.23",
    "httpx>=0.27",
    "openapi-spec-validator>=0.7",
]
```

- [ ] **Step 3: Run uv sync to update the venv**

```bash
uv sync --extra dev
```
Expected: prints something like `Installed N packages`, no errors. The lockfile (`uv.lock`) updates.

- [ ] **Step 4: Verify the validator is importable**

```bash
uv run python -c "from openapi_spec_validator import validate; print('OK', validate.__module__)"
```
Expected: `OK openapi_spec_validator` (or similar). Confirms the dependency is installed and importable.

- [ ] **Step 5: Commit dep + lockfile**

```bash
git add pyproject.toml uv.lock
git commit -m "$(cat <<'EOF'
build(tu04.1.1): add openapi-spec-validator dev dep

Required by the new tests/test_openapi.py spec validity
test. Pure-Python (no Node toolchain), validates OpenAPI 3.1
schema.

Bead: opensrm-tu04.1.1.
EOF
)"
```
Expected: commit succeeds, working tree clean.

---

### Task 2: Create the `_openapi` subpackage with `paths_health.py`

**Files:**
- Create: `src/nthlayer_core/_openapi/__init__.py`
- Create: `src/nthlayer_core/_openapi/paths_health.py`

- [ ] **Step 1: Create the subpackage marker**

Create `/Users/robfox/Documents/GitHub/nthlayer-ecosystem/nthlayer-core/src/nthlayer_core/_openapi/__init__.py` with this exact content:

```python
"""Per-path-group OpenAPI spec fragments.

Each module exports:
  PATHS: dict[str, dict]  — OpenAPI Path Item objects keyed by path.
  SCHEMAS: dict[str, dict]  — Component schemas this group contributes.

The leading underscore marks this as internal: consumers read the
assembled spec via openapi_spec.OPENAPI, not by importing individual
modules. Module names follow paths_<group>.py for discoverability.
"""
```

- [ ] **Step 2: Create paths_health.py**

Create `/Users/robfox/Documents/GitHub/nthlayer-ecosystem/nthlayer-core/src/nthlayer_core/_openapi/paths_health.py` with this exact content:

```python
"""OpenAPI spec fragment for /health.

The simplest endpoint — used as the worked example in tu04.1.1.
"""
from __future__ import annotations

PATHS: dict[str, dict] = {
    "/health": {
        "get": {
            "summary": "Liveness probe",
            "description": (
                "Returns 200 with a fixed payload as long as the ASGI app is "
                "running. Does not check store connectivity — for that, query "
                "any /verdicts route and rely on the 5xx contract."
            ),
            "operationId": "getHealth",
            "tags": ["meta"],
            "responses": {
                "200": {
                    "description": "Server is running.",
                    "content": {
                        "application/json": {
                            "schema": {
                                "type": "object",
                                "required": ["status"],
                                "properties": {
                                    "status": {"type": "string", "enum": ["ok"]},
                                },
                            },
                            "examples": {
                                "ok": {"value": {"status": "ok"}},
                            },
                        },
                    },
                },
            },
        },
    },
}

SCHEMAS: dict[str, dict] = {}
```

- [ ] **Step 3: Confirm the files exist and import**

```bash
cd /Users/robfox/Documents/GitHub/nthlayer-ecosystem/nthlayer-core
uv run python -c "from nthlayer_core._openapi import paths_health; print(list(paths_health.PATHS.keys()), len(paths_health.SCHEMAS))"
```
Expected: `['/health'] 0`

- [ ] **Step 4: Do NOT commit yet** — the next task wires this into `openapi_spec.py`. Land both together in one commit.

---

### Task 3: Create `openapi_spec.py` — the aggregator

**Files:**
- Create: `src/nthlayer_core/openapi_spec.py`

- [ ] **Step 1: Write the file**

Create `/Users/robfox/Documents/GitHub/nthlayer-ecosystem/nthlayer-core/src/nthlayer_core/openapi_spec.py` with this exact content:

```python
"""OpenAPI 3.1 spec for nthlayer-core's HTTP API.

The OPENAPI dict below is the source of truth. Twin artefacts:

  - Runtime: GET /openapi.json serves OPENAPI as JSON.
  - Static:  docs/api/openapi.json (regenerated by scripts/regen_openapi.py).

Drift detection: tests/test_openapi.py asserts every Starlette route in
server.routes appears in OPENAPI["paths"] and vice versa. Adding a new
route without updating the spec fails CI.

Per-path-group fragments live in nthlayer_core._openapi.paths_*; this
module aggregates them. Phases 2-4 (tu04.1.2/3/4) each add one fragment
module and one import line below.

Bead: opensrm-tu04.1.1 (Phase 1, framework + /health).
"""
from __future__ import annotations

from typing import Any

from nthlayer_core._openapi import paths_health

# Aggregate per-group fragments. New phases append to this list.
_FRAGMENTS = [
    paths_health,
    # paths_verdicts,            # tu04.1.2
    # paths_assessments_cases,   # tu04.1.3
    # paths_other,               # tu04.1.4
]


def _build_paths() -> dict[str, dict[str, Any]]:
    paths: dict[str, dict[str, Any]] = {}
    for fragment in _FRAGMENTS:
        for path, item in fragment.PATHS.items():
            if path in paths:
                raise ValueError(
                    f"Duplicate OpenAPI path entry: {path!r} declared in "
                    f"multiple paths_*.py fragments"
                )
            paths[path] = item
    return paths


def _build_schemas() -> dict[str, dict[str, Any]]:
    # Shared components. ErrorEnvelope is referenced by every 4xx/5xx
    # response across the API.
    schemas: dict[str, dict[str, Any]] = {
        "ErrorEnvelope": {
            "type": "object",
            "required": ["error"],
            "properties": {
                "error": {
                    "type": "string",
                    "description": (
                        "Machine-readable error code. Handlers raise a fixed "
                        "vocabulary of codes documented per-endpoint. The "
                        "internal_error code is used when the store layer "
                        "raises an unexpected exception (opensrm-9uow.1)."
                    ),
                },
                "detail": {
                    "type": "object",
                    "description": (
                        "Structured detail. Shape varies by error code and "
                        "endpoint. Operators read structured server logs for "
                        "the canonical diagnosis; clients use this for "
                        "user-facing messages."
                    ),
                    "additionalProperties": True,
                },
            },
            "additionalProperties": False,
        },
    }
    for fragment in _FRAGMENTS:
        for name, schema in fragment.SCHEMAS.items():
            if name in schemas:
                raise ValueError(
                    f"Duplicate OpenAPI schema component: {name!r} declared "
                    f"in multiple paths_*.py fragments"
                )
            schemas[name] = schema
    return schemas


OPENAPI: dict[str, Any] = {
    "openapi": "3.1.0",
    "info": {
        "title": "NthLayer Core API",
        "version": "1.6.0",
        "description": (
            "Tier-1 reliability-critical HTTP API: verdict store, case "
            "management, manifest catalogue, heartbeats, component state. "
            "Workers and bench access the store exclusively through these "
            "endpoints. Verdicts are immutable after creation; outcome "
            "resolution writes a new verdict referencing the original as "
            "parent."
        ),
    },
    "servers": [
        {"url": "/", "description": "Same-origin"},
    ],
    "paths": _build_paths(),
    "components": {
        "schemas": _build_schemas(),
    },
}


def _spec_path_method_pairs() -> set[tuple[str, str]]:
    """Return {(path, METHOD)} pairs declared in OPENAPI['paths']."""
    out: set[tuple[str, str]] = set()
    for path, item in OPENAPI["paths"].items():
        for method in item.keys():
            # OpenAPI Path Item keys may include non-method keys
            # (parameters, summary, description); guard with a known set.
            if method.lower() in {"get", "post", "put", "delete", "patch", "head", "options"}:
                out.add((path, method.upper()))
    return out


def _route_spec_pairs() -> set[tuple[str, str]]:
    """Return {(path, METHOD)} pairs declared in server.routes.

    Excludes the /openapi.json route itself — that route is added in
    Task 4 and is not documented as part of the API (it IS the API
    documentation).
    """
    from nthlayer_core.server import routes  # noqa: PLC0415 — avoid import cycle at module load
    out: set[tuple[str, str]] = set()
    for r in routes:
        path = getattr(r, "path", None)
        methods = getattr(r, "methods", None) or set()
        if path is None or not methods:
            continue
        if path == "/openapi.json":
            continue
        for m in methods:
            if m == "HEAD":
                # Starlette adds HEAD for free on GET routes — don't
                # require it in the spec.
                continue
            out.add((path, m.upper()))
    return out


def assert_parity() -> None:
    """Raise AssertionError if routes and spec drift.

    Used by tests/test_openapi.py and optionally at server startup. The
    error message lists both sides so the fix is obvious from CI logs.
    """
    spec = _spec_path_method_pairs()
    routes = _route_spec_pairs()
    only_in_routes = routes - spec
    only_in_spec = spec - routes
    if only_in_routes or only_in_spec:
        raise AssertionError(
            "OpenAPI spec / server.routes parity violated.\n"
            f"  In routes but not spec: {sorted(only_in_routes)}\n"
            f"  In spec but not routes: {sorted(only_in_spec)}\n"
            "Add/remove entries in src/nthlayer_core/_openapi/paths_*.py "
            "to restore parity."
        )
```

- [ ] **Step 2: Confirm the module imports and OPENAPI is well-formed**

```bash
cd /Users/robfox/Documents/GitHub/nthlayer-ecosystem/nthlayer-core
uv run python -c "
from nthlayer_core.openapi_spec import OPENAPI, _spec_path_method_pairs
import json
print('openapi version:', OPENAPI['openapi'])
print('info title:', OPENAPI['info']['title'])
print('paths:', list(OPENAPI['paths'].keys()))
print('schemas:', list(OPENAPI['components']['schemas'].keys()))
print('spec pairs:', sorted(_spec_path_method_pairs()))
"
```
Expected:
```
openapi version: 3.1.0
info title: NthLayer Core API
paths: ['/health']
schemas: ['ErrorEnvelope']
spec pairs: [('/health', 'GET')]
```

- [ ] **Step 3: Commit the framework + /health fragment together**

```bash
git add src/nthlayer_core/openapi_spec.py src/nthlayer_core/_openapi/
git commit -m "$(cat <<'EOF'
feat(tu04.1.1): OpenAPI 3.1 framework + /health worked example

src/nthlayer_core/openapi_spec.py is the source of truth:
aggregates per-group fragments from nthlayer_core._openapi.paths_*,
assembles the OPENAPI dict, exposes assert_parity() to catch
route/spec drift. ErrorEnvelope is the shared shape every 4xx/5xx
response references.

Phases 2-4 (tu04.1.2/3/4) plug in by adding one paths_*.py
fragment + one import line. Disjoint files → parallel fan-out
with no merge conflict.

This commit ships:
  - _openapi/__init__.py  (subpackage marker)
  - _openapi/paths_health.py  (PATHS for /health, no schemas)
  - openapi_spec.py  (aggregator + parity check)

Bead: opensrm-tu04.1.1.
Spec: nthlayer/docs/superpowers/specs/2026-06-11-tu04-1-openapi-design.md
EOF
)"
```

---

### Task 4: Add the `GET /openapi.json` route

**Files:**
- Modify: `src/nthlayer_core/server.py`

- [ ] **Step 1: Read the current routes block**

```bash
grep -n "^routes\s*=\|^app = Starlette" src/nthlayer_core/server.py
```
Expected: shows the location of `routes = [...]` and `app = Starlette(routes=routes)`.

- [ ] **Step 2: Add the handler near the `health` handler**

Use the Edit tool. Find:

```python
async def health(request: Request) -> JSONResponse:
    return JSONResponse({"status": "ok"})
```

Replace with:

```python
async def health(request: Request) -> JSONResponse:
    return JSONResponse({"status": "ok"})


async def openapi_json(request: Request) -> JSONResponse:
    """Serve the OpenAPI 3.1 spec.

    Source of truth lives in nthlayer_core.openapi_spec.OPENAPI; the
    checked-in artefact at docs/api/openapi.json is regenerated by
    scripts/regen_openapi.py.
    """
    from nthlayer_core.openapi_spec import OPENAPI
    return JSONResponse(OPENAPI)
```

- [ ] **Step 3: Add the Route entry**

Find the `routes = [` block. The first entry is:

```python
    Route("/health", health, methods=["GET"]),
```

Replace with:

```python
    Route("/health", health, methods=["GET"]),
    Route("/openapi.json", openapi_json, methods=["GET"]),
```

- [ ] **Step 4: Smoke-confirm the server still imports**

```bash
uv run python -c "from nthlayer_core.server import app, routes; print('routes:', len(routes))"
```
Expected: `routes: 30` (was 29; now +1 for /openapi.json).

- [ ] **Step 5: Confirm the parity check passes**

```bash
uv run python -c "from nthlayer_core.openapi_spec import assert_parity; assert_parity(); print('PARITY OK')"
```
Expected:

```
Traceback (most recent call last):
  ...
AssertionError: OpenAPI spec / server.routes parity violated.
  In routes but not spec: [('/assessments', 'GET'), ('/assessments', 'POST'), ...]
  In spec but not routes: []
  Add/remove entries in src/nthlayer_core/_openapi/paths_*.py to restore parity.
```

This **expected failure** is the design working: only `/health` is documented in Phase 1, so all other routes appear as drift. Phases 2-4 will close the gap. The test in Task 6 will use a phase-aware variant that allows the open gap.

- [ ] **Step 6: Commit**

```bash
git add src/nthlayer_core/server.py
git commit -m "$(cat <<'EOF'
feat(tu04.1.1): serve OpenAPI spec at GET /openapi.json

Adds openapi_json handler that returns the OPENAPI dict from
nthlayer_core.openapi_spec. The handler imports lazily to
avoid a circular import (openapi_spec imports server.routes
for the parity check).

Bead: opensrm-tu04.1.1.
EOF
)"
```

---

### Task 5: Create the regen script

**Files:**
- Create: `scripts/regen_openapi.py`
- Create: `docs/api/openapi.json`

- [ ] **Step 1: Confirm `scripts/` and `docs/api/` exist (create if not)**

```bash
ls scripts/ 2>/dev/null && echo SCRIPTS_OK || mkdir scripts
ls docs/api/ 2>/dev/null && echo DOCSAPI_OK || mkdir -p docs/api
```

- [ ] **Step 2: Write the regen script**

Create `/Users/robfox/Documents/GitHub/nthlayer-ecosystem/nthlayer-core/scripts/regen_openapi.py` with this exact content:

```python
"""Regenerate docs/api/openapi.json from the OPENAPI source-of-truth dict.

Run manually after editing any src/nthlayer_core/_openapi/paths_*.py:

    uv run python scripts/regen_openapi.py

The checked-in artefact MUST match what this script produces. A test
(tests/test_openapi.py::test_checked_in_artefact_matches) gates this in
CI — PRs that change the spec must commit the regenerated JSON.

Bead: opensrm-tu04.1.1.
"""
from __future__ import annotations

import json
import pathlib
import sys

from nthlayer_core.openapi_spec import OPENAPI

OUT = pathlib.Path(__file__).resolve().parent.parent / "docs" / "api" / "openapi.json"


def main() -> int:
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(OPENAPI, indent=2, sort_keys=False) + "\n")
    print(f"wrote {OUT.relative_to(OUT.parent.parent.parent)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 3: Run the script to produce the initial artefact**

```bash
uv run python scripts/regen_openapi.py
```
Expected: `wrote docs/api/openapi.json`.

- [ ] **Step 4: Sanity-check the artefact**

```bash
cat docs/api/openapi.json | head -20
ls -l docs/api/openapi.json
```
Expected: 20 lines showing the openapi/info/paths block, file size > 500 bytes.

- [ ] **Step 5: Validate it with openapi-spec-validator**

```bash
uv run python -m openapi_spec_validator docs/api/openapi.json
echo "EXIT=$?"
```
Expected: silent output (or an "OK" message depending on the version), `EXIT=0`.

If non-zero, fix the OPENAPI dict before continuing — likely a schema field has an invalid `type` value or a `$ref` points to something that doesn't exist.

- [ ] **Step 6: Commit**

```bash
git add scripts/regen_openapi.py docs/api/openapi.json
git commit -m "$(cat <<'EOF'
feat(tu04.1.1): scripts/regen_openapi.py + initial openapi.json

Regen script reads OPENAPI source-of-truth dict and writes
docs/api/openapi.json (indent=2, trailing newline). Run
manually after editing any paths_*.py fragment; CI test
asserts the checked-in file matches the dict.

Initial artefact covers /health only — phases 2-4 extend.

Bead: opensrm-tu04.1.1.
EOF
)"
```

---

### Task 6: Write the four OpenAPI tests

**Files:**
- Create: `tests/test_openapi.py`

This task uses TDD shape: write each test, run it, watch it pass against the (already-implemented) framework. Some tests fail right now (parity has a known open gap until Phases 2-4 land) — those use `xfail(strict=True)` so the failure is expected and tracked.

- [ ] **Step 1: Write the test file**

Create `/Users/robfox/Documents/GitHub/nthlayer-ecosystem/nthlayer-core/tests/test_openapi.py` with this exact content:

```python
"""Tests for the OpenAPI 3.1 spec.

Four invariants:
  1. Routes and spec are in sync (parity). XFAIL until tu04.1.2/3/4 land.
  2. The spec is a valid OpenAPI 3.1 document.
  3. The checked-in docs/api/openapi.json matches the OPENAPI dict.
  4. GET /openapi.json serves the dict.

Bead: opensrm-tu04.1.1.
"""
from __future__ import annotations

import json
import pathlib

import pytest
from openapi_spec_validator import validate
from starlette.testclient import TestClient

from nthlayer_core.openapi_spec import (
    OPENAPI,
    _route_spec_pairs,
    _spec_path_method_pairs,
)
from nthlayer_core.server import app

ARTEFACT_PATH = (
    pathlib.Path(__file__).resolve().parent.parent / "docs" / "api" / "openapi.json"
)


@pytest.mark.xfail(
    strict=True,
    reason=(
        "Phase 1 (tu04.1.1) documents only /health. Routes for verdicts, "
        "assessments, cases, change-freezes, heartbeats, manifests, monitoring, "
        "suppressions, component-state remain undocumented until tu04.1.2/3/4 "
        "close. This xfail flips to xpass — and the test becomes load-bearing — "
        "when tu04.1 closes."
    ),
)
def test_route_parity() -> None:
    spec = _spec_path_method_pairs()
    routes = _route_spec_pairs()
    assert spec == routes, (
        f"In routes but not spec: {sorted(routes - spec)}\n"
        f"In spec but not routes: {sorted(spec - routes)}"
    )


def test_spec_is_valid_openapi_31() -> None:
    """Run openapi-spec-validator against the in-memory OPENAPI dict."""
    # validate() raises on invalid spec; passes through on valid.
    validate(OPENAPI)


def test_checked_in_artefact_matches() -> None:
    """docs/api/openapi.json must match what the dict produces.

    If this fails: `uv run python scripts/regen_openapi.py` and commit.
    """
    assert ARTEFACT_PATH.exists(), (
        f"Missing {ARTEFACT_PATH.relative_to(ARTEFACT_PATH.parent.parent.parent)}. "
        "Run scripts/regen_openapi.py."
    )
    on_disk = json.loads(ARTEFACT_PATH.read_text())
    assert on_disk == OPENAPI, (
        "docs/api/openapi.json is stale. "
        "Run scripts/regen_openapi.py and commit the result."
    )


def test_openapi_endpoint_served() -> None:
    """GET /openapi.json returns the OPENAPI dict."""
    with TestClient(app) as client:
        response = client.get("/openapi.json")
    assert response.status_code == 200
    assert response.json() == OPENAPI
```

- [ ] **Step 2: Run each test individually**

```bash
uv run pytest tests/test_openapi.py::test_spec_is_valid_openapi_31 -v
```
Expected: PASS.

```bash
uv run pytest tests/test_openapi.py::test_checked_in_artefact_matches -v
```
Expected: PASS.

```bash
uv run pytest tests/test_openapi.py::test_openapi_endpoint_served -v
```
Expected: PASS.

```bash
uv run pytest tests/test_openapi.py::test_route_parity -v
```
Expected: XFAIL (expected failure recorded; not a test suite failure). Output includes `expected failure` or `XFAIL`.

- [ ] **Step 3: Run the full openapi test file**

```bash
uv run pytest tests/test_openapi.py -v
```
Expected: `3 passed, 1 xfailed in N.NNs`. No errors, no FAILs.

- [ ] **Step 4: Run the full nthlayer-core test suite to confirm no regression**

```bash
uv run pytest -q
```
Expected: all existing tests still pass; new file adds 3 passing + 1 xfailed.

- [ ] **Step 5: Run ruff to confirm no lint regressions**

```bash
uv run ruff check src/ tests/ scripts/
```
Expected: `All checks passed!` or similar.

- [ ] **Step 6: Commit**

```bash
git add tests/test_openapi.py
git commit -m "$(cat <<'EOF'
test(tu04.1.1): four OpenAPI invariants

  - test_route_parity (xfail until tu04.1.2-4 land): every
    Starlette route appears in OPENAPI['paths'] and vice
    versa.
  - test_spec_is_valid_openapi_31: openapi-spec-validator
    accepts the dict.
  - test_checked_in_artefact_matches: docs/api/openapi.json
    must match the dict (regen script enforces sync).
  - test_openapi_endpoint_served: GET /openapi.json returns
    the dict.

xfail flips to xpass when tu04.1 closes (after .1.2/.1.3/.1.4
land their fragments and the parity gap closes).

Bead: opensrm-tu04.1.1.
EOF
)"
```

---

### Task 7: Push and confirm CI green

**Files:** none.

- [ ] **Step 1: Confirm clean local state and 6 new commits**

```bash
git status
git log --oneline -7
```
Expected: working tree clean. Last 6 commits:
- test(tu04.1.1): four OpenAPI invariants
- feat(tu04.1.1): scripts/regen_openapi.py + initial openapi.json
- feat(tu04.1.1): serve OpenAPI spec at GET /openapi.json
- feat(tu04.1.1): OpenAPI 3.1 framework + /health worked example
- build(tu04.1.1): add openapi-spec-validator dev dep
- (prior tip)

- [ ] **Step 2: Confirm remote name**

```bash
git remote -v
```
Expected: shows the canonical remote (likely `origin` for nthlayer-core, per CI's "ahead of origin/main" earlier).

- [ ] **Step 3: Push**

```bash
git push origin main
```
Expected: push succeeds. If the branch is ahead by more commits than the new 5, that's fine — pre-existing local commits go up too.

- [ ] **Step 4: Watch CI**

```bash
sleep 6
gh run list --workflow=ci.yml --limit 3 --json databaseId,status,conclusion,headSha
```
Capture the most recent run's databaseId, then:

```bash
gh run watch <RUN_ID> --exit-status --interval 10
```
Expected: green. CI matrix runs Python 3.11 + 3.12; both must pass.

- [ ] **Step 5: Record the green run number for the bead-close note**

```bash
gh run list --limit 1 --json databaseId --jq '.[0].databaseId'
```

---

### Task 8: Close the bead

**Files:** none.

- [ ] **Step 1: Capture HEAD SHA**

```bash
cd /Users/robfox/Documents/GitHub/nthlayer-ecosystem/nthlayer-core
git rev-parse --short=7 HEAD
```

- [ ] **Step 2: Close**

```bash
cd /Users/robfox/Documents/GitHub/nthlayer-ecosystem/opensrm
bd close opensrm-tu04.1.1 --reason "Framework landed in nthlayer-core@<HEAD-SHA>. Green CI on run <RUN-NUMBER>. /health documented; 3/4 tests pass + 1 xfail (parity — flips to xpass when tu04.1.2/3/4 close). Unblocks tu04.1.2, tu04.1.3, tu04.1.4."
```
Substitute `<HEAD-SHA>` and `<RUN-NUMBER>` from prior tasks.

- [ ] **Step 3: Verify the three siblings are now READY**

```bash
bd ready --json | python3 -c "
import json, sys
items = json.load(sys.stdin)
items = items if isinstance(items, list) else items.get('issues', [])
for i in items:
    if 'tu04.1.' in i.get('id', ''):
        print(i.get('id'), '-', i.get('title', '')[:60])
"
```
Expected: `tu04.1.2`, `tu04.1.3`, `tu04.1.4` all listed. `tu04.1.1` absent (closed).

---

## Self-Review

**Spec coverage:**
- ✓ `openapi_spec.py` aggregator with OPENAPI dict, parity helpers, assert_parity() — Tasks 2-3.
- ✓ Per-path-group fragments under `_openapi/` — Task 2 lays the subpackage.
- ✓ Shared `ErrorEnvelope` component — Task 3.
- ✓ GET `/openapi.json` route — Task 4.
- ✓ `scripts/regen_openapi.py` + `docs/api/openapi.json` checked in — Task 5.
- ✓ Four tests (parity, validity, artefact-match, endpoint-served) — Task 6.
- ✓ `openapi-spec-validator` added as dev dep — Task 1.
- ✓ CI wiring: existing `uv run pytest` step picks up `test_openapi.py` automatically — no workflow edits needed.
- ✓ `/health` worked endpoint — Task 2 (paths_health.py).
- ✓ Out of scope: Swagger UI, Pydantic models, Spectral — none introduced.

**Placeholder scan:** No TBD/TODO. Each step has exact code or exact commands. Task 4 step 5 explicitly shows the expected AssertionError as the design working — not a placeholder, a documented expected state.

**Type consistency:** `_FRAGMENTS` list naming, `PATHS`/`SCHEMAS` dict names, `assert_parity()` function name appear consistently across openapi_spec.py, paths_health.py, the regen script, and the test file. Bead ID `tu04.1.1` is consistent in every commit message and docstring.

**Phase-2-and-beyond hook:** the architecture (per-group fragment module + explicit import list) was designed for parallel fan-out. Phases 2/3/4 each add one file under `_openapi/` and one line in `_FRAGMENTS`. The orchestrator merges the four-line addition; agents never touch the same file beyond that.

---

Plan complete and saved to `nthlayer/docs/superpowers/plans/2026-06-11-tu04-1-1-openapi-infra.md`. Two execution options:

1. **Subagent-Driven (recommended)** — fresh subagent per task, two-stage review between tasks.
2. **Inline Execution** — execute tasks in this session using executing-plans, batch with checkpoints.

Which approach?
