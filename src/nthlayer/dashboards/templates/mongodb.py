"""MongoDB dashboard template."""

from typing import List

from nthlayer.dashboards.models import Panel, Target
from nthlayer.dashboards.templates.base import TechnologyTemplate


class MongoDBTemplate(TechnologyTemplate):
    """Template for MongoDB panels."""
    
    @property
    def name(self) -> str:
        return "mongodb"
    
    @property
    def display_name(self) -> str:
        return "MongoDB"
    
    def get_overview_panels(self, service_var: str = "$service") -> List[Panel]:
        """Get overview MongoDB panels.
        
        Args:
            service_var: Service variable name (default: $service)
            
        Returns:
            List of MongoDB monitoring panels
        """
        return [
            Panel(
                title="MongoDB Connections",
                panel_type="timeseries",
                targets=[
                    Target(
                        expr=f'mongodb_connections{{service="{service_var}",state="current"}}',
                        legend_format="Current connections",
                    )
                ],
                description="Active MongoDB connections",
                unit="short",
                decimals=0,
                grid_pos={"h": 8, "w": 12, "x": 0, "y": 0}
            ),
            Panel(
                title="MongoDB Operations/sec",
                panel_type="timeseries",
                targets=[
                    Target(
                        expr=f'rate(mongodb_operations_total{{service="{service_var}"}}[5m])',
                        legend_format="{{type}} ops",
                    )
                ],
                description="Database operations per second by type",
                unit="ops",
                decimals=1,
                grid_pos={"h": 8, "w": 12, "x": 12, "y": 0}
            ),
            Panel(
                title="MongoDB Query Duration (p95)",
                panel_type="timeseries",
                targets=[
                    Target(
                        expr=f'histogram_quantile(0.95, sum by (le) (rate(mongodb_query_duration_seconds_bucket{{service="{service_var}"}}[5m]))) * 1000',
                        legend_format="p95 query time",
                        ref_id="A"
                    ),
                    Target(
                        expr=f'histogram_quantile(0.99, sum by (le) (rate(mongodb_query_duration_seconds_bucket{{service="{service_var}"}}[5m]))) * 1000',
                        legend_format="p99 query time",
                        ref_id="B"
                    )
                ],
                description="Query execution time percentiles",
                unit="ms",
                decimals=1,
                grid_pos={"h": 8, "w": 12, "x": 0, "y": 8}
            ),
        ]
    
    def get_panels(self, service_var: str = "$service") -> List[Panel]:
        """Get full MongoDB panel set.
        
        For now, returns same as overview. Can be expanded later.
        
        Args:
            service_var: Service variable name
            
        Returns:
            Complete list of MongoDB panels
        """
        return self.get_overview_panels(service_var)
