"""Tests for nthlayer.generators.backstage — Backstage entity generation."""

import json


from nthlayer.generators.backstage import (
    BackstageGenerationResult,
    band_to_grade,
    gate_result_to_status,
    generate_backstage_from_manifest,
    _build_backstage_entity_from_manifest,
)
from nthlayer.generators.backstage import ScoreBand
from nthlayer_common.gate_models import GateResult
from nthlayer.specs.manifest import ReliabilityManifest, SLODefinition


def _make_manifest(**overrides) -> ReliabilityManifest:
    defaults = dict(
        name="checkout",
        team="platform",
        tier="critical",
        type="api",
        slos=[SLODefinition(name="avail", target=99.9, window="30d")],
    )
    defaults.update(overrides)
    return ReliabilityManifest(**defaults)


class TestBackstageGenerationResult:
    def test_defaults(self):
        r = BackstageGenerationResult(success=True, service="test")
        assert r.output_file is None
        assert r.slo_count == 0


class TestBandToGrade:
    def test_enum_values(self):
        assert band_to_grade(ScoreBand.EXCELLENT) == "A"
        assert band_to_grade(ScoreBand.GOOD) == "B"
        assert band_to_grade(ScoreBand.FAIR) == "C"
        assert band_to_grade(ScoreBand.POOR) == "D"
        assert band_to_grade(ScoreBand.CRITICAL) == "F"

    def test_string_values(self):
        assert band_to_grade("excellent") == "A"
        assert band_to_grade("critical") == "F"

    def test_none(self):
        assert band_to_grade(None) is None


class TestGateResultToStatus:
    def test_all_values(self):
        assert gate_result_to_status(GateResult.APPROVED) == "APPROVED"
        assert gate_result_to_status(GateResult.WARNING) == "WARNING"
        assert gate_result_to_status(GateResult.BLOCKED) == "BLOCKED"


class TestBuildBackstageEntity:
    def test_entity_structure(self):
        manifest = _make_manifest()
        entity = _build_backstage_entity_from_manifest(manifest)

        assert entity["schemaVersion"] == "v1"
        assert "generatedAt" in entity
        assert entity["service"]["name"] == "checkout"
        assert entity["service"]["team"] == "platform"
        assert entity["service"]["tier"] == "critical"
        assert entity["service"]["type"] == "api"

    def test_slos_section(self):
        manifest = _make_manifest()
        entity = _build_backstage_entity_from_manifest(manifest)

        assert len(entity["slos"]) == 1
        slo = entity["slos"][0]
        assert slo["name"] == "avail"
        assert slo["target"] == 99.9
        assert slo["window"] == "30d"

    def test_deployment_gate_defaults(self):
        manifest = _make_manifest()
        entity = _build_backstage_entity_from_manifest(manifest)

        gate = entity["deploymentGate"]
        assert gate["status"] == "APPROVED"
        assert gate["warningThreshold"] is not None
        assert gate["blockingThreshold"] is not None

    def test_error_budget_section(self):
        manifest = _make_manifest()
        entity = _build_backstage_entity_from_manifest(manifest)

        budget = entity["errorBudget"]
        # Static generation — all values are None
        assert budget["totalMinutes"] is None
        assert budget["remainingPercent"] is None

    def test_links_section(self):
        manifest = _make_manifest()
        entity = _build_backstage_entity_from_manifest(manifest)

        links = entity["links"]
        assert "slothSpec" in links
        assert "checkout" in links["slothSpec"]


class TestGenerateBackstageFromManifest:
    def test_generates_json(self, tmp_path):
        manifest = _make_manifest()
        result = generate_backstage_from_manifest(manifest, tmp_path)

        assert result.success is True
        assert result.slo_count == 1
        assert result.output_file == tmp_path / "backstage.json"

        # Verify JSON is valid
        data = json.loads(result.output_file.read_text())
        assert data["service"]["name"] == "checkout"

    def test_creates_output_dir(self, tmp_path):
        manifest = _make_manifest()
        output = tmp_path / "sub" / "dir"
        result = generate_backstage_from_manifest(manifest, output)
        assert result.success is True
        assert output.exists()

    def test_no_slos(self, tmp_path):
        manifest = _make_manifest(slos=[])
        result = generate_backstage_from_manifest(manifest, tmp_path)
        assert result.success is True
        assert result.slo_count == 0
