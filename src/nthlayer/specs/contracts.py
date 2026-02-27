"""
Contract registry and dependency validation.

Implements OpenSRM spec sections 11.2 and 11.3:
- File-based contract registry (11.3 Optional)
- Dependency expectation validation (11.3 Recommended)
- Transitive feasibility check (11.3 Optional)

All validation produces warnings (not errors) per spec.
"""

from __future__ import annotations

import structlog
import math
from pathlib import Path

from nthlayer.specs.manifest import Contract, ReliabilityManifest

logger = structlog.get_logger()


class ContractRegistry:
    """
    Registry of service contracts for cross-service validation.

    Stores contracts indexed by service name, enabling dependency
    expectation validation and transitive feasibility checks.
    """

    def __init__(self) -> None:
        self._contracts: dict[str, Contract] = {}

    def register(self, manifest: ReliabilityManifest) -> None:
        """Register a manifest's contract by service name."""
        if manifest.contract is not None:
            self._contracts[manifest.name] = manifest.contract

    def get_contract(self, name: str) -> Contract | None:
        """Get contract for a service, or None if not registered."""
        return self._contracts.get(name)

    def has_contract(self, name: str) -> bool:
        """Check if a service has a registered contract."""
        return name in self._contracts

    @property
    def services(self) -> list[str]:
        """Sorted list of registered service names."""
        return sorted(self._contracts.keys())

    @classmethod
    def from_manifests(cls, manifests: list[ReliabilityManifest]) -> ContractRegistry:
        """Build registry from a list of pre-loaded manifests."""
        registry = cls()
        for manifest in manifests:
            registry.register(manifest)
        return registry

    @classmethod
    def from_directory(cls, directory: str | Path) -> ContractRegistry:
        """
        Build registry by scanning a directory for manifest files.

        Loads each manifest file found via is_manifest_file() and
        registers any contracts.
        """
        from nthlayer.specs.loader import ManifestLoadError, is_manifest_file, load_manifest

        registry = cls()
        path = Path(directory)

        if not path.is_dir():
            logger.warning("Contract registry directory not found: %s", directory)
            return registry

        for pattern in ("*.yaml", "*.yml"):
            for file_path in sorted(path.rglob(pattern)):
                if not is_manifest_file(file_path):
                    continue
                try:
                    manifest = load_manifest(file_path, suppress_deprecation_warning=True)
                    registry.register(manifest)
                except (ManifestLoadError, FileNotFoundError, ValueError) as e:
                    logger.debug("Skipping %s: %s", file_path, e)

        return registry


def validate_dependency_expectations(
    manifest: ReliabilityManifest,
    registry: ContractRegistry,
) -> list[str]:
    """
    Validate that dependency SLO expectations don't exceed provider contracts.

    For each dependency with an availability expectation, checks that:
    - The expected availability doesn't exceed the provider's contract
    - Critical dependencies have a contract in the registry

    Returns list of warning strings.
    """
    warnings: list[str] = []

    for dep in manifest.dependencies:
        contract = registry.get_contract(dep.name)

        if dep.slo and dep.slo.availability is not None and contract is not None:
            if contract.availability is not None:
                # dep.slo.availability is percentage (99.99),
                # contract.availability is ratio (0.9999)
                contract_pct = contract.availability * 100
                if dep.slo.availability > contract_pct:
                    warnings.append(
                        f"Dependency '{dep.name}': expected availability "
                        f"({dep.slo.availability}%) exceeds provider contract "
                        f"({contract_pct}%)"
                    )

        if dep.critical and not registry.has_contract(dep.name):
            warnings.append(f"Critical dependency '{dep.name}' has no contract " f"in registry")

    return warnings


def validate_transitive_feasibility(
    manifest: ReliabilityManifest,
    registry: ContractRegistry,
) -> list[str]:
    """
    Check if the service's contract is feasible given dependency availabilities.

    Uses a serial chain model: theoretical_max = product(dep_availabilities).
    Only runs if the manifest has a contract with availability set.

    Returns list of warning strings.
    """
    warnings: list[str] = []

    if not manifest.contract or manifest.contract.availability is None:
        return warnings

    # Collect critical dep availabilities
    availabilities: list[float] = []
    unknown_deps: list[str] = []

    for dep in manifest.dependencies:
        if not dep.critical:
            continue

        # Try registry first, then fall back to expected SLO
        contract = registry.get_contract(dep.name)
        if contract is not None and contract.availability is not None:
            availabilities.append(contract.availability)
        elif dep.slo and dep.slo.availability is not None:
            # dep.slo.availability is percentage, convert to ratio
            availabilities.append(dep.slo.availability / 100.0)
        else:
            unknown_deps.append(dep.name)

    for dep_name in unknown_deps:
        warnings.append(
            f"Critical dependency '{dep_name}' has unknown availability "
            f"(cannot verify transitive feasibility)"
        )

    if not availabilities:
        return warnings

    # Serial chain: P(all up) = P1 * P2 * ... * Pn
    theoretical_max = math.prod(availabilities)

    if theoretical_max < manifest.contract.availability:
        warnings.append(
            f"Contract availability ({manifest.contract.availability}) may be "
            f"infeasible: critical dependency chain theoretical max is "
            f"{theoretical_max:.6f}"
        )

    return warnings
