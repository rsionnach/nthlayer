"""Tests for Alertmanager configuration generation."""

from nthlayer.alertmanager import (
    AlertmanagerConfig,
    InhibitRule,
    PagerDutyReceiver,
    Receiver,
    Route,
    generate_alertmanager_config,
)


class TestPagerDutyReceiver:
    """Tests for PagerDutyReceiver."""

    def test_to_dict_minimal(self):
        """Test minimal receiver config."""
        receiver = PagerDutyReceiver(service_key="abc123")
        result = receiver.to_dict()

        assert result["service_key"] == "abc123"
        assert result["send_resolved"] is True
        assert "url" not in result  # Default URL not included

    def test_to_dict_full(self):
        """Test full receiver config."""
        receiver = PagerDutyReceiver(
            service_key="abc123",
            severity="critical",
            class_="database",
            component="payment-api",
            group="platform",
        )
        result = receiver.to_dict()

        assert result["service_key"] == "abc123"
        assert result["severity"] == "critical"
        assert result["class"] == "database"
        assert result["component"] == "payment-api"
        assert result["group"] == "platform"


class TestReceiver:
    """Tests for Receiver."""

    def test_to_dict(self):
        """Test receiver to dict."""
        receiver = Receiver(
            name="platform-pagerduty",
            pagerduty_configs=[PagerDutyReceiver(service_key="abc123")],
        )
        result = receiver.to_dict()

        assert result["name"] == "platform-pagerduty"
        assert len(result["pagerduty_configs"]) == 1
        assert result["pagerduty_configs"][0]["service_key"] == "abc123"


class TestRoute:
    """Tests for Route."""

    def test_to_dict_minimal(self):
        """Test minimal route config."""
        route = Route(receiver="default")
        result = route.to_dict()

        assert result["receiver"] == "default"
        assert result["group_by"] == ["alertname", "service"]

    def test_to_dict_with_matchers(self):
        """Test route with matchers."""
        route = Route(
            receiver="platform-pagerduty",
            matchers=['service="payment-api"', 'severity="critical"'],
        )
        result = route.to_dict()

        assert result["receiver"] == "platform-pagerduty"
        assert len(result["matchers"]) == 2

    def test_to_dict_with_nested_routes(self):
        """Test route with nested routes."""
        child_route = Route(receiver="child", matchers=['routing="sre"'])
        parent_route = Route(receiver="parent", routes=[child_route])
        result = parent_route.to_dict()

        assert result["receiver"] == "parent"
        assert len(result["routes"]) == 1
        assert result["routes"][0]["receiver"] == "child"


class TestInhibitRule:
    """Tests for InhibitRule."""

    def test_to_dict(self):
        """Test inhibit rule to dict."""
        rule = InhibitRule(
            source_matchers=['severity="critical"'],
            target_matchers=['severity="warning"'],
            equal=["alertname", "service"],
        )
        result = rule.to_dict()

        assert result["source_matchers"] == ['severity="critical"']
        assert result["target_matchers"] == ['severity="warning"']
        assert result["equal"] == ["alertname", "service"]


class TestAlertmanagerConfig:
    """Tests for AlertmanagerConfig."""

    def test_to_dict(self):
        """Test full config to dict."""
        config = AlertmanagerConfig(
            route=Route(receiver="default"),
            receivers=[Receiver(name="default")],
            inhibit_rules=[
                InhibitRule(
                    source_matchers=['severity="critical"'],
                    target_matchers=['severity="warning"'],
                )
            ],
        )
        result = config.to_dict()

        assert "route" in result
        assert "receivers" in result
        assert "inhibit_rules" in result

    def test_to_yaml(self):
        """Test config to YAML."""
        config = AlertmanagerConfig(
            route=Route(receiver="default"),
            receivers=[Receiver(name="default")],
        )
        yaml_output = config.to_yaml()

        assert "route:" in yaml_output
        assert "receivers:" in yaml_output


class TestGenerateAlertmanagerConfig:
    """Tests for generate_alertmanager_config function."""

    def test_basic_config(self):
        """Test basic config generation."""
        config = generate_alertmanager_config(
            service_name="payment-api",
            team="platform",
            pagerduty_integration_key="abc123",
        )

        assert len(config.receivers) == 1
        assert config.receivers[0].name == "platform-pagerduty"
        assert config.route.receiver == "platform-pagerduty"

    def test_config_with_sre_routing(self):
        """Test config with SRE integration key."""
        config = generate_alertmanager_config(
            service_name="payment-api",
            team="platform",
            pagerduty_integration_key="abc123",
            sre_integration_key="sre456",
        )

        assert len(config.receivers) == 2
        receiver_names = [r.name for r in config.receivers]
        assert "platform-pagerduty" in receiver_names
        assert "sre-pagerduty" in receiver_names

        # Check SRE route exists
        sre_routes = [r for r in config.route.routes if r.receiver == "sre-pagerduty"]
        assert len(sre_routes) == 1
        assert 'routing="sre"' in sre_routes[0].matchers

    def test_tier_affects_timing(self):
        """Test that tier affects timing settings."""
        critical_config = generate_alertmanager_config(
            service_name="payment-api",
            team="platform",
            pagerduty_integration_key="abc123",
            tier="critical",
        )

        low_config = generate_alertmanager_config(
            service_name="payment-api",
            team="platform",
            pagerduty_integration_key="abc123",
            tier="low",
        )

        # Critical tier should have shorter repeat interval
        critical_route = next(
            r for r in critical_config.route.routes if 'service="payment-api"' in r.matchers
        )
        low_route = next(
            r for r in low_config.route.routes if 'service="payment-api"' in r.matchers
        )

        assert critical_route.repeat_interval == "1h"
        assert low_route.repeat_interval == "12h"

    def test_inhibit_rules_created(self):
        """Test that inhibit rules are created."""
        config = generate_alertmanager_config(
            service_name="payment-api",
            team="platform",
            pagerduty_integration_key="abc123",
        )

        assert len(config.inhibit_rules) == 1
        rule = config.inhibit_rules[0]
        assert 'severity="critical"' in rule.source_matchers
        assert 'severity="warning"' in rule.target_matchers
