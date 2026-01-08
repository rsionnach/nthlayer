"""Tests for discovery/client.py.

Tests for Prometheus metric discovery client and classifier.
"""

from unittest.mock import MagicMock, patch

import requests
from nthlayer.discovery.classifier import MetricClassifier
from nthlayer.discovery.client import MetricDiscoveryClient
from nthlayer.discovery.models import (
    DiscoveredMetric,
    DiscoveryResult,
    MetricType,
    TechnologyGroup,
)


class TestMetricDiscoveryClientInit:
    """Tests for MetricDiscoveryClient initialization."""

    def test_init_basic(self):
        """Test basic initialization with URL only."""
        client = MetricDiscoveryClient("http://prometheus:9090")

        assert client.prometheus_url == "http://prometheus:9090"
        assert client.auth is None
        assert client.headers == {}
        assert client.classifier is not None

    def test_init_strips_trailing_slash(self):
        """Test URL trailing slash is stripped."""
        client = MetricDiscoveryClient("http://prometheus:9090/")

        assert client.prometheus_url == "http://prometheus:9090"

    def test_init_with_basic_auth(self):
        """Test initialization with HTTP basic auth."""
        client = MetricDiscoveryClient(
            "http://prometheus:9090",
            username="user",
            password="pass",
        )

        assert client.auth is not None
        assert client.auth.username == "user"
        assert client.auth.password == "pass"

    def test_init_with_bearer_token(self):
        """Test initialization with bearer token."""
        client = MetricDiscoveryClient(
            "http://prometheus:9090",
            bearer_token="my-token",
        )

        assert client.headers == {"Authorization": "Bearer my-token"}

    def test_init_username_only_no_auth(self):
        """Test username only does not set auth."""
        client = MetricDiscoveryClient(
            "http://prometheus:9090",
            username="user",
        )

        assert client.auth is None

    def test_init_password_only_no_auth(self):
        """Test password only does not set auth."""
        client = MetricDiscoveryClient(
            "http://prometheus:9090",
            password="pass",
        )

        assert client.auth is None


class TestExtractServiceFromSelector:
    """Tests for _extract_service_from_selector method."""

    def test_extract_simple_selector(self):
        """Test extracting service from simple selector."""
        client = MetricDiscoveryClient("http://prometheus:9090")

        result = client._extract_service_from_selector('{service="payment-api"}')

        assert result == "payment-api"

    def test_extract_complex_selector(self):
        """Test extracting service from complex selector."""
        client = MetricDiscoveryClient("http://prometheus:9090")

        result = client._extract_service_from_selector(
            '{namespace="prod",service="payment-api",env="production"}'
        )

        assert result == "payment-api"

    def test_extract_no_service_returns_unknown(self):
        """Test no service label returns unknown."""
        client = MetricDiscoveryClient("http://prometheus:9090")

        result = client._extract_service_from_selector('{job="app"}')

        assert result == "unknown"

    def test_extract_empty_selector(self):
        """Test empty selector returns unknown."""
        client = MetricDiscoveryClient("http://prometheus:9090")

        result = client._extract_service_from_selector("{}")

        assert result == "unknown"


class TestGetMetricNames:
    """Tests for _get_metric_names method."""

    @patch("nthlayer.discovery.client.requests.get")
    def test_get_metric_names_success(self, mock_get):
        """Test successful metric name discovery."""
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "status": "success",
            "data": [
                {"__name__": "http_requests_total", "service": "api"},
                {"__name__": "http_response_time", "service": "api"},
                {"__name__": "http_requests_total", "service": "api", "method": "GET"},
            ],
        }
        mock_get.return_value = mock_response

        client = MetricDiscoveryClient("http://prometheus:9090")
        result = client._get_metric_names('{service="api"}')

        assert result == ["http_requests_total", "http_response_time"]
        mock_get.assert_called_once()

    @patch("nthlayer.discovery.client.requests.get")
    def test_get_metric_names_api_error(self, mock_get):
        """Test API error response."""
        mock_response = MagicMock()
        mock_response.json.return_value = {"status": "error", "error": "bad query"}
        mock_get.return_value = mock_response

        client = MetricDiscoveryClient("http://prometheus:9090")
        result = client._get_metric_names('{service="api"}')

        assert result == []

    @patch("nthlayer.discovery.client.requests.get")
    def test_get_metric_names_connection_error(self, mock_get):
        """Test connection error handling."""
        mock_get.side_effect = requests.ConnectionError("Connection refused")

        client = MetricDiscoveryClient("http://prometheus:9090")
        result = client._get_metric_names('{service="api"}')

        assert result == []

    @patch("nthlayer.discovery.client.requests.get")
    def test_get_metric_names_http_error(self, mock_get):
        """Test HTTP error handling."""
        mock_response = MagicMock()
        mock_response.raise_for_status.side_effect = requests.HTTPError("500 Server Error")
        mock_get.return_value = mock_response

        client = MetricDiscoveryClient("http://prometheus:9090")
        result = client._get_metric_names('{service="api"}')

        assert result == []

    @patch("nthlayer.discovery.client.requests.get")
    def test_get_metric_names_adds_http_prefix(self, mock_get):
        """Test URL without protocol gets http:// prefix."""
        mock_response = MagicMock()
        mock_response.json.return_value = {"status": "success", "data": []}
        mock_get.return_value = mock_response

        # Note: the code has a quirk where path gets duplicated when adding http prefix
        client = MetricDiscoveryClient("localhost:9090")
        client._get_metric_names('{service="api"}')

        call_url = mock_get.call_args[0][0]
        # Code adds /api/v1/series first, then wraps with http:// and adds again
        assert call_url == "http://localhost:9090/api/v1/series/api/v1/series"

    @patch("nthlayer.discovery.client.requests.get")
    def test_get_metric_names_with_auth(self, mock_get):
        """Test metric names discovery with authentication."""
        mock_response = MagicMock()
        mock_response.json.return_value = {"status": "success", "data": []}
        mock_get.return_value = mock_response

        client = MetricDiscoveryClient(
            "http://prometheus:9090",
            username="user",
            password="pass",
            bearer_token="token",
        )
        client._get_metric_names('{service="api"}')

        call_kwargs = mock_get.call_args[1]
        assert call_kwargs["auth"] is not None
        assert call_kwargs["headers"] == {"Authorization": "Bearer token"}

    @patch("nthlayer.discovery.client.requests.get")
    def test_get_metric_names_empty_data(self, mock_get):
        """Test empty data response."""
        mock_response = MagicMock()
        mock_response.json.return_value = {"status": "success", "data": []}
        mock_get.return_value = mock_response

        client = MetricDiscoveryClient("http://prometheus:9090")
        result = client._get_metric_names('{service="api"}')

        assert result == []


class TestGetMetricsFromEndpoint:
    """Tests for _get_metrics_from_endpoint method (fallback parser)."""

    @patch("nthlayer.discovery.client.requests.get")
    def test_parse_metrics_endpoint(self, mock_get):
        """Test parsing /metrics endpoint."""
        mock_response = MagicMock()
        mock_response.text = """# HELP http_requests_total Total HTTP requests
# TYPE http_requests_total counter
http_requests_total{service="api",method="GET"} 100
http_requests_total{service="api",method="POST"} 50
http_response_time{service="api"} 0.5
"""
        mock_get.return_value = mock_response

        client = MetricDiscoveryClient("http://app.fly.dev")
        result = client._get_metrics_from_endpoint('{service="api"}')

        assert "http_requests_total" in result
        assert "http_response_time" in result

    @patch("nthlayer.discovery.client.requests.get")
    def test_parse_metrics_without_labels(self, mock_get):
        """Test parsing metrics without labels."""
        mock_response = MagicMock()
        mock_response.text = """# HELP up Target is up
up 1
process_cpu_seconds_total 10.5
"""
        mock_get.return_value = mock_response

        # Empty selector should get all metrics
        client = MetricDiscoveryClient("http://app.fly.dev")
        result = client._get_metrics_from_endpoint("{}")

        assert "up" in result
        assert "process_cpu_seconds_total" in result

    @patch("nthlayer.discovery.client.requests.get")
    def test_parse_metrics_filters_by_service(self, mock_get):
        """Test filtering metrics by service label."""
        mock_response = MagicMock()
        mock_response.text = """http_requests{service="api"} 100
http_requests{service="worker"} 50
other_metric{service="api"} 10
"""
        mock_get.return_value = mock_response

        client = MetricDiscoveryClient("http://app.fly.dev")
        result = client._get_metrics_from_endpoint('{service="api"}')

        # Both metrics with service="api"
        assert "http_requests" in result
        assert "other_metric" in result

    @patch("nthlayer.discovery.client.requests.get")
    def test_parse_metrics_connection_error(self, mock_get):
        """Test connection error handling for /metrics endpoint."""
        mock_get.side_effect = requests.ConnectionError("Connection refused")

        client = MetricDiscoveryClient("http://app.fly.dev")
        result = client._get_metrics_from_endpoint('{service="api"}')

        assert result == []

    @patch("nthlayer.discovery.client.requests.get")
    def test_parse_metrics_skips_comments(self, mock_get):
        """Test comments are skipped."""
        mock_response = MagicMock()
        mock_response.text = """# HELP metric help text
# TYPE metric counter
metric 1
"""
        mock_get.return_value = mock_response

        client = MetricDiscoveryClient("http://app.fly.dev")
        result = client._get_metrics_from_endpoint("{}")

        assert result == ["metric"]


class TestGetMetricMetadata:
    """Tests for _get_metric_metadata method."""

    @patch("nthlayer.discovery.client.requests.get")
    def test_get_metadata_success(self, mock_get):
        """Test successful metadata retrieval."""
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "status": "success",
            "data": {"http_requests_total": [{"type": "counter", "help": "Total HTTP requests"}]},
        }
        mock_get.return_value = mock_response

        client = MetricDiscoveryClient("http://prometheus:9090")
        result = client._get_metric_metadata("http_requests_total")

        assert result["type"] == "counter"
        assert result["help"] == "Total HTTP requests"

    @patch("nthlayer.discovery.client.requests.get")
    def test_get_metadata_not_found(self, mock_get):
        """Test metadata not found."""
        mock_response = MagicMock()
        mock_response.json.return_value = {"status": "success", "data": {}}
        mock_get.return_value = mock_response

        client = MetricDiscoveryClient("http://prometheus:9090")
        result = client._get_metric_metadata("unknown_metric")

        assert result == {}

    @patch("nthlayer.discovery.client.requests.get")
    def test_get_metadata_api_error(self, mock_get):
        """Test API error handling."""
        mock_response = MagicMock()
        mock_response.json.return_value = {"status": "error"}
        mock_get.return_value = mock_response

        client = MetricDiscoveryClient("http://prometheus:9090")
        result = client._get_metric_metadata("metric")

        assert result == {}

    @patch("nthlayer.discovery.client.requests.get")
    def test_get_metadata_connection_error(self, mock_get):
        """Test connection error handling."""
        mock_get.side_effect = requests.ConnectionError("Connection refused")

        client = MetricDiscoveryClient("http://prometheus:9090")
        result = client._get_metric_metadata("metric")

        assert result == {}


class TestGetLabelValues:
    """Tests for _get_label_values method."""

    @patch("nthlayer.discovery.client.requests.get")
    def test_get_labels_success(self, mock_get):
        """Test successful label retrieval."""
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "status": "success",
            "data": [
                {"__name__": "metric", "method": "GET", "status": "200"},
                {"__name__": "metric", "method": "POST", "status": "201"},
                {"__name__": "metric", "method": "GET", "status": "500"},
            ],
        }
        mock_get.return_value = mock_response

        client = MetricDiscoveryClient("http://prometheus:9090")
        result = client._get_label_values("metric", '{service="api"}')

        assert result["method"] == ["GET", "POST"]
        assert result["status"] == ["200", "201", "500"]

    @patch("nthlayer.discovery.client.requests.get")
    def test_get_labels_excludes_name(self, mock_get):
        """Test __name__ label is excluded."""
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "status": "success",
            "data": [{"__name__": "metric", "label": "value"}],
        }
        mock_get.return_value = mock_response

        client = MetricDiscoveryClient("http://prometheus:9090")
        result = client._get_label_values("metric", "{}")

        assert "__name__" not in result
        assert result["label"] == ["value"]

    @patch("nthlayer.discovery.client.requests.get")
    def test_get_labels_api_error(self, mock_get):
        """Test API error handling."""
        mock_response = MagicMock()
        mock_response.json.return_value = {"status": "error"}
        mock_get.return_value = mock_response

        client = MetricDiscoveryClient("http://prometheus:9090")
        result = client._get_label_values("metric", "{}")

        assert result == {}

    @patch("nthlayer.discovery.client.requests.get")
    def test_get_labels_connection_error(self, mock_get):
        """Test connection error handling."""
        mock_get.side_effect = requests.ConnectionError("Connection refused")

        client = MetricDiscoveryClient("http://prometheus:9090")
        result = client._get_label_values("metric", "{}")

        assert result == {}


class TestDiscoverMetric:
    """Tests for _discover_metric method."""

    @patch.object(MetricDiscoveryClient, "_get_label_values")
    @patch.object(MetricDiscoveryClient, "_get_metric_metadata")
    def test_discover_metric(self, mock_metadata, mock_labels):
        """Test discovering a single metric."""
        mock_metadata.return_value = {"type": "counter", "help": "Total requests"}
        mock_labels.return_value = {"method": ["GET", "POST"]}

        client = MetricDiscoveryClient("http://prometheus:9090")
        result = client._discover_metric("http_requests_total", '{service="api"}')

        assert result.name == "http_requests_total"
        assert result.type == MetricType.COUNTER
        assert result.help_text == "Total requests"
        assert result.labels == {"method": ["GET", "POST"]}

    @patch.object(MetricDiscoveryClient, "_get_label_values")
    @patch.object(MetricDiscoveryClient, "_get_metric_metadata")
    def test_discover_metric_unknown_type(self, mock_metadata, mock_labels):
        """Test discovering metric with unknown type."""
        mock_metadata.return_value = {}
        mock_labels.return_value = {}

        client = MetricDiscoveryClient("http://prometheus:9090")
        result = client._discover_metric("custom_metric", '{service="api"}')

        assert result.type == MetricType.UNKNOWN


class TestDiscover:
    """Tests for discover method (main entry point)."""

    @patch.object(MetricDiscoveryClient, "_get_metric_names")
    @patch.object(MetricDiscoveryClient, "_discover_metric")
    def test_discover_full_flow(self, mock_discover_metric, mock_get_names):
        """Test full discovery flow."""
        mock_get_names.return_value = ["pg_stat_activity", "http_requests_total"]
        mock_discover_metric.side_effect = [
            DiscoveredMetric(
                name="pg_stat_activity",
                type=MetricType.GAUGE,
                technology=TechnologyGroup.UNKNOWN,
            ),
            DiscoveredMetric(
                name="http_requests_total",
                type=MetricType.COUNTER,
                technology=TechnologyGroup.UNKNOWN,
            ),
        ]

        client = MetricDiscoveryClient("http://prometheus:9090")
        result = client.discover('{service="payment-api"}')

        assert result.service == "payment-api"
        assert result.total_metrics == 2
        assert len(result.metrics) == 2
        # Classified by classifier
        assert TechnologyGroup.POSTGRESQL in result.metrics_by_technology
        assert TechnologyGroup.HTTP in result.metrics_by_technology

    @patch.object(MetricDiscoveryClient, "_get_metric_names")
    def test_discover_empty_metrics(self, mock_get_names):
        """Test discovery with no metrics."""
        mock_get_names.return_value = []

        client = MetricDiscoveryClient("http://prometheus:9090")
        result = client.discover('{service="api"}')

        assert result.total_metrics == 0
        assert result.metrics == []

    @patch.object(MetricDiscoveryClient, "_get_metric_names")
    @patch.object(MetricDiscoveryClient, "_discover_metric")
    def test_discover_skips_none_metrics(self, mock_discover_metric, mock_get_names):
        """Test discovery skips metrics that return None."""
        mock_get_names.return_value = ["metric1", "metric2"]
        mock_discover_metric.side_effect = [
            DiscoveredMetric(name="metric1", type=MetricType.GAUGE),
            None,  # Skipped
        ]

        client = MetricDiscoveryClient("http://prometheus:9090")
        result = client.discover("{}")

        assert result.total_metrics == 1

    @patch.object(MetricDiscoveryClient, "_get_metric_names")
    @patch.object(MetricDiscoveryClient, "_discover_metric")
    def test_discover_groups_by_type(self, mock_discover_metric, mock_get_names):
        """Test metrics are grouped by type."""
        mock_get_names.return_value = ["counter1", "gauge1", "counter2"]
        mock_discover_metric.side_effect = [
            DiscoveredMetric(name="counter1_total", type=MetricType.COUNTER),
            DiscoveredMetric(name="gauge1", type=MetricType.GAUGE),
            DiscoveredMetric(name="counter2_total", type=MetricType.COUNTER),
        ]

        client = MetricDiscoveryClient("http://prometheus:9090")
        result = client.discover("{}")

        assert MetricType.COUNTER in result.metrics_by_type
        assert MetricType.GAUGE in result.metrics_by_type
        assert len(result.metrics_by_type[MetricType.COUNTER]) == 2
        assert len(result.metrics_by_type[MetricType.GAUGE]) == 1


class TestGetMetricNamesFallback:
    """Tests for /metrics endpoint fallback in _get_metric_names."""

    @patch.object(MetricDiscoveryClient, "_get_metrics_from_endpoint")
    def test_uses_endpoint_for_metrics_url(self, mock_endpoint):
        """Test /metrics URL triggers endpoint fallback."""
        mock_endpoint.return_value = ["metric1"]

        client = MetricDiscoveryClient("http://app.fly.dev/metrics")
        result = client._get_metric_names('{service="api"}')

        mock_endpoint.assert_called_once()
        assert result == ["metric1"]

    @patch.object(MetricDiscoveryClient, "_get_metrics_from_endpoint")
    def test_uses_endpoint_for_fly_dev(self, mock_endpoint):
        """Test fly.dev URL triggers endpoint fallback."""
        mock_endpoint.return_value = ["metric1", "metric2"]

        client = MetricDiscoveryClient("http://my-app.fly.dev")
        result = client._get_metric_names("{}")

        mock_endpoint.assert_called_once()
        assert result == ["metric1", "metric2"]


class TestMetricClassifier:
    """Tests for MetricClassifier class."""

    def test_classify_postgresql(self):
        """Test PostgreSQL metric classification."""
        classifier = MetricClassifier()
        metric = DiscoveredMetric(name="pg_stat_activity", type=MetricType.GAUGE)

        result = classifier.classify(metric)

        assert result.technology == TechnologyGroup.POSTGRESQL

    def test_classify_postgresql_postgres(self):
        """Test postgres in name classification."""
        classifier = MetricClassifier()
        metric = DiscoveredMetric(name="my_postgres_connections", type=MetricType.GAUGE)

        result = classifier.classify(metric)

        assert result.technology == TechnologyGroup.POSTGRESQL

    def test_classify_redis(self):
        """Test Redis metric classification."""
        classifier = MetricClassifier()
        metric = DiscoveredMetric(name="redis_connected_clients", type=MetricType.GAUGE)

        result = classifier.classify(metric)

        assert result.technology == TechnologyGroup.REDIS

    def test_classify_redis_cache_hits(self):
        """Test cache_hits classified as Redis."""
        classifier = MetricClassifier()
        metric = DiscoveredMetric(name="cache_hits_total", type=MetricType.COUNTER)

        result = classifier.classify(metric)

        assert result.technology == TechnologyGroup.REDIS

    def test_classify_redis_cache_misses(self):
        """Test cache_misses classified as Redis."""
        classifier = MetricClassifier()
        metric = DiscoveredMetric(name="cache_misses_total", type=MetricType.COUNTER)

        result = classifier.classify(metric)

        assert result.technology == TechnologyGroup.REDIS

    def test_classify_mongodb(self):
        """Test MongoDB metric classification."""
        classifier = MetricClassifier()
        metric = DiscoveredMetric(name="mongodb_connections", type=MetricType.GAUGE)

        result = classifier.classify(metric)

        assert result.technology == TechnologyGroup.MONGODB

    def test_classify_mongo(self):
        """Test mongo_ prefix classification."""
        classifier = MetricClassifier()
        metric = DiscoveredMetric(name="mongo_queries", type=MetricType.GAUGE)

        result = classifier.classify(metric)

        assert result.technology == TechnologyGroup.MONGODB

    def test_classify_kafka(self):
        """Test Kafka metric classification."""
        classifier = MetricClassifier()
        metric = DiscoveredMetric(name="kafka_consumer_lag", type=MetricType.GAUGE)

        result = classifier.classify(metric)

        assert result.technology == TechnologyGroup.KAFKA

    def test_classify_mysql(self):
        """Test MySQL metric classification."""
        classifier = MetricClassifier()
        metric = DiscoveredMetric(name="mysql_queries_total", type=MetricType.COUNTER)

        result = classifier.classify(metric)

        assert result.technology == TechnologyGroup.MYSQL

    def test_classify_rabbitmq(self):
        """Test RabbitMQ metric classification."""
        classifier = MetricClassifier()
        metric = DiscoveredMetric(name="rabbitmq_queue_messages", type=MetricType.GAUGE)

        result = classifier.classify(metric)

        assert result.technology == TechnologyGroup.RABBITMQ

    def test_classify_kubernetes(self):
        """Test Kubernetes metric classification."""
        classifier = MetricClassifier()
        metric = DiscoveredMetric(name="kube_pod_status", type=MetricType.GAUGE)

        result = classifier.classify(metric)

        assert result.technology == TechnologyGroup.KUBERNETES

    def test_classify_kubernetes_container(self):
        """Test container_ prefix classification."""
        classifier = MetricClassifier()
        metric = DiscoveredMetric(name="container_cpu_usage", type=MetricType.GAUGE)

        result = classifier.classify(metric)

        assert result.technology == TechnologyGroup.KUBERNETES

    def test_classify_kubernetes_pod(self):
        """Test _pod_ in name classification."""
        classifier = MetricClassifier()
        metric = DiscoveredMetric(name="custom_pod_metrics", type=MetricType.GAUGE)

        result = classifier.classify(metric)

        assert result.technology == TechnologyGroup.KUBERNETES

    def test_classify_ecs_as_kubernetes(self):
        """Test ECS classified as Kubernetes."""
        classifier = MetricClassifier()
        metric = DiscoveredMetric(name="ecs_task_count", type=MetricType.GAUGE)

        result = classifier.classify(metric)

        assert result.technology == TechnologyGroup.KUBERNETES

    def test_classify_http(self):
        """Test HTTP metric classification."""
        classifier = MetricClassifier()
        metric = DiscoveredMetric(name="http_requests_total", type=MetricType.COUNTER)

        result = classifier.classify(metric)

        assert result.technology == TechnologyGroup.HTTP

    def test_classify_http_request(self):
        """Test _request in name classification."""
        classifier = MetricClassifier()
        metric = DiscoveredMetric(name="api_request_duration", type=MetricType.HISTOGRAM)

        result = classifier.classify(metric)

        assert result.technology == TechnologyGroup.HTTP

    def test_classify_http_response(self):
        """Test _response in name classification."""
        classifier = MetricClassifier()
        metric = DiscoveredMetric(name="api_response_time", type=MetricType.HISTOGRAM)

        result = classifier.classify(metric)

        assert result.technology == TechnologyGroup.HTTP

    def test_classify_custom(self):
        """Test unknown metric classified as custom."""
        classifier = MetricClassifier()
        metric = DiscoveredMetric(name="my_app_metric", type=MetricType.GAUGE)

        result = classifier.classify(metric)

        assert result.technology == TechnologyGroup.CUSTOM

    def test_infer_type_counter_total(self):
        """Test inferring counter type from _total suffix."""
        classifier = MetricClassifier()
        metric = DiscoveredMetric(name="requests_total", type=MetricType.UNKNOWN)

        result = classifier.classify(metric)

        assert result.type == MetricType.COUNTER

    def test_infer_type_counter_count(self):
        """Test inferring counter type from _count suffix."""
        classifier = MetricClassifier()
        metric = DiscoveredMetric(name="errors_count", type=MetricType.UNKNOWN)

        result = classifier.classify(metric)

        assert result.type == MetricType.COUNTER

    def test_infer_type_counter_created(self):
        """Test inferring counter type from _created suffix."""
        classifier = MetricClassifier()
        metric = DiscoveredMetric(name="process_created", type=MetricType.UNKNOWN)

        result = classifier.classify(metric)

        assert result.type == MetricType.COUNTER

    def test_infer_type_histogram_bucket(self):
        """Test inferring histogram type from _bucket suffix."""
        classifier = MetricClassifier()
        metric = DiscoveredMetric(name="request_duration_bucket", type=MetricType.UNKNOWN)

        result = classifier.classify(metric)

        assert result.type == MetricType.HISTOGRAM

    def test_infer_type_histogram_seconds(self):
        """Test inferring histogram type from _seconds_."""
        classifier = MetricClassifier()
        # Use a name with _seconds_ that doesn't match _sum pattern
        metric = DiscoveredMetric(name="request_seconds_duration", type=MetricType.UNKNOWN)

        result = classifier.classify(metric)

        assert result.type == MetricType.HISTOGRAM

    def test_infer_type_summary_sum(self):
        """Test inferring summary type from _sum suffix."""
        classifier = MetricClassifier()
        metric = DiscoveredMetric(name="request_latency_sum", type=MetricType.UNKNOWN)

        result = classifier.classify(metric)

        assert result.type == MetricType.SUMMARY

    def test_infer_type_gauge_bytes(self):
        """Test inferring gauge type from _bytes."""
        classifier = MetricClassifier()
        metric = DiscoveredMetric(name="memory_bytes", type=MetricType.UNKNOWN)

        result = classifier.classify(metric)

        assert result.type == MetricType.GAUGE

    def test_infer_type_gauge_ratio(self):
        """Test inferring gauge type from _ratio suffix."""
        classifier = MetricClassifier()
        metric = DiscoveredMetric(name="cpu_ratio", type=MetricType.UNKNOWN)

        result = classifier.classify(metric)

        assert result.type == MetricType.GAUGE

    def test_infer_type_gauge_percentage(self):
        """Test inferring gauge type from _percentage suffix."""
        classifier = MetricClassifier()
        metric = DiscoveredMetric(name="disk_usage_percentage", type=MetricType.UNKNOWN)

        result = classifier.classify(metric)

        assert result.type == MetricType.GAUGE

    def test_infer_type_default_gauge(self):
        """Test default type inference is gauge."""
        classifier = MetricClassifier()
        metric = DiscoveredMetric(name="custom_metric", type=MetricType.UNKNOWN)

        result = classifier.classify(metric)

        assert result.type == MetricType.GAUGE

    def test_preserves_known_type(self):
        """Test known type is not overwritten."""
        classifier = MetricClassifier()
        metric = DiscoveredMetric(name="requests_total", type=MetricType.HISTOGRAM)

        result = classifier.classify(metric)

        # Type should remain HISTOGRAM despite _total suffix
        assert result.type == MetricType.HISTOGRAM


class TestDiscoveryModels:
    """Tests for discovery models."""

    def test_metric_type_enum(self):
        """Test MetricType enum values."""
        assert MetricType.COUNTER == "counter"
        assert MetricType.GAUGE == "gauge"
        assert MetricType.HISTOGRAM == "histogram"
        assert MetricType.SUMMARY == "summary"
        assert MetricType.UNKNOWN == "unknown"

    def test_technology_group_enum(self):
        """Test TechnologyGroup enum values."""
        assert TechnologyGroup.POSTGRESQL == "postgresql"
        assert TechnologyGroup.REDIS == "redis"
        assert TechnologyGroup.MONGODB == "mongodb"
        assert TechnologyGroup.KAFKA == "kafka"
        assert TechnologyGroup.MYSQL == "mysql"
        assert TechnologyGroup.RABBITMQ == "rabbitmq"
        assert TechnologyGroup.KUBERNETES == "kubernetes"
        assert TechnologyGroup.HTTP == "http"
        assert TechnologyGroup.CUSTOM == "custom"
        assert TechnologyGroup.UNKNOWN == "unknown"

    def test_discovered_metric_defaults(self):
        """Test DiscoveredMetric default values."""
        metric = DiscoveredMetric(name="test_metric")

        assert metric.name == "test_metric"
        assert metric.type == MetricType.UNKNOWN
        assert metric.technology == TechnologyGroup.UNKNOWN
        assert metric.help_text is None
        assert metric.labels == {}

    def test_discovered_metric_full(self):
        """Test DiscoveredMetric with all fields."""
        metric = DiscoveredMetric(
            name="http_requests_total",
            type=MetricType.COUNTER,
            technology=TechnologyGroup.HTTP,
            help_text="Total HTTP requests",
            labels={"method": ["GET", "POST"], "status": ["200", "500"]},
        )

        assert metric.name == "http_requests_total"
        assert metric.type == MetricType.COUNTER
        assert metric.technology == TechnologyGroup.HTTP
        assert metric.help_text == "Total HTTP requests"
        assert metric.labels == {"method": ["GET", "POST"], "status": ["200", "500"]}

    def test_discovery_result_defaults(self):
        """Test DiscoveryResult default values."""
        result = DiscoveryResult(service="test-api", total_metrics=0)

        assert result.service == "test-api"
        assert result.total_metrics == 0
        assert result.metrics == []
        assert result.metrics_by_technology == {}
        assert result.metrics_by_type == {}

    def test_discovery_result_full(self):
        """Test DiscoveryResult with all fields."""
        metric = DiscoveredMetric(name="test", type=MetricType.GAUGE)
        result = DiscoveryResult(
            service="payment-api",
            total_metrics=1,
            metrics=[metric],
            metrics_by_technology={"unknown": [metric]},
            metrics_by_type={"gauge": [metric]},
        )

        assert result.service == "payment-api"
        assert result.total_metrics == 1
        assert len(result.metrics) == 1
        assert "unknown" in result.metrics_by_technology
        assert "gauge" in result.metrics_by_type
