"""
Service specification parsing and validation.

Parses NthLayer service YAML files with implicit service context.
"""

from nthlayer.specs.parser import parse_service_file, ServiceContext, Resource
from nthlayer.specs.validator import validate_service_file, ValidationResult

__all__ = [
    "parse_service_file",
    "ServiceContext",
    "Resource",
    "validate_service_file",
    "ValidationResult",
]
