"""
Code generators for various formats.

Generates SLO configs, Prometheus rules, etc. from service definitions.
"""

from nthlayer.generators.sloth import SlothGenerationResult, generate_sloth_spec

__all__ = [
    "generate_sloth_spec",
    "SlothGenerationResult",
]
