"""Tests for dependency discovery module."""

import pytest
from nthlayer.dependencies import (
    BlastRadiusResult,
    DependencyDirection,
    DependencyGraph,
    DependencyType,
    DiscoveredDependency,
    ResolvedDependency,
    create_demo_discovery,
)
from nthlayer.identity import ServiceIdentity


class TestDependencyType:
    """Tests for DependencyType enum."""

    def test_all_types(self):
        """Test all dependency types are defined."""
        assert DependencyType.SERVICE.value == "service"
        assert DependencyType.DATASTORE.value == "datastore"
        assert DependencyType.QUEUE.value == "queue"
        assert DependencyType.EXTERNAL.value == "external"
        assert DependencyType.INFRASTRUCTURE.value == "infra"


class TestDependencyDirection:
    """Tests for DependencyDirection enum."""

    def test_directions(self):
        """Test dependency directions."""
        assert DependencyDirection.UPSTREAM.value == "upstream"
        assert DependencyDirection.DOWNSTREAM.value == "downstream"


class TestDiscoveredDependency:
    """Tests for DiscoveredDependency model."""

    def test_basic_dependency(self):
        """Test creating basic discovered dependency."""
        dep = DiscoveredDependency(
            source_service="payment-api",
            target_service="user-service",
            provider="prometheus",
        )

        assert dep.source_service == "payment-api"
        assert dep.target_service == "user-service"
        assert dep.provider == "prometheus"
        assert dep.dep_type == DependencyType.SERVICE
        assert dep.confidence == 0.5

    def test_dependency_with_type(self):
        """Test dependency with specific type."""
        dep = DiscoveredDependency(
            source_service="payment-api",
            target_service="postgresql",
            provider="prometheus",
            dep_type=DependencyType.DATASTORE,
            confidence=0.9,
        )

        assert dep.dep_type == DependencyType.DATASTORE
        assert dep.confidence == 0.9

    def test_to_dict(self):
        """Test serialization to dict."""
        dep = DiscoveredDependency(
            source_service="payment-api",
            target_service="user-service",
            provider="prometheus",
            metadata={"query": "http_client_requests_total"},
        )

        data = dep.to_dict()
        assert data["source_service"] == "payment-api"
        assert data["target_service"] == "user-service"
        assert data["provider"] == "prometheus"
        assert data["metadata"]["query"] == "http_client_requests_total"


class TestResolvedDependency:
    """Tests for ResolvedDependency model."""

    @pytest.fixture
    def payment_identity(self):
        """Create payment service identity."""
        return ServiceIdentity(canonical_name="payment-api")

    @pytest.fixture
    def user_identity(self):
        """Create user service identity."""
        return ServiceIdentity(canonical_name="user-service")

    def test_basic_resolved(self, payment_identity, user_identity):
        """Test creating resolved dependency."""
        dep = ResolvedDependency(
            source=payment_identity,
            target=user_identity,
            dep_type=DependencyType.SERVICE,
            confidence=0.95,
            providers=["prometheus"],
        )

        assert dep.source.canonical_name == "payment-api"
        assert dep.target.canonical_name == "user-service"
        assert dep.confidence == 0.95
        assert "prometheus" in dep.providers

    def test_to_dict(self, payment_identity, user_identity):
        """Test serialization to dict."""
        dep = ResolvedDependency(
            source=payment_identity,
            target=user_identity,
            dep_type=DependencyType.SERVICE,
            confidence=0.95,
            providers=["prometheus", "backstage"],
        )

        data = dep.to_dict()
        assert data["source"] == "payment-api"
        assert data["target"] == "user-service"
        assert data["dep_type"] == "service"
        assert data["confidence"] == 0.95
        assert len(data["providers"]) == 2


class TestDependencyGraph:
    """Tests for DependencyGraph model."""

    @pytest.fixture
    def sample_graph(self):
        """Create a sample dependency graph."""
        graph = DependencyGraph()

        # Create identities
        payment = ServiceIdentity(canonical_name="payment-api")
        user = ServiceIdentity(canonical_name="user-service")
        checkout = ServiceIdentity(canonical_name="checkout-api")
        postgres = ServiceIdentity(canonical_name="postgresql")

        # Add services
        graph.add_service(payment)
        graph.add_service(user)
        graph.add_service(checkout)
        graph.add_service(postgres)

        # payment-api calls user-service
        graph.add_edge(
            ResolvedDependency(
                source=payment,
                target=user,
                dep_type=DependencyType.SERVICE,
                confidence=0.95,
                providers=["prometheus"],
            )
        )

        # payment-api calls postgresql
        graph.add_edge(
            ResolvedDependency(
                source=payment,
                target=postgres,
                dep_type=DependencyType.DATASTORE,
                confidence=0.9,
                providers=["prometheus"],
            )
        )

        # checkout-api calls payment-api
        graph.add_edge(
            ResolvedDependency(
                source=checkout,
                target=payment,
                dep_type=DependencyType.SERVICE,
                confidence=0.95,
                providers=["prometheus"],
            )
        )

        return graph

    def test_add_service(self, sample_graph):
        """Test adding services to graph."""
        assert "payment-api" in sample_graph.services
        assert "user-service" in sample_graph.services
        assert sample_graph.get_service_count() == 4

    def test_add_edge(self, sample_graph):
        """Test adding edges to graph."""
        assert sample_graph.get_edge_count() == 3

    def test_get_upstream(self, sample_graph):
        """Test getting upstream dependencies."""
        upstream = sample_graph.get_upstream("payment-api")
        assert len(upstream) == 2  # user-service and postgresql

        targets = [dep.target.canonical_name for dep in upstream]
        assert "user-service" in targets
        assert "postgresql" in targets

    def test_get_downstream(self, sample_graph):
        """Test getting downstream dependencies."""
        downstream = sample_graph.get_downstream("payment-api")
        assert len(downstream) == 1  # checkout-api

        sources = [dep.source.canonical_name for dep in downstream]
        assert "checkout-api" in sources

    def test_get_transitive_upstream(self, sample_graph):
        """Test getting transitive upstream dependencies."""
        # checkout-api -> payment-api -> user-service, postgresql
        transitive = sample_graph.get_transitive_upstream("checkout-api")

        # Should find payment-api at depth 1, and its deps at depth 2
        depths = {dep.target.canonical_name: depth for dep, depth in transitive}
        assert "payment-api" in depths
        assert depths["payment-api"] == 1

    def test_get_transitive_downstream(self, sample_graph):
        """Test getting transitive downstream dependencies."""
        # user-service is called by payment-api, which is called by checkout-api
        transitive = sample_graph.get_transitive_downstream("user-service")

        sources = {dep.source.canonical_name for dep, _ in transitive}
        assert "payment-api" in sources

    def test_deduplication(self, sample_graph):
        """Test that duplicate edges are merged."""
        payment = sample_graph.services["payment-api"]
        user = sample_graph.services["user-service"]

        # Add duplicate edge with different provider
        sample_graph.add_edge(
            ResolvedDependency(
                source=payment,
                target=user,
                dep_type=DependencyType.SERVICE,
                confidence=0.85,
                providers=["backstage"],
            )
        )

        # Should still have same number of edges
        upstream = sample_graph.get_upstream("payment-api")
        user_deps = [d for d in upstream if d.target.canonical_name == "user-service"]
        assert len(user_deps) == 1

        # But should have merged providers
        assert "prometheus" in user_deps[0].providers
        assert "backstage" in user_deps[0].providers

    def test_to_dict(self, sample_graph):
        """Test serialization to dict."""
        data = sample_graph.to_dict()

        assert "services" in data
        assert "edges" in data
        assert "built_at" in data
        assert data["stats"]["service_count"] == 4
        assert data["stats"]["edge_count"] == 3


class TestBlastRadiusResult:
    """Tests for BlastRadiusResult model."""

    def test_basic_result(self):
        """Test creating blast radius result."""
        result = BlastRadiusResult(
            service="payment-api",
            tier="critical",
            risk_level="high",
            total_services_affected=5,
            critical_services_affected=2,
        )

        assert result.service == "payment-api"
        assert result.tier == "critical"
        assert result.risk_level == "high"
        assert result.total_services_affected == 5
        assert result.critical_services_affected == 2

    def test_to_dict(self):
        """Test serialization to dict."""
        result = BlastRadiusResult(
            service="payment-api",
            risk_level="medium",
            recommendation="Deploy during low-traffic window",
        )

        data = result.to_dict()
        assert data["service"] == "payment-api"
        assert data["risk_level"] == "medium"
        assert data["recommendation"] == "Deploy during low-traffic window"


class TestDemoDiscovery:
    """Tests for demo discovery helper."""

    def test_create_demo_discovery(self):
        """Test creating demo discovery instance."""
        discovery, graph = create_demo_discovery()

        # Check graph has expected services
        assert "payment-api" in graph.services
        assert "checkout-api" in graph.services
        assert "user-service" in graph.services
        assert "postgresql" in graph.services
        assert "redis" in graph.services

        # Check edges exist
        assert graph.get_edge_count() > 0

        # Check discovery has tier mappings
        assert "payment-api" in discovery.tier_mapping
        assert discovery.tier_mapping["payment-api"] == "critical"

    def test_demo_blast_radius(self):
        """Test blast radius calculation with demo data."""
        discovery, graph = create_demo_discovery()

        result = discovery.calculate_blast_radius(
            service="payment-api",
            graph=graph,
            max_depth=3,
        )

        # payment-api should have downstream dependents
        assert result.service == "payment-api"
        assert len(result.direct_downstream) > 0
        assert result.total_services_affected > 0

    def test_demo_upstream_dependencies(self):
        """Test getting upstream dependencies from demo graph."""
        _, graph = create_demo_discovery()

        upstream = graph.get_upstream("payment-api")

        # payment-api should call user-service, postgresql, redis
        targets = [dep.target.canonical_name for dep in upstream]
        assert "user-service" in targets
        assert "postgresql" in targets
        assert "redis" in targets

    def test_demo_downstream_dependencies(self):
        """Test getting downstream dependencies from demo graph."""
        _, graph = create_demo_discovery()

        downstream = graph.get_downstream("payment-api")

        # checkout-api and mobile-gateway call payment-api
        sources = [dep.source.canonical_name for dep in downstream]
        assert "checkout-api" in sources
        assert "mobile-gateway" in sources
