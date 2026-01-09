"""Tests for Backstage dependency provider."""

import pytest
import respx
from httpx import Response
from nthlayer.dependencies.models import DependencyType
from nthlayer.dependencies.providers.backstage import (
    BackstageDepProvider,
    BackstageDepProviderError,
)

# Sample catalog entities for testing
SAMPLE_ENTITIES = [
    {
        "apiVersion": "backstage.io/v1alpha1",
        "kind": "Component",
        "metadata": {
            "name": "payment-api",
            "namespace": "default",
            "uid": "abc-123",
        },
        "spec": {
            "type": "service",
            "owner": "team-payments",
            "dependsOn": [
                "component:user-service",
                "resource:postgresql",
                "component:default/audit-service",
            ],
            "consumesApis": ["notification-api"],
        },
    },
    {
        "apiVersion": "backstage.io/v1alpha1",
        "kind": "Component",
        "metadata": {
            "name": "user-service",
            "namespace": "default",
            "uid": "def-456",
        },
        "spec": {
            "type": "service",
            "owner": "team-identity",
            "dependsOn": ["resource:postgresql"],
        },
    },
    {
        "apiVersion": "backstage.io/v1alpha1",
        "kind": "Component",
        "metadata": {
            "name": "checkout-api",
            "namespace": "default",
            "uid": "ghi-789",
        },
        "spec": {
            "type": "service",
            "owner": "team-commerce",
            "dependsOn": ["component:payment-api"],
        },
    },
]


class TestBackstageDepProviderInit:
    """Tests for provider initialization."""

    def test_init_minimal(self):
        """Test minimal initialization."""
        provider = BackstageDepProvider(url="https://backstage.example.com")
        assert provider.url == "https://backstage.example.com"
        assert provider.token is None
        assert provider.namespace is None
        assert provider.name == "backstage"

    def test_init_with_token(self):
        """Test initialization with token."""
        provider = BackstageDepProvider(
            url="https://backstage.example.com",
            token="secret-token",
        )
        assert provider.token == "secret-token"

    def test_init_with_namespace(self):
        """Test initialization with namespace filter."""
        provider = BackstageDepProvider(
            url="https://backstage.example.com",
            namespace="production",
        )
        assert provider.namespace == "production"


class TestBackstageDepProviderParseEntityRef:
    """Tests for entity reference parsing."""

    def test_parse_simple_ref(self):
        """Test parsing simple kind:name reference."""
        provider = BackstageDepProvider(url="https://backstage.example.com")
        kind, namespace, name = provider._parse_entity_ref("component:payment-api")
        assert kind == "component"
        assert namespace is None
        assert name == "payment-api"

    def test_parse_namespaced_ref(self):
        """Test parsing kind:namespace/name reference."""
        provider = BackstageDepProvider(url="https://backstage.example.com")
        kind, namespace, name = provider._parse_entity_ref("component:production/payment-api")
        assert kind == "component"
        assert namespace == "production"
        assert name == "payment-api"

    def test_parse_resource_ref(self):
        """Test parsing resource reference."""
        provider = BackstageDepProvider(url="https://backstage.example.com")
        kind, namespace, name = provider._parse_entity_ref("resource:postgresql")
        assert kind == "resource"
        assert namespace is None
        assert name == "postgresql"

    def test_parse_fallback(self):
        """Test fallback for malformed reference."""
        provider = BackstageDepProvider(url="https://backstage.example.com")
        kind, namespace, name = provider._parse_entity_ref("just-a-name")
        assert kind == "component"
        assert namespace is None
        assert name == "just-a-name"


class TestBackstageDepProviderInferType:
    """Tests for dependency type inference."""

    def test_infer_component_type(self):
        """Test component infers to SERVICE."""
        provider = BackstageDepProvider(url="https://backstage.example.com")
        dep_type = provider._infer_dependency_type("component", "payment-api")
        assert dep_type == DependencyType.SERVICE

    def test_infer_resource_database(self):
        """Test database resource infers to DATASTORE."""
        provider = BackstageDepProvider(url="https://backstage.example.com")
        assert provider._infer_dependency_type("resource", "postgresql") == DependencyType.DATASTORE
        assert (
            provider._infer_dependency_type("resource", "mysql-primary") == DependencyType.DATASTORE
        )
        assert (
            provider._infer_dependency_type("resource", "redis-cache") == DependencyType.DATASTORE
        )

    def test_infer_resource_queue(self):
        """Test queue resource infers to QUEUE."""
        provider = BackstageDepProvider(url="https://backstage.example.com")
        assert provider._infer_dependency_type("resource", "kafka-cluster") == DependencyType.QUEUE
        assert provider._infer_dependency_type("resource", "rabbitmq") == DependencyType.QUEUE

    def test_infer_resource_other(self):
        """Test other resource infers to INFRASTRUCTURE."""
        provider = BackstageDepProvider(url="https://backstage.example.com")
        assert (
            provider._infer_dependency_type("resource", "s3-bucket")
            == DependencyType.INFRASTRUCTURE
        )

    def test_infer_api_type(self):
        """Test API infers to SERVICE."""
        provider = BackstageDepProvider(url="https://backstage.example.com")
        assert provider._infer_dependency_type("api", "payment-api") == DependencyType.SERVICE


@pytest.mark.asyncio
class TestBackstageDepProviderListServices:
    """Tests for list_services()."""

    @respx.mock
    async def test_list_services(self):
        """Test listing all services."""
        respx.get("https://backstage.example.com/api/catalog/entities").mock(
            return_value=Response(200, json=SAMPLE_ENTITIES)
        )

        provider = BackstageDepProvider(url="https://backstage.example.com")
        services = await provider.list_services()

        assert "payment-api" in services
        assert "user-service" in services
        assert "checkout-api" in services
        assert len(services) == 3

    @respx.mock
    async def test_list_services_empty(self):
        """Test listing when no services exist."""
        respx.get("https://backstage.example.com/api/catalog/entities").mock(
            return_value=Response(200, json=[])
        )

        provider = BackstageDepProvider(url="https://backstage.example.com")
        services = await provider.list_services()

        assert services == []


@pytest.mark.asyncio
class TestBackstageDepProviderDiscover:
    """Tests for discover()."""

    @respx.mock
    async def test_discover_explicit_dependencies(self):
        """Test discovering dependencies from spec.dependsOn."""
        # Mock entity lookup
        respx.get(
            "https://backstage.example.com/api/catalog/entities/by-name/component/default/payment-api"
        ).mock(return_value=Response(200, json=SAMPLE_ENTITIES[0]))

        provider = BackstageDepProvider(url="https://backstage.example.com")
        deps = await provider.discover("payment-api")

        # Should find user-service, postgresql, audit-service from dependsOn
        target_names = [d.target_service for d in deps]
        assert "user-service" in target_names
        assert "postgresql" in target_names
        assert "audit-service" in target_names

        # Check confidence
        for dep in deps:
            if dep.metadata.get("source") == "spec.dependsOn":
                assert dep.confidence == 0.95

    @respx.mock
    async def test_discover_consumed_apis(self):
        """Test discovering dependencies from spec.consumesApis."""
        respx.get(
            "https://backstage.example.com/api/catalog/entities/by-name/component/default/payment-api"
        ).mock(return_value=Response(200, json=SAMPLE_ENTITIES[0]))

        provider = BackstageDepProvider(url="https://backstage.example.com")
        deps = await provider.discover("payment-api")

        # Should find notification-api from consumesApis
        api_deps = [d for d in deps if d.metadata.get("source") == "spec.consumesApis"]
        assert len(api_deps) == 1
        assert api_deps[0].target_service == "notification-api"
        assert api_deps[0].confidence == 0.90

    @respx.mock
    async def test_discover_not_found_fallback(self):
        """Test fallback to search when entity not found directly."""
        # Direct lookup returns 404
        respx.get(
            "https://backstage.example.com/api/catalog/entities/by-name/component/default/payment-api"
        ).mock(return_value=Response(404))

        # Search returns all entities
        respx.get("https://backstage.example.com/api/catalog/entities").mock(
            return_value=Response(200, json=SAMPLE_ENTITIES)
        )

        provider = BackstageDepProvider(url="https://backstage.example.com")
        deps = await provider.discover("payment-api")

        # Should still find dependencies via search
        assert len(deps) > 0

    @respx.mock
    async def test_discover_entity_not_found(self):
        """Test when entity doesn't exist anywhere."""
        respx.get(
            "https://backstage.example.com/api/catalog/entities/by-name/component/default/nonexistent"
        ).mock(return_value=Response(404))

        respx.get("https://backstage.example.com/api/catalog/entities").mock(
            return_value=Response(200, json=SAMPLE_ENTITIES)
        )

        provider = BackstageDepProvider(url="https://backstage.example.com")
        deps = await provider.discover("nonexistent")

        assert deps == []


@pytest.mark.asyncio
class TestBackstageDepProviderDiscoverDownstream:
    """Tests for discover_downstream()."""

    @respx.mock
    async def test_discover_downstream(self):
        """Test discovering downstream dependencies."""
        respx.get("https://backstage.example.com/api/catalog/entities").mock(
            return_value=Response(200, json=SAMPLE_ENTITIES)
        )

        provider = BackstageDepProvider(url="https://backstage.example.com")
        deps = await provider.discover_downstream("payment-api")

        # checkout-api depends on payment-api
        source_names = [d.source_service for d in deps]
        assert "checkout-api" in source_names

    @respx.mock
    async def test_discover_downstream_none(self):
        """Test when nothing depends on the service."""
        respx.get("https://backstage.example.com/api/catalog/entities").mock(
            return_value=Response(200, json=SAMPLE_ENTITIES)
        )

        provider = BackstageDepProvider(url="https://backstage.example.com")
        deps = await provider.discover_downstream("checkout-api")

        # Nothing depends on checkout-api in our sample
        assert deps == []


@pytest.mark.asyncio
class TestBackstageDepProviderHealthCheck:
    """Tests for health_check()."""

    @respx.mock
    async def test_health_check_success(self):
        """Test successful health check."""
        respx.get("https://backstage.example.com/api/catalog/entities").mock(
            return_value=Response(200, json=[])
        )

        provider = BackstageDepProvider(url="https://backstage.example.com")
        health = await provider.health_check()

        assert health.healthy is True
        assert "Connected" in health.message

    @respx.mock
    async def test_health_check_auth_failure(self):
        """Test health check with auth failure."""
        respx.get("https://backstage.example.com/api/catalog/entities").mock(
            return_value=Response(401, json={"error": "Unauthorized"})
        )

        provider = BackstageDepProvider(url="https://backstage.example.com")
        health = await provider.health_check()

        assert health.healthy is False
        assert "401" in health.message

    @respx.mock
    async def test_health_check_connection_error(self):
        """Test health check with connection error."""
        import httpx as httpx_module

        respx.get("https://backstage.example.com/api/catalog/entities").mock(
            side_effect=httpx_module.ConnectError("Connection refused")
        )

        provider = BackstageDepProvider(url="https://backstage.example.com")
        health = await provider.health_check()

        assert health.healthy is False
        assert "Connection" in health.message


@pytest.mark.asyncio
class TestBackstageDepProviderGetAttributes:
    """Tests for get_service_attributes()."""

    @respx.mock
    async def test_get_service_attributes(self):
        """Test getting service attributes."""
        respx.get(
            "https://backstage.example.com/api/catalog/entities/by-name/component/default/payment-api"
        ).mock(return_value=Response(200, json=SAMPLE_ENTITIES[0]))

        provider = BackstageDepProvider(url="https://backstage.example.com")
        attrs = await provider.get_service_attributes("payment-api")

        assert attrs["name"] == "payment-api"
        assert attrs["namespace"] == "default"
        assert attrs["owner"] == "team-payments"
        assert attrs["type"] == "service"

    @respx.mock
    async def test_get_service_attributes_not_found(self):
        """Test getting attributes for nonexistent service."""
        respx.get(
            "https://backstage.example.com/api/catalog/entities/by-name/component/default/nonexistent"
        ).mock(return_value=Response(404))

        provider = BackstageDepProvider(url="https://backstage.example.com")
        attrs = await provider.get_service_attributes("nonexistent")

        assert attrs == {}


@pytest.mark.asyncio
class TestBackstageDepProviderErrors:
    """Tests for error handling."""

    @respx.mock
    async def test_auth_error(self):
        """Test authentication error raises exception."""
        respx.get("https://backstage.example.com/api/catalog/entities").mock(
            return_value=Response(401, json={"error": "Unauthorized"})
        )

        provider = BackstageDepProvider(url="https://backstage.example.com")

        with pytest.raises(BackstageDepProviderError) as exc_info:
            await provider.list_services()

        assert "Authentication failed" in str(exc_info.value)

    @respx.mock
    async def test_forbidden_error(self):
        """Test forbidden error raises exception."""
        respx.get("https://backstage.example.com/api/catalog/entities").mock(
            return_value=Response(403, json={"error": "Forbidden"})
        )

        provider = BackstageDepProvider(url="https://backstage.example.com")

        with pytest.raises(BackstageDepProviderError) as exc_info:
            await provider.list_services()

        assert "Authentication failed" in str(exc_info.value)


class TestBackstageDepProviderDeduplicate:
    """Tests for deduplication."""

    def test_deduplicate_keeps_highest_confidence(self):
        """Test deduplication keeps highest confidence."""
        from nthlayer.dependencies.models import DiscoveredDependency

        provider = BackstageDepProvider(url="https://backstage.example.com")

        deps = [
            DiscoveredDependency(
                source_service="a",
                target_service="b",
                provider="backstage",
                dep_type=DependencyType.SERVICE,
                confidence=0.8,
                metadata={},
            ),
            DiscoveredDependency(
                source_service="a",
                target_service="b",
                provider="backstage",
                dep_type=DependencyType.SERVICE,
                confidence=0.95,
                metadata={},
            ),
        ]

        result = provider._deduplicate(deps)

        assert len(result) == 1
        assert result[0].confidence == 0.95
