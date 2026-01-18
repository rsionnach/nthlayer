from __future__ import annotations

import time
from contextlib import asynccontextmanager
from typing import Any, AsyncIterator

import aioboto3
import structlog

logger = structlog.get_logger()


class MetricsCollector:
    """CloudWatch metrics collector."""

    def __init__(self, namespace: str = "NthLayer", region: str = "eu-west-1") -> None:
        self.namespace = namespace
        self.region = region
        self._metrics_buffer: list[dict[str, Any]] = []

    @asynccontextmanager
    async def timer(self, metric_name: str, **dimensions: str) -> AsyncIterator[None]:
        """Context manager to time operations and emit duration metric."""
        start = time.time()
        try:
            yield
        finally:
            duration = time.time() - start
            await self.emit(metric_name, duration, unit="Seconds", **dimensions)

    async def emit(
        self,
        metric_name: str,
        value: float,
        *,
        unit: str = "Count",
        **dimensions: str,
    ) -> None:
        """Emit a metric to CloudWatch."""
        metric_data = {
            "MetricName": metric_name,
            "Value": value,
            "Unit": unit,
            "Dimensions": [{"Name": k, "Value": v} for k, v in dimensions.items()],
            "Timestamp": time.time(),
        }
        self._metrics_buffer.append(metric_data)

        if len(self._metrics_buffer) >= 20:
            await self._flush()

    async def _flush(self) -> None:
        """Flush buffered metrics to CloudWatch."""
        if not self._metrics_buffer:
            return

        try:
            session = aioboto3.Session(region_name=self.region)
            async with session.client("cloudwatch") as client:
                await client.put_metric_data(
                    Namespace=self.namespace,
                    MetricData=self._metrics_buffer,
                )
            self._metrics_buffer.clear()
        except Exception as exc:
            logger.error("metrics_flush_failed", error=str(exc))

    async def close(self) -> None:
        """Flush remaining metrics on shutdown."""
        await self._flush()


_metrics_collector: MetricsCollector | None = None


def get_metrics_collector(
    namespace: str = "NthLayer", region: str = "eu-west-1"
) -> MetricsCollector:
    """Get singleton metrics collector."""
    global _metrics_collector
    if _metrics_collector is None:
        _metrics_collector = MetricsCollector(namespace, region)
    return _metrics_collector
