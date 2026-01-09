"""
CODEOWNERS ownership provider.

Parses GitHub/GitLab CODEOWNERS files to extract ownership information.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from nthlayer.identity.ownership import OwnershipSignal, OwnershipSource
from nthlayer.identity.ownership_providers.base import (
    BaseOwnershipProvider,
    OwnershipProviderHealth,
)

# Standard CODEOWNERS file locations
CODEOWNERS_PATHS = [
    "CODEOWNERS",
    ".github/CODEOWNERS",
    ".gitlab/CODEOWNERS",
    "docs/CODEOWNERS",
]


@dataclass
class CODEOWNERSProvider(BaseOwnershipProvider):
    """
    Ownership provider that parses CODEOWNERS files.

    Searches for CODEOWNERS in standard locations and extracts
    the default owner (line starting with `*`).

    Attributes:
        repo_root: Root directory of the repository
        codeowners_content: Optional pre-loaded CODEOWNERS content
    """

    repo_root: str | Path = "."
    codeowners_content: str | None = field(default=None, repr=False)

    # Cached parsed owners
    _parsed: dict[str, str] | None = field(default=None, repr=False)
    _codeowners_path: str | None = field(default=None, repr=False)

    @property
    def name(self) -> str:
        return "codeowners"

    @property
    def source(self) -> OwnershipSource:
        return OwnershipSource.CODEOWNERS

    @property
    def default_confidence(self) -> float:
        return 0.85

    def _find_codeowners(self) -> str | None:
        """Find CODEOWNERS file in standard locations."""
        if self.codeowners_content:
            return self.codeowners_content

        root = Path(self.repo_root)
        for path in CODEOWNERS_PATHS:
            full_path = root / path
            if full_path.exists():
                self._codeowners_path = str(path)
                return full_path.read_text()

        return None

    def _parse_codeowners(self, content: str) -> dict[str, str]:
        """
        Parse CODEOWNERS content into pattern -> owner mapping.

        Returns dict with special keys:
        - "*": Default owner (matches everything)
        - Pattern paths for specific matches
        """
        owners: dict[str, str] = {}

        for line in content.splitlines():
            line = line.strip()

            # Skip empty lines and comments
            if not line or line.startswith("#"):
                continue

            # Parse: pattern owner1 owner2 ...
            parts = line.split()
            if len(parts) >= 2:
                pattern = parts[0]
                # Take first owner (could be @org/team or @user)
                owner = parts[1]
                owners[pattern] = owner

        return owners

    def _get_default_owner(self) -> str | None:
        """Get the default owner (from * pattern)."""
        if self._parsed is None:
            content = self._find_codeowners()
            if content:
                self._parsed = self._parse_codeowners(content)
            else:
                self._parsed = {}

        return self._parsed.get("*")

    def _infer_owner_type(self, owner: str) -> str:
        """Infer owner type from owner string."""
        if "/" in owner:
            # @org/team format
            return "group"
        elif owner.startswith("@"):
            # @username format
            return "individual"
        else:
            # Email or team name
            if "@" in owner and "." in owner:
                return "individual"
            return "team"

    async def get_owner(self, service: str) -> OwnershipSignal | None:
        """
        Get ownership from CODEOWNERS.

        Currently only returns the default owner (*).
        Future: Could match service path patterns.
        """
        default_owner = self._get_default_owner()

        if not default_owner:
            return None

        return OwnershipSignal(
            source=self.source,
            owner=default_owner,
            confidence=self.default_confidence,
            owner_type=self._infer_owner_type(default_owner),
            metadata={
                "file": self._codeowners_path or "CODEOWNERS",
                "pattern": "*",
            },
        )

    async def health_check(self) -> OwnershipProviderHealth:
        """Check if CODEOWNERS file exists."""
        content = self._find_codeowners()

        if content:
            return OwnershipProviderHealth(
                healthy=True,
                message=f"Found CODEOWNERS at {self._codeowners_path}",
            )
        else:
            return OwnershipProviderHealth(
                healthy=False,
                message="No CODEOWNERS file found",
            )
