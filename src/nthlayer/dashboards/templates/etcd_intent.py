"""Intent-Based etcd Dashboard Template."""

from typing import List

from nthlayer.dashboards.panel_spec import PanelSpec, PanelType
from nthlayer.dashboards.templates.base_intent import IntentBasedTemplate


class EtcdIntentTemplate(IntentBasedTemplate):
    """etcd monitoring template using intent-based metrics."""

    @property
    def name(self) -> str:
        return "etcd"

    @property
    def display_name(self) -> str:
        return "etcd"

    def get_panel_specs(self, service_name: str = "$service") -> List[PanelSpec]:
        """Get etcd panel specifications with intents."""
        return [
            self._leader_spec(service_name),
            self._db_size_spec(service_name),
            self._proposals_spec(service_name),
            self._wal_fsync_spec(service_name),
            self._network_peer_spec(service_name),
        ]

    def get_overview_panels(self, service_name: str = "$service") -> List:
        """Get most critical etcd panels."""
        specs = [
            self._leader_spec(service_name),
            self._db_size_spec(service_name),
            self._proposals_spec(service_name),
        ]
        panels = []
        for spec in specs:
            panel = self._build_panel_from_spec(spec, service_name)
            if panel:
                panels.append(panel)
        return panels

    def _leader_spec(self, service: str) -> PanelSpec:
        return PanelSpec(
            title="Has Leader",
            panel_type=PanelType.STAT,
            intent="etcd.has_leader",
            query_template=f'{{{{metric}}}}{{service="{service}"}}',
            unit="short",
            description="Whether the cluster has a leader",
        )

    def _db_size_spec(self, service: str) -> PanelSpec:
        return PanelSpec(
            title="DB Size",
            panel_type=PanelType.TIMESERIES,
            intent="etcd.mvcc_db_total_size_in_bytes",
            query_template=f'{{{{metric}}}}{{service="{service}"}}',
            unit="bytes",
            description="Total size of the etcd database",
        )

    def _proposals_spec(self, service: str) -> PanelSpec:
        return PanelSpec(
            title="Proposals/sec",
            panel_type=PanelType.TIMESERIES,
            intent="etcd.proposals_committed_total",
            query_template=f'rate({{{{metric}}}}{{service="{service}"}}[5m])',
            unit="short",
            description="Raft proposals committed per second",
        )

    def _wal_fsync_spec(self, service: str) -> PanelSpec:
        return PanelSpec(
            title="WAL Fsync Duration (p99)",
            panel_type=PanelType.TIMESERIES,
            intent="etcd.disk_wal_fsync_duration_seconds",
            query_template=(
                f"histogram_quantile(0.99, sum by (le) "
                f'(rate({{{{metric}}}}_bucket{{service="{service}"}}[5m])))'
            ),
            unit="s",
            description="99th percentile WAL fsync duration",
        )

    def _network_peer_spec(self, service: str) -> PanelSpec:
        return PanelSpec(
            title="Network Peer RTT",
            panel_type=PanelType.TIMESERIES,
            intent="etcd.network_peer_round_trip_time_seconds",
            query_template=(
                f"histogram_quantile(0.99, sum by (le) "
                f'(rate({{{{metric}}}}_bucket{{service="{service}"}}[5m])))'
            ),
            unit="s",
            description="Peer round trip time",
        )
