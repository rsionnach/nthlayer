"""Tests for service documentation generator.

Tests for nthlayer generate-docs command including README generation,
ADR scaffolding, API documentation stubs, and integration tests.
"""

import tempfile
from pathlib import Path

import pytest

from nthlayer.generators.docs import (
    DocsGenerationResult,
    _generate_adr_scaffold,
    _generate_api_docs,
    _generate_readme,
    generate_docs_from_manifest,
    generate_service_docs,
)
from nthlayer.specs.manifest import (
    Dependency,
    DependencySLO,
    DeploymentConfig,
    DeploymentGates,
    ErrorBudgetGate,
    Observability,
    Ownership,
    ReliabilityManifest,
    SLODefinition,
)


@pytest.fixture
def full_manifest():
    """Create a fully populated ReliabilityManifest."""
    return ReliabilityManifest(
        name="payment-api",
        team="payments",
        tier="critical",
        type="api",
        description="Payment processing API",
        slos=[
            SLODefinition(
                name="availability",
                target=99.95,
                window="30d",
                slo_type="availability",
            ),
            SLODefinition(
                name="latency_p99",
                target=200,
                window="30d",
                slo_type="latency",
            ),
        ],
        dependencies=[
            Dependency(
                name="orders-db",
                type="database",
                critical=True,
                slo=DependencySLO(availability=99.99),
            ),
            Dependency(
                name="auth-service",
                type="api",
                critical=False,
            ),
        ],
        ownership=Ownership(
            team="payments",
            slack="#payments-alerts",
            email="payments@example.com",
            escalation="payments-oncall",
            runbook="https://runbooks.example.com/payment-api",
        ),
        observability=Observability(
            metrics_prefix="payment_api",
            prometheus_job="payment-api",
            grafana_url="https://grafana.example.com/d/payment-api",
        ),
        deployment=DeploymentConfig(
            environments=["staging", "production"],
            gates=DeploymentGates(
                error_budget=ErrorBudgetGate(enabled=True, threshold=0.10),
            ),
        ),
    )


@pytest.fixture
def minimal_manifest():
    """Create a minimal ReliabilityManifest."""
    return ReliabilityManifest(
        name="simple-service",
        team="platform",
        tier="standard",
        type="api",
    )


@pytest.fixture
def worker_manifest():
    """Create a worker-type manifest."""
    return ReliabilityManifest(
        name="order-processor",
        team="fulfillment",
        tier="standard",
        type="worker",
        slos=[
            SLODefinition(name="throughput", target=1000, window="30d", slo_type="throughput"),
        ],
    )


@pytest.fixture
def stream_manifest():
    """Create a stream-type manifest."""
    return ReliabilityManifest(
        name="event-router",
        team="platform",
        tier="high",
        type="stream",
    )


@pytest.fixture
def service_yaml_file():
    """Create a service YAML file for integration tests."""
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
      objective: 99.95
      window: 30d
      indicator:
        type: availability
""")
        yield str(service_file)


class TestDocsGenerationResult:
    """Tests for DocsGenerationResult dataclass."""

    def test_success_result(self):
        result = DocsGenerationResult(
            success=True,
            service="payment-api",
            files_generated=["README.md", "api.md"],
            output_dir=Path("/tmp/docs"),
        )
        assert result.success is True
        assert result.service == "payment-api"
        assert len(result.files_generated) == 2
        assert result.error is None

    def test_failure_result(self):
        result = DocsGenerationResult(
            success=False,
            service="unknown",
            error="File not found",
        )
        assert result.success is False
        assert result.error == "File not found"
        assert result.files_generated == []

    def test_default_fields(self):
        result = DocsGenerationResult(success=True, service="test")
        assert result.files_generated == []
        assert result.output_dir is None
        assert result.error is None


class TestGenerateReadme:
    """Tests for README generation."""

    def test_contains_service_name(self, full_manifest):
        readme = _generate_readme(full_manifest)
        assert "# payment-api" in readme

    def test_contains_description(self, full_manifest):
        readme = _generate_readme(full_manifest)
        assert "Payment processing API" in readme

    def test_contains_ownership(self, full_manifest):
        readme = _generate_readme(full_manifest)
        assert "## Ownership" in readme
        assert "payments" in readme
        assert "#payments-alerts" in readme
        assert "payments@example.com" in readme

    def test_contains_architecture(self, full_manifest):
        readme = _generate_readme(full_manifest)
        assert "## Architecture" in readme
        assert "critical" in readme
        assert "api" in readme
        assert "payment_api" in readme

    def test_contains_slos_table(self, full_manifest):
        readme = _generate_readme(full_manifest)
        assert "## SLOs" in readme
        assert "availability" in readme
        assert "99.95" in readme
        assert "latency_p99" in readme

    def test_contains_dependencies_table(self, full_manifest):
        readme = _generate_readme(full_manifest)
        assert "## Dependencies" in readme
        assert "orders-db" in readme
        assert "auth-service" in readme
        assert "database" in readme

    def test_contains_deployment(self, full_manifest):
        readme = _generate_readme(full_manifest)
        assert "## Deployment" in readme
        assert "staging" in readme
        assert "production" in readme
        assert "Error Budget" in readme

    def test_contains_runbook_link(self, full_manifest):
        readme = _generate_readme(full_manifest)
        assert "## Runbook" in readme
        assert "https://runbooks.example.com/payment-api" in readme

    def test_contains_apis_section(self, full_manifest):
        readme = _generate_readme(full_manifest)
        assert "## APIs" in readme
        assert "grafana.example.com" in readme

    def test_minimal_manifest_readme(self, minimal_manifest):
        readme = _generate_readme(minimal_manifest)
        assert "# simple-service" in readme
        assert "## Ownership" in readme
        assert "## Architecture" in readme
        # No SLOs or Dependencies sections when empty
        assert "## SLOs" not in readme
        assert "## Dependencies" not in readme

    def test_no_deployment_config(self, minimal_manifest):
        readme = _generate_readme(minimal_manifest)
        assert "No deployment configuration defined" in readme

    def test_runbook_placeholder(self, minimal_manifest):
        readme = _generate_readme(minimal_manifest)
        assert "TODO: Add runbook link" in readme


class TestGenerateADR:
    """Tests for ADR scaffold generation."""

    def test_creates_adr_directory(self, full_manifest):
        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir)
            files = _generate_adr_scaffold(full_manifest, output_dir)
            assert (output_dir / "adr").is_dir()
            assert len(files) == 3

    def test_creates_index(self, full_manifest):
        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir)
            _generate_adr_scaffold(full_manifest, output_dir)
            index = (output_dir / "adr" / "README.md").read_text()
            assert "Architecture Decision Records" in index
            assert "payment-api" in index

    def test_creates_template(self, full_manifest):
        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir)
            _generate_adr_scaffold(full_manifest, output_dir)
            template = (output_dir / "adr" / "template.md").read_text()
            assert "## Status" in template
            assert "## Context" in template
            assert "## Decision" in template
            assert "## Consequences" in template

    def test_creates_initial_adr(self, full_manifest):
        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir)
            _generate_adr_scaffold(full_manifest, output_dir)
            adr = (output_dir / "adr" / "001-initial-architecture.md").read_text()
            assert "payment-api" in adr
            assert "critical" in adr
            assert "payments" in adr
            assert "availability" in adr
            assert "orders-db" in adr

    def test_adr_file_list(self, full_manifest):
        with tempfile.TemporaryDirectory() as tmpdir:
            files = _generate_adr_scaffold(full_manifest, Path(tmpdir))
            assert "adr/README.md" in files
            assert "adr/template.md" in files
            assert "adr/001-initial-architecture.md" in files


class TestGenerateAPIDocs:
    """Tests for API documentation generation."""

    def test_api_type_generates_http_scaffold(self, full_manifest):
        api_doc = _generate_api_docs(full_manifest)
        assert "# API Documentation" in api_doc
        assert "GET /health" in api_doc
        assert "GET /api/v1/resource" in api_doc

    def test_worker_type_generates_job_scaffold(self, worker_manifest):
        api_doc = _generate_api_docs(worker_manifest)
        assert "# Job Documentation" in api_doc
        assert "Queue" in api_doc
        assert "Retry Policy" in api_doc

    def test_stream_type_generates_event_scaffold(self, stream_manifest):
        api_doc = _generate_api_docs(stream_manifest)
        assert "# Event Documentation" in api_doc
        assert "example.event" in api_doc

    def test_database_type_generates_schema_scaffold(self):
        manifest = ReliabilityManifest(
            name="orders-db", team="data", tier="critical", type="database"
        )
        api_doc = _generate_api_docs(manifest)
        assert "# Database Documentation" in api_doc
        assert "Schema" in api_doc

    def test_ai_gate_type_generates_decision_scaffold(self):
        manifest = ReliabilityManifest(
            name="fraud-detector",
            team="risk",
            tier="critical",
            type="ai-gate",
            slos=[
                SLODefinition(name="reversal_rate", target=0.05, slo_type="judgment"),
                SLODefinition(name="availability", target=99.9, slo_type="availability"),
            ],
        )
        api_doc = _generate_api_docs(manifest)
        assert "# AI Gate Documentation" in api_doc
        assert "Decision Endpoints" in api_doc
        assert "Judgment SLOs" in api_doc
        assert "reversal_rate" in api_doc

    def test_slo_expectations_included(self, full_manifest):
        api_doc = _generate_api_docs(full_manifest)
        assert "SLO Expectations" in api_doc
        assert "99.95" in api_doc


class TestGenerateDocsIntegration:
    """Integration tests: service YAML → generated docs directory."""

    def test_end_to_end_from_yaml(self, service_yaml_file):
        with tempfile.TemporaryDirectory() as tmpdir:
            result = generate_service_docs(
                service_file=service_yaml_file,
                output_dir=tmpdir,
                include_adr=True,
                include_api=True,
            )
            assert result.success is True
            assert result.service == "payment-api"
            assert "README.md" in result.files_generated
            assert "api.md" in result.files_generated
            assert "adr/README.md" in result.files_generated
            assert "adr/template.md" in result.files_generated
            assert "adr/001-initial-architecture.md" in result.files_generated

            # Verify files exist on disk
            output = Path(tmpdir)
            assert (output / "README.md").exists()
            assert (output / "api.md").exists()
            assert (output / "adr" / "README.md").exists()
            assert (output / "adr" / "template.md").exists()
            assert (output / "adr" / "001-initial-architecture.md").exists()

    def test_readme_only(self, service_yaml_file):
        with tempfile.TemporaryDirectory() as tmpdir:
            result = generate_service_docs(
                service_file=service_yaml_file,
                output_dir=tmpdir,
            )
            assert result.success is True
            assert result.files_generated == ["README.md"]
            assert not (Path(tmpdir) / "adr").exists()
            assert not (Path(tmpdir) / "api.md").exists()

    def test_from_manifest(self, full_manifest):
        with tempfile.TemporaryDirectory() as tmpdir:
            result = generate_docs_from_manifest(
                manifest=full_manifest,
                output_dir=tmpdir,
                include_adr=True,
                include_api=True,
            )
            assert result.success is True
            assert result.service == "payment-api"
            assert len(result.files_generated) == 5

    def test_nonexistent_file(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            result = generate_service_docs(
                service_file="/nonexistent/path.yaml",
                output_dir=tmpdir,
            )
            assert result.success is False
            assert result.error is not None

    def test_creates_output_dir(self, service_yaml_file):
        with tempfile.TemporaryDirectory() as tmpdir:
            nested_dir = Path(tmpdir) / "deep" / "nested" / "output"
            result = generate_service_docs(
                service_file=service_yaml_file,
                output_dir=nested_dir,
            )
            assert result.success is True
            assert nested_dir.exists()
            assert (nested_dir / "README.md").exists()
