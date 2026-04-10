"""Tests for nthlayer.generators.docs — service documentation generation."""

from nthlayer.generators.docs import (
    DocsGenerationResult,
    _generate_api_docs,
    _generate_readme,
    generate_docs_from_manifest,
)
from nthlayer.specs.manifest import (
    Dependency,
    Ownership,
    ReliabilityManifest,
    SLODefinition,
)


def _make_manifest(**overrides) -> ReliabilityManifest:
    defaults = dict(
        name="checkout",
        team="platform",
        tier="critical",
        type="api",
        description="Checkout service",
        slos=[SLODefinition(name="avail", target=99.9, window="30d")],
        dependencies=[Dependency(name="postgres", type="database", critical=True)],
    )
    defaults.update(overrides)
    return ReliabilityManifest(**defaults)


class TestDocsGenerationResult:
    def test_defaults(self):
        r = DocsGenerationResult(success=True, service="test")
        assert r.files_generated == []
        assert r.output_dir is None
        assert r.error is None


class TestGenerateReadme:
    def test_includes_service_name(self):
        manifest = _make_manifest()
        readme = _generate_readme(manifest)
        assert "# checkout" in readme

    def test_includes_description(self):
        manifest = _make_manifest(description="Payment processing")
        readme = _generate_readme(manifest)
        assert "Payment processing" in readme

    def test_includes_slo_table(self):
        manifest = _make_manifest()
        readme = _generate_readme(manifest)
        assert "| avail |" in readme
        assert "99.9" in readme

    def test_includes_dependency_table(self):
        manifest = _make_manifest()
        readme = _generate_readme(manifest)
        assert "| postgres |" in readme

    def test_includes_ownership(self):
        manifest = _make_manifest(
            ownership=Ownership(team="platform", slack="#platform", email="team@co.com")
        )
        readme = _generate_readme(manifest)
        assert "#platform" in readme

    def test_no_slos_section_when_empty(self):
        manifest = _make_manifest(slos=[])
        readme = _generate_readme(manifest)
        assert "## SLOs" not in readme


class TestGenerateApiDocs:
    def test_api_type(self):
        manifest = _make_manifest(type="api")
        docs = _generate_api_docs(manifest)
        assert "API Documentation" in docs
        assert "GET /health" in docs

    def test_worker_type(self):
        manifest = _make_manifest(type="worker")
        docs = _generate_api_docs(manifest)
        assert "Job Documentation" in docs

    def test_stream_type(self):
        manifest = _make_manifest(type="stream")
        docs = _generate_api_docs(manifest)
        assert "Event Documentation" in docs

    def test_database_type(self):
        manifest = _make_manifest(type="database")
        docs = _generate_api_docs(manifest)
        assert "Database Documentation" in docs

    def test_ai_gate_type(self):
        manifest = _make_manifest(type="ai-gate")
        docs = _generate_api_docs(manifest)
        assert "AI Gate Documentation" in docs


class TestGenerateDocsFromManifest:
    def test_generates_readme(self, tmp_path):
        manifest = _make_manifest()
        result = generate_docs_from_manifest(manifest, tmp_path)
        assert result.success is True
        assert "README.md" in result.files_generated
        assert (tmp_path / "README.md").exists()

    def test_includes_adr_when_requested(self, tmp_path):
        manifest = _make_manifest()
        result = generate_docs_from_manifest(manifest, tmp_path, include_adr=True)
        assert result.success is True
        assert "adr/README.md" in result.files_generated
        assert "adr/template.md" in result.files_generated
        assert "adr/001-initial-architecture.md" in result.files_generated

    def test_includes_api_when_requested(self, tmp_path):
        manifest = _make_manifest()
        result = generate_docs_from_manifest(manifest, tmp_path, include_api=True)
        assert result.success is True
        assert "api.md" in result.files_generated

    def test_creates_output_dir(self, tmp_path):
        manifest = _make_manifest()
        output = tmp_path / "sub" / "dir"
        result = generate_docs_from_manifest(manifest, output)
        assert result.success is True
        assert output.exists()
