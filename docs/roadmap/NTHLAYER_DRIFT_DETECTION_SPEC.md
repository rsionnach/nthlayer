# NthLayer Drift Detection Feature Spec

## Overview

**Feature Name:** Service Reliability Drift Engine
**Status:** Proposed
**Target Release:** v0.2.0

### Problem Statement

NthLayer currently catches reliability issues at two points:
1. **Pre-deployment** (`verify`, `validate-spec`, `--lint`) — static validation
2. **Deployment gate** (`check-deploy`) — instant error budget snapshot

Missing: **Trend analysis** — detecting gradual reliability degradation before burn-rate alerts fire.

Example scenario: A service's 99.95% availability SLO slowly declines to 99.7% over 8 weeks. Daily burn rate never exceeds thresholds, so no alerts fire. Error budget technically remains positive. But the trend indicates a systemic issue that will eventually cause an incident.

### Solution

Add drift detection capabilities to NthLayer that:
1. Query SLO/error budget metrics over configurable time windows
2. Calculate trend slopes and project future budget exhaustion
3. Detect drift patterns (gradual decline, step-change, seasonal)
4. Integrate with existing CLI (`check-deploy`, `portfolio`) and CI/CD pipelines
5. Provide actionable output with severity classification

---

## Architecture

### Integration with Existing NthLayer

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                        NthLayer Reliability Pipeline                        │
├─────────────────┬─────────────────┬─────────────────┬─────────────────────┤
│    GENERATE     │    VALIDATE     │     PROTECT     │      MONITOR        │
│                 │                 │                 │      (NEW)          │
├─────────────────┼─────────────────┼─────────────────┼─────────────────────┤
│ nthlayer apply  │ --lint          │ check-deploy    │ drift               │
│ nthlayer plan   │ verify          │                 │ portfolio --drift   │
│                 │ validate-spec   │                 │                     │
├─────────────────┼─────────────────┼─────────────────┼─────────────────────┤
│ Instant         │ Instant         │ Instant query   │ Range query         │
│ File generation │ Point-in-time   │ Current budget  │ Historical trend    │
└─────────────────┴─────────────────┴─────────────────┴─────────────────────┘
```

### New Module Structure

```
src/nthlayer/
├── drift/                      # NEW PACKAGE
│   ├── __init__.py
│   ├── analyzer.py             # Core drift analysis logic
│   ├── patterns.py             # Pattern detection (gradual, step, seasonal)
│   ├── projector.py            # Budget exhaustion projection
│   └── models.py               # DriftResult, DriftPattern, DriftSeverity
├── cli/
│   ├── drift.py                # NEW: `nthlayer drift` command
│   ├── check_deploy.py         # MODIFY: add --include-drift flag
│   └── portfolio.py            # MODIFY: add --drift flag
└── slos/
    └── collector.py            # MODIFY: add query_range() method
```

### Data Flow

```
service.yaml
     │
     ▼
┌─────────────┐    ┌──────────────────┐    ┌─────────────────┐
│ ServiceContext │──▶│  DriftAnalyzer   │──▶│   DriftResult   │
└─────────────┘    │                  │    │                 │
                   │ - query_range()  │    │ - slope         │
                   │ - linear_regress │    │ - projection    │
                   │ - detect_pattern │    │ - pattern       │
                   └──────────────────┘    │ - severity      │
                            │              │ - recommendation│
                            ▼              └─────────────────┘
                   ┌──────────────────┐
                   │   Prometheus     │
                   │ /api/v1/query_range │
                   └──────────────────┘
```

---

## Service Specification Extension

### New `drift` Block

```yaml
# service.yaml
name: payment-api
tier: critical
type: api
team: payments

slos:
  availability: 99.95
  latency_p99_ms: 200

# NEW SECTION
drift:
  enabled: true                    # Default: true for critical/standard, false for low
  window: 30d                      # Analysis window (default: 30d)

  # Alert thresholds (optional - defaults derived from tier)
  thresholds:
    warn: -0.3%/week               # Warn if losing 0.3% budget per week
    critical: -1.0%/week           # Critical if losing 1.0% budget per week

  # Projection settings
  projection:
    horizon: 90d                   # How far to project (default: 90d)
    exhaustion_warn: 30d           # Warn if projected exhaustion within 30 days
    exhaustion_critical: 7d        # Critical if projected exhaustion within 7 days

  # Pattern detection
  patterns:
    detect_step_change: true       # Detect sudden degradation
    detect_seasonal: false         # Detect recurring patterns (requires 60d+ data)
    step_change_threshold: 5%      # Step change if >5% budget drop in <24h

dependencies:
  - postgresql
  - redis
```

### Tier-Based Defaults

```python
DRIFT_DEFAULTS = {
    "critical": {
        "enabled": True,
        "window": "30d",
        "thresholds": {"warn": "-0.2%/week", "critical": "-0.5%/week"},
        "projection": {"horizon": "90d", "exhaustion_warn": "30d", "exhaustion_critical": "14d"},
    },
    "standard": {
        "enabled": True,
        "window": "30d",
        "thresholds": {"warn": "-0.5%/week", "critical": "-1.0%/week"},
        "projection": {"horizon": "60d", "exhaustion_warn": "14d", "exhaustion_critical": "7d"},
    },
    "low": {
        "enabled": False,  # Opt-in for low-tier services
        "window": "14d",
        "thresholds": {"warn": "-1.0%/week", "critical": "-2.0%/week"},
        "projection": {"horizon": "30d", "exhaustion_warn": "7d", "exhaustion_critical": "3d"},
    },
}
```

---

## Data Models

### DriftResult

```python
# src/nthlayer/drift/models.py
from dataclasses import dataclass
from enum import Enum
from typing import Optional
from datetime import datetime, timedelta


class DriftSeverity(Enum):
    NONE = "none"           # No significant drift
    INFO = "info"           # Minor drift, informational
    WARN = "warn"           # Actionable drift, investigate
    CRITICAL = "critical"   # Severe drift, immediate action needed


class DriftPattern(Enum):
    STABLE = "stable"               # No significant trend
    GRADUAL_DECLINE = "gradual_decline"   # Slow, steady degradation
    GRADUAL_IMPROVEMENT = "gradual_improvement"  # Slow recovery
    STEP_CHANGE_DOWN = "step_change_down"  # Sudden drop
    STEP_CHANGE_UP = "step_change_up"      # Sudden improvement
    SEASONAL = "seasonal"           # Recurring pattern
    VOLATILE = "volatile"           # High variance, no clear trend


@dataclass
class DriftMetrics:
    """Raw metrics from drift analysis."""
    slope_per_day: float            # Budget change per day (e.g., -0.001 = -0.1%/day)
    slope_per_week: float           # Budget change per week
    r_squared: float                # Goodness of fit (0-1, higher = more linear)
    current_budget: float           # Current error budget remaining (0-1)
    budget_at_window_start: float   # Budget at start of analysis window
    variance: float                 # Variance in budget over window
    data_points: int                # Number of data points analyzed


@dataclass
class DriftProjection:
    """Future budget projection."""
    days_until_exhaustion: Optional[int]  # None if not trending toward exhaustion
    projected_budget_30d: float     # Projected budget in 30 days
    projected_budget_60d: float     # Projected budget in 60 days
    projected_budget_90d: float     # Projected budget in 90 days
    confidence: float               # Confidence in projection (based on r_squared)


@dataclass
class DriftResult:
    """Complete drift analysis result for a service."""
    service_name: str
    tier: str
    slo_name: str                   # e.g., "availability", "latency_p99"

    # Analysis metadata
    window: str                     # e.g., "30d"
    analyzed_at: datetime
    data_start: datetime
    data_end: datetime

    # Core results
    metrics: DriftMetrics
    projection: DriftProjection
    pattern: DriftPattern
    severity: DriftSeverity

    # Actionable output
    summary: str                    # Human-readable summary
    recommendation: str             # Suggested action

    # For CI/CD
    exit_code: int                  # 0=ok, 1=warn, 2=critical

    def to_dict(self) -> dict:
        """Serialize for JSON output."""
        return {
            "service": self.service_name,
            "tier": self.tier,
            "slo": self.slo_name,
            "window": self.window,
            "analyzed_at": self.analyzed_at.isoformat(),
            "severity": self.severity.value,
            "pattern": self.pattern.value,
            "metrics": {
                "slope_per_week": f"{self.metrics.slope_per_week:.4f}",
                "slope_per_week_pct": f"{self.metrics.slope_per_week * 100:.2f}%",
                "current_budget": f"{self.metrics.current_budget:.4f}",
                "r_squared": f"{self.metrics.r_squared:.3f}",
            },
            "projection": {
                "days_until_exhaustion": self.projection.days_until_exhaustion,
                "budget_30d": f"{self.projection.projected_budget_30d:.4f}",
                "budget_60d": f"{self.projection.projected_budget_60d:.4f}",
                "confidence": f"{self.projection.confidence:.2f}",
            },
            "summary": self.summary,
            "recommendation": self.recommendation,
            "exit_code": self.exit_code,
        }
```

---

## Prometheus Queries

### Required Recording Rules

NthLayer already generates recording rules. Drift detection relies on these existing rules:

```yaml
# Already generated by nthlayer apply
groups:
  - name: payment-api-slo-recording
    rules:
      # Error budget remaining (0-1 scale)
      - record: slo:error_budget_remaining:ratio
        expr: |
          1 - (
            sum(rate(http_requests_total{service="payment-api", status=~"5.."}[30d]))
            /
            sum(rate(http_requests_total{service="payment-api"}[30d]))
          ) / (1 - 0.9995)
        labels:
          service: payment-api
          slo: availability

      # SLI value (actual success rate)
      - record: slo:sli:ratio
        expr: |
          sum(rate(http_requests_total{service="payment-api", status!~"5.."}[5m]))
          /
          sum(rate(http_requests_total{service="payment-api"}[5m]))
        labels:
          service: payment-api
          slo: availability
```

### Drift Analysis Queries

```python
# src/nthlayer/drift/analyzer.py

class DriftAnalyzer:
    """Analyzes SLO drift over time using Prometheus range queries."""

    def __init__(self, prometheus_client: PrometheusClient):
        self.prometheus = prometheus_client

    def _build_budget_query(self, service: str, slo: str = "availability") -> str:
        """Build query for error budget remaining."""
        return f'slo:error_budget_remaining:ratio{{service="{service}", slo="{slo}"}}'

    def _build_sli_query(self, service: str, slo: str = "availability") -> str:
        """Build query for raw SLI value."""
        return f'slo:sli:ratio{{service="{service}", slo="{slo}"}}'

    async def query_budget_history(
        self,
        service: str,
        window: str = "30d",
        step: str = "1h",
        slo: str = "availability"
    ) -> list[tuple[datetime, float]]:
        """
        Query error budget over time window.

        Returns list of (timestamp, budget_value) tuples.
        """
        query = self._build_budget_query(service, slo)

        # Calculate time range
        end = datetime.now()
        start = end - self._parse_duration(window)

        # Prometheus range query
        result = await self.prometheus.query_range(
            query=query,
            start=start.timestamp(),
            end=end.timestamp(),
            step=step,
        )

        # Parse response
        if not result or "data" not in result:
            raise DriftAnalysisError(f"No data returned for {service}")

        values = result["data"]["result"][0]["values"]
        return [(datetime.fromtimestamp(ts), float(val)) for ts, val in values]
```

### Example Range Query Request

```
GET /api/v1/query_range?query=slo:error_budget_remaining:ratio{service="payment-api"}&start=1701388800&end=1704067200&step=1h
```

Response:
```json
{
  "status": "success",
  "data": {
    "resultType": "matrix",
    "result": [
      {
        "metric": {"service": "payment-api", "slo": "availability"},
        "values": [
          [1701388800, "0.9523"],
          [1701392400, "0.9518"],
          [1701396000, "0.9512"],
          ...
        ]
      }
    ]
  }
}
```

---

## Core Analysis Logic

### Linear Regression for Trend Detection

```python
# src/nthlayer/drift/analyzer.py
import numpy as np
from scipy import stats


class DriftAnalyzer:

    def _calculate_trend(
        self,
        data: list[tuple[datetime, float]]
    ) -> tuple[float, float, float]:
        """
        Calculate linear trend using least squares regression.

        Returns:
            slope: Change per second
            intercept: Y-intercept
            r_squared: Coefficient of determination (fit quality)
        """
        if len(data) < 2:
            raise DriftAnalysisError("Insufficient data points for trend analysis")

        # Convert to numpy arrays
        timestamps = np.array([d[0].timestamp() for d in data])
        values = np.array([d[1] for d in data])

        # Normalize timestamps to start from 0
        timestamps = timestamps - timestamps[0]

        # Linear regression
        slope, intercept, r_value, p_value, std_err = stats.linregress(
            timestamps, values
        )

        r_squared = r_value ** 2

        return slope, intercept, r_squared

    def _slope_to_weekly(self, slope_per_second: float) -> float:
        """Convert slope from per-second to per-week."""
        seconds_per_week = 7 * 24 * 60 * 60
        return slope_per_second * seconds_per_week

    def _project_exhaustion(
        self,
        current_budget: float,
        slope_per_second: float
    ) -> Optional[int]:
        """
        Project days until budget exhaustion.

        Returns None if:
        - Slope is positive (improving)
        - Slope is effectively zero
        - Budget is already exhausted
        """
        if slope_per_second >= 0:
            return None  # Not declining

        if current_budget <= 0:
            return 0  # Already exhausted

        # Time to reach 0 = current_budget / |slope|
        seconds_to_exhaustion = current_budget / abs(slope_per_second)
        days_to_exhaustion = seconds_to_exhaustion / (24 * 60 * 60)

        # Cap at reasonable maximum
        if days_to_exhaustion > 365:
            return None  # Effectively stable

        return int(days_to_exhaustion)
```

### Pattern Detection

```python
# src/nthlayer/drift/patterns.py

class PatternDetector:
    """Detect drift patterns beyond simple linear trends."""

    def detect(
        self,
        data: list[tuple[datetime, float]],
        slope: float,
        r_squared: float,
        step_threshold: float = 0.05
    ) -> DriftPattern:
        """
        Classify the drift pattern.

        Args:
            data: Time series data
            slope: Linear regression slope
            r_squared: Fit quality
            step_threshold: Minimum change to consider a step change
        """
        values = [d[1] for d in data]
        variance = np.var(values)

        # Check for step change first
        step_change = self._detect_step_change(data, step_threshold)
        if step_change:
            return step_change

        # High variance + low r_squared = volatile
        if r_squared < 0.3 and variance > 0.01:
            return DriftPattern.VOLATILE

        # Classify by slope direction and significance
        weekly_slope = slope * 7 * 24 * 60 * 60

        if abs(weekly_slope) < 0.001:  # Less than 0.1% per week
            return DriftPattern.STABLE
        elif weekly_slope < 0:
            return DriftPattern.GRADUAL_DECLINE
        else:
            return DriftPattern.GRADUAL_IMPROVEMENT

    def _detect_step_change(
        self,
        data: list[tuple[datetime, float]],
        threshold: float
    ) -> Optional[DriftPattern]:
        """
        Detect sudden step changes in the data.

        Looks for >threshold change within 24-hour window.
        """
        values = [d[1] for d in data]
        timestamps = [d[0] for d in data]

        for i in range(1, len(values)):
            time_diff = (timestamps[i] - timestamps[i-1]).total_seconds()
            value_diff = values[i] - values[i-1]

            # Check if change exceeds threshold within ~24 hours
            if time_diff < 86400 * 1.5:  # 1.5 days tolerance
                if value_diff < -threshold:
                    return DriftPattern.STEP_CHANGE_DOWN
                elif value_diff > threshold:
                    return DriftPattern.STEP_CHANGE_UP

        return None
```

### Severity Classification

```python
# src/nthlayer/drift/analyzer.py

class DriftAnalyzer:

    def _classify_severity(
        self,
        slope_per_week: float,
        days_until_exhaustion: Optional[int],
        pattern: DriftPattern,
        thresholds: dict,
        projection_config: dict
    ) -> DriftSeverity:
        """
        Classify drift severity based on slope, projection, and pattern.

        Priority order:
        1. Projected exhaustion within critical window → CRITICAL
        2. Step change down → CRITICAL
        3. Slope exceeds critical threshold → CRITICAL
        4. Projected exhaustion within warn window → WARN
        5. Slope exceeds warn threshold → WARN
        6. Any negative slope → INFO
        7. Otherwise → NONE
        """
        # Parse thresholds
        warn_slope = self._parse_threshold(thresholds["warn"])
        critical_slope = self._parse_threshold(thresholds["critical"])
        exhaustion_warn = self._parse_days(projection_config["exhaustion_warn"])
        exhaustion_critical = self._parse_days(projection_config["exhaustion_critical"])

        # Check critical conditions
        if days_until_exhaustion is not None:
            if days_until_exhaustion <= exhaustion_critical:
                return DriftSeverity.CRITICAL

        if pattern == DriftPattern.STEP_CHANGE_DOWN:
            return DriftSeverity.CRITICAL

        if slope_per_week <= critical_slope:
            return DriftSeverity.CRITICAL

        # Check warn conditions
        if days_until_exhaustion is not None:
            if days_until_exhaustion <= exhaustion_warn:
                return DriftSeverity.WARN

        if slope_per_week <= warn_slope:
            return DriftSeverity.WARN

        # Check info conditions
        if slope_per_week < 0:
            return DriftSeverity.INFO

        return DriftSeverity.NONE

    def _parse_threshold(self, threshold: str) -> float:
        """Parse threshold string like '-0.5%/week' to float."""
        # Remove '/week' suffix and '%' symbol
        value = threshold.replace("/week", "").replace("%", "").strip()
        return float(value) / 100  # Convert percentage to decimal

    def _parse_days(self, duration: str) -> int:
        """Parse duration string like '30d' to integer days."""
        return int(duration.replace("d", ""))
```

---

## CLI Interface

### New `drift` Command

```python
# src/nthlayer/cli/drift.py
import click
from rich.console import Console
from rich.table import Table

from nthlayer.drift.analyzer import DriftAnalyzer
from nthlayer.drift.models import DriftSeverity
from nthlayer.specs.parser import parse_service_file


@click.command()
@click.argument("service_file", type=click.Path(exists=True))
@click.option("--window", "-w", default=None, help="Analysis window (e.g., 30d, 14d)")
@click.option("--slo", "-s", default="availability", help="SLO to analyze")
@click.option("--format", "-f", type=click.Choice(["table", "json"]), default="table")
@click.option("--prometheus-url", envvar="NTHLAYER_PROMETHEUS_URL")
@click.pass_context
def drift(ctx, service_file: str, window: str, slo: str, format: str, prometheus_url: str):
    """
    Analyze reliability drift for a service.

    Queries historical SLO metrics and detects degradation trends.

    Exit codes:
      0 - No significant drift
      1 - Warning: drift detected, investigate
      2 - Critical: severe drift, immediate action needed

    Examples:
      nthlayer drift service.yaml
      nthlayer drift service.yaml --window 14d
      nthlayer drift service.yaml --slo latency_p99 --format json
    """
    console = Console()

    # Parse service spec
    service = parse_service_file(service_file)

    # Get drift config (with tier defaults)
    drift_config = service.get_drift_config()

    if not drift_config["enabled"]:
        console.print(f"[dim]Drift detection disabled for {service.name}[/dim]")
        ctx.exit(0)

    # Override window if provided
    analysis_window = window or drift_config["window"]

    # Run analysis
    analyzer = DriftAnalyzer(prometheus_url)
    result = analyzer.analyze(
        service=service,
        window=analysis_window,
        slo=slo,
        thresholds=drift_config["thresholds"],
        projection_config=drift_config["projection"],
    )

    # Output
    if format == "json":
        console.print_json(data=result.to_dict())
    else:
        _print_drift_table(console, result)

    ctx.exit(result.exit_code)


def _print_drift_table(console: Console, result: DriftResult):
    """Print drift analysis as formatted table."""
    # Severity coloring
    severity_colors = {
        DriftSeverity.NONE: "green",
        DriftSeverity.INFO: "blue",
        DriftSeverity.WARN: "yellow",
        DriftSeverity.CRITICAL: "red",
    }
    color = severity_colors[result.severity]

    console.print()
    console.print(f"[bold]Drift Analysis: {result.service_name}[/bold]")
    console.print(f"SLO: {result.slo_name} | Window: {result.window}")
    console.print()

    table = Table(show_header=True, header_style="bold")
    table.add_column("Metric")
    table.add_column("Value")

    table.add_row("Current Budget", f"{result.metrics.current_budget:.2%}")
    table.add_row("Trend", f"{result.metrics.slope_per_week * 100:+.3f}%/week")
    table.add_row("Pattern", result.pattern.value.replace("_", " ").title())
    table.add_row("Fit Quality (R²)", f"{result.metrics.r_squared:.3f}")

    if result.projection.days_until_exhaustion:
        table.add_row(
            "Projected Exhaustion",
            f"{result.projection.days_until_exhaustion} days"
        )
    else:
        table.add_row("Projected Exhaustion", "N/A (stable or improving)")

    table.add_row("30-day Projection", f"{result.projection.projected_budget_30d:.2%}")

    console.print(table)
    console.print()

    # Severity banner
    console.print(f"[{color} bold]Severity: {result.severity.value.upper()}[/{color} bold]")
    console.print(f"[dim]{result.summary}[/dim]")
    console.print()

    if result.recommendation:
        console.print(f"[bold]Recommendation:[/bold] {result.recommendation}")
```

### Extended `check-deploy` Command

```python
# src/nthlayer/cli/check_deploy.py (modified)

@click.command()
@click.argument("service_file", type=click.Path(exists=True))
@click.option("--include-drift/--no-drift", default=False,
              help="Include drift analysis in deployment gate")
@click.option("--drift-window", default=None, help="Drift analysis window")
@click.pass_context
def check_deploy(ctx, service_file: str, include_drift: bool, drift_window: str):
    """
    Check if service is safe to deploy.

    Validates error budget and optionally checks for reliability drift.

    Exit codes:
      0 - Safe to deploy
      1 - Warning (drift detected but budget OK)
      2 - Blocked (budget exhausted OR critical drift)
    """
    service = parse_service_file(service_file)

    # Existing budget check
    budget_result = check_error_budget(service)

    if budget_result.exhausted:
        console.print("[red bold]BLOCKED: Error budget exhausted[/red bold]")
        ctx.exit(2)

    # Optional drift check
    if include_drift:
        drift_config = service.get_drift_config()
        if drift_config["enabled"]:
            analyzer = DriftAnalyzer(prometheus_url)
            drift_result = analyzer.analyze(service, window=drift_window)

            if drift_result.severity == DriftSeverity.CRITICAL:
                console.print("[red bold]BLOCKED: Critical reliability drift[/red bold]")
                console.print(f"[dim]{drift_result.summary}[/dim]")
                ctx.exit(2)

            if drift_result.severity == DriftSeverity.WARN:
                console.print("[yellow bold]WARNING: Reliability drift detected[/yellow bold]")
                console.print(f"[dim]{drift_result.summary}[/dim]")
                # Don't block, but surface the warning

    console.print("[green bold]APPROVED: Safe to deploy[/green bold]")
    ctx.exit(0)
```

### Extended `portfolio` Command

```python
# src/nthlayer/cli/portfolio.py (modified)

@click.command()
@click.option("--drift/--no-drift", default=False, help="Include drift analysis")
@click.option("--format", "-f", type=click.Choice(["table", "json"]), default="table")
def portfolio(drift: bool, format: str):
    """
    Display org-wide reliability portfolio.

    Shows SLO health across all registered services.
    With --drift, includes trend analysis for each service.
    """
    services = discover_services()

    results = []
    for service in services:
        budget = check_error_budget(service)

        row = {
            "service": service.name,
            "tier": service.tier,
            "budget_remaining": budget.remaining,
            "status": budget.status,
        }

        if drift:
            drift_result = analyze_drift(service)
            row["drift_trend"] = f"{drift_result.metrics.slope_per_week * 100:+.2f}%/wk"
            row["drift_severity"] = drift_result.severity.value
            row["days_to_exhaustion"] = drift_result.projection.days_until_exhaustion

        results.append(row)

    if format == "json":
        print_json(results)
    else:
        print_portfolio_table(results, include_drift=drift)
```

---

## CLI Output Examples

### `nthlayer drift service.yaml`

```
Drift Analysis: payment-api
SLO: availability | Window: 30d

┏━━━━━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━━━━━━┓
┃ Metric               ┃ Value               ┃
┡━━━━━━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━━━━━━━━┩
│ Current Budget       │ 72.34%              │
│ Trend                │ -0.523%/week        │
│ Pattern              │ Gradual Decline     │
│ Fit Quality (R²)     │ 0.847               │
│ Projected Exhaustion │ 138 days            │
│ 30-day Projection    │ 70.25%              │
└──────────────────────┴─────────────────────┘

Severity: WARN
Error budget declining at 0.52% per week with high confidence (R²=0.85).

Recommendation: Investigate recent changes. Common causes: increased traffic,
dependency degradation, or configuration drift. Run `nthlayer verify` to check
metric coverage.
```

### `nthlayer drift service.yaml --format json`

```json
{
  "service": "payment-api",
  "tier": "critical",
  "slo": "availability",
  "window": "30d",
  "analyzed_at": "2026-01-06T14:32:00Z",
  "severity": "warn",
  "pattern": "gradual_decline",
  "metrics": {
    "slope_per_week": "-0.0052",
    "slope_per_week_pct": "-0.52%",
    "current_budget": "0.7234",
    "r_squared": "0.847"
  },
  "projection": {
    "days_until_exhaustion": 138,
    "budget_30d": "0.7025",
    "budget_60d": "0.6817",
    "confidence": "0.85"
  },
  "summary": "Error budget declining at 0.52% per week with high confidence.",
  "recommendation": "Investigate recent changes...",
  "exit_code": 1
}
```

### `nthlayer portfolio --drift`

```
NthLayer Portfolio - Reliability Overview
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

┏━━━━━━━━━━━━━━━━┳━━━━━━━━━━┳━━━━━━━━━┳━━━━━━━━━━┳━━━━━━━━━━━━━┳━━━━━━━━━━━━━┓
┃ Service        ┃ Tier     ┃ Budget  ┃ Status   ┃ Drift       ┃ Exhaustion  ┃
┡━━━━━━━━━━━━━━━━╇━━━━━━━━━━╇━━━━━━━━━╇━━━━━━━━━━╇━━━━━━━━━━━━━╇━━━━━━━━━━━━━┩
│ payment-api    │ critical │ 72.34%  │ healthy  │ -0.52%/wk ⚠ │ 138 days    │
│ user-service   │ critical │ 91.20%  │ healthy  │ +0.12%/wk ✓ │ -           │
│ order-worker   │ standard │ 45.10%  │ warning  │ -1.23%/wk ⚠ │ 37 days     │
│ analytics-api  │ low      │ 23.45%  │ critical │ -2.10%/wk ✗ │ 11 days     │
│ email-worker   │ standard │ 88.00%  │ healthy  │ stable ✓    │ -           │
└────────────────┴──────────┴─────────┴──────────┴─────────────┴─────────────┘

Summary: 5 services | 2 healthy | 2 drifting | 1 critical
```

---

## Exit Codes

| Code | Meaning | When Returned | CI/CD Action |
|------|---------|---------------|--------------|
| `0` | OK | No drift or positive trend | Continue |
| `1` | Warning | Drift detected, within thresholds | Continue (with warning) |
| `2` | Critical | Severe drift or projected exhaustion | Block deployment |

---

## CI/CD Integration

### GitHub Actions

```yaml
# .github/workflows/deploy.yml
name: Deploy with Drift Check

on:
  push:
    branches: [main]

jobs:
  reliability-gate:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Install NthLayer
        run: pipx install nthlayer

      - name: Generate artifacts
        run: nthlayer apply service.yaml --lint

      - name: Verify metrics
        run: nthlayer verify service.yaml
        env:
          NTHLAYER_PROMETHEUS_URL: ${{ secrets.PROMETHEUS_URL }}

      - name: Check deployment gate (with drift)
        run: nthlayer check-deploy service.yaml --include-drift
        env:
          NTHLAYER_PROMETHEUS_URL: ${{ secrets.PROMETHEUS_URL }}

      - name: Deploy
        if: success()
        run: kubectl apply -f generated/
```

### GitLab CI

```yaml
# .gitlab-ci.yml
reliability-gate:
  stage: validate
  script:
    - pipx install nthlayer
    - nthlayer apply service.yaml --lint
    - nthlayer verify service.yaml
    - nthlayer check-deploy service.yaml --include-drift
  allow_failure:
    exit_codes:
      - 1  # Allow warnings, block on exit code 2
```

---

## Testing Strategy

### Unit Tests

```python
# tests/drift/test_analyzer.py

def test_slope_calculation_declining():
    """Test that declining budget produces negative slope."""
    data = [
        (datetime(2026, 1, 1), 0.95),
        (datetime(2026, 1, 8), 0.93),
        (datetime(2026, 1, 15), 0.91),
        (datetime(2026, 1, 22), 0.89),
    ]
    analyzer = DriftAnalyzer(mock_prometheus)
    slope, _, r_squared = analyzer._calculate_trend(data)

    assert slope < 0
    assert r_squared > 0.9  # Should be highly linear


def test_severity_classification_critical():
    """Test critical severity when exhaustion imminent."""
    result = analyzer._classify_severity(
        slope_per_week=-0.02,
        days_until_exhaustion=5,
        pattern=DriftPattern.GRADUAL_DECLINE,
        thresholds={"warn": "-0.005", "critical": "-0.01"},
        projection_config={"exhaustion_warn": "30d", "exhaustion_critical": "7d"},
    )

    assert result == DriftSeverity.CRITICAL


def test_step_change_detection():
    """Test detection of sudden budget drop."""
    data = [
        (datetime(2026, 1, 1, 0), 0.95),
        (datetime(2026, 1, 1, 12), 0.94),
        (datetime(2026, 1, 2, 0), 0.85),  # 9% drop in 12 hours
        (datetime(2026, 1, 2, 12), 0.84),
    ]
    detector = PatternDetector()
    pattern = detector.detect(data, slope=-0.01, r_squared=0.5, step_threshold=0.05)

    assert pattern == DriftPattern.STEP_CHANGE_DOWN
```

### Integration Tests

```python
# tests/drift/test_integration.py

@pytest.mark.integration
def test_drift_command_with_prometheus(prometheus_container):
    """Test full drift command against real Prometheus."""
    # Seed Prometheus with test data
    seed_budget_data(prometheus_container, service="test-api", days=30)

    result = runner.invoke(drift, ["service.yaml", "--format", "json"])

    assert result.exit_code in [0, 1, 2]
    data = json.loads(result.output)
    assert "slope_per_week" in data["metrics"]
    assert "days_until_exhaustion" in data["projection"]
```

---

## Future Enhancements

### Phase 2: Advanced Pattern Detection

- **Seasonal patterns**: Detect weekly/monthly cycles (requires 60d+ data)
- **Correlation with deploys**: Link drift to specific deployments via annotations
- **Multi-SLO correlation**: Detect when multiple SLOs drift together

### Phase 3: Automated Remediation

- **Runbook linking**: Suggest runbooks based on drift patterns
- **Auto-rollback triggers**: Integrate with ArgoCD/Flux for automatic rollback
- **Slack/PagerDuty alerts**: Proactive drift notifications

### Phase 4: ML-Enhanced Detection

- **Anomaly detection**: Use isolation forests for unusual patterns
- **Forecasting**: ARIMA/Prophet for better projections
- **Root cause hints**: Correlate with infrastructure metrics

---

## Dependencies

### New Dependencies

```toml
# pyproject.toml additions
[project]
dependencies = [
    # Existing...
    "scipy>=1.11.0",      # Linear regression, statistics
    "numpy>=1.24.0",      # Numerical operations
]

[project.optional-dependencies]
drift-ml = [
    "scikit-learn>=1.3.0",  # For future anomaly detection
    "prophet>=1.1.0",       # For future forecasting
]
```

### Prometheus Client Extension

```python
# src/nthlayer/discovery/prometheus.py (extend existing)

class PrometheusClient:

    async def query_range(
        self,
        query: str,
        start: float,
        end: float,
        step: str = "1h",
    ) -> dict:
        """
        Execute Prometheus range query.

        Args:
            query: PromQL expression
            start: Start timestamp (Unix epoch)
            end: End timestamp (Unix epoch)
            step: Query resolution (e.g., "1h", "5m")

        Returns:
            Prometheus API response dict
        """
        params = {
            "query": query,
            "start": start,
            "end": end,
            "step": step,
        }

        async with self.session.get(
            f"{self.base_url}/api/v1/query_range",
            params=params,
        ) as response:
            response.raise_for_status()
            return await response.json()
```

---

## Summary

This feature extends NthLayer from a "pre-deployment validation" tool to a "complete reliability lifecycle" tool by adding trend analysis. The implementation:

1. **Fits naturally** into the existing architecture (reuses ServiceContext, Prometheus integration, CLI patterns)
2. **Maintains stateless design** (all analysis via Prometheus range queries)
3. **Respects tier-based defaults** (critical services get tighter thresholds)
4. **Integrates with CI/CD** (exit codes, --include-drift flag)
5. **Provides actionable output** (severity, recommendations, projections)

The recommended implementation order:
1. Data models + basic analyzer (1-2 days)
2. `nthlayer drift` CLI command (1 day)
3. Pattern detection (1 day)
4. `check-deploy --include-drift` integration (0.5 day)
5. `portfolio --drift` integration (0.5 day)
6. Tests + documentation (1-2 days)

**Estimated total: 5-7 days of focused development**
