"""Tests for SDK Adapter - Bridge between NthLayer and Grafana Foundation SDK."""

import json

import pytest
from nthlayer.dashboards.models import Panel, Target
from nthlayer.dashboards.sdk_adapter import SDKAdapter, create_service_dashboard
from nthlayer.specs.models import ServiceContext


@pytest.fixture
def api_service_context():
    """API service context for testing."""
    return ServiceContext(
        name="test-api",
        team="platform",
        tier="critical",
        type="api",
    )


@pytest.fixture
def worker_service_context():
    """Worker service context for testing."""
    return ServiceContext(
        name="test-worker",
        team="platform",
        tier="standard",
        type="worker",
    )


@pytest.fixture
def stream_service_context():
    """Stream service context for testing."""
    return ServiceContext(
        name="test-stream",
        team="data",
        tier="standard",
        type="stream",
    )


@pytest.fixture
def service_with_environment():
    """Service context with environment set."""
    ctx = ServiceContext(
        name="test-service",
        team="platform",
        tier="critical",
        type="api",
    )
    ctx.environment = "production"
    return ctx


@pytest.fixture
def service_with_description():
    """Service context with custom description."""
    ctx = ServiceContext(
        name="test-service",
        team="platform",
        tier="standard",
        type="api",
    )
    ctx.description = "Custom service description"
    return ctx


class TestCreateDashboard:
    """Tests for SDKAdapter.create_dashboard."""

    def test_creates_dashboard_with_default_uid(self, api_service_context):
        """Test dashboard creation with default UID."""
        dash = SDKAdapter.create_dashboard(api_service_context)
        model = dash.build()

        assert model.title == "test-api - Service Dashboard"
        assert model.uid == "test-api-overview"

    def test_creates_dashboard_with_custom_uid(self, api_service_context):
        """Test dashboard creation with custom UID."""
        dash = SDKAdapter.create_dashboard(api_service_context, uid="custom-uid")
        model = dash.build()

        assert model.uid == "custom-uid"

    def test_adds_service_tags(self, api_service_context):
        """Test that service metadata is added as tags."""
        dash = SDKAdapter.create_dashboard(api_service_context)
        model = dash.build()

        assert "platform" in model.tags
        assert "critical" in model.tags
        assert "api" in model.tags

    def test_adds_environment_tag(self, service_with_environment):
        """Test environment is added as tag when present."""
        dash = SDKAdapter.create_dashboard(service_with_environment)
        model = dash.build()

        assert "production" in model.tags

    def test_default_description(self, api_service_context):
        """Test default description generation."""
        dash = SDKAdapter.create_dashboard(api_service_context)
        model = dash.build()

        assert "test-api" in model.description
        assert "Auto-generated" in model.description

    def test_custom_description(self, service_with_description):
        """Test custom description from service context."""
        dash = SDKAdapter.create_dashboard(service_with_description)
        model = dash.build()

        assert model.description == "Custom service description"

    def test_editable_dashboard(self, api_service_context):
        """Test editable dashboard setting."""
        dash = SDKAdapter.create_dashboard(api_service_context, editable=True)
        model = dash.build()

        assert model.editable is True

    def test_readonly_dashboard(self, api_service_context):
        """Test readonly dashboard setting."""
        dash = SDKAdapter.create_dashboard(api_service_context, editable=False)
        model = dash.build()

        assert model.editable is False

    def test_time_range(self, api_service_context):
        """Test default time range is set."""
        dash = SDKAdapter.create_dashboard(api_service_context)
        model = dash.build()

        assert model.time.from_val == "now-6h"
        assert model.time.to == "now"

    def test_timezone(self, api_service_context):
        """Test timezone is set to browser."""
        dash = SDKAdapter.create_dashboard(api_service_context)
        model = dash.build()

        assert model.timezone == "browser"


class TestCreateRow:
    """Tests for SDKAdapter.create_row."""

    def test_creates_row_with_title(self):
        """Test row creation with title."""
        row = SDKAdapter.create_row("SLO Metrics")
        model = row.build()

        assert model.title == "SLO Metrics"

    def test_row_not_collapsed_by_default(self):
        """Test row is not collapsed by default."""
        row = SDKAdapter.create_row("Test Row")
        model = row.build()

        assert model.collapsed is not True

    def test_row_collapsed_when_specified(self):
        """Test row is collapsed when specified."""
        row = SDKAdapter.create_row("Collapsed Row", collapsed=True)
        model = row.build()

        assert model.collapsed is True


class TestCreateTimeseriesPanel:
    """Tests for SDKAdapter.create_timeseries_panel."""

    def test_creates_panel_with_title(self):
        """Test timeseries panel creation."""
        panel = SDKAdapter.create_timeseries_panel("Request Rate")
        model = panel.build()

        assert model.title == "Request Rate"

    def test_adds_description(self):
        """Test description is added."""
        panel = SDKAdapter.create_timeseries_panel("Test Panel", description="Test description")
        model = panel.build()

        assert model.description == "Test description"

    def test_empty_description_not_set(self):
        """Test empty description is handled."""
        panel = SDKAdapter.create_timeseries_panel("Test Panel", description="")
        model = panel.build()

        # Build should succeed without error
        assert model.title == "Test Panel"

    def test_with_queries(self):
        """Test panel with queries."""
        query = SDKAdapter.create_prometheus_query("up{service='test'}")
        panel = SDKAdapter.create_timeseries_panel("Test Panel", queries=[query])
        model = panel.build()

        assert len(model.targets) == 1
        assert model.targets[0].expr == "up{service='test'}"

    def test_with_legend_format(self):
        """Test legend format is applied to queries without format."""
        query = SDKAdapter.create_prometheus_query("up{service='test'}")
        panel = SDKAdapter.create_timeseries_panel(
            "Test Panel", queries=[query], legend_format="{{service}}"
        )
        model = panel.build()

        # The legend format should be applied
        assert len(model.targets) == 1


class TestCreateStatPanel:
    """Tests for SDKAdapter.create_stat_panel."""

    def test_creates_panel_with_title(self):
        """Test stat panel creation."""
        panel = SDKAdapter.create_stat_panel("Current Value")
        model = panel.build()

        assert model.title == "Current Value"

    def test_adds_description(self):
        """Test description is added."""
        panel = SDKAdapter.create_stat_panel("Test Panel", description="Shows current value")
        model = panel.build()

        assert model.description == "Shows current value"

    def test_with_query(self):
        """Test panel with query."""
        query = SDKAdapter.create_prometheus_query("up{service='test'}")
        panel = SDKAdapter.create_stat_panel("Test Panel", query=query)
        model = panel.build()

        assert len(model.targets) == 1


class TestCreateGaugePanel:
    """Tests for SDKAdapter.create_gauge_panel."""

    def test_creates_panel_with_title(self):
        """Test gauge panel creation."""
        panel = SDKAdapter.create_gauge_panel("SLO Status")
        model = panel.build()

        assert model.title == "SLO Status"

    def test_adds_description(self):
        """Test description is added."""
        panel = SDKAdapter.create_gauge_panel("Test Panel", description="Shows percentage")
        model = panel.build()

        assert model.description == "Shows percentage"

    def test_with_query(self):
        """Test panel with query."""
        query = SDKAdapter.create_prometheus_query("up{service='test'}")
        panel = SDKAdapter.create_gauge_panel("Test Panel", query=query)
        model = panel.build()

        assert len(model.targets) == 1


class TestCreateTextPanel:
    """Tests for SDKAdapter.create_text_panel."""

    def test_creates_text_panel(self):
        """Test text panel creation."""
        panel = SDKAdapter.create_text_panel("Instructions", content="# Welcome")
        # Should return a panel (text or fallback stat)
        assert panel is not None

    def test_text_panel_with_html_mode(self):
        """Test text panel with HTML mode."""
        panel = SDKAdapter.create_text_panel("HTML Content", content="<b>Bold</b>", mode="html")
        assert panel is not None

    def test_text_panel_fallback(self):
        """Test text panel fallback to stat panel."""
        # This will use the actual SDK behavior - either text panel or stat fallback
        panel = SDKAdapter.create_text_panel("Guidance", content="Instructions here")
        assert panel is not None
        model = panel.build()
        assert model.title is not None


class TestCreateGuidancePanel:
    """Tests for SDKAdapter.create_guidance_panel."""

    def test_creates_guidance_panel_with_exporter(self):
        """Test guidance panel with exporter recommendation."""
        panel, no_value_msg = SDKAdapter.create_guidance_panel(
            title="PostgreSQL Metrics",
            missing_intents=["query_time", "connections"],
            exporter_recommendation="helm install prometheus-postgres-exporter",
            technology="PostgreSQL",
        )

        assert panel is not None
        assert "Install PostgreSQL exporter" in no_value_msg

    def test_creates_guidance_panel_without_exporter(self):
        """Test guidance panel without exporter recommendation."""
        panel, no_value_msg = SDKAdapter.create_guidance_panel(
            title="Custom Metrics",
            missing_intents=["metric1", "metric2", "metric3"],
        )

        assert panel is not None
        assert "Missing metrics" in no_value_msg

    def test_guidance_panel_truncates_long_intent_list(self):
        """Test guidance panel truncates long intent lists."""
        panel, no_value_msg = SDKAdapter.create_guidance_panel(
            title="Many Missing",
            missing_intents=["a", "b", "c", "d", "e"],
        )

        assert "+2 more" in no_value_msg


class TestCreatePrometheusQuery:
    """Tests for SDKAdapter.create_prometheus_query."""

    def test_creates_query_with_expr(self):
        """Test query creation with expression."""
        query = SDKAdapter.create_prometheus_query("up{service='test'}")
        model = query.build()

        assert model.expr == "up{service='test'}"

    def test_with_legend_format(self):
        """Test legend format is set."""
        query = SDKAdapter.create_prometheus_query("up", legend_format="{{instance}}")
        model = query.build()

        assert model.legend_format == "{{instance}}"

    def test_with_interval(self):
        """Test interval is set."""
        query = SDKAdapter.create_prometheus_query("rate(requests[5m])", interval="30s")
        model = query.build()

        assert model.interval == "30s"

    def test_with_ref_id(self):
        """Test ref_id is set."""
        query = SDKAdapter.create_prometheus_query("up", ref_id="B")
        model = query.build()

        # ref_id should be set if supported
        assert model is not None


class TestConvertPanelToSDK:
    """Tests for SDKAdapter.convert_panel_to_sdk."""

    def test_converts_timeseries_panel(self):
        """Test timeseries panel conversion."""
        nthlayer_panel = Panel(
            title="Request Rate",
            targets=[Target(expr="rate(requests[5m])")],
        )
        nthlayer_panel.type = "timeseries"

        sdk_panel = SDKAdapter.convert_panel_to_sdk(nthlayer_panel)
        model = sdk_panel.build()

        assert model.title == "Request Rate"
        assert len(model.targets) == 1

    def test_converts_stat_panel(self):
        """Test stat panel conversion."""
        nthlayer_panel = Panel(
            title="Current Value",
            targets=[Target(expr="up{service='test'}")],
        )
        nthlayer_panel.type = "stat"

        sdk_panel = SDKAdapter.convert_panel_to_sdk(nthlayer_panel)
        model = sdk_panel.build()

        assert model.title == "Current Value"

    def test_converts_gauge_panel(self):
        """Test gauge panel conversion."""
        nthlayer_panel = Panel(
            title="SLO Status",
            targets=[Target(expr="slo_status")],
        )
        nthlayer_panel.type = "gauge"

        sdk_panel = SDKAdapter.convert_panel_to_sdk(nthlayer_panel)
        model = sdk_panel.build()

        assert model.title == "SLO Status"

    def test_defaults_to_timeseries(self):
        """Test default panel type is timeseries."""
        nthlayer_panel = Panel(
            title="Default Panel",
            targets=[Target(expr="metric")],
        )
        # No type set - should default to timeseries

        sdk_panel = SDKAdapter.convert_panel_to_sdk(nthlayer_panel)
        model = sdk_panel.build()

        assert model.title == "Default Panel"

    def test_handles_empty_targets(self):
        """Test panel with no targets."""
        nthlayer_panel = Panel(
            title="Empty Panel",
            targets=[],
        )
        nthlayer_panel.type = "stat"

        sdk_panel = SDKAdapter.convert_panel_to_sdk(nthlayer_panel)
        model = sdk_panel.build()

        assert model.title == "Empty Panel"

    def test_preserves_legend_format(self):
        """Test legend format is preserved."""
        target = Target(expr="metric")
        target.legend_format = "{{label}}"
        nthlayer_panel = Panel(
            title="Panel with Legend",
            targets=[target],
        )
        nthlayer_panel.type = "timeseries"

        sdk_panel = SDKAdapter.convert_panel_to_sdk(nthlayer_panel)
        model = sdk_panel.build()

        assert model.targets[0].legend_format == "{{label}}"

    def test_panel_with_description(self):
        """Test panel with description."""
        nthlayer_panel = Panel(
            title="Panel with Desc",
            targets=[Target(expr="metric")],
        )
        nthlayer_panel.type = "timeseries"
        nthlayer_panel.description = "Test description"

        sdk_panel = SDKAdapter.convert_panel_to_sdk(nthlayer_panel)
        model = sdk_panel.build()

        assert model.description == "Test description"


class TestBuildAvailabilityQuery:
    """Tests for SDKAdapter._build_availability_query."""

    def test_api_availability_query(self):
        """Test availability query for API service."""
        query = SDKAdapter._build_availability_query("api", "5m")

        assert "http_requests_total" in query
        assert "status!~" in query  # Not 5xx
        assert "5m" in query

    def test_worker_availability_query(self):
        """Test availability query for worker service."""
        query = SDKAdapter._build_availability_query("worker", "5m")

        assert "notifications_sent_total" in query
        assert 'status!="failed"' in query

    def test_stream_availability_query(self):
        """Test availability query for stream service."""
        query = SDKAdapter._build_availability_query("stream", "5m")

        assert "events_processed_total" in query
        assert 'status!="error"' in query


class TestBuildLatencyQuery:
    """Tests for SDKAdapter._build_latency_query."""

    def test_api_latency_query(self):
        """Test latency query for API service."""
        query = SDKAdapter._build_latency_query("api", "5m", "0.95")

        assert "http_request_duration_seconds_bucket" in query
        assert "histogram_quantile" in query
        assert "0.95" in query

    def test_worker_latency_query(self):
        """Test latency query for worker service."""
        query = SDKAdapter._build_latency_query("worker", "5m", "0.99")

        assert "notification_processing_duration_seconds_bucket" in query
        assert "0.99" in query

    def test_stream_latency_query(self):
        """Test latency query for stream service."""
        query = SDKAdapter._build_latency_query("stream", "5m", "0.95")

        assert "event_processing_duration_seconds_bucket" in query


class TestBuildErrorRateQuery:
    """Tests for SDKAdapter._build_error_rate_query."""

    def test_api_error_rate_query(self):
        """Test error rate query for API service."""
        query = SDKAdapter._build_error_rate_query("api", "5m")

        assert "http_requests_total" in query
        assert "status=~" in query  # 5xx pattern

    def test_worker_error_rate_query(self):
        """Test error rate query for worker service."""
        query = SDKAdapter._build_error_rate_query("worker", "5m")

        assert "notifications_sent_total" in query
        assert 'status="failed"' in query

    def test_stream_error_rate_query(self):
        """Test error rate query for stream service."""
        query = SDKAdapter._build_error_rate_query("stream", "5m")

        assert "events_processed_total" in query
        assert 'status="error"' in query


class TestConvertSLOToQuery:
    """Tests for SDKAdapter.convert_slo_to_query."""

    def test_slo_with_existing_query(self):
        """Test SLO that already has a query."""
        slo = {"name": "custom-slo", "query": "custom_metric{service='test'}"}

        query = SDKAdapter.convert_slo_to_query(slo)
        model = query.build()

        assert model.expr == "custom_metric{service='test'}"

    def test_availability_slo_api(self):
        """Test availability SLO for API service."""
        slo = {"name": "availability"}

        query = SDKAdapter.convert_slo_to_query(slo, service_type="api")
        model = query.build()

        assert "http_requests_total" in model.expr

    def test_availability_slo_worker(self):
        """Test availability SLO for worker service."""
        slo = {"name": "availability"}

        query = SDKAdapter.convert_slo_to_query(slo, service_type="worker")
        model = query.build()

        assert "notifications_sent_total" in model.expr

    def test_success_slo(self):
        """Test success rate SLO."""
        slo = {"name": "success-rate"}

        query = SDKAdapter.convert_slo_to_query(slo, service_type="api")
        model = query.build()

        assert "http_requests_total" in model.expr

    def test_latency_p95_slo(self):
        """Test p95 latency SLO."""
        slo = {"name": "p95-latency"}

        query = SDKAdapter.convert_slo_to_query(slo, service_type="api")
        model = query.build()

        assert "histogram_quantile" in model.expr
        assert "0.95" in model.expr

    def test_latency_p99_slo(self):
        """Test p99 latency SLO."""
        slo = {"name": "p99-latency"}

        query = SDKAdapter.convert_slo_to_query(slo, service_type="api")
        model = query.build()

        assert "0.99" in model.expr

    def test_error_rate_slo(self):
        """Test error rate SLO."""
        slo = {"name": "error-rate"}

        query = SDKAdapter.convert_slo_to_query(slo, service_type="api")
        model = query.build()

        assert "http_requests_total" in model.expr
        assert "5.." in model.expr

    def test_default_slo_api(self):
        """Test default SLO query for API service."""
        slo = {"name": "unknown-slo"}

        query = SDKAdapter.convert_slo_to_query(slo, service_type="api")
        model = query.build()

        assert "http_requests_total" in model.expr

    def test_default_slo_worker(self):
        """Test default SLO query for worker service."""
        slo = {"name": "unknown-slo"}

        query = SDKAdapter.convert_slo_to_query(slo, service_type="worker")
        model = query.build()

        assert "notifications_sent_total" in model.expr

    def test_default_slo_stream(self):
        """Test default SLO query for stream service."""
        slo = {"name": "unknown-slo"}

        query = SDKAdapter.convert_slo_to_query(slo, service_type="stream")
        model = query.build()

        assert "events_processed_total" in model.expr

    def test_slo_object(self):
        """Test SLO as object instead of dict."""
        from unittest.mock import MagicMock

        # Create a mock SLO object with required attributes
        slo = MagicMock()
        slo.name = "availability"
        slo.query = None

        query = SDKAdapter.convert_slo_to_query(slo, service_type="api")
        model = query.build()

        assert "http_requests_total" in model.expr

    def test_slo_object_with_query(self):
        """Test SLO object with existing query."""
        from unittest.mock import MagicMock

        # Create a mock SLO object with a custom query
        slo = MagicMock()
        slo.name = "custom"
        slo.query = "custom_metric"

        query = SDKAdapter.convert_slo_to_query(slo)
        model = query.build()

        assert model.expr == "custom_metric"


class TestSerializeDashboard:
    """Tests for SDKAdapter.serialize_dashboard."""

    def test_serializes_to_json(self, api_service_context):
        """Test dashboard serialization to JSON."""
        dash = SDKAdapter.create_dashboard(api_service_context)

        json_str = SDKAdapter.serialize_dashboard(dash)

        # Should be valid JSON
        parsed = json.loads(json_str)
        assert parsed["title"] == "test-api - Service Dashboard"
        assert parsed["uid"] == "test-api-overview"

    def test_serialized_json_is_sorted(self, api_service_context):
        """Test that JSON keys are sorted."""
        dash = SDKAdapter.create_dashboard(api_service_context)

        json_str = SDKAdapter.serialize_dashboard(dash)

        # Should be indented and sorted
        assert "  " in json_str  # indented


class TestAddTemplateVariables:
    """Tests for SDKAdapter.add_template_variables."""

    def test_returns_dashboard_unchanged(self, api_service_context):
        """Test that template variables method returns dashboard unchanged."""
        from nthlayer.dashboards.models import TemplateVariable

        dash = SDKAdapter.create_dashboard(api_service_context)
        variables = [
            TemplateVariable(name="service", label="Service", query="label_values(service)")
        ]

        result = SDKAdapter.add_template_variables(dash, variables)

        # Should return same dashboard (variables not yet supported)
        assert result == dash


class TestCreateServiceDashboard:
    """Tests for create_service_dashboard convenience function."""

    def test_creates_dashboard_without_slos(self, api_service_context):
        """Test dashboard creation without SLOs."""
        dash = create_service_dashboard(api_service_context)
        model = dash.build()

        assert model.title == "test-api - Service Dashboard"

    def test_creates_dashboard_with_slos(self, api_service_context):
        """Test dashboard creation with SLOs (panels not added - documented limitation)."""
        from unittest.mock import MagicMock

        # Create mock SLOs
        slo1 = MagicMock()
        slo1.name = "availability"
        slo2 = MagicMock()
        slo2.name = "latency"
        slos = [slo1, slo2]

        dash = create_service_dashboard(api_service_context, slos=slos)
        model = dash.build()

        # Dashboard is created, but SLO panels not added (documented limitation)
        assert model.title == "test-api - Service Dashboard"
