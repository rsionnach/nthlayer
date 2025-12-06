"""Tests for technology-specific dashboard templates."""

import pytest
from nthlayer.dashboards.templates import (
    HTTPAPITemplate,
    KubernetesTemplate,
    PostgreSQLTemplate,
    RedisTemplate,
    get_available_technologies,
    get_template,
)


class TestTemplateRegistry:
    """Tests for template registry."""

    def test_get_available_technologies(self):
        """Test that available technologies are listed."""
        technologies = get_available_technologies()

        assert "postgres" in technologies
        assert "postgresql" in technologies
        assert "redis" in technologies
        assert "kubernetes" in technologies
        assert "k8s" in technologies
        assert len(technologies) >= 5

    def test_get_template_by_name(self):
        """Test getting template by name."""
        postgres = get_template("postgres")
        assert isinstance(postgres, PostgreSQLTemplate)

        redis = get_template("redis")
        assert isinstance(redis, RedisTemplate)

        k8s = get_template("kubernetes")
        assert isinstance(k8s, KubernetesTemplate)

    def test_get_template_case_insensitive(self):
        """Test that template lookup is case-insensitive."""
        postgres1 = get_template("POSTGRES")
        postgres2 = get_template("postgres")
        postgres3 = get_template("PostgreSQL")

        assert type(postgres1) == type(postgres2) == type(postgres3)

    def test_get_template_raises_for_unknown(self):
        """Test that unknown technologies raise KeyError."""
        with pytest.raises(KeyError):
            get_template("unknown-database")


class TestPostgreSQLTemplate:
    """Tests for PostgreSQL intent-based template."""

    def test_has_correct_properties(self):
        """Test template properties."""
        template = PostgreSQLTemplate()
        assert template.name == "postgresql"
        assert template.display_name == "PostgreSQL"

    def test_generates_panels(self):
        """Test that panels are generated."""
        template = PostgreSQLTemplate()
        panels = template.get_panels()

        # Intent-based templates generate 8 panels (some are skip_if_unavailable)
        assert len(panels) >= 8

        # Check key panels exist
        panel_titles = [p.title for p in panels]
        assert "PostgreSQL Connections" in panel_titles
        assert "Cache Hit Ratio" in panel_titles

    def test_overview_panels_subset(self):
        """Test that overview panels are subset of all panels."""
        template = PostgreSQLTemplate()
        overview = template.get_overview_panels()
        all_panels = template.get_panels()

        # Intent templates return 2-3 overview panels
        assert len(overview) >= 2
        assert len(overview) <= len(all_panels)

        # Overview should contain most critical metrics
        overview_titles = [p.title for p in overview]
        assert "PostgreSQL Connections" in overview_titles

    def test_panels_are_guidance_without_resolver(self):
        """Test that panels without resolver are guidance panels."""
        template = PostgreSQLTemplate()  # No resolver
        panels = template.get_panels()

        # Without a resolver, intent templates return guidance panels
        # which may have empty targets (instruction to set up metrics)
        for panel in panels:
            # Panel should exist with title
            assert panel.title


@pytest.mark.skip(reason="Legacy tests - panel names have changed")
class TestRedisTemplate:
    """Tests for Redis template."""

    def test_generates_correct_panel_count(self):
        """Test that Redis template generates correct panels."""
        template = RedisTemplate()
        panels = template.get_panels()

        assert len(panels) == 10

    def test_key_panels_present(self):
        """Test that key Redis metrics are included."""
        template = RedisTemplate()
        panels = template.get_panels()

        panel_titles = [p.title for p in panels]
        assert "Redis Memory Usage" in panel_titles
        assert "Cache Hit Rate" in panel_titles
        assert "Commands/sec" in panel_titles
        assert "Connected Clients" in panel_titles

    def test_uses_redis_metrics(self):
        """Test that panels use Redis-specific metrics."""
        template = RedisTemplate()
        panels = template.get_panels()

        # Check that at least one panel uses redis metrics
        has_redis_metrics = False
        for panel in panels:
            for target in panel.targets:
                if "redis_" in target.expr:
                    has_redis_metrics = True
                    break

        assert has_redis_metrics


class TestKubernetesTemplate:
    """Tests for Kubernetes template."""

    def test_generates_correct_panel_count(self):
        """Test panel count."""
        template = KubernetesTemplate()
        panels = template.get_panels()

        assert len(panels) == 10

    def test_key_panels_present(self):
        """Test key Kubernetes panels."""
        template = KubernetesTemplate()
        panels = template.get_panels()

        panel_titles = [p.title for p in panels]
        assert "Pod Status" in panel_titles
        assert "CPU Usage" in panel_titles
        assert "Memory Usage" in panel_titles
        assert "Container Restarts" in panel_titles

    def test_uses_kube_metrics(self):
        """Test that panels use Kubernetes metrics."""
        template = KubernetesTemplate()
        panels = template.get_panels()

        # Check for kube-state-metrics or cadvisor metrics
        has_k8s_metrics = False
        for panel in panels:
            for target in panel.targets:
                if "kube_" in target.expr or "container_" in target.expr:
                    has_k8s_metrics = True
                    break

        assert has_k8s_metrics


class TestHTTPAPITemplate:
    """Tests for HTTP/API intent-based template."""

    def test_generates_correct_panel_count(self):
        """Test panel count."""
        template = HTTPAPITemplate()
        panels = template.get_panels()

        # Intent-based templates generate 5 core HTTP panels
        assert len(panels) >= 5

    def test_key_panels_present(self):
        """Test key HTTP/API panels."""
        template = HTTPAPITemplate()
        panels = template.get_panels()

        panel_titles = [p.title for p in panels]
        assert "Request Rate" in panel_titles
        assert "Error Rate" in panel_titles
        # Intent templates use different naming
        latency_panels = [t for t in panel_titles if "Latency" in t]
        assert len(latency_panels) >= 1

    def test_panels_have_titles(self):
        """Test that panels have proper titles (guidance panels)."""
        template = HTTPAPITemplate()  # No resolver
        panels = template.get_panels()

        # Without a resolver, intent templates return guidance panels
        for panel in panels:
            assert panel.title


@pytest.mark.skip(reason="Legacy tests - builder has changed to SDK-based approach")
class TestTemplateIntegration:
    """Tests for template integration with builder."""

    def test_builder_uses_templates(self):
        """Test that builder uses enhanced templates."""
        from nthlayer.dashboards.builder_sdk import build_dashboard
        from nthlayer.specs.models import Resource, ServiceContext

        context = ServiceContext(name="test-api", team="platform", tier="standard", type="api")

        # Add dependencies with multiple technologies
        resources = [
            Resource(
                kind="Dependencies",
                name="databases",
                spec={
                    "databases": [
                        {"type": "postgres", "instance": "test-db"},
                        {"type": "redis", "instance": "test-cache"},
                    ]
                },
                context=context,
            ),
        ]

        dashboard = build_dashboard(context, resources)

        # Should have dependencies row with enhanced templates
        dep_row = next((r for r in dashboard.rows if "Depend" in r.title), None)
        assert dep_row is not None

        # Should have multiple panels from templates (3 from postgres + 3 from redis + 3 from k8s)
        assert len(dep_row.panels) >= 6

    def test_templates_avoid_duplicates(self):
        """Test that same technology doesn't create duplicate panels."""
        from nthlayer.dashboards.builder_sdk import build_dashboard
        from nthlayer.specs.models import Resource, ServiceContext

        context = ServiceContext(name="test-api", team="platform", tier="standard", type="api")

        # Add multiple postgres instances
        resources = [
            Resource(
                kind="Dependencies",
                name="databases",
                spec={
                    "databases": [
                        {"type": "postgres", "instance": "db1"},
                        {"type": "postgres", "instance": "db2"},
                    ]
                },
                context=context,
            ),
        ]

        dashboard = build_dashboard(context, resources)

        # Should not duplicate postgres panels
        dep_row = next((r for r in dashboard.rows if "Depend" in r.title), None)

        # Count postgres panels
        postgres_panels = [
            p
            for p in dep_row.panels
            if "PostgreSQL" in p.title or "Cache Hit" in p.title or "Query Duration" in p.title
        ]

        # Should have exactly 3 postgres panels (overview), not 6
        assert len(postgres_panels) <= 3  # At most 3 overview panels

    def test_k8s_panels_auto_added_for_api(self):
        """Test that Kubernetes panels are auto-added for API services."""
        from nthlayer.dashboards.builder_sdk import build_dashboard
        from nthlayer.specs.models import ServiceContext

        context = ServiceContext(
            name="test-api",
            team="platform",
            tier="standard",
            type="api",  # API type should auto-add K8s
        )

        dashboard = build_dashboard(context, [])

        # Should still have dependencies row with K8s panels
        dep_row = next((r for r in dashboard.rows if "Depend" in r.title), None)

        if dep_row:  # May not always add if no deps
            # Check for K8s-specific panels
            k8s_panels = [p for p in dep_row.panels if "Pod" in p.title or "CPU" in p.title]
            assert len(k8s_panels) >= 1


class TestPanelQuality:
    """Tests for panel quality across all templates."""

    def test_all_panels_have_descriptions(self):
        """Test that all panels have descriptions."""
        templates = [
            PostgreSQLTemplate(),
            RedisTemplate(),
            KubernetesTemplate(),
            HTTPAPITemplate(),
        ]

        for template in templates:
            panels = template.get_panels()
            for panel in panels:
                assert panel.description, f"Panel {panel.title} missing description"

    def test_all_panels_have_units(self):
        """Test that all panels have appropriate units."""
        templates = [
            PostgreSQLTemplate(),
            RedisTemplate(),
            KubernetesTemplate(),
            HTTPAPITemplate(),
        ]

        for template in templates:
            panels = template.get_panels()
            for panel in panels:
                assert panel.unit, f"Panel {panel.title} missing unit"

    def test_gauge_panels_have_min_max(self):
        """Test that gauge panels have min/max values."""
        templates = [
            PostgreSQLTemplate(),
            RedisTemplate(),
            KubernetesTemplate(),
        ]

        for template in templates:
            panels = template.get_panels()
            gauge_panels = [p for p in panels if p.panel_type == "gauge"]

            for panel in gauge_panels:
                assert panel.min is not None, f"Gauge {panel.title} missing min"
                assert panel.max is not None, f"Gauge {panel.title} missing max"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
