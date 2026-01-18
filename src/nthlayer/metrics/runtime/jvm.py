"""
JVM runtime metric definitions.

Based on OpenTelemetry JVM runtime semantic conventions.
Reference: https://opentelemetry.io/docs/specs/semconv/runtime/jvm-metrics/
"""

from nthlayer.metrics.models import (
    AttributeDefinition,
    MetricDefinition,
    MetricType,
    RequirementLevel,
)
from nthlayer.metrics.standards.otel_semconv import (
    JVM_CLASSES_LOADED,
    JVM_GC_DURATION,
    JVM_MEMORY_USED,
    JVM_THREADS_COUNT,
)

JVM_METRICS: list[MetricDefinition] = [
    MetricDefinition(
        name=JVM_MEMORY_USED,
        type=MetricType.UPDOWN_COUNTER,
        unit="bytes",
        description="JVM memory used",
        attributes=[
            AttributeDefinition(
                name="jvm.memory.type",
                required=True,
                examples=["heap", "non_heap"],
            ),
            AttributeDefinition(
                name="jvm.memory.pool.name",
                examples=["G1 Eden Space", "G1 Old Gen", "Metaspace"],
            ),
        ],
        requirement_level=RequirementLevel.RECOMMENDED,
        slo_usage=["saturation"],
    ),
    MetricDefinition(
        name="process.runtime.jvm.memory.committed",
        type=MetricType.UPDOWN_COUNTER,
        unit="bytes",
        description="JVM memory committed",
        attributes=[
            AttributeDefinition(name="jvm.memory.type", required=True),
            AttributeDefinition(name="jvm.memory.pool.name"),
        ],
        requirement_level=RequirementLevel.RECOMMENDED,
    ),
    MetricDefinition(
        name="process.runtime.jvm.memory.limit",
        type=MetricType.UPDOWN_COUNTER,
        unit="bytes",
        description="JVM memory limit",
        attributes=[
            AttributeDefinition(name="jvm.memory.type", required=True),
            AttributeDefinition(name="jvm.memory.pool.name"),
        ],
        requirement_level=RequirementLevel.RECOMMENDED,
    ),
    MetricDefinition(
        name=JVM_GC_DURATION,
        type=MetricType.HISTOGRAM,
        unit="seconds",
        description="Duration of JVM garbage collection",
        attributes=[
            AttributeDefinition(
                name="jvm.gc.name",
                required=True,
                examples=["G1 Young Generation", "G1 Old Generation"],
            ),
            AttributeDefinition(
                name="jvm.gc.action",
                examples=["end of minor GC", "end of major GC"],
            ),
        ],
        requirement_level=RequirementLevel.RECOMMENDED,
        buckets=[0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0],
    ),
    MetricDefinition(
        name=JVM_THREADS_COUNT,
        type=MetricType.UPDOWN_COUNTER,
        unit="{thread}",
        description="Number of JVM threads",
        attributes=[
            AttributeDefinition(
                name="jvm.thread.daemon",
                type="bool",
                examples=["true", "false"],
            ),
            AttributeDefinition(
                name="jvm.thread.state",
                examples=["runnable", "blocked", "waiting", "timed_waiting"],
            ),
        ],
        requirement_level=RequirementLevel.RECOMMENDED,
    ),
    MetricDefinition(
        name=JVM_CLASSES_LOADED,
        type=MetricType.UPDOWN_COUNTER,
        unit="{class}",
        description="Number of loaded JVM classes",
        requirement_level=RequirementLevel.RECOMMENDED,
    ),
    MetricDefinition(
        name="process.runtime.jvm.cpu.recent_utilization",
        type=MetricType.GAUGE,
        unit="1",
        description="Recent CPU utilization (0.0 to 1.0)",
        requirement_level=RequirementLevel.RECOMMENDED,
    ),
]
