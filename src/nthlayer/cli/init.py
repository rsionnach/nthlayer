"""CLI command for initializing new NthLayer services."""

from pathlib import Path

from nthlayer.specs.custom_templates import CustomTemplateLoader


def init_command(
    service_name: str | None = None,
    team: str | None = None,
    template: str | None = None,
    interactive: bool = True
) -> int:
    """Initialize new NthLayer service.
    
    Creates a service YAML file from template and sets up project structure.
    
    Args:
        service_name: Service name (lowercase-with-hyphens)
        team: Team name
        template: Template name (critical-api, standard-api, etc.)
        interactive: Whether to prompt for missing values
        
    Returns:
        Exit code (0 for success, 1 for error)
    """
    print("🎉 Welcome to NthLayer!\n")
    
    # Load templates (built-in + custom)
    try:
        registry = CustomTemplateLoader.load_all_templates()
    except Exception as e:
        print(f"❌ Error loading templates: {e}")
        return 1
    
    # Interactive prompts if not provided
    if not service_name and interactive:
        service_name = input("Service name (lowercase-with-hyphens): ").strip()
    
    if not service_name:
        print("❌ Error: Service name is required")
        return 1
    
    # Validate service name format
    if not _is_valid_service_name(service_name):
        print(f"❌ Error: Invalid service name '{service_name}'")
        print("   Service name must be lowercase with hyphens (e.g., payment-api)")
        return 1
    
    if not team and interactive:
        team = input("Team name: ").strip()
    
    if not team:
        print("❌ Error: Team name is required")
        return 1
    
    # Show available templates
    if not template and interactive:
        print("\n📋 Available templates:")
        templates = registry.list()
        for i, tmpl in enumerate(templates, 1):
            print(f"  {i}. {tmpl.name}")
            print(f"     {tmpl.description}")
            print(f"     Resources: {len(tmpl.resources)}")
            print()
        
        while True:
            choice = input(f"Choose template (1-{len(templates)}): ").strip()
            try:
                idx = int(choice) - 1
                if 0 <= idx < len(templates):
                    template = templates[idx].name
                    break
                else:
                    print(f"   Please enter a number between 1 and {len(templates)}")
            except ValueError:
                print("   Please enter a valid number")
    
    if not template:
        print("❌ Error: Template is required")
        return 1
    
    # Validate template exists
    if not registry.exists(template):
        print(f"❌ Error: Unknown template '{template}'")
        print(f"   Available templates: {', '.join(registry.templates.keys())}")
        return 1
    
    template_obj = registry.get(template)
    
    # Create service file
    service_file = Path(f"{service_name}.yaml")
    if service_file.exists():
        print(f"\n❌ Error: {service_file} already exists")
        print("   Remove the existing file or choose a different service name")
        return 1
    
    # Generate service YAML content
    service_content = _generate_service_yaml(service_name, team, template_obj)
    
    try:
        service_file.write_text(service_content)
    except OSError as e:
        print(f"❌ Error creating service file: {e}")
        return 1
    
    # Create .nthlayer directory
    nthlayer_dir = Path(".nthlayer")
    try:
        nthlayer_dir.mkdir(exist_ok=True)
    except OSError as e:
        print(f"⚠️  Warning: Could not create .nthlayer directory: {e}")
    
    # Create config file if it doesn't exist
    config_file = nthlayer_dir / "config.yaml"
    if not config_file.exists():
        config_content = _generate_config_yaml()
        try:
            config_file.write_text(config_content)
        except OSError as e:
            print(f"⚠️  Warning: Could not create config file: {e}")
    
    # Success message
    print(f"\n✅ Created {service_file}")
    if nthlayer_dir.exists():
        print(f"✅ Created {nthlayer_dir}/")
    
    print("\n📋 Next steps:")
    print(f"  1. Review {service_file} and customize if needed")
    print(f"  2. Validate: nthlayer validate {service_file}")
    print(f"  3. Generate SLOs: nthlayer generate-slo {service_file}")
    print(f"  4. Setup PagerDuty: nthlayer setup-pagerduty {service_file} --api-key YOUR_KEY")
    print("\n💡 Pro tip: Run 'nthlayer --help' to see all commands")
    
    return 0


def _is_valid_service_name(name: str) -> bool:
    """Check if service name is valid (lowercase with hyphens).
    
    Args:
        name: Service name to validate
        
    Returns:
        True if valid
    """
    if not name:
        return False
    
    # Must be lowercase, numbers, and hyphens only
    # Must not start or end with hyphen
    if name[0] == '-' or name[-1] == '-':
        return False
    
    for char in name:
        if not (char.islower() or char.isdigit() or char == '-'):
            return False
    
    return True


def _generate_service_yaml(service_name: str, team: str, template) -> str:
    """Generate service YAML content.
    
    Args:
        service_name: Service name
        team: Team name
        template: ServiceTemplate object
        
    Returns:
        YAML content as string
    """
    return f"""# {service_name} Service Definition
# Generated by NthLayer

service:
  name: {service_name}
  team: {team}
  tier: {template.tier}     # critical | standard | low
  type: {template.type}     # api | background-job | pipeline | web | database
  template: {template.name}

# Template provides:
{_format_template_resources(template)}

# Optional: Override template defaults or add new resources
# resources:
#   - kind: SLO
#     name: latency-p95
#     spec:
#       threshold_ms: 300  # Override template default
#
#   - kind: Dependencies
#     name: upstream
#     spec:
#       services:
#         - name: user-service
#           criticality: high
"""


def _format_template_resources(template) -> str:
    """Format template resources as comments.
    
    Args:
        template: ServiceTemplate object
        
    Returns:
        Formatted comment block
    """
    lines = []
    for resource in template.resources:
        lines.append(f"#   - {resource.kind}: {resource.name}")
    return "\n".join(lines) if lines else "#   (no resources)"


def _generate_config_yaml() -> str:
    """Generate .nthlayer/config.yaml content.
    
    Returns:
        YAML content as string
    """
    return """# NthLayer Configuration
# This file configures project-wide settings for NthLayer

# Error budget configuration
error_budgets:
  # Enable inherited impact attribution (enterprise feature)
  # When true, attributes error budget burn to upstream service failures
  inherited_attribution: false
  
  # Minimum correlation confidence for attribution (0.0 to 1.0)
  min_correlation_confidence: 0.8
  
  # Time window for correlating incidents and deployments (minutes)
  time_window_minutes: 5

# Deployment gate thresholds (optional overrides)
# deployment_gates:
#   critical:
#     block_threshold: 0.10   # Block deploys if >10% budget consumed
#     warn_threshold: 0.20    # Warn if >20% consumed
#   standard:
#     warn_threshold: 0.20
"""
