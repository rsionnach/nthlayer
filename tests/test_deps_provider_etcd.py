"""Tests for etcd dependency provider."""

import json
from unittest.mock import MagicMock, patch

import pytest
from nthlayer.dependencies.models import DependencyType

# Sample service data for testing
SAMPLE_SERVICE_DATA = json.dumps(
    {
        "name": "payment-api",
        "endpoints": ["10.0.0.1:8080", "10.0.0.2:8080"],
        "dependencies": ["user-service", "postgresql"],
        "databases": ["redis-cache"],
        "queues": ["events-kafka"],
        "metadata": {
            "version": "1.0.0",
            "team": "payments",
            "tier": "critical",
        },
    }
).encode("utf-8")

SAMPLE_USER_SERVICE = json.dumps(
    {
        "name": "user-service",
        "endpoints": ["10.0.0.3:8081"],
        "dependencies": ["postgresql"],
        "metadata": {"team": "identity"},
    }
).encode("utf-8")


# Mock etcd3 module
@pytest.fixture
def mock_etcd3():
    """Mock etcd3 module for testing."""
    with patch.dict("sys.modules", {"etcd3": MagicMock()}):
        mock_client = MagicMock()
        mock_etcd_module = MagicMock()
        mock_etcd_module.client.return_value = mock_client

        with patch("nthlayer.dependencies.providers.etcd.ETCD3_AVAILABLE", True):
            with patch("nthlayer.dependencies.providers.etcd.etcd3", mock_etcd_module):
                yield mock_client


class TestEtcdDepProviderInit:
    """Tests for provider initialization."""

    def test_init_defaults(self, mock_etcd3):
        """Test default initialization."""
        from nthlayer.dependencies.providers.etcd import EtcdDepProvider

        provider = EtcdDepProvider()
        assert provider.host == "localhost"
        assert provider.port == 2379
        assert provider.prefix == "/services"
        assert provider.username is None
        assert provider.password is None
        assert provider.name == "etcd"

    def test_init_with_host(self, mock_etcd3):
        """Test initialization with custom host."""
        from nthlayer.dependencies.providers.etcd import EtcdDepProvider

        provider = EtcdDepProvider(host="etcd.example.com")
        assert provider.host == "etcd.example.com"

    def test_init_with_port(self, mock_etcd3):
        """Test initialization with custom port."""
        from nthlayer.dependencies.providers.etcd import EtcdDepProvider

        provider = EtcdDepProvider(port=2380)
        assert provider.port == 2380

    def test_init_with_prefix(self, mock_etcd3):
        """Test initialization with custom prefix."""
        from nthlayer.dependencies.providers.etcd import EtcdDepProvider

        provider = EtcdDepProvider(prefix="/prod/services")
        assert provider.prefix == "/prod/services"

    def test_init_with_auth(self, mock_etcd3):
        """Test initialization with authentication."""
        from nthlayer.dependencies.providers.etcd import EtcdDepProvider

        provider = EtcdDepProvider(username="admin", password="secret")
        assert provider.username == "admin"
        assert provider.password == "secret"

    def test_init_full(self, mock_etcd3):
        """Test initialization with all options."""
        from nthlayer.dependencies.providers.etcd import EtcdDepProvider

        provider = EtcdDepProvider(
            host="etcd.example.com",
            port=2380,
            prefix="/prod/services",
            username="admin",
            password="secret",
            timeout=60.0,
        )
        assert provider.host == "etcd.example.com"
        assert provider.port == 2380
        assert provider.prefix == "/prod/services"
        assert provider.username == "admin"
        assert provider.password == "secret"
        assert provider.timeout == 60.0


class TestEtcdDepProviderParseData:
    """Tests for service data parsing."""

    def test_parse_valid_json(self, mock_etcd3):
        """Test parsing valid JSON data."""
        from nthlayer.dependencies.providers.etcd import EtcdDepProvider

        provider = EtcdDepProvider()
        data = provider._parse_service_data(SAMPLE_SERVICE_DATA)

        assert data["name"] == "payment-api"
        assert len(data["endpoints"]) == 2
        assert "dependencies" in data

    def test_parse_string_data(self, mock_etcd3):
        """Test parsing string (not bytes) data."""
        from nthlayer.dependencies.providers.etcd import EtcdDepProvider

        provider = EtcdDepProvider()
        data = provider._parse_service_data('{"name": "test"}')

        assert data["name"] == "test"

    def test_parse_empty_data(self, mock_etcd3):
        """Test parsing empty data."""
        from nthlayer.dependencies.providers.etcd import EtcdDepProvider

        provider = EtcdDepProvider()
        data = provider._parse_service_data(b"")

        assert data == {}

    def test_parse_invalid_json(self, mock_etcd3):
        """Test parsing invalid JSON."""
        from nthlayer.dependencies.providers.etcd import EtcdDepProvider

        provider = EtcdDepProvider()
        data = provider._parse_service_data(b"not json")

        assert data == {}

    def test_parse_none_data(self, mock_etcd3):
        """Test parsing None data."""
        from nthlayer.dependencies.providers.etcd import EtcdDepProvider

        provider = EtcdDepProvider()
        data = provider._parse_service_data(None)

        assert data == {}


class TestEtcdDepProviderParseDependencies:
    """Tests for dependency parsing."""

    def test_parse_dependencies_list(self, mock_etcd3):
        """Test parsing dependencies from list."""
        from nthlayer.dependencies.providers.etcd import EtcdDepProvider

        provider = EtcdDepProvider()
        data = {"dependencies": ["service-a", "service-b"]}
        deps = provider._parse_dependencies(data)

        assert len(deps) == 2
        targets = [d[0] for d in deps]
        assert "service-a" in targets
        assert "service-b" in targets

    def test_parse_dependencies_string(self, mock_etcd3):
        """Test parsing dependencies from comma-separated string."""
        from nthlayer.dependencies.providers.etcd import EtcdDepProvider

        provider = EtcdDepProvider()
        data = {"dependencies": "service-a, service-b, service-c"}
        deps = provider._parse_dependencies(data)

        assert len(deps) == 3

    def test_parse_databases(self, mock_etcd3):
        """Test parsing databases field."""
        from nthlayer.dependencies.providers.etcd import EtcdDepProvider

        provider = EtcdDepProvider()
        data = {"databases": ["postgresql", "redis"]}
        deps = provider._parse_dependencies(data)

        assert len(deps) == 2
        for _, dep_type in deps:
            assert dep_type == DependencyType.DATASTORE

    def test_parse_datastores(self, mock_etcd3):
        """Test parsing datastores field (alternative name)."""
        from nthlayer.dependencies.providers.etcd import EtcdDepProvider

        provider = EtcdDepProvider()
        data = {"datastores": ["mongodb"]}
        deps = provider._parse_dependencies(data)

        assert len(deps) == 1
        assert deps[0][1] == DependencyType.DATASTORE

    def test_parse_queues(self, mock_etcd3):
        """Test parsing queues field."""
        from nthlayer.dependencies.providers.etcd import EtcdDepProvider

        provider = EtcdDepProvider()
        data = {"queues": ["kafka", "rabbitmq"]}
        deps = provider._parse_dependencies(data)

        assert len(deps) == 2
        for _, dep_type in deps:
            assert dep_type == DependencyType.QUEUE

    def test_parse_messaging(self, mock_etcd3):
        """Test parsing messaging field (alternative name)."""
        from nthlayer.dependencies.providers.etcd import EtcdDepProvider

        provider = EtcdDepProvider()
        data = {"messaging": ["nats"]}
        deps = provider._parse_dependencies(data)

        assert len(deps) == 1
        assert deps[0][1] == DependencyType.QUEUE

    def test_parse_external(self, mock_etcd3):
        """Test parsing external field."""
        from nthlayer.dependencies.providers.etcd import EtcdDepProvider

        provider = EtcdDepProvider()
        data = {"external": ["stripe-api", "twilio"]}
        deps = provider._parse_dependencies(data)

        assert len(deps) == 2
        for _, dep_type in deps:
            assert dep_type == DependencyType.EXTERNAL

    def test_parse_external_apis(self, mock_etcd3):
        """Test parsing external_apis field (alternative name)."""
        from nthlayer.dependencies.providers.etcd import EtcdDepProvider

        provider = EtcdDepProvider()
        data = {"external_apis": ["sendgrid"]}
        deps = provider._parse_dependencies(data)

        assert len(deps) == 1
        assert deps[0][1] == DependencyType.EXTERNAL

    def test_parse_services(self, mock_etcd3):
        """Test parsing services field."""
        from nthlayer.dependencies.providers.etcd import EtcdDepProvider

        provider = EtcdDepProvider()
        data = {"services": ["auth-service"]}
        deps = provider._parse_dependencies(data)

        assert len(deps) == 1
        assert deps[0][1] == DependencyType.SERVICE

    def test_parse_upstream(self, mock_etcd3):
        """Test parsing upstream field."""
        from nthlayer.dependencies.providers.etcd import EtcdDepProvider

        provider = EtcdDepProvider()
        data = {"upstream": ["gateway"]}
        deps = provider._parse_dependencies(data)

        assert len(deps) == 1
        assert deps[0][1] == DependencyType.SERVICE

    def test_parse_combined(self, mock_etcd3):
        """Test parsing combined dependencies."""
        from nthlayer.dependencies.providers.etcd import EtcdDepProvider

        provider = EtcdDepProvider()
        data = {
            "dependencies": ["user-service"],
            "databases": ["postgresql"],
            "queues": ["kafka"],
            "external": ["stripe"],
        }
        deps = provider._parse_dependencies(data)

        assert len(deps) == 4


class TestEtcdDepProviderInferType:
    """Tests for dependency type inference."""

    def test_infer_postgres(self, mock_etcd3):
        """Test inferring PostgreSQL as DATASTORE."""
        from nthlayer.dependencies.providers.etcd import EtcdDepProvider

        provider = EtcdDepProvider()
        assert provider._infer_dependency_type("postgresql") == DependencyType.DATASTORE

    def test_infer_mysql(self, mock_etcd3):
        """Test inferring MySQL as DATASTORE."""
        from nthlayer.dependencies.providers.etcd import EtcdDepProvider

        provider = EtcdDepProvider()
        assert provider._infer_dependency_type("mysql-primary") == DependencyType.DATASTORE

    def test_infer_redis(self, mock_etcd3):
        """Test inferring Redis as DATASTORE."""
        from nthlayer.dependencies.providers.etcd import EtcdDepProvider

        provider = EtcdDepProvider()
        assert provider._infer_dependency_type("redis-cache") == DependencyType.DATASTORE

    def test_infer_kafka(self, mock_etcd3):
        """Test inferring Kafka as QUEUE."""
        from nthlayer.dependencies.providers.etcd import EtcdDepProvider

        provider = EtcdDepProvider()
        assert provider._infer_dependency_type("kafka-cluster") == DependencyType.QUEUE

    def test_infer_rabbitmq(self, mock_etcd3):
        """Test inferring RabbitMQ as QUEUE."""
        from nthlayer.dependencies.providers.etcd import EtcdDepProvider

        provider = EtcdDepProvider()
        assert provider._infer_dependency_type("rabbitmq") == DependencyType.QUEUE

    def test_infer_service(self, mock_etcd3):
        """Test inferring regular service."""
        from nthlayer.dependencies.providers.etcd import EtcdDepProvider

        provider = EtcdDepProvider()
        assert provider._infer_dependency_type("payment-api") == DependencyType.SERVICE


@pytest.mark.asyncio
class TestEtcdDepProviderListServices:
    """Tests for list_services()."""

    async def test_list_services(self, mock_etcd3):
        """Test listing all services."""
        from nthlayer.dependencies.providers.etcd import EtcdDepProvider

        # Setup mock responses
        mock_metadata1 = MagicMock()
        mock_metadata1.key = b"/services/payment-api"
        mock_metadata2 = MagicMock()
        mock_metadata2.key = b"/services/user-service"
        mock_metadata3 = MagicMock()
        mock_metadata3.key = b"/services/notification"

        mock_etcd3.get_prefix.return_value = [
            (SAMPLE_SERVICE_DATA, mock_metadata1),
            (SAMPLE_USER_SERVICE, mock_metadata2),
            (b'{"name": "notification"}', mock_metadata3),
        ]

        provider = EtcdDepProvider()
        provider._client = mock_etcd3
        provider._initialized = True

        services = await provider.list_services()

        assert "payment-api" in services
        assert "user-service" in services
        assert "notification" in services
        assert len(services) == 3

    async def test_list_services_with_subkeys(self, mock_etcd3):
        """Test that subkeys are handled correctly."""
        from nthlayer.dependencies.providers.etcd import EtcdDepProvider

        mock_metadata1 = MagicMock()
        mock_metadata1.key = b"/services/payment-api"
        mock_metadata2 = MagicMock()
        mock_metadata2.key = b"/services/payment-api/instances/1"

        mock_etcd3.get_prefix.return_value = [
            (SAMPLE_SERVICE_DATA, mock_metadata1),
            (b"{}", mock_metadata2),
        ]

        provider = EtcdDepProvider()
        provider._client = mock_etcd3
        provider._initialized = True

        services = await provider.list_services()

        # Should deduplicate to just payment-api
        assert "payment-api" in services
        assert len(services) == 1

    async def test_list_services_filters_internal(self, mock_etcd3):
        """Test that internal keys are filtered out."""
        from nthlayer.dependencies.providers.etcd import EtcdDepProvider

        mock_metadata1 = MagicMock()
        mock_metadata1.key = b"/services/payment-api"
        mock_metadata2 = MagicMock()
        mock_metadata2.key = b"/services/_internal"

        mock_etcd3.get_prefix.return_value = [
            (SAMPLE_SERVICE_DATA, mock_metadata1),
            (b"{}", mock_metadata2),
        ]

        provider = EtcdDepProvider()
        provider._client = mock_etcd3
        provider._initialized = True

        services = await provider.list_services()

        assert "payment-api" in services
        assert "_internal" not in services


@pytest.mark.asyncio
class TestEtcdDepProviderDiscover:
    """Tests for discover()."""

    async def test_discover_dependencies(self, mock_etcd3):
        """Test discovering dependencies from service data."""
        from nthlayer.dependencies.providers.etcd import EtcdDepProvider

        mock_metadata = MagicMock()
        mock_etcd3.get.return_value = (SAMPLE_SERVICE_DATA, mock_metadata)

        provider = EtcdDepProvider()
        provider._client = mock_etcd3
        provider._initialized = True

        deps = await provider.discover("payment-api")

        target_names = [d.target_service for d in deps]
        assert "user-service" in target_names
        assert "postgresql" in target_names
        assert "redis-cache" in target_names
        assert "events-kafka" in target_names

    async def test_discover_typed_dependencies(self, mock_etcd3):
        """Test that typed dependencies get correct types."""
        from nthlayer.dependencies.providers.etcd import EtcdDepProvider

        mock_metadata = MagicMock()
        mock_etcd3.get.return_value = (SAMPLE_SERVICE_DATA, mock_metadata)

        provider = EtcdDepProvider()
        provider._client = mock_etcd3
        provider._initialized = True

        deps = await provider.discover("payment-api")

        # redis-cache from databases should be DATASTORE
        redis_deps = [d for d in deps if d.target_service == "redis-cache"]
        assert len(redis_deps) > 0
        assert redis_deps[0].dep_type == DependencyType.DATASTORE

        # events-kafka from queues should be QUEUE
        kafka_deps = [d for d in deps if d.target_service == "events-kafka"]
        assert len(kafka_deps) > 0
        assert kafka_deps[0].dep_type == DependencyType.QUEUE

    async def test_discover_not_found(self, mock_etcd3):
        """Test discovering for nonexistent service."""
        from nthlayer.dependencies.providers.etcd import EtcdDepProvider

        mock_etcd3.get.return_value = (None, None)

        provider = EtcdDepProvider()
        provider._client = mock_etcd3
        provider._initialized = True

        deps = await provider.discover("nonexistent")

        assert deps == []

    async def test_discover_empty_data(self, mock_etcd3):
        """Test discovering when service has no dependencies."""
        from nthlayer.dependencies.providers.etcd import EtcdDepProvider

        mock_metadata = MagicMock()
        mock_etcd3.get.return_value = (b'{"name": "empty-service"}', mock_metadata)

        provider = EtcdDepProvider()
        provider._client = mock_etcd3
        provider._initialized = True

        deps = await provider.discover("empty-service")

        assert deps == []


@pytest.mark.asyncio
class TestEtcdDepProviderHealthCheck:
    """Tests for health_check()."""

    async def test_health_check_success(self, mock_etcd3):
        """Test successful health check."""
        from nthlayer.dependencies.providers.etcd import EtcdDepProvider

        mock_status = MagicMock()
        mock_status.leader = 12345
        mock_status.version = "3.5.0"
        mock_etcd3.status.return_value = mock_status

        provider = EtcdDepProvider()
        provider._client = mock_etcd3
        provider._initialized = True

        health = await provider.health_check()

        assert health.healthy is True
        assert "Connected" in health.message
        assert "3.5.0" in health.message

    async def test_health_check_no_status(self, mock_etcd3):
        """Test health check when status unavailable."""
        from nthlayer.dependencies.providers.etcd import EtcdDepProvider

        mock_etcd3.status.return_value = None

        provider = EtcdDepProvider()
        provider._client = mock_etcd3
        provider._initialized = True

        health = await provider.health_check()

        assert health.healthy is False
        assert "unavailable" in health.message

    async def test_health_check_connection_error(self, mock_etcd3):
        """Test health check with connection error."""
        from nthlayer.dependencies.providers.etcd import EtcdDepProvider

        mock_etcd3.status.side_effect = Exception("Connection refused")

        provider = EtcdDepProvider()
        provider._client = mock_etcd3
        provider._initialized = True

        health = await provider.health_check()

        assert health.healthy is False
        assert "failed" in health.message


@pytest.mark.asyncio
class TestEtcdDepProviderGetAttributes:
    """Tests for get_service_attributes()."""

    async def test_get_service_attributes(self, mock_etcd3):
        """Test getting service attributes."""
        from nthlayer.dependencies.providers.etcd import EtcdDepProvider

        mock_metadata = MagicMock()
        mock_metadata.version = 5
        mock_metadata.mod_revision = 123456
        mock_etcd3.get.return_value = (SAMPLE_SERVICE_DATA, mock_metadata)

        provider = EtcdDepProvider()
        provider._client = mock_etcd3
        provider._initialized = True

        attrs = await provider.get_service_attributes("payment-api")

        assert attrs["name"] == "payment-api"
        assert len(attrs["endpoints"]) == 2
        assert attrs["metadata"]["team"] == "payments"
        assert attrs["version"] == 5
        assert attrs["mod_revision"] == 123456

    async def test_get_service_attributes_not_found(self, mock_etcd3):
        """Test getting attributes for nonexistent service."""
        from nthlayer.dependencies.providers.etcd import EtcdDepProvider

        mock_etcd3.get.return_value = (None, None)

        provider = EtcdDepProvider()
        provider._client = mock_etcd3
        provider._initialized = True

        attrs = await provider.get_service_attributes("nonexistent")

        assert attrs == {}


class TestEtcdDepProviderDeduplicate:
    """Tests for deduplication."""

    def test_deduplicate_keeps_highest_confidence(self, mock_etcd3):
        """Test deduplication keeps highest confidence."""
        from nthlayer.dependencies.models import DiscoveredDependency
        from nthlayer.dependencies.providers.etcd import EtcdDepProvider

        provider = EtcdDepProvider()

        deps = [
            DiscoveredDependency(
                source_service="a",
                target_service="b",
                provider="etcd",
                dep_type=DependencyType.SERVICE,
                confidence=0.80,
            ),
            DiscoveredDependency(
                source_service="a",
                target_service="b",
                provider="etcd",
                dep_type=DependencyType.SERVICE,
                confidence=0.85,
            ),
        ]

        result = provider._deduplicate(deps)

        assert len(result) == 1
        assert result[0].confidence == 0.85

    def test_deduplicate_different_targets(self, mock_etcd3):
        """Test deduplication keeps different targets."""
        from nthlayer.dependencies.models import DiscoveredDependency
        from nthlayer.dependencies.providers.etcd import EtcdDepProvider

        provider = EtcdDepProvider()

        deps = [
            DiscoveredDependency(
                source_service="a",
                target_service="b",
                provider="etcd",
                dep_type=DependencyType.SERVICE,
                confidence=0.85,
            ),
            DiscoveredDependency(
                source_service="a",
                target_service="c",
                provider="etcd",
                dep_type=DependencyType.SERVICE,
                confidence=0.85,
            ),
        ]

        result = provider._deduplicate(deps)

        assert len(result) == 2


class TestEtcdDepProviderNoEtcd3:
    """Tests for behavior when etcd3 is not installed."""

    def test_init_without_etcd3(self):
        """Test initialization fails gracefully without etcd3."""
        with patch("nthlayer.dependencies.providers.etcd.ETCD3_AVAILABLE", False):
            from nthlayer.dependencies.providers.etcd import (
                EtcdDepProvider,
                EtcdDepProviderError,
            )

            with pytest.raises(EtcdDepProviderError) as exc_info:
                EtcdDepProvider()

            assert "etcd3 library is required" in str(exc_info.value)

    async def test_health_check_without_etcd3(self):
        """Test health check returns error without etcd3."""
        with patch("nthlayer.dependencies.providers.etcd.ETCD3_AVAILABLE", False):
            from nthlayer.dependencies.providers.etcd import EtcdDepProvider

            # Bypass __post_init__ validation
            provider = object.__new__(EtcdDepProvider)
            provider.host = "localhost"
            provider.port = 2379
            provider.prefix = "/services"
            provider.username = None
            provider.password = None
            provider.timeout = 30.0
            provider._client = None
            provider._initialized = False

            health = await provider.health_check()

            assert health.healthy is False
            assert "etcd3" in health.message.lower()
