"""
Service YAML parser.

Parses service definition files with implicit service context.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from nthlayer.specs.custom_templates import CustomTemplateLoader
from nthlayer.specs.environment_merger import EnvironmentMerger
from nthlayer.specs.environments import EnvironmentLoader
from nthlayer.specs.models import Resource, ServiceContext
from nthlayer.specs.template import substitute_variables
from nthlayer.specs.templates import TemplateRegistry
from nthlayer.specs.variable_substitution import substitute_variables as substitute_env_variables


class ServiceParseError(Exception):
    """Raised when service YAML parsing fails."""


def parse_service_file(
    file_path: str | Path,
    template_registry: TemplateRegistry | None = None,
    environment: str | None = None
) -> tuple[ServiceContext, list[Resource]]:
    """
    Parse service YAML file with optional environment overrides.
    
    Expected structure:
        service:
          name: my-service
          team: my-team
          tier: critical
          type: api
        
        resources:
          - kind: SLO
            name: availability
            spec:
              objective: 99.9
    
    Environment overrides (optional):
        environments/dev.yaml:
          environment: dev
          service:
            tier: low
          resources:
            - kind: SLO
              name: availability
              spec:
                objective: 99.0
    
    Args:
        file_path: Path to service YAML file
        template_registry: Optional template registry
        environment: Optional environment name (dev, staging, prod)
    
    Returns:
        Tuple of (service_context, resources)
    
    Raises:
        ServiceParseError: If parsing fails or required fields missing
    """
    file_path = Path(file_path)
    
    if not file_path.exists():
        raise ServiceParseError(f"Service file not found: {file_path}")
    
    # Load base file
    try:
        with open(file_path) as f:
            data = yaml.safe_load(f)
    except yaml.YAMLError as e:
        raise ServiceParseError(f"Invalid YAML in {file_path}: {e}") from e
    
    # If environment specified, load and merge environment overrides
    if environment:
        env_file = EnvironmentLoader.find_environment_file(file_path, environment)
        if env_file:
            try:
                with open(env_file) as f:
                    env_data = yaml.safe_load(f)
                
                # Merge environment overrides into base data
                data = EnvironmentMerger.merge_service_config(data, env_data)
            except Exception as e:
                raise ServiceParseError(
                    f"Error loading environment '{environment}' from {env_file}: {e}"
                ) from e
    
    if not isinstance(data, dict):
        raise ServiceParseError(f"Service file must be a YAML dictionary: {file_path}")
    
    # Apply variable substitution if environment is specified
    # Do this before parsing to substitute throughout the config
    if environment:
        # First pass: get service name and team for variable context
        service_name = data.get("service", {}).get("name", "")
        team = data.get("service", {}).get("team", "")
        
        # Substitute variables throughout the entire config
        data = substitute_env_variables(
            data,
            environment=environment,
            service_name=service_name,
            team=team
        )
    
    # Parse service context (required)
    if "service" not in data:
        raise ServiceParseError(
            f"Missing required 'service' section in {file_path}"
        )
    
    service_data = data["service"]
    if not isinstance(service_data, dict):
        raise ServiceParseError(
            f"'service' section must be a dictionary in {file_path}"
        )
    
    try:
        service_context = ServiceContext(
            name=service_data.get("name", ""),
            team=service_data.get("team", ""),
            tier=service_data.get("tier", ""),
            type=service_data.get("type", ""),
            language=service_data.get("language"),
            framework=service_data.get("framework"),
            template=service_data.get("template"),
            environment=environment,  # Set runtime environment
            metadata=service_data.get("metadata", {}),
        )
    except (ValueError, TypeError) as e:
        raise ServiceParseError(
            f"Invalid service context in {file_path}: {e}"
        ) from e
    
    # Load template resources if template is specified
    template_resources: list[Resource] = []
    
    if service_context.template:
        if template_registry is None:
            # Load both built-in and custom templates
            template_registry = CustomTemplateLoader.load_all_templates()
        
        template = template_registry.get(service_context.template)
        if template is None:
            raise ServiceParseError(
                f"Unknown template '{service_context.template}' in {file_path}. "
                f"Available templates: {', '.join(template_registry.templates.keys())}"
            )
        
        # Clone template resources with service context
        for resource in template.resources:
            template_resources.append(Resource(
                kind=resource.kind,
                name=resource.name,
                spec=resource.spec.copy(),
                context=service_context,
            ))
    
    # Parse user-defined resources (optional)
    user_resources: list[Resource] = []
    
    if "resources" in data:
        resources_data = data["resources"]
        
        if not isinstance(resources_data, list):
            raise ServiceParseError(
                f"'resources' must be a list in {file_path}"
            )
        
        for i, resource_data in enumerate(resources_data):
            if not isinstance(resource_data, dict):
                raise ServiceParseError(
                    f"Resource {i} must be a dictionary in {file_path}"
                )
            
            try:
                resource = Resource(
                    kind=resource_data.get("kind", ""),
                    name=resource_data.get("name"),
                    spec=resource_data.get("spec", {}),
                    context=service_context,  # Inject context
                )
                user_resources.append(resource)
            except (ValueError, TypeError) as e:
                raise ServiceParseError(
                    f"Invalid resource {i} in {file_path}: {e}"
                ) from e
    
    # Merge resources: user resources override template by name
    merged_resources = _merge_resources(template_resources, user_resources)
    
    return service_context, merged_resources


def _merge_resources(
    template_resources: list[Resource],
    user_resources: list[Resource]
) -> list[Resource]:
    """
    Merge template and user resources.
    
    User resources with the same (kind, name) override template resources.
    This allows users to customize specific template resources while keeping others.
    
    Args:
        template_resources: Resources from template
        user_resources: Resources from user YAML
    
    Returns:
        Merged list of resources (user overrides template)
    """
    # Build index by (kind, name)
    merged: dict[tuple[str, str], Resource] = {}
    
    # Start with template resources
    for resource in template_resources:
        key = (resource.kind, resource.name)
        merged[key] = resource
    
    # User resources override template
    for resource in user_resources:
        key = (resource.kind, resource.name)
        merged[key] = resource
    
    # Return in stable order (template order first, then new user resources)
    result: list[Resource] = []
    seen_keys: set[tuple[str, str]] = set()
    
    # Add template resources (possibly overridden)
    for resource in template_resources:
        key = (resource.kind, resource.name)
        result.append(merged[key])
        seen_keys.add(key)
    
    # Add new user resources not in template
    for resource in user_resources:
        key = (resource.kind, resource.name)
        if key not in seen_keys:
            result.append(resource)
    
    return result


def render_resource_spec(
    resource: Resource,
) -> dict[str, Any]:
    """
    Render resource spec with template variable substitution.
    
    Substitutes all {{ .variable }} patterns with values from
    the resource's service context.
    
    Args:
        resource: Resource with context
    
    Returns:
        Rendered spec with variables substituted
    
    Examples:
        >>> resource = Resource(
        ...     kind="SLO",
        ...     name="availability",
        ...     spec={"query": "service={{ .service }}"},
        ...     context=ServiceContext(name="payment-api", ...),
        ... )
        >>> render_resource_spec(resource)
        {"query": "service=payment-api"}
    """
    if not resource.context:
        raise ValueError("Resource has no context for template substitution")
    
    context_vars = resource.context.to_dict()
    
    return substitute_variables(resource.spec, context_vars)
