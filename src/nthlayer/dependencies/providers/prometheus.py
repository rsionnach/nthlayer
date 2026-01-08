"""
Prometheus dependency provider.

Discovers service dependencies from Prometheus metrics including:
- HTTP client/server relationships
- gRPC service calls
- Database connections
- Message queue consumers/producers
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

import httpx

from nthlayer.dependencies.models import DependencyType, DiscoveredDependency
from nthlayer.dependencies.providers.base import BaseDepProvider, ProviderHealth


class PrometheusDepProviderError(RuntimeError):
    """Raised when Prometheus dependency provider encounters an error."""


# Metric patterns for dependency discovery
# Each pattern specifies: metric name pattern, source label, target label, dependency type
DEPENDENCY_PATTERNS = [
    # HTTP client metrics (outbound calls)
    {
        "name": "http_client",
        "queries": [
            'count by (service, target_service) (http_client_requests_total{service=~".+"})',
            'count by (job, target) (http_client_request_duration_seconds_count{job=~".+"})',
        ],
        "source_labels": ["service", "job"],
        "target_labels": ["target_service", "target"],
        "dep_type": DependencyType.SERVICE,
        "confidence": 0.9,
    },
    # gRPC client metrics
    {
        "name": "grpc_client",
        "queries": [
            'count by (service, grpc_service) (grpc_client_handled_total{service=~".+"})',
            'count by (job, grpc_method) (grpc_client_started_total{job=~".+"})',
        ],
        "source_labels": ["service", "job"],
        "target_labels": ["grpc_service", "grpc_method"],
        "dep_type": DependencyType.SERVICE,
        "confidence": 0.9,
    },
    # Database connections
    {
        "name": "database",
        "queries": [
            'count by (service, database) (db_client_connections{service=~".+"})',
            'count by (job, db_name) (sql_client_queries_total{job=~".+"})',
            'count by (service, addr) (pg_stat_activity_count{service=~".+"})',
        ],
        "source_labels": ["service", "job"],
        "target_labels": ["database", "db_name", "addr"],
        "dep_type": DependencyType.DATASTORE,
        "confidence": 0.85,
    },
    # Redis connections
    {
        "name": "redis",
        "queries": [
            'count by (service, redis_addr) (redis_client_commands_total{service=~".+"})',
            'count by (job, addr) (redis_commands_total{job=~".+"})',
        ],
        "source_labels": ["service", "job"],
        "target_labels": ["redis_addr", "addr"],
        "dep_type": DependencyType.DATASTORE,
        "confidence": 0.85,
    },
    # Kafka consumers
    {
        "name": "kafka",
        "queries": [
            'count by (service, topic) (kafka_consumer_records_consumed_total{service=~".+"})',
            'count by (consumergroup, topic) (kafka_consumergroup_lag{consumergroup=~".+"})',
        ],
        "source_labels": ["service", "consumergroup"],
        "target_labels": ["topic"],
        "dep_type": DependencyType.QUEUE,
        "confidence": 0.85,
    },
    # RabbitMQ consumers
    {
        "name": "rabbitmq",
        "queries": [
            'count by (service, queue) (rabbitmq_consumer_messages_total{service=~".+"})',
        ],
        "source_labels": ["service"],
        "target_labels": ["queue"],
        "dep_type": DependencyType.QUEUE,
        "confidence": 0.85,
    },
]


@dataclass
class PrometheusDepProvider(BaseDepProvider):
    """
    Discover dependencies from Prometheus metrics.

    Configuration:
        url: Prometheus server URL
        username: Optional basic auth username
        password: Optional basic auth password
        timeout: Request timeout in seconds

    Environment variables:
        NTHLAYER_PROMETHEUS_URL: Prometheus URL
        NTHLAYER_METRICS_USER: Basic auth username
        NTHLAYER_METRICS_PASSWORD: Basic auth password
    """

    url: str
    username: str | None = None
    password: str | None = None
    timeout: float = 30.0

    # Optional: custom patterns
    custom_patterns: list[dict[str, Any]] = field(default_factory=list)

    @property
    def name(self) -> str:
        return "prometheus"

    def _get_auth(self) -> tuple[str, str] | None:
        """Get basic auth tuple if credentials are set."""
        if self.username and self.password:
            return (self.username, self.password)
        return None

    async def _query(self, promql: str) -> list[dict[str, Any]]:
        """Execute a PromQL instant query."""
        auth = self._get_auth()

        async with httpx.AsyncClient(auth=auth, timeout=self.timeout) as client:
            response = await client.get(
                f"{self.url.rstrip('/')}/api/v1/query",
                params={"query": promql},
            )
            response.raise_for_status()
            result = response.json()

        if result.get("status") != "success":
            raise PrometheusDepProviderError(
                f"Prometheus query failed: {result.get('error', 'Unknown')}"
            )

        return result.get("data", {}).get("result", [])

    async def discover(self, service: str) -> list[DiscoveredDependency]:
        """Discover dependencies for a service from Prometheus metrics."""
        deps: list[DiscoveredDependency] = []
        patterns = DEPENDENCY_PATTERNS + self.custom_patterns

        for pattern in patterns:
            for query in pattern.get("queries", []):
                try:
                    # Modify query to filter by service
                    filtered_query = self._add_service_filter(
                        query, service, pattern["source_labels"]
                    )
                    results = await self._query(filtered_query)

                    for result in results:
                        metric = result.get("metric", {})

                        # Extract source and target from labels
                        source = self._extract_label(metric, pattern["source_labels"])
                        target = self._extract_label(metric, pattern["target_labels"])

                        if source and target:
                            deps.append(
                                DiscoveredDependency(
                                    source_service=source,
                                    target_service=target,
                                    provider=self.name,
                                    dep_type=pattern["dep_type"],
                                    confidence=pattern["confidence"],
                                    metadata={
                                        "pattern": pattern["name"],
                                        "query": filtered_query,
                                        "labels": metric,
                                    },
                                    raw_source=source,
                                    raw_target=target,
                                )
                            )
                except Exception:
                    # Continue with other patterns on error
                    continue

        # Deduplicate dependencies
        return self._deduplicate(deps)

    async def discover_downstream(self, service: str) -> list[DiscoveredDependency]:
        """Discover services that call this service (downstream dependents)."""
        deps: list[DiscoveredDependency] = []
        patterns = DEPENDENCY_PATTERNS + self.custom_patterns

        for pattern in patterns:
            for query in pattern.get("queries", []):
                try:
                    # Modify query to filter by target service
                    filtered_query = self._add_target_filter(
                        query, service, pattern["target_labels"]
                    )
                    results = await self._query(filtered_query)

                    for result in results:
                        metric = result.get("metric", {})

                        source = self._extract_label(metric, pattern["source_labels"])
                        target = self._extract_label(metric, pattern["target_labels"])

                        if source and target:
                            deps.append(
                                DiscoveredDependency(
                                    source_service=source,
                                    target_service=target,
                                    provider=self.name,
                                    dep_type=pattern["dep_type"],
                                    confidence=pattern["confidence"],
                                    metadata={
                                        "pattern": pattern["name"],
                                        "direction": "downstream",
                                    },
                                    raw_source=source,
                                    raw_target=target,
                                )
                            )
                except Exception:
                    continue

        return self._deduplicate(deps)

    def _add_service_filter(self, query: str, service: str, source_labels: list[str]) -> str:
        """Add service filter to query."""
        # Find a source label that's in the query and add filter
        for label in source_labels:
            if f"{label}=" in query or f"{label}~" in query:
                # Replace the regex matcher with exact match
                import re

                query = re.sub(
                    rf'{label}[=~]+"[^"]*"',
                    f'{label}="{service}"',
                    query,
                )
                return query

        # If no label found in query, add filter
        label = source_labels[0]
        # Insert before closing brace
        if "{" in query:
            query = query.replace("}", f',{label}="{service}"}}')
        return query

    def _add_target_filter(self, query: str, service: str, target_labels: list[str]) -> str:
        """Add target filter to query."""
        for label in target_labels:
            if f"{label}=" in query or f"{label}~" in query:
                import re

                query = re.sub(
                    rf'{label}[=~]+"[^"]*"',
                    f'{label}="{service}"',
                    query,
                )
                return query

        label = target_labels[0]
        if "{" in query:
            query = query.replace("}", f',{label}="{service}"}}')
        return query

    def _extract_label(self, metric: dict[str, str], labels: list[str]) -> str | None:
        """Extract first available label from metric."""
        for label in labels:
            if label in metric and metric[label]:
                return metric[label]
        return None

    def _deduplicate(self, deps: list[DiscoveredDependency]) -> list[DiscoveredDependency]:
        """Remove duplicate dependencies, keeping highest confidence."""
        seen: dict[str, DiscoveredDependency] = {}

        for dep in deps:
            key = f"{dep.source_service}:{dep.target_service}:{dep.dep_type.value}"

            if key not in seen or dep.confidence > seen[key].confidence:
                seen[key] = dep

        return list(seen.values())

    async def list_services(self) -> list[str]:
        """List all services with metrics in Prometheus."""
        services: set[str] = set()

        # Query for common service label names
        label_queries = [
            'count by (service) ({__name__=~".+", service=~".+"})',
            'count by (job) ({__name__=~".+", job=~".+"})',
        ]

        for query in label_queries:
            try:
                results = await self._query(query)
                for result in results:
                    metric = result.get("metric", {})
                    for label in ["service", "job"]:
                        if label in metric and metric[label]:
                            services.add(metric[label])
            except Exception:
                continue

        return sorted(services)

    async def health_check(self) -> ProviderHealth:
        """Check Prometheus connectivity."""
        start = time.time()

        try:
            auth = self._get_auth()
            async with httpx.AsyncClient(auth=auth, timeout=10.0) as client:
                response = await client.get(f"{self.url.rstrip('/')}/api/v1/status/config")
                latency = (time.time() - start) * 1000

                if response.status_code == 200:
                    return ProviderHealth(
                        healthy=True,
                        message="Connected to Prometheus",
                        latency_ms=latency,
                    )
                else:
                    return ProviderHealth(
                        healthy=False,
                        message=f"Prometheus returned {response.status_code}",
                        latency_ms=latency,
                    )
        except httpx.TimeoutException:
            return ProviderHealth(
                healthy=False,
                message="Prometheus connection timed out",
            )
        except Exception as e:
            return ProviderHealth(
                healthy=False,
                message=f"Prometheus connection failed: {e}",
            )

    async def get_service_attributes(self, service: str) -> dict:
        """Get service attributes from Prometheus labels."""
        attributes: dict[str, Any] = {}

        # Query for service info metrics
        try:
            results = await self._query(f'{{service="{service}", __name__=~".*info.*"}}')

            if results:
                # Collect all labels from info metrics
                for result in results:
                    metric = result.get("metric", {})
                    for key, value in metric.items():
                        if key not in ["__name__", "service"] and value:
                            attributes[key] = value
        except Exception:
            pass

        return attributes
