"""Tests for ownership resolution."""

import json

import pytest
from nthlayer.identity.ownership import (
    DEFAULT_CONFIDENCE,
    OwnershipAttribution,
    OwnershipResolver,
    OwnershipSignal,
    OwnershipSource,
    create_demo_attribution,
)
from nthlayer.identity.ownership_providers.codeowners import CODEOWNERSProvider
from nthlayer.identity.ownership_providers.declared import DeclaredOwnershipProvider


class TestOwnershipSource:
    """Tests for OwnershipSource enum."""

    def test_all_sources_have_default_confidence(self):
        """All sources should have a default confidence score."""
        for source in OwnershipSource:
            assert source in DEFAULT_CONFIDENCE
            assert 0 <= DEFAULT_CONFIDENCE[source] <= 1

    def test_declared_has_highest_confidence(self):
        """Declared source should have highest confidence."""
        assert DEFAULT_CONFIDENCE[OwnershipSource.DECLARED] == 1.0

    def test_pagerduty_high_confidence(self):
        """PagerDuty should have high confidence (who gets paged owns it)."""
        assert DEFAULT_CONFIDENCE[OwnershipSource.PAGERDUTY] == 0.95


class TestOwnershipSignal:
    """Tests for OwnershipSignal dataclass."""

    def test_create_signal(self):
        """Test creating an ownership signal."""
        signal = OwnershipSignal(
            source=OwnershipSource.PAGERDUTY,
            owner="payments-team",
            confidence=0.95,
            owner_type="team",
            metadata={"escalation_policy": "payments-oncall"},
        )
        assert signal.source == OwnershipSource.PAGERDUTY
        assert signal.owner == "payments-team"
        assert signal.confidence == 0.95
        assert signal.owner_type == "team"

    def test_signal_to_dict(self):
        """Test signal serialization."""
        signal = OwnershipSignal(
            source=OwnershipSource.BACKSTAGE,
            owner="team-identity",
            confidence=0.90,
        )
        data = signal.to_dict()
        assert data["source"] == "backstage"
        assert data["owner"] == "team-identity"
        assert data["confidence"] == 0.90


class TestOwnershipAttribution:
    """Tests for OwnershipAttribution dataclass."""

    def test_create_attribution(self):
        """Test creating an ownership attribution."""
        attribution = OwnershipAttribution(
            service="payment-api",
            owner="payments-team",
            confidence=0.95,
            source=OwnershipSource.PAGERDUTY,
        )
        assert attribution.service == "payment-api"
        assert attribution.owner == "payments-team"

    def test_attribution_to_dict(self):
        """Test attribution serialization."""
        attribution = OwnershipAttribution(
            service="payment-api",
            owner="payments-team",
            confidence=0.95,
            source=OwnershipSource.PAGERDUTY,
            signals=[
                OwnershipSignal(
                    source=OwnershipSource.PAGERDUTY,
                    owner="payments-team",
                    confidence=0.95,
                )
            ],
            slack_channel="#team-payments",
            pagerduty_escalation="payments-oncall",
        )
        data = attribution.to_dict()
        assert data["service"] == "payment-api"
        assert data["owner"] == "payments-team"
        assert data["source"] == "pagerduty"
        assert len(data["signals"]) == 1
        assert data["contact"]["slack_channel"] == "#team-payments"
        assert data["contact"]["pagerduty_escalation"] == "payments-oncall"

    def test_attribution_json_serializable(self):
        """Test that attribution can be serialized to JSON."""
        attribution = create_demo_attribution()
        data = attribution.to_dict()
        json_str = json.dumps(data)
        assert "payment-api" in json_str


class TestDeclaredOwnershipProvider:
    """Tests for DeclaredOwnershipProvider."""

    @pytest.mark.asyncio
    async def test_get_owner_with_team(self):
        """Test getting owner from declared team."""
        provider = DeclaredOwnershipProvider()
        provider.set_declaration("payment-api", team="payments-team")

        signal = await provider.get_owner("payment-api")

        assert signal is not None
        assert signal.owner == "payments-team"
        assert signal.confidence == 1.0
        assert signal.owner_type == "team"

    @pytest.mark.asyncio
    async def test_get_owner_with_owner_field(self):
        """Test getting owner from owner field (individual)."""
        provider = DeclaredOwnershipProvider()
        provider.set_declaration("payment-api", owner="john@company.com")

        signal = await provider.get_owner("payment-api")

        assert signal is not None
        assert signal.owner == "john@company.com"
        assert signal.owner_type == "individual"

    @pytest.mark.asyncio
    async def test_team_takes_precedence_over_owner(self):
        """Test that team field takes precedence over owner."""
        provider = DeclaredOwnershipProvider()
        provider.set_declaration(
            "payment-api",
            team="payments-team",
            owner="john@company.com",
        )

        signal = await provider.get_owner("payment-api")

        assert signal is not None
        assert signal.owner == "payments-team"
        assert signal.owner_type == "team"

    @pytest.mark.asyncio
    async def test_get_owner_not_found(self):
        """Test getting owner for unknown service."""
        provider = DeclaredOwnershipProvider()

        signal = await provider.get_owner("unknown-service")

        assert signal is None

    @pytest.mark.asyncio
    async def test_health_check(self):
        """Test health check always returns healthy."""
        provider = DeclaredOwnershipProvider()

        health = await provider.health_check()

        assert health.healthy is True

    def test_provider_properties(self):
        """Test provider properties."""
        provider = DeclaredOwnershipProvider()

        assert provider.name == "declared"
        assert provider.source == OwnershipSource.DECLARED
        assert provider.default_confidence == 1.0


class TestCODEOWNERSProvider:
    """Tests for CODEOWNERSProvider."""

    @pytest.mark.asyncio
    async def test_get_owner_from_codeowners(self, tmp_path):
        """Test getting owner from CODEOWNERS file."""
        codeowners = tmp_path / ".github" / "CODEOWNERS"
        codeowners.parent.mkdir(parents=True)
        codeowners.write_text("* @acme/platform\n")

        provider = CODEOWNERSProvider(repo_root=tmp_path)
        signal = await provider.get_owner("any-service")

        assert signal is not None
        assert signal.owner == "@acme/platform"
        assert signal.source == OwnershipSource.CODEOWNERS
        assert signal.confidence == 0.85

    @pytest.mark.asyncio
    async def test_get_owner_from_root_codeowners(self, tmp_path):
        """Test getting owner from root CODEOWNERS file."""
        codeowners = tmp_path / "CODEOWNERS"
        codeowners.write_text("* @myteam\n")

        provider = CODEOWNERSProvider(repo_root=tmp_path)
        signal = await provider.get_owner("any-service")

        assert signal is not None
        assert signal.owner == "@myteam"

    @pytest.mark.asyncio
    async def test_get_owner_no_codeowners(self, tmp_path):
        """Test when no CODEOWNERS file exists."""
        provider = CODEOWNERSProvider(repo_root=tmp_path)
        signal = await provider.get_owner("any-service")

        assert signal is None

    @pytest.mark.asyncio
    async def test_get_owner_no_default_owner(self, tmp_path):
        """Test CODEOWNERS without default owner."""
        codeowners = tmp_path / "CODEOWNERS"
        codeowners.write_text("/src/payments/ @payments-team\n")

        provider = CODEOWNERSProvider(repo_root=tmp_path)
        signal = await provider.get_owner("any-service")

        # No default owner (*), so no signal
        assert signal is None

    @pytest.mark.asyncio
    async def test_owner_type_inference(self, tmp_path):
        """Test owner type inference from format."""
        # Group format
        codeowners = tmp_path / "CODEOWNERS"
        codeowners.write_text("* @org/team\n")

        provider = CODEOWNERSProvider(repo_root=tmp_path)
        signal = await provider.get_owner("any-service")

        assert signal is not None
        assert signal.owner_type == "group"

    @pytest.mark.asyncio
    async def test_health_check_with_codeowners(self, tmp_path):
        """Test health check when CODEOWNERS exists."""
        codeowners = tmp_path / ".github" / "CODEOWNERS"
        codeowners.parent.mkdir(parents=True)
        codeowners.write_text("* @team\n")

        provider = CODEOWNERSProvider(repo_root=tmp_path)
        health = await provider.health_check()

        assert health.healthy is True
        assert ".github/CODEOWNERS" in health.message

    @pytest.mark.asyncio
    async def test_health_check_without_codeowners(self, tmp_path):
        """Test health check when no CODEOWNERS exists."""
        provider = CODEOWNERSProvider(repo_root=tmp_path)
        health = await provider.health_check()

        assert health.healthy is False

    def test_provider_properties(self):
        """Test provider properties."""
        provider = CODEOWNERSProvider()

        assert provider.name == "codeowners"
        assert provider.source == OwnershipSource.CODEOWNERS
        assert provider.default_confidence == 0.85


class TestOwnershipResolver:
    """Tests for OwnershipResolver."""

    @pytest.mark.asyncio
    async def test_resolve_with_declared_owner(self):
        """Test resolving with declared owner."""
        resolver = OwnershipResolver()

        attribution = await resolver.resolve(
            service="payment-api",
            declared_team="payments-team",
        )

        assert attribution.owner == "payments-team"
        assert attribution.confidence == 1.0
        assert attribution.source == OwnershipSource.DECLARED

    @pytest.mark.asyncio
    async def test_resolve_with_declared_owner_individual(self):
        """Test resolving with declared owner as individual."""
        resolver = OwnershipResolver()

        attribution = await resolver.resolve(
            service="payment-api",
            declared_owner="john@company.com",
        )

        assert attribution.owner == "john@company.com"
        assert attribution.owner_type == "individual"
        assert attribution.source == OwnershipSource.DECLARED

    @pytest.mark.asyncio
    async def test_resolve_with_provider(self, tmp_path):
        """Test resolving with a provider."""
        # Create CODEOWNERS
        codeowners = tmp_path / "CODEOWNERS"
        codeowners.write_text("* @platform-team\n")

        resolver = OwnershipResolver()
        resolver.add_provider(CODEOWNERSProvider(repo_root=tmp_path))

        attribution = await resolver.resolve(service="payment-api")

        assert attribution.owner == "@platform-team"
        assert attribution.source == OwnershipSource.CODEOWNERS
        assert len(attribution.signals) == 1

    @pytest.mark.asyncio
    async def test_declared_takes_precedence(self, tmp_path):
        """Test that declared owner takes precedence over providers."""
        # Create CODEOWNERS
        codeowners = tmp_path / "CODEOWNERS"
        codeowners.write_text("* @platform-team\n")

        resolver = OwnershipResolver()
        resolver.add_provider(CODEOWNERSProvider(repo_root=tmp_path))

        attribution = await resolver.resolve(
            service="payment-api",
            declared_team="payments-team",
        )

        # Declared should win
        assert attribution.owner == "payments-team"
        assert attribution.source == OwnershipSource.DECLARED
        # But CODEOWNERS signal should still be present
        assert len(attribution.signals) == 2

    @pytest.mark.asyncio
    async def test_signals_sorted_by_confidence(self, tmp_path):
        """Test that signals are sorted by confidence."""
        codeowners = tmp_path / "CODEOWNERS"
        codeowners.write_text("* @codeowners-team\n")

        resolver = OwnershipResolver()
        resolver.add_provider(CODEOWNERSProvider(repo_root=tmp_path))

        attribution = await resolver.resolve(
            service="payment-api",
            declared_team="declared-team",
        )

        # Signals should be sorted highest confidence first
        assert attribution.signals[0].confidence >= attribution.signals[-1].confidence
        assert attribution.signals[0].source == OwnershipSource.DECLARED

    @pytest.mark.asyncio
    async def test_no_signals_returns_empty_attribution(self):
        """Test resolving with no signals."""
        resolver = OwnershipResolver()

        attribution = await resolver.resolve(service="unknown-service")

        assert attribution.owner is None
        assert attribution.confidence == 0.0
        assert attribution.source is None
        assert len(attribution.signals) == 0

    @pytest.mark.asyncio
    async def test_slack_channel_inferred(self):
        """Test that Slack channel is inferred from owner."""
        resolver = OwnershipResolver()

        attribution = await resolver.resolve(
            service="payment-api",
            declared_team="payments",
        )

        assert attribution.slack_channel == "#team-payments"


class TestCreateDemoAttribution:
    """Tests for demo attribution helper."""

    def test_create_demo_attribution(self):
        """Test creating demo attribution."""
        attribution = create_demo_attribution()

        assert attribution.service == "payment-api"
        assert attribution.owner == "payments-team"
        assert len(attribution.signals) == 5
        assert attribution.pagerduty_escalation == "payments-escalation"
        assert attribution.slack_channel == "#team-payments"

    def test_demo_has_all_source_types(self):
        """Test that demo includes multiple source types."""
        attribution = create_demo_attribution()

        sources = {s.source for s in attribution.signals}
        assert OwnershipSource.DECLARED in sources
        assert OwnershipSource.PAGERDUTY in sources
        assert OwnershipSource.BACKSTAGE in sources
        assert OwnershipSource.CODEOWNERS in sources
        assert OwnershipSource.KUBERNETES in sources


class TestOwnershipCLI:
    """Tests for ownership CLI command."""

    def test_demo_mode(self, capsys, tmp_path):
        """Test demo mode output."""
        from nthlayer.cli.ownership import ownership_command

        # Create a temporary service file (not used in demo mode)
        service_file = tmp_path / "service.yaml"
        service_file.write_text("name: test-service\ntier: standard\n")

        exit_code = ownership_command(
            service_file=str(service_file),
            demo=True,
        )

        assert exit_code == 0
        captured = capsys.readouterr()

        # Check output contains expected content
        assert "Ownership: payment-api" in captured.out
        assert "payments-team" in captured.out
        assert "declared" in captured.out
        assert "pagerduty" in captured.out

    def test_demo_mode_json(self, capsys, tmp_path):
        """Test demo mode with JSON output."""
        from nthlayer.cli.ownership import ownership_command

        service_file = tmp_path / "service.yaml"
        service_file.write_text("name: test-service\ntier: standard\n")

        exit_code = ownership_command(
            service_file=str(service_file),
            output_format="json",
            demo=True,
        )

        assert exit_code == 0
        captured = capsys.readouterr()

        # Parse JSON output
        data = json.loads(captured.out)
        assert data["service"] == "payment-api"
        assert data["owner"] == "payments-team"
        assert len(data["signals"]) == 5

    def test_with_codeowners(self, capsys, tmp_path):
        """Test with CODEOWNERS file."""
        from nthlayer.cli.ownership import ownership_command

        # Create service file
        service_file = tmp_path / "service.yaml"
        service_file.write_text(
            """
service:
  name: test-service
  team: test-team
  tier: standard
  type: api
"""
        )

        # Create CODEOWNERS
        codeowners = tmp_path / "CODEOWNERS"
        codeowners.write_text("* @test-codeowners\n")

        exit_code = ownership_command(
            service_file=str(service_file),
            output_format="json",
            codeowners_root=str(tmp_path),
        )

        assert exit_code == 0
        captured = capsys.readouterr()

        data = json.loads(captured.out)
        assert data["owner"] == "test-team"  # Declared wins
        # Should have declared and codeowners signals
        sources = [s["source"] for s in data["signals"]]
        assert "declared" in sources
        assert "codeowners" in sources

    def test_invalid_service_file(self, capsys, tmp_path):
        """Test error with invalid service file."""
        from nthlayer.cli.ownership import ownership_command

        service_file = tmp_path / "nonexistent.yaml"

        exit_code = ownership_command(
            service_file=str(service_file),
        )

        assert exit_code == 2
        captured = capsys.readouterr()
        assert "Error parsing service file" in captured.out
