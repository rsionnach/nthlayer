"""
OpenSLO YAML parser.

Parses SLO definitions from OpenSLO-compliant YAML files.
Specification: https://github.com/OpenSLO/OpenSLO
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from nthlayer.slos.models import SLO, TimeWindow, TimeWindowType


class OpenSLOParserError(Exception):
    """Raised when parsing OpenSLO YAML fails."""


def parse_slo_file(file_path: str | Path) -> SLO:
    """
    Parse an OpenSLO YAML file into an SLO object.
    
    Args:
        file_path: Path to the OpenSLO YAML file
        
    Returns:
        SLO object
        
    Raises:
        OpenSLOParserError: If parsing fails
    """
    try:
        with open(file_path) as f:
            data = yaml.safe_load(f)
    except FileNotFoundError as exc:
        raise OpenSLOParserError(f"SLO file not found: {file_path}") from exc
    except yaml.YAMLError as exc:
        raise OpenSLOParserError(f"Invalid YAML in {file_path}: {exc}") from exc
    
    return parse_slo_dict(data)


def parse_slo_dict(data: dict[str, Any]) -> SLO:
    """
    Parse OpenSLO dictionary into an SLO object.
    
    Args:
        data: Dictionary from OpenSLO YAML
        
    Returns:
        SLO object
        
    Raises:
        OpenSLOParserError: If required fields are missing
    """
    # Validate apiVersion and kind
    api_version = data.get("apiVersion", "")
    kind = data.get("kind", "")
    
    if not api_version.startswith("openslo/"):
        raise OpenSLOParserError(f"Invalid apiVersion: {api_version}, expected openslo/v1")
    
    if kind != "SLO":
        raise OpenSLOParserError(f"Invalid kind: {kind}, expected SLO")
    
    # Extract metadata
    metadata = data.get("metadata", {})
    if not metadata:
        raise OpenSLOParserError("Missing required field: metadata")
    
    slo_id = metadata.get("name")
    if not slo_id:
        raise OpenSLOParserError("Missing required field: metadata.name")
    
    # Extract spec
    spec = data.get("spec", {})
    if not spec:
        raise OpenSLOParserError("Missing required field: spec")
    
    service = spec.get("service")
    if not service:
        raise OpenSLOParserError("Missing required field: spec.service")
    
    # Parse objectives
    objectives = spec.get("objectives", [])
    if not objectives:
        raise OpenSLOParserError("Missing required field: spec.objectives")
    
    objective = objectives[0]  # Use first objective
    target = objective.get("target")
    if target is None:
        raise OpenSLOParserError("Missing required field: spec.objectives[0].target")
    
    # Parse indicator (Prometheus query)
    indicator = objective.get("indicator", {})
    indicator_spec = indicator.get("spec", {})
    query = indicator_spec.get("query", "")
    
    if not query:
        raise OpenSLOParserError("Missing required field: spec.objectives[0].indicator.spec.query")
    
    # Parse time window
    time_windows = spec.get("timeWindow", [])
    if not time_windows:
        raise OpenSLOParserError("Missing required field: spec.timeWindow")
    
    window_data = time_windows[0]  # Use first time window
    duration = window_data.get("duration")
    if not duration:
        raise OpenSLOParserError("Missing required field: spec.timeWindow[0].duration")
    
    window_type_str = window_data.get("type", "rolling")
    try:
        window_type = TimeWindowType(window_type_str)
    except ValueError as exc:
        raise OpenSLOParserError(f"Invalid time window type: {window_type_str}") from exc
    
    time_window = TimeWindow(duration=duration, type=window_type)
    
    # Create SLO object
    return SLO(
        id=slo_id,
        service=service,
        name=metadata.get("displayName", slo_id),
        description=spec.get("description", ""),
        target=target,
        time_window=time_window,
        query=query,
        owner=metadata.get("labels", {}).get("owner"),
        labels=metadata.get("labels", {}),
    )


def validate_slo(slo: SLO) -> list[str]:
    """
    Validate an SLO object.
    
    Args:
        slo: SLO to validate
        
    Returns:
        List of validation errors (empty if valid)
    """
    errors = []
    
    # Validate target
    if not (0.0 < slo.target <= 1.0):
        errors.append(f"Invalid target: {slo.target}, must be between 0.0 and 1.0")
    
    # Validate time window duration format
    try:
        slo.time_window.to_timedelta()
    except ValueError as exc:
        errors.append(f"Invalid time window duration: {exc}")
    
    # Validate query is not empty
    if not slo.query.strip():
        errors.append("Prometheus query cannot be empty")
    
    # Validate service name
    if not slo.service.strip():
        errors.append("Service name cannot be empty")
    
    return errors
