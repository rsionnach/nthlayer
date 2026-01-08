"""
Unified error handling for NthLayer CLI commands.

This module provides standardized error handling, exit codes, and
error reporting for all CLI commands.

Exit Codes:
- 0: Success
- 1: Warning (advisory, operation succeeded with warnings)
- 2: Blocked (operation blocked, e.g., by deployment gate)
- 10: Configuration error
- 11: Provider error (external service failure)
- 12: Validation error
- 127: Unknown/internal error
"""

from __future__ import annotations

import functools
import sys
import traceback
from enum import IntEnum
from typing import Any, Callable, TypeVar

import structlog

logger = structlog.get_logger()


class ExitCode(IntEnum):
    """Standardized exit codes for CLI commands."""

    SUCCESS = 0
    WARNING = 1
    BLOCKED = 2
    CONFIG_ERROR = 10
    PROVIDER_ERROR = 11
    VALIDATION_ERROR = 12
    UNKNOWN_ERROR = 127


class NthLayerError(Exception):
    """Base exception for NthLayer errors with exit code support."""

    exit_code: ExitCode = ExitCode.UNKNOWN_ERROR
    show_traceback: bool = False

    def __init__(self, message: str, details: dict[str, Any] | None = None):
        super().__init__(message)
        self.message = message
        self.details = details or {}


class ConfigurationError(NthLayerError):
    """Raised for configuration-related errors."""

    exit_code = ExitCode.CONFIG_ERROR


class ProviderError(NthLayerError):
    """Raised when an external provider/service fails."""

    exit_code = ExitCode.PROVIDER_ERROR


class ValidationError(NthLayerError):
    """Raised for validation failures."""

    exit_code = ExitCode.VALIDATION_ERROR


class BlockedError(NthLayerError):
    """Raised when an operation is blocked (e.g., by deployment gate)."""

    exit_code = ExitCode.BLOCKED


class WarningResult(NthLayerError):
    """Raised to indicate success with warnings."""

    exit_code = ExitCode.WARNING


# Type variable for decorated functions
F = TypeVar("F", bound=Callable[..., int])


def main_with_error_handling(
    *,
    show_traceback: bool = False,
    log_errors: bool = True,
) -> Callable[[F], F]:
    """
    Decorator for CLI main functions that provides unified error handling.

    Catches exceptions and converts them to appropriate exit codes with
    consistent error reporting.

    Args:
        show_traceback: If True, show full traceback for unexpected errors
        log_errors: If True, log errors to structlog

    Usage:
        @main_with_error_handling()
        def my_command() -> int:
            # command implementation
            return 0

    Exit codes:
        - NthLayerError subclasses: Uses the error's exit_code
        - KeyboardInterrupt: Returns 130 (standard for SIGINT)
        - Other exceptions: Returns 127 (unknown error)
    """

    def decorator(func: F) -> F:
        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> int:
            try:
                return func(*args, **kwargs)
            except NthLayerError as e:
                if log_errors:
                    logger.error(
                        "command_error",
                        error_type=type(e).__name__,
                        message=e.message,
                        exit_code=e.exit_code,
                        **e.details,
                    )
                if e.show_traceback or show_traceback:
                    traceback.print_exc(file=sys.stderr)
                return e.exit_code
            except KeyboardInterrupt:
                if log_errors:
                    logger.info("command_interrupted")
                return 130  # Standard exit code for SIGINT
            except Exception as e:
                if log_errors:
                    logger.error(
                        "unexpected_error",
                        error_type=type(e).__name__,
                        message=str(e),
                        exit_code=ExitCode.UNKNOWN_ERROR,
                    )
                if show_traceback:
                    traceback.print_exc(file=sys.stderr)
                return ExitCode.UNKNOWN_ERROR

        return wrapper  # type: ignore[return-value]

    return decorator


def format_error_message(error: NthLayerError) -> str:
    """Format an error message for display to users."""
    msg = error.message
    if error.details:
        detail_str = ", ".join(f"{k}={v}" for k, v in error.details.items())
        msg = f"{msg} ({detail_str})"
    return msg


def exit_with_error(error: NthLayerError) -> None:
    """Print error and exit with appropriate code."""
    from nthlayer.cli.ux import error as print_error

    print_error(format_error_message(error))
    sys.exit(error.exit_code)
