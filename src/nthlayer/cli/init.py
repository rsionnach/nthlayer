"""CLI command for initializing new NthLayer services."""

from pathlib import Path

from nthlayer.cli.ux import (
    console,
    error,
    header,
    info,
    multi_select,
    select,
    success,
    text_input,
    warning,
)
from nthlayer.core.tiers import TIER_CONFIGS
from nthlayer.specs.custom_templates import CustomTemplateLoader

# Service type descriptions
SERVICE_TYPES = {
    "api": "REST/GraphQL API service",
    "worker": "Background job processor",
    "stream": "Stream processing service (Kafka, etc.)",
    "web": "Web application (frontend)",
    "batch": "Batch processing job",
    "ml": "Machine learning/AI service",
}

# Map user-friendly service types to template types
SERVICE_TYPE_TO_TEMPLATE_TYPE = {
    "api": "api",
    "worker": "background-job",
    "stream": "pipeline",
    "web": "web",
    "batch": "pipeline",
    "ml": "api",  # ML services often have API interfaces
}

# Tier descriptions derived from centralized config
TIERS = {name: config.display_name for name, config in TIER_CONFIGS.items()}

# Common dependencies
DEPENDENCIES = [
    "postgresql",
    "mysql",
    "redis",
    "mongodb",
    "elasticsearch",
    "kafka",
    "rabbitmq",
    "dynamodb",
]


def init_command(
    service_name: str | None = None,
    team: str | None = None,
    template: str | None = None,
    interactive: bool = True,
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
    header("Initialize NthLayer Service")
    console.print()
    console.print("[muted]Create a new service.yaml with interactive prompts[/muted]")
    console.print()

    # Load templates (built-in + custom)
    try:
        registry = CustomTemplateLoader.load_all_templates()
    except Exception as e:
        error(f"Error loading templates: {e}")
        return 1

    # Interactive prompts using questionary/gum
    if not service_name and interactive:
        service_name = text_input(
            "Service name",
            placeholder="lowercase-with-hyphens (e.g., payment-api)",
        )

    if not service_name:
        error("Service name is required")
        return 1

    # Validate service name format
    if not _is_valid_service_name(service_name):
        error(f"Invalid service name '{service_name}'")
        console.print(
            "   [muted]Service name must be lowercase with hyphens (e.g., payment-api)[/muted]"
        )
        return 1

    if not team and interactive:
        team = text_input("Team name", placeholder="e.g., platform, payments")

    if not team:
        error("Team name is required")
        return 1

    # Select service tier using interactive menu
    tier = None
    if interactive:
        tier_choices = [f"{k} - {v}" for k, v in TIERS.items()]
        selected_tier = select("Service tier", tier_choices, default=tier_choices[1])
        tier = selected_tier.split(" - ")[0]

    # Select service type using interactive menu
    service_type = None
    if interactive:
        type_choices = [f"{k} - {v}" for k, v in SERVICE_TYPES.items()]
        selected_type = select("Service type", type_choices, default=type_choices[0])
        service_type = selected_type.split(" - ")[0]

    # Select dependencies using multi-select
    dependencies = []
    if interactive:
        console.print()
        console.print(
            "[muted]Select service dependencies (space to toggle, enter to confirm)[/muted]"
        )
        dependencies = multi_select("Dependencies", DEPENDENCIES)

    # Template selection (optional - filter by service type if selected)
    if not template and interactive:
        templates = registry.list()
        # Filter templates by service type if one was selected
        if service_type and templates:
            template_type = SERVICE_TYPE_TO_TEMPLATE_TYPE.get(service_type, service_type)
            templates = [t for t in templates if t.type == template_type]
        if templates:
            template_choices = [f"{t.name} - {t.description}" for t in templates]
            template_choices.insert(0, "none - Generate from selections above")
            selected = select("Use template?", template_choices)
            if not selected.startswith("none"):
                template = selected.split(" - ")[0]

    # Get template object if specified
    template_obj = None
    if template:
        if not registry.exists(template):
            error(f"Unknown template '{template}'")
            console.print(
                f"   [muted]Available templates: {', '.join(registry.templates.keys())}[/muted]"
            )
            return 1
        template_obj = registry.get(template)
        # Use template's tier and type if not explicitly selected
        if template_obj:
            if not tier:
                tier = template_obj.tier
            if not service_type:
                service_type = template_obj.type

    # Default values if still not set
    tier = tier or "standard"
    service_type = service_type or "api"

    # Create service file
    service_file = Path(f"{service_name}.yaml")
    if service_file.exists():
        console.print()
        error(f"{service_file} already exists")
        console.print(
            "   [muted]Remove the existing file or choose a different service name[/muted]"
        )
        return 1

    # Generate service YAML content
    service_content = _generate_service_yaml_v2(
        service_name, team, tier, service_type, dependencies, template_obj
    )

    try:
        service_file.write_text(service_content)
    except OSError as e:
        error(f"Error creating service file: {e}")
        return 1

    # Create .nthlayer directory
    nthlayer_dir = Path(".nthlayer")
    try:
        nthlayer_dir.mkdir(exist_ok=True)
    except OSError as e:
        warning(f"Could not create .nthlayer directory: {e}")

    # Create config file if it doesn't exist
    config_file = nthlayer_dir / "config.yaml"
    if not config_file.exists():
        config_content = _generate_config_yaml()
        try:
            config_file.write_text(config_content)
        except OSError as e:
            warning(f"Could not create config file: {e}")

    # Success message
    console.print()
    success(f"Created {service_file}")
    if nthlayer_dir.exists():
        success(f"Created {nthlayer_dir}/")

    console.print()
    console.print("[bold]Next steps:[/bold]")
    console.print(f"  [muted]1.[/muted] Review {service_file} and customize if needed")
    console.print(f"  [muted]2.[/muted] Validate: [info]nthlayer validate {service_file}[/info]")
    console.print(
        f"  [muted]3.[/muted] Generate SLOs: [info]nthlayer generate-slo {service_file}[/info]"
    )
    console.print(
        f"  [muted]4.[/muted] Setup PagerDuty: "
        f"[info]nthlayer setup-pagerduty {service_file} --api-key YOUR_KEY[/info]"
    )
    console.print()
    info("Pro tip: Run 'nthlayer --help' to see all commands")

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
    if name[0] == "-" or name[-1] == "-":
        return False

    for char in name:
        if not (char.islower() or char.isdigit() or char == "-"):
            return False

    return True


def _generate_service_yaml_v2(
    service_name: str,
    team: str,
    tier: str,
    service_type: str,
    dependencies: list[str],
    template=None,
) -> str:
    """Generate service YAML content with all parameters.

    Args:
        service_name: Service name
        team: Team name
        tier: Service tier (critical, standard, low)
        service_type: Service type (api, worker, stream, etc.)
        dependencies: List of dependency names
        template: Optional ServiceTemplate object

    Returns:
        YAML content as string
    """
    # Build resources section
    resources_yaml = _build_resources_yaml(service_name, tier, service_type, dependencies)

    # Template line if using a template
    template_line = f"  template: {template.name}\n" if template else ""

    return f"""# {service_name} Service Definition
# Generated by NthLayer

service:
  name: {service_name}
  team: {team}
  tier: {tier}
  type: {service_type}
{template_line}
resources:
{resources_yaml}
"""


def _build_resources_yaml(
    service_name: str,
    tier: str,
    service_type: str,
    dependencies: list[str],
) -> str:
    """Build the resources YAML section.

    Args:
        service_name: Service name
        tier: Service tier
        service_type: Service type
        dependencies: List of dependency names

    Returns:
        YAML content for resources
    """
    resources = []

    # Add SLO based on tier
    if tier == "critical":
        resources.append(
            """  # Availability SLO - critical tier
  - kind: SLO
    name: availability
    spec:
      objective: 99.95
      window: 30d
      indicator:
        type: availability"""
        )
    else:
        resources.append(
            """  # Availability SLO
  - kind: SLO
    name: availability
    spec:
      objective: 99.9
      window: 30d
      indicator:
        type: availability"""
        )

    # Add latency SLO for API types
    if service_type in ("api", "web"):
        resources.append(
            """
  # Latency SLO - p95
  - kind: SLO
    name: latency-p95
    spec:
      objective: 99.0
      window: 30d
      indicator:
        type: latency
        percentile: 95
        threshold_ms: 500"""
        )

    # Add PagerDuty for critical tier
    if tier == "critical":
        resources.append(
            """
  # PagerDuty integration
  - kind: PagerDuty
    name: primary
    spec:
      urgency: high
      auto_create: true"""
        )

    # Add dependencies if selected
    if dependencies:
        db_deps = [d for d in dependencies if d in ("postgresql", "mysql", "mongodb", "dynamodb")]
        cache_deps = [d for d in dependencies if d in ("redis", "elasticsearch")]
        queue_deps = [d for d in dependencies if d in ("kafka", "rabbitmq")]

        deps_yaml = """
  # Service dependencies
  - kind: Dependencies
    name: infrastructure
    spec:"""

        if db_deps:
            deps_yaml += "\n      databases:"
            for db in db_deps:
                deps_yaml += f"""
        - name: {service_name}-{db}
          type: {db}
          criticality: high"""

        if cache_deps:
            deps_yaml += "\n      caches:"
            for cache in cache_deps:
                deps_yaml += f"""
        - name: {service_name}-{cache}
          type: {cache}
          criticality: medium"""

        if queue_deps:
            deps_yaml += "\n      queues:"
            for queue in queue_deps:
                deps_yaml += f"""
        - name: {service_name}-{queue}
          type: {queue}
          criticality: high"""

        resources.append(deps_yaml)

    return "\n".join(resources)


def _generate_service_yaml(service_name: str, team: str, template) -> str:
    """Generate service YAML content (legacy).

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
