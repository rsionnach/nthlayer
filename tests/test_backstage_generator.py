"""Tests for Backstage entity generator.

Tests for nthlayer generate-backstage command including JSON generation,
schema validation, dry-run mode, and orchestrator integration.
"""

import json
import tempfile
from pathlib import Path

import pytest

from nthlayer.generators.backstage import (
    BackstageGenerationResult,
    band_to_grade,
    gate_result_to_status,
    generate_backstage_entity,
    generate_backstage_from_manifest,
)
from nthlayer.scorecard.models import ScoreBand
from nthlayer.slos.gates import GateResult
from nthlayer.specs.manifest import ReliabilityManifest, SLODefinition


@pytest.fixture
def service_with_slo_yaml():
    """Create a service YAML with SLO resources."""
    with tempfile.TemporaryDirectory() as tmpdir:
        service_file = Path(tmpdir) / "payment-api.yaml"
        service_file.write_text("""
service:
  name: payment-api
  team: payments
  tier: critical
  type: api

resources:
  - kind: SLO
    name: availability
    spec:
      objective: 99.9
      window: 30d
      indicator:
        type: availability
        query: |
          sum(rate(http_requests_total{status=~"[1234].."}[5m]))
          /
          sum(rate(http_requests_total{}[5m]))
  - kind: SLO
    name: latency-p99
    spec:
      objective: 99.0
      window: 30d
      indicator:
        type: latency
        percentile: 99
        threshold_ms: 500
""")
        yield str(service_file)


@pytest.fixture
def minimal_service_yaml():
    """Create a minimal service YAML without SLOs."""
    with tempfile.TemporaryDirectory() as tmpdir:
        service_file = Path(tmpdir) / "minimal-service.yaml"
        service_file.write_text("""
service:
  name: minimal-service
  team: test
  tier: standard
  type: api
""")
        yield str(service_file)


@pytest.fixture
def sample_manifest():
    """Create a sample ReliabilityManifest."""
    return ReliabilityManifest(
        name="test-service",
        team="test-team",
        tier="critical",
        type="api",
        description="Test service for Backstage",
        slos=[
            SLODefinition(
                name="availability",
                target=99.95,
                window="30d",
                slo_type="availability",
                description="API availability SLO",
            ),
            SLODefinition(
                name="latency-p99",
                target=99.0,
                window="30d",
                slo_type="latency",
                description="P99 latency SLO",
            ),
        ],
    )


class TestBackstageGenerationResult:
    """Tests for BackstageGenerationResult dataclass."""

    def test_success_result(self, tmp_path):
        """Test successful generation result."""
        result = BackstageGenerationResult(
            success=True,
            service="payment-api",
            output_file=tmp_path / "backstage.json",
            slo_count=2,
        )

        assert result.success is True
        assert result.service == "payment-api"
        assert result.slo_count == 2
        assert result.error is None

    def test_failure_result(self):
        """Test failed generation result."""
        result = BackstageGenerationResult(
            success=False,
            service="unknown",
            error="Failed to parse service file",
        )

        assert result.success is False
        assert result.error == "Failed to parse service file"
        assert result.output_file is None


class TestGenerateBackstageEntity:
    """Tests for generate_backstage_entity function."""

    def test_generate_with_valid_service(self, service_with_slo_yaml, tmp_path):
        """Test successful Backstage entity generation."""
        result = generate_backstage_entity(
            service_file=service_with_slo_yaml,
            output_dir=tmp_path,
        )

        assert result.success is True
        assert result.service == "payment-api"
        assert result.slo_count == 2
        assert result.output_file is not None
        assert result.output_file.exists()

    def test_generates_valid_json(self, service_with_slo_yaml, tmp_path):
        """Test that output is valid JSON."""
        result = generate_backstage_entity(
            service_file=service_with_slo_yaml,
            output_dir=tmp_path,
        )

        assert result.output_file is not None
        with open(result.output_file) as f:
            entity = json.load(f)

        assert "schemaVersion" in entity
        assert "generatedAt" in entity
        assert "service" in entity

    def test_entity_schema_version(self, service_with_slo_yaml, tmp_path):
        """Test that schema version is v1."""
        result = generate_backstage_entity(
            service_file=service_with_slo_yaml,
            output_dir=tmp_path,
        )

        assert result.output_file is not None
        with open(result.output_file) as f:
            entity = json.load(f)

        assert entity["schemaVersion"] == "v1"

    def test_entity_service_section(self, service_with_slo_yaml, tmp_path):
        """Test service section in generated entity."""
        result = generate_backstage_entity(
            service_file=service_with_slo_yaml,
            output_dir=tmp_path,
        )

        assert result.output_file is not None
        with open(result.output_file) as f:
            entity = json.load(f)

        service = entity["service"]
        assert service["name"] == "payment-api"
        assert service["team"] == "payments"
        assert service["tier"] == "critical"
        assert service["type"] == "api"

    def test_entity_slos_section(self, service_with_slo_yaml, tmp_path):
        """Test SLOs section in generated entity."""
        result = generate_backstage_entity(
            service_file=service_with_slo_yaml,
            output_dir=tmp_path,
        )

        assert result.output_file is not None
        with open(result.output_file) as f:
            entity = json.load(f)

        slos = entity["slos"]
        assert len(slos) == 2

        # Check first SLO
        avail_slo = next(s for s in slos if s["name"] == "availability")
        assert avail_slo["target"] == 99.9
        assert avail_slo["window"] == "30d"
        assert avail_slo["sloType"] == "availability"

    def test_entity_deployment_gate(self, service_with_slo_yaml, tmp_path):
        """Test deployment gate section in generated entity."""
        result = generate_backstage_entity(
            service_file=service_with_slo_yaml,
            output_dir=tmp_path,
        )

        assert result.output_file is not None
        with open(result.output_file) as f:
            entity = json.load(f)

        gate = entity["deploymentGate"]
        assert gate["status"] == "APPROVED"
        # Critical tier has blocking threshold
        assert gate["blockingThreshold"] is not None
        assert gate["warningThreshold"] is not None

    def test_entity_links_section(self, service_with_slo_yaml, tmp_path):
        """Test links section in generated entity."""
        result = generate_backstage_entity(
            service_file=service_with_slo_yaml,
            output_dir=tmp_path,
        )

        assert result.output_file is not None
        with open(result.output_file) as f:
            entity = json.load(f)

        links = entity["links"]
        assert "serviceManifest" in links
        assert "slothSpec" in links
        assert "alertsYaml" in links

    def test_entity_error_budget_null(self, service_with_slo_yaml, tmp_path):
        """Test that error budget values are null in static mode."""
        result = generate_backstage_entity(
            service_file=service_with_slo_yaml,
            output_dir=tmp_path,
        )

        assert result.output_file is not None
        with open(result.output_file) as f:
            entity = json.load(f)

        budget = entity["errorBudget"]
        assert budget["totalMinutes"] is None
        assert budget["consumedMinutes"] is None
        assert budget["burnRate"] is None

    def test_entity_score_null(self, service_with_slo_yaml, tmp_path):
        """Test that score values are null in static mode."""
        result = generate_backstage_entity(
            service_file=service_with_slo_yaml,
            output_dir=tmp_path,
        )

        assert result.output_file is not None
        with open(result.output_file) as f:
            entity = json.load(f)

        score = entity["score"]
        assert score["score"] is None
        assert score["grade"] is None
        assert score["band"] is None

    def test_missing_file_fails(self, tmp_path):
        """Test that missing file returns error."""
        result = generate_backstage_entity(
            service_file="/nonexistent/service.yaml",
            output_dir=tmp_path,
        )

        assert result.success is False
        assert result.error is not None

    def test_creates_output_directory(self, service_with_slo_yaml, tmp_path):
        """Test that output directory is created."""
        output_dir = tmp_path / "nested" / "output"

        result = generate_backstage_entity(
            service_file=service_with_slo_yaml,
            output_dir=output_dir,
        )

        assert result.success is True
        assert output_dir.exists()

    def test_with_environment(self, service_with_slo_yaml, tmp_path):
        """Test generation with environment parameter."""
        result = generate_backstage_entity(
            service_file=service_with_slo_yaml,
            output_dir=tmp_path,
            environment="production",
        )

        assert result.success is True


class TestGenerateBackstageFromManifest:
    """Tests for generate_backstage_from_manifest function."""

    def test_generate_from_manifest(self, sample_manifest, tmp_path):
        """Test successful generation from manifest."""
        result = generate_backstage_from_manifest(
            manifest=sample_manifest,
            output_dir=tmp_path,
        )

        assert result.success is True
        assert result.service == "test-service"
        assert result.slo_count == 2

    def test_manifest_service_section(self, sample_manifest, tmp_path):
        """Test service section from manifest."""
        result = generate_backstage_from_manifest(
            manifest=sample_manifest,
            output_dir=tmp_path,
        )

        assert result.output_file is not None
        with open(result.output_file) as f:
            entity = json.load(f)

        service = entity["service"]
        assert service["name"] == "test-service"
        assert service["team"] == "test-team"
        assert service["tier"] == "critical"
        assert service["description"] == "Test service for Backstage"

    def test_manifest_slos_section(self, sample_manifest, tmp_path):
        """Test SLOs from manifest."""
        result = generate_backstage_from_manifest(
            manifest=sample_manifest,
            output_dir=tmp_path,
        )

        assert result.output_file is not None
        with open(result.output_file) as f:
            entity = json.load(f)

        slos = entity["slos"]
        assert len(slos) == 2

        avail_slo = next(s for s in slos if s["name"] == "availability")
        assert avail_slo["target"] == 99.95
        assert avail_slo["description"] == "API availability SLO"


class TestBandToGrade:
    """Tests for band_to_grade helper function."""

    def test_excellent_to_a(self):
        """Test excellent band maps to A."""
        assert band_to_grade(ScoreBand.EXCELLENT) == "A"
        assert band_to_grade("excellent") == "A"

    def test_good_to_b(self):
        """Test good band maps to B."""
        assert band_to_grade(ScoreBand.GOOD) == "B"
        assert band_to_grade("good") == "B"

    def test_fair_to_c(self):
        """Test fair band maps to C."""
        assert band_to_grade(ScoreBand.FAIR) == "C"
        assert band_to_grade("fair") == "C"

    def test_poor_to_d(self):
        """Test poor band maps to D."""
        assert band_to_grade(ScoreBand.POOR) == "D"
        assert band_to_grade("poor") == "D"

    def test_critical_to_f(self):
        """Test critical band maps to F."""
        assert band_to_grade(ScoreBand.CRITICAL) == "F"
        assert band_to_grade("critical") == "F"

    def test_none_returns_none(self):
        """Test None input returns None."""
        assert band_to_grade(None) is None


class TestGateResultToStatus:
    """Tests for gate_result_to_status helper function."""

    def test_approved_status(self):
        """Test APPROVED gate result."""
        assert gate_result_to_status(GateResult.APPROVED) == "APPROVED"

    def test_warning_status(self):
        """Test WARNING gate result."""
        assert gate_result_to_status(GateResult.WARNING) == "WARNING"

    def test_blocked_status(self):
        """Test BLOCKED gate result."""
        assert gate_result_to_status(GateResult.BLOCKED) == "BLOCKED"


class TestTierThresholds:
    """Tests for tier-based deployment gate thresholds."""

    def test_critical_tier_has_blocking(self, tmp_path):
        """Test critical tier has blocking threshold."""
        with tempfile.TemporaryDirectory() as tmpdir:
            service_file = Path(tmpdir) / "critical-service.yaml"
            service_file.write_text("""
service:
  name: critical-service
  team: platform
  tier: critical
  type: api

resources:
  - kind: SLO
    name: availability
    spec:
      objective: 99.99
      window: 30d
""")

            result = generate_backstage_entity(
                service_file=str(service_file),
                output_dir=tmp_path,
            )

            assert result.output_file is not None
            with open(result.output_file) as f:
                entity = json.load(f)

            gate = entity["deploymentGate"]
            assert gate["blockingThreshold"] is not None

    def test_standard_tier_thresholds(self, tmp_path):
        """Test standard tier has warning threshold."""
        with tempfile.TemporaryDirectory() as tmpdir:
            service_file = Path(tmpdir) / "standard-service.yaml"
            service_file.write_text("""
service:
  name: standard-service
  team: platform
  tier: standard
  type: api

resources:
  - kind: SLO
    name: availability
    spec:
      objective: 99.9
      window: 30d
""")

            result = generate_backstage_entity(
                service_file=str(service_file),
                output_dir=tmp_path,
            )

            assert result.output_file is not None
            with open(result.output_file) as f:
                entity = json.load(f)

            gate = entity["deploymentGate"]
            assert gate["warningThreshold"] is not None
