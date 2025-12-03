"""Environment configuration merging logic.

Handles deep merging of base service config with environment-specific overrides.
"""

from copy import deepcopy
from pathlib import Path
from typing import Any, Dict, List

import yaml


class EnvironmentMerger:
    """Merges base service configuration with environment overrides."""
    
    @staticmethod
    def merge_service_config(
        base_data: Dict[str, Any],
        env_overrides: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Merge base service config with environment overrides.
        
        Args:
            base_data: Base service YAML data (full dict with 'service' and 'resources')
            env_overrides: Environment override data (with 'service' and 'resources')
            
        Returns:
            Merged configuration
        """
        result = deepcopy(base_data)
        
        # Merge service-level fields
        if "service" in env_overrides:
            result["service"] = EnvironmentMerger._merge_dict(
                result.get("service", {}),
                env_overrides["service"]
            )
        
        # Merge resources
        if "resources" in env_overrides:
            result["resources"] = EnvironmentMerger._merge_resources(
                result.get("resources", []),
                env_overrides["resources"]
            )
        
        return result
    
    @staticmethod
    def _merge_dict(base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
        """Deep merge two dictionaries (override wins).
        
        Args:
            base: Base dictionary
            override: Override dictionary
            
        Returns:
            Merged dictionary
        """
        result = deepcopy(base)
        
        for key, value in override.items():
            if key in result and isinstance(result[key], dict) and isinstance(value, dict):
                # Recursive merge for nested dicts
                result[key] = EnvironmentMerger._merge_dict(result[key], value)
            else:
                # Override value
                result[key] = deepcopy(value)
        
        return result
    
    @staticmethod
    def _merge_resources(
        base_resources: List[Dict[str, Any]],
        override_resources: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """Merge resource lists (override by kind+name).
        
        Args:
            base_resources: Base resources list
            override_resources: Override resources list
            
        Returns:
            Merged resources list
        """
        # Index base resources by (kind, name)
        indexed = {}
        for resource in base_resources:
            key = (resource.get("kind"), resource.get("name"))
            indexed[key] = deepcopy(resource)
        
        # Apply overrides
        for override_resource in override_resources:
            key = (override_resource.get("kind"), override_resource.get("name"))
            
            if key in indexed:
                # Merge spec (deep merge)
                if "spec" in override_resource:
                    indexed[key]["spec"] = EnvironmentMerger._merge_dict(
                        indexed[key].get("spec", {}),
                        override_resource["spec"]
                    )
                
                # Other fields override completely
                for field in ["kind", "name"]:
                    if field in override_resource:
                        indexed[key][field] = override_resource[field]
            else:
                # New resource in environment
                indexed[key] = deepcopy(override_resource)
        
        # Return resources in stable order
        result = []
        seen_keys = set()
        
        # First, add base resources (possibly overridden)
        for resource in base_resources:
            key = (resource.get("kind"), resource.get("name"))
            result.append(indexed[key])
            seen_keys.add(key)
        
        # Then add new resources from override
        for override_resource in override_resources:
            key = (override_resource.get("kind"), override_resource.get("name"))
            if key not in seen_keys:
                result.append(indexed[key])
        
        return result
    
    @staticmethod
    def merge_environment(
        base_file: Path,
        env_file: Path
    ) -> Dict[str, Any]:
        """Merge base service file with environment override file.
        
        Args:
            base_file: Path to base service YAML
            env_file: Path to environment override YAML
            
        Returns:
            Merged configuration dict
        """
        # Load base
        with open(base_file) as f:
            base_data = yaml.safe_load(f)
        
        # Load environment
        with open(env_file) as f:
            env_data = yaml.safe_load(f)
        
        # Merge
        return EnvironmentMerger.merge_service_config(base_data, env_data)
