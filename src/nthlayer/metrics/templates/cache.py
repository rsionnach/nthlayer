"""
Cache client service type metric template.

For cache clients (Redis, Memcached, etc.).
"""

from nthlayer.metrics.models import (
    AttributeDefinition,
    MetricDefinition,
    MetricType,
    RequirementLevel,
    ServiceTypeTemplate,
)

CACHE_TEMPLATE = ServiceTypeTemplate(
    name="cache",
    required=[
        MetricDefinition(
            name="cache.operation.duration",
            type=MetricType.HISTOGRAM,
            unit="seconds",
            description="Duration of cache operations",
            attributes=[
                AttributeDefinition(
                    name="cache.system",
                    required=True,
                    examples=["redis", "memcached", "hazelcast"],
                ),
                AttributeDefinition(
                    name="cache.operation",
                    required=True,
                    examples=["get", "set", "delete", "mget", "mset"],
                ),
                AttributeDefinition(
                    name="cache.hit",
                    type="bool",
                    examples=["true", "false"],
                ),
            ],
            requirement_level=RequirementLevel.REQUIRED,
            slo_usage=["latency"],
            buckets=[0.0001, 0.0005, 0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5],
        ),
    ],
    recommended=[
        MetricDefinition(
            name="cache.hit_ratio",
            type=MetricType.GAUGE,
            unit="1",
            description="Cache hit ratio (0.0 to 1.0)",
            attributes=[
                AttributeDefinition(name="cache.system"),
                AttributeDefinition(name="cache.name"),
            ],
            requirement_level=RequirementLevel.RECOMMENDED,
            slo_usage=["efficiency"],
        ),
        MetricDefinition(
            name="cache.size",
            type=MetricType.GAUGE,
            unit="bytes",
            description="Current cache size in bytes",
            attributes=[
                AttributeDefinition(name="cache.system"),
                AttributeDefinition(name="cache.name"),
            ],
            requirement_level=RequirementLevel.RECOMMENDED,
        ),
        MetricDefinition(
            name="cache.evictions.total",
            type=MetricType.COUNTER,
            unit="{eviction}",
            description="Number of cache evictions",
            attributes=[
                AttributeDefinition(name="cache.system"),
                AttributeDefinition(name="eviction.policy"),
            ],
            requirement_level=RequirementLevel.RECOMMENDED,
        ),
        MetricDefinition(
            name="cache.keys.count",
            type=MetricType.GAUGE,
            unit="{key}",
            description="Number of keys in cache",
            attributes=[
                AttributeDefinition(name="cache.system"),
                AttributeDefinition(name="cache.name"),
            ],
            requirement_level=RequirementLevel.RECOMMENDED,
        ),
    ],
    slo_formulas={
        "latency_p99": (
            "histogram_quantile(0.99, "
            "sum(rate(cache_operation_duration_seconds_bucket[5m])) by (le)"
            ")"
        ),
        "hit_rate": (
            "sum(rate(cache_operation_duration_seconds_count{cache_hit='true'}[5m])) / "
            "sum(rate(cache_operation_duration_seconds_count{cache_operation='get'}[5m]))"
        ),
    },
)
