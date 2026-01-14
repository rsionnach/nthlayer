"""
Tests for the awesome-prometheus-alerts sync script.
"""

import tempfile
from pathlib import Path

import yaml

# Import from scripts directory
import sys

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

from sync_awesome_alerts import (
    ConvertedAlert,
    alert_to_prometheus_dict,
    apply_nthlayer_fixes,
    group_by_technology,
    guess_category,
    normalize_alert_name,
    parse_upstream_rules,
    write_template_file,
)


class TestNormalizeAlertName:
    """Tests for alert name normalization."""

    def test_simple_name(self):
        assert normalize_alert_name("Prometheus job missing") == "PrometheusJobMissing"

    def test_hyphenated_name(self):
        assert normalize_alert_name("Redis-missing-master") == "RedisMissingMaster"

    def test_underscored_name(self):
        assert normalize_alert_name("host_cpu_high") == "HostCpuHigh"

    def test_mixed_separators(self):
        assert normalize_alert_name("MySQL slow-queries_high") == "MysqlSlowQueriesHigh"


class TestGuessCategory:
    """Tests for category guessing from service names."""

    def test_postgresql(self):
        category, tech = guess_category("PostgreSQL", "Databases")
        assert category == "databases"
        assert tech == "postgres"

    def test_redis(self):
        category, tech = guess_category("Redis", "Databases")
        assert category == "databases"
        assert tech == "redis"

    def test_kubernetes(self):
        category, tech = guess_category("Kubernetes", "Container orchestration")
        assert category == "orchestrators"
        assert tech == "kubernetes"

    def test_prometheus(self):
        category, tech = guess_category("Prometheus self-monitoring", "Basic monitoring")
        assert category == "monitoring"
        assert tech == "prometheus"

    def test_unknown_defaults_to_other(self):
        category, tech = guess_category("Some Unknown Service", "Unknown Group")
        assert category == "other"
        assert tech == "some-unknown-service"


class TestParseUpstreamRules:
    """Tests for parsing upstream rules.yml format."""

    def test_parse_simple_rule(self):
        rules_yaml = """
groups:
  - name: Databases
    services:
      - name: PostgreSQL
        exporters:
          - slug: postgres-exporter
            rules:
              - name: Postgresql down
                description: PostgreSQL instance is down
                query: pg_up == 0
                severity: critical
"""
        alerts = parse_upstream_rules(rules_yaml)

        assert len(alerts) == 1
        assert alerts[0].name == "PostgresqlDown"
        assert alerts[0].expr == "pg_up == 0"
        assert alerts[0].severity == "critical"
        assert alerts[0].technology == "postgres"

    def test_parse_rule_with_for_duration(self):
        rules_yaml = """
groups:
  - name: Monitoring
    services:
      - name: Prometheus self-monitoring
        exporters:
          - slug: embedded
            rules:
              - name: Prometheus rule evaluation slow
                description: Rule evaluation is slow
                query: 'prometheus_rule_group_last_duration_seconds > 30'
                severity: warning
                for: 5m
"""
        alerts = parse_upstream_rules(rules_yaml)

        assert len(alerts) == 1
        assert alerts[0].duration == "5m"

    def test_parse_multiple_services(self):
        rules_yaml = """
groups:
  - name: Databases
    services:
      - name: PostgreSQL
        exporters:
          - slug: postgres-exporter
            rules:
              - name: Postgresql down
                query: pg_up == 0
                severity: critical
      - name: Redis
        exporters:
          - slug: redis-exporter
            rules:
              - name: Redis down
                query: redis_up == 0
                severity: critical
"""
        alerts = parse_upstream_rules(rules_yaml)

        assert len(alerts) == 2
        assert alerts[0].technology == "postgres"
        assert alerts[1].technology == "redis"


class TestApplyNthlayerFixes:
    """Tests for NthLayer-specific fixes."""

    def test_fixes_zero_duration(self):
        alerts = [
            ConvertedAlert(
                name="TestAlert",
                expr="up == 0",
                duration="0m",
                severity="critical",
                summary="Test",
                description="Test",
                category="test",
                technology="test",
            )
        ]

        fixed = apply_nthlayer_fixes(alerts)

        assert fixed[0].duration == "1m"

    def test_fixes_empty_duration(self):
        alerts = [
            ConvertedAlert(
                name="TestAlert",
                expr="up == 0",
                duration="",
                severity="critical",
                summary="Test",
                description="Test",
                category="test",
                technology="test",
            )
        ]

        fixed = apply_nthlayer_fixes(alerts)

        assert fixed[0].duration == "1m"

    def test_preserves_valid_duration(self):
        alerts = [
            ConvertedAlert(
                name="TestAlert",
                expr="up == 0",
                duration="5m",
                severity="critical",
                summary="Test",
                description="Test",
                category="test",
                technology="test",
            )
        ]

        fixed = apply_nthlayer_fixes(alerts)

        assert fixed[0].duration == "5m"


class TestGroupByTechnology:
    """Tests for grouping alerts by category and technology."""

    def test_groups_correctly(self):
        alerts = [
            ConvertedAlert(
                name="PostgresqlDown",
                expr="pg_up == 0",
                duration="1m",
                severity="critical",
                summary="Postgresql down",
                description="Test",
                category="databases",
                technology="postgres",
            ),
            ConvertedAlert(
                name="PostgresqlSlow",
                expr="pg_slow > 100",
                duration="5m",
                severity="warning",
                summary="Postgresql slow",
                description="Test",
                category="databases",
                technology="postgres",
            ),
            ConvertedAlert(
                name="RedisDown",
                expr="redis_up == 0",
                duration="1m",
                severity="critical",
                summary="Redis down",
                description="Test",
                category="databases",
                technology="redis",
            ),
        ]

        grouped = group_by_technology(alerts)

        assert "databases" in grouped
        assert "postgres" in grouped["databases"]
        assert "redis" in grouped["databases"]
        assert len(grouped["databases"]["postgres"]) == 2
        assert len(grouped["databases"]["redis"]) == 1


class TestAlertToPrometheusDict:
    """Tests for converting alerts to Prometheus format."""

    def test_converts_to_prometheus_format(self):
        alert = ConvertedAlert(
            name="PostgresqlDown",
            expr="pg_up == 0",
            duration="1m",
            severity="critical",
            summary="Postgresql down",
            description="PostgreSQL instance is down",
            category="databases",
            technology="postgres",
        )

        result = alert_to_prometheus_dict(alert)

        assert result["alert"] == "PostgresqlDown"
        assert result["expr"] == "pg_up == 0"
        assert result["for"] == "1m"
        assert result["labels"]["severity"] == "critical"
        assert "{{ $labels.instance }}" in result["annotations"]["summary"]
        assert "{{ $value }}" in result["annotations"]["description"]


class TestWriteTemplateFile:
    """Tests for writing template files."""

    def test_writes_valid_yaml(self):
        alerts = [
            ConvertedAlert(
                name="PostgresqlDown",
                expr="pg_up == 0",
                duration="1m",
                severity="critical",
                summary="Postgresql down",
                description="PostgreSQL instance is down",
                category="databases",
                technology="postgres",
            )
        ]

        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir)
            output_file = write_template_file(
                category="databases",
                technology="postgres",
                alerts=alerts,
                output_dir=output_dir,
                dry_run=False,
            )

            assert output_file.exists()

            # Verify it's valid YAML
            with open(output_file) as f:
                content = f.read()
                # Skip header comments
                yaml_content = "\n".join(
                    line for line in content.split("\n") if not line.startswith("#")
                )
                data = yaml.safe_load(yaml_content)

            assert "groups" in data
            assert len(data["groups"]) == 1
            assert data["groups"][0]["name"] == "postgres"
            assert len(data["groups"][0]["rules"]) == 1

    def test_dry_run_does_not_write(self):
        alerts = [
            ConvertedAlert(
                name="TestAlert",
                expr="up == 0",
                duration="1m",
                severity="critical",
                summary="Test",
                description="Test",
                category="test",
                technology="test",
            )
        ]

        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir)
            output_file = write_template_file(
                category="test",
                technology="test",
                alerts=alerts,
                output_dir=output_dir,
                dry_run=True,
            )

            # File should not exist in dry run
            assert not output_file.exists()


class TestIntegration:
    """Integration tests for the full sync pipeline."""

    def test_full_sync_with_sample_data(self):
        """Test full sync pipeline with sample upstream data."""
        sample_rules = """
groups:
  - name: Databases
    services:
      - name: PostgreSQL
        exporters:
          - slug: postgres-exporter
            rules:
              - name: Postgresql down
                description: PostgreSQL instance is down
                query: pg_up == 0
                severity: critical
              - name: Postgresql high rollback rate
                description: Ratio of transactions being aborted is high
                query: 'sum by (namespace,datname) (rate(pg_stat_database_xact_rollback[3m])) > 0.02'
                severity: warning
                for: 0m
      - name: Redis
        exporters:
          - slug: redis-exporter
            rules:
              - name: Redis down
                description: Redis instance is down
                query: redis_up == 0
                severity: critical
"""
        # Parse
        alerts = parse_upstream_rules(sample_rules)
        assert len(alerts) == 3

        # Apply fixes
        fixed = apply_nthlayer_fixes(alerts)

        # Verify 0m was fixed
        rollback_alert = next(a for a in fixed if "Rollback" in a.name)
        assert rollback_alert.duration == "1m"

        # Group
        grouped = group_by_technology(fixed)
        assert "databases" in grouped
        assert "postgres" in grouped["databases"]
        assert "redis" in grouped["databases"]

        # Write
        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir)

            for category, technologies in grouped.items():
                for technology, tech_alerts in technologies.items():
                    output_file = write_template_file(category, technology, tech_alerts, output_dir)
                    assert output_file.exists()

            # Verify files
            assert (output_dir / "databases" / "postgres.yaml").exists()
            assert (output_dir / "databases" / "redis.yaml").exists()

    def test_synced_templates_loadable_by_nthlayer(self):
        """Test that synced templates can be loaded by NthLayer's AlertTemplateLoader."""
        from nthlayer.alerts import AlertTemplateLoader

        sample_rules = """
groups:
  - name: Databases
    services:
      - name: PostgreSQL
        exporters:
          - slug: postgres-exporter
            rules:
              - name: Postgresql down
                description: PostgreSQL instance is down
                query: pg_up == 0
                severity: critical
                for: 1m
"""
        alerts = parse_upstream_rules(sample_rules)
        fixed = apply_nthlayer_fixes(alerts)
        grouped = group_by_technology(fixed)

        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir)

            for category, technologies in grouped.items():
                for technology, tech_alerts in technologies.items():
                    write_template_file(category, technology, tech_alerts, output_dir)

            # Try loading with NthLayer's loader
            loader = AlertTemplateLoader(templates_dir=output_dir)
            loaded = loader.load_technology("postgres")

            assert len(loaded) == 1
            assert loaded[0].name == "PostgresqlDown"
            assert loaded[0].severity == "critical"
