"""
Service specification parsing and validation.

Parses NthLayer service YAML files with implicit service context.
"""

from nthlayer.specs.parser import Resource, ServiceContext, parse_service_file
from nthlayer.specs.validator import ValidationResult, validate_service_file

__all__ = [
    "parse_service_file",
    "ServiceContext",
    "Resource",
    "validate_service_file",
    "ValidationResult",
]
