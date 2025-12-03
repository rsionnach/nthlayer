"""Template loader for NthLayer service templates."""

from pathlib import Path
from typing import Dict

import yaml

from .models import Resource
from .templates import ServiceTemplate, TemplateRegistry


class TemplateLoader:
    """Loads service templates from YAML files."""
    
    @staticmethod
    def load_from_file(path: Path) -> ServiceTemplate:
        """Load single template from YAML file.
        
        Args:
            path: Path to template YAML file
            
        Returns:
            ServiceTemplate object
            
        Raises:
            FileNotFoundError: If template file doesn't exist
            ValueError: If template YAML is invalid
        """
        if not path.exists():
            raise FileNotFoundError(f"Template file not found: {path}")
        
        with open(path) as f:
            data = yaml.safe_load(f)
        
        if not data:
            raise ValueError(f"Empty template file: {path}")
        
        # Validate required fields
        required = ["name", "description", "tier", "type"]
        for field in required:
            if field not in data:
                raise ValueError(f"Missing required field '{field}' in template: {path}")
        
        # Parse resources (no context yet - added during application)
        resources = []
        for resource_data in data.get("resources", []):
            # Create resource without context (will be added when applied)
            resource = Resource(
                kind=resource_data["kind"],
                name=resource_data["name"],
                spec=resource_data.get("spec", {}),
                context=None  # Context added when template is applied
            )
            resources.append(resource)
        
        return ServiceTemplate(
            name=data["name"],
            description=data["description"],
            tier=data["tier"],
            type=data["type"],
            resources=resources
        )
    
    @staticmethod
    def load_builtin() -> TemplateRegistry:
        """Load all built-in templates from builtin_templates directory.
        
        Returns:
            TemplateRegistry with all built-in templates
            
        Raises:
            RuntimeError: If builtin templates directory doesn't exist
        """
        templates_dir = Path(__file__).parent / "builtin_templates"
        
        if not templates_dir.exists():
            raise RuntimeError(f"Built-in templates directory not found: {templates_dir}")
        
        templates: Dict[str, ServiceTemplate] = {}
        
        for yaml_file in sorted(templates_dir.glob("*.yaml")):
            try:
                template = TemplateLoader.load_from_file(yaml_file)
                templates[template.name] = template
            except Exception as e:
                # Log warning but continue loading other templates
                print(f"Warning: Failed to load template {yaml_file.name}: {e}")
        
        return TemplateRegistry(templates=templates)
