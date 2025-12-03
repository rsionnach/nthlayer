"""Kubernetes dashboard template.

Comprehensive monitoring panels for Kubernetes deployments.
"""

from typing import List

from nthlayer.dashboards.models import Panel, Target
from nthlayer.dashboards.templates.base import TechnologyTemplate


class KubernetesTemplate(TechnologyTemplate):
    """Kubernetes monitoring template."""
    
    @property
    def name(self) -> str:
        return "kubernetes"
    
    @property
    def display_name(self) -> str:
        return "Kubernetes"
    
    def get_panels(self, service_name: str = "$service") -> List[Panel]:
        """Get all Kubernetes monitoring panels."""
        return [
            self._pod_status_panel(service_name),
            self._cpu_usage_panel(service_name),
            self._memory_usage_panel(service_name),
            self._restart_count_panel(service_name),
            self._pod_ready_panel(service_name),
            self._network_io_panel(service_name),
            self._disk_io_panel(service_name),
            self._container_throttling_panel(service_name),
            self._oom_kills_panel(service_name),
            self._resource_requests_limits_panel(service_name),
        ]
    
    def get_overview_panels(self, service_name: str = "$service") -> List[Panel]:
        """Get most critical Kubernetes panels."""
        return [
            self._pod_status_panel(service_name),
            self._cpu_usage_panel(service_name),
            self._memory_usage_panel(service_name),
        ]
    
    def _pod_status_panel(self, service: str) -> Panel:
        """Pod status breakdown."""
        return Panel(
            title="Pod Status",
            panel_type="timeseries",
            targets=[
                Target(
                    expr=f'kube_pod_status_phase{{service="{service}",phase="Running"}}',
                    legend_format="Running",
                    ref_id="A"
                ),
                Target(
                    expr=f'kube_pod_status_phase{{service="{service}",phase="Pending"}}',
                    legend_format="Pending",
                    ref_id="B"
                ),
                Target(
                    expr=f'kube_pod_status_phase{{service="{service}",phase="Failed"}}',
                    legend_format="Failed",
                    ref_id="C"
                ),
            ],
            description="Number of pods in each status",
            unit="short",
            decimals=0,
            grid_pos={"h": 8, "w": 12, "x": 0, "y": 0}
        )
    
    def _cpu_usage_panel(self, service: str) -> Panel:
        """CPU usage by pod."""
        return Panel(
            title="CPU Usage",
            panel_type="timeseries",
            targets=[
                Target(
                    expr=f'sum(rate(container_cpu_usage_seconds_total{{service="{service}",container!=""}}[5m])) by (pod)',
                    legend_format="{{pod}}",
                    ref_id="A"
                ),
            ],
            description="CPU cores used per pod",
            unit="short",
            decimals=2,
            grid_pos={"h": 8, "w": 12, "x": 0, "y": 0}
        )
    
    def _memory_usage_panel(self, service: str) -> Panel:
        """Memory usage by pod."""
        return Panel(
            title="Memory Usage",
            panel_type="timeseries",
            targets=[
                Target(
                    expr=f'sum(container_memory_working_set_bytes{{service="{service}",container!=""}}) by (pod)',
                    legend_format="{{pod}}",
                    ref_id="A"
                ),
            ],
            description="Memory usage per pod",
            unit="bytes",
            decimals=0,
            grid_pos={"h": 8, "w": 12, "x": 0, "y": 0}
        )
    
    def _restart_count_panel(self, service: str) -> Panel:
        """Container restart count."""
        return Panel(
            title="Container Restarts",
            panel_type="timeseries",
            targets=[
                Target(
                    expr=f'sum(rate(kube_pod_container_status_restarts_total{{service="{service}"}}[15m])) by (pod)',
                    legend_format="{{pod}} restarts",
                    ref_id="A"
                ),
            ],
            description="Container restarts per pod - should be zero",
            unit="short",
            decimals=2,
            thresholds=[
                {"value": 0, "color": "green"},
                {"value": 0.01, "color": "yellow"},
                {"value": 0.1, "color": "red"},
            ],
            grid_pos={"h": 8, "w": 12, "x": 0, "y": 0}
        )
    
    def _pod_ready_panel(self, service: str) -> Panel:
        """Pods ready vs desired."""
        return Panel(
            title="Pod Readiness",
            panel_type="gauge",
            targets=[
                Target(
                    expr=(
                        f'sum(kube_pod_status_ready{{service="{service}",condition="true"}}) / '
                        f'sum(kube_deployment_spec_replicas{{service="{service}"}}) * 100'
                    ),
                    legend_format="Ready %",
                    ref_id="A"
                ),
            ],
            description="Percentage of pods ready vs desired count",
            unit="percent",
            decimals=0,
            min=0,
            max=100,
            thresholds=[
                {"value": 0, "color": "red"},
                {"value": 80, "color": "yellow"},
                {"value": 100, "color": "green"},
            ],
            grid_pos={"h": 8, "w": 6, "x": 0, "y": 0}
        )
    
    def _network_io_panel(self, service: str) -> Panel:
        """Network I/O by pod."""
        return Panel(
            title="Network I/O",
            panel_type="timeseries",
            targets=[
                Target(
                    expr=f'sum(rate(container_network_receive_bytes_total{{service="{service}"}}[5m])) by (pod)',
                    legend_format="{{pod}} RX",
                    ref_id="A"
                ),
                Target(
                    expr=f'sum(rate(container_network_transmit_bytes_total{{service="{service}"}}[5m])) by (pod)',
                    legend_format="{{pod}} TX",
                    ref_id="B"
                ),
            ],
            description="Network receive and transmit bytes per second",
            unit="Bps",
            decimals=0,
            grid_pos={"h": 8, "w": 12, "x": 0, "y": 0}
        )
    
    def _disk_io_panel(self, service: str) -> Panel:
        """Disk I/O by pod."""
        return Panel(
            title="Disk I/O",
            panel_type="timeseries",
            targets=[
                Target(
                    expr=f'sum(rate(container_fs_reads_bytes_total{{service="{service}"}}[5m])) by (pod)',
                    legend_format="{{pod}} reads",
                    ref_id="A"
                ),
                Target(
                    expr=f'sum(rate(container_fs_writes_bytes_total{{service="{service}"}}[5m])) by (pod)',
                    legend_format="{{pod}} writes",
                    ref_id="B"
                ),
            ],
            description="Disk read and write throughput",
            unit="Bps",
            decimals=0,
            grid_pos={"h": 8, "w": 12, "x": 0, "y": 0}
        )
    
    def _container_throttling_panel(self, service: str) -> Panel:
        """CPU throttling events."""
        return Panel(
            title="CPU Throttling",
            panel_type="timeseries",
            targets=[
                Target(
                    expr=f'rate(container_cpu_cfs_throttled_seconds_total{{service="{service}",container!=""}}[5m])',
                    legend_format="{{pod}} throttled",
                    ref_id="A"
                ),
            ],
            description="CPU throttling - increase limits if consistently high",
            unit="s",
            decimals=3,
            thresholds=[
                {"value": 0, "color": "green"},
                {"value": 0.1, "color": "yellow"},
                {"value": 1, "color": "red"},
            ],
            grid_pos={"h": 8, "w": 12, "x": 0, "y": 0}
        )
    
    def _oom_kills_panel(self, service: str) -> Panel:
        """Out of memory kills."""
        return Panel(
            title="OOM Kills",
            panel_type="stat",
            targets=[
                Target(
                    expr=f'sum(rate(kube_pod_container_status_terminated_reason{{service="{service}",reason="OOMKilled"}}[1h]))',
                    legend_format="OOM kills/hour",
                    ref_id="A"
                ),
            ],
            description="Out of memory kills in last hour - should be zero",
            unit="short",
            decimals=0,
            thresholds=[
                {"value": 0, "color": "green"},
                {"value": 1, "color": "red"},
            ],
            grid_pos={"h": 8, "w": 6, "x": 0, "y": 0}
        )
    
    def _resource_requests_limits_panel(self, service: str) -> Panel:
        """CPU/memory requests vs limits."""
        return Panel(
            title="Resource Requests vs Limits",
            panel_type="timeseries",
            targets=[
                Target(
                    expr=f'sum(kube_pod_container_resource_requests{{service="{service}",resource="cpu"}}) by (pod)',
                    legend_format="{{pod}} CPU request",
                    ref_id="A"
                ),
                Target(
                    expr=f'sum(kube_pod_container_resource_limits{{service="{service}",resource="cpu"}}) by (pod)',
                    legend_format="{{pod}} CPU limit",
                    ref_id="B"
                ),
            ],
            description="Configured CPU requests and limits",
            unit="short",
            decimals=2,
            grid_pos={"h": 8, "w": 12, "x": 0, "y": 0}
        )
