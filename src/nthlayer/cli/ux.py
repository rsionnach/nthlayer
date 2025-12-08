"""
Hybrid CLI UX utilities using Charm tools (gum) with Python fallbacks.

Progressive enhancement: Best UX when gum is installed, always works via pip.
Uses rich/questionary as fallbacks when gum is not available.

Environment handling:
- Automatically detects TTY vs pipe/CI
- Respects NO_COLOR and FORCE_COLOR environment variables
- Falls back to plain text in non-interactive environments
- Safe for CI/CD pipelines (GitHub Actions, Jenkins, etc.)
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from contextlib import contextmanager
from typing import Any, Iterator

# Questionary for interactive prompts
import questionary
from questionary import Style as QStyle

# Rich imports (always available)
from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.table import Table
from rich.theme import Theme

# Nord color palette (https://www.nordtheme.com/)
# Polar Night: #2E3440, #3B4252, #434C5E, #4C566A
# Snow Storm: #D8DEE9, #E5E9F0, #ECEFF4
# Frost: #8FBCBB, #88C0D0, #81A1C1, #5E81AC
# Aurora: #BF616A (red), #D08770 (orange), #EBCB8B (yellow), #A3BE8C (green), #B48EAD (purple)

NTHLAYER_THEME = Theme(
    {
        "info": "#88C0D0",  # Nord frost - light blue
        "success": "#A3BE8C",  # Nord aurora - green
        "warning": "#EBCB8B",  # Nord aurora - yellow
        "error": "#BF616A bold",  # Nord aurora - red
        "highlight": "#B48EAD",  # Nord aurora - purple
        "muted": "#D8DEE9",  # Nord snow storm - light grey (readable on dark bg)
        "frost": "#81A1C1",  # Nord frost - blue
        "orange": "#D08770",  # Nord aurora - orange
    }
)


def _is_interactive() -> bool:
    """Check if we're in an interactive terminal environment."""
    # Check for CI environment variables
    ci_vars = ["CI", "GITHUB_ACTIONS", "JENKINS_URL", "GITLAB_CI", "CIRCLECI", "TRAVIS"]
    if any(os.environ.get(var) for var in ci_vars):
        return False
    # Check if stdout is a TTY
    return sys.stdout.isatty()


def _should_use_color() -> bool:
    """Check if we should use colored output."""
    # Respect NO_COLOR standard (https://no-color.org/)
    if os.environ.get("NO_COLOR"):
        return False
    # Respect FORCE_COLOR for CI that supports it
    if os.environ.get("FORCE_COLOR"):
        return True
    # Default: use color if interactive
    return _is_interactive()


# Create console with environment-aware settings
# Rich automatically handles most of this, but we're explicit for clarity
console = Console(
    theme=NTHLAYER_THEME,
    force_terminal=os.environ.get("FORCE_COLOR") is not None,
    no_color=os.environ.get("NO_COLOR") is not None,
)

# Questionary style matching Nord theme
PROMPT_STYLE = QStyle(
    [
        ("qmark", "fg:#88C0D0 bold"),  # Nord frost
        ("question", "bold"),
        ("answer", "fg:#A3BE8C"),  # Nord aurora green
        ("pointer", "fg:#88C0D0 bold"),  # Nord frost
        ("highlighted", "fg:#81A1C1 bold"),  # Nord frost blue
        ("selected", "fg:#A3BE8C"),  # Nord aurora green
    ]
)


def has_gum() -> bool:
    """Check if gum is available in PATH."""
    return shutil.which("gum") is not None


def _run_gum(args: list[str], **kwargs: Any) -> subprocess.CompletedProcess:
    """Run gum command with given arguments."""
    return subprocess.run(["gum", *args], **kwargs)


# === Spinners and Progress ===


@contextmanager
def spinner(message: str) -> Iterator[None]:
    """Show a spinner while work is in progress.

    Uses gum spin if available, otherwise rich spinner.
    """
    if has_gum():
        # gum spin runs a command, so we can't use it as a context manager easily
        # Fall back to rich for spinner context manager
        pass

    # Use rich spinner (works everywhere)
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
        transient=True,
    ) as progress:
        progress.add_task(description=message, total=None)
        yield


def progress_bar(items: list[Any], description: str = "Processing") -> Iterator[Any]:
    """Iterate over items with a progress bar."""
    with Progress(console=console) as progress:
        task = progress.add_task(f"[cyan]{description}", total=len(items))
        for item in items:
            yield item
            progress.advance(task)


# === Output Formatting ===


def success(message: str) -> None:
    """Print a success message."""
    if has_gum():
        _run_gum(["style", "--foreground", "10", f"✓ {message}"])
    else:
        console.print(f"[success]✓ {message}[/success]")


def error(message: str) -> None:
    """Print an error message."""
    if has_gum():
        _run_gum(["style", "--foreground", "9", f"✗ {message}"])
    else:
        console.print(f"[error]✗ {message}[/error]")


def warning(message: str) -> None:
    """Print a warning message."""
    if has_gum():
        _run_gum(["style", "--foreground", "11", f"⚠ {message}"])
    else:
        console.print(f"[warning]⚠ {message}[/warning]")


def info(message: str) -> None:
    """Print an info message."""
    if has_gum():
        _run_gum(["style", "--foreground", "14", f"ℹ {message}"])
    else:
        console.print(f"[info]ℹ {message}[/info]")


def header(title: str) -> None:
    """Print a section header."""
    if has_gum():
        result = subprocess.run(
            ["gum", "style", "--border", "rounded", "--padding", "0 2", "--bold", title],
            capture_output=True,
            text=True,
        )
        print(result.stdout)
    else:
        console.print()
        console.print(Panel(f"[bold]{title}[/bold]", border_style="cyan"))


def print_table(
    title: str,
    columns: list[str],
    rows: list[list[str]],
    show_header: bool = True,
) -> None:
    """Print a formatted table."""
    table = Table(title=title, show_header=show_header)

    for col in columns:
        table.add_column(col)

    for row in rows:
        table.add_row(*row)

    console.print(table)


def print_key_value(items: dict[str, str], title: str | None = None) -> None:
    """Print key-value pairs in a nice format."""
    if title:
        console.print(f"\n[bold]{title}[/bold]")

    for key, value in items.items():
        console.print(f"  [cyan]{key}:[/cyan] {value}")


# === Interactive Prompts ===


def confirm(message: str, default: bool = False) -> bool:
    """Ask for confirmation."""
    if has_gum():
        default_flag = "--default" if default else "--default=false"
        result = _run_gum(["confirm", default_flag, message])
        return result.returncode == 0
    else:
        return questionary.confirm(message, default=default, style=PROMPT_STYLE).ask() or False


def text_input(message: str, default: str = "", placeholder: str = "") -> str:
    """Get text input from user."""
    if has_gum():
        result = _run_gum(
            ["input", "--placeholder", placeholder or message, "--value", default],
            capture_output=True,
            text=True,
        )
        return result.stdout.strip() if result.returncode == 0 else default
    else:
        return (
            questionary.text(
                message,
                default=default,
                style=PROMPT_STYLE,
            ).ask()
            or default
        )


def select(message: str, choices: list[str], default: str | None = None) -> str:
    """Select from a list of choices."""
    if has_gum():
        result = _run_gum(
            ["choose", *choices],
            capture_output=True,
            text=True,
        )
        return result.stdout.strip() if result.returncode == 0 else (default or choices[0])
    else:
        return questionary.select(
            message,
            choices=choices,
            default=default,
            style=PROMPT_STYLE,
        ).ask() or (default or choices[0])


def multi_select(message: str, choices: list[str], defaults: list[str] | None = None) -> list[str]:
    """Select multiple items from a list."""
    if has_gum():
        args = ["choose", "--no-limit", *choices]
        result = _run_gum(args, capture_output=True, text=True)
        if result.returncode == 0:
            return [line.strip() for line in result.stdout.strip().split("\n") if line.strip()]
        return defaults or []
    else:
        return (
            questionary.checkbox(
                message,
                choices=choices,
                default=defaults,
                style=PROMPT_STYLE,
            ).ask()
            or []
        )


def password_input(message: str) -> str:
    """Get password/secret input (hidden)."""
    if has_gum():
        result = _run_gum(
            ["input", "--password", "--placeholder", message],
            capture_output=True,
            text=True,
        )
        return result.stdout.strip() if result.returncode == 0 else ""
    else:
        return questionary.password(message, style=PROMPT_STYLE).ask() or ""


# === Higher-level Components ===


def show_results(
    title: str,
    results: list[dict[str, Any]],
    success_key: str = "success",
    name_key: str = "name",
) -> None:
    """Show operation results in a nice format."""
    success_count = sum(1 for r in results if r.get(success_key, True))
    total = len(results)

    header(title)

    for result in results:
        name = result.get(name_key, "Unknown")
        if result.get(success_key, True):
            success(f"{name}")
        else:
            error_msg = result.get("error", "Failed")
            error(f"{name}: {error_msg}")

    console.print()
    if success_count == total:
        success(f"All {total} operations completed successfully")
    else:
        warning(f"{success_count}/{total} operations completed")


def wizard_intro(title: str, description: str) -> None:
    """Show wizard introduction."""
    if has_gum():
        subprocess.run(
            [
                "gum",
                "style",
                "--border",
                "double",
                "--border-foreground",
                "212",
                "--padding",
                "1 4",
                "--margin",
                "1",
                title,
            ]
        )
        print(description)
        print()
    else:
        console.print()
        console.print(
            Panel(
                f"[bold #B48EAD]{title}[/bold #B48EAD]\n\n{description}",
                border_style="#B48EAD",  # Nord aurora purple
                padding=(1, 4),
            )
        )
        console.print()


# Blocky ASCII banner - only shown in interactive mode
# Uses Nord frost colors (#88C0D0)
NTHLAYER_BANNER = """
[#88C0D0]███╗   ██╗████████╗██╗  ██╗██╗      █████╗ ██╗   ██╗███████╗██████╗[/#88C0D0]
[#88C0D0]████╗  ██║╚══██╔══╝██║  ██║██║     ██╔══██╗╚██╗ ██╔╝██╔════╝██╔══██╗[/#88C0D0]
[#88C0D0]██╔██╗ ██║   ██║   ███████║██║     ███████║ ╚████╔╝ █████╗  ██████╔╝[/#88C0D0]
[#88C0D0]██║╚██╗██║   ██║   ██╔══██║██║     ██╔══██║  ╚██╔╝  ██╔══╝  ██╔══██╗[/#88C0D0]
[#88C0D0]██║ ╚████║   ██║   ██║  ██║███████╗██║  ██║   ██║   ███████╗██║  ██║[/#88C0D0]
[#88C0D0]╚═╝  ╚═══╝   ╚═╝   ╚═╝  ╚═╝╚══════╝╚═╝  ╚═╝   ╚═╝   ╚══════╝╚═╝  ╚═╝[/#88C0D0]
[#D8DEE9]The Missing Layer of Reliability[/#D8DEE9]
"""


def print_banner() -> None:
    """Print ASCII banner (only in interactive terminals, not CI).

    Respects FORCE_COLOR to show banner in VHS/demo recordings.
    """
    # Show banner if interactive OR if FORCE_COLOR is set (for demos)
    if _is_interactive() or os.environ.get("FORCE_COLOR"):
        console.print(NTHLAYER_BANNER)


def is_interactive() -> bool:
    """Public function to check if running interactively."""
    return _is_interactive()
