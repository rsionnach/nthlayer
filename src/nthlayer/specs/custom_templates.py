"""Custom template support for NthLayer.

Allows users to create organization-specific templates in .nthlayer/templates/
that override or extend the built-in templates.
"""

from pathlib import Path
from typing import Dict, Optional

from .template_loader import TemplateLoader
from .templates import ServiceTemplate, TemplateRegistry


class CustomTemplateLoader:
    """Loads custom templates from project directory."""
    
    @staticmethod
    def find_templates_directory() -> Optional[Path]:
        """Find .nthlayer/templates directory in current or parent directories.
        
        Searches upward from current directory to find .nthlayer/templates/
        
        Returns:
            Path to templates directory if found, None otherwise
        """
        current = Path.cwd()
        
        # Search upward for .nthlayer/templates
        for parent in [current] + list(current.parents):
            templates_dir = parent / ".nthlayer" / "templates"
            if templates_dir.exists() and templates_dir.is_dir():
                return templates_dir
        
        return None
    
    @staticmethod
    def load_custom_templates() -> Dict[str, ServiceTemplate]:
        """Load all custom templates from .nthlayer/templates directory.
        
        Returns:
            Dictionary mapping template name to ServiceTemplate
        """
        templates_dir = CustomTemplateLoader.find_templates_directory()
        
        if not templates_dir:
            return {}
        
        custom_templates = {}
        
        for yaml_file in sorted(templates_dir.glob("*.yaml")):
            try:
                template = TemplateLoader.load_from_file(yaml_file)
                custom_templates[template.name] = template
            except Exception as e:
                # Log warning but continue loading other templates
                print(f"⚠️  Warning: Failed to load custom template {yaml_file.name}: {e}")
        
        return custom_templates
    
    @staticmethod
    def load_all_templates() -> TemplateRegistry:
        """Load built-in and custom templates with custom taking precedence.
        
        Returns:
            TemplateRegistry with all templates (custom override built-in)
        """
        # Start with built-in templates
        builtin_registry = TemplateLoader.load_builtin()
        all_templates = builtin_registry.templates.copy()
        
        # Load custom templates (override built-in)
        custom_templates = CustomTemplateLoader.load_custom_templates()
        
        if custom_templates:
            # Custom templates override built-in
            all_templates.update(custom_templates)
            
            # Show which templates were overridden
            overridden = set(custom_templates.keys()) & set(builtin_registry.templates.keys())
            if overridden:
                for name in overridden:
                    print(f"📝 Using custom template '{name}' (overrides built-in)")
        
        return TemplateRegistry(templates=all_templates)
    
    @staticmethod
    def get_template_source(template_name: str) -> str:
        """Get the source of a template (built-in or custom).
        
        Args:
            template_name: Name of template
            
        Returns:
            'built-in', 'custom', or 'unknown'
        """
        builtin = TemplateLoader.load_builtin()
        custom = CustomTemplateLoader.load_custom_templates()
        
        if template_name in custom:
            return 'custom'
        elif template_name in builtin.templates:
            return 'built-in'
        else:
            return 'unknown'
