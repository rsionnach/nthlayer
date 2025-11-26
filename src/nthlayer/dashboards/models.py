"""Grafana dashboard data models.

Provides typed Python models for Grafana dashboard JSON structures.
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class Target:
    """Prometheus query target for a panel."""
    
    expr: str  # PromQL expression
    legend_format: str = "{{label}}"
    ref_id: str = "A"
    interval: Optional[str] = None
    instant: bool = False
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to Grafana JSON format."""
        result = {
            "expr": self.expr,
            "legendFormat": self.legend_format,
            "refId": self.ref_id,
        }
        if self.interval:
            result["interval"] = self.interval
        if self.instant:
            result["instant"] = True
        return result


@dataclass
class Panel:
    """Grafana dashboard panel."""
    
    title: str
    targets: List[Target]
    panel_type: str = "timeseries"  # timeseries, gauge, stat, table
    description: Optional[str] = None
    unit: Optional[str] = None
    decimals: Optional[int] = None
    min: Optional[float] = None
    max: Optional[float] = None
    thresholds: Optional[List[Dict[str, Any]]] = None
    grid_pos: Optional[Dict[str, int]] = None
    
    # Internal tracking
    id: int = 0
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to Grafana JSON format."""
        result = {
            "id": self.id,
            "title": self.title,
            "type": self.panel_type,
            "targets": [t.to_dict() for t in self.targets],
            "gridPos": self.grid_pos or {"h": 8, "w": 12, "x": 0, "y": 0},
        }
        
        if self.description:
            result["description"] = self.description
        
        # Field config (units, decimals, thresholds)
        field_config = {}
        defaults = {}
        
        if self.unit:
            defaults["unit"] = self.unit
        if self.decimals is not None:
            defaults["decimals"] = self.decimals
        if self.min is not None:
            defaults["min"] = self.min
        if self.max is not None:
            defaults["max"] = self.max
        if self.thresholds:
            defaults["thresholds"] = {
                "mode": "absolute",
                "steps": self.thresholds
            }
        
        if defaults:
            field_config["defaults"] = defaults
            result["fieldConfig"] = field_config
        
        # Panel-specific options
        if self.panel_type == "timeseries":
            result["options"] = {
                "tooltip": {"mode": "multi"},
                "legend": {"displayMode": "list", "placement": "bottom"}
            }
        elif self.panel_type == "gauge":
            result["options"] = {
                "showThresholdLabels": False,
                "showThresholdMarkers": True
            }
        elif self.panel_type == "stat":
            result["options"] = {
                "graphMode": "area",
                "colorMode": "value",
                "orientation": "auto"
            }
        
        return result


@dataclass
class Row:
    """Dashboard row (container for panels)."""
    
    title: str
    collapsed: bool = False
    panels: List[Panel] = field(default_factory=list)
    
    # Internal tracking
    id: int = 0
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to Grafana JSON format."""
        return {
            "id": self.id,
            "type": "row",
            "title": self.title,
            "collapsed": self.collapsed,
            "gridPos": {"h": 1, "w": 24, "x": 0, "y": 0},
            "panels": []  # Panels are siblings, not children in JSON
        }


@dataclass
class TemplateVariable:
    """Dashboard template variable."""
    
    name: str
    label: str
    query: str
    var_type: str = "query"  # query, custom, interval, datasource
    datasource: Optional[str] = None
    multi: bool = False
    include_all: bool = False
    current: Optional[Dict[str, Any]] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to Grafana JSON format."""
        result = {
            "name": self.name,
            "label": self.label,
            "type": self.var_type,
            "query": self.query,
            "multi": self.multi,
            "includeAll": self.include_all,
        }
        
        if self.datasource:
            result["datasource"] = self.datasource
        if self.current:
            result["current"] = self.current
        
        return result


@dataclass
class Dashboard:
    """Complete Grafana dashboard."""
    
    title: str
    panels: List[Panel] = field(default_factory=list)
    rows: List[Row] = field(default_factory=list)
    template_variables: List[TemplateVariable] = field(default_factory=list)
    
    # Metadata
    uid: Optional[str] = None
    description: Optional[str] = None
    tags: List[str] = field(default_factory=list)
    timezone: str = "browser"
    editable: bool = True
    
    # Time settings
    time_from: str = "now-6h"
    time_to: str = "now"
    refresh: str = "30s"
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to Grafana JSON format."""
        # Assign panel IDs and grid positions
        panel_id = 1
        y_pos = 0
        
        all_panels = []
        
        # Add row panels and their contents
        for row in self.rows:
            row.id = panel_id
            panel_id += 1
            
            # Add row itself
            row_dict = row.to_dict()
            row_dict["gridPos"]["y"] = y_pos
            all_panels.append(row_dict)
            y_pos += 1
            
            # Add panels in this row
            x_pos = 0
            for panel in row.panels:
                panel.id = panel_id
                panel_id += 1
                
                panel_dict = panel.to_dict()
                w = panel_dict["gridPos"]["w"]
                h = panel_dict["gridPos"]["h"]
                panel_dict["gridPos"] = {"h": h, "w": w, "x": x_pos, "y": y_pos}
                all_panels.append(panel_dict)
                
                x_pos += w
                if x_pos >= 24:
                    x_pos = 0
                    y_pos += h
            
            # Move to next row
            if row.panels and x_pos > 0:
                y_pos += 8  # Default panel height
        
        # Add standalone panels (not in rows)
        x_pos = 0
        for panel in self.panels:
            panel.id = panel_id
            panel_id += 1
            
            panel_dict = panel.to_dict()
            w = panel_dict["gridPos"]["w"]
            h = panel_dict["gridPos"]["h"]
            panel_dict["gridPos"] = {"h": h, "w": w, "x": x_pos, "y": y_pos}
            all_panels.append(panel_dict)
            
            x_pos += w
            if x_pos >= 24:
                x_pos = 0
                y_pos += h
        
        # Build dashboard JSON
        dashboard = {
            "title": self.title,
            "panels": all_panels,
            "editable": self.editable,
            "timezone": self.timezone,
            "tags": self.tags,
            "time": {
                "from": self.time_from,
                "to": self.time_to
            },
            "refresh": self.refresh,
            "schemaVersion": 38,
            "version": 0,
        }
        
        if self.uid:
            dashboard["uid"] = self.uid
        if self.description:
            dashboard["description"] = self.description
        
        # Add template variables
        if self.template_variables:
            dashboard["templating"] = {
                "list": [tv.to_dict() for tv in self.template_variables]
            }
        
        return dashboard
    
    def to_grafana_payload(self) -> Dict[str, Any]:
        """Convert to Grafana API payload format."""
        return {
            "dashboard": self.to_dict(),
            "overwrite": True,
            "message": "Generated by NthLayer"
        }
