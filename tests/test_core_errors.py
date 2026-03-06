"""Tests for nthlayer.core.errors module."""

from __future__ import annotations

import pytest

from nthlayer.core.errors import (
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


class TestExitCode:
    """Tests for ExitCode IntEnum."""

    def test_success_value(self) -> None:
        assert ExitCode.SUCCESS == 0

    def test_warning_value(self) -> None:
        assert ExitCode.WARNING == 1

    def test_blocked_value(self) -> None:
        assert ExitCode.BLOCKED == 2

    def test_config_error_value(self) -> None:
        assert ExitCode.CONFIG_ERROR == 10

    def test_provider_error_value(self) -> None:
        assert ExitCode.PROVIDER_ERROR == 11

    def test_validation_error_value(self) -> None:
        assert ExitCode.VALIDATION_ERROR == 12

    def test_unknown_error_value(self) -> None:
        assert ExitCode.UNKNOWN_ERROR == 127

    def test_int_coercion(self) -> None:
        assert int(ExitCode.BLOCKED) == 2
        assert int(ExitCode.UNKNOWN_ERROR) == 127

    def test_is_int_subclass(self) -> None:
        assert isinstance(ExitCode.SUCCESS, int)


class TestNthLayerError:
    """Tests for NthLayerError base class."""

    def test_is_exception(self) -> None:
        err = NthLayerError("boom")
        assert isinstance(err, Exception)

    def test_message_attribute(self) -> None:
        err = NthLayerError("something broke")
        assert err.message == "something broke"

    def test_str_representation(self) -> None:
        err = NthLayerError("something broke")
        assert str(err) == "something broke"

    def test_default_details_empty_dict(self) -> None:
        err = NthLayerError("boom")
        assert err.details == {}

    def test_details_stored(self) -> None:
        err = NthLayerError("boom", details={"service": "api", "code": 500})
        assert err.details == {"service": "api", "code": 500}

    def test_default_exit_code(self) -> None:
        assert NthLayerError.exit_code == ExitCode.UNKNOWN_ERROR

    def test_default_show_traceback(self) -> None:
        assert NthLayerError.show_traceback is False


class TestErrorSubclasses:
    """Tests that each subclass maps to the correct exit code."""

    @pytest.mark.parametrize(
        ("cls", "expected_exit_code"),
        [
            (ConfigurationError, ExitCode.CONFIG_ERROR),
            (ProviderError, ExitCode.PROVIDER_ERROR),
            (ValidationError, ExitCode.VALIDATION_ERROR),
            (BlockedError, ExitCode.BLOCKED),
            (PolicyAuditError, ExitCode.VALIDATION_ERROR),
            (WarningResult, ExitCode.WARNING),
        ],
    )
    def test_exit_code(self, cls: type[NthLayerError], expected_exit_code: ExitCode) -> None:
        assert cls.exit_code == expected_exit_code

    @pytest.mark.parametrize(
        "cls",
        [
            ConfigurationError,
            ProviderError,
            ValidationError,
            BlockedError,
            PolicyAuditError,
            WarningResult,
        ],
    )
    def test_is_nthlayer_error(self, cls: type[NthLayerError]) -> None:
        err = cls("test error")
        assert isinstance(err, NthLayerError)
        assert isinstance(err, Exception)


class TestMainWithErrorHandling:
    """Tests for the main_with_error_handling decorator."""

    def test_success_path(self) -> None:
        @main_with_error_handling(log_errors=False)
        def cmd() -> int:
            return 0

        assert cmd() == 0

    def test_catches_configuration_error(self) -> None:
        @main_with_error_handling(log_errors=False)
        def cmd() -> int:
            raise ConfigurationError("bad config")

        assert cmd() == ExitCode.CONFIG_ERROR

    def test_catches_provider_error(self) -> None:
        @main_with_error_handling(log_errors=False)
        def cmd() -> int:
            raise ProviderError("grafana down")

        assert cmd() == ExitCode.PROVIDER_ERROR

    def test_catches_validation_error(self) -> None:
        @main_with_error_handling(log_errors=False)
        def cmd() -> int:
            raise ValidationError("invalid spec")

        assert cmd() == ExitCode.VALIDATION_ERROR

    def test_catches_blocked_error(self) -> None:
        @main_with_error_handling(log_errors=False)
        def cmd() -> int:
            raise BlockedError("budget exhausted")

        assert cmd() == ExitCode.BLOCKED

    def test_catches_warning_result(self) -> None:
        @main_with_error_handling(log_errors=False)
        def cmd() -> int:
            raise WarningResult("drift detected")

        assert cmd() == ExitCode.WARNING

    def test_keyboard_interrupt_returns_130(self) -> None:
        @main_with_error_handling(log_errors=False)
        def cmd() -> int:
            raise KeyboardInterrupt

        assert cmd() == 130

    def test_unexpected_exception_returns_127(self) -> None:
        @main_with_error_handling(log_errors=False)
        def cmd() -> int:
            raise RuntimeError("oops")

        assert cmd() == ExitCode.UNKNOWN_ERROR

    def test_preserves_function_name(self) -> None:
        @main_with_error_handling(log_errors=False)
        def my_special_command() -> int:
            return 0

        assert my_special_command.__name__ == "my_special_command"

    def test_passes_args_and_kwargs(self) -> None:
        @main_with_error_handling(log_errors=False)
        def cmd(a: int, b: int, extra: int = 0) -> int:
            return a + b + extra

        assert cmd(1, 2, extra=10) == 13


class TestFormatErrorMessage:
    """Tests for format_error_message helper."""

    def test_simple_message(self) -> None:
        err = NthLayerError("something failed")
        assert format_error_message(err) == "something failed"

    def test_message_with_details(self) -> None:
        err = NthLayerError("connection failed", details={"host": "grafana", "port": 3000})
        result = format_error_message(err)
        assert result.startswith("connection failed (")
        assert "host=grafana" in result
        assert "port=3000" in result

    def test_empty_details_no_parens(self) -> None:
        err = NthLayerError("clean message", details={})
        assert format_error_message(err) == "clean message"
