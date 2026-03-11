"""CLI smoke test fixtures and path setup."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

# Ensure tests/smoke/ is on sys.path so test modules can `import _helpers`
_smoke_dir = str(Path(__file__).resolve().parent)
if _smoke_dir not in sys.path:
    sys.path.insert(0, _smoke_dir)


@pytest.fixture
def output_dir(tmp_path: Path) -> Path:
    """Provide a temporary output directory for apply/generate commands."""
    return tmp_path
