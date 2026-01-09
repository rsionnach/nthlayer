"""Tests for identity CLI command."""

import json

from nthlayer.cli.identity import (
    NormalizationStep,
    create_demo_identities,
    create_demo_resolver,
    identity_add_mapping_command,
    identity_list_command,
    identity_normalize_command,
    identity_resolve_command,
    normalize_with_steps,
)
from nthlayer.identity.normalizer import normalize_service_name


class TestNormalizeServiceName:
    """Tests for normalization logic."""

    def test_normalize_lowercase(self):
        """Test lowercase conversion."""
        assert normalize_service_name("PAYMENT-API") == "payment"

    def test_normalize_env_suffix(self):
        """Test environment suffix removal."""
        assert normalize_service_name("payment-api-prod") == "payment"
        assert normalize_service_name("payment-api-staging") == "payment"
        assert normalize_service_name("payment-api-dev") == "payment"

    def test_normalize_version_suffix(self):
        """Test version suffix removal."""
        assert normalize_service_name("payment-api-v2") == "payment"
        assert normalize_service_name("payment-v3") == "payment"

    def test_normalize_type_suffix(self):
        """Test type suffix removal."""
        assert normalize_service_name("payment-service") == "payment"
        assert normalize_service_name("payment-svc") == "payment"
        assert normalize_service_name("payment-api") == "payment"

    def test_normalize_type_prefix(self):
        """Test type prefix removal."""
        assert normalize_service_name("svc-payment") == "payment"
        assert normalize_service_name("api-payment") == "payment"

    def test_normalize_combined(self):
        """Test combined normalization."""
        # Note: Rules are applied in order, so -v2 is removed first,
        # then -prod (now at end), but -api is not at end so not removed
        assert normalize_service_name("payment-api-prod-v2") == "payment-api-prod"
        # But this order works better:
        assert normalize_service_name("payment-api-v2") == "payment"
        assert normalize_service_name("payment-prod-api") == "payment-prod"


class TestNormalizeWithSteps:
    """Tests for step-by-step normalization."""

    def test_returns_steps(self):
        """Test that steps are returned."""
        result, steps = normalize_with_steps("Payment-API-Prod")
        assert result == "payment"
        assert len(steps) > 0
        assert all(isinstance(s, NormalizationStep) for s in steps)

    def test_tracks_changes(self):
        """Test that changed flag is accurate."""
        _, steps = normalize_with_steps("payment-api-prod")

        # At least one step should show a change
        changed_steps = [s for s in steps if s.changed]
        assert len(changed_steps) > 0

    def test_first_step_is_lowercase(self):
        """Test first step is lowercase."""
        _, steps = normalize_with_steps("PAYMENT")
        assert steps[0].rule_name == "Lowercase"
        assert steps[0].changed is True


class TestDemoData:
    """Tests for demo data generation."""

    def test_create_demo_identities(self):
        """Test demo identities are created."""
        identities = create_demo_identities()
        assert len(identities) >= 3

        names = [i.canonical_name for i in identities]
        assert "payment-api" in names
        assert "search-api" in names

    def test_demo_identities_have_aliases(self):
        """Test demo identities have aliases."""
        identities = create_demo_identities()
        payment = next(i for i in identities if i.canonical_name == "payment-api")

        assert len(payment.aliases) > 0
        assert "payment-service" in payment.aliases

    def test_demo_identities_have_external_ids(self):
        """Test demo identities have external IDs."""
        identities = create_demo_identities()
        payment = next(i for i in identities if i.canonical_name == "payment-api")

        assert "kubernetes" in payment.external_ids
        assert "backstage" in payment.external_ids

    def test_create_demo_resolver(self):
        """Test demo resolver is populated."""
        resolver = create_demo_resolver()
        identities = resolver.list_identities()

        assert len(identities) >= 3

        # Check explicit mappings were added
        assert "legacy-payments" in resolver.explicit_mappings


class TestIdentityResolveCommand:
    """Tests for identity resolve command."""

    def test_resolve_demo_exact_match(self, capsys):
        """Test resolving exact match in demo mode."""
        exit_code = identity_resolve_command(
            name="payment-api",
            demo=True,
        )

        assert exit_code == 0
        captured = capsys.readouterr()
        assert "payment-api" in captured.out
        assert "Match Type" in captured.out

    def test_resolve_demo_alias_match(self, capsys):
        """Test resolving alias match in demo mode."""
        exit_code = identity_resolve_command(
            name="payment-service",
            demo=True,
        )

        assert exit_code == 0
        captured = capsys.readouterr()
        assert "payment-api" in captured.out  # Should resolve to canonical

    def test_resolve_demo_no_match(self, capsys):
        """Test resolving with no match."""
        exit_code = identity_resolve_command(
            name="unknown-service-xyz",
            demo=True,
        )

        assert exit_code == 1  # No match found
        captured = capsys.readouterr()
        assert "No identity match found" in captured.out

    def test_resolve_demo_json_output(self, capsys):
        """Test JSON output format."""
        exit_code = identity_resolve_command(
            name="payment-api",
            output_format="json",
            demo=True,
        )

        assert exit_code == 0
        captured = capsys.readouterr()
        data = json.loads(captured.out)

        assert data["query"] == "payment-api"
        assert data["found"] is True
        assert data["identity"]["canonical_name"] == "payment-api"

    def test_resolve_without_demo_empty(self, capsys):
        """Test resolve without demo returns no match."""
        exit_code = identity_resolve_command(
            name="payment-api",
            demo=False,
        )

        assert exit_code == 1  # No identities registered


class TestIdentityListCommand:
    """Tests for identity list command."""

    def test_list_demo(self, capsys):
        """Test listing demo identities."""
        exit_code = identity_list_command(demo=True)

        assert exit_code == 0
        captured = capsys.readouterr()
        assert "payment-api" in captured.out
        assert "search-api" in captured.out
        assert "identities found" in captured.out

    def test_list_demo_json(self, capsys):
        """Test listing with JSON output."""
        exit_code = identity_list_command(
            output_format="json",
            demo=True,
        )

        assert exit_code == 0
        captured = capsys.readouterr()
        data = json.loads(captured.out)

        assert isinstance(data, list)
        assert len(data) >= 3
        names = [i["canonical_name"] for i in data]
        assert "payment-api" in names

    def test_list_with_filter(self, capsys):
        """Test listing with filter pattern."""
        exit_code = identity_list_command(
            filter_pattern="payment*",
            demo=True,
        )

        assert exit_code == 0
        captured = capsys.readouterr()
        assert "payment-api" in captured.out
        assert "search-api" not in captured.out

    def test_list_without_demo_empty(self, capsys):
        """Test listing without demo shows no identities."""
        exit_code = identity_list_command(demo=False)

        assert exit_code == 0
        captured = capsys.readouterr()
        assert "No identities registered" in captured.out


class TestIdentityNormalizeCommand:
    """Tests for identity normalize command."""

    def test_normalize_basic(self, capsys):
        """Test basic normalization output."""
        exit_code = identity_normalize_command(name="payment-api-prod")

        assert exit_code == 0
        captured = capsys.readouterr()
        assert "payment" in captured.out
        assert "Result:" in captured.out

    def test_normalize_verbose(self, capsys):
        """Test verbose normalization output."""
        exit_code = identity_normalize_command(
            name="Payment-API-Prod-V2",
            verbose=True,
        )

        assert exit_code == 0
        captured = capsys.readouterr()
        assert "Step" in captured.out

    def test_normalize_json(self, capsys):
        """Test JSON output format."""
        exit_code = identity_normalize_command(
            name="payment-api-prod",
            output_format="json",
        )

        assert exit_code == 0
        captured = capsys.readouterr()
        data = json.loads(captured.out)

        assert data["input"] == "payment-api-prod"
        assert data["output"] == "payment"
        assert "steps" in data


class TestIdentityAddMappingCommand:
    """Tests for identity add-mapping command."""

    def test_add_mapping_basic(self, capsys):
        """Test adding basic mapping."""
        exit_code = identity_add_mapping_command(
            raw_name="legacy-payment",
            canonical_name="payment-api",
        )

        assert exit_code == 0
        captured = capsys.readouterr()
        assert "Added mapping" in captured.out
        assert "legacy-payment" in captured.out
        assert "payment-api" in captured.out

    def test_add_mapping_with_provider(self, capsys):
        """Test adding mapping with provider."""
        exit_code = identity_add_mapping_command(
            raw_name="legacy-payment",
            canonical_name="payment-api",
            provider="consul",
        )

        assert exit_code == 0
        captured = capsys.readouterr()
        assert "provider: consul" in captured.out

    def test_add_mapping_json(self, capsys):
        """Test JSON output format."""
        exit_code = identity_add_mapping_command(
            raw_name="legacy-payment",
            canonical_name="payment-api",
            provider="kubernetes",
            output_format="json",
        )

        assert exit_code == 0
        captured = capsys.readouterr()
        data = json.loads(captured.out)

        assert data["raw_name"] == "legacy-payment"
        assert data["canonical_name"] == "payment-api"
        assert data["provider"] == "kubernetes"
