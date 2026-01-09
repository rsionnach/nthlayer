"""Tests for Zookeeper dependency provider."""

import json
from unittest.mock import MagicMock, patch

import pytest
from nthlayer.dependencies.models import DependencyType

# Sample Curator-style instance data
SAMPLE_INSTANCE_DATA = json.dumps(
    {
        "name": "payment-api",
        "id": "instance-1",
        "address": "10.0.0.1",
        "port": 8080,
        "payload": {
            "dependencies": ["user-service", "postgresql"],
            "databases": ["redis-cache"],
            "metadata": {
                "version": "1.0.0",
                "team": "payments",
            },
        },
    }
).encode("utf-8")

SAMPLE_SERVICE_DATA = json.dumps(
    {
        "name": "payment-api",
        "payload": {
            "dependencies": ["config-service"],
            "metadata": {"tier": "critical"},
        },
    }
).encode("utf-8")

SAMPLE_USER_INSTANCE = json.dumps(
    {
        "name": "user-service",
        "id": "instance-1",
        "address": "10.0.0.2",
        "port": 8081,
        "payload": {
            "dependencies": ["postgresql"],
        },
    }
).encode("utf-8")


# Mock the kazoo import
@pytest.fixture
def mock_kazoo():
    """Mock kazoo module for testing."""
    with patch.dict(
        "sys.modules",
        {
            "kazoo": MagicMock(),
            "kazoo.client": MagicMock(),
            "kazoo.exceptions": MagicMock(),
        },
    ):
        # Create mock classes
        mock_client_class = MagicMock()
        mock_client = MagicMock()
        mock_client_class.return_value = mock_client

        # Mock state
        mock_state = MagicMock()
        mock_state.CONNECTED = "CONNECTED"

        with patch("nthlayer.dependencies.providers.zookeeper.KAZOO_AVAILABLE", True):
            with patch("nthlayer.dependencies.providers.zookeeper.KazooClient", mock_client_class):
                with patch("nthlayer.dependencies.providers.zookeeper.KazooState", mock_state):
                    with patch("nthlayer.dependencies.providers.zookeeper.NoNodeError", Exception):
                        with patch(
                            "nthlayer.dependencies.providers.zookeeper.ZookeeperError", Exception
                        ):
                            yield mock_client


class TestZookeeperDepProviderInit:
    """Tests for provider initialization."""

    def test_init_defaults(self, mock_kazoo):
        """Test default initialization."""
        from nthlayer.dependencies.providers.zookeeper import ZookeeperDepProvider

        provider = ZookeeperDepProvider()
        assert provider.hosts == "localhost:2181"
        assert provider.root_path == "/services"
        assert provider.timeout == 30.0
        assert provider.auth is None
        assert provider.name == "zookeeper"

    def test_init_with_hosts(self, mock_kazoo):
        """Test initialization with custom hosts."""
        from nthlayer.dependencies.providers.zookeeper import ZookeeperDepProvider

        provider = ZookeeperDepProvider(hosts="zk1:2181,zk2:2181,zk3:2181")
        assert provider.hosts == "zk1:2181,zk2:2181,zk3:2181"

    def test_init_with_root_path(self, mock_kazoo):
        """Test initialization with custom root path."""
        from nthlayer.dependencies.providers.zookeeper import ZookeeperDepProvider

        provider = ZookeeperDepProvider(root_path="/discovery/services")
        assert provider.root_path == "/discovery/services"

    def test_init_with_auth(self, mock_kazoo):
        """Test initialization with authentication."""
        from nthlayer.dependencies.providers.zookeeper import ZookeeperDepProvider

        provider = ZookeeperDepProvider(auth=("digest", "user:password"))
        assert provider.auth == ("digest", "user:password")

    def test_init_full(self, mock_kazoo):
        """Test initialization with all options."""
        from nthlayer.dependencies.providers.zookeeper import ZookeeperDepProvider

        provider = ZookeeperDepProvider(
            hosts="zk.example.com:2181",
            root_path="/prod/services",
            timeout=60.0,
            auth=("digest", "admin:secret"),
        )
        assert provider.hosts == "zk.example.com:2181"
        assert provider.root_path == "/prod/services"
        assert provider.timeout == 60.0
        assert provider.auth == ("digest", "admin:secret")


class TestZookeeperDepProviderParseCurator:
    """Tests for Curator instance parsing."""

    def test_parse_valid_json(self, mock_kazoo):
        """Test parsing valid Curator JSON."""
        from nthlayer.dependencies.providers.zookeeper import ZookeeperDepProvider

        provider = ZookeeperDepProvider()
        data = provider._parse_curator_instance(SAMPLE_INSTANCE_DATA)

        assert data["name"] == "payment-api"
        assert data["id"] == "instance-1"
        assert data["address"] == "10.0.0.1"
        assert data["port"] == 8080
        assert "dependencies" in data["payload"]

    def test_parse_empty_data(self, mock_kazoo):
        """Test parsing empty data."""
        from nthlayer.dependencies.providers.zookeeper import ZookeeperDepProvider

        provider = ZookeeperDepProvider()
        data = provider._parse_curator_instance(b"")

        assert data == {}

    def test_parse_invalid_json(self, mock_kazoo):
        """Test parsing invalid JSON."""
        from nthlayer.dependencies.providers.zookeeper import ZookeeperDepProvider

        provider = ZookeeperDepProvider()
        data = provider._parse_curator_instance(b"not json")

        assert data == {}

    def test_parse_none_data(self, mock_kazoo):
        """Test parsing None data."""
        from nthlayer.dependencies.providers.zookeeper import ZookeeperDepProvider

        provider = ZookeeperDepProvider()
        data = provider._parse_curator_instance(None)

        assert data == {}


class TestZookeeperDepProviderParseDependencies:
    """Tests for dependency parsing from payload."""

    def test_parse_dependencies_list(self, mock_kazoo):
        """Test parsing dependencies from list."""
        from nthlayer.dependencies.providers.zookeeper import ZookeeperDepProvider

        provider = ZookeeperDepProvider()
        payload = {"dependencies": ["service-a", "service-b"]}
        deps = provider._parse_dependencies_from_payload(payload)

        assert len(deps) == 2
        targets = [d[0] for d in deps]
        assert "service-a" in targets
        assert "service-b" in targets

    def test_parse_dependencies_string(self, mock_kazoo):
        """Test parsing dependencies from comma-separated string."""
        from nthlayer.dependencies.providers.zookeeper import ZookeeperDepProvider

        provider = ZookeeperDepProvider()
        payload = {"dependencies": "service-a, service-b, service-c"}
        deps = provider._parse_dependencies_from_payload(payload)

        assert len(deps) == 3
        targets = [d[0] for d in deps]
        assert "service-a" in targets
        assert "service-b" in targets
        assert "service-c" in targets

    def test_parse_typed_databases(self, mock_kazoo):
        """Test parsing databases field."""
        from nthlayer.dependencies.providers.zookeeper import ZookeeperDepProvider

        provider = ZookeeperDepProvider()
        payload = {"databases": ["postgresql", "redis"]}
        deps = provider._parse_dependencies_from_payload(payload)

        assert len(deps) == 2
        for _, dep_type in deps:
            assert dep_type == DependencyType.DATASTORE

    def test_parse_typed_queues(self, mock_kazoo):
        """Test parsing queues field."""
        from nthlayer.dependencies.providers.zookeeper import ZookeeperDepProvider

        provider = ZookeeperDepProvider()
        payload = {"queues": ["kafka", "rabbitmq"]}
        deps = provider._parse_dependencies_from_payload(payload)

        assert len(deps) == 2
        for _, dep_type in deps:
            assert dep_type == DependencyType.QUEUE

    def test_parse_typed_external(self, mock_kazoo):
        """Test parsing external field."""
        from nthlayer.dependencies.providers.zookeeper import ZookeeperDepProvider

        provider = ZookeeperDepProvider()
        payload = {"external": ["stripe-api", "twilio"]}
        deps = provider._parse_dependencies_from_payload(payload)

        assert len(deps) == 2
        for _, dep_type in deps:
            assert dep_type == DependencyType.EXTERNAL

    def test_parse_combined(self, mock_kazoo):
        """Test parsing combined dependencies."""
        from nthlayer.dependencies.providers.zookeeper import ZookeeperDepProvider

        provider = ZookeeperDepProvider()
        payload = {
            "dependencies": ["user-service"],
            "databases": ["postgresql"],
            "queues": ["kafka"],
        }
        deps = provider._parse_dependencies_from_payload(payload)

        assert len(deps) == 3


class TestZookeeperDepProviderInferType:
    """Tests for dependency type inference."""

    def test_infer_postgres(self, mock_kazoo):
        """Test inferring PostgreSQL as DATASTORE."""
        from nthlayer.dependencies.providers.zookeeper import ZookeeperDepProvider

        provider = ZookeeperDepProvider()
        assert provider._infer_dependency_type("postgresql") == DependencyType.DATASTORE

    def test_infer_mysql(self, mock_kazoo):
        """Test inferring MySQL as DATASTORE."""
        from nthlayer.dependencies.providers.zookeeper import ZookeeperDepProvider

        provider = ZookeeperDepProvider()
        assert provider._infer_dependency_type("mysql-primary") == DependencyType.DATASTORE

    def test_infer_redis(self, mock_kazoo):
        """Test inferring Redis as DATASTORE."""
        from nthlayer.dependencies.providers.zookeeper import ZookeeperDepProvider

        provider = ZookeeperDepProvider()
        assert provider._infer_dependency_type("redis-cache") == DependencyType.DATASTORE

    def test_infer_kafka(self, mock_kazoo):
        """Test inferring Kafka as QUEUE."""
        from nthlayer.dependencies.providers.zookeeper import ZookeeperDepProvider

        provider = ZookeeperDepProvider()
        assert provider._infer_dependency_type("kafka-cluster") == DependencyType.QUEUE

    def test_infer_rabbitmq(self, mock_kazoo):
        """Test inferring RabbitMQ as QUEUE."""
        from nthlayer.dependencies.providers.zookeeper import ZookeeperDepProvider

        provider = ZookeeperDepProvider()
        assert provider._infer_dependency_type("rabbitmq") == DependencyType.QUEUE

    def test_infer_service(self, mock_kazoo):
        """Test inferring regular service."""
        from nthlayer.dependencies.providers.zookeeper import ZookeeperDepProvider

        provider = ZookeeperDepProvider()
        assert provider._infer_dependency_type("payment-api") == DependencyType.SERVICE


@pytest.mark.asyncio
class TestZookeeperDepProviderListServices:
    """Tests for list_services()."""

    async def test_list_services(self, mock_kazoo):
        """Test listing all services."""
        from nthlayer.dependencies.providers.zookeeper import ZookeeperDepProvider

        mock_kazoo.exists.return_value = True
        mock_kazoo.get_children.return_value = [
            "payment-api",
            "user-service",
            "notification",
        ]

        provider = ZookeeperDepProvider()
        provider._client = mock_kazoo
        provider._initialized = True

        services = await provider.list_services()

        assert "payment-api" in services
        assert "user-service" in services
        assert "notification" in services
        assert len(services) == 3

    async def test_list_services_filters_special(self, mock_kazoo):
        """Test that special znodes are filtered out."""
        from nthlayer.dependencies.providers.zookeeper import ZookeeperDepProvider

        mock_kazoo.exists.return_value = True
        mock_kazoo.get_children.return_value = [
            "payment-api",
            "_admin",
            "instances",
        ]

        provider = ZookeeperDepProvider()
        provider._client = mock_kazoo
        provider._initialized = True

        services = await provider.list_services()

        assert "payment-api" in services
        assert "_admin" not in services
        assert "instances" not in services

    async def test_list_services_root_not_exists(self, mock_kazoo):
        """Test listing when root path doesn't exist."""
        from nthlayer.dependencies.providers.zookeeper import ZookeeperDepProvider

        mock_kazoo.exists.return_value = False

        provider = ZookeeperDepProvider()
        provider._client = mock_kazoo
        provider._initialized = True

        services = await provider.list_services()

        assert services == []


@pytest.mark.asyncio
class TestZookeeperDepProviderDiscover:
    """Tests for discover()."""

    async def test_discover_from_instance(self, mock_kazoo):
        """Test discovering dependencies from instance data."""
        from nthlayer.dependencies.providers.zookeeper import ZookeeperDepProvider

        # Setup mock responses
        mock_kazoo.exists.side_effect = lambda path: True
        mock_kazoo.get.side_effect = lambda path: (
            (SAMPLE_SERVICE_DATA, MagicMock())
            if path == "/services/payment-api"
            else (SAMPLE_INSTANCE_DATA, MagicMock())
        )
        mock_kazoo.get_children.return_value = ["instance-1"]

        provider = ZookeeperDepProvider()
        provider._client = mock_kazoo
        provider._initialized = True

        deps = await provider.discover("payment-api")

        # Should find dependencies from both service and instance data
        target_names = [d.target_service for d in deps]
        assert "user-service" in target_names
        assert "postgresql" in target_names
        assert "config-service" in target_names

    async def test_discover_with_confidence(self, mock_kazoo):
        """Test that instance deps have higher confidence than service deps."""
        from nthlayer.dependencies.providers.zookeeper import ZookeeperDepProvider

        mock_kazoo.exists.side_effect = lambda path: True
        mock_kazoo.get.side_effect = lambda path: (
            (SAMPLE_SERVICE_DATA, MagicMock())
            if path == "/services/payment-api"
            else (SAMPLE_INSTANCE_DATA, MagicMock())
        )
        mock_kazoo.get_children.return_value = ["instance-1"]

        provider = ZookeeperDepProvider()
        provider._client = mock_kazoo
        provider._initialized = True

        deps = await provider.discover("payment-api")

        # Instance-based deps should be 0.90
        instance_deps = [d for d in deps if d.metadata.get("source") == "curator_instance"]
        for dep in instance_deps:
            assert dep.confidence == 0.90

        # Service-based deps should be 0.85
        service_deps = [d for d in deps if d.metadata.get("source") == "service_znode"]
        for dep in service_deps:
            assert dep.confidence == 0.85

    async def test_discover_service_not_found(self, mock_kazoo):
        """Test discovering for nonexistent service."""
        from nthlayer.dependencies.providers.zookeeper import ZookeeperDepProvider

        mock_kazoo.exists.return_value = False

        provider = ZookeeperDepProvider()
        provider._client = mock_kazoo
        provider._initialized = True

        deps = await provider.discover("nonexistent")

        assert deps == []

    async def test_discover_typed_databases(self, mock_kazoo):
        """Test that typed databases are discovered as DATASTORE."""
        from nthlayer.dependencies.providers.zookeeper import ZookeeperDepProvider

        mock_kazoo.exists.side_effect = lambda path: True
        mock_kazoo.get.side_effect = lambda path: (SAMPLE_INSTANCE_DATA, MagicMock())
        mock_kazoo.get_children.return_value = ["instance-1"]

        provider = ZookeeperDepProvider()
        provider._client = mock_kazoo
        provider._initialized = True

        deps = await provider.discover("payment-api")

        # redis-cache from databases field should be DATASTORE
        redis_deps = [d for d in deps if d.target_service == "redis-cache"]
        assert len(redis_deps) > 0
        assert redis_deps[0].dep_type == DependencyType.DATASTORE


@pytest.mark.asyncio
class TestZookeeperDepProviderHealthCheck:
    """Tests for health_check()."""

    async def test_health_check_success(self, mock_kazoo):
        """Test successful health check."""
        from nthlayer.dependencies.providers.zookeeper import ZookeeperDepProvider

        mock_kazoo.state = "CONNECTED"

        provider = ZookeeperDepProvider()
        provider._client = mock_kazoo
        provider._initialized = True

        with patch("nthlayer.dependencies.providers.zookeeper.KazooState") as mock_state:
            mock_state.CONNECTED = "CONNECTED"
            health = await provider.health_check()

        assert health.healthy is True
        assert "Connected" in health.message

    async def test_health_check_disconnected(self, mock_kazoo):
        """Test health check when disconnected."""
        from nthlayer.dependencies.providers.zookeeper import ZookeeperDepProvider

        mock_kazoo.state = "SUSPENDED"

        provider = ZookeeperDepProvider()
        provider._client = mock_kazoo
        provider._initialized = True

        with patch("nthlayer.dependencies.providers.zookeeper.KazooState") as mock_state:
            mock_state.CONNECTED = "CONNECTED"
            health = await provider.health_check()

        assert health.healthy is False
        assert "state" in health.message.lower()


@pytest.mark.asyncio
class TestZookeeperDepProviderGetAttributes:
    """Tests for get_service_attributes()."""

    async def test_get_service_attributes(self, mock_kazoo):
        """Test getting service attributes."""
        from nthlayer.dependencies.providers.zookeeper import ZookeeperDepProvider

        mock_stat = MagicMock()
        mock_stat.created = 1234567890
        mock_stat.last_modified = 1234567899

        mock_kazoo.exists.side_effect = lambda path: True
        mock_kazoo.get.side_effect = lambda path: (
            (SAMPLE_SERVICE_DATA, mock_stat)
            if path == "/services/payment-api"
            else (SAMPLE_INSTANCE_DATA, mock_stat)
        )
        mock_kazoo.get_children.return_value = ["instance-1"]

        provider = ZookeeperDepProvider()
        provider._client = mock_kazoo
        provider._initialized = True

        attrs = await provider.get_service_attributes("payment-api")

        assert attrs["name"] == "payment-api"
        assert attrs["path"] == "/services/payment-api"
        assert attrs["instance_count"] == 1
        assert len(attrs["instances"]) == 1

    async def test_get_service_attributes_not_found(self, mock_kazoo):
        """Test getting attributes for nonexistent service."""
        from nthlayer.dependencies.providers.zookeeper import ZookeeperDepProvider

        mock_kazoo.exists.return_value = False

        provider = ZookeeperDepProvider()
        provider._client = mock_kazoo
        provider._initialized = True

        attrs = await provider.get_service_attributes("nonexistent")

        assert attrs == {}


class TestZookeeperDepProviderDeduplicate:
    """Tests for deduplication."""

    def test_deduplicate_keeps_highest_confidence(self, mock_kazoo):
        """Test deduplication keeps highest confidence."""
        from nthlayer.dependencies.models import DiscoveredDependency
        from nthlayer.dependencies.providers.zookeeper import ZookeeperDepProvider

        provider = ZookeeperDepProvider()

        deps = [
            DiscoveredDependency(
                source_service="a",
                target_service="b",
                provider="zookeeper",
                dep_type=DependencyType.SERVICE,
                confidence=0.85,
                metadata={"source": "service_znode"},
            ),
            DiscoveredDependency(
                source_service="a",
                target_service="b",
                provider="zookeeper",
                dep_type=DependencyType.SERVICE,
                confidence=0.90,
                metadata={"source": "curator_instance"},
            ),
        ]

        result = provider._deduplicate(deps)

        assert len(result) == 1
        assert result[0].confidence == 0.90
        assert result[0].metadata["source"] == "curator_instance"

    def test_deduplicate_different_targets(self, mock_kazoo):
        """Test deduplication keeps different targets."""
        from nthlayer.dependencies.models import DiscoveredDependency
        from nthlayer.dependencies.providers.zookeeper import ZookeeperDepProvider

        provider = ZookeeperDepProvider()

        deps = [
            DiscoveredDependency(
                source_service="a",
                target_service="b",
                provider="zookeeper",
                dep_type=DependencyType.SERVICE,
                confidence=0.85,
            ),
            DiscoveredDependency(
                source_service="a",
                target_service="c",
                provider="zookeeper",
                dep_type=DependencyType.SERVICE,
                confidence=0.85,
            ),
        ]

        result = provider._deduplicate(deps)

        assert len(result) == 2


class TestZookeeperDepProviderNoKazoo:
    """Tests for behavior when kazoo is not installed."""

    def test_init_without_kazoo(self):
        """Test initialization fails gracefully without kazoo."""
        with patch("nthlayer.dependencies.providers.zookeeper.KAZOO_AVAILABLE", False):
            from nthlayer.dependencies.providers.zookeeper import (
                ZookeeperDepProvider,
                ZookeeperDepProviderError,
            )

            with pytest.raises(ZookeeperDepProviderError) as exc_info:
                ZookeeperDepProvider()

            assert "kazoo library is required" in str(exc_info.value)

    async def test_health_check_without_kazoo(self):
        """Test health check returns error without kazoo."""
        with patch("nthlayer.dependencies.providers.zookeeper.KAZOO_AVAILABLE", False):
            from nthlayer.dependencies.providers.zookeeper import ZookeeperDepProvider

            # Bypass __post_init__ validation
            provider = object.__new__(ZookeeperDepProvider)
            provider.hosts = "localhost:2181"
            provider.root_path = "/services"
            provider.timeout = 30.0
            provider.auth = None
            provider._client = None
            provider._initialized = False

            health = await provider.health_check()

            assert health.healthy is False
            assert "kazoo" in health.message.lower()
