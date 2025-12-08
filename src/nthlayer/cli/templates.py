"""CLI command for listing service templates."""

from nthlayer.cli.ux import console, error, header, info
from nthlayer.specs.custom_templates import CustomTemplateLoader


def list_templates_command() -> int:
    """List all available service templates.

    Returns:
        Exit code (0 for success)
    """
    try:
        # Load both built-in and custom templates
        registry = CustomTemplateLoader.load_all_templates()
    except Exception as e:
        error(f"Error loading templates: {e}")
        return 1

    if not registry.templates:
        info("No templates available")
        return 0

    header("Available Service Templates")
    console.print()

    for template in registry.list():
        # Show template source (built-in or custom)
        source = CustomTemplateLoader.get_template_source(template.name)
        source_label = (
            "[highlight]custom[/highlight]" if source == "custom" else "[muted]built-in[/muted]"
        )

        console.print(f"  [bold cyan]{template.name}[/bold cyan] ({source_label})")
        console.print(f"    {template.description}")
        console.print(f"    [muted]Tier: {template.tier} | Type: {template.type}[/muted]")
        res_summary = _resource_summary(template)
        console.print(f"    [muted]Resources: {len(template.resources)} ({res_summary})[/muted]")
        console.print()

    console.print("[bold]Usage:[/bold]")
    console.print("  [cyan]nthlayer init my-service --template critical-api[/cyan]")
    console.print("  [muted]or add 'template: critical-api' to your service YAML[/muted]")

    return 0


def _resource_summary(template) -> str:
    """Generate summary of resources in template.

    Args:
        template: ServiceTemplate

    Returns:
        Comma-separated list of resource types
    """
    kinds = {}
    for resource in template.resources:
        kinds[resource.kind] = kinds.get(resource.kind, 0) + 1

    parts = []
    for kind, count in sorted(kinds.items()):
        if count == 1:
            parts.append(kind)
        else:
            parts.append(f"{count} {kind}s")

    return ", ".join(parts) if parts else "none"
