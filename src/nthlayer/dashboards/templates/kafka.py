"""Kafka dashboard template."""

from typing import List

from nthlayer.dashboards.models import Panel, Target
from nthlayer.dashboards.templates.base import TechnologyTemplate


class KafkaTemplate(TechnologyTemplate):
    """Template for Kafka panels."""
    
    @property
    def name(self) -> str:
        return "kafka"
    
    @property
    def display_name(self) -> str:
        return "Apache Kafka"
    
    def get_overview_panels(self, service_var: str = "$service") -> List[Panel]:
        """Get overview Kafka panels.
        
        Args:
            service_var: Service variable name (default: $service)
            
        Returns:
            List of Kafka monitoring panels
        """
        return [
            Panel(
                title="Kafka Consumer Lag",
                panel_type="timeseries",
                targets=[
                    Target(
                        expr=f'kafka_consumer_lag_seconds{{service="{service_var}"}}',
                        legend_format="{{topic}} lag",
                    )
                ],
                description="Consumer lag in seconds behind latest messages",
                unit="s",
                decimals=2,
                grid_pos={"h": 8, "w": 12, "x": 0, "y": 0}
            ),
            Panel(
                title="Kafka Throughput",
                panel_type="timeseries",
                targets=[
                    Target(
                        expr=f'kafka_consumer_records_per_second{{service="{service_var}"}}',
                        legend_format="{{topic}} records/sec",
                    )
                ],
                description="Records consumed per second",
                unit="rps",
                decimals=1,
                grid_pos={"h": 8, "w": 12, "x": 12, "y": 0}
            ),
            Panel(
                title="Kafka Offset Progress",
                panel_type="timeseries",
                targets=[
                    Target(
                        expr=f'rate(kafka_consumer_offset_total{{service="{service_var}"}}[5m])',
                        legend_format="{{topic}}-p{{partition}}",
                    )
                ],
                description="Message offset progression per partition",
                unit="msgs/s",
                decimals=1,
                grid_pos={"h": 8, "w": 12, "x": 0, "y": 8}
            ),
        ]
    
    def get_panels(self, service_var: str = "$service") -> List[Panel]:
        """Get full Kafka panel set.
        
        For now, returns same as overview. Can be expanded later.
        
        Args:
            service_var: Service variable name
            
        Returns:
            Complete list of Kafka panels
        """
        return self.get_overview_panels(service_var)
