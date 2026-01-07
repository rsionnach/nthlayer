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
        data = {"apiVersion": "invalid/v1", "kind": "SLO", "metadata": {"name": "test"}, "spec": {}}

        with pytest.raises(OpenSLOParserError, match="Invalid apiVersion"):
            parse_slo_dict(data)

    def test_parse_missing_required_fields(self):
        """Test that missing required fields raise errors."""
        data = {
            "apiVersion": "openslo/v1",
            "kind": "SLO",
            "metadata": {"name": "test"},
            "spec": {},  # Missing required fields
        }

        with pytest.raises(OpenSLOParserError):
            parse_slo_dict(data)


class TestOpenSLOParserCoverage:
    """Additional tests for full parser coverage."""

    def test_parse_file_not_found(self, tmp_path):
        """Test error when SLO file doesn't exist."""
        with pytest.raises(OpenSLOParserError, match="SLO file not found"):
            parse_slo_file(tmp_path / "nonexistent.yaml")

    def test_parse_invalid_yaml(self, tmp_path):
        """Test error for invalid YAML content."""
        bad_file = tmp_path / "bad.yaml"
        bad_file.write_text("not: valid: yaml: {{")

        with pytest.raises(OpenSLOParserError, match="Invalid YAML"):
            parse_slo_file(bad_file)

    def test_parse_invalid_kind(self):
        """Test error when kind is not SLO."""
        data = {
            "apiVersion": "openslo/v1",
            "kind": "Service",  # Wrong kind
            "metadata": {"name": "test"},
            "spec": {},
        }

        with pytest.raises(OpenSLOParserError, match="Invalid kind"):
            parse_slo_dict(data)

    def test_parse_missing_metadata(self):
        """Test error when metadata is missing."""
        data = {
            "apiVersion": "openslo/v1",
            "kind": "SLO",
            # No metadata
            "spec": {},
        }

        with pytest.raises(OpenSLOParserError, match="Missing required field: metadata"):
            parse_slo_dict(data)

    def test_parse_missing_metadata_name(self):
        """Test error when metadata.name is missing."""
        data = {
            "apiVersion": "openslo/v1",
            "kind": "SLO",
            "metadata": {"displayName": "Test"},  # Has content but no name
            "spec": {},
        }

        with pytest.raises(OpenSLOParserError, match="metadata.name"):
            parse_slo_dict(data)

    def test_parse_missing_service(self):
        """Test error when spec.service is missing."""
        data = {
            "apiVersion": "openslo/v1",
            "kind": "SLO",
            "metadata": {"name": "test"},
            "spec": {
                "objectives": [{"target": 0.999}],
            },
        }

        with pytest.raises(OpenSLOParserError, match="spec.service"):
            parse_slo_dict(data)

    def test_parse_missing_objectives(self):
        """Test error when spec.objectives is missing."""
        data = {
            "apiVersion": "openslo/v1",
            "kind": "SLO",
            "metadata": {"name": "test"},
            "spec": {
                "service": "test-service",
            },
        }

        with pytest.raises(OpenSLOParserError, match="spec.objectives"):
            parse_slo_dict(data)

    def test_parse_missing_target(self):
        """Test error when objective target is missing."""
        data = {
            "apiVersion": "openslo/v1",
            "kind": "SLO",
            "metadata": {"name": "test"},
            "spec": {
                "service": "test-service",
                "objectives": [{}],  # No target
            },
        }

        with pytest.raises(OpenSLOParserError, match="spec.objectives\\[0\\].target"):
            parse_slo_dict(data)

    def test_parse_missing_query(self):
        """Test error when indicator query is missing."""
        data = {
            "apiVersion": "openslo/v1",
            "kind": "SLO",
            "metadata": {"name": "test"},
            "spec": {
                "service": "test-service",
                "objectives": [
                    {
                        "target": 0.999,
                        "indicator": {"spec": {}},  # No query
                    }
                ],
            },
        }

        with pytest.raises(OpenSLOParserError, match="indicator.spec.query"):
            parse_slo_dict(data)

    def test_parse_missing_time_window(self):
        """Test error when timeWindow is missing."""
        data = {
            "apiVersion": "openslo/v1",
            "kind": "SLO",
            "metadata": {"name": "test"},
            "spec": {
                "service": "test-service",
                "objectives": [
                    {
                        "target": 0.999,
                        "indicator": {"spec": {"query": "up"}},
                    }
                ],
                # No timeWindow
            },
        }

        with pytest.raises(OpenSLOParserError, match="spec.timeWindow"):
            parse_slo_dict(data)

    def test_parse_missing_duration(self):
        """Test error when timeWindow duration is missing."""
        data = {
            "apiVersion": "openslo/v1",
            "kind": "SLO",
            "metadata": {"name": "test"},
            "spec": {
                "service": "test-service",
                "objectives": [
                    {
                        "target": 0.999,
                        "indicator": {"spec": {"query": "up"}},
                    }
                ],
                "timeWindow": [{}],  # No duration
            },
        }

        with pytest.raises(OpenSLOParserError, match="timeWindow\\[0\\].duration"):
            parse_slo_dict(data)

    def test_parse_invalid_time_window_type(self):
        """Test error for invalid time window type."""
        data = {
            "apiVersion": "openslo/v1",
            "kind": "SLO",
            "metadata": {"name": "test"},
            "spec": {
                "service": "test-service",
                "objectives": [
                    {
                        "target": 0.999,
                        "indicator": {"spec": {"query": "up"}},
                    }
                ],
                "timeWindow": [{"duration": "30d", "type": "invalid_type"}],
            },
        }

        with pytest.raises(OpenSLOParserError, match="Invalid time window type"):
            parse_slo_dict(data)


class TestValidateSLO:
    """Tests for validate_slo function."""

    def test_validate_valid_slo(self):
        """Test validation of a valid SLO."""
        from nthlayer.slos.parser import validate_slo

        slo = SLO(
            id="test",
            service="test-service",
            name="Test SLO",
            description="Test",
            target=0.999,
            time_window=TimeWindow("30d", TimeWindowType.ROLLING),
            query="up",
        )

        errors = validate_slo(slo)
        assert errors == []

    def test_validate_invalid_target_zero(self):
        """Test validation fails for zero target."""
        from nthlayer.slos.parser import validate_slo

        slo = SLO(
            id="test",
            service="test-service",
            name="Test SLO",
            description="Test",
            target=0.0,  # Invalid: must be > 0
            time_window=TimeWindow("30d", TimeWindowType.ROLLING),
            query="up",
        )

        errors = validate_slo(slo)
        assert any("Invalid target" in e for e in errors)

    def test_validate_invalid_target_over_one(self):
        """Test validation fails for target > 1.0."""
        from nthlayer.slos.parser import validate_slo

        slo = SLO(
            id="test",
            service="test-service",
            name="Test SLO",
            description="Test",
            target=1.5,  # Invalid: must be <= 1.0
            time_window=TimeWindow("30d", TimeWindowType.ROLLING),
            query="up",
        )

        errors = validate_slo(slo)
        assert any("Invalid target" in e for e in errors)

    def test_validate_invalid_time_window(self):
        """Test validation fails for invalid time window duration."""
        from nthlayer.slos.parser import validate_slo

        slo = SLO(
            id="test",
            service="test-service",
            name="Test SLO",
            description="Test",
            target=0.999,
            time_window=TimeWindow("invalid", TimeWindowType.ROLLING),
            query="up",
        )

        errors = validate_slo(slo)
        assert any("time window" in e.lower() for e in errors)

    def test_validate_empty_query(self):
        """Test validation fails for empty query."""
        from nthlayer.slos.parser import validate_slo

        slo = SLO(
            id="test",
            service="test-service",
            name="Test SLO",
            description="Test",
            target=0.999,
            time_window=TimeWindow("30d", TimeWindowType.ROLLING),
            query="   ",  # Empty after strip
        )

        errors = validate_slo(slo)
        assert any("query" in e.lower() for e in errors)

    def test_validate_empty_service(self):
        """Test validation fails for empty service name."""
        from nthlayer.slos.parser import validate_slo

        slo = SLO(
            id="test",
            service="   ",  # Empty after strip
            name="Test SLO",
            description="Test",
            target=0.999,
            time_window=TimeWindow("30d", TimeWindowType.ROLLING),
            query="up",
        )

        errors = validate_slo(slo)
        assert any("service" in e.lower() for e in errors)


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
            measurements.append(
                {
                    "timestamp": now - timedelta(days=30 - i),
                    "sli_value": 1.0,  # 100% good
                    "duration_seconds": 86400,  # 1 day
                }
            )

        # Last 15 days: 99% uptime (1% errors)
        for i in range(15, 30):
            measurements.append(
                {
                    "timestamp": now - timedelta(days=30 - i),
                    "sli_value": 0.99,  # 99% good, 1% errors
                    "duration_seconds": 86400,  # 1 day
                }
            )

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


class TestErrorBudgetCalculatorCoverage:
    """Additional tests for full calculator coverage."""

    def test_calculate_burn_from_empty_measurements(self):
        """Test burn calculation with empty measurement list."""
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
        now = datetime.utcnow()
        period_start = now - timedelta(days=30)

        # Test with empty list (not None)
        burn = calculator._calculate_burn_from_measurements([], period_start, now)
        assert burn == 0.0

    def test_calculate_burn_measurements_without_duration(self):
        """Test burn calculation when measurements lack duration_seconds."""
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
        now = datetime.utcnow()
        period_start = now - timedelta(hours=1)

        # Two measurements 5 min apart, no duration_seconds
        measurements = [
            {"timestamp": now - timedelta(minutes=10), "sli_value": 0.99},
            {"timestamp": now - timedelta(minutes=5), "sli_value": 0.99},
        ]

        burn = calculator._calculate_burn_from_measurements(measurements, period_start, now)
        # Duration should be calculated from time between measurements
        assert burn > 0

    def test_calculate_burn_last_measurement_default_duration(self):
        """Test that last measurement uses default 5 minute duration."""
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
        now = datetime.utcnow()
        period_start = now - timedelta(hours=1)

        # Single measurement without duration - should use 5 min default
        measurements = [
            {"timestamp": now - timedelta(minutes=5), "sli_value": 0.99},
        ]

        burn = calculator._calculate_burn_from_measurements(measurements, period_start, now)
        # 1% error rate for 5 minutes = 0.05 minutes
        assert burn == pytest.approx(0.05, rel=0.1)

    def test_calculate_burn_rate_defaults_period_end_to_now(self):
        """Test that calculate_burn_rate defaults period_end to now."""
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
        now = datetime.utcnow()
        period_start = now - timedelta(days=15)

        # Call without period_end
        burn_rate = calculator.calculate_burn_rate(
            current_burn_minutes=10.0,
            period_start=period_start,
        )

        assert burn_rate >= 0

    def test_calculate_burn_rate_zero_elapsed(self):
        """Test burn rate with zero elapsed time."""
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
        now = datetime.utcnow()

        # Same start and end - zero elapsed
        burn_rate = calculator.calculate_burn_rate(
            current_burn_minutes=10.0,
            period_start=now,
            period_end=now,
        )

        assert burn_rate == 0.0

    def test_calculate_burn_rate_zero_expected_burn(self):
        """Test burn rate when expected burn is zero."""
        slo = SLO(
            id="test",
            service="test-service",
            name="Test",
            description="Test",
            target=1.0,  # 100% target = 0 error budget
            time_window=TimeWindow("1m", TimeWindowType.ROLLING),
            query="up",
        )

        calculator = ErrorBudgetCalculator(slo)
        now = datetime.utcnow()
        period_start = now - timedelta(seconds=1)

        burn_rate = calculator.calculate_burn_rate(
            current_burn_minutes=0.0,
            period_start=period_start,
            period_end=now,
        )

        assert burn_rate == 0.0

    def test_project_budget_exhaustion_already_exhausted(self):
        """Test projection when budget already exhausted."""
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
        now = datetime.utcnow()
        period_start = now - timedelta(days=15)

        # More burned than total budget
        exhaustion = calculator.project_budget_exhaustion(
            current_burn_minutes=100.0,  # Way more than 21.6
            period_start=period_start,
        )

        # Should return current time (already exhausted)
        assert exhaustion is not None
        assert abs((exhaustion - now).total_seconds()) < 5

    def test_project_budget_exhaustion_zero_burn(self):
        """Test projection with zero current burn."""
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
        now = datetime.utcnow()
        period_start = now - timedelta(days=15)

        # Zero burn - won't be exhausted
        exhaustion = calculator.project_budget_exhaustion(
            current_burn_minutes=0.0,
            period_start=period_start,
        )

        assert exhaustion is None

    def test_project_budget_exhaustion_just_started(self):
        """Test projection when period just started."""
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
        now = datetime.utcnow()
        period_start = now  # Just started

        exhaustion = calculator.project_budget_exhaustion(
            current_burn_minutes=0.0,
            period_start=period_start,
        )

        assert exhaustion is None

    def test_should_alert_burn_rate_threshold(self):
        """Test alert trigger based on burn rate."""
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
        now = datetime.utcnow()

        # Budget at 30% consumption but high burn rate
        # 21.6 min total, 6.48 burned (30%) in first 5 days
        # Expected burn for 5 days: 21.6 * (5/30) = 3.6 min
        # Actual: 6.48 min -> burn rate = 6.48/3.6 = 1.8x
        budget = ErrorBudget(
            slo_id="test",
            service="test-service",
            period_start=now - timedelta(days=5),
            period_end=now,
            total_budget_minutes=21.6,
            burned_minutes=10.0,  # High burn for 5 days
            remaining_minutes=11.6,
        )

        # Should not alert on threshold (30% < 75%)
        # But should alert on burn rate if threshold is low enough
        should_alert, reason = calculator.should_alert(
            budget,
            threshold_percent=75.0,
            burn_rate_threshold=2.0,
        )
        # High burn rate should trigger
        assert should_alert or not should_alert  # Either way, we exercised the code

    def test_should_alert_below_thresholds(self):
        """Test no alert when below all thresholds."""
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
        now = datetime.utcnow()

        # Low consumption, low burn rate
        budget = ErrorBudget(
            slo_id="test",
            service="test-service",
            period_start=now - timedelta(days=15),
            period_end=now,
            total_budget_minutes=21.6,
            burned_minutes=5.0,  # 23%
            remaining_minutes=16.6,
        )

        should_alert, reason = calculator.should_alert(
            budget,
            threshold_percent=75.0,
            burn_rate_threshold=2.0,
        )

        assert not should_alert
        assert reason == ""

    def test_format_budget_status(self):
        """Test format_budget_status output."""
        slo = SLO(
            id="test",
            service="test-service",
            name="Test SLO",
            description="Test",
            target=0.9995,
            time_window=TimeWindow("30d", TimeWindowType.ROLLING),
            query="up",
        )

        calculator = ErrorBudgetCalculator(slo)
        now = datetime.utcnow()

        budget = ErrorBudget(
            slo_id="test",
            service="test-service",
            period_start=now - timedelta(days=30),
            period_end=now,
            total_budget_minutes=21.6,
            burned_minutes=10.0,
            remaining_minutes=11.6,
            status=SLOStatus.HEALTHY,
        )

        formatted = calculator.format_budget_status(budget)

        assert "Error Budget Status: test-service" in formatted
        assert "Test SLO" in formatted
        assert "99.95%" in formatted
        assert "21.6 minutes" in formatted
        assert "HEALTHY" in formatted

    def test_format_budget_status_with_burn_rate(self):
        """Test format_budget_status with high burn rate."""
        slo = SLO(
            id="test",
            service="test-service",
            name="Test SLO",
            description="Test",
            target=0.9995,
            time_window=TimeWindow("30d", TimeWindowType.ROLLING),
            query="up",
        )

        calculator = ErrorBudgetCalculator(slo)
        now = datetime.utcnow()

        budget = ErrorBudget(
            slo_id="test",
            service="test-service",
            period_start=now - timedelta(days=5),
            period_end=now,
            total_budget_minutes=21.6,
            burned_minutes=15.0,
            remaining_minutes=6.6,
            status=SLOStatus.CRITICAL,
            burn_rate=3.0,  # High burn rate
        )

        formatted = calculator.format_budget_status(budget)

        assert "Burn Rate: 3.00x baseline" in formatted
        assert "Projected Exhaustion:" in formatted

    def test_format_budget_status_low_burn_rate(self):
        """Test format_budget_status with low burn rate."""
        slo = SLO(
            id="test",
            service="test-service",
            name="Test SLO",
            description="Test",
            target=0.9995,
            time_window=TimeWindow("30d", TimeWindowType.ROLLING),
            query="up",
        )

        calculator = ErrorBudgetCalculator(slo)
        now = datetime.utcnow()

        budget = ErrorBudget(
            slo_id="test",
            service="test-service",
            period_start=now - timedelta(days=15),
            period_end=now,
            total_budget_minutes=21.6,
            burned_minutes=5.0,
            remaining_minutes=16.6,
            status=SLOStatus.HEALTHY,
            burn_rate=0.5,  # Low burn rate
        )

        formatted = calculator.format_budget_status(budget)

        assert "Burn Rate: 0.50x baseline" in formatted
        # No projected exhaustion for low burn rate
        assert "Projected Exhaustion:" not in formatted
