"""CLI smoke test helpers — subprocess runner and manifest paths."""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]

# Example manifests used across smoke tests
CHECKOUT_SERVICE = str(PROJECT_ROOT / "examples" / "services" / "checkout-service.yaml")
PAYMENT_API_OPENSRM = str(PROJECT_ROOT / "examples" / "uat" / "payment-api.reliability.yaml")


@dataclass(frozen=True)
class CLIResult:
    """Captured result from a CLI subprocess invocation."""

    exit_code: int
    stdout: str
    stderr: str
    command: list[str]

    def __repr__(self) -> str:
        cmd_str = " ".join(self.command)
        return (
            f"CLIResult(exit_code={self.exit_code}, command={cmd_str!r})\n"
            f"--- stdout ---\n{self.stdout[:500]}\n"
            f"--- stderr ---\n{self.stderr[:500]}"
        )


def run_nthlayer(*args: str, timeout: int = 30) -> CLIResult:
    """Run ``uv run nthlayer <args>`` as a subprocess and return the result."""
    cmd = ["uv", "run", "nthlayer", *args]
    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=timeout,
        cwd=str(PROJECT_ROOT),
    )
    return CLIResult(
        exit_code=result.returncode,
        stdout=result.stdout,
        stderr=result.stderr,
        command=cmd,
    )
