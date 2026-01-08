"""Tests for dashboards/validator.py.

Tests for dashboard validation logic including ValidationResult,
DashboardValidator, and extraction functions.
"""

from unittest.mock import MagicMock, patch

from nthlayer.dashboards.resolver import ResolutionStatus
from nthlayer.dashboards.validator import (
    DashboardValidator,
    IntentResult,
    ValidationResult,
    extract_custom_overrides,
    extract_technologies,
)


class TestIntentResult:
    """Tests for IntentResult dataclass."""

    def test_create_resolved_intent(self):
        """Test creating a resolved intent result."""
        result = IntentResult(
            name="postgresql.connections.active",
            status=ResolutionStatus.RESOLVED,
            metric_name="pg_stat_activity_count",
        )

        assert result.name == "postgresql.connections.active"
        assert result.status == ResolutionStatus.RESOLVED
        assert result.metric_name == "pg_stat_activity_count"
        assert result.message is None
        assert result.synthesis_expr is None

    def test_create_unresolved_intent(self):
        """Test creating an unresolved intent result."""
        result = IntentResult(
            name="postgresql.missing",
            status=ResolutionStatus.UNRESOLVED,
            message="No matching metric found",
        )

        assert result.name == "postgresql.missing"
        assert result.status == ResolutionStatus.UNRESOLVED
        assert result.metric_name is None
        assert result.message == "No matching metric found"

    def test_create_synthesized_intent(self):
        """Test creating a synthesized intent result."""
        result = IntentResult(
            name="postgresql.rate",
            status=ResolutionStatus.SYNTHESIZED,
            metric_name="synthesized_rate",
            synthesis_expr="rate(pg_total[5m])",
        )

        assert result.status == ResolutionStatus.SYNTHESIZED
        assert result.synthesis_expr == "rate(pg_total[5m])"


class TestValidationResult:
    """Tests for ValidationResult dataclass."""

    def test_empty_result(self):
        """Test empty validation result."""
        result = ValidationResult()

        assert result.total == 0
        assert result.resolved_count == 0
        assert result.has_unresolved is False
        assert result.get_exit_code(has_prometheus=True) == 0

    def test_total_property(self):
        """Test total property calculation."""
        result = ValidationResult(
            resolved=[IntentResult(name="r1", status=ResolutionStatus.RESOLVED)],
            fallback=[IntentResult(name="f1", status=ResolutionStatus.FALLBACK)],
            unresolved=[IntentResult(name="u1", status=ResolutionStatus.UNRESOLVED)],
            custom=[IntentResult(name="c1", status=ResolutionStatus.CUSTOM)],
            synthesized=[IntentResult(name="s1", status=ResolutionStatus.SYNTHESIZED)],
        )

        assert result.total == 5

    def test_resolved_count_includes_synthesized(self):
        """Test resolved_count includes synthesized intents."""
        result = ValidationResult(
            resolved=[
                IntentResult(name="r1", status=ResolutionStatus.RESOLVED),
                IntentResult(name="r2", status=ResolutionStatus.RESOLVED),
            ],
            synthesized=[
                IntentResult(name="s1", status=ResolutionStatus.SYNTHESIZED),
            ],
        )

        assert result.resolved_count == 3

    def test_has_unresolved(self):
        """Test has_unresolved property."""
        result = ValidationResult(
            resolved=[IntentResult(name="r1", status=ResolutionStatus.RESOLVED)],
            unresolved=[IntentResult(name="u1", status=ResolutionStatus.UNRESOLVED)],
        )

        assert result.has_unresolved is True

    def test_get_exit_code_success(self):
        """Test exit code 0 for successful validation."""
        result = ValidationResult(
            resolved=[IntentResult(name="r1", status=ResolutionStatus.RESOLVED)],
        )

        assert result.get_exit_code(has_prometheus=True) == 0
        assert result.get_exit_code(has_prometheus=False) == 0

    def test_get_exit_code_unresolved_with_prometheus(self):
        """Test exit code 2 for unresolved with prometheus."""
        result = ValidationResult(
            unresolved=[IntentResult(name="u1", status=ResolutionStatus.UNRESOLVED)],
        )

        assert result.get_exit_code(has_prometheus=True) == 2

    def test_get_exit_code_unresolved_without_prometheus(self):
        """Test exit code 0 for unresolved without prometheus."""
        result = ValidationResult(
            unresolved=[IntentResult(name="u1", status=ResolutionStatus.UNRESOLVED)],
        )

        assert result.get_exit_code(has_prometheus=False) == 0


class TestDashboardValidator:
    """Tests for DashboardValidator class."""

    def test_init_with_url(self):
        """Test validator initialization with URL."""
        validator = DashboardValidator(prometheus_url="http://prometheus:9090")

        assert validator.prometheus_url == "http://prometheus:9090"

    def test_init_without_url(self):
        """Test validator initialization without URL."""
        validator = DashboardValidator()

        assert validator.prometheus_url is None

    @patch("nthlayer.dashboards.validator.create_resolver")
    @patch("nthlayer.dashboards.validator.get_intents_for_technology")
    def test_validate_without_prometheus(self, mock_get_intents, mock_create_resolver):
        """Test validation without prometheus URL."""
        mock_resolver = MagicMock()
        mock_resolution = MagicMock()
        mock_resolution.status = ResolutionStatus.UNRESOLVED
        mock_resolution.metric_name = None
        mock_resolution.message = "No discovery"
        mock_resolver.resolve.return_value = mock_resolution
        mock_create_resolver.return_value = mock_resolver

        mock_get_intents.return_value = {"postgresql.test": MagicMock()}

        validator = DashboardValidator()
        result = validator.validate(
            service_name="test-service",
            technologies={"postgresql"},
        )

        assert result.discovery_count == 0
        mock_resolver.discover_for_service.assert_not_called()

    @patch("nthlayer.dashboards.validator.create_resolver")
    @patch("nthlayer.dashboards.validator.get_intents_for_technology")
    def test_validate_with_prometheus_discovery(self, mock_get_intents, mock_create_resolver):
        """Test validation with prometheus discovery."""
        mock_resolver = MagicMock()
        mock_resolver.discover_for_service.return_value = 50
        mock_resolution = MagicMock()
        mock_resolution.status = ResolutionStatus.RESOLVED
        mock_resolution.metric_name = "pg_test"
        mock_resolution.message = None
        mock_resolver.resolve.return_value = mock_resolution
        mock_create_resolver.return_value = mock_resolver

        mock_get_intents.return_value = {"postgresql.test": MagicMock()}

        validator = DashboardValidator(prometheus_url="http://prometheus:9090")
        result = validator.validate(
            service_name="test-service",
            technologies={"postgresql"},
        )

        assert result.discovery_count == 50
        mock_resolver.discover_for_service.assert_called_once_with("test-service")

    @patch("nthlayer.dashboards.validator.create_resolver")
    @patch("nthlayer.dashboards.validator.get_intents_for_technology")
    def test_validate_discovery_error(self, mock_get_intents, mock_create_resolver):
        """Test validation handles discovery errors."""
        mock_resolver = MagicMock()
        mock_resolver.discover_for_service.side_effect = ConnectionError("Connection refused")
        mock_create_resolver.return_value = mock_resolver

        mock_get_intents.return_value = {}

        validator = DashboardValidator(prometheus_url="http://prometheus:9090")
        result = validator.validate(
            service_name="test-service",
            technologies={"postgresql"},
        )

        assert result.discovery_error == "Connection refused"

    @patch("nthlayer.dashboards.validator.create_resolver")
    @patch(
        "nthlayer.dashboards.validator.ALL_INTENTS",
        {"intent.one": MagicMock(), "intent.two": MagicMock()},
    )
    def test_validate_all_intents(self, mock_create_resolver):
        """Test validating all intents."""
        mock_resolver = MagicMock()
        mock_resolution = MagicMock()
        mock_resolution.status = ResolutionStatus.RESOLVED
        mock_resolution.metric_name = "test"
        mock_resolution.message = None
        mock_resolver.resolve.return_value = mock_resolution
        mock_create_resolver.return_value = mock_resolver

        validator = DashboardValidator()
        result = validator.validate(
            service_name="test-service",
            technologies=set(),
            validate_all=True,
        )

        assert result.total == 2

    @patch("nthlayer.dashboards.validator.create_resolver")
    @patch("nthlayer.dashboards.validator.get_intents_for_technology")
    def test_validate_categorizes_results(self, mock_get_intents, mock_create_resolver):
        """Test that validation categorizes results correctly."""
        mock_resolver = MagicMock()

        # Create different resolution types using startswith for exact matching
        def mock_resolve(intent_name):
            resolution = MagicMock()
            if intent_name.startswith("ok."):
                resolution.status = ResolutionStatus.RESOLVED
            elif intent_name.startswith("custom."):
                resolution.status = ResolutionStatus.CUSTOM
            elif intent_name.startswith("fallback."):
                resolution.status = ResolutionStatus.FALLBACK
            elif intent_name.startswith("synth."):
                resolution.status = ResolutionStatus.SYNTHESIZED
            else:
                resolution.status = ResolutionStatus.UNRESOLVED
            resolution.metric_name = f"metric_{intent_name}"
            resolution.message = None
            return resolution

        mock_resolver.resolve.side_effect = mock_resolve
        mock_create_resolver.return_value = mock_resolver

        mock_get_intents.return_value = {
            "ok.intent": MagicMock(),
            "custom.intent": MagicMock(),
            "fallback.intent": MagicMock(),
            "synth.intent": MagicMock(),
            "missing.intent": MagicMock(),
        }

        validator = DashboardValidator()
        result = validator.validate(
            service_name="test-service",
            technologies={"test"},
        )

        assert len(result.resolved) == 1
        assert len(result.custom) == 1
        assert len(result.fallback) == 1
        assert len(result.synthesized) == 1
        assert len(result.unresolved) == 1

    @patch("nthlayer.dashboards.validator.create_resolver")
    @patch("nthlayer.dashboards.validator.get_intents_for_technology")
    def test_validate_with_custom_overrides(self, mock_get_intents, mock_create_resolver):
        """Test validation passes custom overrides to resolver."""
        mock_resolver = MagicMock()
        mock_create_resolver.return_value = mock_resolver
        mock_get_intents.return_value = {}

        validator = DashboardValidator()
        custom_overrides = {"postgresql.connections": "custom_metric"}

        validator.validate(
            service_name="test-service",
            technologies=set(),
            custom_overrides=custom_overrides,
        )

        mock_create_resolver.assert_called_once_with(
            prometheus_url=None,
            custom_overrides=custom_overrides,
        )


class TestExtractTechnologies:
    """Tests for extract_technologies function."""

    def test_extract_from_databases(self):
        """Test extracting technologies from databases."""
        context = MagicMock()
        context.type = "worker"

        resource = MagicMock()
        resource.kind = "Dependencies"
        resource.spec = {
            "databases": [
                {"type": "postgresql"},
                {"type": "mysql"},
            ],
        }

        result = extract_technologies(context, [resource])

        assert "postgresql" in result
        assert "mysql" in result

    def test_extract_from_caches(self):
        """Test extracting technologies from caches."""
        context = MagicMock()
        context.type = "worker"

        resource = MagicMock()
        resource.kind = "Dependencies"
        resource.spec = {
            "caches": [
                {"type": "redis"},
                {"type": "memcached"},
            ],
        }

        result = extract_technologies(context, [resource])

        assert "redis" in result
        assert "memcached" in result

    def test_extract_default_cache_type(self):
        """Test default cache type is redis."""
        context = MagicMock()
        context.type = "worker"

        resource = MagicMock()
        resource.kind = "Dependencies"
        resource.spec = {
            "caches": [{}],  # No explicit type
        }

        result = extract_technologies(context, [resource])

        assert "redis" in result

    def test_adds_http_for_api_services(self):
        """Test HTTP is added for API services."""
        context = MagicMock()
        context.type = "api"

        result = extract_technologies(context, [])

        assert "http" in result

    def test_adds_http_for_web_services(self):
        """Test HTTP is added for web services."""
        context = MagicMock()
        context.type = "web"

        result = extract_technologies(context, [])

        assert "http" in result

    def test_no_http_for_workers(self):
        """Test HTTP is not added for worker services."""
        context = MagicMock()
        context.type = "worker"

        result = extract_technologies(context, [])

        assert "http" not in result

    def test_handles_non_dict_spec(self):
        """Test handles non-dict spec gracefully."""
        context = MagicMock()
        context.type = "worker"

        resource = MagicMock()
        resource.kind = "Dependencies"
        resource.spec = "invalid"

        result = extract_technologies(context, [resource])

        assert result == set()

    def test_handles_empty_databases(self):
        """Test handles empty databases list."""
        context = MagicMock()
        context.type = "api"

        resource = MagicMock()
        resource.kind = "Dependencies"
        resource.spec = {"databases": []}

        result = extract_technologies(context, [resource])

        assert "http" in result
        assert len(result) == 1

    def test_handles_object_style_databases(self):
        """Test handles object-style database entries."""
        context = MagicMock()
        context.type = "worker"

        db_obj = MagicMock()
        db_obj.type = "mongodb"

        resource = MagicMock()
        resource.kind = "Dependencies"
        resource.spec = {"databases": [db_obj]}

        result = extract_technologies(context, [resource])

        assert "mongodb" in result


class TestExtractCustomOverrides:
    """Tests for extract_custom_overrides function."""

    def test_extract_metrics_from_spec(self):
        """Test extracting metrics from resource spec."""
        resource = MagicMock()
        resource.spec = {
            "metrics": {
                "postgresql.connections": "custom_pg_connections",
                "redis.connections": "custom_redis_connections",
            }
        }

        result = extract_custom_overrides([resource])

        assert result["postgresql.connections"] == "custom_pg_connections"
        assert result["redis.connections"] == "custom_redis_connections"

    def test_merges_from_multiple_resources(self):
        """Test merging metrics from multiple resources."""
        resource1 = MagicMock()
        resource1.spec = {"metrics": {"metric.one": "value1"}}

        resource2 = MagicMock()
        resource2.spec = {"metrics": {"metric.two": "value2"}}

        result = extract_custom_overrides([resource1, resource2])

        assert result["metric.one"] == "value1"
        assert result["metric.two"] == "value2"

    def test_handles_no_spec(self):
        """Test handles resources without spec."""
        resource = MagicMock(spec=[])  # spec is a list, not dict
        delattr(resource, "spec")

        result = extract_custom_overrides([resource])

        assert result == {}

    def test_handles_no_metrics(self):
        """Test handles spec without metrics key."""
        resource = MagicMock()
        resource.spec = {"other": "value"}

        result = extract_custom_overrides([resource])

        assert result == {}

    def test_handles_non_dict_metrics(self):
        """Test handles non-dict metrics value."""
        resource = MagicMock()
        resource.spec = {"metrics": "invalid"}

        result = extract_custom_overrides([resource])

        assert result == {}

    def test_empty_resources_list(self):
        """Test empty resources list."""
        result = extract_custom_overrides([])

        assert result == {}
