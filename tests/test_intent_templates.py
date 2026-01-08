"""
Shared tests for all intent-based dashboard templates.

Uses parametrization to test all templates with the same test patterns.
"""

import pytest
from nthlayer.dashboards.templates.base_intent import IntentBasedTemplate
from nthlayer.dashboards.templates.consul_intent import ConsulIntentTemplate
from nthlayer.dashboards.templates.elasticsearch_intent import ElasticsearchIntentTemplate
from nthlayer.dashboards.templates.etcd_intent import EtcdIntentTemplate
from nthlayer.dashboards.templates.haproxy_intent import HaproxyIntentTemplate
from nthlayer.dashboards.templates.http_intent import HTTPIntentTemplate
from nthlayer.dashboards.templates.kafka_intent import KafkaIntentTemplate
from nthlayer.dashboards.templates.mongodb_intent import MongoDBIntentTemplate
from nthlayer.dashboards.templates.mysql_intent import MySQLIntentTemplate
from nthlayer.dashboards.templates.nats_intent import NatsIntentTemplate
from nthlayer.dashboards.templates.nginx_intent import NginxIntentTemplate
from nthlayer.dashboards.templates.postgresql_intent import PostgreSQLIntentTemplate
from nthlayer.dashboards.templates.pulsar_intent import PulsarIntentTemplate
from nthlayer.dashboards.templates.rabbitmq_intent import RabbitmqIntentTemplate
from nthlayer.dashboards.templates.redis_intent import RedisIntentTemplate
from nthlayer.dashboards.templates.stream_intent import StreamIntentTemplate
from nthlayer.dashboards.templates.traefik_intent import TraefikIntentTemplate
from nthlayer.dashboards.templates.worker_intent import WorkerIntentTemplate

# All intent template classes
INTENT_TEMPLATES = [
    ConsulIntentTemplate,
    ElasticsearchIntentTemplate,
    EtcdIntentTemplate,
    HaproxyIntentTemplate,
    HTTPIntentTemplate,
    KafkaIntentTemplate,
    MongoDBIntentTemplate,
    MySQLIntentTemplate,
    NatsIntentTemplate,
    NginxIntentTemplate,
    PostgreSQLIntentTemplate,
    PulsarIntentTemplate,
    RabbitmqIntentTemplate,
    RedisIntentTemplate,
    StreamIntentTemplate,
    TraefikIntentTemplate,
    WorkerIntentTemplate,
]


@pytest.fixture(params=INTENT_TEMPLATES, ids=lambda cls: cls.__name__)
def template_class(request):
    """Parametrized fixture providing each template class."""
    return request.param


@pytest.fixture
def template_instance(template_class):
    """Create an instance of the template."""
    return template_class()


class TestIntentTemplateProperties:
    """Test basic properties of all intent templates."""

    def test_has_name_property(self, template_instance):
        """Test that template has name property."""
        assert hasattr(template_instance, "name")
        name = template_instance.name
        assert isinstance(name, str)
        assert len(name) > 0

    def test_has_display_name_property(self, template_instance):
        """Test that template has display_name property."""
        assert hasattr(template_instance, "display_name")
        display_name = template_instance.display_name
        assert isinstance(display_name, str)
        assert len(display_name) > 0

    def test_is_intent_based_template(self, template_instance):
        """Test that template is instance of IntentBasedTemplate."""
        assert isinstance(template_instance, IntentBasedTemplate)


class TestIntentTemplatePanelSpecs:
    """Test panel specifications from intent templates."""

    def test_get_panel_specs_returns_list(self, template_instance):
        """Test that get_panel_specs returns a list."""
        specs = template_instance.get_panel_specs("test-service")
        assert isinstance(specs, list)

    def test_get_panel_specs_with_variable(self, template_instance):
        """Test get_panel_specs with Grafana variable."""
        specs = template_instance.get_panel_specs("$service")
        assert isinstance(specs, list)
        assert len(specs) > 0

    def test_panel_specs_have_title(self, template_instance):
        """Test that each panel spec has a title."""
        specs = template_instance.get_panel_specs("test-service")

        for spec in specs:
            assert hasattr(spec, "title")
            assert hasattr(spec, "panel_type")


class TestIntentTemplateOverviewPanels:
    """Test overview panel generation."""

    def test_get_overview_panels_returns_list(self, template_instance):
        """Test that get_overview_panels returns a list."""
        panels = template_instance.get_overview_panels("test-service")
        assert isinstance(panels, list)

    def test_get_overview_panels_with_variable(self, template_instance):
        """Test get_overview_panels with Grafana variable."""
        panels = template_instance.get_overview_panels("$service")
        assert isinstance(panels, list)

    def test_overview_panels_subset_of_full_specs(self, template_instance):
        """Test that overview panels are subset of full panel specs."""
        overview = template_instance.get_overview_panels("test-service")
        specs = template_instance.get_panel_specs("test-service")

        # Overview should have fewer or equal panels than full specs
        assert len(overview) <= len(specs)


class TestIntentBasedTemplateBase:
    """Test base IntentBasedTemplate methods."""

    def test_build_panel_from_spec(self, template_instance):
        """Test building panel from spec."""
        specs = template_instance.get_panel_specs("test-service")

        if specs:
            spec = specs[0]
            panel = template_instance._build_panel_from_spec(spec, "test-service")
            # Panel can be None if metric resolution fails, which is valid
            if panel is not None:
                assert hasattr(panel, "title") or isinstance(panel, dict)


class TestSpecificTemplates:
    """Test specific functionality for individual templates."""

    def test_consul_template_basic(self):
        """Test Consul template basic usage."""
        template = ConsulIntentTemplate()
        assert template.name == "consul"
        specs = template.get_panel_specs("test-service")
        overview = template.get_overview_panels("test-service")
        assert len(specs) > 0
        assert len(overview) <= len(specs)

    def test_elasticsearch_template_basic(self):
        """Test Elasticsearch template basic usage."""
        template = ElasticsearchIntentTemplate()
        assert template.name == "elasticsearch"
        specs = template.get_panel_specs("test-service")
        overview = template.get_overview_panels("test-service")
        assert len(specs) > 0
        assert len(overview) <= len(specs)

    def test_etcd_template_basic(self):
        """Test etcd template basic usage."""
        template = EtcdIntentTemplate()
        assert template.name == "etcd"
        specs = template.get_panel_specs("test-service")
        overview = template.get_overview_panels("test-service")
        assert len(specs) > 0
        assert len(overview) <= len(specs)

    def test_haproxy_template_basic(self):
        """Test HAProxy template basic usage."""
        template = HaproxyIntentTemplate()
        assert template.name == "haproxy"
        specs = template.get_panel_specs("test-service")
        overview = template.get_overview_panels("test-service")
        assert len(specs) > 0
        assert len(overview) <= len(specs)

    def test_http_template_basic(self):
        """Test HTTP template basic usage."""
        template = HTTPIntentTemplate()
        assert template.name == "http"
        specs = template.get_panel_specs("test-service")
        overview = template.get_overview_panels("test-service")
        assert len(specs) > 0

    def test_kafka_template_basic(self):
        """Test Kafka template basic usage."""
        template = KafkaIntentTemplate()
        assert template.name == "kafka"
        specs = template.get_panel_specs("test-service")
        overview = template.get_overview_panels("test-service")
        assert len(specs) > 0
        assert len(overview) <= len(specs)

    def test_mongodb_template_basic(self):
        """Test MongoDB template basic usage."""
        template = MongoDBIntentTemplate()
        assert template.name == "mongodb"
        specs = template.get_panel_specs("test-service")
        overview = template.get_overview_panels("test-service")
        assert len(specs) > 0
        assert len(overview) <= len(specs)

    def test_mysql_template_basic(self):
        """Test MySQL template basic usage."""
        template = MySQLIntentTemplate()
        assert template.name == "mysql"
        specs = template.get_panel_specs("test-service")
        overview = template.get_overview_panels("test-service")
        assert len(specs) > 0

    def test_nats_template_basic(self):
        """Test NATS template basic usage."""
        template = NatsIntentTemplate()
        assert template.name == "nats"
        specs = template.get_panel_specs("test-service")
        overview = template.get_overview_panels("test-service")
        assert len(specs) > 0
        assert len(overview) <= len(specs)

    def test_nginx_template_basic(self):
        """Test Nginx template basic usage."""
        template = NginxIntentTemplate()
        assert template.name == "nginx"
        specs = template.get_panel_specs("test-service")
        overview = template.get_overview_panels("test-service")
        assert len(specs) > 0
        assert len(overview) <= len(specs)

    def test_postgresql_template_basic(self):
        """Test PostgreSQL template basic usage."""
        template = PostgreSQLIntentTemplate()
        assert template.name == "postgresql"
        specs = template.get_panel_specs("test-service")
        overview = template.get_overview_panels("test-service")
        assert len(specs) > 0

    def test_pulsar_template_basic(self):
        """Test Pulsar template basic usage."""
        template = PulsarIntentTemplate()
        assert template.name == "pulsar"
        specs = template.get_panel_specs("test-service")
        overview = template.get_overview_panels("test-service")
        assert len(specs) > 0
        assert len(overview) <= len(specs)

    def test_rabbitmq_template_basic(self):
        """Test RabbitMQ template basic usage."""
        template = RabbitmqIntentTemplate()
        assert template.name == "rabbitmq"
        specs = template.get_panel_specs("test-service")
        overview = template.get_overview_panels("test-service")
        assert len(specs) > 0
        assert len(overview) <= len(specs)

    def test_redis_template_basic(self):
        """Test Redis template basic usage."""
        template = RedisIntentTemplate()
        assert template.name == "redis"
        specs = template.get_panel_specs("test-service")
        overview = template.get_overview_panels("test-service")
        assert len(specs) > 0

    def test_stream_template_basic(self):
        """Test Stream template basic usage."""
        template = StreamIntentTemplate()
        assert template.name == "stream"
        specs = template.get_panel_specs("test-service")
        overview = template.get_overview_panels("test-service")
        assert len(specs) > 0

    def test_traefik_template_basic(self):
        """Test Traefik template basic usage."""
        template = TraefikIntentTemplate()
        assert template.name == "traefik"
        specs = template.get_panel_specs("test-service")
        overview = template.get_overview_panels("test-service")
        assert len(specs) > 0
        assert len(overview) <= len(specs)

    def test_worker_template_basic(self):
        """Test Worker template basic usage."""
        template = WorkerIntentTemplate()
        assert template.name == "worker"
        specs = template.get_panel_specs("test-service")
        overview = template.get_overview_panels("test-service")
        assert len(specs) > 0
