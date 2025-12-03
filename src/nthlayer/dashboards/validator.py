"""
Dashboard validation using metric discovery.

This module validates dashboard panels against actual discovered metrics,
preventing the creation of panels that query non-existent metrics.
"""

import logging
import re
from typing import Dict, List, Optional, Set

from nthlayer.discovery import DiscoveryResult, MetricDiscoveryClient

from .models import Panel

logger = logging.getLogger(__name__)


class DashboardValidator:
    """Validates dashboard panels against discovered metrics."""
    
    def __init__(self, discovery_client: Optional[MetricDiscoveryClient] = None):
        """
        Initialize validator.
        
        Args:
            discovery_client: Optional discovery client. If None, validation is skipped.
        """
        self.discovery_client = discovery_client
        self._discovery_cache: Dict[str, DiscoveryResult] = {}
    
    def validate_dashboard(
        self,
        service_name: str,
        panels: List[Panel],
        discover_metrics: bool = True
    ) -> tuple[List[Panel], List[str]]:
        """
        Validate all panels in a dashboard against discovered metrics.
        
        Args:
            service_name: Service name to discover metrics for
            panels: List of panels to validate
            discover_metrics: Whether to discover metrics (False for testing)
            
        Returns:
            Tuple of (valid_panels, warnings)
            - valid_panels: Panels that query existing metrics
            - warnings: List of warning messages for invalid panels
        """
        if not self.discovery_client or not discover_metrics:
            logger.debug("Skipping validation (no discovery client or disabled)")
            return panels, []
        
        # Discover metrics for service
        logger.info(f"Discovering metrics for {service_name}...")
        discovery = self._get_discovery_result(service_name)
        
        if not discovery or discovery.total_metrics == 0:
            logger.warning(f"No metrics discovered for {service_name}, skipping validation")
            return panels, [f"No metrics discovered for {service_name} - validation skipped"]
        
        logger.info(f"Discovered {discovery.total_metrics} metrics for {service_name}")
        
        # Extract all discovered metric names
        discovered_metric_names = {m.name for m in discovery.metrics}
        
        # Validate each panel
        valid_panels = []
        warnings = []
        
        for panel in panels:
            is_valid, panel_warnings = self._validate_panel(panel, discovered_metric_names)
            
            if is_valid:
                valid_panels.append(panel)
            else:
                warnings.extend(panel_warnings)
                logger.warning(f"Removing panel '{panel.title}': {', '.join(panel_warnings)}")
        
        logger.info(f"Validation complete: {len(valid_panels)}/{len(panels)} panels valid")
        return valid_panels, warnings
    
    def _get_discovery_result(self, service_name: str) -> Optional[DiscoveryResult]:
        """Get discovery result for service (cached)."""
        if service_name in self._discovery_cache:
            return self._discovery_cache[service_name]
        
        try:
            result = self.discovery_client.discover(f'{{service="{service_name}"}}')
            self._discovery_cache[service_name] = result
            return result
        except Exception as e:
            logger.error(f"Error discovering metrics for {service_name}: {e}")
            return None
    
    def _validate_panel(
        self,
        panel: Panel,
        discovered_metrics: Set[str]
    ) -> tuple[bool, List[str]]:
        """
        Validate a single panel.
        
        Returns:
            Tuple of (is_valid, warnings)
        """
        if not panel.targets:
            return True, []  # Panel with no targets (e.g., row) is valid
        
        warnings = []
        has_valid_target = False
        
        for target in panel.targets:
            expr = target.expr
            if not expr:
                continue
            
            # Extract metric names from PromQL expression
            metrics_in_query = self._extract_metrics_from_expr(expr)
            
            # Check if any metrics in query exist
            missing_metrics = []
            for metric in metrics_in_query:
                if metric not in discovered_metrics:
                    missing_metrics.append(metric)
            
            if missing_metrics:
                warnings.append(
                    f"Panel '{panel.title}' queries non-existent metrics: {', '.join(missing_metrics)}"
                )
            else:
                has_valid_target = True
        
        # Panel is valid if at least one target has all its metrics
        return has_valid_target, warnings
    
    def _extract_metrics_from_expr(self, expr: str) -> Set[str]:
        """
        Extract metric names from a PromQL expression.
        
        Examples:
            'http_requests_total{service="foo"}' -> {'http_requests_total'}
            'rate(http_requests_total[5m])' -> {'http_requests_total'}
            'sum by (le) (rate(http_duration_bucket[5m]))' -> {'http_duration_bucket'}
        """
        # Pattern: metric name is alphanumeric + underscores, followed by { or (
        # Handles: metric_name{...}, rate(metric_name[...]), etc.
        pattern = r'\b([a-z_][a-z0-9_]*)\s*(?:\{|\[)'
        
        metrics = set()
        for match in re.finditer(pattern, expr, re.IGNORECASE):
            metric_name = match.group(1)
            
            # Filter out PromQL functions and aggregations
            promql_keywords = {
                'rate', 'irate', 'sum', 'avg', 'max', 'min', 'count',
                'by', 'without', 'histogram_quantile', 'label_replace',
                'increase', 'delta', 'abs', 'ceil', 'floor', 'round',
                'sort', 'sort_desc', 'topk', 'bottomk', 'time', 'vector'
            }
            
            if metric_name not in promql_keywords:
                metrics.add(metric_name)
        
        return metrics
    
    def get_technology_metrics(self, service_name: str, technology: str) -> List[str]:
        """
        Get all metrics for a specific technology.
        
        Useful for template generators to know which metrics are available.
        
        Args:
            service_name: Service to discover metrics for
            technology: Technology group (e.g., 'postgresql', 'redis')
            
        Returns:
            List of metric names for that technology
        """
        discovery = self._get_discovery_result(service_name)
        if not discovery:
            return []
        
        tech_metrics = discovery.metrics_by_technology.get(technology, [])
        return [m.name for m in tech_metrics]
