"""Tests for cli/dependencies.py.

Tests for dependency validation CLI command.
"""

import tempfile
from pathlib import Path

import pytest
from nthlayer.cli.dependencies import validate_dependencies_command


@pytest.fixture
def minimal_service_yaml():
    """Create minimal service YAML content."""
    return """
service:
  name: test-service
  team: test-team
  tier: tier-1
  type: api
"""


@pytest.fixture
def service_with_dependencies():
    """Create service YAML with dependencies."""
    return """
service:
  name: payment-api
  team: payments-team
  tier: tier-1
  type: api
resources:
  - kind: Dependencies
    name: upstream
    spec:
      services:
        - name: user-service
          criticality: critical
        - name: inventory-service
          criticality: medium
"""


@pytest.fixture
def service_with_invalid_dep():
    """Create service YAML with invalid dependency."""
    return """
service:
  name: order-api
  team: orders-team
  tier: tier-2
  type: api
resources:
  - kind: Dependencies
    name: upstream
    spec:
      services:
        - name: nonexistent-service
          criticality: critical
"""


class TestValidateDependenciesCommand:
    """Tests for validate_dependencies_command function."""

    def test_empty_file_list(self):
        """Test with empty file list."""
        result = validate_dependencies_command([])

        # Should succeed with no files
        assert result == 0

    def test_missing_file(self):
        """Test with non-existent file."""
        # The command catches parsing errors but errors still end up in all_errors
        # and result == 1
        result = validate_dependencies_command(["/nonexistent/service.yaml"])

        # Should return error because parsing failed
        assert result == 1

    def test_single_service_no_deps(self, minimal_service_yaml):
        """Test single service without dependencies."""
        with tempfile.TemporaryDirectory() as tmpdir:
            service_file = Path(tmpdir) / "service.yaml"
            service_file.write_text(minimal_service_yaml)

            result = validate_dependencies_command([str(service_file)])

        assert result == 0

    def test_single_service_with_valid_deps(self, service_with_dependencies):
        """Test single service with self-referencing valid deps."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create two service files
            payment_file = Path(tmpdir) / "payment.yaml"
            payment_file.write_text(service_with_dependencies)

            user_file = Path(tmpdir) / "user.yaml"
            user_file.write_text("""
service:
  name: user-service
  team: users-team
  tier: tier-1
  type: api
""")

            inventory_file = Path(tmpdir) / "inventory.yaml"
            inventory_file.write_text("""
service:
  name: inventory-service
  team: inventory-team
  tier: tier-2
  type: api
""")

            result = validate_dependencies_command(
                [
                    str(payment_file),
                    str(user_file),
                    str(inventory_file),
                ]
            )

        assert result == 0

    def test_service_with_missing_dependency(self, service_with_invalid_dep):
        """Test service with dependency on non-existent service."""
        with tempfile.TemporaryDirectory() as tmpdir:
            order_file = Path(tmpdir) / "order.yaml"
            order_file.write_text(service_with_invalid_dep)

            result = validate_dependencies_command([str(order_file)])

        # Missing dependencies result in warnings, not errors, so command succeeds
        # (this allows for forward dependencies where the other service will be deployed)
        assert result == 0

    def test_invalid_yaml(self):
        """Test with invalid YAML file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            bad_file = Path(tmpdir) / "bad.yaml"
            bad_file.write_text("not: valid: yaml: {{")

            result = validate_dependencies_command([str(bad_file)])

        assert result == 1

    def test_circular_dependencies(self):
        """Test detection of circular dependencies."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create two services that depend on each other
            service_a = Path(tmpdir) / "service-a.yaml"
            service_a.write_text("""
service:
  name: service-a
  team: team-a
  tier: tier-1
  type: api
resources:
  - kind: Dependencies
    name: upstream
    spec:
      services:
        - name: service-b
          criticality: critical
""")

            service_b = Path(tmpdir) / "service-b.yaml"
            service_b.write_text("""
service:
  name: service-b
  team: team-b
  tier: tier-1
  type: api
resources:
  - kind: Dependencies
    name: upstream
    spec:
      services:
        - name: service-a
          criticality: critical
""")

            result = validate_dependencies_command(
                [
                    str(service_a),
                    str(service_b),
                ]
            )

        # Should fail due to circular dependency
        assert result == 1

    def test_multiple_services_all_valid(self):
        """Test multiple services with all valid dependencies."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create a chain of services with valid dependencies
            gateway = Path(tmpdir) / "gateway.yaml"
            gateway.write_text("""
service:
  name: gateway
  team: gateway-team
  tier: tier-1
  type: api
resources:
  - kind: Dependencies
    name: upstream
    spec:
      services:
        - name: backend
          criticality: critical
""")

            backend = Path(tmpdir) / "backend.yaml"
            backend.write_text("""
service:
  name: backend
  team: backend-team
  tier: tier-2
  type: api
resources:
  - kind: Dependencies
    name: upstream
    spec:
      services:
        - name: database
          criticality: critical
""")

            database = Path(tmpdir) / "database.yaml"
            database.write_text("""
service:
  name: database
  team: data-team
  tier: tier-3
  type: database
""")

            result = validate_dependencies_command(
                [
                    str(gateway),
                    str(backend),
                    str(database),
                ]
            )

        assert result == 0

    def test_default_criticality(self):
        """Test dependencies without explicit criticality use default."""
        with tempfile.TemporaryDirectory() as tmpdir:
            service_file = Path(tmpdir) / "service.yaml"
            service_file.write_text("""
service:
  name: api-service
  team: api-team
  tier: tier-1
  type: api
resources:
  - kind: Dependencies
    name: upstream
    spec:
      services:
        - name: helper-service
""")

            helper_file = Path(tmpdir) / "helper.yaml"
            helper_file.write_text("""
service:
  name: helper-service
  team: helper-team
  tier: tier-2
  type: api
""")

            result = validate_dependencies_command(
                [
                    str(service_file),
                    str(helper_file),
                ]
            )

        assert result == 0

    def test_empty_dependencies_spec(self):
        """Test service with empty dependencies spec."""
        with tempfile.TemporaryDirectory() as tmpdir:
            service_file = Path(tmpdir) / "service.yaml"
            service_file.write_text("""
service:
  name: standalone-service
  team: standalone-team
  tier: tier-1
  type: api
resources:
  - kind: Dependencies
    name: upstream
    spec:
      services: []
""")

            result = validate_dependencies_command([str(service_file)])

        assert result == 0
