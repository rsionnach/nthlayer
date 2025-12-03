"""
Panel Specification Model for Intent-Based Dashboard Generation.

PanelSpec defines what a panel should display using abstract intents
rather than hardcoded metric names. The resolver translates these
intents to actual metrics at generation time.

This enables:
1. Exporter-agnostic dashboards
2. Automatic fallback handling
3. Guidance panels when metrics unavailable
4. Custom metric overrides
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional


class PanelType(Enum):
    """Types of dashboard panels."""
    TIMESERIES = "timeseries"
    GAUGE = "gauge"
    STAT = "stat"
    TABLE = "table"
    HEATMAP = "heatmap"
    TEXT = "text"  # For guidance panels


class AggregationType(Enum):
    """Common aggregation functions."""
    RATE = "rate"
    INCREASE = "increase"
    SUM = "sum"
    AVG = "avg"
    MAX = "max"
    MIN = "min"
    HISTOGRAM_QUANTILE = "histogram_quantile"


@dataclass
class QuerySpec:
    """Specification for a single query within a panel."""
    
    intent: str  # e.g., "postgresql.connections"
    query_template: str = "{{metric}}"  # Template with {{metric}} placeholder
    legend: str = ""  # Legend format
    ref_id: str = "A"  # Query reference ID
    
    # Optional aggregation settings
    aggregation: Optional[AggregationType] = None
    rate_interval: str = "5m"
    
    # For histogram queries
    quantile: Optional[float] = None  # e.g., 0.95 for p95
    
    # Additional labels/filters
    additional_labels: Dict[str, str] = field(default_factory=dict)
    
    def build_query(self, metric_name: str, service: str) -> str:
        """
        Build actual PromQL query from template.
        
        Args:
            metric_name: Resolved metric name
            service: Service name for filtering
            
        Returns:
            Complete PromQL query string
        """
        # Start with template
        query = self.query_template.replace("{{metric}}", metric_name)
        query = query.replace("$service", service)
        query = query.replace("{{service}}", service)
        
        return query


@dataclass
class ThresholdSpec:
    """Threshold configuration for panels."""
    
    value: float
    color: str = "red"
    mode: str = "gt"  # gt, lt, eq


@dataclass
class PanelSpec:
    """
    Specification for a dashboard panel using intents.
    
    Templates define panels using PanelSpec, and the builder
    resolves intents to actual metrics at generation time.
    """
    
    title: str
    panel_type: PanelType = PanelType.TIMESERIES
    
    # Intent-based queries
    queries: List[QuerySpec] = field(default_factory=list)
    
    # For simple single-intent panels
    intent: Optional[str] = None
    query_template: str = "{{metric}}"
    
    # Display settings
    unit: str = "short"
    description: str = ""
    
    # Layout hints
    width: int = 12
    height: int = 8
    
    # Thresholds
    thresholds: List[ThresholdSpec] = field(default_factory=list)
    
    # For stat/gauge panels
    color_mode: str = "value"
    graph_mode: str = "area"
    
    # Row grouping
    row: Optional[str] = None
    
    # Whether to skip if metrics unavailable (vs showing guidance)
    skip_if_unavailable: bool = False
    
    # Priority for layout ordering
    priority: int = 0
    
    def __post_init__(self):
        """Convert simple intent to queries if needed."""
        if self.intent and not self.queries:
            self.queries = [
                QuerySpec(
                    intent=self.intent,
                    query_template=self.query_template,
                    ref_id="A"
                )
            ]
    
    def get_intents(self) -> List[str]:
        """Get all intents used by this panel."""
        return [q.intent for q in self.queries]


@dataclass
class RowSpec:
    """Specification for a dashboard row (collapsible section)."""
    
    title: str
    panels: List[PanelSpec] = field(default_factory=list)
    collapsed: bool = False


@dataclass
class GuidancePanelSpec:
    """
    Specification for a guidance panel shown when metrics unavailable.
    
    Guidance panels explain what instrumentation is needed and how
    to add it, rather than showing "No Data".
    """
    
    title: str
    intent: str
    missing_metrics: List[str]
    
    # Exporter info
    exporter_name: Optional[str] = None
    exporter_helm: Optional[str] = None
    exporter_docker: Optional[str] = None
    exporter_docs: Optional[str] = None
    
    # Instrumentation code snippets
    code_snippets: Dict[str, str] = field(default_factory=dict)
    
    # Custom override hint
    yaml_override_example: str = ""
    
    def build_markdown(self) -> str:
        """Build markdown content for the guidance panel."""
        lines = [
            f"## {self.title} - Needs Instrumentation",
            "",
            "This panel requires metrics that aren't currently being collected.",
            "",
            f"**Required metric pattern:** `{self.missing_metrics[0] if self.missing_metrics else 'N/A'}`",
            "",
        ]
        
        if self.exporter_name:
            lines.extend([
                "### Install Exporter",
                "",
            ])
            if self.exporter_helm:
                lines.append(f"**Helm:** `{self.exporter_helm}`")
            if self.exporter_docker:
                lines.append(f"**Docker:** `{self.exporter_docker}`")
            if self.exporter_docs:
                lines.append(f"**Docs:** [{self.exporter_docs}]({self.exporter_docs})")
            lines.append("")
        
        if self.yaml_override_example:
            lines.extend([
                "### Or Use Custom Metric",
                "",
                "Add to your service YAML:",
                "```yaml",
                self.yaml_override_example,
                "```",
            ])
        
        return "\n".join(lines)


# =============================================================================
# Template Builder Helpers
# =============================================================================

def http_availability_panel(service_var: str = "$service") -> PanelSpec:
    """Create standard HTTP availability panel."""
    return PanelSpec(
        title="Availability",
        panel_type=PanelType.STAT,
        intent="http.requests_total",
        query_template=f'''sum(rate({{{{metric}}}}{{service="{service_var}",status!~"5.."}}[5m])) / 
sum(rate({{{{metric}}}}{{service="{service_var}"}}[5m])) * 100''',
        unit="percent",
        description="Percentage of successful (non-5xx) requests",
        thresholds=[
            ThresholdSpec(value=99, color="green"),
            ThresholdSpec(value=95, color="yellow"),
            ThresholdSpec(value=0, color="red"),
        ]
    )


def http_latency_panel(percentile: float = 0.95, service_var: str = "$service") -> PanelSpec:
    """Create HTTP latency percentile panel."""
    pct_label = f"p{int(percentile * 100)}"
    return PanelSpec(
        title=f"Latency ({pct_label})",
        panel_type=PanelType.STAT,
        intent="http.request_duration",
        query_template=f'''histogram_quantile({percentile}, 
sum(rate({{{{metric}}}}{{service="{service_var}"}}[5m])) by (le))''',
        unit="s",
        description=f"{pct_label} response latency"
    )


def database_connections_panel(tech: str, service_var: str = "$service") -> PanelSpec:
    """Create database connections panel for any DB technology."""
    return PanelSpec(
        title=f"{tech.title()} Connections",
        panel_type=PanelType.TIMESERIES,
        intent=f"{tech}.connections",
        query_template=f'{{{{metric}}}}{{service="{service_var}"}}',
        unit="short",
        description="Active database connections"
    )


def cache_hit_ratio_panel(service_var: str = "$service") -> PanelSpec:
    """Create cache hit ratio panel."""
    return PanelSpec(
        title="Cache Hit Ratio",
        panel_type=PanelType.GAUGE,
        queries=[
            QuerySpec(
                intent="redis.hits",
                query_template=f'''rate({{{{metric}}}}{{service="{service_var}"}}[5m]) / 
(rate({{{{metric}}}}{{service="{service_var}"}}[5m]) + 
rate(cache_misses_total{{service="{service_var}"}}[5m])) * 100''',
                ref_id="A"
            )
        ],
        unit="percent",
        description="Percentage of cache hits vs total requests"
    )


# =============================================================================
# Panel Collection for Technologies
# =============================================================================

def get_http_panels() -> List[PanelSpec]:
    """Get standard HTTP panels."""
    return [
        http_availability_panel(),
        http_latency_panel(0.95),
        http_latency_panel(0.99),
        PanelSpec(
            title="Request Rate",
            panel_type=PanelType.TIMESERIES,
            intent="http.requests_total",
            query_template='sum(rate({{metric}}{service="$service"}[5m])) by (endpoint)',
            unit="reqps"
        ),
        PanelSpec(
            title="Error Rate",
            panel_type=PanelType.TIMESERIES,
            intent="http.requests_total",
            query_template='sum(rate({{metric}}{service="$service",status=~"5.."}[5m]))',
            unit="reqps"
        ),
        PanelSpec(
            title="Requests In Flight",
            panel_type=PanelType.TIMESERIES,
            intent="http.requests_in_flight",
            query_template='{{metric}}{service="$service"}',
            unit="short"
        ),
    ]


def get_postgresql_panels() -> List[PanelSpec]:
    """Get standard PostgreSQL panels."""
    return [
        database_connections_panel("postgresql"),
        PanelSpec(
            title="Transactions",
            panel_type=PanelType.TIMESERIES,
            queries=[
                QuerySpec(
                    intent="postgresql.transactions_committed",
                    query_template='rate({{metric}}{service="$service"}[5m])',
                    legend="Committed",
                    ref_id="A"
                ),
                QuerySpec(
                    intent="postgresql.transactions_rolled_back",
                    query_template='rate({{metric}}{service="$service"}[5m])',
                    legend="Rolled Back",
                    ref_id="B"
                ),
            ],
            unit="short"
        ),
        PanelSpec(
            title="Cache Hit Ratio",
            panel_type=PanelType.GAUGE,
            queries=[
                QuerySpec(
                    intent="postgresql.cache_hit",
                    query_template='''rate({{metric}}{service="$service"}[5m]) / 
(rate({{metric}}{service="$service"}[5m]) + rate(pg_stat_database_blks_read{service="$service"}[5m])) * 100''',
                    ref_id="A"
                )
            ],
            unit="percent"
        ),
        PanelSpec(
            title="Database Size",
            panel_type=PanelType.STAT,
            intent="postgresql.database_size",
            query_template='{{metric}}{service="$service"}',
            unit="bytes"
        ),
        PanelSpec(
            title="Dead Tuples (Table Bloat)",
            panel_type=PanelType.TIMESERIES,
            intent="postgresql.table_bloat",
            query_template='sum({{metric}}{service="$service"}) by (relname)',
            unit="short"
        ),
        PanelSpec(
            title="Deadlocks",
            panel_type=PanelType.TIMESERIES,
            intent="postgresql.deadlocks",
            query_template='rate({{metric}}{service="$service"}[5m])',
            unit="short"
        ),
        PanelSpec(
            title="Replication Lag",
            panel_type=PanelType.TIMESERIES,
            intent="postgresql.replication_lag",
            query_template='{{metric}}{service="$service"}',
            unit="s",
            skip_if_unavailable=True  # Only relevant for replicas
        ),
    ]


def get_redis_panels() -> List[PanelSpec]:
    """Get standard Redis panels."""
    return [
        PanelSpec(
            title="Memory Usage",
            panel_type=PanelType.TIMESERIES,
            intent="redis.memory",
            query_template='{{metric}}{service="$service"}',
            unit="bytes"
        ),
        PanelSpec(
            title="Connected Clients",
            panel_type=PanelType.TIMESERIES,
            intent="redis.connections",
            query_template='{{metric}}{service="$service"}',
            unit="short"
        ),
        PanelSpec(
            title="Cache Hits vs Misses",
            panel_type=PanelType.TIMESERIES,
            queries=[
                QuerySpec(
                    intent="redis.hits",
                    query_template='rate({{metric}}{service="$service"}[5m])',
                    legend="Hits",
                    ref_id="A"
                ),
                QuerySpec(
                    intent="redis.misses",
                    query_template='rate({{metric}}{service="$service"}[5m])',
                    legend="Misses",
                    ref_id="B"
                ),
            ],
            unit="short"
        ),
        cache_hit_ratio_panel(),
        PanelSpec(
            title="Keys",
            panel_type=PanelType.STAT,
            intent="redis.keys",
            query_template='sum({{metric}}{service="$service"})',
            unit="short"
        ),
        PanelSpec(
            title="Evicted Keys",
            panel_type=PanelType.TIMESERIES,
            intent="redis.evicted_keys",
            query_template='rate({{metric}}{service="$service"}[5m])',
            unit="short"
        ),
        PanelSpec(
            title="Commands/sec",
            panel_type=PanelType.TIMESERIES,
            intent="redis.commands",
            query_template='rate({{metric}}{service="$service"}[5m])',
            unit="short"
        ),
    ]
