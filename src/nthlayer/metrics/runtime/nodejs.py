"""
Node.js runtime metric definitions.

Based on OpenTelemetry Node.js runtime semantic conventions.
Reference: https://opentelemetry.io/docs/specs/semconv/runtime/
"""

from nthlayer.metrics.models import (
    MetricDefinition,
    MetricType,
    RequirementLevel,
)

NODEJS_METRICS: list[MetricDefinition] = [
    MetricDefinition(
        name="process.runtime.nodejs.memory.heap.used",
        type=MetricType.GAUGE,
        unit="bytes",
        description="Node.js heap memory used",
        requirement_level=RequirementLevel.RECOMMENDED,
        slo_usage=["saturation"],
    ),
    MetricDefinition(
        name="process.runtime.nodejs.memory.heap.total",
        type=MetricType.GAUGE,
        unit="bytes",
        description="Node.js total heap memory",
        requirement_level=RequirementLevel.RECOMMENDED,
    ),
    MetricDefinition(
        name="process.runtime.nodejs.memory.external",
        type=MetricType.GAUGE,
        unit="bytes",
        description="Node.js external memory (C++ objects bound to V8)",
        requirement_level=RequirementLevel.RECOMMENDED,
    ),
    MetricDefinition(
        name="process.runtime.nodejs.memory.array_buffers",
        type=MetricType.GAUGE,
        unit="bytes",
        description="Node.js ArrayBuffer memory",
        requirement_level=RequirementLevel.RECOMMENDED,
    ),
    MetricDefinition(
        name="process.runtime.nodejs.event_loop.lag",
        type=MetricType.GAUGE,
        unit="seconds",
        description="Event loop lag (delay between scheduled and executed callbacks)",
        requirement_level=RequirementLevel.RECOMMENDED,
        slo_usage=["latency"],
    ),
    MetricDefinition(
        name="process.runtime.nodejs.event_loop.utilization",
        type=MetricType.GAUGE,
        unit="1",
        description="Event loop utilization (0.0 to 1.0)",
        requirement_level=RequirementLevel.RECOMMENDED,
    ),
    MetricDefinition(
        name="process.runtime.nodejs.active_handles",
        type=MetricType.GAUGE,
        unit="{handle}",
        description="Number of active handles (sockets, timers, etc.)",
        requirement_level=RequirementLevel.RECOMMENDED,
    ),
    MetricDefinition(
        name="process.runtime.nodejs.active_requests",
        type=MetricType.GAUGE,
        unit="{request}",
        description="Number of active async requests",
        requirement_level=RequirementLevel.RECOMMENDED,
    ),
]
