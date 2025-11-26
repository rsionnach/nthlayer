"""
Code generators for various formats.

Generates SLO configs, Prometheus rules, etc. from service definitions.
"""

from nthlayer.generators.sloth import generate_sloth_spec, SlothGenerationResult

__all__ = [
    "generate_sloth_spec",
    "SlothGenerationResult",
]
