"""
Prometheus metric discovery client.

Queries Prometheus to discover actual metrics for a service, inspired by autograf.
"""

import logging
from typing import Dict, List, Optional

import requests
from requests.auth import HTTPBasicAuth

from .classifier import MetricClassifier
from .models import DiscoveredMetric, DiscoveryResult, MetricType

logger = logging.getLogger(__name__)


class MetricDiscoveryClient:
    """Client for discovering metrics from Prometheus."""
    
    def __init__(
        self,
        prometheus_url: str,
        username: Optional[str] = None,
        password: Optional[str] = None,
        bearer_token: Optional[str] = None,
    ):
        """
        Initialize discovery client.
        
        Args:
            prometheus_url: Prometheus server URL
            username: Optional HTTP basic auth username
            password: Optional HTTP basic auth password
            bearer_token: Optional bearer token for authentication
        """
        self.prometheus_url = prometheus_url.rstrip('/')
        self.auth = HTTPBasicAuth(username, password) if username and password else None
        self.headers = {'Authorization': f'Bearer {bearer_token}'} if bearer_token else {}
        self.classifier = MetricClassifier()
    
    def discover(self, selector: str) -> DiscoveryResult:
        """
        Discover all metrics matching the given selector.
        
        Args:
            selector: Prometheus selector (e.g., '{service="payment-api"}')
            
        Returns:
            DiscoveryResult with all discovered metrics
        """
        logger.info(f"Discovering metrics for selector: {selector}")
        
        # Step 1: Get all metric names
        metric_names = self._get_metric_names(selector)
        logger.info(f"Found {len(metric_names)} unique metrics")
        
        # Step 2: Get metadata for each metric
        metrics = []
        for name in metric_names:
            metric = self._discover_metric(name, selector)
            if metric:
                metrics.append(metric)
        
        # Step 3: Classify and group
        classified_metrics = [self.classifier.classify(m) for m in metrics]
        
        # Step 4: Build result with groupings
        result = DiscoveryResult(
            service=self._extract_service_from_selector(selector),
            total_metrics=len(classified_metrics),
            metrics=classified_metrics,
        )
        
        # Group by technology
        for metric in classified_metrics:
            tech = metric.technology
            if tech not in result.metrics_by_technology:
                result.metrics_by_technology[tech] = []
            result.metrics_by_technology[tech].append(metric)
        
        # Group by type
        for metric in classified_metrics:
            mtype = metric.type
            if mtype not in result.metrics_by_type:
                result.metrics_by_type[mtype] = []
            result.metrics_by_type[mtype].append(metric)
        
        logger.info(f"Discovered {result.total_metrics} metrics across {len(result.metrics_by_technology)} technologies")
        return result
    
    def _get_metric_names(self, selector: str) -> List[str]:
        """
        Query Prometheus for all metric names matching selector.
        
        Uses the series endpoint to get all metrics matching the selector,
        then extracts unique metric names.
        
        For POC, can also parse /metrics endpoint directly if Prometheus API unavailable.
        """
        # Try Prometheus API first
        url = f"{self.prometheus_url}/api/v1/series"
        if not url.startswith('http'):
            url = f"http://{url}/api/v1/series"
        params = {'match[]': selector}
        
        # Check if this is a /metrics endpoint instead
        if '/metrics' in self.prometheus_url or 'fly.dev' in self.prometheus_url:
            return self._get_metrics_from_endpoint(selector)
        
        
        try:
            response = requests.get(
                url,
                params=params,
                auth=self.auth,
                headers=self.headers,
                timeout=30
            )
            response.raise_for_status()
            data = response.json()
            
            if data.get('status') != 'success':
                logger.error(f"Prometheus API error: {data}")
                return []
            
            # Extract unique metric names
            metric_names = set()
            for series in data.get('data', []):
                if '__name__' in series:
                    metric_names.add(series['__name__'])
            
            return sorted(metric_names)
            
        except Exception as e:
            logger.error(f"Error querying Prometheus series: {e}")
            return []
    
    def _discover_metric(self, metric_name: str, selector: str) -> Optional[DiscoveredMetric]:
        """
        Discover detailed information about a specific metric.
        
        Queries Prometheus metadata API to get type and help text.
        """
        # Get metadata
        metadata = self._get_metric_metadata(metric_name)
        
        # Get label values
        labels = self._get_label_values(metric_name, selector)
        
        return DiscoveredMetric(
            name=metric_name,
            type=MetricType(metadata.get('type', 'unknown')),
            help_text=metadata.get('help'),
            labels=labels,
        )
    
    def _get_metric_metadata(self, metric_name: str) -> Dict:
        """
        Query Prometheus metadata API for metric type and help text.
        """
        url = f"{self.prometheus_url}/api/v1/metadata"
        params = {'metric': metric_name}
        
        try:
            response = requests.get(
                url,
                params=params,
                auth=self.auth,
                headers=self.headers,
                timeout=10
            )
            response.raise_for_status()
            data = response.json()
            
            if data.get('status') == 'success':
                metric_data = data.get('data', {}).get(metric_name, [])
                if metric_data:
                    return metric_data[0]
            
            return {}
            
        except Exception as e:
            logger.debug(f"Error getting metadata for {metric_name}: {e}")
            return {}
    
    def _get_label_values(self, metric_name: str, selector: str) -> Dict[str, List[str]]:
        """
        Get all label values for a metric.
        
        Queries the series endpoint to get all label combinations.
        """
        url = f"{self.prometheus_url}/api/v1/series"
        # Combine metric name with selector
        full_selector = f'{metric_name}{selector}'
        params = {'match[]': full_selector}
        
        try:
            response = requests.get(
                url,
                params=params,
                auth=self.auth,
                headers=self.headers,
                timeout=10
            )
            response.raise_for_status()
            data = response.json()
            
            if data.get('status') != 'success':
                return {}
            
            # Collect all unique label values
            labels: Dict[str, set] = {}
            for series in data.get('data', []):
                for label, value in series.items():
                    if label == '__name__':
                        continue
                    if label not in labels:
                        labels[label] = set()
                    labels[label].add(value)
            
            # Convert sets to sorted lists
            return {k: sorted(v) for k, v in labels.items()}
            
        except Exception as e:
            logger.debug(f"Error getting labels for {metric_name}: {e}")
            return {}
    
    def _get_metrics_from_endpoint(self, selector: str) -> List[str]:
        """
        Parse /metrics endpoint directly (for POC without Prometheus).
        
        This is a fallback for testing against Fly.io metrics endpoint.
        """
        service = self._extract_service_from_selector(selector)
        url = f"{self.prometheus_url}/metrics"
        
        # If selector is empty or '{}', get ALL metrics
        filter_by_service = service and service != "unknown"
        
        try:
            response = requests.get(
                url,
                auth=self.auth,
                headers=self.headers,
                timeout=30
            )
            response.raise_for_status()
            
            # Parse Prometheus text format
            metric_names = set()
            for line in response.text.split('\n'):
                if not line or line.startswith('#'):
                    continue
                
                # Check if line contains our service (if filtering)
                if filter_by_service and f'service="{service}"' not in line:
                    continue
                
                # Extract metric name (before { or space)
                if '{' in line:
                    metric_name = line.split('{')[0]
                    metric_names.add(metric_name)
                elif ' ' in line:
                    # Handle metrics without labels
                    metric_name = line.split(' ')[0]
                    metric_names.add(metric_name)
            
            logger.info(f"Parsed {len(metric_names)} metrics from /metrics endpoint")
            return sorted(metric_names)
            
        except Exception as e:
            logger.error(f"Error parsing /metrics endpoint: {e}")
            return []
    
    def _extract_service_from_selector(self, selector: str) -> str:
        """Extract service name from selector string."""
        # Simple extraction: {service="name"} -> name
        import re
        match = re.search(r'service="([^"]+)"', selector)
        if match:
            return match.group(1)
        return "unknown"
