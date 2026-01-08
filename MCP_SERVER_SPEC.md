# NthLayer MCP Server Specification

## Overview

**Feature Name:** NthLayer MCP Server
**Status:** Proposed
**Target Release:** v0.5.0 (after dependency discovery)
**Estimated Effort:** 2-3 days

### What is MCP?

Model Context Protocol (MCP) is Anthropic's open standard for connecting AI assistants to external tools and data sources. It provides a standardized way for LLMs to:

- **Call tools** — Execute functions and get results
- **Read resources** — Access structured data
- **Use prompts** — Get pre-defined prompt templates

MCP Documentation: https://modelcontextprotocol.io/

### Why MCP for NthLayer?

An MCP server transforms NthLayer from a CLI tool into an **AI-powered SRE advisor**:

| Without MCP | With MCP |
|-------------|----------|
| Human runs `nthlayer drift payment-api` | AI runs drift check when discussing reliability |
| Human interprets output | AI interprets and recommends actions |
| Human correlates across services | AI synthesizes portfolio-wide insights |
| Manual, command-by-command | Conversational, context-aware |

**Use cases:**
- "Is payment-api healthy?" → AI checks drift, dependencies, ownership
- "What's our reliability posture?" → AI queries portfolio, identifies risks
- "Should we deploy this PR?" → AI validates SLO feasibility
- "Who should I page if user-service degrades?" → AI returns ownership + blast radius

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              AI Assistant                                   │
│                        (Claude, GPT, etc.)                                  │
└─────────────────────────────────────┬───────────────────────────────────────┘
                                      │ MCP Protocol
                                      │ (JSON-RPC over stdio/SSE)
                                      ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                           NthLayer MCP Server                               │
│                                                                             │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐        │
│  │   Tools     │  │  Resources  │  │   Prompts   │  │   Config    │        │
│  │             │  │             │  │             │  │             │        │
│  │ • drift     │  │ • service   │  │ • incident  │  │ • prom URL  │        │
│  │ • validate  │  │ • portfolio │  │ • review    │  │ • providers │        │
│  │ • blast     │  │ • graph     │  │ • capacity  │  │ • thresholds│        │
│  │ • deps      │  │             │  │             │  │             │        │
│  │ • ownership │  │             │  │             │  │             │        │
│  └─────────────┘  └─────────────┘  └─────────────┘  └─────────────┘        │
│                                      │                                      │
└──────────────────────────────────────┼──────────────────────────────────────┘
                                       │
                                       ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                           NthLayer Core Library                             │
│                                                                             │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐        │
│  │   Drift     │  │ Dependencies│  │  Ownership  │  │  Portfolio  │        │
│  │  Analyzer   │  │  Discovery  │  │  Resolver   │  │  Aggregator │        │
│  └─────────────┘  └─────────────┘  └─────────────┘  └─────────────┘        │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
                                       │
                                       ▼
                    ┌─────────────────────────────────┐
                    │         Data Sources            │
                    │  Prometheus │ Consul │ Backstage│
                    └─────────────────────────────────┘
```

---

## Dependencies

```toml
# pyproject.toml
[project.optional-dependencies]
mcp = [
    "mcp>=1.0.0",                  # MCP Python SDK
    "httpx>=0.25.0",               # Async HTTP (for SSE transport)
]
```

MCP Python SDK: https://github.com/modelcontextprotocol/python-sdk

---

## Server Implementation

### Entry Point

```python
# src/nthlayer/mcp/server.py

"""
NthLayer MCP Server

Exposes reliability intelligence to AI assistants via Model Context Protocol.

Usage:
    # stdio transport (for Claude Desktop, etc.)
    nthlayer mcp serve

    # SSE transport (for web clients)
    nthlayer mcp serve --transport sse --port 8080
"""

import asyncio
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.server.sse import SseServerTransport

from nthlayer.mcp.tools import register_tools
from nthlayer.mcp.resources import register_resources
from nthlayer.mcp.prompts import register_prompts
from nthlayer.mcp.context import NthLayerContext


def create_server() -> Server:
    """Create and configure the MCP server."""
    server = Server("nthlayer")

    # Initialize NthLayer context (shared state)
    context = NthLayerContext.from_config()

    # Register capabilities
    register_tools(server, context)
    register_resources(server, context)
    register_prompts(server, context)

    return server


async def run_stdio():
    """Run server with stdio transport."""
    server = create_server()
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())


async def run_sse(port: int = 8080):
    """Run server with SSE transport."""
    from starlette.applications import Starlette
    from starlette.routing import Route
    import uvicorn

    server = create_server()
    transport = SseServerTransport("/messages")

    async def handle_sse(request):
        async with transport.connect_sse(
            request.scope, request.receive, request._send
        ) as streams:
            await server.run(
                streams[0], streams[1], server.create_initialization_options()
            )

    app = Starlette(routes=[
        Route("/sse", endpoint=handle_sse),
    ])

    config = uvicorn.Config(app, host="0.0.0.0", port=port)
    server = uvicorn.Server(config)
    await server.serve()


# CLI entry point
def main():
    import argparse

    parser = argparse.ArgumentParser(description="NthLayer MCP Server")
    parser.add_argument("--transport", choices=["stdio", "sse"], default="stdio")
    parser.add_argument("--port", type=int, default=8080)
    args = parser.parse_args()

    if args.transport == "stdio":
        asyncio.run(run_stdio())
    else:
        asyncio.run(run_sse(args.port))


if __name__ == "__main__":
    main()
```

### Shared Context

```python
# src/nthlayer/mcp/context.py

"""
Shared context for MCP server operations.
"""

from dataclasses import dataclass, field
from pathlib import Path

from nthlayer.drift.analyzer import DriftAnalyzer
from nthlayer.dependencies.discovery import DiscoveryOrchestrator
from nthlayer.identity.ownership import OwnershipResolver
from nthlayer.identity.resolver import IdentityResolver
from nthlayer.slos.collector import SLOCollector
from nthlayer.config import load_config


@dataclass
class NthLayerContext:
    """
    Shared context containing initialized NthLayer components.

    Lazily initializes components on first use to keep startup fast.
    """

    config: dict = field(default_factory=dict)

    # Lazy-initialized components
    _drift_analyzer: DriftAnalyzer | None = None
    _discovery: DiscoveryOrchestrator | None = None
    _ownership: OwnershipResolver | None = None
    _identity: IdentityResolver | None = None
    _slo_collector: SLOCollector | None = None

    @classmethod
    def from_config(cls, config_path: Path | None = None) -> "NthLayerContext":
        """Load context from nthlayer.yaml config."""
        config = load_config(config_path)
        return cls(config=config)

    @property
    def drift_analyzer(self) -> DriftAnalyzer:
        if self._drift_analyzer is None:
            self._drift_analyzer = DriftAnalyzer(
                prometheus_url=self.config.get("prometheus", {}).get("url"),
            )
        return self._drift_analyzer

    @property
    def discovery(self) -> DiscoveryOrchestrator:
        if self._discovery is None:
            from nthlayer.dependencies.providers import create_providers_from_config
            providers = create_providers_from_config(self.config.get("discovery", {}))
            self._discovery = DiscoveryOrchestrator(
                providers=providers,
                identity_resolver=self.identity,
            )
        return self._discovery

    @property
    def ownership(self) -> OwnershipResolver:
        if self._ownership is None:
            from nthlayer.identity.ownership_providers import create_ownership_providers
            providers = create_ownership_providers(self.config.get("ownership", {}))
            self._ownership = OwnershipResolver(providers=providers)
        return self._ownership

    @property
    def identity(self) -> IdentityResolver:
        if self._identity is None:
            self._identity = IdentityResolver()
        return self._identity

    @property
    def slo_collector(self) -> SLOCollector:
        if self._slo_collector is None:
            self._slo_collector = SLOCollector(
                prometheus_url=self.config.get("prometheus", {}).get("url"),
            )
        return self._slo_collector
```

---

## Tools

Tools are functions the AI can call. Each tool has a name, description, input schema, and returns structured output.

### Tool Registration

```python
# src/nthlayer/mcp/tools.py

"""
MCP Tools for NthLayer.

Tools allow AI assistants to execute NthLayer operations.
"""

from mcp.server import Server
from mcp.types import Tool, TextContent
from pydantic import BaseModel, Field

from nthlayer.mcp.context import NthLayerContext


def register_tools(server: Server, context: NthLayerContext):
    """Register all NthLayer tools with the MCP server."""

    @server.list_tools()
    async def list_tools() -> list[Tool]:
        return [
            Tool(
                name="nthlayer_drift_check",
                description="Check error budget drift for a service. Detects gradual SLO degradation before alerts fire.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "service": {
                            "type": "string",
                            "description": "Service name to check drift for"
                        },
                        "window": {
                            "type": "string",
                            "description": "Analysis window (e.g., '7d', '14d', '30d')",
                            "default": "30d"
                        },
                        "slo": {
                            "type": "string",
                            "description": "Specific SLO to check (optional, checks all if not specified)"
                        }
                    },
                    "required": ["service"]
                }
            ),
            Tool(
                name="nthlayer_validate_slo",
                description="Validate if an SLO target is mathematically achievable given the service's dependency chain.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "service": {
                            "type": "string",
                            "description": "Service name to validate"
                        },
                        "target": {
                            "type": "number",
                            "description": "SLO target as decimal (e.g., 0.999 for 99.9%)"
                        }
                    },
                    "required": ["service"]
                }
            ),
            Tool(
                name="nthlayer_blast_radius",
                description="Analyze impact if a service degrades. Returns affected services, teams, and estimated SLO impact.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "service": {
                            "type": "string",
                            "description": "Service to analyze blast radius for"
                        },
                        "degradation": {
                            "type": "number",
                            "description": "Simulated availability (e.g., 0.99 for 99%)",
                            "default": 0.99
                        },
                        "duration_hours": {
                            "type": "number",
                            "description": "Duration of degradation in hours",
                            "default": 1
                        }
                    },
                    "required": ["service"]
                }
            ),
            Tool(
                name="nthlayer_get_dependencies",
                description="Get upstream and downstream dependencies for a service.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "service": {
                            "type": "string",
                            "description": "Service name"
                        },
                        "direction": {
                            "type": "string",
                            "enum": ["upstream", "downstream", "both"],
                            "description": "Which dependencies to return",
                            "default": "both"
                        },
                        "depth": {
                            "type": "integer",
                            "description": "How many levels deep to traverse",
                            "default": 2
                        }
                    },
                    "required": ["service"]
                }
            ),
            Tool(
                name="nthlayer_get_ownership",
                description="Get ownership information for a service including team, contacts, and escalation paths.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "service": {
                            "type": "string",
                            "description": "Service name"
                        }
                    },
                    "required": ["service"]
                }
            ),
            Tool(
                name="nthlayer_portfolio_status",
                description="Get reliability status across all services. Identifies services with drift, low budgets, or dependency risks.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "tier": {
                            "type": "string",
                            "enum": ["critical", "standard", "low", "all"],
                            "description": "Filter by service tier",
                            "default": "all"
                        },
                        "include_drift": {
                            "type": "boolean",
                            "description": "Include drift analysis (slower)",
                            "default": False
                        },
                        "include_dependencies": {
                            "type": "boolean",
                            "description": "Include dependency risk analysis",
                            "default": False
                        }
                    }
                }
            ),
            Tool(
                name="nthlayer_check_deploy",
                description="Check if a deployment should proceed. Validates current reliability state against deployment gates.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "service": {
                            "type": "string",
                            "description": "Service being deployed"
                        },
                        "include_drift": {
                            "type": "boolean",
                            "description": "Include drift in deployment gate",
                            "default": True
                        },
                        "include_dependencies": {
                            "type": "boolean",
                            "description": "Check dependency health",
                            "default": True
                        }
                    },
                    "required": ["service"]
                }
            ),
        ]

    @server.call_tool()
    async def call_tool(name: str, arguments: dict) -> list[TextContent]:
        """Route tool calls to implementations."""

        if name == "nthlayer_drift_check":
            result = await _drift_check(context, **arguments)
        elif name == "nthlayer_validate_slo":
            result = await _validate_slo(context, **arguments)
        elif name == "nthlayer_blast_radius":
            result = await _blast_radius(context, **arguments)
        elif name == "nthlayer_get_dependencies":
            result = await _get_dependencies(context, **arguments)
        elif name == "nthlayer_get_ownership":
            result = await _get_ownership(context, **arguments)
        elif name == "nthlayer_portfolio_status":
            result = await _portfolio_status(context, **arguments)
        elif name == "nthlayer_check_deploy":
            result = await _check_deploy(context, **arguments)
        else:
            result = {"error": f"Unknown tool: {name}"}

        import json
        return [TextContent(type="text", text=json.dumps(result, indent=2, default=str))]


# Tool implementations

async def _drift_check(
    context: NthLayerContext,
    service: str,
    window: str = "30d",
    slo: str | None = None,
) -> dict:
    """Check drift for a service."""
    try:
        results = await context.drift_analyzer.analyze(
            service=service,
            window=window,
            slo_filter=slo,
        )

        return {
            "service": service,
            "window": window,
            "analyzed_at": results.analyzed_at.isoformat(),
            "slos": [
                {
                    "name": r.slo_name,
                    "current_budget": f"{r.metrics.current_budget:.2%}",
                    "trend": f"{r.metrics.slope_per_week:+.3%}/week",
                    "pattern": r.pattern.value,
                    "severity": r.severity.value,
                    "projection": {
                        "days_until_exhaustion": r.projection.days_until_exhaustion,
                        "budget_30d": f"{r.projection.projected_budget_30d:.2%}",
                    },
                    "recommendation": r.recommendation,
                }
                for r in results.slo_results
            ],
            "overall_severity": results.overall_severity.value,
            "summary": results.summary,
        }
    except Exception as e:
        return {"error": str(e), "service": service}


async def _validate_slo(
    context: NthLayerContext,
    service: str,
    target: float | None = None,
) -> dict:
    """Validate SLO feasibility against dependency chain."""
    try:
        # Get service config for target if not provided
        if target is None:
            # Load from service.yaml
            target = 0.999  # Default, would load from config

        # Get dependencies
        deps = await context.discovery.discover_for_service(service)

        # Calculate serial availability
        dep_availabilities = []
        for dep in deps:
            # Get dependency's SLO or assume 99.9%
            dep_availability = dep.metadata.get("availability", 0.999)
            dep_availabilities.append({
                "service": dep.target.canonical_name,
                "availability": dep_availability,
            })

        serial_availability = 1.0
        for d in dep_availabilities:
            serial_availability *= d["availability"]

        feasible = serial_availability >= target
        ceiling = serial_availability

        return {
            "service": service,
            "target": f"{target:.3%}",
            "feasible": feasible,
            "dependency_chain": dep_availabilities,
            "serial_availability": f"{serial_availability:.3%}",
            "ceiling": f"{ceiling:.3%}",
            "gap": f"{(target - serial_availability):.3%}" if not feasible else None,
            "recommendations": _generate_slo_recommendations(target, serial_availability, dep_availabilities) if not feasible else [],
        }
    except Exception as e:
        return {"error": str(e), "service": service}


def _generate_slo_recommendations(target: float, actual: float, deps: list) -> list[str]:
    """Generate recommendations for achieving SLO target."""
    recs = []
    gap = target - actual

    if gap > 0.001:  # >0.1% gap
        recs.append(f"Consider reducing target to {actual:.2%} to match achievable ceiling")

    # Find weakest dependencies
    sorted_deps = sorted(deps, key=lambda d: d["availability"])
    if sorted_deps:
        weakest = sorted_deps[0]
        recs.append(f"Improve {weakest['service']} availability (currently {weakest['availability']:.2%})")
        recs.append(f"Add redundancy or circuit breaker for {weakest['service']}")

    return recs


async def _blast_radius(
    context: NthLayerContext,
    service: str,
    degradation: float = 0.99,
    duration_hours: float = 1,
) -> dict:
    """Analyze blast radius if service degrades."""
    try:
        # Get downstream dependents
        graph = await context.discovery.build_full_graph()

        direct = graph.get_downstream(service)
        transitive = graph.get_transitive_downstream(service, max_depth=5)

        # Get ownership for affected services
        affected_services = [d.source.canonical_name for d in direct]
        ownerships = await context.ownership.get_teams_for_services(affected_services)

        # Group by team
        teams_affected = {}
        for svc, ownership in ownerships.items():
            team = ownership.owner or "unknown"
            if team not in teams_affected:
                teams_affected[team] = {
                    "services": [],
                    "contact": ownership.slack_channel or ownership.email,
                }
            teams_affected[team]["services"].append(svc)

        # Calculate SLO impact (simplified)
        # In reality, would calculate based on actual SLO configs
        critical_affected = len([d for d in direct if d.metadata.get("tier") == "critical"])
        estimated_impact = (1 - degradation) * duration_hours * 0.01  # Simplified

        return {
            "service": service,
            "scenario": {
                "degradation": f"{degradation:.2%}",
                "duration_hours": duration_hours,
            },
            "direct_dependents": [
                {
                    "service": d.source.canonical_name,
                    "tier": d.metadata.get("tier", "unknown"),
                    "owner": ownerships.get(d.source.canonical_name, {}).owner,
                }
                for d in direct
            ],
            "transitive_impact": {
                "total_services": len(transitive),
                "by_depth": _count_by_depth(transitive),
            },
            "teams_affected": teams_affected,
            "estimated_org_impact": f"{estimated_impact:.3%} SLO impact",
            "critical_services_affected": critical_affected,
        }
    except Exception as e:
        return {"error": str(e), "service": service}


def _count_by_depth(deps: list) -> dict:
    """Count dependencies by depth."""
    counts = {}
    for dep, depth in deps:
        counts[f"depth_{depth}"] = counts.get(f"depth_{depth}", 0) + 1
    return counts


async def _get_dependencies(
    context: NthLayerContext,
    service: str,
    direction: str = "both",
    depth: int = 2,
) -> dict:
    """Get service dependencies."""
    try:
        graph = await context.discovery.build_full_graph()

        result = {"service": service}

        if direction in ("upstream", "both"):
            upstream = graph.get_upstream(service)
            if depth > 1:
                transitive_up = graph.get_transitive_upstream(service, max_depth=depth)
            else:
                transitive_up = []

            result["upstream"] = {
                "direct": [
                    {
                        "service": d.target.canonical_name,
                        "type": d.dep_type.value,
                        "confidence": f"{d.confidence:.0%}",
                        "providers": d.providers,
                    }
                    for d in upstream
                ],
                "transitive": [
                    {
                        "service": d.target.canonical_name,
                        "depth": depth,
                    }
                    for d, depth in transitive_up
                ] if depth > 1 else [],
            }

        if direction in ("downstream", "both"):
            downstream = graph.get_downstream(service)
            if depth > 1:
                transitive_down = graph.get_transitive_downstream(service, max_depth=depth)
            else:
                transitive_down = []

            result["downstream"] = {
                "direct": [
                    {
                        "service": d.source.canonical_name,
                        "type": d.dep_type.value,
                        "confidence": f"{d.confidence:.0%}",
                    }
                    for d in downstream
                ],
                "transitive": [
                    {
                        "service": d.source.canonical_name,
                        "depth": depth,
                    }
                    for d, depth in transitive_down
                ] if depth > 1 else [],
            }

        return result
    except Exception as e:
        return {"error": str(e), "service": service}


async def _get_ownership(
    context: NthLayerContext,
    service: str,
) -> dict:
    """Get ownership information for a service."""
    try:
        ownership = await context.ownership.resolve(service)

        return {
            "service": service,
            "owner": ownership.owner,
            "confidence": f"{ownership.confidence:.0%}",
            "source": ownership.source.value if ownership.source else None,
            "contacts": {
                "slack": ownership.slack_channel,
                "email": ownership.email,
                "pagerduty": ownership.pagerduty_escalation,
            },
            "all_signals": [
                {
                    "source": s.source.value,
                    "owner": s.owner,
                    "confidence": f"{s.confidence:.0%}",
                }
                for s in ownership.signals
            ],
        }
    except Exception as e:
        return {"error": str(e), "service": service}


async def _portfolio_status(
    context: NthLayerContext,
    tier: str = "all",
    include_drift: bool = False,
    include_dependencies: bool = False,
) -> dict:
    """Get portfolio-wide reliability status."""
    try:
        # This would integrate with existing portfolio command
        # Simplified implementation
        services = await context.discovery._discover_all_services()

        # Filter by tier if specified
        # Would load service configs and filter

        results = []
        for service in services[:20]:  # Limit for performance
            svc_result = {
                "service": service,
                "tier": "unknown",  # Would load from config
            }

            if include_drift:
                drift = await _drift_check(context, service)
                svc_result["drift"] = drift.get("overall_severity", "unknown")

            if include_dependencies:
                deps = await _get_dependencies(context, service, direction="upstream", depth=1)
                svc_result["dependency_count"] = len(deps.get("upstream", {}).get("direct", []))

            # Get ownership
            ownership = await context.ownership.resolve(service)
            svc_result["owner"] = ownership.owner

            results.append(svc_result)

        # Summary
        return {
            "total_services": len(results),
            "services": results,
            "summary": {
                "with_drift_warning": len([r for r in results if r.get("drift") in ("warn", "critical")]),
                "unowned": len([r for r in results if not r.get("owner")]),
            }
        }
    except Exception as e:
        return {"error": str(e)}


async def _check_deploy(
    context: NthLayerContext,
    service: str,
    include_drift: bool = True,
    include_dependencies: bool = True,
) -> dict:
    """Check if deployment should proceed."""
    try:
        checks = []
        can_deploy = True

        # Check error budget
        budget = await context.slo_collector.get_current_budget(service)
        if budget < 0.1:  # <10% budget remaining
            checks.append({
                "check": "error_budget",
                "status": "fail",
                "message": f"Error budget critically low: {budget:.1%}",
            })
            can_deploy = False
        else:
            checks.append({
                "check": "error_budget",
                "status": "pass",
                "message": f"Error budget healthy: {budget:.1%}",
            })

        # Check drift
        if include_drift:
            drift = await _drift_check(context, service)
            severity = drift.get("overall_severity", "none")

            if severity == "critical":
                checks.append({
                    "check": "drift",
                    "status": "fail",
                    "message": "Critical drift detected - investigate before deploying",
                })
                can_deploy = False
            elif severity == "warn":
                checks.append({
                    "check": "drift",
                    "status": "warn",
                    "message": "Drift warning - deploy with caution",
                })
            else:
                checks.append({
                    "check": "drift",
                    "status": "pass",
                    "message": "No significant drift",
                })

        # Check dependency health
        if include_dependencies:
            deps = await context.discovery.discover_for_service(service)
            unhealthy_deps = []

            for dep in deps:
                dep_drift = await _drift_check(context, dep.target.canonical_name)
                if dep_drift.get("overall_severity") == "critical":
                    unhealthy_deps.append(dep.target.canonical_name)

            if unhealthy_deps:
                checks.append({
                    "check": "dependency_health",
                    "status": "warn",
                    "message": f"Dependencies with issues: {', '.join(unhealthy_deps)}",
                })
            else:
                checks.append({
                    "check": "dependency_health",
                    "status": "pass",
                    "message": "All dependencies healthy",
                })

        return {
            "service": service,
            "can_deploy": can_deploy,
            "checks": checks,
            "recommendation": "Proceed with deployment" if can_deploy else "Resolve issues before deploying",
        }
    except Exception as e:
        return {"error": str(e), "service": service, "can_deploy": False}
```

---

## Resources

Resources are data the AI can read. They're like files but dynamically generated.

```python
# src/nthlayer/mcp/resources.py

"""
MCP Resources for NthLayer.

Resources provide read access to NthLayer data.
"""

from mcp.server import Server
from mcp.types import Resource, TextContent

from nthlayer.mcp.context import NthLayerContext


def register_resources(server: Server, context: NthLayerContext):
    """Register all NthLayer resources with the MCP server."""

    @server.list_resources()
    async def list_resources() -> list[Resource]:
        return [
            Resource(
                uri="nthlayer://portfolio",
                name="Service Portfolio",
                description="Overview of all services with reliability status",
                mimeType="application/json",
            ),
            Resource(
                uri="nthlayer://service/{name}",
                name="Service Details",
                description="Detailed information about a specific service including drift, dependencies, and ownership",
                mimeType="application/json",
            ),
            Resource(
                uri="nthlayer://graph",
                name="Dependency Graph",
                description="Complete service dependency graph",
                mimeType="application/json",
            ),
            Resource(
                uri="nthlayer://config",
                name="NthLayer Configuration",
                description="Current NthLayer configuration and enabled providers",
                mimeType="application/json",
            ),
        ]

    @server.read_resource()
    async def read_resource(uri: str) -> str:
        """Read a resource by URI."""
        import json

        if uri == "nthlayer://portfolio":
            data = await _read_portfolio(context)
        elif uri.startswith("nthlayer://service/"):
            service_name = uri.replace("nthlayer://service/", "")
            data = await _read_service(context, service_name)
        elif uri == "nthlayer://graph":
            data = await _read_graph(context)
        elif uri == "nthlayer://config":
            data = await _read_config(context)
        else:
            data = {"error": f"Unknown resource: {uri}"}

        return json.dumps(data, indent=2, default=str)


async def _read_portfolio(context: NthLayerContext) -> dict:
    """Read portfolio overview."""
    services = await context.discovery._discover_all_services()

    portfolio = []
    for service in services[:50]:  # Limit for performance
        ownership = await context.ownership.resolve(service)
        portfolio.append({
            "service": service,
            "owner": ownership.owner,
            "slack": ownership.slack_channel,
        })

    return {
        "total_services": len(services),
        "services": portfolio,
    }


async def _read_service(context: NthLayerContext, service: str) -> dict:
    """Read detailed service information."""
    # Get dependencies
    deps = await context.discovery.discover_for_service(service)

    # Get ownership
    ownership = await context.ownership.resolve(service)

    # Get drift (if available)
    try:
        drift = await context.drift_analyzer.analyze(service)
        drift_data = {
            "severity": drift.overall_severity.value,
            "summary": drift.summary,
        }
    except:
        drift_data = None

    return {
        "service": service,
        "ownership": {
            "owner": ownership.owner,
            "source": ownership.source.value if ownership.source else None,
            "contacts": {
                "slack": ownership.slack_channel,
                "pagerduty": ownership.pagerduty_escalation,
            }
        },
        "dependencies": {
            "upstream": [
                {
                    "service": d.target.canonical_name,
                    "type": d.dep_type.value,
                }
                for d in deps if d.source.canonical_name == service
            ],
            "downstream": [
                {
                    "service": d.source.canonical_name,
                    "type": d.dep_type.value,
                }
                for d in deps if d.target.canonical_name == service
            ],
        },
        "drift": drift_data,
    }


async def _read_graph(context: NthLayerContext) -> dict:
    """Read complete dependency graph."""
    graph = await context.discovery.build_full_graph()

    return {
        "nodes": [
            {
                "id": name,
                "aliases": list(identity.aliases),
            }
            for name, identity in graph.services.items()
        ],
        "edges": [
            {
                "source": edge.source.canonical_name,
                "target": edge.target.canonical_name,
                "type": edge.dep_type.value,
                "confidence": edge.confidence,
            }
            for edge in graph.edges
        ],
        "metadata": {
            "built_at": graph.built_at.isoformat(),
            "providers": graph.providers_used,
        }
    }


async def _read_config(context: NthLayerContext) -> dict:
    """Read current configuration."""
    return {
        "prometheus": {
            "url": context.config.get("prometheus", {}).get("url"),
        },
        "discovery": {
            "providers": list(context.config.get("discovery", {}).get("providers", {}).keys()),
            "enabled": [
                name for name, cfg in context.config.get("discovery", {}).get("providers", {}).items()
                if cfg.get("enabled", False)
            ],
        },
        "ownership": {
            "providers": list(context.config.get("ownership", {}).get("providers", {}).keys()),
            "enabled": [
                name for name, cfg in context.config.get("ownership", {}).get("providers", {}).items()
                if cfg.get("enabled", False)
            ],
        },
    }
```

---

## Prompts

Prompts are pre-defined templates for common workflows.

```python
# src/nthlayer/mcp/prompts.py

"""
MCP Prompts for NthLayer.

Prompts provide templates for common reliability workflows.
"""

from mcp.server import Server
from mcp.types import Prompt, PromptArgument, PromptMessage, TextContent

from nthlayer.mcp.context import NthLayerContext


def register_prompts(server: Server, context: NthLayerContext):
    """Register all NthLayer prompts with the MCP server."""

    @server.list_prompts()
    async def list_prompts() -> list[Prompt]:
        return [
            Prompt(
                name="incident_response",
                description="Guide through incident response for a degraded service",
                arguments=[
                    PromptArgument(
                        name="service",
                        description="The service experiencing issues",
                        required=True,
                    ),
                    PromptArgument(
                        name="symptoms",
                        description="Observed symptoms or alerts",
                        required=False,
                    ),
                ],
            ),
            Prompt(
                name="pre_deploy_review",
                description="Review reliability posture before deployment",
                arguments=[
                    PromptArgument(
                        name="service",
                        description="Service being deployed",
                        required=True,
                    ),
                    PromptArgument(
                        name="changes",
                        description="Summary of changes being deployed",
                        required=False,
                    ),
                ],
            ),
            Prompt(
                name="capacity_planning",
                description="Analyze capacity and reliability for a service",
                arguments=[
                    PromptArgument(
                        name="service",
                        description="Service to analyze",
                        required=True,
                    ),
                    PromptArgument(
                        name="growth_percent",
                        description="Expected traffic growth percentage",
                        required=False,
                    ),
                ],
            ),
            Prompt(
                name="weekly_reliability_review",
                description="Generate weekly reliability review for a team or portfolio",
                arguments=[
                    PromptArgument(
                        name="team",
                        description="Team name (optional, reviews all if not specified)",
                        required=False,
                    ),
                ],
            ),
            Prompt(
                name="slo_design",
                description="Help design appropriate SLOs for a service",
                arguments=[
                    PromptArgument(
                        name="service",
                        description="Service to design SLOs for",
                        required=True,
                    ),
                    PromptArgument(
                        name="tier",
                        description="Service tier (critical, standard, low)",
                        required=False,
                    ),
                ],
            ),
        ]

    @server.get_prompt()
    async def get_prompt(name: str, arguments: dict | None) -> list[PromptMessage]:
        """Generate prompt content."""
        arguments = arguments or {}

        if name == "incident_response":
            return _incident_response_prompt(arguments)
        elif name == "pre_deploy_review":
            return _pre_deploy_review_prompt(arguments)
        elif name == "capacity_planning":
            return _capacity_planning_prompt(arguments)
        elif name == "weekly_reliability_review":
            return _weekly_review_prompt(arguments)
        elif name == "slo_design":
            return _slo_design_prompt(arguments)
        else:
            return [PromptMessage(
                role="user",
                content=TextContent(type="text", text=f"Unknown prompt: {name}"),
            )]


def _incident_response_prompt(args: dict) -> list[PromptMessage]:
    service = args.get("service", "unknown")
    symptoms = args.get("symptoms", "degraded performance")

    return [PromptMessage(
        role="user",
        content=TextContent(type="text", text=f"""I'm responding to an incident with {service}.

Symptoms: {symptoms}

Please help me by:
1. First, use nthlayer_get_ownership to identify who owns this service and get contact info
2. Use nthlayer_get_dependencies to understand what {service} depends on (upstream) and what depends on it (downstream)
3. Use nthlayer_drift_check to see if there were any warning signs before this incident
4. Use nthlayer_blast_radius to understand the impact scope

Based on this information:
- Who should be paged/notified?
- What are the likely root causes based on dependencies?
- What's the blast radius and which teams need to know?
- Were there any drift warnings we missed?

Guide me through the incident response."""),
    )]


def _pre_deploy_review_prompt(args: dict) -> list[PromptMessage]:
    service = args.get("service", "unknown")
    changes = args.get("changes", "Not specified")

    return [PromptMessage(
        role="user",
        content=TextContent(type="text", text=f"""I'm about to deploy changes to {service}.

Changes: {changes}

Please review the reliability posture:
1. Use nthlayer_check_deploy to run all pre-deployment checks
2. Use nthlayer_drift_check to see current reliability trends
3. Use nthlayer_validate_slo to confirm our SLO targets are still achievable
4. Use nthlayer_get_dependencies to identify what might be affected

Tell me:
- Is it safe to deploy right now?
- Are there any reliability concerns I should address first?
- What should I monitor closely after deployment?
- Who should I notify before/after the deployment?"""),
    )]


def _capacity_planning_prompt(args: dict) -> list[PromptMessage]:
    service = args.get("service", "unknown")
    growth = args.get("growth_percent", "20")

    return [PromptMessage(
        role="user",
        content=TextContent(type="text", text=f"""I need to do capacity planning for {service} with expected {growth}% traffic growth.

Please analyze:
1. Use nthlayer_get_dependencies to map the full dependency chain
2. Use nthlayer_validate_slo to check if current SLO targets are achievable
3. Use nthlayer_drift_check to identify any concerning trends
4. Use nthlayer_blast_radius to understand the criticality of this service

Based on this:
- Which dependencies might become bottlenecks under increased load?
- Is our current SLO target realistic given dependencies?
- Are there reliability trends that might worsen with more traffic?
- What capacity improvements would have the most impact?"""),
    )]


def _weekly_review_prompt(args: dict) -> list[PromptMessage]:
    team = args.get("team")
    scope = f"team {team}" if team else "the entire portfolio"

    return [PromptMessage(
        role="user",
        content=TextContent(type="text", text=f"""Generate a weekly reliability review for {scope}.

Please:
1. Use nthlayer_portfolio_status with include_drift=true to get the current state
2. For any services with drift warnings, use nthlayer_drift_check to get details
3. Identify the top 3-5 reliability risks

Format the review as:
- Executive Summary (2-3 sentences)
- Services Requiring Attention (with specific concerns and owners)
- Positive Trends (services that improved)
- Recommended Actions (prioritized)
- Metrics Summary (budget status, drift trends)"""),
    )]


def _slo_design_prompt(args: dict) -> list[PromptMessage]:
    service = args.get("service", "unknown")
    tier = args.get("tier", "standard")

    return [PromptMessage(
        role="user",
        content=TextContent(type="text", text=f"""Help me design appropriate SLOs for {service} (tier: {tier}).

Please:
1. Use nthlayer_get_dependencies to understand the dependency chain
2. Use nthlayer_validate_slo with different targets to find achievable levels
3. Use nthlayer_get_ownership to understand the team context

Based on this analysis:
- What availability target is mathematically achievable given dependencies?
- What latency SLOs make sense for this service?
- What error rate target should we set?
- How should we configure alerting windows and burn rates?
- Are there dependency improvements needed to achieve desired targets?

Consider that this is a {tier} tier service."""),
    )]
```

---

## CLI Integration

```python
# src/nthlayer/cli/mcp.py

"""
CLI commands for MCP server.
"""

import click


@click.group()
def mcp():
    """MCP server commands."""
    pass


@mcp.command()
@click.option("--transport", type=click.Choice(["stdio", "sse"]), default="stdio")
@click.option("--port", type=int, default=8080, help="Port for SSE transport")
def serve(transport: str, port: int):
    """Start the NthLayer MCP server.

    Examples:
        # For Claude Desktop (stdio)
        nthlayer mcp serve

        # For web clients (SSE)
        nthlayer mcp serve --transport sse --port 8080
    """
    from nthlayer.mcp.server import run_stdio, run_sse
    import asyncio

    if transport == "stdio":
        click.echo("Starting NthLayer MCP server (stdio)...", err=True)
        asyncio.run(run_stdio())
    else:
        click.echo(f"Starting NthLayer MCP server (SSE) on port {port}...", err=True)
        asyncio.run(run_sse(port))


@mcp.command()
def config():
    """Show MCP configuration for Claude Desktop.

    Outputs the JSON configuration to add to Claude Desktop's config file.
    """
    import json
    import sys

    config = {
        "mcpServers": {
            "nthlayer": {
                "command": sys.executable,
                "args": ["-m", "nthlayer.mcp.server"],
                "env": {
                    "NTHLAYER_CONFIG": "~/.config/nthlayer/config.yaml"
                }
            }
        }
    }

    click.echo("Add this to your Claude Desktop configuration:\n")
    click.echo(json.dumps(config, indent=2))
    click.echo("\n# macOS: ~/Library/Application Support/Claude/claude_desktop_config.json")
    click.echo("# Windows: %APPDATA%\\Claude\\claude_desktop_config.json")
```

---

## Configuration

```yaml
# nthlayer.yaml
mcp:
  # Server settings
  server:
    name: "nthlayer"
    version: "0.5.0"

  # Which capabilities to expose
  capabilities:
    tools:
      - nthlayer_drift_check
      - nthlayer_validate_slo
      - nthlayer_blast_radius
      - nthlayer_get_dependencies
      - nthlayer_get_ownership
      - nthlayer_portfolio_status
      - nthlayer_check_deploy

    resources:
      - nthlayer://portfolio
      - nthlayer://service/*
      - nthlayer://graph
      - nthlayer://config

    prompts:
      - incident_response
      - pre_deploy_review
      - capacity_planning
      - weekly_reliability_review
      - slo_design

  # Performance limits
  limits:
    max_services_in_portfolio: 100
    dependency_depth: 5
    cache_ttl: 300
```

---

## Claude Desktop Integration

```json
// ~/Library/Application Support/Claude/claude_desktop_config.json
{
  "mcpServers": {
    "nthlayer": {
      "command": "nthlayer",
      "args": ["mcp", "serve"],
      "env": {
        "PROMETHEUS_URL": "http://prometheus:9090",
        "PAGERDUTY_API_KEY": "your-key-here"
      }
    }
  }
}
```

---

## Example Conversations

### Incident Response

```
User: payment-api is showing elevated errors

Claude: Let me investigate payment-api.
[Calls nthlayer_get_ownership]
[Calls nthlayer_drift_check]
[Calls nthlayer_get_dependencies]
[Calls nthlayer_blast_radius]

Here's what I found:

**Ownership:** payments-team owns this (contact: #team-payments)

**Recent Drift:** I see error budget has been declining at 0.8%/week
for the past 2 weeks - this incident may have been predictable.

**Dependencies:** payment-api depends on:
- user-service (healthy)
- postgresql (healthy)
- stripe-api (showing 2% error rate increase)

**Blast Radius:** 3 critical services depend on payment-api:
- checkout-api (checkout-squad)
- order-service (orders-team)

**Recommended actions:**
1. Page payments-team via #team-payments
2. Investigate stripe-api connection - likely root cause
3. Notify checkout-squad and orders-team of potential impact
4. After resolution, investigate why drift warnings weren't actioned
```

### Pre-Deploy Check

```
User: Can I deploy the new auth changes to user-service?

Claude: Let me check the deployment readiness.
[Calls nthlayer_check_deploy]

**Deployment Check Results:**

✓ Error budget: 91% remaining - healthy
✓ Drift: No significant drift detected
⚠️ Dependency health: payment-api showing drift warning

**Recommendation:** You can deploy, but be aware that payment-api
(which depends on user-service) is already showing reliability
stress. Monitor closely after deployment and consider:

1. Deploying during low-traffic window
2. Having payments-team on standby
3. Preparing rollback plan

Want me to check what specifically is happening with payment-api?
```

---

## Summary

This MCP server spec provides:

**7 Tools:**
- `nthlayer_drift_check` — Check error budget drift
- `nthlayer_validate_slo` — Validate SLO feasibility
- `nthlayer_blast_radius` — Analyze degradation impact
- `nthlayer_get_dependencies` — Get service dependencies
- `nthlayer_get_ownership` — Get ownership info
- `nthlayer_portfolio_status` — Org-wide reliability view
- `nthlayer_check_deploy` — Pre-deployment validation

**4 Resources:**
- `nthlayer://portfolio` — Service portfolio
- `nthlayer://service/{name}` — Service details
- `nthlayer://graph` — Dependency graph
- `nthlayer://config` — Current configuration

**5 Prompts:**
- `incident_response` — Incident investigation workflow
- `pre_deploy_review` — Deployment readiness check
- `capacity_planning` — Capacity analysis
- `weekly_reliability_review` — Weekly review generation
- `slo_design` — SLO design assistance

**Estimated Implementation:** 2-3 days (assumes drift + dependency discovery complete)
