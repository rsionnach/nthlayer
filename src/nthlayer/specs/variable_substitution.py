"""Variable substitution for service configurations.

Supports substitution of:
- ${env} - Environment name
- ${service} - Service name
- ${team} - Team name
"""

import re
from typing import Any, Dict, Optional


class VariableSubstitutor:
    """Handles variable substitution in service configurations."""
    
    def __init__(
        self,
        environment: Optional[str] = None,
        service_name: Optional[str] = None,
        team: Optional[str] = None
    ):
        """Initialize substitutor with context variables.
        
        Args:
            environment: Environment name (dev, staging, prod)
            service_name: Service name
            team: Team name
        """
        self.variables = {
            "env": environment or "",
            "service": service_name or "",
            "team": team or "",
        }
    
    def substitute(self, value: Any) -> Any:
        """Recursively substitute variables in a value.
        
        Supports:
        - Strings: "availability-${env}" → "availability-prod"
        - Dicts: Recursively processes all values
        - Lists: Recursively processes all items
        - Other types: Returned unchanged
        
        Args:
            value: Value to process
            
        Returns:
            Value with variables substituted
            
        Example:
            >>> sub = VariableSubstitutor(environment="prod", service_name="payment-api")
            >>> sub.substitute("slo-${service}-${env}")
            'slo-payment-api-prod'
        """
        if isinstance(value, str):
            return self._substitute_string(value)
        elif isinstance(value, dict):
            return {k: self.substitute(v) for k, v in value.items()}
        elif isinstance(value, list):
            return [self.substitute(item) for item in value]
        else:
            # Numbers, booleans, None, etc. - return unchanged
            return value
    
    def _substitute_string(self, text: str) -> str:
        """Substitute variables in a string.
        
        Replaces ${var} with the value of self.variables['var'].
        
        Args:
            text: String containing variables
            
        Returns:
            String with variables replaced
        """
        def replace_var(match):
            var_name = match.group(1)
            return self.variables.get(var_name, match.group(0))
        
        # Replace ${var} patterns
        return re.sub(r'\$\{(\w+)\}', replace_var, text)


def substitute_variables(
    data: Dict[str, Any],
    environment: Optional[str] = None,
    service_name: Optional[str] = None,
    team: Optional[str] = None
) -> Dict[str, Any]:
    """Substitute variables throughout a configuration dictionary.
    
    Convenience function for one-shot substitution.
    
    Args:
        data: Configuration dictionary
        environment: Environment name
        service_name: Service name
        team: Team name
        
    Returns:
        Configuration with variables substituted
        
    Example:
        >>> config = {
        ...     "service": {"name": "api", "metadata": {"env": "${env}"}},
        ...     "resources": [{"name": "slo-${env}"}]
        ... }
        >>> substitute_variables(config, environment="prod")
        {'service': {'name': 'api', 'metadata': {'env': 'prod'}}, 'resources': [{'name': 'slo-prod'}]}
    """
    substitutor = VariableSubstitutor(
        environment=environment,
        service_name=service_name,
        team=team
    )
    return substitutor.substitute(data)
