"""Tests for Kubernetes dependency provider."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from nthlayer.dependencies.models import DependencyType


class TestKubernetesDepProviderAvailability:
    """Tests for kubernetes package availability."""

    def test_check_kubernetes_available(self):
        """Test kubernetes availability check."""
        from nthlayer.dependencies.providers.kubernetes import _check_kubernetes_available

        # Should return True since kubernetes is installed in dev
        assert _check_kubernetes_available() is True


class TestKubernetesDepProviderInit:
    """Tests for provider initialization."""

    def test_default_config(self):
        """Test provider with default configuration."""
        from nthlayer.dependencies.providers.kubernetes import KubernetesDepProvider

        provider = KubernetesDepProvider()

        assert provider.name == "kubernetes"
        assert provider.namespace is None
        assert provider.timeout == 30.0

    def test_custom_namespace(self):
        """Test provider with custom namespace."""
        from nthlayer.dependencies.providers.kubernetes import KubernetesDepProvider

        provider = KubernetesDepProvider(namespace="production")

        assert provider.namespace == "production"

    def test_env_var_config(self, monkeypatch):
        """Test provider reads from environment variables."""
        monkeypatch.setenv("NTHLAYER_K8S_NAMESPACE", "test-ns")
        monkeypatch.setenv("KUBECONFIG", "/path/to/kubeconfig")
        monkeypatch.setenv("NTHLAYER_K8S_CONTEXT", "test-context")

        from nthlayer.dependencies.providers.kubernetes import KubernetesDepProvider

        provider = KubernetesDepProvider()

        assert provider.namespace == "test-ns"
        assert provider.kubeconfig == "/path/to/kubeconfig"
        assert provider.context == "test-context"


class TestKubernetesDepProviderListServices:
    """Tests for list_services method."""

    @pytest.fixture
    def mock_k8s_services(self):
        """Create mock Kubernetes service list."""
        mock_svc1 = MagicMock()
        mock_svc1.metadata.name = "payment-api"
        mock_svc1.metadata.namespace = "default"

        mock_svc2 = MagicMock()
        mock_svc2.metadata.name = "user-service"
        mock_svc2.metadata.namespace = "default"

        mock_svc3 = MagicMock()
        mock_svc3.metadata.name = "kube-dns"
        mock_svc3.metadata.namespace = "kube-system"  # Should be filtered

        mock_list = MagicMock()
        mock_list.items = [mock_svc1, mock_svc2, mock_svc3]

        return mock_list

    @pytest.mark.asyncio
    async def test_list_services_all_namespaces(self, mock_k8s_services):
        """Test listing services across all namespaces."""
        from nthlayer.dependencies.providers.kubernetes import KubernetesDepProvider

        provider = KubernetesDepProvider()

        with patch.object(provider, "_ensure_initialized"):
            with patch.object(provider, "_get_core_api") as mock_api:
                mock_core = MagicMock()
                mock_core.list_service_for_all_namespaces.return_value = mock_k8s_services
                mock_api.return_value = mock_core

                with patch.object(provider, "_run_sync", new_callable=AsyncMock) as mock_run:
                    mock_run.return_value = mock_k8s_services

                    services = await provider.list_services()

        # Should exclude kube-system services
        assert "payment-api" in services
        assert "user-service" in services
        assert "kube-dns" not in services

    @pytest.mark.asyncio
    async def test_list_services_single_namespace(self, mock_k8s_services):
        """Test listing services in a single namespace."""
        from nthlayer.dependencies.providers.kubernetes import KubernetesDepProvider

        provider = KubernetesDepProvider(namespace="default")

        with patch.object(provider, "_ensure_initialized"):
            with patch.object(provider, "_get_core_api") as mock_api:
                mock_core = MagicMock()
                mock_core.list_namespaced_service.return_value = mock_k8s_services
                mock_api.return_value = mock_core

                with patch.object(provider, "_run_sync", new_callable=AsyncMock) as mock_run:
                    mock_run.return_value = mock_k8s_services

                    services = await provider.list_services()

        assert len(services) >= 2


class TestKubernetesDepProviderDiscoverIngress:
    """Tests for ingress-based dependency discovery."""

    @pytest.fixture
    def mock_ingress_list(self):
        """Create mock ingress with service backends."""
        # Create ingress that routes to payment-api
        mock_backend = MagicMock()
        mock_backend.service.name = "payment-api"

        mock_path = MagicMock()
        mock_path.backend = mock_backend
        mock_path.path = "/api/payments"

        mock_rule = MagicMock()
        mock_rule.host = "api.example.com"
        mock_rule.http.paths = [mock_path]

        mock_ingress = MagicMock()
        mock_ingress.metadata.name = "payment-ingress"
        mock_ingress.metadata.namespace = "default"
        mock_ingress.spec.rules = [mock_rule]

        mock_list = MagicMock()
        mock_list.items = [mock_ingress]

        return mock_list

    @pytest.mark.asyncio
    async def test_discover_from_ingress(self, mock_ingress_list):
        """Test discovering dependencies from ingress resources."""
        from nthlayer.dependencies.providers.kubernetes import KubernetesDepProvider

        provider = KubernetesDepProvider()

        with patch.object(provider, "_ensure_initialized"):
            with patch.object(provider, "_get_networking_api") as mock_api:
                mock_net = MagicMock()
                mock_api.return_value = mock_net

                with patch.object(provider, "_run_sync", new_callable=AsyncMock) as mock_run:
                    mock_run.return_value = mock_ingress_list

                    deps = await provider._discover_from_ingress("payment-api")

        # Should find ingress pointing to payment-api
        assert len(deps) == 1
        assert deps[0].source_service == "ingress/payment-ingress"
        assert deps[0].target_service == "payment-api"
        assert deps[0].confidence == 0.95
        assert deps[0].dep_type == DependencyType.INFRASTRUCTURE


class TestKubernetesDepProviderDiscoverNetworkPolicy:
    """Tests for NetworkPolicy-based dependency discovery."""

    @pytest.fixture
    def mock_network_policy_list(self):
        """Create mock network policy with egress rules."""
        # Create policy that applies to payment-api and allows egress to redis
        mock_to_selector = MagicMock()
        mock_to_selector.pod_selector.match_labels = {"app": "redis"}

        mock_to = MagicMock()
        mock_to.pod_selector = mock_to_selector.pod_selector

        mock_egress = MagicMock()
        mock_egress.to = [mock_to]

        mock_policy = MagicMock()
        mock_policy.metadata.name = "payment-policy"
        mock_policy.metadata.namespace = "default"
        mock_policy.spec.pod_selector.match_labels = {"app": "payment-api"}
        mock_policy.spec.egress = [mock_egress]
        mock_policy.spec.ingress = None

        mock_list = MagicMock()
        mock_list.items = [mock_policy]

        return mock_list

    @pytest.mark.asyncio
    async def test_discover_from_network_policy(self, mock_network_policy_list):
        """Test discovering dependencies from network policies."""
        from nthlayer.dependencies.providers.kubernetes import KubernetesDepProvider

        provider = KubernetesDepProvider()

        with patch.object(provider, "_ensure_initialized"):
            with patch.object(provider, "_get_networking_api") as mock_api:
                mock_net = MagicMock()
                mock_api.return_value = mock_net

                with patch.object(provider, "_run_sync", new_callable=AsyncMock) as mock_run:
                    mock_run.return_value = mock_network_policy_list

                    deps = await provider._discover_from_network_policies("payment-api")

        # Should find egress to redis
        assert len(deps) == 1
        assert deps[0].source_service == "payment-api"
        assert deps[0].target_service == "redis"
        assert deps[0].confidence == 0.85
        assert deps[0].dep_type == DependencyType.SERVICE


class TestKubernetesDepProviderDiscoverEnv:
    """Tests for Pod env var-based dependency discovery."""

    @pytest.fixture
    def mock_pod_list(self):
        """Create mock pod with env vars referencing services."""
        # Create env vars
        mock_env_db = MagicMock()
        mock_env_db.name = "DATABASE_URL"
        mock_env_db.value = "postgresql://postgres-svc:5432/db"

        mock_env_redis = MagicMock()
        mock_env_redis.name = "REDIS_HOST"
        mock_env_redis.value = "redis-svc"

        mock_env_k8s = MagicMock()
        mock_env_k8s.name = "USER_SERVICE_SERVICE_HOST"
        mock_env_k8s.value = "10.0.0.1"

        mock_container = MagicMock()
        mock_container.env = [mock_env_db, mock_env_redis, mock_env_k8s]

        mock_pod = MagicMock()
        mock_pod.metadata.namespace = "default"
        mock_pod.metadata.labels = {"app": "payment-api"}
        mock_pod.spec.containers = [mock_container]

        mock_list = MagicMock()
        mock_list.items = [mock_pod]

        return mock_list

    @pytest.mark.asyncio
    async def test_discover_from_env(self, mock_pod_list):
        """Test discovering dependencies from pod environment variables."""
        from nthlayer.dependencies.providers.kubernetes import KubernetesDepProvider

        provider = KubernetesDepProvider()

        with patch.object(provider, "_ensure_initialized"):
            with patch.object(provider, "_get_core_api") as mock_api:
                mock_core = MagicMock()
                mock_api.return_value = mock_core

                with patch.object(provider, "_run_sync", new_callable=AsyncMock) as mock_run:
                    mock_run.return_value = mock_pod_list

                    deps = await provider._discover_from_service_env("payment-api")

        # Should find postgres, redis, user-service from env vars
        targets = [d.target_service for d in deps]
        assert "postgres-svc" in targets or any("postgres" in t for t in targets)


class TestKubernetesDepProviderHealthCheck:
    """Tests for health check functionality."""

    @pytest.mark.asyncio
    async def test_health_check_success(self):
        """Test successful health check."""
        from nthlayer.dependencies.providers.kubernetes import KubernetesDepProvider

        provider = KubernetesDepProvider()

        with patch.object(provider, "_ensure_initialized"):
            with patch.object(provider, "_get_core_api") as mock_api:
                mock_core = MagicMock()
                mock_core.get_api_versions.return_value = MagicMock()
                mock_api.return_value = mock_core

                with patch.object(provider, "_run_sync", new_callable=AsyncMock) as mock_run:
                    mock_run.return_value = MagicMock()

                    health = await provider.health_check()

        assert health.healthy is True
        assert "Kubernetes" in health.message

    @pytest.mark.asyncio
    async def test_health_check_failure(self):
        """Test health check when connection fails."""
        from nthlayer.dependencies.providers.kubernetes import (
            KubernetesDepProvider,
            KubernetesDepProviderError,
        )

        provider = KubernetesDepProvider()

        with patch.object(
            provider,
            "_ensure_initialized",
            side_effect=KubernetesDepProviderError("Config not found"),
        ):
            health = await provider.health_check()

        assert health.healthy is False
        assert "Config not found" in health.message


class TestKubernetesDepProviderGetAttributes:
    """Tests for get_service_attributes method."""

    @pytest.fixture
    def mock_service_with_labels(self):
        """Create mock service with labels and annotations."""
        mock_svc = MagicMock()
        mock_svc.metadata.name = "payment-api"
        mock_svc.metadata.namespace = "production"
        mock_svc.metadata.labels = {
            "app": "payment-api",
            "app.kubernetes.io/version": "1.2.3",
            "team": "payments",
            "tier": "critical",
        }
        mock_svc.metadata.annotations = {
            "owner": "payments-team@example.com",
        }

        mock_list = MagicMock()
        mock_list.items = [mock_svc]

        return mock_list

    @pytest.mark.asyncio
    async def test_get_service_attributes(self, mock_service_with_labels):
        """Test getting service attributes from labels."""
        from nthlayer.dependencies.providers.kubernetes import KubernetesDepProvider

        provider = KubernetesDepProvider()

        with patch.object(provider, "_ensure_initialized"):
            with patch.object(provider, "_get_core_api") as mock_api:
                mock_core = MagicMock()
                mock_api.return_value = mock_core

                with patch.object(provider, "_run_sync", new_callable=AsyncMock) as mock_run:
                    mock_run.return_value = mock_service_with_labels

                    attrs = await provider.get_service_attributes("payment-api")

        assert attrs.get("team") == "payments"
        assert attrs.get("tier") == "critical"
        assert attrs.get("namespace") == "production"


class TestKubernetesDepProviderHelpers:
    """Tests for helper methods."""

    def test_selector_matches_service(self):
        """Test label selector matching."""
        from nthlayer.dependencies.providers.kubernetes import KubernetesDepProvider

        provider = KubernetesDepProvider()

        # Should match app label
        assert provider._selector_matches_service({"app": "payment-api"}, "payment-api")

        # Should match app.kubernetes.io/name label
        assert provider._selector_matches_service(
            {"app.kubernetes.io/name": "payment-api"}, "payment-api"
        )

        # Should not match different service
        assert not provider._selector_matches_service({"app": "other-service"}, "payment-api")

    def test_extract_service_from_selector(self):
        """Test extracting service name from selector labels."""
        from nthlayer.dependencies.providers.kubernetes import KubernetesDepProvider

        provider = KubernetesDepProvider()

        assert provider._extract_service_from_selector({"app": "redis"}) == "redis"
        assert (
            provider._extract_service_from_selector({"app.kubernetes.io/name": "postgres"})
            == "postgres"
        )
        assert provider._extract_service_from_selector({"other": "label"}) is None

    def test_extract_service_from_env(self):
        """Test extracting service name from environment variable."""
        from nthlayer.dependencies.providers.kubernetes import KubernetesDepProvider

        provider = KubernetesDepProvider()

        # K8s service discovery env var
        assert (
            provider._extract_service_from_env("USER_SERVICE_SERVICE_HOST", "10.0.0.1")
            == "user-service"
        )

        # URL pattern
        assert (
            provider._extract_service_from_env("DATABASE_URL", "postgresql://postgres-svc:5432/db")
            == "postgres-svc"
        )

        # Should not extract localhost
        assert provider._extract_service_from_env("URL", "http://localhost:8080") is None

    def test_infer_dep_type_from_env(self):
        """Test inferring dependency type from env var name."""
        from nthlayer.dependencies.providers.kubernetes import KubernetesDepProvider

        provider = KubernetesDepProvider()

        assert provider._infer_dep_type_from_env("DATABASE_URL") == DependencyType.DATASTORE
        assert provider._infer_dep_type_from_env("POSTGRES_HOST") == DependencyType.DATASTORE
        assert provider._infer_dep_type_from_env("REDIS_URL") == DependencyType.DATASTORE
        assert provider._infer_dep_type_from_env("KAFKA_BROKERS") == DependencyType.QUEUE
        assert provider._infer_dep_type_from_env("EXTERNAL_API_KEY") == DependencyType.EXTERNAL
        assert provider._infer_dep_type_from_env("USER_SERVICE_URL") == DependencyType.SERVICE

    def test_deduplicate(self):
        """Test deduplication of discovered dependencies."""
        from nthlayer.dependencies.models import DiscoveredDependency
        from nthlayer.dependencies.providers.kubernetes import KubernetesDepProvider

        provider = KubernetesDepProvider()

        deps = [
            DiscoveredDependency(
                source_service="payment-api",
                target_service="redis",
                provider="kubernetes",
                confidence=0.75,
            ),
            DiscoveredDependency(
                source_service="payment-api",
                target_service="redis",
                provider="kubernetes",
                confidence=0.85,  # Higher confidence
            ),
            DiscoveredDependency(
                source_service="payment-api",
                target_service="postgres",
                provider="kubernetes",
                confidence=0.9,
            ),
        ]

        deduped = provider._deduplicate(deps)

        assert len(deduped) == 2

        redis_dep = [d for d in deduped if d.target_service == "redis"][0]
        assert redis_dep.confidence == 0.85  # Kept higher confidence


class TestKubernetesDepProviderIntegration:
    """Integration tests for the full discover method."""

    @pytest.mark.asyncio
    async def test_discover_combines_sources(self):
        """Test that discover combines results from multiple sources."""
        from nthlayer.dependencies.models import DiscoveredDependency
        from nthlayer.dependencies.providers.kubernetes import KubernetesDepProvider

        provider = KubernetesDepProvider()

        # Mock all discovery methods
        with patch.object(
            provider,
            "_discover_from_ingress",
            new_callable=AsyncMock,
            return_value=[
                DiscoveredDependency(
                    source_service="ingress/api",
                    target_service="payment-api",
                    provider="kubernetes",
                    dep_type=DependencyType.INFRASTRUCTURE,
                    confidence=0.95,
                )
            ],
        ):
            with patch.object(
                provider,
                "_discover_from_network_policies",
                new_callable=AsyncMock,
                return_value=[
                    DiscoveredDependency(
                        source_service="payment-api",
                        target_service="redis",
                        provider="kubernetes",
                        confidence=0.85,
                    )
                ],
            ):
                with patch.object(
                    provider,
                    "_discover_from_service_env",
                    new_callable=AsyncMock,
                    return_value=[
                        DiscoveredDependency(
                            source_service="payment-api",
                            target_service="postgres",
                            provider="kubernetes",
                            dep_type=DependencyType.DATASTORE,
                            confidence=0.75,
                        )
                    ],
                ):
                    deps = await provider.discover("payment-api")

        # Should have combined results from all sources
        assert len(deps) >= 2
        targets = [d.target_service for d in deps]
        assert "redis" in targets
        assert "postgres" in targets
