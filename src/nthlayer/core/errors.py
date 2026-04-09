"""
Re-export shim — canonical source is nthlayer_common.errors.

This shim maintains backward compatibility during the ecosystem migration.
All consumers within nthlayer can continue to import from nthlayer.core.errors.

Note: exit_with_error stays here because it imports nthlayer.cli.ux (generate-only).
"""

from __future__ import annotations

import sys

from nthlayer_common.errors import (  # noqa: F401
    BlockedError,
    ConfigurationError,
    ExitCode,
    NthLayerError,
    PolicyAuditError,
    ProviderError,
    ValidationError,
    WarningResult,
    format_error_message,
    main_with_error_handling,
)

# Re-exports from nthlayer_common.errors
__all__ = [
    "ExitCode",
    "NthLayerError",
    "ConfigurationError",
    "ProviderError",
    "ValidationError",
    "BlockedError",
    "PolicyAuditError",
    "WarningResult",
    "main_with_error_handling",
    "format_error_message",
]

# Local to this shim — imports nthlayer.cli.ux (generate-only)
__all__ += ["exit_with_error"]


def exit_with_error(error: NthLayerError) -> None:
    """Print error and exit with appropriate code.

    This function stays in generate because it imports nthlayer.cli.ux,
    which is a generate-only CLI concern.
    """
    from nthlayer.cli.ux import error as print_error

    print_error(format_error_message(error))
    sys.exit(error.exit_code)
