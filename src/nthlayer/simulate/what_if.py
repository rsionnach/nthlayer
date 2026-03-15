"""What-if scenario parsing and application."""

from __future__ import annotations

import copy
from typing import Any

from nthlayer.simulate.models import (
    DependencyModel,
    ServiceFailureModel,
    derive_failure_model,
)


def parse_what_if(scenario_str: str) -> dict[str, Any]:
    """Parse a what-if scenario string into a structured dict.

    Formats:
    - redundant:<service> — add redundant instance (squares failure prob)
    - improve:<service>:availability:<value> — improve availability target
    - remove:<service> — remove dependency
    - degrade:<service>:<factor> — change critical dep to non-critical
    """
    parts = scenario_str.split(":")

    if parts[0] == "redundant" and len(parts) == 2:
        return {"type": "redundant", "service": parts[1]}
    elif parts[0] == "improve" and len(parts) == 4:
        return {
            "type": "improve",
            "service": parts[1],
            "metric": parts[2],
            "value": float(parts[3]),
        }
    elif parts[0] == "remove" and len(parts) == 2:
        return {"type": "remove", "service": parts[1]}
    elif parts[0] == "degrade" and len(parts) == 3:
        return {
            "type": "degrade",
            "service": parts[1],
            "factor": float(parts[2]),
        }
    else:
        raise ValueError(
            f"Unknown what-if scenario: '{scenario_str}'. "
            f"Valid formats: redundant:<svc>, improve:<svc>:availability:<val>, "
            f"remove:<svc>, degrade:<svc>:<factor>"
        )


def apply_scenario(
    services: list[ServiceFailureModel],
    dependencies: list[DependencyModel],
    scenario: dict[str, Any],
) -> tuple[list[ServiceFailureModel], list[DependencyModel]]:
    """Apply a what-if scenario, returning modified copies."""
    new_services = copy.deepcopy(services)
    new_deps = copy.deepcopy(dependencies)

    stype = scenario["type"]
    svc_name = scenario["service"]

    if stype == "redundant":
        # Active-active: effective availability = 1 - (1 - A)^2
        for i, s in enumerate(new_services):
            if s.name == svc_name:
                p_fail = 1.0 - s.availability_target
                new_avail = 1.0 - (p_fail * p_fail)
                new_services[i] = derive_failure_model(s.name, new_avail, s.mttr_hours)
                break

    elif stype == "improve":
        value = scenario["value"]
        for i, s in enumerate(new_services):
            if s.name == svc_name:
                new_services[i] = derive_failure_model(s.name, value, s.mttr_hours)
                break

    elif stype == "remove":
        new_deps = [d for d in new_deps if d.to_service != svc_name]

    elif stype == "degrade":
        factor = scenario["factor"]
        for i, d in enumerate(new_deps):
            if d.to_service == svc_name and d.critical:
                new_deps[i] = DependencyModel(
                    from_service=d.from_service,
                    to_service=d.to_service,
                    critical=False,
                    degradation_factor=factor,
                )

    return new_services, new_deps
