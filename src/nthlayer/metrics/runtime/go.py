"""
Go runtime metric definitions.

Based on OpenTelemetry Go runtime semantic conventions.
Reference: https://opentelemetry.io/docs/specs/semconv/runtime/
"""

from nthlayer.metrics.models import (
    MetricDefinition,
    MetricType,
    RequirementLevel,
)

GO_METRICS: list[MetricDefinition] = [
    MetricDefinition(
        name="process.runtime.go.goroutines",
        type=MetricType.UPDOWN_COUNTER,
        unit="{goroutine}",
        description="Number of goroutines",
        requirement_level=RequirementLevel.RECOMMENDED,
        slo_usage=["saturation"],
    ),
    MetricDefinition(
        name="process.runtime.go.gc.pause_total",
        type=MetricType.COUNTER,
        unit="seconds",
        description="Total GC pause time",
        requirement_level=RequirementLevel.RECOMMENDED,
    ),
    MetricDefinition(
        name="process.runtime.go.gc.count",
        type=MetricType.COUNTER,
        unit="{gc}",
        description="Number of completed GC cycles",
        requirement_level=RequirementLevel.RECOMMENDED,
    ),
    MetricDefinition(
        name="process.runtime.go.mem.heap_alloc",
        type=MetricType.UPDOWN_COUNTER,
        unit="bytes",
        description="Heap memory allocated and in use",
        requirement_level=RequirementLevel.RECOMMENDED,
    ),
    MetricDefinition(
        name="process.runtime.go.mem.heap_idle",
        type=MetricType.UPDOWN_COUNTER,
        unit="bytes",
        description="Heap memory waiting to be used",
        requirement_level=RequirementLevel.RECOMMENDED,
    ),
    MetricDefinition(
        name="process.runtime.go.mem.heap_inuse",
        type=MetricType.UPDOWN_COUNTER,
        unit="bytes",
        description="Heap memory in use",
        requirement_level=RequirementLevel.RECOMMENDED,
    ),
    MetricDefinition(
        name="process.runtime.go.mem.heap_released",
        type=MetricType.UPDOWN_COUNTER,
        unit="bytes",
        description="Heap memory released to the OS",
        requirement_level=RequirementLevel.RECOMMENDED,
    ),
    MetricDefinition(
        name="process.runtime.go.mem.stack_inuse",
        type=MetricType.UPDOWN_COUNTER,
        unit="bytes",
        description="Stack memory in use",
        requirement_level=RequirementLevel.RECOMMENDED,
    ),
]
