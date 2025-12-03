"""Tests for Hybrid Dashboard Builder (SDK-based with intent resolution)."""



class TestDashboardBuilderSDK:
    """Tests for DashboardBuilderSDK hybrid model."""

    def test_builds_dashboard_for_api_service(self):
        """Test dashboard generation for API service type."""
        from nthlayer.dashboards.builder_sdk import DashboardBuilderSDK
        from nthlayer.specs.models import Resource, ServiceContext

        context = ServiceContext(
            name="test-api",
            team="platform",
            tier="critical",
            type="api"
        )
        resources = [
            Resource(kind="SLO", name="availability", spec={"objective": 99.9}),
        ]

        builder = DashboardBuilderSDK(
            service_context=context,
            resources=resources,
            use_intent_templates=True
        )
        result = builder.build()
        dashboard = result.get("dashboard", result)

        assert dashboard["title"] == "test-api - Service Dashboard"
        assert dashboard["uid"] == "test-api-overview"
        assert len(dashboard["panels"]) > 0

    def test_builds_dashboard_for_worker_service(self):
        """Test dashboard generation for worker service type."""
        from nthlayer.dashboards.builder_sdk import DashboardBuilderSDK
        from nthlayer.specs.models import Resource, ServiceContext

        context = ServiceContext(
            name="test-worker",
            team="platform",
            tier="standard",
            type="worker"
        )
        resources = [
            Resource(kind="SLO", name="availability", spec={"objective": 99.9}),
        ]

        builder = DashboardBuilderSDK(
            service_context=context,
            resources=resources,
            use_intent_templates=True
        )
        result = builder.build()
        dashboard = result.get("dashboard", result)

        assert dashboard["title"] == "test-worker - Service Dashboard"
        # Worker should use notifications_sent_total, not http_requests_total
        slo_panel = next((p for p in dashboard["panels"] if p.get("title") == "availability"), None)
        assert slo_panel is not None
        expr = slo_panel.get("targets", [{}])[0].get("expr", "")
        assert "notifications_sent_total" in expr or "jobs_processed_total" in expr

    def test_builds_dashboard_for_stream_service(self):
        """Test dashboard generation for stream service type."""
        from nthlayer.dashboards.builder_sdk import DashboardBuilderSDK
        from nthlayer.specs.models import Resource, ServiceContext

        context = ServiceContext(
            name="test-stream",
            team="data",
            tier="standard",
            type="stream"
        )
        resources = [
            Resource(kind="SLO", name="availability", spec={"objective": 99.9}),
        ]

        builder = DashboardBuilderSDK(
            service_context=context,
            resources=resources,
            use_intent_templates=True
        )
        result = builder.build()
        dashboard = result.get("dashboard", result)

        assert dashboard["title"] == "test-stream - Service Dashboard"
        # Stream should use events_processed_total
        slo_panel = next((p for p in dashboard["panels"] if p.get("title") == "availability"), None)
        assert slo_panel is not None
        expr = slo_panel.get("targets", [{}])[0].get("expr", "")
        assert "events_processed_total" in expr


class TestServiceTypeRouting:
    """Tests for service type routing in SLO queries."""

    def test_api_slo_uses_http_metrics(self):
        """API services should use HTTP request metrics for SLOs."""
        from nthlayer.dashboards.sdk_adapter import SDKAdapter

        query = SDKAdapter.convert_slo_to_query(
            {"name": "availability", "objective": 99.9},
            service_type="api"
        )
        expr = query.build().expr
        assert "http_requests_total" in expr
        assert "status!~" in expr or "status=~" in expr

    def test_worker_slo_uses_notification_metrics(self):
        """Worker services should use notification metrics for SLOs."""
        from nthlayer.dashboards.sdk_adapter import SDKAdapter

        query = SDKAdapter.convert_slo_to_query(
            {"name": "availability", "objective": 99.9},
            service_type="worker"
        )
        expr = query.build().expr
        assert "notifications_sent_total" in expr
        assert 'status!="failed"' in expr or 'status="failed"' in expr

    def test_stream_slo_uses_events_metrics(self):
        """Stream services should use events metrics for SLOs."""
        from nthlayer.dashboards.sdk_adapter import SDKAdapter

        query = SDKAdapter.convert_slo_to_query(
            {"name": "availability", "objective": 99.9},
            service_type="stream"
        )
        expr = query.build().expr
        assert "events_processed_total" in expr
        assert 'status!="error"' in expr or 'status="error"' in expr


class TestHistogramQuantileSyntax:
    """Tests for correct histogram_quantile PromQL syntax."""

    def test_latency_slo_has_sum_by_le(self):
        """Latency SLOs should use sum by (le) for histogram_quantile."""
        from nthlayer.dashboards.sdk_adapter import SDKAdapter

        query = SDKAdapter.convert_slo_to_query(
            {"name": "latency-p95", "objective": 99.0},
            service_type="api"
        )
        expr = query.build().expr
        assert "histogram_quantile" in expr
        assert "sum by (le)" in expr


class TestIntentResolution:
    """Tests for intent-based metric resolution."""

    def test_http_intent_resolves(self):
        """HTTP intents should resolve to correct metrics."""
        from nthlayer.dashboards.intents import get_intent

        intent = get_intent("http.requests_total")
        assert intent is not None
        assert "http_requests_total" in intent.candidates

    def test_redis_intent_resolves(self):
        """Redis intents should resolve to correct metrics."""
        from nthlayer.dashboards.intents import get_intent

        intent = get_intent("redis.memory")
        assert intent is not None
        assert "redis_memory_used_bytes" in intent.candidates

    def test_postgresql_intent_resolves(self):
        """PostgreSQL intents should resolve to correct metrics."""
        from nthlayer.dashboards.intents import get_intent

        intent = get_intent("postgresql.connections")
        assert intent is not None
        assert len(intent.candidates) > 0

    def test_worker_intent_resolves(self):
        """Worker intents should resolve to correct metrics."""
        from nthlayer.dashboards.intents import get_intent

        intent = get_intent("worker.jobs_processed")
        assert intent is not None
        assert "notifications_sent_total" in intent.candidates

    def test_stream_intent_resolves(self):
        """Stream intents should resolve to correct metrics."""
        from nthlayer.dashboards.intents import get_intent

        intent = get_intent("stream.events_processed")
        assert intent is not None
        assert "events_processed_total" in intent.candidates


class TestStatusLabelConsistency:
    """Tests for consistent status label usage."""

    def test_worker_uses_failed_status(self):
        """Worker error queries should use status='failed'."""
        from nthlayer.dashboards.templates.worker_intent import WorkerIntentTemplate

        template = WorkerIntentTemplate()
        specs = template.get_panel_specs("$service")
        
        error_spec = next((s for s in specs if "Error" in s.title), None)
        assert error_spec is not None
        
        # Check query template uses status="failed"
        if hasattr(error_spec, 'queries') and error_spec.queries:
            query = error_spec.queries[0].query_template
            assert 'status="failed"' in query

    def test_stream_uses_error_status(self):
        """Stream error queries should use status='error'."""
        from nthlayer.dashboards.templates.stream_intent import StreamIntentTemplate

        template = StreamIntentTemplate()
        specs = template.get_panel_specs("$service")
        
        error_spec = next((s for s in specs if "Error" in s.title), None)
        assert error_spec is not None
        
        # Check query template uses status="error"
        if hasattr(error_spec, 'queries') and error_spec.queries:
            query = error_spec.queries[0].query_template
            assert 'status="error"' in query


class TestLabelConsistency:
    """Tests for consistent label selector usage."""

    def test_elasticsearch_uses_service_label(self):
        """Elasticsearch queries should use service label, not cluster."""
        from nthlayer.dashboards.templates.elasticsearch_intent import ElasticsearchIntentTemplate

        template = ElasticsearchIntentTemplate()
        specs = template.get_panel_specs("$service")
        
        for spec in specs:
            if hasattr(spec, 'query_template') and spec.query_template:
                assert 'cluster="$service"' not in spec.query_template
                # Should use service="$service" or service="{service}"
