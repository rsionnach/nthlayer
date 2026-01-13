"""Tests for Prometheus recording rules generation."""

import tempfile
from pathlib import Path

import pytest
import yaml
from nthlayer.recording_rules.builder import build_recording_rules
from nthlayer.recording_rules.models import RecordingRule, RecordingRuleGroup, create_rule_groups
from nthlayer.specs.models import Resource, ServiceContext


class TestRecordingRuleModels:
    """Tests for recording rule data models."""

    def test_recording_rule_creation(self):
        """Test creating a recording rule."""
        rule = RecordingRule(
            record="my:metric:rate5m", expr="rate(my_metric_total[5m])", labels={"service": "test"}
        )

        assert rule.record == "my:metric:rate5m"
        assert rule.expr == "rate(my_metric_total[5m])"
        assert rule.labels == {"service": "test"}

    def test_recording_rule_to_dict(self):
        """Test converting recording rule to dict."""
        rule = RecordingRule(
            record="my:metric:rate5m",
            expr="rate(my_metric_total[5m])",
            labels={"service": "test", "env": "prod"},
        )

        result = rule.to_dict()

        assert result["record"] == "my:metric:rate5m"
        assert result["expr"] == "rate(my_metric_total[5m])"
        assert result["labels"] == {"service": "test", "env": "prod"}

    def test_recording_rule_without_labels(self):
        """Test recording rule without labels."""
        rule = RecordingRule(record="my:metric:rate5m", expr="rate(my_metric_total[5m])")

        result = rule.to_dict()

        assert "labels" not in result

    def test_recording_rule_group_creation(self):
        """Test creating a recording rule group."""
        group = RecordingRuleGroup(name="test_group", interval="30s")

        assert group.name == "test_group"
        assert group.interval == "30s"
        assert len(group.rules) == 0

    def test_recording_rule_group_add_rule(self):
        """Test adding rules to a group."""
        group = RecordingRuleGroup(name="test_group")

        rule1 = RecordingRule(record="metric1", expr="expr1")
        rule2 = RecordingRule(record="metric2", expr="expr2")

        group.add_rule(rule1)
        group.add_rule(rule2)

        assert len(group.rules) == 2
        assert group.rules[0] == rule1
        assert group.rules[1] == rule2

    def test_recording_rule_group_to_dict(self):
        """Test converting rule group to dict."""
        group = RecordingRuleGroup(name="test_group", interval="1m")
        group.add_rule(RecordingRule(record="metric1", expr="expr1"))

        result = group.to_dict()

        assert result["name"] == "test_group"
        assert result["interval"] == "1m"
        assert len(result["rules"]) == 1
        assert result["rules"][0]["record"] == "metric1"

    def test_recording_rule_group_to_yaml(self):
        """Test converting rule group to YAML."""
        group = RecordingRuleGroup(name="test_group", interval="30s")
        group.add_rule(
            RecordingRule(
                record="test:metric", expr="sum(rate(metric[5m]))", labels={"service": "test"}
            )
        )

        yaml_str = group.to_yaml()

        # Parse YAML to verify structure
        data = yaml.safe_load(yaml_str)

        assert "groups" in data
        assert len(data["groups"]) == 1
        assert data["groups"][0]["name"] == "test_group"
        assert data["groups"][0]["interval"] == "30s"

    def test_create_rule_groups_multiple(self):
        """Test creating YAML for multiple rule groups."""
        group1 = RecordingRuleGroup(name="group1")
        group1.add_rule(RecordingRule(record="metric1", expr="expr1"))

        group2 = RecordingRuleGroup(name="group2")
        group2.add_rule(RecordingRule(record="metric2", expr="expr2"))

        yaml_str = create_rule_groups([group1, group2])
        data = yaml.safe_load(yaml_str)

        assert len(data["groups"]) == 2
        assert data["groups"][0]["name"] == "group1"
        assert data["groups"][1]["name"] == "group2"


class TestRecordingRuleBuilder:
    """Tests for recording rule builder."""

    def test_builds_rules_from_service_spec(self):
        """Test building recording rules from service spec."""
        context = ServiceContext(name="test-api", team="platform", tier="standard", type="api")

        resources = [
            Resource(
                kind="SLO",
                name="availability",
                spec={"objective": 99.9, "window": "30d"},
                context=context,
            ),
        ]

        groups = build_recording_rules(context, resources)

        assert len(groups) >= 1  # At least SLO group

        # Find SLO group
        slo_group = next((g for g in groups if "slo" in g.name), None)
        assert slo_group is not None
        assert len(slo_group.rules) >= 4  # At least 4 availability rules

    def test_availability_slo_rules(self):
        """Test that availability SLO generates correct rules."""
        context = ServiceContext(name="test-api", team="platform", tier="standard", type="api")

        resources = [
            Resource(
                kind="SLO",
                name="availability",
                spec={"objective": 99.9, "window": "30d"},
                context=context,
            ),
        ]

        groups = build_recording_rules(context, resources)
        slo_group = next((g for g in groups if "slo" in g.name), None)

        # Check for key rules
        rule_names = [r.record for r in slo_group.rules]

        assert "slo:requests_total:30d" in rule_names
        assert "slo:requests_success:30d" in rule_names
        assert "slo:availability:ratio" in rule_names
        assert "slo:error_budget_remaining:ratio" in rule_names

    def test_latency_slo_rules(self):
        """Test that latency SLO generates correct rules."""
        context = ServiceContext(name="test-api", team="platform", tier="standard", type="api")

        resources = [
            Resource(
                kind="SLO",
                name="latency-p95",
                spec={"objective": 99.0, "latency_threshold": 500, "window": "30d"},
                context=context,
            ),
        ]

        groups = build_recording_rules(context, resources)
        slo_group = next((g for g in groups if "slo" in g.name), None)

        # Check for key rules
        rule_names = [r.record for r in slo_group.rules]

        assert "slo:latency_requests_total:30d" in rule_names
        assert "slo:latency_requests_fast:30d" in rule_names
        assert "slo:latency:ratio" in rule_names
        assert "slo:http_request_duration_seconds:p95" in rule_names
        assert "slo:http_request_duration_seconds:p99" in rule_names

    def test_multiple_slos_create_multiple_rules(self):
        """Test that multiple SLOs create multiple rules."""
        context = ServiceContext(name="test-api", team="platform", tier="standard", type="api")

        resources = [
            Resource(kind="SLO", name="availability", spec={"objective": 99.9}, context=context),
            Resource(
                kind="SLO",
                name="latency-p95",
                spec={"objective": 99.0, "latency_threshold": 500},
                context=context,
            ),
        ]

        groups = build_recording_rules(context, resources)
        slo_group = next((g for g in groups if "slo" in g.name), None)

        # Should have rules for both SLOs
        assert len(slo_group.rules) >= 8  # At least 4 per SLO

    def test_health_metrics_group(self):
        """Test that health metrics group is created."""
        context = ServiceContext(name="test-api", team="platform", tier="standard", type="api")

        groups = build_recording_rules(context, [])

        # Find health group
        health_group = next((g for g in groups if "health" in g.name), None)
        assert health_group is not None

        # Check for key health metrics
        rule_names = [r.record for r in health_group.rules]

        assert "service:http_requests:rate5m" in rule_names
        assert "service:http_errors:rate5m" in rule_names
        assert "service:http_request_duration_seconds:p95" in rule_names
        assert "service:http_request_duration_seconds:p99" in rule_names

    def test_rules_have_service_labels(self):
        """Test that all rules have service labels."""
        context = ServiceContext(name="test-api", team="platform", tier="standard", type="api")

        resources = [
            Resource(kind="SLO", name="availability", spec={"objective": 99.9}, context=context),
        ]

        groups = build_recording_rules(context, resources)

        for group in groups:
            for rule in group.rules:
                assert "service" in rule.labels
                assert rule.labels["service"] == "test-api"

    def test_rules_have_valid_promql(self):
        """Test that all rules have valid-looking PromQL."""
        context = ServiceContext(name="test-api", team="platform", tier="standard", type="api")

        resources = [
            Resource(kind="SLO", name="availability", spec={"objective": 99.9}, context=context),
        ]

        groups = build_recording_rules(context, resources)

        for group in groups:
            for rule in group.rules:
                # Basic validation - should contain metric names
                assert len(rule.expr) > 0
                assert "{" in rule.expr or "(" in rule.expr  # Has labels or functions


class TestRecordingRulesCommand:
    """Tests for generate-recording-rules CLI command."""

    def test_generates_rules_file(self):
        """Test that command generates recording rules YAML file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir = Path(tmpdir)

            service_file = tmpdir / "test-api.yaml"
            service_file.write_text("""
service:
  name: test-api
  team: platform
  tier: standard
  type: api

resources:
  - kind: SLO
    name: availability
    spec:
      objective: 99.9
      window: 30d
            """)

            output_file = tmpdir / "rules.yaml"

            from nthlayer.cli.recording_rules import generate_recording_rules_command

            result = generate_recording_rules_command(
                str(service_file), output=str(output_file), environment=None, dry_run=False
            )

            assert result == 0
            assert output_file.exists()

            # Verify YAML is valid
            rules_data = yaml.safe_load(output_file.read_text())
            assert "groups" in rules_data
            assert len(rules_data["groups"]) >= 1

    def test_dry_run_doesnt_write_file(self):
        """Test that dry-run mode doesn't create files."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir = Path(tmpdir)

            service_file = tmpdir / "test-api.yaml"
            service_file.write_text("""
service:
  name: test-api
  team: platform
  tier: standard
  type: api

resources:
  - kind: SLO
    name: availability
    spec:
      objective: 99.9
            """)

            output_file = tmpdir / "rules.yaml"

            from nthlayer.cli.recording_rules import generate_recording_rules_command

            result = generate_recording_rules_command(
                str(service_file), output=str(output_file), environment=None, dry_run=True
            )

            assert result == 0
            assert not output_file.exists()  # No file in dry-run mode

    def test_environment_aware_rules(self):
        """Test that rules work with environment specs."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir = Path(tmpdir)

            service_file = tmpdir / "test-api.yaml"
            service_file.write_text("""
service:
  name: test-api
  team: platform
  tier: standard
  type: api

resources:
  - kind: SLO
    name: availability
    spec:
      objective: 99.9
            """)

            env_dir = tmpdir / "environments"
            env_dir.mkdir()
            (env_dir / "prod.yaml").write_text("""
environment: prod
resources:
  - kind: SLO
    name: availability
    spec:
      objective: 99.99
            """)

            output_file = tmpdir / "rules.yaml"

            from nthlayer.cli.recording_rules import generate_recording_rules_command

            result = generate_recording_rules_command(
                str(service_file), output=str(output_file), environment="prod", dry_run=False
            )

            assert result == 0
            assert output_file.exists()

            # Verify rules were generated
            rules_data = yaml.safe_load(output_file.read_text())
            assert len(rules_data["groups"]) >= 1


class TestPrometheusIntegration:
    """Tests for Prometheus integration."""

    def test_yaml_format_is_valid(self):
        """Test that generated YAML is valid Prometheus format."""
        context = ServiceContext(name="test-api", team="platform", tier="standard", type="api")

        resources = [
            Resource(kind="SLO", name="availability", spec={"objective": 99.9}, context=context),
        ]

        groups = build_recording_rules(context, resources)
        yaml_str = create_rule_groups(groups)

        # Parse YAML
        data = yaml.safe_load(yaml_str)

        # Verify Prometheus format
        assert "groups" in data
        for group in data["groups"]:
            assert "name" in group
            assert "interval" in group
            assert "rules" in group

            for rule in group["rules"]:
                assert "record" in rule
                assert "expr" in rule

    def test_rule_names_follow_conventions(self):
        """Test that rule names follow Prometheus conventions."""
        context = ServiceContext(name="test-api", team="platform", tier="standard", type="api")

        resources = [
            Resource(kind="SLO", name="availability", spec={"objective": 99.9}, context=context),
        ]

        groups = build_recording_rules(context, resources)

        for group in groups:
            for rule in group.rules:
                # Rule names should contain colons
                assert ":" in rule.record
                # Should not start/end with underscores
                assert not rule.record.startswith("_")
                assert not rule.record.endswith("_")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
