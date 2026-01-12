"""Tests for Consul dependency provider."""

import pytest
import respx
from httpx import Response
from nthlayer.dependencies.models import DependencyType
from nthlayer.dependencies.providers.consul import (
    ConsulDepProvider,
    ConsulDepProviderError,
)

# Sample catalog data for testing
SAMPLE_CATALOG = {
    "consul": [],
    "payment-api": ["primary", "upstream:user-service", "db:postgresql"],
    "user-service": ["primary", "upstream:notification"],
    "notification": ["v2"],
    "postgresql": [],
}

# Sample health data for testing
SAMPLE_HEALTH_PAYMENT = [
    {
        "Node": {
            "Node": "node-1",
            "Address": "10.0.0.1",
            "Datacenter": "dc1",
        },
        "Service": {
            "ID": "payment-api-1",
            "Service": "payment-api",
            "Address": "10.0.0.1",
            "Port": 8080,
            "Tags": ["primary", "upstream:user-service", "db:postgresql"],
            "Meta": {
                "version": "1.0.0",
                "dependencies": "cache-service,audit-log",
            },
        },
        "Checks": [{"Status": "passing"}],
    }
]

SAMPLE_HEALTH_USER = [
    {
        "Node": {
            "Node": "node-2",
            "Address": "10.0.0.2",
            "Datacenter": "dc1",
        },
        "Service": {
            "ID": "user-service-1",
            "Service": "user-service",
            "Address": "10.0.0.2",
            "Port": 8081,
            "Tags": ["primary", "upstream:notification"],
            "Meta": {},
        },
        "Checks": [{"Status": "passing"}],
    }
]

# Sample intentions data
SAMPLE_INTENTIONS = [
    {
        "SourceName": "payment-api",
        "DestinationName": "user-service",
        "Action": "allow",
    },
    {
        "SourceName": "payment-api",
        "DestinationName": "postgresql",
        "Action": "allow",
    },
    {
        "SourceName": "checkout",
        "DestinationName": "payment-api",
        "Action": "allow",
    },
    {
        "SourceName": "blocked-service",
        "DestinationName": "payment-api",
        "Action": "deny",
    },
]


class TestConsulDepProviderInit:
    """Tests for provider initialization."""

    def test_init_defaults(self):
        """Test default initialization."""
        provider = ConsulDepProvider()
        assert provider.url == "http://localhost:8500"
        assert provider.token is None
        assert provider.datacenter is None
        assert provider.namespace is None
        assert provider.name == "consul"

    def test_init_with_url(self):
        """Test initialization with custom URL."""
        provider = ConsulDepProvider(url="http://consul.example.com:8500")
        assert provider.url == "http://consul.example.com:8500"

    def test_init_with_token(self):
        """Test initialization with ACL token."""
        provider = ConsulDepProvider(token="secret-acl-token")
        assert provider.token == "secret-acl-token"

    def test_init_with_datacenter(self):
        """Test initialization with datacenter filter."""
        provider = ConsulDepProvider(datacenter="dc1")
        assert provider.datacenter == "dc1"

    def test_init_with_namespace(self):
        """Test initialization with namespace (Enterprise)."""
        provider = ConsulDepProvider(namespace="production")
        assert provider.namespace == "production"

    def test_init_full(self):
        """Test initialization with all options."""
        provider = ConsulDepProvider(
            url="http://consul.example.com:8500",
            token="secret-token",
            datacenter="dc1",
            namespace="prod",
            timeout=60.0,
        )
        assert provider.url == "http://consul.example.com:8500"
        assert provider.token == "secret-token"
        assert provider.datacenter == "dc1"
        assert provider.namespace == "prod"
        assert provider.timeout == 60.0


class TestConsulDepProviderParseTags:
    """Tests for dependency tag parsing."""

    def test_parse_upstream_tag(self):
        """Test parsing upstream:service tag."""
        provider = ConsulDepProvider()
        deps = provider._parse_dependency_tags(["upstream:user-service"])

        assert len(deps) == 1
        assert deps[0] == ("user-service", DependencyType.SERVICE)

    def test_parse_depends_on_tag(self):
        """Test parsing depends-on:service tag."""
        provider = ConsulDepProvider()
        deps = provider._parse_dependency_tags(["depends-on:payment-api"])

        assert len(deps) == 1
        assert deps[0] == ("payment-api", DependencyType.SERVICE)

    def test_parse_db_tag(self):
        """Test parsing db:name tag."""
        provider = ConsulDepProvider()
        deps = provider._parse_dependency_tags(["db:postgresql"])

        assert len(deps) == 1
        assert deps[0] == ("postgresql", DependencyType.DATASTORE)

    def test_parse_database_tag(self):
        """Test parsing database:name tag."""
        provider = ConsulDepProvider()
        deps = provider._parse_dependency_tags(["database:mysql"])

        assert len(deps) == 1
        assert deps[0] == ("mysql", DependencyType.DATASTORE)

    def test_parse_queue_tag(self):
        """Test parsing queue:name tag."""
        provider = ConsulDepProvider()
        deps = provider._parse_dependency_tags(["queue:events"])

        assert len(deps) == 1
        assert deps[0] == ("events", DependencyType.QUEUE)

    def test_parse_mq_tag(self):
        """Test parsing mq:name tag."""
        provider = ConsulDepProvider()
        deps = provider._parse_dependency_tags(["mq:rabbitmq"])

        assert len(deps) == 1
        assert deps[0] == ("rabbitmq", DependencyType.QUEUE)

    def test_parse_external_tag(self):
        """Test parsing external:name tag."""
        provider = ConsulDepProvider()
        deps = provider._parse_dependency_tags(["external:stripe-api"])

        assert len(deps) == 1
        assert deps[0] == ("stripe-api", DependencyType.EXTERNAL)

    def test_parse_multiple_tags(self):
        """Test parsing multiple dependency tags."""
        provider = ConsulDepProvider()
        deps = provider._parse_dependency_tags(
            [
                "upstream:user-service",
                "db:postgresql",
                "queue:events",
                "primary",  # Non-dependency tag
            ]
        )

        assert len(deps) == 3
        targets = [d[0] for d in deps]
        assert "user-service" in targets
        assert "postgresql" in targets
        assert "events" in targets

    def test_parse_no_dependency_tags(self):
        """Test parsing tags with no dependencies."""
        provider = ConsulDepProvider()
        deps = provider._parse_dependency_tags(["primary", "v2", "stable"])

        assert deps == []

    def test_parse_case_insensitive(self):
        """Test that tag prefixes are case-insensitive."""
        provider = ConsulDepProvider()
        deps = provider._parse_dependency_tags(
            [
                "UPSTREAM:service-a",
                "DB:mysql",
            ]
        )

        assert len(deps) == 2


class TestConsulDepProviderInferType:
    """Tests for dependency type inference."""

    def test_infer_postgres(self):
        """Test inferring PostgreSQL as DATASTORE."""
        provider = ConsulDepProvider()
        assert provider._infer_dependency_type("postgresql") == DependencyType.DATASTORE

    def test_infer_mysql(self):
        """Test inferring MySQL as DATASTORE."""
        provider = ConsulDepProvider()
        assert provider._infer_dependency_type("mysql-primary") == DependencyType.DATASTORE

    def test_infer_redis(self):
        """Test inferring Redis as DATASTORE."""
        provider = ConsulDepProvider()
        assert provider._infer_dependency_type("redis-cache") == DependencyType.DATASTORE

    def test_infer_kafka(self):
        """Test inferring Kafka as QUEUE."""
        provider = ConsulDepProvider()
        assert provider._infer_dependency_type("kafka-cluster") == DependencyType.QUEUE

    def test_infer_rabbitmq(self):
        """Test inferring RabbitMQ as QUEUE."""
        provider = ConsulDepProvider()
        assert provider._infer_dependency_type("rabbitmq") == DependencyType.QUEUE

    def test_infer_service(self):
        """Test inferring regular service."""
        provider = ConsulDepProvider()
        assert provider._infer_dependency_type("payment-api") == DependencyType.SERVICE


@pytest.mark.asyncio
class TestConsulDepProviderListServices:
    """Tests for list_services()."""

    @respx.mock
    async def test_list_services(self):
        """Test listing all services."""
        respx.get("http://localhost:8500/v1/catalog/services").mock(
            return_value=Response(200, json=SAMPLE_CATALOG)
        )

        provider = ConsulDepProvider()
        services = await provider.list_services()

        # Should exclude consul itself
        assert "consul" not in services
        assert "payment-api" in services
        assert "user-service" in services
        assert "notification" in services
        assert "postgresql" in services
        assert len(services) == 4

    @respx.mock
    async def test_list_services_empty(self):
        """Test listing when only consul service exists."""
        respx.get("http://localhost:8500/v1/catalog/services").mock(
            return_value=Response(200, json={"consul": []})
        )

        provider = ConsulDepProvider()
        services = await provider.list_services()

        assert services == []

    @respx.mock
    async def test_list_services_with_datacenter(self):
        """Test listing services filters by datacenter."""
        respx.get("http://localhost:8500/v1/catalog/services").mock(
            return_value=Response(200, json=SAMPLE_CATALOG)
        )

        provider = ConsulDepProvider(datacenter="dc1")
        await provider.list_services()

        # Verify datacenter param was included
        request = respx.calls.last.request
        assert "dc=dc1" in str(request.url)


@pytest.mark.asyncio
class TestConsulDepProviderDiscover:
    """Tests for discover()."""

    @respx.mock
    async def test_discover_from_tags(self):
        """Test discovering dependencies from service tags."""
        respx.get("http://localhost:8500/v1/health/service/payment-api").mock(
            return_value=Response(200, json=SAMPLE_HEALTH_PAYMENT)
        )
        respx.get("http://localhost:8500/v1/connect/intentions/match").mock(
            return_value=Response(404)
        )

        provider = ConsulDepProvider()
        deps = await provider.discover("payment-api")

        # Should find user-service and postgresql from tags
        target_names = [d.target_service for d in deps]
        assert "user-service" in target_names
        assert "postgresql" in target_names

        # Check tag-based dependencies have correct confidence
        tag_deps = [d for d in deps if d.metadata.get("source") == "service_tag"]
        for dep in tag_deps:
            assert dep.confidence == 0.80

    @respx.mock
    async def test_discover_from_metadata(self):
        """Test discovering dependencies from service metadata."""
        respx.get("http://localhost:8500/v1/health/service/payment-api").mock(
            return_value=Response(200, json=SAMPLE_HEALTH_PAYMENT)
        )
        respx.get("http://localhost:8500/v1/connect/intentions/match").mock(
            return_value=Response(404)
        )

        provider = ConsulDepProvider()
        deps = await provider.discover("payment-api")

        # Should find dependencies from Meta.dependencies
        target_names = [d.target_service for d in deps]
        assert "cache-service" in target_names
        assert "audit-log" in target_names

        # Check metadata-based dependencies have correct confidence
        meta_deps = [d for d in deps if d.metadata.get("source") == "service_meta"]
        for dep in meta_deps:
            assert dep.confidence == 0.85

    @respx.mock
    async def test_discover_from_intentions(self):
        """Test discovering dependencies from Connect intentions."""
        respx.get("http://localhost:8500/v1/health/service/payment-api").mock(
            return_value=Response(200, json=[])
        )
        respx.get("http://localhost:8500/v1/connect/intentions/match").mock(
            return_value=Response(
                200,
                json={
                    "user-service": [{"Action": "allow"}],
                    "postgresql": [{"Action": "allow"}],
                },
            )
        )

        provider = ConsulDepProvider()
        deps = await provider.discover("payment-api")

        target_names = [d.target_service for d in deps]
        assert "user-service" in target_names
        assert "postgresql" in target_names

        # Check intention-based dependencies have correct confidence
        intention_deps = [d for d in deps if d.metadata.get("source") == "connect_intention"]
        for dep in intention_deps:
            assert dep.confidence == 0.95

    @respx.mock
    async def test_discover_not_found(self):
        """Test discovering dependencies for nonexistent service."""
        respx.get("http://localhost:8500/v1/health/service/nonexistent").mock(
            return_value=Response(200, json=[])
        )
        respx.get("http://localhost:8500/v1/connect/intentions/match").mock(
            return_value=Response(404)
        )

        provider = ConsulDepProvider()
        deps = await provider.discover("nonexistent")

        assert deps == []


@pytest.mark.asyncio
class TestConsulDepProviderDiscoverDownstream:
    """Tests for discover_downstream()."""

    @respx.mock
    async def test_discover_downstream(self):
        """Test discovering downstream dependencies."""
        respx.get("http://localhost:8500/v1/connect/intentions").mock(
            return_value=Response(200, json=SAMPLE_INTENTIONS)
        )

        provider = ConsulDepProvider()
        deps = await provider.discover_downstream("payment-api")

        # checkout calls payment-api
        source_names = [d.source_service for d in deps]
        assert "checkout" in source_names

        # blocked-service is denied, should not be included
        assert "blocked-service" not in source_names

    @respx.mock
    async def test_discover_downstream_none(self):
        """Test when nothing calls this service."""
        respx.get("http://localhost:8500/v1/connect/intentions").mock(
            return_value=Response(200, json=[])
        )

        provider = ConsulDepProvider()
        deps = await provider.discover_downstream("isolated-service")

        assert deps == []

    @respx.mock
    async def test_discover_downstream_connect_disabled(self):
        """Test graceful handling when Connect is disabled."""
        respx.get("http://localhost:8500/v1/connect/intentions").mock(return_value=Response(404))

        provider = ConsulDepProvider()
        deps = await provider.discover_downstream("payment-api")

        assert deps == []


@pytest.mark.asyncio
class TestConsulDepProviderHealthCheck:
    """Tests for health_check()."""

    @respx.mock
    async def test_health_check_success(self):
        """Test successful health check."""
        respx.get("http://localhost:8500/v1/status/leader").mock(
            return_value=Response(200, text='"10.0.0.1:8300"')
        )

        provider = ConsulDepProvider()
        health = await provider.health_check()

        assert health.healthy is True
        assert "Connected" in health.message
        assert "10.0.0.1:8300" in health.message

    @respx.mock
    async def test_health_check_no_leader(self):
        """Test health check with no leader."""
        respx.get("http://localhost:8500/v1/status/leader").mock(
            return_value=Response(200, text='""')
        )

        provider = ConsulDepProvider()
        health = await provider.health_check()

        assert health.healthy is False
        assert "no leader" in health.message

    @respx.mock
    async def test_health_check_auth_failure(self):
        """Test health check with auth failure."""
        respx.get("http://localhost:8500/v1/status/leader").mock(
            return_value=Response(403, json={"error": "Forbidden"})
        )

        provider = ConsulDepProvider()
        health = await provider.health_check()

        assert health.healthy is False
        assert "403" in health.message

    @respx.mock
    async def test_health_check_connection_error(self):
        """Test health check with connection error."""
        import httpx as httpx_module

        respx.get("http://localhost:8500/v1/status/leader").mock(
            side_effect=httpx_module.ConnectError("Connection refused")
        )

        provider = ConsulDepProvider()
        health = await provider.health_check()

        assert health.healthy is False
        assert "Connection" in health.message


@pytest.mark.asyncio
class TestConsulDepProviderGetAttributes:
    """Tests for get_service_attributes()."""

    @respx.mock
    async def test_get_service_attributes(self):
        """Test getting service attributes."""
        respx.get("http://localhost:8500/v1/health/service/payment-api").mock(
            return_value=Response(200, json=SAMPLE_HEALTH_PAYMENT)
        )

        provider = ConsulDepProvider()
        attrs = await provider.get_service_attributes("payment-api")

        assert attrs["name"] == "payment-api"
        assert attrs["id"] == "payment-api-1"
        assert attrs["address"] == "10.0.0.1"
        assert attrs["port"] == 8080
        assert "upstream:user-service" in attrs["tags"]
        assert attrs["meta"]["version"] == "1.0.0"
        assert attrs["datacenter"] == "dc1"

    @respx.mock
    async def test_get_service_attributes_not_found(self):
        """Test getting attributes for nonexistent service."""
        respx.get("http://localhost:8500/v1/health/service/nonexistent").mock(
            return_value=Response(200, json=[])
        )

        provider = ConsulDepProvider()
        attrs = await provider.get_service_attributes("nonexistent")

        assert attrs == {}


@pytest.mark.asyncio
class TestConsulDepProviderErrors:
    """Tests for error handling."""

    @respx.mock
    async def test_auth_error(self):
        """Test authentication error raises exception."""
        respx.get("http://localhost:8500/v1/catalog/services").mock(
            return_value=Response(401, json={"error": "Unauthorized"})
        )

        provider = ConsulDepProvider()

        with pytest.raises(ConsulDepProviderError) as exc_info:
            await provider.list_services()

        assert "Authentication failed" in str(exc_info.value)

    @respx.mock
    async def test_forbidden_error(self):
        """Test forbidden error raises exception."""
        respx.get("http://localhost:8500/v1/catalog/services").mock(
            return_value=Response(403, json={"error": "Forbidden"})
        )

        provider = ConsulDepProvider()

        with pytest.raises(ConsulDepProviderError) as exc_info:
            await provider.list_services()

        assert "Authentication failed" in str(exc_info.value)

    @respx.mock
    async def test_server_error(self):
        """Test server error raises exception."""
        respx.get("http://localhost:8500/v1/catalog/services").mock(
            return_value=Response(500, json={"error": "Internal error"})
        )

        provider = ConsulDepProvider()

        with pytest.raises(ConsulDepProviderError) as exc_info:
            await provider.list_services()

        assert "Catalog query failed" in str(exc_info.value)


class TestConsulDepProviderDeduplicate:
    """Tests for deduplication."""

    def test_deduplicate_keeps_highest_confidence(self):
        """Test deduplication keeps highest confidence."""
        from nthlayer.dependencies.models import DiscoveredDependency

        provider = ConsulDepProvider()

        deps = [
            DiscoveredDependency(
                source_service="a",
                target_service="b",
                provider="consul",
                dep_type=DependencyType.SERVICE,
                confidence=0.80,
                metadata={"source": "service_tag"},
            ),
            DiscoveredDependency(
                source_service="a",
                target_service="b",
                provider="consul",
                dep_type=DependencyType.SERVICE,
                confidence=0.95,
                metadata={"source": "connect_intention"},
            ),
        ]

        result = provider._deduplicate(deps)

        assert len(result) == 1
        assert result[0].confidence == 0.95
        assert result[0].metadata["source"] == "connect_intention"

    def test_deduplicate_different_targets(self):
        """Test deduplication keeps different targets."""
        from nthlayer.dependencies.models import DiscoveredDependency

        provider = ConsulDepProvider()

        deps = [
            DiscoveredDependency(
                source_service="a",
                target_service="b",
                provider="consul",
                dep_type=DependencyType.SERVICE,
                confidence=0.80,
            ),
            DiscoveredDependency(
                source_service="a",
                target_service="c",
                provider="consul",
                dep_type=DependencyType.SERVICE,
                confidence=0.80,
            ),
        ]

        result = provider._deduplicate(deps)

        assert len(result) == 2
