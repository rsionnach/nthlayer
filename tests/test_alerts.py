"""
Tests for alert generation module.
"""

import pytest
from nthlayer.alerts import AlertRule, AlertTemplateLoader


def test_alert_rule_from_dict():
    """Test parsing alert rule from dict"""
    data = {
        "alert": "PostgresqlDown",
        "expr": "pg_up == 0",
        "for": "0m",
        "labels": {"severity": "critical"},
        "annotations": {"summary": "Postgresql down", "description": "Postgresql instance is down"},
    }

    alert = AlertRule.from_dict(data, technology="postgres", category="databases")

    assert alert.name == "PostgresqlDown"
    assert alert.expr == "pg_up == 0"
    assert alert.severity == "critical"
    assert alert.is_critical()
    assert alert.is_down_alert()


def test_alert_rule_customize():
    """Test customizing alert for a service"""
    alert = AlertRule(
        name="PostgresqlDown",
        expr="pg_up == 0",
        severity="critical",
        summary="DB is down",
        description="Database unavailable",
        technology="postgres",
    )

    customized = alert.customize_for_service(
        service_name="search-api",
        team="platform",
        tier=1,
        notification_channel="pagerduty",
        runbook_url="https://runbooks.example.com",
    )

    assert customized.labels["service"] == "search-api"
    assert customized.labels["team"] == "platform"
    assert customized.labels["tier"] == "1"
    assert customized.annotations["channel"] == "pagerduty"
    assert "runbooks.example.com/search-api/PostgresqlDown" in customized.annotations["runbook"]


def test_alert_rule_to_prometheus():
    """Test converting alert to Prometheus format"""
    alert = AlertRule(
        name="TestAlert",
        expr="up == 0",
        duration="5m",
        severity="warning",
        labels={"env": "prod"},
        annotations={"summary": "Test alert"},
    )

    prometheus_format = alert.to_prometheus()

    assert prometheus_format["alert"] == "TestAlert"
    assert prometheus_format["expr"] == "up == 0"
    assert prometheus_format["for"] == "5m"
    assert prometheus_format["labels"]["env"] == "prod"
    assert prometheus_format["annotations"]["summary"] == "Test alert"


def test_alert_template_loader_postgres():
    """Test loading PostgreSQL alerts"""
    loader = AlertTemplateLoader()
    alerts = loader.load_technology("postgres")

    # Should load at least 10 PostgreSQL alerts
    assert len(alerts) >= 10

    # Check first alert
    assert alerts[0].technology == "postgres"
    assert alerts[0].category == "databases"

    # Should have critical alerts
    critical_alerts = [a for a in alerts if a.is_critical()]
    assert len(critical_alerts) > 0

    # Should have a "Down" alert
    down_alerts = [a for a in alerts if a.is_down_alert()]
    assert len(down_alerts) > 0


def test_extract_dependencies():
    """Test dependency extraction from service resources"""
    from nthlayer.generators.alerts import extract_dependencies
    from nthlayer.specs.models import Resource

    resources = [
        Resource(
            kind="Dependencies",
            name="upstream",
            spec={
                "databases": [
                    {"name": "postgres-main", "type": "postgres"},
                    {"name": "redis-cache", "type": "redis"},
                ]
            },
        )
    ]

    deps = extract_dependencies(resources)
    assert "postgres" in deps
    assert "redis" in deps
    assert len(deps) == 2


def test_extract_dependencies_no_type():
    """Test dependency extraction when type is inferred from name"""
    from nthlayer.generators.alerts import extract_dependencies
    from nthlayer.specs.models import Resource

    resources = [
        Resource(
            kind="Dependencies",
            name="upstream",
            spec={
                "databases": [
                    {"name": "postgres-main"},  # No explicit type
                    {"name": "redis-cache"},
                ]
            },
        )
    ]

    deps = extract_dependencies(resources)
    assert "postgres" in deps
    assert "redis" in deps


def test_filter_by_tier():
    """Test tier-based alert filtering"""
    from nthlayer.alerts import AlertRule
    from nthlayer.generators.alerts import filter_by_tier

    alerts = [
        AlertRule(name="Critical", expr="up==0", severity="critical", technology="postgres"),
        AlertRule(name="Warning", expr="up==1", severity="warning", technology="postgres"),
        AlertRule(name="Info", expr="up==2", severity="info", technology="postgres"),
    ]

    # Critical tier: all alerts
    filtered = filter_by_tier(alerts, "critical")
    assert len(filtered) == 3

    # Standard tier: critical + warning
    filtered = filter_by_tier(alerts, "standard")
    assert len(filtered) == 2
    assert all(a.severity in ["critical", "warning"] for a in filtered)

    # Low tier: only critical
    filtered = filter_by_tier(alerts, "low")
    assert len(filtered) == 1
    assert filtered[0].severity == "critical"


def test_generate_alerts_integration(tmp_path):
    """Test full alert generation workflow"""
    from nthlayer.generators.alerts import generate_alerts_for_service

    # Create temp service file
    service_file = tmp_path / "test-service.yaml"
    service_file.write_text("""
service:
  name: test-api
  team: test
  tier: critical
  type: api

resources:
  - kind: Dependencies
    name: upstream
    spec:
      databases:
        - name: postgres-main
          type: postgres
""")

    alerts = generate_alerts_for_service(service_file)

    # Should have postgres alerts
    assert len(alerts) > 0

    # All alerts should have service labels
    assert all(a.labels["service"] == "test-api" for a in alerts)
    assert all(a.labels["team"] == "test" for a in alerts)
    assert all(a.labels["tier"] == "critical" for a in alerts)

    # Should have postgres technology
    assert all(a.technology == "postgres" for a in alerts)


def test_generate_alerts_with_output(tmp_path):
    """Test alert generation with file output"""
    from nthlayer.generators.alerts import generate_alerts_for_service

    # Create temp service file
    service_file = tmp_path / "test-service.yaml"
    service_file.write_text("""
service:
  name: test-api
  team: test
  tier: standard
  type: api

resources:
  - kind: Dependencies
    name: upstream
    spec:
      databases:
        - type: redis
""")

    output_file = tmp_path / "alerts.yaml"
    alerts = generate_alerts_for_service(service_file, output_file)

    # Should have generated alerts
    assert len(alerts) > 0

    # Output file should exist
    assert output_file.exists()

    # Output should be valid YAML
    import yaml

    with open(output_file) as f:
        data = yaml.safe_load(f)

    assert "groups" in data
    assert len(data["groups"]) > 0
    assert "rules" in data["groups"][0]


def test_generate_alerts_quiet_mode(tmp_path, capsys):
    """Test that quiet mode suppresses progress output.

    This ensures JSON output from plan/apply commands isn't polluted
    by alert generator progress messages.
    """
    from nthlayer.generators.alerts import generate_alerts_for_service

    # Create temp service file with dependencies
    service_file = tmp_path / "test-service.yaml"
    service_file.write_text("""
service:
  name: test-api
  team: test
  tier: critical
  type: api

resources:
  - kind: Dependencies
    name: upstream
    spec:
      databases:
        - name: postgres-main
          type: postgres
""")

    # Generate alerts with quiet=True
    alerts = generate_alerts_for_service(service_file, quiet=True)

    # Should still generate alerts
    assert len(alerts) > 0

    # Should not produce any stdout output
    captured = capsys.readouterr()
    assert captured.out == "", f"Expected no output, but got: {captured.out}"


def test_generate_alerts_no_deps_quiet_mode(tmp_path, capsys):
    """Test that quiet mode suppresses output even when no dependencies."""
    from nthlayer.generators.alerts import generate_alerts_for_service

    # Create temp service file without dependencies
    service_file = tmp_path / "test-service.yaml"
    service_file.write_text("""
service:
  name: test-api
  team: test
  tier: critical
  type: api
""")

    # Generate alerts with quiet=True
    alerts = generate_alerts_for_service(service_file, quiet=True)

    # Should return empty list
    assert alerts == []

    # Should not produce any stdout output
    captured = capsys.readouterr()
    assert captured.out == "", f"Expected no output, but got: {captured.out}"


def test_alert_template_loader_caching():
    """Test that loader caches results"""
    loader = AlertTemplateLoader()

    # First load
    alerts1 = loader.load_technology("postgres")

    # Second load (should be cached)
    alerts2 = loader.load_technology("postgres")

    # Should be same objects (cached)
    assert alerts1 is alerts2


def test_alert_template_loader_aliases():
    """Test technology name aliases"""
    loader = AlertTemplateLoader()

    # All these should work (using _ prefix for unused results)
    pg_alerts = loader.load_technology("postgres")
    _postgresql_alerts = loader.load_technology("postgresql")
    _pg_short_alerts = loader.load_technology("pg")

    # Should all return alerts (exact match depends on implementation)
    assert len(pg_alerts) > 0


def test_alert_template_loader_unknown_technology():
    """Test loading unknown technology"""
    loader = AlertTemplateLoader()
    alerts = loader.load_technology("unknown-tech-xyz")

    # Should return empty list, not raise error
    assert alerts == []


@pytest.mark.skip("Requires full template library")
def test_list_available_technologies():
    """Test listing all available technologies"""
    loader = AlertTemplateLoader()
    techs = loader.list_available_technologies()

    # Should include postgres, redis, etc.
    assert "postgres" in techs
    assert len(techs) > 10


# --- Alert Validation Tests ---


class TestPromQLLabelExtraction:
    """Tests for PromQL label extraction from expressions."""

    def test_by_clause_extracts_labels(self):
        """Test that by() clause labels are extracted."""
        from nthlayer.alerts.validator import extract_promql_output_labels

        expr = "sum by (namespace, datname) (pg_stat_database_xact_rollback)"
        labels = extract_promql_output_labels(expr)

        assert labels == {"namespace", "datname"}

    def test_without_clause_marks_removed(self):
        """Test that without() clause marks labels as removed."""
        from nthlayer.alerts.validator import extract_promql_output_labels

        expr = "count without (instance, job) (redis_connected_slaves)"
        labels = extract_promql_output_labels(expr)

        # Should return negative markers for removed labels
        assert labels == {"!instance", "!job"}

    def test_bare_aggregation_returns_empty(self):
        """Test that bare aggregation (no by/without) returns empty set."""
        from nthlayer.alerts.validator import extract_promql_output_labels

        expr = "count(redis_instance_info{role='master'})"
        labels = extract_promql_output_labels(expr)

        assert labels == set()

    def test_no_aggregation_returns_none(self):
        """Test that no aggregation returns None (all labels preserved)."""
        from nthlayer.alerts.validator import extract_promql_output_labels

        expr = "pg_up == 0"
        labels = extract_promql_output_labels(expr)

        assert labels is None

    def test_multiple_by_clauses(self):
        """Test expressions with multiple by() clauses."""
        from nthlayer.alerts.validator import extract_promql_output_labels

        expr = "sum by (a) (x) / sum by (b, c) (y)"
        labels = extract_promql_output_labels(expr)

        assert labels == {"a", "b", "c"}


class TestAnnotationLabelExtraction:
    """Tests for extracting label references from annotations."""

    def test_extracts_label_references(self):
        """Test extraction of {{ $labels.xxx }} patterns."""
        from nthlayer.alerts.validator import extract_annotation_label_refs

        annotations = {
            "summary": "Alert on {{ $labels.instance }}",
            "description": "Service {{ $labels.service }} has {{ $labels.job }} issue",
        }

        labels = extract_annotation_label_refs(annotations)
        assert labels == {"instance", "service", "job"}

    def test_no_labels_returns_empty(self):
        """Test annotations with no label references."""
        from nthlayer.alerts.validator import extract_annotation_label_refs

        annotations = {
            "summary": "Static alert message",
            "description": "Value is {{ $value }}",
        }

        labels = extract_annotation_label_refs(annotations)
        assert labels == set()


class TestAlertValidation:
    """Tests for alert validation and fixing."""

    def test_fixes_invalid_label_reference_by_clause(self):
        """Test fixing invalid label reference when by() removes it."""
        alert = AlertRule(
            name="PostgresqlHighRollbackRate",
            expr="sum by (namespace, datname) (pg_stat_database_xact_rollback) > 0.02",
            duration="0m",
            severity="warning",
            annotations={
                "summary": "High rollback rate (instance {{ $labels.instance }})",
                "description": "Database {{ $labels.datname }} has issues",
            },
            technology="postgres",
        )

        fixed, result = alert.validate_and_fix()

        # Should have issues
        assert not result.is_valid
        assert len(result.issues) > 0
        assert len(result.fixes_applied) > 0

        # instance should be removed, datname should remain
        assert "{{ $labels.instance }}" not in fixed.annotations["summary"]
        assert "{{ $labels.datname }}" in fixed.annotations["description"]

    def test_fixes_invalid_label_reference_without_clause(self):
        """Test fixing invalid label when without() removes it."""
        alert = AlertRule(
            name="RedisDisconnectedSlaves",
            expr="count without (instance, job) (redis_connected_slaves) > 0",
            duration="0m",
            severity="warning",
            annotations={
                "summary": "Redis disconnected (instance {{ $labels.instance }})",
            },
            technology="redis",
        )

        fixed, result = alert.validate_and_fix()

        # Should detect and fix instance label
        assert not result.is_valid
        assert "{{ $labels.instance }}" not in fixed.annotations["summary"]

    def test_fixes_zero_duration(self):
        """Test fixing 'for: 0m' duration."""
        alert = AlertRule(
            name="TestAlert",
            expr="up == 0",
            duration="0m",
            severity="critical",
            annotations={"summary": "Test"},
            technology="postgres",
        )

        fixed, result = alert.validate_and_fix()

        # Should fix duration
        assert "1m" == fixed.duration
        assert any("for" in fix for fix in result.fixes_applied)

    def test_preserves_valid_alert(self):
        """Test that valid alerts are not modified."""
        alert = AlertRule(
            name="PostgresqlDown",
            expr="pg_up == 0",
            duration="5m",
            severity="critical",
            annotations={
                "summary": "Postgresql down (instance {{ $labels.instance }})",
            },
            technology="postgres",
        )

        fixed, result = alert.validate_and_fix()

        # No aggregation = all labels preserved, valid duration
        assert result.is_valid
        assert len(result.fixes_applied) == 0
        assert fixed.annotations == alert.annotations
        assert fixed.duration == alert.duration

    def test_fixes_bare_aggregation_label_refs(self):
        """Test fixing labels when bare aggregation removes all."""
        alert = AlertRule(
            name="RedisMissingMaster",
            expr="count(redis_instance_info{role='master'}) < 1",
            duration="5m",
            severity="critical",
            annotations={
                "summary": "Redis missing master (instance {{ $labels.instance }})",
            },
            technology="redis",
        )

        fixed, result = alert.validate_and_fix()

        # count() removes all labels
        assert not result.is_valid
        assert "{{ $labels.instance }}" not in fixed.annotations["summary"]


class TestAlertValidationIntegration:
    """Integration tests for alert validation in generation pipeline."""

    def test_generated_alerts_are_validated(self, tmp_path):
        """Test that generated alerts go through validation."""
        from nthlayer.generators.alerts import generate_alerts_for_service

        service_file = tmp_path / "test-service.yaml"
        service_file.write_text("""
service:
  name: test-api
  team: test
  tier: critical
  type: api

resources:
  - kind: Dependencies
    name: upstream
    spec:
      databases:
        - type: postgres
""")

        alerts = generate_alerts_for_service(service_file)

        # All alerts should have safe duration (not 0m)
        for alert in alerts:
            assert alert.duration != "0m", f"Alert {alert.name} has unsafe duration"
