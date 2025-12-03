"""
Integration tests for SLO functionality.

Tests SLO parsing, storage, and error budget calculation.
"""

from datetime import datetime, timedelta

import pytest
from nthlayer.slos.calculator import ErrorBudgetCalculator
from nthlayer.slos.models import SLO, ErrorBudget, SLOStatus, TimeWindow, TimeWindowType
from nthlayer.slos.parser import OpenSLOParserError, parse_slo_dict, parse_slo_file


class TestOpenSLOParser:
    """Test OpenSLO YAML parsing."""

    def test_parse_payment_api_availability(self):
        """Test parsing payment API availability SLO file."""
        slo = parse_slo_file("examples/slos/payment-api-availability.yaml")
        
        assert slo.id == "payment-api-availability"
        assert slo.service == "payment-api"
        assert slo.name == "Payment API Availability"
        assert slo.target == 0.9995
        assert slo.time_window.duration == "30d"
        assert slo.time_window.type == TimeWindowType.ROLLING
        assert slo.owner == "john@company.com"
        assert "team" in slo.labels
        assert slo.labels["team"] == "platform"

    def test_parse_payment_api_latency(self):
        """Test parsing payment API latency SLO file."""
        slo = parse_slo_file("examples/slos/payment-api-latency.yaml")
        
        assert slo.id == "payment-api-latency"
        assert slo.service == "payment-api"
        assert slo.target == 0.99
        assert slo.time_window.duration == "30d"

    def test_parse_search_api_availability(self):
        """Test parsing search API availability SLO file."""
        slo = parse_slo_file("examples/slos/search-api-availability.yaml")
        
        assert slo.id == "search-api-availability"
        assert slo.service == "search-api"
        assert slo.target == 0.999  # 99.9%
        assert slo.time_window.duration == "30d"

    def test_parse_invalid_api_version(self):
        """Test that invalid apiVersion raises error."""
        data = {
            "apiVersion": "invalid/v1",
            "kind": "SLO",
            "metadata": {"name": "test"},
            "spec": {}
        }
        
        with pytest.raises(OpenSLOParserError, match="Invalid apiVersion"):
            parse_slo_dict(data)

    def test_parse_missing_required_fields(self):
        """Test that missing required fields raise errors."""
        data = {
            "apiVersion": "openslo/v1",
            "kind": "SLO",
            "metadata": {"name": "test"},
            "spec": {}  # Missing required fields
        }
        
        with pytest.raises(OpenSLOParserError):
            parse_slo_dict(data)


class TestSLOModel:
    """Test SLO data model."""

    def test_error_budget_calculation(self):
        """Test error budget calculation for different SLO targets."""
        # 99.95% availability over 30 days
        slo = SLO(
            id="test",
            service="test-service",
            name="Test SLO",
            description="Test",
            target=0.9995,
            time_window=TimeWindow(duration="30d", type=TimeWindowType.ROLLING),
            query="up",
        )
        
        # 0.05% of 30 days = 0.05% * 30 * 24 * 60 = 21.6 minutes
        assert slo.error_budget_minutes() == pytest.approx(21.6, rel=0.01)
        assert slo.error_budget_percent() == pytest.approx(0.0005, rel=0.01)  # 0.05%

    def test_time_window_to_timedelta(self):
        """Test time window conversion to timedelta."""
        assert TimeWindow("30d", TimeWindowType.ROLLING).to_timedelta() == timedelta(days=30)
        assert TimeWindow("7d", TimeWindowType.ROLLING).to_timedelta() == timedelta(days=7)
        assert TimeWindow("1h", TimeWindowType.ROLLING).to_timedelta() == timedelta(hours=1)
        assert TimeWindow("5m", TimeWindowType.ROLLING).to_timedelta() == timedelta(minutes=5)

    def test_slo_to_dict_roundtrip(self):
        """Test SLO can be converted to dict and back."""
        slo = SLO(
            id="test-slo",
            service="test-service",
            name="Test SLO",
            description="Test description",
            target=0.999,
            time_window=TimeWindow(duration="30d", type=TimeWindowType.ROLLING),
            query="rate(http_requests[5m])",
            owner="test@example.com",
            labels={"team": "test"},
        )
        
        # Convert to dict
        slo_dict = slo.to_dict()
        
        # Verify structure
        assert slo_dict["apiVersion"] == "openslo/v1"
        assert slo_dict["kind"] == "SLO"
        assert slo_dict["metadata"]["name"] == "test-slo"
        assert slo_dict["spec"]["service"] == "test-service"
        assert slo_dict["spec"]["objectives"][0]["target"] == 0.999


class TestErrorBudgetCalculator:
    """Test error budget calculation logic."""

    def test_calculate_budget_no_measurements(self):
        """Test budget calculation with no measurements."""
        slo = SLO(
            id="test",
            service="test-service",
            name="Test",
            description="Test",
            target=0.9995,
            time_window=TimeWindow("30d", TimeWindowType.ROLLING),
            query="up",
        )
        
        calculator = ErrorBudgetCalculator(slo)
        budget = calculator.calculate_budget()
        
        assert budget.total_budget_minutes == pytest.approx(21.6, rel=0.01)
        assert budget.burned_minutes == 0.0
        assert budget.remaining_minutes == pytest.approx(21.6, rel=0.01)
        assert budget.status == SLOStatus.HEALTHY

    def test_calculate_budget_with_measurements(self):
        """Test budget calculation with SLI measurements."""
        slo = SLO(
            id="test",
            service="test-service",
            name="Test",
            description="Test",
            target=0.9995,
            time_window=TimeWindow("30d", TimeWindowType.ROLLING),
            query="up",
        )
        
        # Simulate measurements: 100% uptime for first half, 99% for second half
        now = datetime.utcnow()
        measurements = []
        
        # First 15 days: 100% uptime
        for i in range(15):
            measurements.append({
                "timestamp": now - timedelta(days=30-i),
                "sli_value": 1.0,  # 100% good
                "duration_seconds": 86400,  # 1 day
            })
        
        # Last 15 days: 99% uptime (1% errors)
        for i in range(15, 30):
            measurements.append({
                "timestamp": now - timedelta(days=30-i),
                "sli_value": 0.99,  # 99% good, 1% errors
                "duration_seconds": 86400,  # 1 day
            })
        
        calculator = ErrorBudgetCalculator(slo)
        budget = calculator.calculate_budget(sli_measurements=measurements)
        
        # 1% error rate for 15 days = 0.01 * 15 * 24 * 60 = 216 minutes
        assert budget.burned_minutes == pytest.approx(216, rel=0.1)
        assert budget.percent_consumed > 50  # Burned more than 50%

    def test_calculate_burn_rate(self):
        """Test burn rate calculation."""
        slo = SLO(
            id="test",
            service="test-service",
            name="Test",
            description="Test",
            target=0.9995,
            time_window=TimeWindow("30d", TimeWindowType.ROLLING),
            query="up",
        )
        
        calculator = ErrorBudgetCalculator(slo)
        
        # Burned 10 minutes in first 15 days (half the period)
        # Expected burn for half period: 21.6 / 2 = 10.8 minutes
        # Burn rate: 10 / 10.8 = 0.93x (slower than expected)
        now = datetime.utcnow()
        period_start = now - timedelta(days=30)
        half_point = now - timedelta(days=15)
        
        burn_rate = calculator.calculate_burn_rate(
            current_burn_minutes=10.0,
            period_start=period_start,
            period_end=half_point,
        )
        
        assert burn_rate < 1.0  # Burning slower than expected
        assert burn_rate == pytest.approx(0.93, rel=0.1)

    def test_project_budget_exhaustion(self):
        """Test budget exhaustion projection."""
        slo = SLO(
            id="test",
            service="test-service",
            name="Test",
            description="Test",
            target=0.9995,
            time_window=TimeWindow("30d", TimeWindowType.ROLLING),
            query="up",
        )
        
        calculator = ErrorBudgetCalculator(slo)
        
        # Burned 15 minutes in first 10 days
        # Burn rate: 1.5 min/day
        # Remaining: 6.6 minutes
        # Days until exhaustion: 6.6 / 1.5 = 4.4 days
        now = datetime.utcnow()
        period_start = now - timedelta(days=10)
        
        exhaustion = calculator.project_budget_exhaustion(
            current_burn_minutes=15.0,
            period_start=period_start,
        )
        
        assert exhaustion is not None
        assert exhaustion > now
        # Should be around 4-5 days from now
        days_until = (exhaustion - now).days
        assert 4 <= days_until <= 5

    def test_should_alert_threshold(self):
        """Test alert thresholds."""
        slo = SLO(
            id="test",
            service="test-service",
            name="Test",
            description="Test",
            target=0.9995,
            time_window=TimeWindow("30d", TimeWindowType.ROLLING),
            query="up",
        )
        
        calculator = ErrorBudgetCalculator(slo)
        
        # Budget at 80% consumption - should alert
        budget = ErrorBudget(
            slo_id="test",
            service="test-service",
            period_start=datetime.utcnow() - timedelta(days=30),
            period_end=datetime.utcnow(),
            total_budget_minutes=21.6,
            burned_minutes=17.3,  # 80%
            remaining_minutes=4.3,
        )
        
        should_alert, reason = calculator.should_alert(budget, threshold_percent=75.0)
        assert should_alert
        assert "80" in reason

    def test_status_calculation(self):
        """Test error budget status calculation."""
        now = datetime.utcnow()
        
        # Healthy: < 50%
        budget = ErrorBudget(
            slo_id="test",
            service="test-service",
            period_start=now - timedelta(days=30),
            period_end=now,
            total_budget_minutes=21.6,
            burned_minutes=10.0,
            remaining_minutes=11.6,
        )
        assert budget.calculate_status() == SLOStatus.HEALTHY
        
        # Warning: 50-80%
        budget.burned_minutes = 15.0
        budget.remaining_minutes = 6.6
        assert budget.calculate_status() == SLOStatus.WARNING
        
        # Critical: 80-95%
        budget.burned_minutes = 18.0
        budget.remaining_minutes = 3.6
        assert budget.calculate_status() == SLOStatus.CRITICAL
        
        # Exhausted: > 95%
        budget.burned_minutes = 21.0
        budget.remaining_minutes = 0.6
        assert budget.calculate_status() == SLOStatus.EXHAUSTED
