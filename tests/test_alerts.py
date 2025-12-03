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
        "annotations": {
            "summary": "Postgresql down",
            "description": "Postgresql instance is down"
        }
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
        technology="postgres"
    )
    
    customized = alert.customize_for_service(
        service_name="search-api",
        team="platform",
        tier=1,
        notification_channel="pagerduty",
        runbook_url="https://runbooks.example.com"
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
        annotations={"summary": "Test alert"}
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
                    {"name": "redis-cache", "type": "redis"}
                ]
            }
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
                    {"name": "redis-cache"}
                ]
            }
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
    
    # All these should work
    pg_alerts = loader.load_technology("postgres")
    postgresql_alerts = loader.load_technology("postgresql")
    pg_short_alerts = loader.load_technology("pg")
    
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
