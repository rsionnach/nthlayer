"""
Background worker/job service type metric template.

For background job processors like Celery, Sidekiq, RQ, etc.
"""

from nthlayer.metrics.models import (
    AttributeDefinition,
    MetricDefinition,
    MetricType,
    RequirementLevel,
    ServiceTypeTemplate,
)

WORKER_TEMPLATE = ServiceTypeTemplate(
    name="worker",
    required=[
        MetricDefinition(
            name="jobs.duration",
            type=MetricType.HISTOGRAM,
            unit="seconds",
            description="Duration of job execution",
            attributes=[
                AttributeDefinition(
                    name="job.type",
                    required=True,
                    examples=["send_email", "process_payment", "generate_report"],
                ),
                AttributeDefinition(
                    name="job.status",
                    required=True,
                    examples=["success", "failure", "timeout"],
                ),
            ],
            requirement_level=RequirementLevel.REQUIRED,
            slo_usage=["latency"],
            buckets=[0.1, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0, 60.0, 120.0, 300.0],
        ),
        MetricDefinition(
            name="jobs.total",
            type=MetricType.COUNTER,
            unit="{job}",
            description="Total jobs processed",
            attributes=[
                AttributeDefinition(
                    name="job.type",
                    required=True,
                ),
                AttributeDefinition(
                    name="job.status",
                    required=True,
                    examples=["success", "failure", "timeout"],
                ),
            ],
            requirement_level=RequirementLevel.REQUIRED,
            slo_usage=["availability"],
        ),
    ],
    recommended=[
        MetricDefinition(
            name="jobs.queue.depth",
            type=MetricType.GAUGE,
            unit="{job}",
            description="Number of jobs waiting in queue",
            attributes=[
                AttributeDefinition(name="queue.name"),
            ],
            requirement_level=RequirementLevel.RECOMMENDED,
            slo_usage=["saturation"],
        ),
        MetricDefinition(
            name="jobs.queue.latency",
            type=MetricType.HISTOGRAM,
            unit="seconds",
            description="Time jobs spend waiting in queue",
            attributes=[
                AttributeDefinition(name="queue.name"),
                AttributeDefinition(name="job.type"),
            ],
            requirement_level=RequirementLevel.RECOMMENDED,
        ),
        MetricDefinition(
            name="jobs.retries.total",
            type=MetricType.COUNTER,
            unit="{retry}",
            description="Number of job retries",
            attributes=[
                AttributeDefinition(name="job.type"),
            ],
            requirement_level=RequirementLevel.RECOMMENDED,
        ),
    ],
    slo_formulas={
        "success_rate": (
            "sum(rate(jobs_total{job_status='success'}[5m])) / " "sum(rate(jobs_total[5m]))"
        ),
        "latency_p99": (
            "histogram_quantile(0.99, " "sum(rate(jobs_duration_seconds_bucket[5m])) by (le)" ")"
        ),
    },
)
