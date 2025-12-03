"""
Intent-Based Worker Service Dashboard Template.

This template provides health panels for worker/background job services
using the intent system for metric resolution.
"""

from typing import List

from nthlayer.dashboards.panel_spec import PanelSpec, PanelType, QuerySpec
from nthlayer.dashboards.templates.base_intent import IntentBasedTemplate


class WorkerIntentTemplate(IntentBasedTemplate):
    """Worker/background job service monitoring template using intent-based metrics."""
    
    @property
    def name(self) -> str:
        return "worker"
    
    @property
    def display_name(self) -> str:
        return "Worker/Job Processor"
    
    def get_panel_specs(self, service_name: str = "$service") -> List[PanelSpec]:
        """Get worker panel specifications with intents."""
        return [
            self._processing_rate_spec(service_name),
            self._error_rate_spec(service_name),
            self._latency_p95_spec(service_name),
            self._latency_p99_spec(service_name),
            self._availability_spec(service_name),
        ]
    
    def get_health_panels(self, service_name: str = "$service") -> List:
        """Get core health panels for service dashboards."""
        specs = [
            self._processing_rate_spec(service_name),
            self._error_rate_spec(service_name),
            self._latency_p95_spec(service_name),
        ]
        panels = []
        for spec in specs:
            panel = self._build_panel_from_spec(spec, service_name)
            if panel:
                panels.append(panel)
        return panels
    
    def _processing_rate_spec(self, service: str) -> PanelSpec:
        """Processing rate panel spec."""
        return PanelSpec(
            title="Notification Rate",
            panel_type=PanelType.TIMESERIES,
            intent="worker.jobs_processed",
            query_template=f'sum(rate({{{{metric}}}}{{service="{service}"}}[5m]))',
            unit="short",
            description="Jobs/notifications processed per second"
        )
    
    def _error_rate_spec(self, service: str) -> PanelSpec:
        """Error rate panel spec."""
        return PanelSpec(
            title="Error Rate",
            panel_type=PanelType.TIMESERIES,
            queries=[
                QuerySpec(
                    intent="worker.jobs_processed",
                    query_template=f'sum(rate({{{{metric}}}}{{service="{service}",status="failed"}}[5m])) / sum(rate({{{{metric}}}}{{service="{service}"}}[5m])) * 100',
                    legend="error %",
                    ref_id="A"
                ),
            ],
            unit="percent",
            description="Percentage of jobs/notifications failing"
        )
    
    def _latency_p95_spec(self, service: str) -> PanelSpec:
        """P95 processing latency panel spec."""
        return PanelSpec(
            title="Processing Latency (p95)",
            panel_type=PanelType.TIMESERIES,
            intent="worker.job_duration",
            query_template=f'histogram_quantile(0.95, sum by (le) (rate({{{{metric}}}}{{service="{service}"}}[5m])))',
            unit="s",
            description="95th percentile processing duration"
        )
    
    def _latency_p99_spec(self, service: str) -> PanelSpec:
        """P99 processing latency panel spec."""
        return PanelSpec(
            title="Processing Latency (p99)",
            panel_type=PanelType.TIMESERIES,
            intent="worker.job_duration",
            query_template=f'histogram_quantile(0.99, sum by (le) (rate({{{{metric}}}}{{service="{service}"}}[5m])))',
            unit="s",
            description="99th percentile processing duration"
        )
    
    def _availability_spec(self, service: str) -> PanelSpec:
        """Availability panel spec."""
        return PanelSpec(
            title="Availability",
            panel_type=PanelType.STAT,
            queries=[
                QuerySpec(
                    intent="worker.jobs_processed",
                    query_template=f'sum(rate({{{{metric}}}}{{service="{service}",status!="failed"}}[5m])) / sum(rate({{{{metric}}}}{{service="{service}"}}[5m])) * 100',
                    legend="availability %",
                    ref_id="A"
                ),
            ],
            unit="percent",
            description="Percentage of successful job processing"
        )
