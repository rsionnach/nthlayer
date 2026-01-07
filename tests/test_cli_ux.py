"""Tests for CLI UX module - styling and interactive prompts."""

from unittest.mock import MagicMock, patch


class TestEnvironmentDetection:
    """Test environment detection functions."""

    def test_is_interactive_in_ci(self):
        """_is_interactive returns False when CI env var is set."""
        from nthlayer.cli.ux import _is_interactive

        with patch.dict("os.environ", {"CI": "true"}, clear=True):
            assert _is_interactive() is False

    def test_is_interactive_in_github_actions(self):
        """_is_interactive returns False in GitHub Actions."""
        from nthlayer.cli.ux import _is_interactive

        with patch.dict("os.environ", {"GITHUB_ACTIONS": "true"}, clear=True):
            assert _is_interactive() is False

    def test_is_interactive_with_tty(self):
        """_is_interactive returns True when stdout is TTY and not CI."""
        from nthlayer.cli.ux import _is_interactive

        with patch.dict("os.environ", {}, clear=True):
            with patch("sys.stdout") as mock_stdout:
                mock_stdout.isatty.return_value = True
                assert _is_interactive() is True

    def test_is_interactive_without_tty(self):
        """_is_interactive returns False when stdout is not TTY."""
        from nthlayer.cli.ux import _is_interactive

        with patch.dict("os.environ", {}, clear=True):
            with patch("sys.stdout") as mock_stdout:
                mock_stdout.isatty.return_value = False
                assert _is_interactive() is False

    def test_should_use_color_no_color(self):
        """_should_use_color returns False when NO_COLOR is set."""
        from nthlayer.cli.ux import _should_use_color

        with patch.dict("os.environ", {"NO_COLOR": "1"}, clear=True):
            assert _should_use_color() is False

    def test_should_use_color_force_color(self):
        """_should_use_color returns True when FORCE_COLOR is set."""
        from nthlayer.cli.ux import _should_use_color

        with patch.dict("os.environ", {"FORCE_COLOR": "1"}, clear=True):
            assert _should_use_color() is True

    def test_has_gum_when_available(self):
        """has_gum returns True when gum is in PATH."""
        from nthlayer.cli.ux import has_gum

        with patch("shutil.which", return_value="/usr/local/bin/gum"):
            assert has_gum() is True

    def test_has_gum_when_not_available(self):
        """has_gum returns False when gum is not in PATH."""
        from nthlayer.cli.ux import has_gum

        with patch("shutil.which", return_value=None):
            assert has_gum() is False

    def test_is_interactive_public_function(self):
        """is_interactive() (public) wraps _is_interactive()."""
        from nthlayer.cli.ux import is_interactive

        with patch.dict("os.environ", {"CI": "true"}, clear=True):
            assert is_interactive() is False


class TestOutputFunctionsExecution:
    """Test output functions actually execute."""

    @patch("nthlayer.cli.ux.has_gum", return_value=False)
    def test_success_without_gum(self, mock_gum, capsys):
        """success() works without gum."""
        from nthlayer.cli.ux import success

        success("Test success message")
        # No exception raised

    @patch("nthlayer.cli.ux.has_gum", return_value=False)
    def test_error_without_gum(self, mock_gum, capsys):
        """error() works without gum."""
        from nthlayer.cli.ux import error

        error("Test error message")
        # No exception raised

    @patch("nthlayer.cli.ux.has_gum", return_value=False)
    def test_warning_without_gum(self, mock_gum, capsys):
        """warning() works without gum."""
        from nthlayer.cli.ux import warning

        warning("Test warning message")
        # No exception raised

    @patch("nthlayer.cli.ux.has_gum", return_value=False)
    def test_info_without_gum(self, mock_gum, capsys):
        """info() works without gum."""
        from nthlayer.cli.ux import info

        info("Test info message")
        # No exception raised

    @patch("nthlayer.cli.ux.has_gum", return_value=False)
    def test_header_without_gum(self, mock_gum, capsys):
        """header() works without gum."""
        from nthlayer.cli.ux import header

        header("Test Header")
        # No exception raised

    @patch("nthlayer.cli.ux.has_gum", return_value=True)
    @patch("nthlayer.cli.ux._run_gum")
    def test_success_with_gum(self, mock_run, mock_gum):
        """success() uses gum when available."""
        from nthlayer.cli.ux import success

        success("Test message")
        mock_run.assert_called_once()

    @patch("nthlayer.cli.ux.has_gum", return_value=True)
    @patch("nthlayer.cli.ux._run_gum")
    def test_error_with_gum(self, mock_run, mock_gum):
        """error() uses gum when available."""
        from nthlayer.cli.ux import error

        error("Test message")
        mock_run.assert_called_once()

    @patch("nthlayer.cli.ux.has_gum", return_value=True)
    @patch("nthlayer.cli.ux._run_gum")
    def test_warning_with_gum(self, mock_run, mock_gum):
        """warning() uses gum when available."""
        from nthlayer.cli.ux import warning

        warning("Test message")
        mock_run.assert_called_once()

    @patch("nthlayer.cli.ux.has_gum", return_value=True)
    @patch("nthlayer.cli.ux._run_gum")
    def test_info_with_gum(self, mock_run, mock_gum):
        """info() uses gum when available."""
        from nthlayer.cli.ux import info

        info("Test message")
        mock_run.assert_called_once()

    @patch("nthlayer.cli.ux.has_gum", return_value=True)
    @patch("subprocess.run")
    def test_header_with_gum(self, mock_run, mock_gum):
        """header() uses gum when available."""
        from nthlayer.cli.ux import header

        mock_run.return_value = MagicMock(stdout="Header output")
        header("Test Header")
        mock_run.assert_called_once()


class TestTableFunctions:
    """Test table output functions."""

    def test_print_table(self, capsys):
        """print_table() outputs a table."""
        from nthlayer.cli.ux import print_table

        print_table(
            title="Test Table",
            columns=["Name", "Value"],
            rows=[["key1", "value1"], ["key2", "value2"]],
        )
        # No exception raised

    def test_print_table_no_header(self, capsys):
        """print_table() can hide header."""
        from nthlayer.cli.ux import print_table

        print_table(
            title="Test Table",
            columns=["Name", "Value"],
            rows=[["key1", "value1"]],
            show_header=False,
        )
        # No exception raised

    def test_print_key_value(self, capsys):
        """print_key_value() outputs key-value pairs."""
        from nthlayer.cli.ux import print_key_value

        print_key_value({"name": "test", "version": "1.0"})
        # No exception raised

    def test_print_key_value_with_title(self, capsys):
        """print_key_value() can show title."""
        from nthlayer.cli.ux import print_key_value

        print_key_value(
            {"name": "test", "version": "1.0"},
            title="Service Info",
        )
        # No exception raised


class TestSpinnerAndProgress:
    """Test spinner and progress bar functions."""

    def test_spinner_context_manager(self):
        """spinner() works as a context manager."""
        from nthlayer.cli.ux import spinner

        with spinner("Processing..."):
            pass  # Just test it doesn't raise

    def test_progress_bar_iterator(self):
        """progress_bar() iterates over items."""
        from nthlayer.cli.ux import progress_bar

        items = [1, 2, 3, 4, 5]
        result = list(progress_bar(items, description="Testing"))

        assert result == items


class TestInteractivePromptExecution:
    """Test interactive prompts with mocking."""

    @patch("nthlayer.cli.ux.has_gum", return_value=False)
    @patch("questionary.confirm")
    def test_confirm_without_gum(self, mock_confirm, mock_gum):
        """confirm() uses questionary when gum not available."""
        from nthlayer.cli.ux import confirm

        mock_confirm.return_value.ask.return_value = True
        result = confirm("Continue?")

        assert result is True
        mock_confirm.assert_called_once()

    @patch("nthlayer.cli.ux.has_gum", return_value=False)
    @patch("questionary.confirm")
    def test_confirm_returns_false_on_none(self, mock_confirm, mock_gum):
        """confirm() returns False when questionary returns None."""
        from nthlayer.cli.ux import confirm

        mock_confirm.return_value.ask.return_value = None
        result = confirm("Continue?")

        assert result is False

    @patch("nthlayer.cli.ux.has_gum", return_value=True)
    @patch("nthlayer.cli.ux._run_gum")
    def test_confirm_with_gum(self, mock_run, mock_gum):
        """confirm() uses gum when available."""
        from nthlayer.cli.ux import confirm

        mock_run.return_value = MagicMock(returncode=0)
        result = confirm("Continue?", default=True)

        assert result is True
        mock_run.assert_called_once()

    @patch("nthlayer.cli.ux.has_gum", return_value=False)
    @patch("questionary.text")
    def test_text_input_without_gum(self, mock_text, mock_gum):
        """text_input() uses questionary when gum not available."""
        from nthlayer.cli.ux import text_input

        mock_text.return_value.ask.return_value = "user input"
        result = text_input("Enter name:")

        assert result == "user input"

    @patch("nthlayer.cli.ux.has_gum", return_value=False)
    @patch("questionary.text")
    def test_text_input_returns_default_on_none(self, mock_text, mock_gum):
        """text_input() returns default when questionary returns None."""
        from nthlayer.cli.ux import text_input

        mock_text.return_value.ask.return_value = None
        result = text_input("Enter name:", default="default_value")

        assert result == "default_value"

    @patch("nthlayer.cli.ux.has_gum", return_value=True)
    @patch("nthlayer.cli.ux._run_gum")
    def test_text_input_with_gum(self, mock_run, mock_gum):
        """text_input() uses gum when available."""
        from nthlayer.cli.ux import text_input

        mock_run.return_value = MagicMock(returncode=0, stdout="gum input\n")
        result = text_input("Enter name:")

        assert result == "gum input"

    @patch("nthlayer.cli.ux.has_gum", return_value=True)
    @patch("nthlayer.cli.ux._run_gum")
    def test_text_input_with_gum_failure(self, mock_run, mock_gum):
        """text_input() returns default when gum fails."""
        from nthlayer.cli.ux import text_input

        mock_run.return_value = MagicMock(returncode=1, stdout="")
        result = text_input("Enter name:", default="fallback")

        assert result == "fallback"

    @patch("nthlayer.cli.ux.has_gum", return_value=False)
    @patch("questionary.select")
    def test_select_without_gum(self, mock_select, mock_gum):
        """select() uses questionary when gum not available."""
        from nthlayer.cli.ux import select

        mock_select.return_value.ask.return_value = "option1"
        result = select("Choose:", ["option1", "option2"])

        assert result == "option1"

    @patch("nthlayer.cli.ux.has_gum", return_value=False)
    @patch("questionary.select")
    def test_select_returns_default_on_none(self, mock_select, mock_gum):
        """select() returns default when questionary returns None."""
        from nthlayer.cli.ux import select

        mock_select.return_value.ask.return_value = None
        result = select("Choose:", ["option1", "option2"], default="option2")

        assert result == "option2"

    @patch("nthlayer.cli.ux.has_gum", return_value=True)
    @patch("nthlayer.cli.ux._run_gum")
    def test_select_with_gum(self, mock_run, mock_gum):
        """select() uses gum when available."""
        from nthlayer.cli.ux import select

        mock_run.return_value = MagicMock(returncode=0, stdout="option1\n")
        result = select("Choose:", ["option1", "option2"])

        assert result == "option1"

    @patch("nthlayer.cli.ux.has_gum", return_value=False)
    @patch("questionary.checkbox")
    def test_multi_select_without_gum(self, mock_checkbox, mock_gum):
        """multi_select() uses questionary when gum not available."""
        from nthlayer.cli.ux import multi_select

        mock_checkbox.return_value.ask.return_value = ["opt1", "opt2"]
        result = multi_select("Choose:", ["opt1", "opt2", "opt3"])

        assert result == ["opt1", "opt2"]

    @patch("nthlayer.cli.ux.has_gum", return_value=False)
    @patch("questionary.checkbox")
    def test_multi_select_returns_empty_on_none(self, mock_checkbox, mock_gum):
        """multi_select() returns empty list when questionary returns None."""
        from nthlayer.cli.ux import multi_select

        mock_checkbox.return_value.ask.return_value = None
        result = multi_select("Choose:", ["opt1", "opt2"])

        assert result == []

    @patch("nthlayer.cli.ux.has_gum", return_value=True)
    @patch("nthlayer.cli.ux._run_gum")
    def test_multi_select_with_gum(self, mock_run, mock_gum):
        """multi_select() uses gum when available."""
        from nthlayer.cli.ux import multi_select

        mock_run.return_value = MagicMock(returncode=0, stdout="opt1\nopt2\n")
        result = multi_select("Choose:", ["opt1", "opt2", "opt3"])

        assert result == ["opt1", "opt2"]

    @patch("nthlayer.cli.ux.has_gum", return_value=True)
    @patch("nthlayer.cli.ux._run_gum")
    def test_multi_select_with_gum_failure(self, mock_run, mock_gum):
        """multi_select() returns defaults when gum fails."""
        from nthlayer.cli.ux import multi_select

        mock_run.return_value = MagicMock(returncode=1, stdout="")
        result = multi_select("Choose:", ["opt1", "opt2"], defaults=["opt1"])

        assert result == ["opt1"]

    @patch("nthlayer.cli.ux.has_gum", return_value=False)
    @patch("questionary.password")
    def test_password_input_without_gum(self, mock_password, mock_gum):
        """password_input() uses questionary when gum not available."""
        from nthlayer.cli.ux import password_input

        mock_password.return_value.ask.return_value = "secret"
        result = password_input("Enter password:")

        assert result == "secret"

    @patch("nthlayer.cli.ux.has_gum", return_value=False)
    @patch("questionary.password")
    def test_password_input_returns_empty_on_none(self, mock_password, mock_gum):
        """password_input() returns empty string when questionary returns None."""
        from nthlayer.cli.ux import password_input

        mock_password.return_value.ask.return_value = None
        result = password_input("Enter password:")

        assert result == ""

    @patch("nthlayer.cli.ux.has_gum", return_value=True)
    @patch("nthlayer.cli.ux._run_gum")
    def test_password_input_with_gum(self, mock_run, mock_gum):
        """password_input() uses gum when available."""
        from nthlayer.cli.ux import password_input

        mock_run.return_value = MagicMock(returncode=0, stdout="secret\n")
        result = password_input("Enter password:")

        assert result == "secret"


class TestHigherLevelComponents:
    """Test higher-level UX components."""

    @patch("nthlayer.cli.ux.has_gum", return_value=False)
    def test_show_results_all_success(self, mock_gum, capsys):
        """show_results() displays all successful results."""
        from nthlayer.cli.ux import show_results

        results = [
            {"name": "service1", "success": True},
            {"name": "service2", "success": True},
        ]
        show_results("Deployment Results", results)
        # No exception raised

    @patch("nthlayer.cli.ux.has_gum", return_value=False)
    def test_show_results_with_failures(self, mock_gum, capsys):
        """show_results() displays mixed success/failure results."""
        from nthlayer.cli.ux import show_results

        results = [
            {"name": "service1", "success": True},
            {"name": "service2", "success": False, "error": "Connection failed"},
        ]
        show_results("Deployment Results", results)
        # No exception raised

    @patch("nthlayer.cli.ux.has_gum", return_value=False)
    def test_wizard_intro_without_gum(self, mock_gum, capsys):
        """wizard_intro() works without gum."""
        from nthlayer.cli.ux import wizard_intro

        wizard_intro("Setup Wizard", "Follow these steps to configure your service.")
        # No exception raised

    @patch("nthlayer.cli.ux.has_gum", return_value=True)
    @patch("subprocess.run")
    def test_wizard_intro_with_gum(self, mock_run, mock_gum, capsys):
        """wizard_intro() uses gum when available."""
        from nthlayer.cli.ux import wizard_intro

        mock_run.return_value = MagicMock(stdout="")
        wizard_intro("Setup Wizard", "Description here")
        mock_run.assert_called_once()

    @patch("nthlayer.cli.ux._is_interactive", return_value=True)
    def test_print_banner_interactive(self, mock_interactive, capsys):
        """print_banner() shows banner in interactive mode."""
        from nthlayer.cli.ux import print_banner

        with patch.dict("os.environ", {}, clear=True):
            print_banner()
        # No exception raised

    @patch("nthlayer.cli.ux._is_interactive", return_value=False)
    def test_print_banner_non_interactive(self, mock_interactive, capsys):
        """print_banner() hides banner in non-interactive mode."""
        from nthlayer.cli.ux import print_banner

        with patch.dict("os.environ", {}, clear=True):
            print_banner()
        # No exception raised

    @patch("nthlayer.cli.ux._is_interactive", return_value=False)
    def test_print_banner_force_color(self, mock_interactive, capsys):
        """print_banner() shows banner when FORCE_COLOR is set."""
        from nthlayer.cli.ux import print_banner

        with patch.dict("os.environ", {"FORCE_COLOR": "1"}, clear=True):
            print_banner()
        # No exception raised


class TestPromptStyle:
    """Test questionary prompt styling configuration."""

    def test_prompt_style_imports_without_error(self):
        """PROMPT_STYLE should be valid and importable."""
        from nthlayer.cli.ux import PROMPT_STYLE

        assert PROMPT_STYLE is not None

    def test_prompt_style_has_required_keys(self):
        """PROMPT_STYLE should define all required style keys."""
        from nthlayer.cli.ux import PROMPT_STYLE

        # Get the style rules from the Style object
        style_rules = PROMPT_STYLE.style_rules

        # Required keys for questionary prompts
        required_keys = [
            "qmark",
            "question",
            "answer",
            "pointer",
            "highlighted",
            "selected",
            "text",
        ]

        defined_keys = [rule[0] for rule in style_rules]

        for key in required_keys:
            assert key in defined_keys, f"Missing required style key: {key}"

    def test_prompt_style_colors_are_valid(self):
        """All colors in PROMPT_STYLE should be valid hex colors."""
        import re

        from nthlayer.cli.ux import PROMPT_STYLE

        hex_color_pattern = re.compile(r"#[0-9A-Fa-f]{6}")

        for class_name, style_str in PROMPT_STYLE.style_rules:
            # Extract hex colors from style string
            colors = hex_color_pattern.findall(style_str)
            for color in colors:
                # Verify it's a valid 6-digit hex
                assert len(color) == 7, f"Invalid color format in {class_name}: {color}"

    def test_prompt_style_no_class_prefix(self):
        """Style keys should not have 'class:' prefix (internal to prompt_toolkit)."""
        from nthlayer.cli.ux import PROMPT_STYLE

        for class_name, _ in PROMPT_STYLE.style_rules:
            assert not class_name.startswith("class:"), (
                f"Invalid style key '{class_name}': " "class: prefix is internal to prompt_toolkit"
            )


class TestConsoleSetup:
    """Test Rich console configuration."""

    def test_console_imports_without_error(self):
        """Console should be properly configured and importable."""
        from nthlayer.cli.ux import console

        assert console is not None

    def test_nthlayer_theme_has_required_styles(self):
        """NTHLAYER_THEME should define all required style names."""
        from nthlayer.cli.ux import NTHLAYER_THEME

        required_styles = ["info", "success", "warning", "error", "muted"]

        for style in required_styles:
            assert style in NTHLAYER_THEME.styles, f"Missing theme style: {style}"


class TestOutputFunctions:
    """Test output helper functions."""

    def test_header_function_exists(self):
        """header() function should be importable."""
        from nthlayer.cli.ux import header

        assert callable(header)

    def test_success_function_exists(self):
        """success() function should be importable."""
        from nthlayer.cli.ux import success

        assert callable(success)

    def test_error_function_exists(self):
        """error() function should be importable."""
        from nthlayer.cli.ux import error

        assert callable(error)

    def test_warning_function_exists(self):
        """warning() function should be importable."""
        from nthlayer.cli.ux import warning

        assert callable(warning)

    def test_info_function_exists(self):
        """info() function should be importable."""
        from nthlayer.cli.ux import info

        assert callable(info)


class TestInteractivePrompts:
    """Test interactive prompt functions (without actually prompting)."""

    def test_select_function_exists(self):
        """select() function should be importable."""
        from nthlayer.cli.ux import select

        assert callable(select)

    def test_multi_select_function_exists(self):
        """multi_select() function should be importable."""
        from nthlayer.cli.ux import multi_select

        assert callable(multi_select)

    def test_text_input_function_exists(self):
        """text_input() function should be importable."""
        from nthlayer.cli.ux import text_input

        assert callable(text_input)

    def test_confirm_function_exists(self):
        """confirm() function should be importable."""
        from nthlayer.cli.ux import confirm

        assert callable(confirm)

    def test_password_input_function_exists(self):
        """password_input() function should be importable."""
        from nthlayer.cli.ux import password_input

        assert callable(password_input)


class TestBanner:
    """Test banner display."""

    def test_print_banner_function_exists(self):
        """print_banner() function should be importable."""
        from nthlayer.cli.ux import print_banner

        assert callable(print_banner)

    def test_banner_constant_exists(self):
        """NTHLAYER_BANNER constant should be defined."""
        from nthlayer.cli.ux import NTHLAYER_BANNER

        assert NTHLAYER_BANNER is not None
        # Banner contains ASCII art + tagline
        assert "The Missing Layer of Reliability" in NTHLAYER_BANNER


class TestQuestionaryIntegration:
    """Test that questionary integration works correctly."""

    def test_questionary_style_is_valid_style_object(self):
        """PROMPT_STYLE should be a valid questionary Style object."""
        from nthlayer.cli.ux import PROMPT_STYLE
        from questionary import Style

        assert isinstance(PROMPT_STYLE, Style)

    def test_questionary_select_accepts_style(self):
        """questionary.select should accept our PROMPT_STYLE without error."""
        import questionary
        from nthlayer.cli.ux import PROMPT_STYLE

        # Create a select question (don't ask it)
        question = questionary.select(
            "Test question",
            choices=["Option 1", "Option 2"],
            style=PROMPT_STYLE,
        )

        # Should create without error
        assert question is not None

    def test_questionary_checkbox_accepts_style(self):
        """questionary.checkbox should accept our PROMPT_STYLE without error."""
        import questionary
        from nthlayer.cli.ux import PROMPT_STYLE

        # Create a checkbox question (don't ask it)
        question = questionary.checkbox(
            "Test question",
            choices=["Option 1", "Option 2"],
            style=PROMPT_STYLE,
        )

        # Should create without error
        assert question is not None

    def test_questionary_text_accepts_style(self):
        """questionary.text should accept our PROMPT_STYLE without error."""
        import questionary
        from nthlayer.cli.ux import PROMPT_STYLE

        # Create a text question (don't ask it)
        question = questionary.text(
            "Test question",
            style=PROMPT_STYLE,
        )

        # Should create without error
        assert question is not None

    def test_questionary_confirm_accepts_style(self):
        """questionary.confirm should accept our PROMPT_STYLE without error."""
        import questionary
        from nthlayer.cli.ux import PROMPT_STYLE

        # Create a confirm question (don't ask it)
        question = questionary.confirm(
            "Test question",
            style=PROMPT_STYLE,
        )

        # Should create without error
        assert question is not None
