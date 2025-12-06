"""Tests for Loki LogQL alert generation."""

from nthlayer.loki import LogQLAlert, LokiAlertGenerator, get_patterns_for_technology
from nthlayer.loki.templates import (
    KAFKA_PATTERNS,
    KUBERNETES_PATTERNS,
    POSTGRESQL_PATTERNS,
    REDIS_PATTERNS,
    list_available_technologies,
)


class TestLogPatterns:
    """Test log pattern templates."""

    def test_postgresql_patterns_exist(self):
        """PostgreSQL patterns should be defined."""
        assert len(POSTGRESQL_PATTERNS) > 0
        pattern_names = [p.name for p in POSTGRESQL_PATTERNS]
        assert "PostgresqlFatalError" in pattern_names
        assert "PostgresqlDeadlock" in pattern_names

    def test_redis_patterns_exist(self):
        """Redis patterns should be defined."""
        assert len(REDIS_PATTERNS) > 0
        pattern_names = [p.name for p in REDIS_PATTERNS]
        assert "RedisOutOfMemory" in pattern_names
        assert "RedisConnectionRefused" in pattern_names

    def test_kafka_patterns_exist(self):
        """Kafka patterns should be defined."""
        assert len(KAFKA_PATTERNS) > 0
        pattern_names = [p.name for p in KAFKA_PATTERNS]
        assert "KafkaUnderReplicatedPartitions" in pattern_names
        assert "KafkaBrokerDown" in pattern_names

    def test_kubernetes_patterns_exist(self):
        """Kubernetes patterns should be defined."""
        assert len(KUBERNETES_PATTERNS) > 0
        pattern_names = [p.name for p in KUBERNETES_PATTERNS]
        assert "KubernetesOOMKilled" in pattern_names
        assert "KubernetesCrashLoopBackOff" in pattern_names

    def test_get_patterns_for_technology(self):
        """Should return patterns for known technologies."""
        pg_patterns = get_patterns_for_technology("postgresql")
        assert len(pg_patterns) > 0

        # Test aliases
        pg_patterns_alias = get_patterns_for_technology("postgres")
        assert len(pg_patterns_alias) == len(pg_patterns)

        pg_patterns_alias2 = get_patterns_for_technology("pg")
        assert len(pg_patterns_alias2) == len(pg_patterns)

    def test_get_patterns_unknown_technology(self):
        """Unknown technology should return application patterns."""
        patterns = get_patterns_for_technology("unknown_tech")
        assert len(patterns) > 0  # Returns APPLICATION_PATTERNS

    def test_list_available_technologies(self):
        """Should list all available technologies."""
        techs = list_available_technologies()
        assert "postgresql" in techs
        assert "redis" in techs
        assert "kafka" in techs
        assert "kubernetes" in techs


class TestLogQLAlert:
    """Test LogQLAlert model."""

    def test_alert_creation(self):
        """Should create alert with required fields."""
        alert = LogQLAlert(
            name="TestAlert",
            expr='count_over_time({app="test"} |= "error" [5m]) > 0',
            severity="warning",
        )
        assert alert.name == "TestAlert"
        assert alert.severity == "warning"
        assert "error" in alert.expr

    def test_alert_to_ruler_format(self):
        """Should convert to Loki ruler format."""
        alert = LogQLAlert(
            name="TestAlert",
            expr='count_over_time({app="test"} |= "error" [5m]) > 0',
            severity="critical",
            for_duration="5m",
            summary="Test alert fired",
            description="Test alert description",
            technology="postgresql",
        )
        ruler = alert.to_ruler_format()

        assert ruler["alert"] == "TestAlert"
        assert ruler["expr"] == alert.expr
        assert ruler["for"] == "5m"
        assert ruler["labels"]["severity"] == "critical"
        assert ruler["labels"]["technology"] == "postgresql"
        assert ruler["annotations"]["summary"] == "Test alert fired"

    def test_alert_from_dict(self):
        """Should create alert from dictionary."""
        data = {
            "alert": "DictAlert",
            "expr": "some_expr",
            "for": "10m",
            "labels": {"severity": "warning", "custom": "value"},
            "annotations": {"summary": "Dict summary", "description": "Dict desc"},
        }
        alert = LogQLAlert.from_dict(data, technology="redis")

        assert alert.name == "DictAlert"
        assert alert.expr == "some_expr"
        assert alert.for_duration == "10m"
        assert alert.severity == "warning"
        assert alert.technology == "redis"


class TestLokiAlertGenerator:
    """Test Loki alert generator."""

    def test_generator_creation(self):
        """Should create generator with default namespace."""
        gen = LokiAlertGenerator()
        assert gen.namespace == "nthlayer"

    def test_generator_custom_namespace(self):
        """Should create generator with custom namespace."""
        gen = LokiAlertGenerator(namespace="myproject")
        assert gen.namespace == "myproject"

    def test_generate_for_service_basic(self):
        """Should generate alerts for a basic service."""
        gen = LokiAlertGenerator()
        alerts = gen.generate_for_service(
            service_name="test-api",
            service_type="api",
        )
        assert len(alerts) > 0
        assert all(isinstance(a, LogQLAlert) for a in alerts)

    def test_generate_for_service_with_dependencies(self):
        """Should generate alerts for service with dependencies."""
        gen = LokiAlertGenerator()
        alerts = gen.generate_for_service(
            service_name="payment-api",
            service_type="api",
            dependencies=["postgresql", "redis"],
        )

        # Should have service alerts + dependency alerts
        service_alerts = [a for a in alerts if a.category == "service"]
        dep_alerts = [a for a in alerts if a.category == "dependency"]

        assert len(service_alerts) > 0
        assert len(dep_alerts) > 0

        # Check for PostgreSQL alerts
        pg_alerts = [a for a in dep_alerts if a.technology == "postgresql"]
        assert len(pg_alerts) > 0

        # Check for Redis alerts
        redis_alerts = [a for a in dep_alerts if a.technology == "redis"]
        assert len(redis_alerts) > 0

    def test_generate_for_service_tier_labels(self):
        """Should include tier in alert labels."""
        gen = LokiAlertGenerator()
        alerts = gen.generate_for_service(
            service_name="critical-api",
            service_type="api",
            tier="critical",
        )

        for alert in alerts:
            ruler = alert.to_ruler_format()
            assert ruler["labels"]["tier"] == "critical"

    def test_to_ruler_yaml(self):
        """Should generate valid YAML output."""
        gen = LokiAlertGenerator()
        alerts = gen.generate_for_service(
            service_name="test-api",
            service_type="api",
        )

        yaml_output = gen.to_ruler_yaml(alerts, group_name="test-group")

        assert "groups:" in yaml_output
        assert "name: test-group" in yaml_output
        assert "rules:" in yaml_output
        assert "alert:" in yaml_output

    def test_logql_expression_format(self):
        """Should generate valid LogQL expressions."""
        gen = LokiAlertGenerator()
        alerts = gen.generate_for_service(
            service_name="test-api",
            service_type="api",
            dependencies=["postgresql"],
        )

        for alert in alerts:
            # LogQL expressions should have proper format
            assert "{" in alert.expr  # Label selector
            assert "}" in alert.expr
            assert "|" in alert.expr or "count_over_time" in alert.expr

    def test_alert_names_are_unique(self):
        """Alert names should be unique within a service."""
        gen = LokiAlertGenerator()
        alerts = gen.generate_for_service(
            service_name="test-api",
            service_type="api",
            dependencies=["postgresql", "redis", "kafka"],
        )

        names = [a.name for a in alerts]
        assert len(names) == len(set(names)), "Duplicate alert names found"


class TestLogQLExpressions:
    """Test LogQL expression generation."""

    def test_threshold_based_expression(self):
        """Threshold patterns should use sum/count_over_time."""
        gen = LokiAlertGenerator()
        alerts = gen.generate_for_service(
            service_name="test-api",
            service_type="api",
        )

        # Find an alert with threshold
        threshold_alerts = [a for a in alerts if "> 10" in a.expr or "> 100" in a.expr]
        assert len(threshold_alerts) > 0

        for alert in threshold_alerts:
            assert "sum(count_over_time" in alert.expr

    def test_existence_based_expression(self):
        """Non-threshold patterns should check for existence."""
        gen = LokiAlertGenerator()
        alerts = gen.generate_for_service(
            service_name="test-api",
            service_type="api",
            dependencies=["postgresql"],
        )

        # Fatal error alerts should trigger on any occurrence
        fatal_alerts = [a for a in alerts if "Fatal" in a.name or "Panic" in a.name]
        assert len(fatal_alerts) > 0

        for alert in fatal_alerts:
            assert "> 0" in alert.expr
