"""
Tests for the drift detection module.

Tests cover:
- Data models (DriftMetrics, DriftProjection, DriftResult)
- Pattern detection (PatternDetector)
- Drift analysis (DriftAnalyzer)
- CLI command (drift_command)
"""

from __future__ import annotations

from datetime import datetime, timedelta
from unittest.mock import patch

import pytest
from nthlayer.drift import (
    DRIFT_DEFAULTS,
    DriftAnalysisError,
    DriftAnalyzer,
    DriftMetrics,
    DriftPattern,
    DriftProjection,
    DriftResult,
    DriftSeverity,
    PatternDetector,
    get_drift_defaults,
)


class TestDriftModels:
    """Tests for drift data models."""

    def test_drift_severity_values(self):
        """Test DriftSeverity enum values."""
        assert DriftSeverity.NONE.value == "none"
        assert DriftSeverity.INFO.value == "info"
        assert DriftSeverity.WARN.value == "warn"
        assert DriftSeverity.CRITICAL.value == "critical"

    def test_drift_pattern_values(self):
        """Test DriftPattern enum values."""
        assert DriftPattern.STABLE.value == "stable"
        assert DriftPattern.GRADUAL_DECLINE.value == "gradual_decline"
        assert DriftPattern.GRADUAL_IMPROVEMENT.value == "gradual_improvement"
        assert DriftPattern.STEP_CHANGE_DOWN.value == "step_change_down"
        assert DriftPattern.STEP_CHANGE_UP.value == "step_change_up"
        assert DriftPattern.VOLATILE.value == "volatile"

    def test_drift_metrics_creation(self):
        """Test DriftMetrics dataclass creation."""
        metrics = DriftMetrics(
            slope_per_day=-0.001,
            slope_per_week=-0.007,
            r_squared=0.85,
            current_budget=0.72,
            budget_at_window_start=0.80,
            variance=0.001,
            data_points=720,
        )

        assert metrics.slope_per_day == -0.001
        assert metrics.slope_per_week == -0.007
        assert metrics.r_squared == 0.85
        assert metrics.current_budget == 0.72
        assert metrics.data_points == 720

    def test_drift_projection_creation(self):
        """Test DriftProjection dataclass creation."""
        projection = DriftProjection(
            days_until_exhaustion=138,
            projected_budget_30d=0.70,
            projected_budget_60d=0.68,
            projected_budget_90d=0.66,
            confidence=0.85,
        )

        assert projection.days_until_exhaustion == 138
        assert projection.projected_budget_30d == 0.70
        assert projection.confidence == 0.85

    def test_drift_projection_none_exhaustion(self):
        """Test DriftProjection with no exhaustion (stable/improving)."""
        projection = DriftProjection(
            days_until_exhaustion=None,
            projected_budget_30d=0.85,
            projected_budget_60d=0.90,
            projected_budget_90d=0.95,
            confidence=0.90,
        )

        assert projection.days_until_exhaustion is None

    def test_drift_result_to_dict(self):
        """Test DriftResult serialization to dict."""
        now = datetime.now()
        result = DriftResult(
            service_name="test-service",
            tier="critical",
            slo_name="availability",
            window="30d",
            analyzed_at=now,
            data_start=now - timedelta(days=30),
            data_end=now,
            metrics=DriftMetrics(
                slope_per_day=-0.001,
                slope_per_week=-0.007,
                r_squared=0.85,
                current_budget=0.72,
                budget_at_window_start=0.80,
                variance=0.001,
                data_points=720,
            ),
            projection=DriftProjection(
                days_until_exhaustion=100,
                projected_budget_30d=0.70,
                projected_budget_60d=0.68,
                projected_budget_90d=0.66,
                confidence=0.85,
            ),
            pattern=DriftPattern.GRADUAL_DECLINE,
            severity=DriftSeverity.WARN,
            summary="Test summary",
            recommendation="Test recommendation",
            exit_code=1,
        )

        d = result.to_dict()

        assert d["service"] == "test-service"
        assert d["tier"] == "critical"
        assert d["slo"] == "availability"
        assert d["severity"] == "warn"
        assert d["pattern"] == "gradual_decline"
        assert d["exit_code"] == 1
        assert "metrics" in d
        assert "projection" in d

    def test_get_drift_defaults_critical(self):
        """Test getting drift defaults for critical tier."""
        defaults = get_drift_defaults("critical")

        assert defaults["enabled"] is True
        assert defaults["window"] == "30d"
        assert "-0.2%/week" in defaults["thresholds"]["warn"]

    def test_get_drift_defaults_standard(self):
        """Test getting drift defaults for standard tier."""
        defaults = get_drift_defaults("standard")

        assert defaults["enabled"] is True
        assert defaults["window"] == "30d"
        assert "-0.5%/week" in defaults["thresholds"]["warn"]

    def test_get_drift_defaults_low(self):
        """Test getting drift defaults for low tier."""
        defaults = get_drift_defaults("low")

        assert defaults["enabled"] is False
        assert defaults["window"] == "14d"

    def test_get_drift_defaults_unknown_tier(self):
        """Test getting drift defaults for unknown tier falls back to standard."""
        defaults = get_drift_defaults("unknown")

        assert defaults == DRIFT_DEFAULTS["standard"]


class TestPatternDetector:
    """Tests for PatternDetector."""

    def test_detect_stable_pattern(self):
        """Test detecting stable pattern (no significant trend)."""
        detector = PatternDetector()

        # Create data with very small slope
        now = datetime.now()
        data = [(now - timedelta(hours=i), 0.80 + (i * 0.00001)) for i in range(100, 0, -1)]

        pattern = detector.detect(data, slope_per_second=0.0000000001, r_squared=0.9)

        assert pattern == DriftPattern.STABLE

    def test_detect_gradual_decline(self):
        """Test detecting gradual decline pattern."""
        detector = PatternDetector()

        now = datetime.now()
        # Declining by 1% per week = significant decline
        data = [(now - timedelta(days=i), 0.80 - (i * 0.001)) for i in range(30, 0, -1)]

        # Slope: -0.001 per day = -0.007 per week
        slope_per_second = -0.001 / 86400
        pattern = detector.detect(data, slope_per_second=slope_per_second, r_squared=0.9)

        assert pattern == DriftPattern.GRADUAL_DECLINE

    def test_detect_gradual_improvement(self):
        """Test detecting gradual improvement pattern."""
        detector = PatternDetector()

        now = datetime.now()
        data = [(now - timedelta(days=i), 0.70 + (i * 0.001)) for i in range(30, 0, -1)]

        # Positive slope
        slope_per_second = 0.001 / 86400
        pattern = detector.detect(data, slope_per_second=slope_per_second, r_squared=0.9)

        assert pattern == DriftPattern.GRADUAL_IMPROVEMENT

    def test_detect_step_change_down(self):
        """Test detecting step change down pattern."""
        detector = PatternDetector(step_change_threshold=0.05)

        now = datetime.now()
        data = [
            (now - timedelta(hours=48), 0.90),
            (now - timedelta(hours=36), 0.89),
            (now - timedelta(hours=24), 0.88),
            (now - timedelta(hours=12), 0.78),  # 10% drop in 12 hours
            (now, 0.77),
        ]

        pattern = detector.detect(data, slope_per_second=-0.001, r_squared=0.5)

        assert pattern == DriftPattern.STEP_CHANGE_DOWN

    def test_detect_step_change_up(self):
        """Test detecting step change up pattern."""
        detector = PatternDetector(step_change_threshold=0.05)

        now = datetime.now()
        data = [
            (now - timedelta(hours=48), 0.70),
            (now - timedelta(hours=36), 0.71),
            (now - timedelta(hours=24), 0.72),
            (now - timedelta(hours=12), 0.82),  # 10% jump
            (now, 0.83),
        ]

        pattern = detector.detect(data, slope_per_second=0.001, r_squared=0.5)

        assert pattern == DriftPattern.STEP_CHANGE_UP

    def test_detect_volatile_pattern(self):
        """Test detecting volatile pattern."""
        detector = PatternDetector(
            volatility_variance_threshold=0.0005,  # Lower threshold to trigger volatile
            volatility_r_squared_threshold=0.3,
            step_change_threshold=0.2,  # High threshold to avoid step change detection
        )

        now = datetime.now()
        # High variance data with poor fit - small oscillations
        # Variance of this data is ~0.0009
        data = [
            (now - timedelta(hours=i), 0.70 + (0.03 if i % 2 == 0 else -0.03))
            for i in range(50, 0, -1)
        ]

        # Low r_squared + high variance = volatile
        pattern = detector.detect(data, slope_per_second=0, r_squared=0.1)

        assert pattern == DriftPattern.VOLATILE

    def test_detect_with_insufficient_data(self):
        """Test detection with insufficient data returns stable."""
        detector = PatternDetector()

        data = [(datetime.now(), 0.80)]

        pattern = detector.detect(data, slope_per_second=0, r_squared=0)

        assert pattern == DriftPattern.STABLE


class TestDriftAnalyzer:
    """Tests for DriftAnalyzer."""

    def test_analyzer_initialization(self):
        """Test DriftAnalyzer initialization."""
        analyzer = DriftAnalyzer(
            prometheus_url="http://prometheus:9090",
            username="user",
            password="pass",
        )

        assert analyzer.prometheus_url == "http://prometheus:9090"
        assert analyzer.username == "user"
        assert analyzer.password == "pass"

    def test_analyzer_url_trailing_slash(self):
        """Test that trailing slashes are removed from URL."""
        analyzer = DriftAnalyzer(prometheus_url="http://prometheus:9090/")

        assert analyzer.prometheus_url == "http://prometheus:9090"

    def test_parse_threshold(self):
        """Test parsing threshold strings."""
        analyzer = DriftAnalyzer(prometheus_url="http://localhost:9090")

        assert analyzer._parse_threshold("-0.5%/week") == -0.005
        assert analyzer._parse_threshold("-1.0%/week") == -0.01
        assert analyzer._parse_threshold("-0.2%/week") == -0.002

    def test_parse_days(self):
        """Test parsing day duration strings."""
        analyzer = DriftAnalyzer(prometheus_url="http://localhost:9090")

        assert analyzer._parse_days("30d") == 30
        assert analyzer._parse_days("14d") == 14
        assert analyzer._parse_days("7d") == 7

    def test_parse_duration(self):
        """Test parsing duration strings to timedelta."""
        analyzer = DriftAnalyzer(prometheus_url="http://localhost:9090")

        assert analyzer._parse_duration("30d") == timedelta(days=30)
        assert analyzer._parse_duration("14d") == timedelta(days=14)
        assert analyzer._parse_duration("1w") == timedelta(weeks=1)
        assert analyzer._parse_duration("24h") == timedelta(hours=24)

    def test_project_exhaustion_declining(self):
        """Test exhaustion projection with declining budget."""
        analyzer = DriftAnalyzer(prometheus_url="http://localhost:9090")

        # 72% budget, declining at 0.5% per day
        current_budget = 0.72
        slope_per_second = -0.005 / 86400

        days = analyzer._project_exhaustion(current_budget, slope_per_second)

        # Should be approximately 144 days (72 / 0.5)
        assert days is not None
        assert 140 <= days <= 150

    def test_project_exhaustion_stable(self):
        """Test exhaustion projection with stable/improving budget."""
        analyzer = DriftAnalyzer(prometheus_url="http://localhost:9090")

        days = analyzer._project_exhaustion(0.72, slope_per_second=0.001)

        assert days is None

    def test_project_exhaustion_already_exhausted(self):
        """Test exhaustion projection when budget is already exhausted."""
        analyzer = DriftAnalyzer(prometheus_url="http://localhost:9090")

        days = analyzer._project_exhaustion(0, slope_per_second=-0.001)

        assert days == 0

    def test_classify_severity_critical_exhaustion(self):
        """Test severity classification with critical exhaustion timeline."""
        analyzer = DriftAnalyzer(prometheus_url="http://localhost:9090")

        severity = analyzer._classify_severity(
            slope_per_week=-0.001,
            days_until_exhaustion=5,  # Within critical window
            pattern=DriftPattern.GRADUAL_DECLINE,
            thresholds={"warn": "-0.5%/week", "critical": "-1.0%/week"},
            projection_config={"exhaustion_warn": "30d", "exhaustion_critical": "14d"},
        )

        assert severity == DriftSeverity.CRITICAL

    def test_classify_severity_step_change(self):
        """Test severity classification with step change."""
        analyzer = DriftAnalyzer(prometheus_url="http://localhost:9090")

        severity = analyzer._classify_severity(
            slope_per_week=-0.001,
            days_until_exhaustion=100,
            pattern=DriftPattern.STEP_CHANGE_DOWN,
            thresholds={"warn": "-0.5%/week", "critical": "-1.0%/week"},
            projection_config={"exhaustion_warn": "30d", "exhaustion_critical": "14d"},
        )

        assert severity == DriftSeverity.CRITICAL

    def test_classify_severity_warn(self):
        """Test severity classification as warning."""
        analyzer = DriftAnalyzer(prometheus_url="http://localhost:9090")

        severity = analyzer._classify_severity(
            slope_per_week=-0.006,  # Exceeds warn threshold
            days_until_exhaustion=50,
            pattern=DriftPattern.GRADUAL_DECLINE,
            thresholds={"warn": "-0.5%/week", "critical": "-1.0%/week"},
            projection_config={"exhaustion_warn": "30d", "exhaustion_critical": "14d"},
        )

        assert severity == DriftSeverity.WARN

    def test_classify_severity_info(self):
        """Test severity classification as info."""
        analyzer = DriftAnalyzer(prometheus_url="http://localhost:9090")

        severity = analyzer._classify_severity(
            slope_per_week=-0.001,  # Below thresholds
            days_until_exhaustion=200,
            pattern=DriftPattern.GRADUAL_DECLINE,
            thresholds={"warn": "-0.5%/week", "critical": "-1.0%/week"},
            projection_config={"exhaustion_warn": "30d", "exhaustion_critical": "14d"},
        )

        assert severity == DriftSeverity.INFO

    def test_classify_severity_none(self):
        """Test severity classification as none (stable/improving)."""
        analyzer = DriftAnalyzer(prometheus_url="http://localhost:9090")

        severity = analyzer._classify_severity(
            slope_per_week=0.001,  # Positive slope
            days_until_exhaustion=None,
            pattern=DriftPattern.STABLE,
            thresholds={"warn": "-0.5%/week", "critical": "-1.0%/week"},
            projection_config={"exhaustion_warn": "30d", "exhaustion_critical": "14d"},
        )

        assert severity == DriftSeverity.NONE

    def test_generate_summary_none(self):
        """Test summary generation for no drift."""
        analyzer = DriftAnalyzer(prometheus_url="http://localhost:9090")

        metrics = DriftMetrics(
            slope_per_day=0,
            slope_per_week=0,
            r_squared=0.9,
            current_budget=0.90,
            budget_at_window_start=0.90,
            variance=0.001,
            data_points=720,
        )

        summary = analyzer._generate_summary(metrics, DriftPattern.STABLE, DriftSeverity.NONE)

        assert "stable" in summary.lower()

    def test_generate_summary_decline(self):
        """Test summary generation for declining drift."""
        analyzer = DriftAnalyzer(prometheus_url="http://localhost:9090")

        metrics = DriftMetrics(
            slope_per_day=-0.001,
            slope_per_week=-0.007,
            r_squared=0.85,
            current_budget=0.72,
            budget_at_window_start=0.80,
            variance=0.001,
            data_points=720,
        )

        summary = analyzer._generate_summary(
            metrics, DriftPattern.GRADUAL_DECLINE, DriftSeverity.WARN
        )

        assert "declining" in summary.lower()
        assert "0.70%" in summary or "0.7" in summary

    @pytest.mark.asyncio
    async def test_analyze_insufficient_data(self):
        """Test analyze raises error with insufficient data."""
        analyzer = DriftAnalyzer(prometheus_url="http://localhost:9090")

        with patch.object(analyzer, "_query_budget_history") as mock_query:
            mock_query.return_value = [(datetime.now(), 0.80)]  # Only 1 point

            with pytest.raises(DriftAnalysisError) as exc_info:
                await analyzer.analyze(
                    service_name="test-service",
                    tier="critical",
                )

            assert "Insufficient data points" in str(exc_info.value)


class TestDriftCLI:
    """Tests for drift CLI command."""

    def test_drift_command_demo_mode(self):
        """Test drift command in demo mode."""
        from nthlayer.cli.drift import drift_command

        # Demo mode should work without Prometheus
        exit_code = drift_command(
            service_file="examples/services/payment-api.yaml",
            demo=True,
        )

        assert exit_code == 1  # Demo returns warning

    def test_drift_command_demo_json(self):
        """Test drift command demo mode with JSON output."""
        from nthlayer.cli.drift import drift_command

        exit_code = drift_command(
            service_file="examples/services/payment-api.yaml",
            demo=True,
            output_format="json",
        )

        assert exit_code == 1

    def test_drift_command_no_prometheus(self, capsys):
        """Test drift command fails gracefully without Prometheus URL."""
        from nthlayer.cli.drift import drift_command

        with patch.dict("os.environ", {}, clear=True):
            exit_code = drift_command(
                service_file="examples/services/payment-api.yaml",
            )

            assert exit_code == 2
            captured = capsys.readouterr()
            assert "No Prometheus URL" in captured.out

    def test_handle_drift_command(self):
        """Test handle_drift_command with args."""
        from argparse import Namespace

        from nthlayer.cli.drift import handle_drift_command

        args = Namespace(
            service_file="examples/services/payment-api.yaml",
            prometheus_url=None,
            environment=None,
            window=None,
            slo="availability",
            output_format="table",
            demo=True,
        )

        exit_code = handle_drift_command(args)

        assert exit_code == 1


class TestDriftIntegration:
    """Integration tests for drift detection."""

    @pytest.mark.asyncio
    async def test_full_analysis_flow_mocked(self):
        """Test full analysis flow with mocked Prometheus."""
        analyzer = DriftAnalyzer(prometheus_url="http://localhost:9090")

        now = datetime.now()
        # Generate declining data - earlier times have higher values
        # i=0 is earliest (30 days ago), i=719 is most recent
        mock_data = [(now - timedelta(hours=720 - i), 0.90 - (i * 0.0002)) for i in range(720)]

        with patch.object(analyzer, "_query_budget_history") as mock_query:
            mock_query.return_value = mock_data

            result = await analyzer.analyze(
                service_name="test-service",
                tier="critical",
                slo="availability",
                window="30d",
            )

        assert result.service_name == "test-service"
        assert result.tier == "critical"
        assert result.slo_name == "availability"
        assert result.metrics.data_points == 720
        assert result.metrics.slope_per_week < 0  # Declining
        assert result.exit_code in [0, 1, 2]

    def test_drift_defaults_all_tiers(self):
        """Test drift defaults are defined for all tiers."""
        for tier in ["critical", "standard", "low"]:
            defaults = get_drift_defaults(tier)

            assert "enabled" in defaults
            assert "window" in defaults
            assert "thresholds" in defaults
            assert "projection" in defaults
            assert "warn" in defaults["thresholds"]
            assert "critical" in defaults["thresholds"]
