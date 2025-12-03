"""Base template class for technology-specific dashboard panels."""

from abc import ABC, abstractmethod
from typing import List

from nthlayer.dashboards.models import Panel


class TechnologyTemplate(ABC):
    """Base class for technology-specific dashboard templates.
    
    Each technology (PostgreSQL, Redis, etc.) implements this to provide
    a set of pre-configured panels for monitoring.
    """
    
    @property
    @abstractmethod
    def name(self) -> str:
        """Technology name."""
        pass
    
    @property
    @abstractmethod
    def display_name(self) -> str:
        """Display name for UI."""
        pass
    
    @abstractmethod
    def get_panels(self, service_name: str = "$service") -> List[Panel]:
        """Get all panels for this technology.
        
        Args:
            service_name: Service name or template variable (default: $service)
            
        Returns:
            List of Panel objects
        """
        pass
    
    def get_overview_panels(self, service_name: str = "$service") -> List[Panel]:
        """Get overview panels (most important metrics).
        
        Subclasses can override to provide a subset of panels for overview dashboards.
        
        Args:
            service_name: Service name or template variable
            
        Returns:
            List of most important panels (typically 2-4)
        """
        # Default: return first 3 panels
        return self.get_panels(service_name)[:3]
