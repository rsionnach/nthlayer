"""
CLI command for identity resolution and management.

Shows service identity mappings, normalization, and resolution details.

Commands:
    nthlayer identity resolve <name>          - Show how a name resolves
    nthlayer identity list                    - List all known identities
    nthlayer identity normalize <name>        - Show normalization steps
    nthlayer identity add-mapping <raw> <can> - Add explicit mapping
"""

from __future__ import annotations

import argparse
import fnmatch
import re
from dataclasses import dataclass
from typing import Optional

from rich.table import Table

from nthlayer.cli.ux import console, error, header
from nthlayer.identity.models import IdentityMatch, ServiceIdentity
from nthlayer.identity.normalizer import DEFAULT_RULES, normalize_service_name
from nthlayer.identity.resolver import IdentityResolver


# Demo data for testing without real services
def create_demo_identities() -> list[ServiceIdentity]:
    """Create demo identity data."""
    return [
        ServiceIdentity(
            canonical_name="payment-api",
            aliases={"payment-service", "payments", "payment-api-prod", "pay-svc"},
            external_ids={
                "kubernetes": "default/payment-api-deployment",
                "backstage": "component:default/payment-api",
                "consul": "payment-prod",
            },
            attributes={"team": "payments-team", "tier": "critical", "repo": "acme/payment-api"},
            confidence=1.0,
            source="declared",
        ),
        ServiceIdentity(
            canonical_name="search-api",
            aliases={"search-service", "search"},
            external_ids={
                "kubernetes": "default/search-api",
                "backstage": "component:default/search-api",
            },
            attributes={"team": "search-team", "tier": "standard"},
            confidence=1.0,
            source="declared",
        ),
        ServiceIdentity(
            canonical_name="user-service",
            aliases={"users", "user-api", "user-svc", "identity-service", "auth-users"},
            external_ids={
                "kubernetes": "auth/user-service",
                "backstage": "component:auth/user-service",
                "consul": "users-prod",
            },
            attributes={"team": "identity-team", "tier": "critical"},
            confidence=0.85,
            source="discovered",
        ),
        ServiceIdentity(
            canonical_name="notification",
            aliases={"notifications", "notifier", "notification-service"},
            external_ids={
                "kubernetes": "messaging/notification-worker",
            },
            attributes={"team": "messaging-team", "tier": "standard"},
            confidence=0.90,
            source="discovered",
        ),
    ]


def create_demo_resolver() -> IdentityResolver:
    """Create a resolver populated with demo data."""
    resolver = IdentityResolver()
    for identity in create_demo_identities():
        resolver.register(identity)
    # Add some explicit mappings
    resolver.add_mapping("legacy-payments", "payment-api")
    resolver.add_mapping("old-user-svc", "user-service", provider="consul")
    return resolver


@dataclass
class NormalizationStep:
    """A single step in the normalization process."""

    rule_name: str
    input_value: str
    output_value: str
    changed: bool


def normalize_with_steps(name: str) -> tuple[str, list[NormalizationStep]]:
    """Normalize a name and return all steps applied."""
    steps = []
    current = name.lower()

    # Step 1: Lowercase
    steps.append(
        NormalizationStep(
            rule_name="Lowercase",
            input_value=name,
            output_value=current,
            changed=name != current,
        )
    )

    # Apply each rule and track changes
    for rule in DEFAULT_RULES:
        before = current
        current = re.sub(rule.pattern, rule.replacement, current, flags=re.IGNORECASE)
        steps.append(
            NormalizationStep(
                rule_name=rule.description,
                input_value=before,
                output_value=current,
                changed=before != current,
            )
        )

    # Normalize separators
    before = current
    current = re.sub(r"[._]", "-", current)
    current = current.strip("-")
    current = re.sub(r"-+", "-", current)
    steps.append(
        NormalizationStep(
            rule_name="Normalize separators",
            input_value=before,
            output_value=current,
            changed=before != current,
        )
    )

    return current, steps


# --- Resolve subcommand ---


def identity_resolve_command(
    name: str,
    provider: Optional[str] = None,
    output_format: str = "table",
    demo: bool = False,
) -> int:
    """
    Resolve a service name to its canonical identity.

    Shows how a name maps through resolution strategies.

    Exit codes:
        0 - Identity found
        1 - No match found
        2 - Error

    Args:
        name: Service name to resolve
        provider: Optional provider context
        output_format: Output format ("table" or "json")
        demo: If True, use demo data

    Returns:
        Exit code
    """
    if demo:
        resolver = create_demo_resolver()
    else:
        # In non-demo mode, create empty resolver
        # Real implementation would load from config/discovery
        resolver = IdentityResolver()

    match = resolver.resolve(name, provider=provider)

    if output_format == "json":
        console.print_json(data=match.to_dict())
    else:
        _print_resolve_output(match)

    return 0 if match.found else 1


def _print_resolve_output(match: IdentityMatch) -> None:
    """Print identity resolution result."""
    console.print()
    header(f"Identity Resolution: {match.query}")
    console.print()

    if not match.found:
        console.print("[yellow]No identity match found[/yellow]")
        console.print()
        normalized = normalize_service_name(match.query)
        console.print(f"[muted]Normalized form: {normalized}[/muted]")
        console.print()
        return

    identity = match.identity
    assert identity is not None  # for type checker

    # Match details
    console.print(f"[bold]Match Type:[/bold] {match.match_type}")
    console.print(f"[bold]Confidence:[/bold] {match.confidence:.0%}")
    console.print()

    # Canonical info
    console.print(f"[bold]Canonical:[/bold] [cyan]{identity.canonical_name}[/cyan]")
    console.print(f"[bold]Source:[/bold] {identity.source}")
    console.print()

    # Aliases
    if identity.aliases:
        console.print("[bold]Aliases:[/bold]")
        for alias in sorted(identity.aliases):
            console.print(f"  - {alias}")
        console.print()

    # External IDs
    if identity.external_ids:
        console.print("[bold]External IDs:[/bold]")
        for provider_name, ext_id in sorted(identity.external_ids.items()):
            console.print(f"  {provider_name}: {ext_id}")
        console.print()

    # Attributes
    if identity.attributes:
        console.print("[bold]Attributes:[/bold]")
        for key, value in sorted(identity.attributes.items()):
            console.print(f"  {key}: {value}")
        console.print()


# --- List subcommand ---


def identity_list_command(
    filter_pattern: Optional[str] = None,
    output_format: str = "table",
    demo: bool = False,
) -> int:
    """
    List all known service identities.

    Exit codes:
        0 - Success
        2 - Error

    Args:
        filter_pattern: Optional glob pattern to filter identities
        output_format: Output format ("table" or "json")
        demo: If True, use demo data

    Returns:
        Exit code
    """
    if demo:
        resolver = create_demo_resolver()
    else:
        resolver = IdentityResolver()

    identities = resolver.list_identities()

    # Filter if pattern provided
    if filter_pattern:
        identities = [i for i in identities if fnmatch.fnmatch(i.canonical_name, filter_pattern)]

    if output_format == "json":
        console.print_json(data=[i.to_dict() for i in identities])
    else:
        _print_identity_list(identities, filter_pattern)

    return 0


def _print_identity_list(identities: list[ServiceIdentity], filter_pattern: Optional[str]) -> None:
    """Print identity list as table."""
    console.print()
    header("Service Identities")
    console.print()

    if not identities:
        if filter_pattern:
            console.print(f"[muted]No identities matching '{filter_pattern}'[/muted]")
        else:
            console.print("[muted]No identities registered[/muted]")
        console.print()
        return

    table = Table(show_header=True, header_style="bold")
    table.add_column("Canonical")
    table.add_column("Aliases", style="muted")
    table.add_column("Source")
    table.add_column("Confidence")

    for identity in sorted(identities, key=lambda i: i.canonical_name):
        alias_count = len(identity.aliases)
        alias_text = f"{alias_count} alias{'es' if alias_count != 1 else ''}"

        source_style = "green" if identity.source == "declared" else "yellow"

        table.add_row(
            f"[cyan]{identity.canonical_name}[/cyan]",
            alias_text,
            f"[{source_style}]{identity.source}[/{source_style}]",
            f"{identity.confidence:.2f}",
        )

    console.print(table)
    console.print()
    console.print(f"[muted]{len(identities)} identities found[/muted]")
    console.print()


# --- Normalize subcommand ---


def identity_normalize_command(
    name: str,
    verbose: bool = False,
    output_format: str = "table",
) -> int:
    """
    Show how a service name gets normalized.

    Exit codes:
        0 - Success

    Args:
        name: Service name to normalize
        verbose: If True, show each step
        output_format: Output format ("table" or "json")

    Returns:
        Exit code
    """
    result, steps = normalize_with_steps(name)

    if output_format == "json":
        console.print_json(
            data={
                "input": name,
                "output": result,
                "steps": [
                    {
                        "rule": s.rule_name,
                        "input": s.input_value,
                        "output": s.output_value,
                        "changed": s.changed,
                    }
                    for s in steps
                ],
            }
        )
    else:
        _print_normalize_output(name, result, steps, verbose)

    return 0


def _print_normalize_output(
    name: str, result: str, steps: list[NormalizationStep], verbose: bool
) -> None:
    """Print normalization result."""
    console.print()
    header(f"Normalization: {name}")
    console.print()

    if verbose:
        step_num = 0
        for step in steps:
            if step.changed:
                step_num += 1
                console.print(f"[bold]Step {step_num}:[/bold] {step.rule_name}")
                console.print(f"  {step.input_value} [dim]->[/dim] {step.output_value}")
                console.print()

        if step_num == 0:
            console.print("[muted]No transformations applied[/muted]")
            console.print()

    console.print(f"[bold]Result:[/bold] [cyan]{result}[/cyan]")
    console.print()


# --- Add-mapping subcommand ---


def identity_add_mapping_command(
    raw_name: str,
    canonical_name: str,
    provider: Optional[str] = None,
    output_format: str = "table",
) -> int:
    """
    Add explicit identity mapping.

    Note: In current implementation, mappings are in-memory only.
    Future: persist to config file.

    Exit codes:
        0 - Success
        2 - Error

    Args:
        raw_name: Raw service name
        canonical_name: Canonical name to map to
        provider: Optional provider context
        output_format: Output format ("table" or "json")

    Returns:
        Exit code
    """
    resolver = IdentityResolver()
    resolver.add_mapping(raw_name, canonical_name, provider=provider)

    mapping_key = f"{raw_name}@{provider}" if provider else raw_name

    if output_format == "json":
        console.print_json(
            data={
                "raw_name": raw_name,
                "canonical_name": canonical_name,
                "provider": provider,
                "mapping_key": mapping_key,
            }
        )
    else:
        console.print()
        provider_text = f" (provider: {provider})" if provider else ""
        console.print(
            f"[green]Added mapping:[/green] {raw_name} [dim]->[/dim] "
            f"{canonical_name}{provider_text}"
        )
        console.print()
        console.print("[muted]Note: Mapping is in-memory only for this session[/muted]")
        console.print()

    return 0


# --- Parser registration ---


def register_identity_parser(subparsers: argparse._SubParsersAction) -> None:
    """Register identity subcommand parser with nested subcommands."""
    identity_parser = subparsers.add_parser(
        "identity",
        help="Service identity resolution and management",
    )

    identity_subparsers = identity_parser.add_subparsers(
        dest="identity_command",
        help="Identity subcommand",
    )

    # resolve subcommand
    resolve_parser = identity_subparsers.add_parser(
        "resolve",
        help="Resolve a service name to canonical identity",
    )
    resolve_parser.add_argument("name", help="Service name to resolve")
    resolve_parser.add_argument(
        "--provider",
        help="Provider context for resolution",
    )
    resolve_parser.add_argument(
        "--format",
        "-f",
        dest="output_format",
        choices=["table", "json"],
        default="table",
        help="Output format (default: table)",
    )
    resolve_parser.add_argument(
        "--demo",
        action="store_true",
        help="Use demo data",
    )

    # list subcommand
    list_parser = identity_subparsers.add_parser(
        "list",
        help="List all known service identities",
    )
    list_parser.add_argument(
        "--filter",
        dest="filter_pattern",
        help="Filter by glob pattern (e.g., 'payment*')",
    )
    list_parser.add_argument(
        "--format",
        "-f",
        dest="output_format",
        choices=["table", "json"],
        default="table",
        help="Output format (default: table)",
    )
    list_parser.add_argument(
        "--demo",
        action="store_true",
        help="Use demo data",
    )

    # normalize subcommand
    normalize_parser = identity_subparsers.add_parser(
        "normalize",
        help="Show how a service name gets normalized",
    )
    normalize_parser.add_argument("name", help="Service name to normalize")
    normalize_parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Show each normalization step",
    )
    normalize_parser.add_argument(
        "--format",
        "-f",
        dest="output_format",
        choices=["table", "json"],
        default="table",
        help="Output format (default: table)",
    )

    # add-mapping subcommand
    mapping_parser = identity_subparsers.add_parser(
        "add-mapping",
        help="Add explicit identity mapping",
    )
    mapping_parser.add_argument("raw_name", help="Raw service name")
    mapping_parser.add_argument("canonical_name", help="Canonical name to map to")
    mapping_parser.add_argument(
        "--provider",
        help="Provider for this mapping",
    )
    mapping_parser.add_argument(
        "--format",
        "-f",
        dest="output_format",
        choices=["table", "json"],
        default="table",
        help="Output format (default: table)",
    )


def handle_identity_command(args: argparse.Namespace) -> int:
    """Handle identity command from CLI args."""
    identity_cmd = getattr(args, "identity_command", None)

    if identity_cmd == "resolve":
        return identity_resolve_command(
            name=args.name,
            provider=getattr(args, "provider", None),
            output_format=getattr(args, "output_format", "table"),
            demo=getattr(args, "demo", False),
        )
    elif identity_cmd == "list":
        return identity_list_command(
            filter_pattern=getattr(args, "filter_pattern", None),
            output_format=getattr(args, "output_format", "table"),
            demo=getattr(args, "demo", False),
        )
    elif identity_cmd == "normalize":
        return identity_normalize_command(
            name=args.name,
            verbose=getattr(args, "verbose", False),
            output_format=getattr(args, "output_format", "table"),
        )
    elif identity_cmd == "add-mapping":
        return identity_add_mapping_command(
            raw_name=args.raw_name,
            canonical_name=args.canonical_name,
            provider=getattr(args, "provider", None),
            output_format=getattr(args, "output_format", "table"),
        )
    else:
        error("No identity subcommand specified. Use --help for usage.")
        return 2
