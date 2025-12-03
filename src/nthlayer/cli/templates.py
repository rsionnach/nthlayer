"""CLI command for listing service templates."""

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
        print(f"❌ Error loading templates: {e}")
        return 1
    
    if not registry.templates:
        print("No templates available")
        return 0
    
    print("📋 Available Service Templates\n")
    
    for template in registry.list():
        # Show template source (built-in or custom)
        source = CustomTemplateLoader.get_template_source(template.name)
        source_label = "🏠 custom" if source == "custom" else "📦 built-in"
        
        print(f"  {template.name} ({source_label})")
        print(f"    {template.description}")
        print(f"    Tier: {template.tier} | Type: {template.type}")
        print(f"    Resources: {len(template.resources)} ({_resource_summary(template)})")
        print()
    
    print("💡 Usage:")
    print("  nthlayer init my-service --template critical-api")
    print("  or add 'template: critical-api' to your service YAML")
    
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
