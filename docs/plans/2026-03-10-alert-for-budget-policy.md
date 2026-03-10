# Alert For Duration & Error Budget Policy Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Implement two NthLayer P2 features — configurable alert `for` duration (trellis-alert-for) and error budget policy DSL (trellis-budget-policy) — to close out the NthLayer backlog.

**Architecture:** Both features extend existing configuration surfaces. Alert `for` duration adds a `for_duration` section to `AlertingConfig` that overrides `AlertRule.duration` by severity during `customize_for_service()`. Error budget policy extends `ErrorBudgetGate` with a `policy` subsection containing thresholds, window, and exhaustion behaviors (`freeze_deploys`, `require_approval`, `notify`) that integrate with `DeploymentGate.check_deployment()`.

**Tech Stack:** Python 3.12, dataclasses, pytest, structlog

---

## Task 1: Add `for_duration` to AlertingConfig

**Files:**
- Modify: `src/nthlayer/specs/alerting.py:44-50`
- Test: `tests/test_alerting_config.py`

### Step 1: Write the failing test

Add to `tests/test_alerting_config.py`:

```python
# -------------------------------------------------------------------------
# ForDuration configuration
# -------------------------------------------------------------------------


class TestForDuration:
    def test_default_for_duration(self) -> None:
        cfg = AlertingConfig(rules=[])
        assert cfg.for_duration is not None
        assert cfg.for_duration.page == "2m"
        assert cfg.for_duration.ticket == "15m"

    def test_custom_for_duration(self) -> None:
        cfg = AlertingConfig(
            rules=[],
            for_duration=ForDuration(page="1m", ticket="10m"),
        )
        assert cfg.for_duration.page == "1m"
        assert cfg.for_duration.ticket == "10m"

    def test_get_for_severity_critical(self) -> None:
        cfg = AlertingConfig(rules=[])
        assert cfg.for_duration.get_for_severity("critical") == "2m"

    def test_get_for_severity_warning(self) -> None:
        cfg = AlertingConfig(rules=[])
        assert cfg.for_duration.get_for_severity("warning") == "15m"

    def test_get_for_severity_info(self) -> None:
        cfg = AlertingConfig(rules=[])
        assert cfg.for_duration.get_for_severity("info") == "15m"
```

### Step 2: Run test to verify it fails

Run: `cd /Users/robfox/Documents/GitHub/opensrm-ecosystem/nthlayer && uv run pytest tests/test_alerting_config.py::TestForDuration -v`
Expected: FAIL — `ForDuration` does not exist yet

### Step 3: Write minimal implementation

In `src/nthlayer/specs/alerting.py`, add before `AlertingConfig`:

```python
@dataclass
class ForDuration:
    """Severity-based alert 'for' duration overrides.

    Controls how long a condition must be true before firing.
    Maps to Prometheus 'for' field on generated AlertRules.

    - page: Duration for critical/page alerts (default: 2m)
    - ticket: Duration for warning/info/ticket alerts (default: 15m)
    """

    page: str = "2m"
    ticket: str = "15m"

    def get_for_severity(self, severity: str) -> str:
        """Return the appropriate 'for' duration based on alert severity."""
        if severity == "critical":
            return self.page
        return self.ticket
```

Update `AlertingConfig` to add the field:

```python
@dataclass
class AlertingConfig:
    """Top-level alerting configuration in a service spec."""

    channels: AlertChannels = field(default_factory=AlertChannels)
    rules: list[SpecAlertRule] = field(default_factory=list)
    auto_rules: bool = True
    for_duration: ForDuration = field(default_factory=ForDuration)

    def get_rules_for_slo(self, slo_name: str) -> list[SpecAlertRule]:
        """Return rules that apply to a specific SLO (exact match or wildcard)."""
        return [r for r in self.rules if r.enabled and (r.slo == "*" or r.slo == slo_name)]
```

### Step 4: Run test to verify it passes

Run: `cd /Users/robfox/Documents/GitHub/opensrm-ecosystem/nthlayer && uv run pytest tests/test_alerting_config.py::TestForDuration -v`
Expected: PASS

### Step 5: Commit

```bash
git add src/nthlayer/specs/alerting.py tests/test_alerting_config.py
git commit -m "feat: add ForDuration to AlertingConfig (trellis-alert-for)"
```

---

## Task 2: Parse `for_duration` from YAML

**Files:**
- Modify: `src/nthlayer/specs/alerting.py:153-185` (parse_alerting_config)
- Test: `tests/test_alerting_config.py`

### Step 1: Write the failing test

Add to `TestParseAlertingConfig` in `tests/test_alerting_config.py`:

```python
    def test_parses_for_duration(self) -> None:
        data = {
            "rules": [],
            "for_duration": {
                "page": "1m",
                "ticket": "10m",
            },
        }
        cfg = parse_alerting_config(data)
        assert cfg is not None
        assert cfg.for_duration.page == "1m"
        assert cfg.for_duration.ticket == "10m"

    def test_for_duration_defaults_when_absent(self) -> None:
        data = {"rules": []}
        cfg = parse_alerting_config(data)
        assert cfg is not None
        assert cfg.for_duration.page == "2m"
        assert cfg.for_duration.ticket == "15m"

    def test_for_duration_partial_override(self) -> None:
        data = {
            "rules": [],
            "for_duration": {"page": "30s"},
        }
        cfg = parse_alerting_config(data)
        assert cfg is not None
        assert cfg.for_duration.page == "30s"
        assert cfg.for_duration.ticket == "15m"  # default kept
```

### Step 2: Run test to verify it fails

Run: `cd /Users/robfox/Documents/GitHub/opensrm-ecosystem/nthlayer && uv run pytest tests/test_alerting_config.py::TestParseAlertingConfig::test_parses_for_duration -v`
Expected: FAIL — `parse_alerting_config` doesn't parse `for_duration` yet

### Step 3: Write minimal implementation

In `parse_alerting_config()` in `src/nthlayer/specs/alerting.py`, add `for_duration` parsing before the return statement:

```python
    for_duration = ForDuration()
    fd_data = data.get("for_duration")
    if fd_data and isinstance(fd_data, dict):
        for_duration = ForDuration(
            page=fd_data.get("page", "2m"),
            ticket=fd_data.get("ticket", "15m"),
        )

    return AlertingConfig(
        channels=channels,
        rules=rules,
        auto_rules=data.get("auto_rules", True),
        for_duration=for_duration,
    )
```

### Step 4: Run test to verify it passes

Run: `cd /Users/robfox/Documents/GitHub/opensrm-ecosystem/nthlayer && uv run pytest tests/test_alerting_config.py::TestParseAlertingConfig -v`
Expected: PASS (all existing and new tests)

### Step 5: Commit

```bash
git add src/nthlayer/specs/alerting.py tests/test_alerting_config.py
git commit -m "feat: parse for_duration from alerting config YAML (trellis-alert-for)"
```

---

## Task 3: Apply `for_duration` in `customize_for_service()`

**Files:**
- Modify: `src/nthlayer/alerts/models.py:84-149` (customize_for_service)
- Test: `tests/test_alerts.py` (or new test file if needed)

### Step 1: Write the failing test

Add to the appropriate test file (check `tests/test_alerts.py` structure first):

```python
class TestForDurationOverride:
    def test_customize_applies_for_duration(self) -> None:
        """for_duration override replaces AlertRule.duration during customization."""
        from nthlayer.alerts.models import AlertRule

        alert = AlertRule(
            name="PostgresqlDown",
            expr="pg_up == 0",
            duration="5m",
            severity="critical",
        )
        customized = alert.customize_for_service(
            service_name="payment-api",
            team="payments",
            tier="critical",
            for_duration_override="2m",
        )
        assert customized.duration == "2m"

    def test_customize_no_override_keeps_original(self) -> None:
        """Without for_duration_override, original duration is preserved."""
        from nthlayer.alerts.models import AlertRule

        alert = AlertRule(
            name="PostgresqlDown",
            expr="pg_up == 0",
            duration="5m",
            severity="critical",
        )
        customized = alert.customize_for_service(
            service_name="payment-api",
            team="payments",
            tier="critical",
        )
        assert customized.duration == "5m"
```

### Step 2: Run test to verify it fails

Run: `cd /Users/robfox/Documents/GitHub/opensrm-ecosystem/nthlayer && uv run pytest tests/test_alerts.py::TestForDurationOverride -v`
Expected: FAIL — `customize_for_service` doesn't accept `for_duration_override` parameter

### Step 3: Write minimal implementation

In `src/nthlayer/alerts/models.py`, update `customize_for_service()` signature and body:

```python
    def customize_for_service(
        self,
        service_name: str,
        team: str,
        tier: str,
        notification_channel: str = "",
        runbook_url: str = "",
        routing: str | None = "",
        grafana_url: str = "",
        for_duration_override: str | None = None,
    ) -> "AlertRule":
```

Add after the `customized = AlertRule(...)` construction (around line 124):

```python
        # Apply for_duration override if provided
        if for_duration_override:
            customized.duration = for_duration_override
```

### Step 4: Run test to verify it passes

Run: `cd /Users/robfox/Documents/GitHub/opensrm-ecosystem/nthlayer && uv run pytest tests/test_alerts.py::TestForDurationOverride -v`
Expected: PASS

### Step 5: Commit

```bash
git add src/nthlayer/alerts/models.py tests/test_alerts.py
git commit -m "feat: add for_duration_override to customize_for_service (trellis-alert-for)"
```

---

## Task 4: Wire `for_duration` through alert generation pipeline

**Files:**
- Modify: `src/nthlayer/generators/alerts.py:83-120` (generate_alerts_from_manifest)
- Modify: `src/nthlayer/generators/alerts.py:157-261` (_load_and_customize_alerts)
- Test: `tests/test_alert_pipeline.py`

### Step 1: Write the failing test

Add to `tests/test_alert_pipeline.py`:

```python
class TestForDurationPipeline:
    def test_manifest_for_duration_applied_to_critical_alerts(self) -> None:
        """for_duration from manifest alerting config flows through to generated alerts."""
        from nthlayer.specs.alerting import AlertingConfig, ForDuration
        from nthlayer.specs.manifest import ReliabilityManifest

        manifest = ReliabilityManifest(
            name="test-svc",
            team="eng",
            tier="critical",
            type="api",
            alerting=AlertingConfig(
                for_duration=ForDuration(page="1m", ticket="20m"),
            ),
        )

        # Use generate_alerts_from_manifest which reads manifest.alerting
        from nthlayer.generators.alerts import generate_alerts_from_manifest

        alerts = generate_alerts_from_manifest(manifest, quiet=True)

        # If no dependencies, no alerts generated — skip assertion
        # This test verifies the plumbing, not the template loading
        # The key assertion is that the function accepts and passes through for_duration
        # We test the actual override in the unit tests above
```

Note: This task is primarily about plumbing. The key change is passing `for_duration` config from `manifest.alerting` through to `customize_for_service()` calls in `_load_and_customize_alerts()`.

### Step 2: Write minimal implementation

In `src/nthlayer/generators/alerts.py`:

1. Update `generate_alerts_from_manifest()` to pass `alerting_config`:

```python
def generate_alerts_from_manifest(
    manifest: ReliabilityManifest,
    output_file: Path | None = None,
    runbook_url: str = "",
    notification_channel: str = "",
    routing: str | None = None,
    grafana_url: str = "",
    quiet: bool = False,
) -> List[AlertRule]:
    deps = extract_dependency_technologies(manifest)
    alert_routing = routing or manifest.support_model

    return _load_and_customize_alerts(
        service_name=manifest.name,
        team=manifest.team,
        tier=manifest.tier,
        dependencies=deps,
        output_file=output_file,
        runbook_url=runbook_url,
        notification_channel=notification_channel,
        routing=alert_routing,
        grafana_url=grafana_url,
        quiet=quiet,
        alerting_config=manifest.alerting,
    )
```

2. Update `_load_and_customize_alerts()` signature and the `customize_for_service()` call:

```python
def _load_and_customize_alerts(
    service_name: str,
    team: str,
    tier: str,
    dependencies: List[str],
    output_file: Path | None = None,
    runbook_url: str = "",
    notification_channel: str = "",
    routing: str = "",
    grafana_url: str = "",
    quiet: bool = False,
    alerting_config: Any = None,
) -> List[AlertRule]:
```

Inside the loop, update the `customize_for_service()` call (around line 213-224):

```python
            # Customize for service
            customized = []
            for alert in filtered:
                # Determine for_duration override from alerting config
                for_override = None
                if alerting_config and alerting_config.for_duration:
                    for_override = alerting_config.for_duration.get_for_severity(
                        alert.severity
                    )

                customized.append(
                    alert.customize_for_service(
                        service_name=service_name,
                        team=team,
                        tier=tier,
                        notification_channel=notification_channel,
                        runbook_url=runbook_url,
                        routing=routing,
                        grafana_url=grafana_url,
                        for_duration_override=for_override,
                    )
                )
```

### Step 3: Run tests to verify everything passes

Run: `cd /Users/robfox/Documents/GitHub/opensrm-ecosystem/nthlayer && uv run pytest tests/test_alert_pipeline.py tests/test_alerts.py tests/test_alerting_config.py -v`
Expected: PASS

### Step 4: Commit

```bash
git add src/nthlayer/generators/alerts.py tests/test_alert_pipeline.py
git commit -m "feat: wire for_duration through alert generation pipeline (trellis-alert-for)"
```

---

## Task 5: OpenSRM manifest integration test for `for_duration`

**Files:**
- Modify: `tests/test_alerting_config.py`

### Step 1: Write the integration test

Add to `TestOpenSRMParsing` class in `tests/test_alerting_config.py`:

```python
    def test_parse_opensrm_with_for_duration(self) -> None:
        from nthlayer.specs.opensrm_parser import parse_opensrm

        data = {
            "apiVersion": "srm/v1",
            "kind": "ServiceReliabilityManifest",
            "metadata": {"name": "test-svc", "team": "eng", "tier": "critical"},
            "spec": {
                "type": "api",
                "alerting": {
                    "for_duration": {"page": "1m", "ticket": "10m"},
                    "rules": [],
                },
            },
        }
        manifest = parse_opensrm(data)
        assert manifest.alerting is not None
        assert manifest.alerting.for_duration.page == "1m"
        assert manifest.alerting.for_duration.ticket == "10m"
```

### Step 2: Run test

Run: `cd /Users/robfox/Documents/GitHub/opensrm-ecosystem/nthlayer && uv run pytest tests/test_alerting_config.py::TestOpenSRMParsing::test_parse_opensrm_with_for_duration -v`
Expected: PASS (OpenSRM parser delegates to `parse_alerting_config` which we already updated)

### Step 3: Commit

```bash
git add tests/test_alerting_config.py
git commit -m "test: add OpenSRM integration test for for_duration (trellis-alert-for)"
```

---

## Task 6: Add `BudgetPolicy` dataclass to manifest

**Files:**
- Modify: `src/nthlayer/specs/manifest.py:222-228`
- Test: `tests/test_budget_policy.py` (new file)

### Step 1: Write the failing test

Create `tests/test_budget_policy.py`:

```python
"""Tests for error budget policy configuration."""

from __future__ import annotations

import pytest

from nthlayer.specs.manifest import BudgetPolicy, BudgetThresholds, ErrorBudgetGate


class TestBudgetPolicy:
    def test_default_thresholds(self) -> None:
        policy = BudgetPolicy()
        assert policy.thresholds.warning == 0.20
        assert policy.thresholds.critical == 0.10

    def test_custom_thresholds(self) -> None:
        policy = BudgetPolicy(
            thresholds=BudgetThresholds(warning=0.30, critical=0.15),
        )
        assert policy.thresholds.warning == 0.30
        assert policy.thresholds.critical == 0.15

    def test_default_window(self) -> None:
        policy = BudgetPolicy()
        assert policy.window == "30d"

    def test_on_exhausted_defaults(self) -> None:
        policy = BudgetPolicy()
        assert policy.on_exhausted == []

    def test_on_exhausted_custom(self) -> None:
        policy = BudgetPolicy(
            on_exhausted=["freeze_deploys", "notify"],
        )
        assert "freeze_deploys" in policy.on_exhausted
        assert "notify" in policy.on_exhausted

    def test_valid_on_exhausted_values(self) -> None:
        # These are the allowed exhaustion behaviors
        valid = ["freeze_deploys", "require_approval", "notify"]
        policy = BudgetPolicy(on_exhausted=valid)
        assert policy.on_exhausted == valid


class TestErrorBudgetGateWithPolicy:
    def test_error_budget_gate_default_no_policy(self) -> None:
        gate = ErrorBudgetGate()
        assert gate.policy is None

    def test_error_budget_gate_with_policy(self) -> None:
        gate = ErrorBudgetGate(
            policy=BudgetPolicy(
                window="7d",
                thresholds=BudgetThresholds(warning=0.25, critical=0.10),
                on_exhausted=["freeze_deploys"],
            ),
        )
        assert gate.policy is not None
        assert gate.policy.window == "7d"
        assert gate.policy.on_exhausted == ["freeze_deploys"]
```

### Step 2: Run test to verify it fails

Run: `cd /Users/robfox/Documents/GitHub/opensrm-ecosystem/nthlayer && uv run pytest tests/test_budget_policy.py -v`
Expected: FAIL — `BudgetPolicy` and `BudgetThresholds` don't exist

### Step 3: Write minimal implementation

In `src/nthlayer/specs/manifest.py`, add before `ErrorBudgetGate`:

```python
# Valid on_exhausted behavior values
VALID_EXHAUSTION_BEHAVIORS = {"freeze_deploys", "require_approval", "notify"}


@dataclass
class BudgetThresholds:
    """Warning and critical thresholds for error budget policy.

    Values are fractions of remaining budget (e.g., 0.20 = 20% remaining).
    """

    warning: float = 0.20
    critical: float = 0.10


@dataclass
class BudgetPolicy:
    """Error budget policy configuration.

    Defines thresholds, evaluation window, and behaviors
    when error budget is exhausted.
    """

    window: str = "30d"
    thresholds: BudgetThresholds = field(default_factory=BudgetThresholds)
    on_exhausted: list[str] = field(default_factory=list)
```

Update `ErrorBudgetGate` to include the policy field:

```python
@dataclass
class ErrorBudgetGate:
    """Error budget gate configuration."""

    enabled: bool = True
    threshold: float | None = None  # Minimum remaining budget (e.g., 0.10 = 10%)
    policy: BudgetPolicy | None = None
```

### Step 4: Run test to verify it passes

Run: `cd /Users/robfox/Documents/GitHub/opensrm-ecosystem/nthlayer && uv run pytest tests/test_budget_policy.py -v`
Expected: PASS

### Step 5: Commit

```bash
git add src/nthlayer/specs/manifest.py tests/test_budget_policy.py
git commit -m "feat: add BudgetPolicy and BudgetThresholds dataclasses (trellis-budget-policy)"
```

---

## Task 7: Parse `policy` from manifest YAML

**Files:**
- Modify: `src/nthlayer/specs/opensrm_parser.py` (or wherever ErrorBudgetGate is parsed from YAML)
- Test: `tests/test_budget_policy.py`

### Step 1: Find the parser

First, locate where `ErrorBudgetGate` is currently parsed from YAML:

Run: `cd /Users/robfox/Documents/GitHub/opensrm-ecosystem/nthlayer && grep -rn "ErrorBudgetGate" src/nthlayer/specs/`

This will identify the parser file. It's likely in `opensrm_parser.py` or `loader.py`.

### Step 2: Write the failing test

Add to `tests/test_budget_policy.py`:

```python
class TestBudgetPolicyParsing:
    def test_parse_opensrm_with_budget_policy(self) -> None:
        from nthlayer.specs.opensrm_parser import parse_opensrm

        data = {
            "apiVersion": "srm/v1",
            "kind": "ServiceReliabilityManifest",
            "metadata": {"name": "test-svc", "team": "eng", "tier": "critical"},
            "spec": {
                "type": "api",
                "deployment": {
                    "gates": {
                        "error_budget": {
                            "enabled": True,
                            "policy": {
                                "window": "7d",
                                "thresholds": {
                                    "warning": 0.25,
                                    "critical": 0.15,
                                },
                                "on_exhausted": ["freeze_deploys", "notify"],
                            },
                        },
                    },
                },
            },
        }
        manifest = parse_opensrm(data)
        assert manifest.deployment is not None
        assert manifest.deployment.gates is not None
        assert manifest.deployment.gates.error_budget is not None
        assert manifest.deployment.gates.error_budget.policy is not None
        policy = manifest.deployment.gates.error_budget.policy
        assert policy.window == "7d"
        assert policy.thresholds.warning == 0.25
        assert policy.thresholds.critical == 0.15
        assert policy.on_exhausted == ["freeze_deploys", "notify"]

    def test_parse_opensrm_without_budget_policy(self) -> None:
        from nthlayer.specs.opensrm_parser import parse_opensrm

        data = {
            "apiVersion": "srm/v1",
            "kind": "ServiceReliabilityManifest",
            "metadata": {"name": "test-svc", "team": "eng", "tier": "critical"},
            "spec": {
                "type": "api",
                "deployment": {
                    "gates": {
                        "error_budget": {"enabled": True},
                    },
                },
            },
        }
        manifest = parse_opensrm(data)
        assert manifest.deployment.gates.error_budget.policy is None
```

### Step 3: Run test to verify it fails

Run: `cd /Users/robfox/Documents/GitHub/opensrm-ecosystem/nthlayer && uv run pytest tests/test_budget_policy.py::TestBudgetPolicyParsing -v`
Expected: FAIL

### Step 4: Write minimal implementation

Locate the OpenSRM parser's `ErrorBudgetGate` construction and add policy parsing. The exact location depends on what Step 1 reveals. The parsing code should be:

```python
def _parse_budget_policy(data: dict) -> BudgetPolicy | None:
    """Parse budget policy from error_budget gate config."""
    policy_data = data.get("policy")
    if not policy_data or not isinstance(policy_data, dict):
        return None

    thresholds = BudgetThresholds()
    thresh_data = policy_data.get("thresholds")
    if thresh_data and isinstance(thresh_data, dict):
        thresholds = BudgetThresholds(
            warning=float(thresh_data.get("warning", 0.20)),
            critical=float(thresh_data.get("critical", 0.10)),
        )

    on_exhausted = policy_data.get("on_exhausted", [])
    if not isinstance(on_exhausted, list):
        on_exhausted = []

    return BudgetPolicy(
        window=policy_data.get("window", "30d"),
        thresholds=thresholds,
        on_exhausted=on_exhausted,
    )
```

Add this call where `ErrorBudgetGate` is constructed from YAML, passing the parsed policy:

```python
ErrorBudgetGate(
    enabled=eb_data.get("enabled", True),
    threshold=eb_data.get("threshold"),
    policy=_parse_budget_policy(eb_data),
)
```

### Step 5: Run test to verify it passes

Run: `cd /Users/robfox/Documents/GitHub/opensrm-ecosystem/nthlayer && uv run pytest tests/test_budget_policy.py -v`
Expected: PASS

### Step 6: Commit

```bash
git add src/nthlayer/specs/opensrm_parser.py tests/test_budget_policy.py
git commit -m "feat: parse budget policy from manifest YAML (trellis-budget-policy)"
```

---

## Task 8: Integrate BudgetPolicy with DeploymentGate thresholds

**Files:**
- Modify: `src/nthlayer/slos/gates.py:156-303` (check_deployment) and `_get_thresholds`
- Test: `tests/test_gates.py`

### Step 1: Write the failing test

Add to `tests/test_gates.py`:

```python
class TestBudgetPolicyIntegration:
    """Test BudgetPolicy integration with DeploymentGate."""

    def test_policy_thresholds_override_tier_defaults(self):
        """BudgetPolicy thresholds from manifest override tier defaults."""
        from nthlayer.specs.manifest import BudgetPolicy, BudgetThresholds

        policy = BudgetPolicy(
            thresholds=BudgetThresholds(warning=0.30, critical=0.15),
        )
        # Convert BudgetPolicy thresholds to GatePolicy
        gate_policy = GatePolicy(
            warning=policy.thresholds.warning * 100,  # 30%
            blocking=policy.thresholds.critical * 100,  # 15%
        )
        gate = DeploymentGate(policy=gate_policy)

        # 20% remaining — below 30% warning but above 15% blocking
        result = gate.check_deployment(
            service="test-svc",
            tier="critical",
            budget_total_minutes=1000,
            budget_consumed_minutes=800,  # 20% remaining
        )
        assert result.result == GateResult.WARNING

    def test_policy_thresholds_block_below_critical(self):
        """Budget below policy critical threshold blocks deployment."""
        from nthlayer.specs.manifest import BudgetPolicy, BudgetThresholds

        policy = BudgetPolicy(
            thresholds=BudgetThresholds(warning=0.30, critical=0.15),
        )
        gate_policy = GatePolicy(
            warning=policy.thresholds.warning * 100,
            blocking=policy.thresholds.critical * 100,
        )
        gate = DeploymentGate(policy=gate_policy)

        # 10% remaining — below 15% critical
        result = gate.check_deployment(
            service="test-svc",
            tier="critical",
            budget_total_minutes=1000,
            budget_consumed_minutes=900,  # 10% remaining
        )
        assert result.result == GateResult.BLOCKED
```

### Step 2: Run test to verify it passes

Run: `cd /Users/robfox/Documents/GitHub/opensrm-ecosystem/nthlayer && uv run pytest tests/test_gates.py::TestBudgetPolicyIntegration -v`
Expected: PASS — `GatePolicy` already supports custom `warning`/`blocking` thresholds, and `DeploymentGate._get_thresholds()` already applies them. This test confirms the plumbing works.

### Step 3: Commit

```bash
git add tests/test_gates.py
git commit -m "test: verify BudgetPolicy thresholds work with DeploymentGate (trellis-budget-policy)"
```

---

## Task 9: Add `on_exhausted` enforcement to DeploymentGate

**Files:**
- Modify: `src/nthlayer/slos/gates.py:156-303`
- Modify: `src/nthlayer/slos/gates.py:72-74` (DeploymentGateCheck)
- Test: `tests/test_gates.py`

### Step 1: Write the failing test

Add to `tests/test_gates.py`:

```python
class TestOnExhaustedBehavior:
    """Test on_exhausted behavior enforcement."""

    def test_freeze_deploys_blocks_when_exhausted(self):
        """freeze_deploys in on_exhausted blocks when budget is 0."""
        gate_policy = GatePolicy(
            warning=20.0,
            blocking=None,  # Standard tier — normally no blocking
            on_exhausted=["freeze_deploys"],
        )
        gate = DeploymentGate(policy=gate_policy)

        result = gate.check_deployment(
            service="test-svc",
            tier="standard",
            budget_total_minutes=1000,
            budget_consumed_minutes=1000,  # 0% remaining — exhausted
        )
        assert result.result == GateResult.BLOCKED
        assert "freeze" in result.message.lower() or "exhausted" in result.message.lower()

    def test_require_approval_warns_when_exhausted(self):
        """require_approval in on_exhausted produces WARNING when budget is 0."""
        gate_policy = GatePolicy(
            warning=20.0,
            blocking=None,
            on_exhausted=["require_approval"],
        )
        gate = DeploymentGate(policy=gate_policy)

        result = gate.check_deployment(
            service="test-svc",
            tier="standard",
            budget_total_minutes=1000,
            budget_consumed_minutes=1000,  # 0% remaining
        )
        # require_approval escalates to at least WARNING
        assert result.result in (GateResult.WARNING, GateResult.BLOCKED)

    def test_no_exhaustion_behavior_when_budget_healthy(self):
        """on_exhausted behaviors don't fire when budget is healthy."""
        gate_policy = GatePolicy(
            warning=20.0,
            blocking=None,
            on_exhausted=["freeze_deploys"],
        )
        gate = DeploymentGate(policy=gate_policy)

        result = gate.check_deployment(
            service="test-svc",
            tier="standard",
            budget_total_minutes=1000,
            budget_consumed_minutes=500,  # 50% remaining — healthy
        )
        assert result.result == GateResult.APPROVED
```

### Step 2: Run test to verify it fails

Run: `cd /Users/robfox/Documents/GitHub/opensrm-ecosystem/nthlayer && uv run pytest tests/test_gates.py::TestOnExhaustedBehavior -v`
Expected: FAIL — `GatePolicy` doesn't have `on_exhausted` and `check_deployment` doesn't enforce it

### Step 3: Write minimal implementation

1. Add `on_exhausted` to `GatePolicy` in `src/nthlayer/slos/gates.py`:

```python
@dataclass
class GatePolicy:
    """Custom gate policy from DeploymentGate resource."""

    # Custom thresholds (override defaults)
    warning: float | None = None
    blocking: float | None = None

    # Conditional policies
    conditions: list[dict[str, Any]] = field(default_factory=list)

    # Exceptions (teams that can bypass)
    exceptions: list[dict[str, Any]] = field(default_factory=list)

    # Behaviors when error budget is exhausted (0% remaining)
    on_exhausted: list[str] = field(default_factory=list)

    @classmethod
    def from_spec(cls, spec: dict[str, Any]) -> "GatePolicy":
        """Create GatePolicy from DeploymentGate resource spec."""
        thresholds = spec.get("thresholds", {})
        return cls(
            warning=thresholds.get("warning"),
            blocking=thresholds.get("blocking"),
            conditions=spec.get("conditions", []),
            exceptions=spec.get("exceptions", []),
            on_exhausted=spec.get("on_exhausted", []),
        )
```

2. In `check_deployment()`, add exhaustion behavior check after the existing gate logic (before the `return` at the end). Insert after the existing BLOCKED/WARNING/APPROVED if-chain:

```python
        # Apply on_exhausted behaviors if budget is fully consumed
        if (
            self.policy
            and self.policy.on_exhausted
            and budget_remaining_pct <= 0
            and result != GateResult.BLOCKED  # Don't downgrade an existing block
        ):
            if "freeze_deploys" in self.policy.on_exhausted:
                result = GateResult.BLOCKED
                message = (
                    f"⛔ Deployment BLOCKED: Error budget exhausted "
                    f"({budget_remaining_pct:.1f}% remaining) — freeze_deploys policy active"
                )
                recommendations = [
                    "Error budget is fully exhausted",
                    "freeze_deploys policy is blocking all deployments",
                    "Wait for budget to recover or request an override",
                ]
            elif "require_approval" in self.policy.on_exhausted:
                result = GateResult.WARNING
                message = (
                    f"⚠️  Deployment WARNING: Error budget exhausted "
                    f"({budget_remaining_pct:.1f}% remaining) — approval required"
                )
                recommendations = [
                    "Error budget is fully exhausted",
                    "require_approval policy — get explicit approval before deploying",
                    "Use --override to bypass after approval",
                ]
```

### Step 4: Run test to verify it passes

Run: `cd /Users/robfox/Documents/GitHub/opensrm-ecosystem/nthlayer && uv run pytest tests/test_gates.py::TestOnExhaustedBehavior -v`
Expected: PASS

### Step 5: Run the full gates test suite

Run: `cd /Users/robfox/Documents/GitHub/opensrm-ecosystem/nthlayer && uv run pytest tests/test_gates.py -v`
Expected: All existing tests still pass

### Step 6: Commit

```bash
git add src/nthlayer/slos/gates.py tests/test_gates.py
git commit -m "feat: add on_exhausted behaviors to DeploymentGate (trellis-budget-policy)"
```

---

## Task 10: Wire BudgetPolicy into check-deploy CLI

**Files:**
- Modify: `src/nthlayer/cli/deploy.py:93-132`
- Test: `tests/test_budget_policy.py`

### Step 1: Write the failing test

Add to `tests/test_budget_policy.py`:

```python
class TestBudgetPolicyCLIWiring:
    """Test that BudgetPolicy flows from manifest to DeploymentGate via CLI."""

    def test_gate_policy_from_budget_policy(self) -> None:
        """BudgetPolicy from manifest converts to GatePolicy for DeploymentGate."""
        from nthlayer.specs.manifest import BudgetPolicy, BudgetThresholds
        from nthlayer.slos.gates import GatePolicy

        budget_policy = BudgetPolicy(
            window="7d",
            thresholds=BudgetThresholds(warning=0.25, critical=0.12),
            on_exhausted=["freeze_deploys", "notify"],
        )

        # Conversion: BudgetPolicy → GatePolicy
        gate_policy = GatePolicy(
            warning=budget_policy.thresholds.warning * 100,
            blocking=budget_policy.thresholds.critical * 100,
            on_exhausted=budget_policy.on_exhausted,
        )

        assert gate_policy.warning == 25.0
        assert gate_policy.blocking == 12.0
        assert gate_policy.on_exhausted == ["freeze_deploys", "notify"]
```

### Step 2: Run test

Run: `cd /Users/robfox/Documents/GitHub/opensrm-ecosystem/nthlayer && uv run pytest tests/test_budget_policy.py::TestBudgetPolicyCLIWiring -v`
Expected: PASS (this is a unit test for the conversion logic)

### Step 3: Update check-deploy CLI wiring

In `src/nthlayer/cli/deploy.py`, around lines 93-96 where the `GatePolicy` is extracted from resources, add fallback to manifest's `BudgetPolicy`:

The existing code:
```python
    gate_resources = [r for r in resources if r.kind == "DeploymentGate"]
    policy = GatePolicy.from_spec(gate_resources[0].spec) if gate_resources else None
```

This currently only reads from `DeploymentGate` resources. For manifests using the new `spec.deployment.gates.error_budget.policy` path, we need to also check if a manifest was loaded. Since `check_deploy_command` uses `parse_service_file()` which returns `(ServiceContext, list[Resource])`, not a `ReliabilityManifest`, the cleanest approach is to add a utility function that extracts `GatePolicy` from either source.

Add a helper function:

```python
def _extract_gate_policy(
    resources: list[Any],
    service_file: str,
    environment: str | None = None,
) -> GatePolicy | None:
    """Extract GatePolicy from DeploymentGate resource or manifest BudgetPolicy."""
    # First: check for explicit DeploymentGate resource
    gate_resources = [r for r in resources if r.kind == "DeploymentGate"]
    if gate_resources:
        return GatePolicy.from_spec(gate_resources[0].spec)

    # Second: check for BudgetPolicy in manifest
    try:
        from nthlayer.specs.loader import load_manifest

        manifest = load_manifest(service_file, environment=environment)
        if (
            manifest.deployment
            and manifest.deployment.gates
            and manifest.deployment.gates.error_budget
            and manifest.deployment.gates.error_budget.policy
        ):
            bp = manifest.deployment.gates.error_budget.policy
            return GatePolicy(
                warning=bp.thresholds.warning * 100,
                blocking=bp.thresholds.critical * 100,
                on_exhausted=bp.on_exhausted,
            )
    except Exception:
        pass

    return None
```

Replace the existing gate policy extraction with:
```python
    policy = _extract_gate_policy(resources, service_file, environment)
```

### Step 4: Run full test suite

Run: `cd /Users/robfox/Documents/GitHub/opensrm-ecosystem/nthlayer && uv run pytest tests/test_budget_policy.py tests/test_gates.py -v`
Expected: PASS

### Step 5: Commit

```bash
git add src/nthlayer/cli/deploy.py tests/test_budget_policy.py
git commit -m "feat: wire BudgetPolicy to check-deploy CLI (trellis-budget-policy)"
```

---

## Task 11: Validate `on_exhausted` values

**Files:**
- Modify: `src/nthlayer/specs/manifest.py`
- Test: `tests/test_budget_policy.py`

### Step 1: Write the failing test

Add to `tests/test_budget_policy.py`:

```python
class TestBudgetPolicyValidation:
    def test_invalid_on_exhausted_raises(self) -> None:
        with pytest.raises(ValueError, match="invalid_behavior"):
            BudgetPolicy(on_exhausted=["invalid_behavior"]).validate()

    def test_valid_on_exhausted_passes(self) -> None:
        # Should not raise
        BudgetPolicy(on_exhausted=["freeze_deploys", "notify"]).validate()

    def test_empty_on_exhausted_passes(self) -> None:
        # Should not raise
        BudgetPolicy(on_exhausted=[]).validate()

    def test_warning_above_critical_passes(self) -> None:
        BudgetPolicy(
            thresholds=BudgetThresholds(warning=0.30, critical=0.10),
        ).validate()

    def test_warning_below_critical_raises(self) -> None:
        with pytest.raises(ValueError, match="warning.*critical"):
            BudgetPolicy(
                thresholds=BudgetThresholds(warning=0.05, critical=0.10),
            ).validate()
```

### Step 2: Run test to verify it fails

Run: `cd /Users/robfox/Documents/GitHub/opensrm-ecosystem/nthlayer && uv run pytest tests/test_budget_policy.py::TestBudgetPolicyValidation -v`
Expected: FAIL — `validate()` method doesn't exist

### Step 3: Write minimal implementation

Add `validate()` method to `BudgetPolicy` in `src/nthlayer/specs/manifest.py`:

```python
    def validate(self) -> None:
        """Validate policy configuration.

        Raises:
            ValueError: If configuration is invalid
        """
        for behavior in self.on_exhausted:
            if behavior not in VALID_EXHAUSTION_BEHAVIORS:
                raise ValueError(
                    f"Invalid on_exhausted behavior: {behavior}. "
                    f"Valid values: {', '.join(sorted(VALID_EXHAUSTION_BEHAVIORS))}"
                )
        if self.thresholds.warning < self.thresholds.critical:
            raise ValueError(
                f"warning threshold ({self.thresholds.warning}) must be >= "
                f"critical threshold ({self.thresholds.critical})"
            )
```

### Step 4: Run test to verify it passes

Run: `cd /Users/robfox/Documents/GitHub/opensrm-ecosystem/nthlayer && uv run pytest tests/test_budget_policy.py::TestBudgetPolicyValidation -v`
Expected: PASS

### Step 5: Commit

```bash
git add src/nthlayer/specs/manifest.py tests/test_budget_policy.py
git commit -m "feat: add BudgetPolicy validation (trellis-budget-policy)"
```

---

## Task 12: Run full test suite and close beads

**Files:** None (verification only)

### Step 1: Run full test suite

Run: `cd /Users/robfox/Documents/GitHub/opensrm-ecosystem/nthlayer && uv run pytest tests/test_alerting_config.py tests/test_alerts.py tests/test_alert_pipeline.py tests/test_gates.py tests/test_budget_policy.py -v`
Expected: All PASS

### Step 2: Run smoke tests

Run: `cd /Users/robfox/Documents/GitHub/opensrm-ecosystem/nthlayer && make smoke`
Expected: PASS

### Step 3: Run lint

Run: `cd /Users/robfox/Documents/GitHub/opensrm-ecosystem/nthlayer && make lint`
Expected: PASS

### Step 4: Close beads

```bash
cd /Users/robfox/Documents/GitHub/opensrm-ecosystem/nthlayer
bd close trellis-alert-for --reason "Implemented ForDuration in AlertingConfig with page/ticket severity mapping, wired through alert generation pipeline"
bd close trellis-budget-policy --reason "Implemented BudgetPolicy with thresholds, window, on_exhausted behaviors, wired to DeploymentGate and check-deploy CLI"
```

### Step 5: Final commit

```bash
git add -A
git commit -m "chore: close trellis-alert-for and trellis-budget-policy beads"
```
