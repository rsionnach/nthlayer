"""Tests for nthlayer.generators.sloth — Sloth SLO spec generation."""

import yaml

from nthlayer.generators.sloth import (
    SlothGenerationResult,
    convert_indicator_to_sli,
    convert_to_sloth_slo,
    generate_alerting_config,
    generate_sloth_from_manifest,
    _extract_error_query,
    _extract_total_query,
)
from nthlayer.specs.manifest import ReliabilityManifest, SLODefinition
from nthlayer.specs.models import ServiceContext


class TestSlothGenerationResult:
    def test_defaults(self):
        r = SlothGenerationResult(success=True, service="test")
        assert r.output_file is None
        assert r.slo_count == 0
        assert r.error is None


class TestConvertIndicatorToSli:
    def test_availability_indicator(self):
        indicator = {
            "type": "availability",
            "query": "sum(rate(http_ok[5m])) / sum(rate(http_total[5m]))",
        }
        sli = convert_indicator_to_sli(indicator)
        assert "events" in sli
        assert "error_query" in sli["events"]
        assert "total_query" in sli["events"]

    def test_latency_indicator(self):
        indicator = {
            "type": "latency",
            "query": "histogram_quantile(0.95, rate(http_duration_bucket[5m]))",
            "threshold_ms": 500,
        }
        sli = convert_indicator_to_sli(indicator)
        assert "events" in sli
        # Error query should include threshold
        assert "0.5" in sli["events"]["error_query"]  # 500ms = 0.5s

    def test_generic_indicator(self):
        indicator = {
            "type": "custom",
            "error_query": "errors",
            "total_query": "totals",
        }
        sli = convert_indicator_to_sli(indicator)
        assert sli["events"]["error_query"] == "errors"
        assert sli["events"]["total_query"] == "totals"

    def test_default_type_is_availability(self):
        sli = convert_indicator_to_sli({})
        assert "events" in sli


class TestExtractErrorQuery:
    def test_with_code_exclusion(self):
        query = 'sum(rate(http{code!~"5.."}[5m])) / sum(rate(http[5m]))'
        result = _extract_error_query(query)
        assert "code=~" in result

    def test_empty_query(self):
        assert _extract_error_query("") == ""


class TestExtractTotalQuery:
    def test_splits_on_division(self):
        query = "numerator / denominator"
        assert _extract_total_query(query) == "denominator"

    def test_no_division(self):
        query = "single_metric"
        assert _extract_total_query(query) == "single_metric"

    def test_empty_query(self):
        assert _extract_total_query("") == ""


class TestGenerateAlertingConfig:
    def test_critical_tier_has_page_alert(self):
        config = generate_alerting_config("avail", "checkout", "critical")
        assert "page_alert" in config
        assert config["page_alert"]["labels"]["severity"] == "critical"

    def test_standard_tier_no_page_alert(self):
        config = generate_alerting_config("avail", "checkout", "standard")
        assert "page_alert" not in config

    def test_always_has_ticket_alert(self):
        config = generate_alerting_config("avail", "checkout", "standard")
        assert "ticket_alert" in config
        assert config["ticket_alert"]["labels"]["severity"] == "warning"

    def test_alert_name_pascal_case(self):
        config = generate_alerting_config("p99-latency", "payment-api", "critical")
        assert config["name"] == "PaymentApiP99Latency"


class TestConvertToSlothSlo:
    def test_basic_conversion(self):
        spec = {
            "objective": 99.9,
            "indicator": {"type": "availability", "query": "test_query"},
        }
        ctx = ServiceContext(name="checkout", team="platform", tier="critical", type="api")
        result = convert_to_sloth_slo("availability", spec, ctx)

        assert result["name"] == "availability"
        assert result["objective"] == 99.9
        assert "sli" in result
        assert "alerting" in result


class TestGenerateSlothFromManifest:
    def test_no_slos_returns_error(self, tmp_path):
        manifest = ReliabilityManifest(
            name="test-svc", team="platform", tier="standard", type="api"
        )
        result = generate_sloth_from_manifest(manifest, tmp_path)
        assert result.success is False
        assert "No SLOs" in result.error

    def test_generates_valid_yaml(self, tmp_path):
        manifest = ReliabilityManifest(
            name="test-svc",
            team="platform",
            tier="critical",
            type="api",
            slos=[
                SLODefinition(
                    name="availability",
                    target=99.9,
                    window="30d",
                    slo_type="availability",
                    indicator_query="sum(rate(http_ok[5m]))/sum(rate(http_total[5m]))",
                ),
            ],
        )
        result = generate_sloth_from_manifest(manifest, tmp_path)

        assert result.success is True
        assert result.slo_count == 1
        assert result.output_file is not None

        # Verify written YAML
        data = yaml.safe_load(result.output_file.read_text())
        assert data["version"] == "prometheus/v1"
        assert data["service"] == "test-svc"
        assert len(data["slos"]) == 1
        assert data["slos"][0]["name"] == "availability"
        assert data["slos"][0]["objective"] == 99.9

    def test_variable_substitution(self, tmp_path):
        manifest = ReliabilityManifest(
            name="checkout",
            team="payments",
            tier="critical",
            type="api",
            slos=[
                SLODefinition(
                    name="avail",
                    target=99.9,
                    window="30d",
                    indicator_query="http_requests{service='${service}',team='${team}'}",
                ),
            ],
        )
        result = generate_sloth_from_manifest(manifest, tmp_path)
        assert result.success is True

        data = yaml.safe_load(result.output_file.read_text())
        slo = data["slos"][0]
        # The query in the SLI should have variables substituted
        sli_str = str(slo["sli"])
        assert "${service}" not in sli_str
