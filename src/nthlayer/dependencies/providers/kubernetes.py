"""
Kubernetes dependency provider.

Discovers service dependencies from Kubernetes resources including:
- Service-to-Service relationships (via label selectors)
- Ingress-to-Service mappings
- NetworkPolicy analysis for allowed connections
"""

from __future__ import annotations

import asyncio
import os
import re
import time
from dataclasses import dataclass, field
from functools import partial
from typing import Any

from nthlayer.dependencies.models import DependencyType, DiscoveredDependency
from nthlayer.dependencies.providers.base import BaseDepProvider, ProviderHealth

# Lazy import kubernetes to allow optional installation
_kubernetes_available: bool | None = None


def _check_kubernetes_available() -> bool:
    """Check if kubernetes package is installed."""
    global _kubernetes_available
    if _kubernetes_available is None:
        try:
            import kubernetes  # noqa: F401

            _kubernetes_available = True
        except ImportError:
            _kubernetes_available = False
    return _kubernetes_available


class KubernetesDepProviderError(RuntimeError):
    """Raised when Kubernetes dependency provider encounters an error."""


@dataclass
class KubernetesDepProvider(BaseDepProvider):
    """
    Discover dependencies from Kubernetes API.

    Configuration:
        namespace: Namespace to search (None = all namespaces)
        kubeconfig: Path to kubeconfig file (optional)
        context: Kubeconfig context to use (optional)
        timeout: API request timeout in seconds

    Environment variables:
        KUBECONFIG: Standard kubeconfig path
        NTHLAYER_K8S_NAMESPACE: Default namespace filter
        NTHLAYER_K8S_CONTEXT: Kubeconfig context
    """

    namespace: str | None = field(default_factory=lambda: os.environ.get("NTHLAYER_K8S_NAMESPACE"))
    kubeconfig: str | None = field(default_factory=lambda: os.environ.get("KUBECONFIG"))
    context: str | None = field(default_factory=lambda: os.environ.get("NTHLAYER_K8S_CONTEXT"))
    timeout: float = 30.0

    # Internal state
    _api_client: Any = field(default=None, repr=False, compare=False)
    _initialized: bool = field(default=False, repr=False, compare=False)

    @property
    def name(self) -> str:
        return "kubernetes"

    def _ensure_initialized(self) -> None:
        """Initialize Kubernetes client if not already done."""
        if self._initialized:
            return

        if not _check_kubernetes_available():
            raise KubernetesDepProviderError(
                "kubernetes package not installed. "
                "Install with: pip install nthlayer[kubernetes]"
            )

        from kubernetes import client, config

        # Try in-cluster config first, then kubeconfig
        try:
            config.load_incluster_config()
        except config.ConfigException:
            try:
                config.load_kube_config(
                    config_file=self.kubeconfig,
                    context=self.context,
                )
            except config.ConfigException as e:
                raise KubernetesDepProviderError(f"Failed to load Kubernetes config: {e}") from e

        self._api_client = client.ApiClient()
        self._initialized = True

    def _get_core_api(self) -> Any:
        """Get CoreV1Api client."""
        self._ensure_initialized()
        from kubernetes import client

        return client.CoreV1Api(self._api_client)

    def _get_networking_api(self) -> Any:
        """Get NetworkingV1Api client."""
        self._ensure_initialized()
        from kubernetes import client

        return client.NetworkingV1Api(self._api_client)

    async def _run_sync(self, func: Any, *args: Any, **kwargs: Any) -> Any:
        """Run synchronous kubernetes API call in executor."""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, partial(func, *args, **kwargs))

    async def discover(self, service: str) -> list[DiscoveredDependency]:
        """Discover dependencies for a service from Kubernetes resources."""
        deps: list[DiscoveredDependency] = []

        # Discover from multiple sources
        deps.extend(await self._discover_from_ingress(service))
        deps.extend(await self._discover_from_network_policies(service))
        deps.extend(await self._discover_from_service_env(service))

        return self._deduplicate(deps)

    async def discover_downstream(self, service: str) -> list[DiscoveredDependency]:
        """Discover services that call this service (downstream dependents)."""
        deps: list[DiscoveredDependency] = []

        # Find services that have this service as a target in their env vars
        deps.extend(await self._discover_downstream_from_env(service))

        # Find ingresses that route to this service
        deps.extend(await self._discover_downstream_from_ingress(service))

        # Find network policies that allow traffic to this service
        deps.extend(await self._discover_downstream_from_network_policies(service))

        return self._deduplicate(deps)

    async def _discover_from_ingress(self, service: str) -> list[DiscoveredDependency]:
        """Find services referenced in Ingress backends for this service."""
        deps: list[DiscoveredDependency] = []

        try:
            networking_api = self._get_networking_api()

            if self.namespace:
                ingresses = await self._run_sync(
                    networking_api.list_namespaced_ingress,
                    self.namespace,
                    timeout_seconds=int(self.timeout),
                )
            else:
                ingresses = await self._run_sync(
                    networking_api.list_ingress_for_all_namespaces,
                    timeout_seconds=int(self.timeout),
                )

            # Find ingresses that have this service as a backend
            for ingress in ingresses.items:
                ingress_name = ingress.metadata.name
                namespace = ingress.metadata.namespace

                if not ingress.spec or not ingress.spec.rules:
                    continue

                for rule in ingress.spec.rules:
                    if not rule.http or not rule.http.paths:
                        continue

                    for path in rule.http.paths:
                        backend = path.backend
                        if backend and backend.service:
                            backend_service = backend.service.name

                            # If this ingress points to our service, the ingress is downstream
                            if backend_service == service:
                                deps.append(
                                    DiscoveredDependency(
                                        source_service=f"ingress/{ingress_name}",
                                        target_service=service,
                                        provider=self.name,
                                        dep_type=DependencyType.INFRASTRUCTURE,
                                        confidence=0.95,
                                        metadata={
                                            "source": "ingress",
                                            "namespace": namespace,
                                            "host": rule.host,
                                            "path": path.path,
                                        },
                                        raw_source=ingress_name,
                                        raw_target=backend_service,
                                    )
                                )

        except Exception as e:
            # Log but continue - RBAC might restrict access
            if "Forbidden" not in str(e):
                raise KubernetesDepProviderError(f"Failed to list ingresses: {e}") from e

        return deps

    async def _discover_downstream_from_ingress(self, service: str) -> list[DiscoveredDependency]:
        """Find ingresses that route to this service."""
        # This is the same as _discover_from_ingress but returns as downstream
        return await self._discover_from_ingress(service)

    async def _discover_from_network_policies(self, service: str) -> list[DiscoveredDependency]:
        """Discover allowed connections from NetworkPolicies."""
        deps: list[DiscoveredDependency] = []

        try:
            networking_api = self._get_networking_api()

            if self.namespace:
                policies = await self._run_sync(
                    networking_api.list_namespaced_network_policy,
                    self.namespace,
                    timeout_seconds=int(self.timeout),
                )
            else:
                policies = await self._run_sync(
                    networking_api.list_network_policy_for_all_namespaces,
                    timeout_seconds=int(self.timeout),
                )

            for policy in policies.items:
                policy_name = policy.metadata.name
                namespace = policy.metadata.namespace

                # Check if this policy applies to our service (via pod selector)
                if not policy.spec or not policy.spec.pod_selector:
                    continue

                # Get the pod selector labels
                selector_labels = policy.spec.pod_selector.match_labels or {}

                # Check if selector matches service (by app label convention)
                if not self._selector_matches_service(selector_labels, service):
                    continue

                # Parse egress rules to find what this service can connect to
                if policy.spec.egress:
                    for egress in policy.spec.egress:
                        if not egress.to:
                            continue

                        for to in egress.to:
                            if to.pod_selector and to.pod_selector.match_labels:
                                target = self._extract_service_from_selector(
                                    to.pod_selector.match_labels
                                )
                                if target:
                                    deps.append(
                                        DiscoveredDependency(
                                            source_service=service,
                                            target_service=target,
                                            provider=self.name,
                                            dep_type=DependencyType.SERVICE,
                                            confidence=0.85,
                                            metadata={
                                                "source": "network_policy_egress",
                                                "policy": policy_name,
                                                "namespace": namespace,
                                            },
                                            raw_source=service,
                                            raw_target=target,
                                        )
                                    )

        except Exception as e:
            if "Forbidden" not in str(e):
                raise KubernetesDepProviderError(f"Failed to list network policies: {e}") from e

        return deps

    async def _discover_downstream_from_network_policies(
        self, service: str
    ) -> list[DiscoveredDependency]:
        """Find services allowed to connect to this service via NetworkPolicies."""
        deps: list[DiscoveredDependency] = []

        try:
            networking_api = self._get_networking_api()

            if self.namespace:
                policies = await self._run_sync(
                    networking_api.list_namespaced_network_policy,
                    self.namespace,
                    timeout_seconds=int(self.timeout),
                )
            else:
                policies = await self._run_sync(
                    networking_api.list_network_policy_for_all_namespaces,
                    timeout_seconds=int(self.timeout),
                )

            for policy in policies.items:
                policy_name = policy.metadata.name
                namespace = policy.metadata.namespace

                if not policy.spec or not policy.spec.pod_selector:
                    continue

                selector_labels = policy.spec.pod_selector.match_labels or {}

                # Check if this policy applies to our target service
                if not self._selector_matches_service(selector_labels, service):
                    continue

                # Parse ingress rules to find who can connect to this service
                if policy.spec.ingress:
                    for ingress_rule in policy.spec.ingress:
                        if not ingress_rule._from:
                            continue

                        for from_rule in ingress_rule._from:
                            if from_rule.pod_selector and from_rule.pod_selector.match_labels:
                                source = self._extract_service_from_selector(
                                    from_rule.pod_selector.match_labels
                                )
                                if source:
                                    deps.append(
                                        DiscoveredDependency(
                                            source_service=source,
                                            target_service=service,
                                            provider=self.name,
                                            dep_type=DependencyType.SERVICE,
                                            confidence=0.85,
                                            metadata={
                                                "source": "network_policy_ingress",
                                                "policy": policy_name,
                                                "namespace": namespace,
                                            },
                                            raw_source=source,
                                            raw_target=service,
                                        )
                                    )

        except Exception as e:
            if "Forbidden" not in str(e):
                raise KubernetesDepProviderError(f"Failed to list network policies: {e}") from e

        return deps

    async def _discover_from_service_env(self, service: str) -> list[DiscoveredDependency]:
        """Discover dependencies from Pod environment variables."""
        deps: list[DiscoveredDependency] = []

        try:
            core_api = self._get_core_api()

            # Find pods for this service
            label_selector = f"app={service}"

            if self.namespace:
                pods = await self._run_sync(
                    core_api.list_namespaced_pod,
                    self.namespace,
                    label_selector=label_selector,
                    timeout_seconds=int(self.timeout),
                )
            else:
                pods = await self._run_sync(
                    core_api.list_pod_for_all_namespaces,
                    label_selector=label_selector,
                    timeout_seconds=int(self.timeout),
                )

            # Also try app.kubernetes.io/name label
            if not pods.items:
                label_selector = f"app.kubernetes.io/name={service}"
                if self.namespace:
                    pods = await self._run_sync(
                        core_api.list_namespaced_pod,
                        self.namespace,
                        label_selector=label_selector,
                        timeout_seconds=int(self.timeout),
                    )
                else:
                    pods = await self._run_sync(
                        core_api.list_pod_for_all_namespaces,
                        label_selector=label_selector,
                        timeout_seconds=int(self.timeout),
                    )

            for pod in pods.items:
                namespace = pod.metadata.namespace

                if not pod.spec or not pod.spec.containers:
                    continue

                for container in pod.spec.containers:
                    if not container.env:
                        continue

                    for env_var in container.env:
                        if not env_var.value:
                            continue

                        # Look for service references in env values
                        target = self._extract_service_from_env(env_var.name, env_var.value)
                        if target and target != service:
                            dep_type = self._infer_dep_type_from_env(env_var.name)
                            deps.append(
                                DiscoveredDependency(
                                    source_service=service,
                                    target_service=target,
                                    provider=self.name,
                                    dep_type=dep_type,
                                    confidence=0.75,
                                    metadata={
                                        "source": "pod_env",
                                        "env_var": env_var.name,
                                        "namespace": namespace,
                                    },
                                    raw_source=service,
                                    raw_target=target,
                                )
                            )

        except Exception as e:
            if "Forbidden" not in str(e):
                raise KubernetesDepProviderError(f"Failed to list pods: {e}") from e

        return deps

    async def _discover_downstream_from_env(self, service: str) -> list[DiscoveredDependency]:
        """Find services that reference this service in their env vars."""
        deps: list[DiscoveredDependency] = []

        try:
            core_api = self._get_core_api()

            # List all pods (this can be expensive in large clusters)
            if self.namespace:
                pods = await self._run_sync(
                    core_api.list_namespaced_pod,
                    self.namespace,
                    timeout_seconds=int(self.timeout),
                )
            else:
                pods = await self._run_sync(
                    core_api.list_pod_for_all_namespaces,
                    timeout_seconds=int(self.timeout),
                )

            for pod in pods.items:
                namespace = pod.metadata.namespace
                labels = pod.metadata.labels or {}

                # Get source service name from labels
                source = labels.get("app") or labels.get("app.kubernetes.io/name")
                if not source or source == service:
                    continue

                if not pod.spec or not pod.spec.containers:
                    continue

                for container in pod.spec.containers:
                    if not container.env:
                        continue

                    for env_var in container.env:
                        if not env_var.value:
                            continue

                        # Check if env value references our service
                        if self._env_references_service(env_var.value, service):
                            dep_type = self._infer_dep_type_from_env(env_var.name)
                            deps.append(
                                DiscoveredDependency(
                                    source_service=source,
                                    target_service=service,
                                    provider=self.name,
                                    dep_type=dep_type,
                                    confidence=0.75,
                                    metadata={
                                        "source": "pod_env_reference",
                                        "env_var": env_var.name,
                                        "namespace": namespace,
                                    },
                                    raw_source=source,
                                    raw_target=service,
                                )
                            )
                            break  # One reference per source is enough

        except Exception as e:
            if "Forbidden" not in str(e):
                raise KubernetesDepProviderError(f"Failed to list pods: {e}") from e

        return deps

    def _selector_matches_service(self, selector_labels: dict[str, str], service: str) -> bool:
        """Check if a label selector matches a service name."""
        for label in ["app", "app.kubernetes.io/name", "name"]:
            if selector_labels.get(label) == service:
                return True
        return False

    def _extract_service_from_selector(self, labels: dict[str, str]) -> str | None:
        """Extract service name from pod selector labels."""
        for label in ["app", "app.kubernetes.io/name", "name"]:
            if label in labels:
                return labels[label]
        return None

    def _extract_service_from_env(self, name: str, value: str) -> str | None:
        """Extract service reference from environment variable."""
        # K8s service discovery pattern: SERVICE_NAME_SERVICE_HOST
        if name.endswith("_SERVICE_HOST"):
            service_name = name.replace("_SERVICE_HOST", "").lower().replace("_", "-")
            return service_name

        # URL patterns
        url_patterns = [
            r"://([a-z0-9-]+)(?:\.[a-z0-9-]+)?(?::\d+)?",  # protocol://service.namespace:port
            r"://([a-z0-9-]+):\d+",  # protocol://service:port
        ]

        for pattern in url_patterns:
            match = re.search(pattern, value.lower())
            if match:
                service_name = match.group(1)
                # Filter out common non-service values
                if service_name not in ["localhost", "127", "0"]:
                    return service_name

        return None

    def _env_references_service(self, value: str, service: str) -> bool:
        """Check if an environment variable value references a service."""
        value_lower = value.lower()
        service_lower = service.lower()

        # Check for direct service name in URL
        patterns = [
            f"://{service_lower}.",
            f"://{service_lower}:",
            f"://{service_lower}/",
            f"://{service_lower} ",
        ]

        for pattern in patterns:
            if pattern in value_lower:
                return True

        # Check K8s service discovery env var format
        service_env = service_lower.replace("-", "_")
        if f"{service_env}_service_host" in value_lower:
            return True

        return False

    def _infer_dep_type_from_env(self, env_name: str) -> DependencyType:
        """Infer dependency type from environment variable name."""
        name_lower = env_name.lower()

        if any(x in name_lower for x in ["database", "db", "postgres", "mysql", "mongo"]):
            return DependencyType.DATASTORE
        if any(x in name_lower for x in ["redis", "cache", "memcache"]):
            return DependencyType.DATASTORE
        if any(x in name_lower for x in ["kafka", "rabbitmq", "queue", "mq", "nats"]):
            return DependencyType.QUEUE
        if any(x in name_lower for x in ["api_key", "external", "third_party"]):
            return DependencyType.EXTERNAL

        return DependencyType.SERVICE

    def _deduplicate(self, deps: list[DiscoveredDependency]) -> list[DiscoveredDependency]:
        """Remove duplicate dependencies, keeping highest confidence."""
        seen: dict[str, DiscoveredDependency] = {}

        for dep in deps:
            key = f"{dep.source_service}:{dep.target_service}:{dep.dep_type.value}"

            if key not in seen or dep.confidence > seen[key].confidence:
                seen[key] = dep

        return list(seen.values())

    async def list_services(self) -> list[str]:
        """List all Kubernetes services."""
        services: set[str] = set()

        try:
            core_api = self._get_core_api()

            if self.namespace:
                svc_list = await self._run_sync(
                    core_api.list_namespaced_service,
                    self.namespace,
                    timeout_seconds=int(self.timeout),
                )
            else:
                svc_list = await self._run_sync(
                    core_api.list_service_for_all_namespaces,
                    timeout_seconds=int(self.timeout),
                )

            for svc in svc_list.items:
                # Skip kubernetes system services
                if svc.metadata.namespace == "kube-system":
                    continue
                services.add(svc.metadata.name)

        except Exception as e:
            raise KubernetesDepProviderError(f"Failed to list services: {e}") from e

        return sorted(services)

    async def health_check(self) -> ProviderHealth:
        """Check Kubernetes API connectivity."""
        start = time.time()

        try:
            self._ensure_initialized()
            core_api = self._get_core_api()

            # Try to get API server version
            await self._run_sync(core_api.get_api_versions)
            latency = (time.time() - start) * 1000

            return ProviderHealth(
                healthy=True,
                message="Connected to Kubernetes API",
                latency_ms=latency,
            )

        except KubernetesDepProviderError as e:
            return ProviderHealth(
                healthy=False,
                message=str(e),
            )
        except Exception as e:
            return ProviderHealth(
                healthy=False,
                message=f"Kubernetes connection failed: {e}",
            )

    async def get_service_attributes(self, service: str) -> dict:
        """Get service attributes from Kubernetes labels and annotations."""
        attributes: dict[str, Any] = {}

        try:
            core_api = self._get_core_api()

            if self.namespace:
                svc_list = await self._run_sync(
                    core_api.list_namespaced_service,
                    self.namespace,
                    field_selector=f"metadata.name={service}",
                    timeout_seconds=int(self.timeout),
                )
            else:
                svc_list = await self._run_sync(
                    core_api.list_service_for_all_namespaces,
                    field_selector=f"metadata.name={service}",
                    timeout_seconds=int(self.timeout),
                )

            if svc_list.items:
                svc = svc_list.items[0]
                labels = svc.metadata.labels or {}
                annotations = svc.metadata.annotations or {}

                # Extract useful attributes
                for key in ["team", "owner", "tier", "environment", "version"]:
                    for source in [labels, annotations]:
                        for prefix in ["", "app.kubernetes.io/", "nthlayer.io/"]:
                            full_key = f"{prefix}{key}"
                            if full_key in source:
                                attributes[key] = source[full_key]
                                break

                attributes["namespace"] = svc.metadata.namespace

        except Exception:
            pass

        return attributes
