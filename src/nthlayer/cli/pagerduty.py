"""
PagerDuty setup command.
"""

from __future__ import annotations

import os

from nthlayer.cli.ux import console, error, header, info, success, warning
from nthlayer.integrations.pagerduty import PagerDutyClient
from nthlayer.specs.parser import parse_service_file


def setup_pagerduty_command(
    service_file: str,
    api_key: str | None = None,
    environment: str | None = None,
    dry_run: bool = False,
) -> int:
    """
    Setup PagerDuty integration for a service.

    Args:
        service_file: Path to service YAML file
        api_key: PagerDuty API key (or use PAGERDUTY_API_KEY env var)
        environment: Optional environment name (dev, staging, prod)
        dry_run: Preview what would be created without making changes

    Returns:
        Exit code (0 = success, 1 = error)
    """
    header("Setup PagerDuty Integration")
    console.print()

    if environment:
        console.print(f"[info]Environment:[/info] {environment}")
        console.print()

    # Get API key
    api_key = api_key or os.environ.get("PAGERDUTY_API_KEY")
    if not api_key:
        error("PagerDuty API key required")
        console.print()
        console.print("[muted]Provide via:[/muted]")
        console.print("  [muted]•[/muted] --api-key flag")
        console.print("  [muted]•[/muted] PAGERDUTY_API_KEY environment variable")
        console.print()
        console.print(
            "[muted]Get your API key at:[/muted] [info]https://support.pagerduty.com/docs/api-access-keys[/info]"
        )
        console.print()
        return 1

    # Parse service file with optional environment overrides
    try:
        service_context, resources = parse_service_file(service_file, environment=environment)
    except Exception as e:
        error(f"Error parsing service file: {e}")
        console.print()
        return 1

    # Find PagerDuty resource
    pagerduty_resources = [r for r in resources if r.kind == "PagerDuty"]

    if not pagerduty_resources:
        error(f"No PagerDuty resource found in {service_file}")
        console.print()
        console.print("[muted]Add a PagerDuty resource to your service definition:[/muted]")
        console.print("  resources:")
        console.print("    - kind: PagerDuty")
        console.print("      name: primary")
        console.print("      spec:")
        console.print("        escalation_policy: my-policy")
        console.print("        urgency: high")
        console.print()
        return 1

    pagerduty_resource = pagerduty_resources[0]
    spec = pagerduty_resource.spec

    console.print(f"[bold]Service:[/bold] {service_context.name}")
    console.print(f"   [muted]Team:[/muted] {service_context.team}")
    console.print(f"   [muted]Tier:[/muted] {service_context.tier}")
    console.print()

    if dry_run:
        info("DRY RUN MODE - No changes will be made")
        console.print()
        console.print("[bold]Would create/verify:[/bold]")
        console.print(f"  [muted]•[/muted] PagerDuty service: {service_context.name}")

        if spec.get("escalation_policy"):
            console.print(f"  [muted]•[/muted] Escalation policy: {spec['escalation_policy']}")

        if service_context.team:
            console.print(f"  [muted]•[/muted] Team mapping: {service_context.team}")

        console.print()
        return 0

    # Setup PagerDuty
    console.print("[info]Setting up PagerDuty integration...[/info]")
    console.print()

    try:
        with PagerDutyClient(api_key) as client:
            # Prepare config
            escalation_policy_name = spec.get("escalation_policy")
            escalation_policy_id = spec.get("escalation_policy_id")
            urgency = spec.get("urgency", "high")
            auto_resolve_timeout = spec.get("auto_resolve_timeout")

            # Check if we should create escalation policy
            create_ep_config = None
            if spec.get("create_escalation_policy"):
                create_ep_config = spec["create_escalation_policy"]

            result = client.setup_service(
                service_name=service_context.name,
                team_name=service_context.team,
                escalation_policy_name=escalation_policy_name,
                escalation_policy_id=escalation_policy_id,
                urgency=urgency,
                auto_resolve_timeout=auto_resolve_timeout,
                create_escalation_policy_config=create_ep_config,
            )

        if not result.success:
            error(f"Setup failed: {result.error}")
            console.print()
            return 1

        # Display results
        if result.created_service:
            success("Created PagerDuty service")
        else:
            success("PagerDuty service already exists")

        console.print(f"   [muted]Service ID:[/muted] {result.service_id}")
        console.print(f"   [muted]Service URL:[/muted] [info]{result.service_url}[/info]")
        console.print()

        if result.created_escalation_policy:
            success("Created escalation policy")
            console.print(f"   [muted]Policy ID:[/muted] {result.escalation_policy_id}")
            console.print()

        if result.team_id:
            if result.created_team:
                success(f"Created team: {service_context.team}")
            else:
                success(f"Added to existing team: {service_context.team}")
            console.print(f"   [muted]Team ID:[/muted] {result.team_id}")
            console.print()

        if result.warnings:
            warning("Warnings:")
            for warn in result.warnings:
                console.print(f"   [warning]•[/warning] {warn}")
            console.print()

        success("PagerDuty setup complete!")
        console.print()
        console.print("[bold]Next steps:[/bold]")
        console.print(f"   [muted]1.[/muted] Visit: [info]{result.service_url}[/info]")
        console.print("   [muted]2.[/muted] Configure integrations (email, webhooks, etc.)")
        console.print(
            f"   [muted]3.[/muted] Test alerting with: "
            f"[info]nthlayer reslayer test-alert {service_context.name}[/info]"
        )
        console.print()

        return 0

    except Exception as e:
        error(f"Unexpected error: {e}")
        import traceback

        traceback.print_exc()
        console.print()
        return 1
