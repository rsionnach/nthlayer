# Mimir Client Move + Explanation Engine Design

**Date:** 2026-04-10
**Beads:** nthlayer-2xe, nthlayer-hmj
**Status:** Approved

## Overview

Two beads completing the post-Purify Generate cleanup:
1. Move MimirRulerProvider from providers/ to clients/ in nthlayer-common (taxonomy fix)
2. Build ExplanationEngine in nthlayer-observe, shared data model in nthlayer-common, remove dead stub from generate

---

## Bead nthlayer-2xe: Move MimirRulerProvider to clients/

### Problem

MimirRulerProvider is a standalone HTTP client in `nthlayer_common/providers/mimir.py` but it does NOT implement the `Provider` protocol. It's deliberately excluded from `providers/__init__.py.__all__`. This confuses the taxonomy: providers/ should contain only `Provider` protocol implementers (Prometheus, Grafana, PagerDuty).

### Design

**Move:** `nthlayer_common/providers/mimir.py` → `nthlayer_common/clients/mimir.py`

**Refactor to extend BaseHTTPClient:**
- Current: uses raw `httpx.AsyncClient` directly (no retry, no circuit breaker)
- New: extends `BaseHTTPClient` (gains per-instance retry via tenacity + circuit breaker)
- Auth wired through `_headers()` override — tenant ID (`X-Scope-OrgID`), API key (`Bearer` token), basic auth, all applied consistently to every request

**Exports retained:** `MimirRulerProvider`, `MimirRulerError`, `RulerPushResult`, `DEFAULT_USER_AGENT`

**Backward compat:** `nthlayer_common/providers/mimir.py` becomes a re-export shim:
```python
from nthlayer_common.clients.mimir import (  # noqa: F401
    DEFAULT_USER_AGENT, MimirRulerError, MimirRulerProvider, RulerPushResult,
)
```
The nthlayer re-export shim (`nthlayer/providers/mimir.py`) is unchanged — it imports from `nthlayer_common.providers.mimir` which re-exports from the new location.

**Taxonomy documentation in CLAUDE.md:**
- `providers/` = `Provider` protocol implementers: async health_check, plan, apply, drift. Managed declarative resources with idempotent state synchronization.
- `clients/` = Standalone HTTP clients with resilience: `BaseHTTPClient` subclasses with retry + circuit breaker. Imperative operations (push, delete, list, send).

### Files Changed

| File | Change |
|------|--------|
| `nthlayer-common/src/nthlayer_common/clients/mimir.py` | **New** — MimirRulerProvider(BaseHTTPClient) |
| `nthlayer-common/src/nthlayer_common/clients/__init__.py` | Add MimirRulerProvider exports |
| `nthlayer-common/src/nthlayer_common/providers/mimir.py` | Becomes re-export shim |
| `nthlayer-common/CLAUDE.md` | Document taxonomy |
| `nthlayer/tests/test_mimir_provider.py` | Verify BaseHTTPClient behavior |

### Acceptance Criteria

1. `from nthlayer_common.clients.mimir import MimirRulerProvider` works
2. `from nthlayer_common.providers.mimir import MimirRulerProvider` still works (backward compat)
3. `isinstance(MimirRulerProvider(...), BaseHTTPClient)` is True
4. Auth headers applied via `_headers()` override
5. All 18 existing tests pass
6. New test verifies retry/circuit breaker config is applied

---

## Bead nthlayer-hmj: Restore alerts explain

### Problem

The `nthlayer alerts explain` command was stubbed out in Phase 1 when ExplanationEngine was deleted from generate. Budget explanations (human-readable context about why an error budget is burning, with causes and recommended actions) are useful for incident response and status reporting.

### Design

Three components across three repos:

#### nthlayer-common: Shared data model + formatter

**New file:** `nthlayer_common/explanation.py`

```python
@dataclass
class BudgetExplanation:
    service: str
    slo_name: str
    headline: str              # One-line summary, e.g. "availability: 73% budget remaining (WARNING)"
    body: str                  # Detailed narrative with budget math
    causes: list[str]          # Contributing factors
    recommended_actions: list[str]  # What to do next
    severity: str              # "info" | "warning" | "critical"

def format_explanation(explanation: BudgetExplanation, fmt: str = "table") -> str:
    """Pure formatter — table, json, or markdown output."""
```

This gives nthlayer-respond's communication agent access to the same formatting for incident updates.

#### nthlayer-observe: Engine + CLI

**New file:** `nthlayer_observe/explanation.py`

```python
class ExplanationEngine:
    def explain_service(
        self,
        service: str,
        store: AssessmentStore,
        slo_filter: str | None = None,
    ) -> list[BudgetExplanation]:
        """Build explanations from latest slo_state assessments.

        For each SLO:
        - Headline from status + percent_consumed
        - Body from budget math (burned_minutes / total_budget_minutes)
        - Enriched with drift assessment if available (pattern, projection)
        - Recommended actions based on severity + tier
        """
```

No LLM. No judgment. Pure arithmetic on assessment data.

**CLI subcommand:** `nthlayer-observe explain`

```
nthlayer-observe explain --store assessments.db [--service SERVICE] [--slo SLO] [--format table|json|markdown]
```

Reads from assessment store, runs ExplanationEngine, formats output via nthlayer-common's `format_explanation()`.

#### nthlayer (generate): Cleanup

- Delete `alerts_explain_command` stub from `cli/alerts.py`
- Remove `explain` from the alerts subparser registration in `cli/alerts.py`
- Remove the 3 stub tests from `test_cli_alerts.py`
- Update `handle_alerts_command` dispatch to remove explain branch
- CLAUDE.md: note explain command now lives in `nthlayer-observe explain`

### Data Flow

```
nthlayer-observe explain --service payment-api --store assessments.db
  → AssessmentStore.query(service="payment-api", type="slo_state")
  → ExplanationEngine.explain_service()
    → for each SLO assessment:
        headline = f"{slo_name}: {percent_consumed:.0f}% consumed ({status})"
        body = budget math narrative
        causes = inferred from status + drift pattern (if available)
        actions = tier-aware recommendations
    → BudgetExplanation per SLO
  → format_explanation() (from nthlayer_common)
  → stdout
```

### Explanation Content

**Headline patterns:**
- HEALTHY: `"availability: 12% consumed — within budget (HEALTHY)"`
- WARNING: `"availability: 73% consumed — approaching threshold (WARNING)"`
- CRITICAL: `"availability: 92% consumed — near exhaustion (CRITICAL)"`
- EXHAUSTED: `"availability: 107% consumed — budget exhausted (EXHAUSTED)"`

**Body includes:** budget window, total minutes, consumed minutes, remaining minutes, current SLI value vs target.

**Causes (derived from assessment data, not LLM):**
- If drift assessment exists with GRADUAL_DECLINE: "Error rate has been gradually increasing over the past {window}"
- If drift assessment exists with STEP_CHANGE_DOWN: "A step change was detected, likely from a recent deployment"
- If percent_consumed > 80 and status changed recently: "Budget consumption accelerated in the last collection window"
- If no drift data: "Budget consumption rate based on current SLI value vs target"

**Recommended actions (tier-aware):**
- CRITICAL tier + WARNING status: "Investigate before next deployment"
- CRITICAL tier + CRITICAL status: "Consider freezing deployments until budget recovers"
- Any tier + EXHAUSTED: "Deployment gate will block — resolve underlying issue"
- Standard/Low tier + WARNING: "Monitor trend — no immediate action required"

### Files Changed

| File | Change |
|------|--------|
| `nthlayer-common/src/nthlayer_common/explanation.py` | **New** — BudgetExplanation dataclass + format_explanation() |
| `nthlayer-common/tests/test_explanation.py` | **New** — formatter tests |
| `nthlayer-observe/src/nthlayer_observe/explanation.py` | **New** — ExplanationEngine |
| `nthlayer-observe/src/nthlayer_observe/cli.py` | Add `explain` subcommand |
| `nthlayer-observe/tests/test_explanation.py` | **New** — engine tests |
| `nthlayer/src/nthlayer/cli/alerts.py` | Delete explain stub + subparser |
| `nthlayer/tests/test_cli_alerts.py` | Delete 3 stub tests |
| CLAUDE.md (all 3 repos) | Updated |

### Acceptance Criteria

1. `nthlayer-observe explain --store assessments.db --service payment-api` produces human-readable budget explanations
2. `--format json` produces valid JSON array of BudgetExplanation objects
3. `--format markdown` produces markdown with headlines and details
4. `--slo` filter works (only explains named SLO)
5. Drift enrichment works when drift assessments exist in the store
6. `from nthlayer_common.explanation import BudgetExplanation, format_explanation` works (for respond)
7. `nthlayer alerts explain` no longer exists (stub removed from generate)
8. All tests pass across all 3 repos

---

## Dependency Chain

```
nthlayer-common (explanation.py) — release to PyPI first
  → nthlayer-observe (ExplanationEngine + CLI) — depends on common
  → nthlayer (cleanup — remove stub) — independent, can go in parallel
```
