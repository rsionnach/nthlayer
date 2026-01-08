"""Tests for init command."""

from unittest.mock import MagicMock, patch

from nthlayer.cli.init import (
    _build_resources_yaml,
    _format_template_resources,
    _generate_config_yaml,
    _generate_service_yaml,
    _generate_service_yaml_v2,
    _is_valid_service_name,
    init_command,
)


class TestInitCommand:
    """Tests for init_command function."""

    def test_init_creates_service_file(self, tmp_path, monkeypatch):
        """Should create service YAML file."""
        monkeypatch.chdir(tmp_path)

        result = init_command(
            service_name="my-api", team="my-team", template="critical-api", interactive=False
        )

        assert result == 0
        assert (tmp_path / "my-api.yaml").exists()

        # Check file content
        content = (tmp_path / "my-api.yaml").read_text()
        assert "name: my-api" in content
        assert "team: my-team" in content
        assert "template: critical-api" in content

    def test_init_creates_config_directory(self, tmp_path, monkeypatch):
        """Should create .nthlayer directory and config."""
        monkeypatch.chdir(tmp_path)

        result = init_command("my-api", "my-team", "critical-api", interactive=False)

        assert result == 0
        assert (tmp_path / ".nthlayer").exists()
        assert (tmp_path / ".nthlayer" / "config.yaml").exists()

        # Check config content
        config = (tmp_path / ".nthlayer" / "config.yaml").read_text()
        assert "error_budgets" in config
        assert "inherited_attribution" in config

    def test_init_does_not_overwrite_config(self, tmp_path, monkeypatch):
        """Should not overwrite existing config file."""
        monkeypatch.chdir(tmp_path)

        # Create existing config
        (tmp_path / ".nthlayer").mkdir()
        (tmp_path / ".nthlayer" / "config.yaml").write_text("existing: config")

        result = init_command("my-api", "my-team", "critical-api", interactive=False)

        assert result == 0
        # Should not overwrite
        config = (tmp_path / ".nthlayer" / "config.yaml").read_text()
        assert config == "existing: config"

    def test_init_rejects_existing_file(self, tmp_path, monkeypatch):
        """Should error if service file already exists."""
        monkeypatch.chdir(tmp_path)
        (tmp_path / "my-api.yaml").write_text("existing")

        result = init_command("my-api", "my-team", "critical-api", interactive=False)

        assert result == 1  # Error

    def test_init_requires_service_name(self, tmp_path, monkeypatch):
        """Should error if service name not provided in non-interactive mode."""
        monkeypatch.chdir(tmp_path)

        result = init_command(
            service_name=None, team="my-team", template="critical-api", interactive=False
        )

        assert result == 1

    def test_init_requires_team(self, tmp_path, monkeypatch):
        """Should error if team not provided in non-interactive mode."""
        monkeypatch.chdir(tmp_path)

        result = init_command(
            service_name="my-api", team=None, template="critical-api", interactive=False
        )

        assert result == 1

    def test_init_works_without_template(self, tmp_path, monkeypatch):
        """Should work without template in non-interactive mode (uses defaults)."""
        monkeypatch.chdir(tmp_path)

        result = init_command(
            service_name="my-api", team="my-team", template=None, interactive=False
        )

        # Should succeed with default tier=standard, type=api
        assert result == 0
        assert (tmp_path / "my-api.yaml").exists()

        content = (tmp_path / "my-api.yaml").read_text()
        assert "name: my-api" in content
        assert "tier: standard" in content
        assert "type: api" in content

    def test_init_rejects_unknown_template(self, tmp_path, monkeypatch):
        """Should error on unknown template."""
        monkeypatch.chdir(tmp_path)

        result = init_command(
            service_name="my-api",
            team="my-team",
            template="nonexistent-template",
            interactive=False,
        )

        assert result == 1

    def test_init_with_different_templates(self, tmp_path, monkeypatch):
        """Should work with different template types."""
        monkeypatch.chdir(tmp_path)

        templates = ["critical-api", "standard-api", "low-api", "background-job", "pipeline"]

        for template in templates:
            service_name = f"test-{template}"
            result = init_command(service_name, "team", template, interactive=False)

            assert result == 0
            assert (tmp_path / f"{service_name}.yaml").exists()

            content = (tmp_path / f"{service_name}.yaml").read_text()
            assert f"template: {template}" in content


class TestServiceNameValidation:
    """Tests for service name validation."""

    def test_valid_service_names(self):
        """Should accept valid service names."""
        valid_names = [
            "my-api",
            "payment-api",
            "user-service",
            "api-v2",
            "service123",
            "my-api-v1",
        ]

        for name in valid_names:
            assert _is_valid_service_name(name), f"{name} should be valid"

    def test_invalid_service_names(self):
        """Should reject invalid service names."""
        invalid_names = [
            "MyApi",  # uppercase
            "my_api",  # underscore
            "my api",  # space
            "-my-api",  # starts with hyphen
            "my-api-",  # ends with hyphen
            "my--api",  # double hyphen is ok actually
            "",  # empty
            "my.api",  # period
        ]

        for name in invalid_names:
            if name == "my--api":
                # Double hyphen is actually valid
                assert _is_valid_service_name(name)
            else:
                assert not _is_valid_service_name(name), f"{name} should be invalid"

    def test_init_rejects_invalid_name(self, tmp_path, monkeypatch):
        """Should error on invalid service name."""
        monkeypatch.chdir(tmp_path)

        result = init_command(
            service_name="MyInvalidApi",  # uppercase
            team="my-team",
            template="critical-api",
            interactive=False,
        )

        assert result == 1


class TestGeneratedServiceFile:
    """Tests for generated service file content."""

    def test_generated_file_is_valid_yaml(self, tmp_path, monkeypatch):
        """Generated file should be valid YAML."""
        monkeypatch.chdir(tmp_path)

        init_command("my-api", "my-team", "critical-api", interactive=False)

        # Should be parseable
        import yaml

        with open(tmp_path / "my-api.yaml") as f:
            data = yaml.safe_load(f)

        assert data["service"]["name"] == "my-api"
        assert data["service"]["team"] == "my-team"
        assert data["service"]["template"] == "critical-api"

    def test_generated_file_validates(self, tmp_path, monkeypatch):
        """Generated file should pass validation."""
        monkeypatch.chdir(tmp_path)

        init_command("my-api", "my-team", "critical-api", interactive=False)

        # Should be parseable by our parser
        from nthlayer.specs.parser import parse_service_file

        context, resources = parse_service_file(tmp_path / "my-api.yaml")

        assert context.name == "my-api"
        assert context.team == "my-team"
        assert context.template == "critical-api"
        assert len(resources) == 3  # From template

    def test_generated_file_includes_comments(self, tmp_path, monkeypatch):
        """Generated file should include helpful comments."""
        monkeypatch.chdir(tmp_path)

        init_command("my-api", "my-team", "critical-api", interactive=False)

        content = (tmp_path / "my-api.yaml").read_text()

        # Should have header comments
        assert "# my-api Service Definition" in content
        assert "# Generated by NthLayer" in content


class TestInitCommandInteractive:
    """Tests for interactive mode of init_command."""

    @patch("nthlayer.cli.init.text_input")
    @patch("nthlayer.cli.init.select")
    @patch("nthlayer.cli.init.multi_select")
    def test_interactive_prompts_for_service_name(
        self, mock_multi_select, mock_select, mock_text_input, tmp_path, monkeypatch
    ):
        """Test interactive mode prompts for service name."""
        monkeypatch.chdir(tmp_path)
        mock_text_input.side_effect = ["my-api", "my-team"]
        mock_select.side_effect = [
            "standard - Standard tier",
            "api - REST/GraphQL API service",
            "none - Generate from selections above",
        ]
        mock_multi_select.return_value = []

        result = init_command(service_name=None, team=None, interactive=True)

        assert result == 0
        assert (tmp_path / "my-api.yaml").exists()

    @patch("nthlayer.cli.init.text_input")
    @patch("nthlayer.cli.init.select")
    @patch("nthlayer.cli.init.multi_select")
    def test_interactive_tier_selection(
        self, mock_multi_select, mock_select, mock_text_input, tmp_path, monkeypatch
    ):
        """Test interactive tier selection."""
        monkeypatch.chdir(tmp_path)
        mock_text_input.return_value = "my-team"
        mock_select.side_effect = [
            "critical - Critical tier",
            "api - REST/GraphQL API service",
            "none - Generate from selections above",
        ]
        mock_multi_select.return_value = []

        result = init_command(service_name="my-api", team=None, interactive=True)

        assert result == 0
        content = (tmp_path / "my-api.yaml").read_text()
        assert "tier: critical" in content

    @patch("nthlayer.cli.init.text_input")
    @patch("nthlayer.cli.init.select")
    @patch("nthlayer.cli.init.multi_select")
    def test_interactive_service_type_selection(
        self, mock_multi_select, mock_select, mock_text_input, tmp_path, monkeypatch
    ):
        """Test interactive service type selection."""
        monkeypatch.chdir(tmp_path)
        mock_text_input.return_value = "my-team"
        mock_select.side_effect = [
            "standard - Standard tier",
            "worker - Background job processor",
            "none - Generate from selections above",
        ]
        mock_multi_select.return_value = []

        result = init_command(service_name="my-api", team=None, interactive=True)

        assert result == 0
        content = (tmp_path / "my-api.yaml").read_text()
        assert "type: worker" in content

    @patch("nthlayer.cli.init.text_input")
    @patch("nthlayer.cli.init.select")
    @patch("nthlayer.cli.init.multi_select")
    def test_interactive_dependencies_selection(
        self, mock_multi_select, mock_select, mock_text_input, tmp_path, monkeypatch
    ):
        """Test interactive dependencies selection."""
        monkeypatch.chdir(tmp_path)
        mock_text_input.return_value = "my-team"
        mock_select.side_effect = [
            "standard - Standard tier",
            "api - REST/GraphQL API service",
            "none - Generate from selections above",
        ]
        mock_multi_select.return_value = ["postgresql", "redis"]

        result = init_command(service_name="my-api", team=None, interactive=True)

        assert result == 0
        content = (tmp_path / "my-api.yaml").read_text()
        assert "Dependencies" in content
        assert "postgresql" in content
        assert "redis" in content

    @patch("nthlayer.cli.init.text_input")
    @patch("nthlayer.cli.init.select")
    @patch("nthlayer.cli.init.multi_select")
    def test_interactive_template_selection(
        self, mock_multi_select, mock_select, mock_text_input, tmp_path, monkeypatch
    ):
        """Test interactive template selection."""
        monkeypatch.chdir(tmp_path)
        mock_text_input.return_value = "my-team"
        mock_select.side_effect = [
            "standard - Standard tier",
            "api - REST/GraphQL API service",
            "critical-api - Critical API template",
        ]
        mock_multi_select.return_value = []

        result = init_command(service_name="my-api", team=None, interactive=True)

        assert result == 0
        content = (tmp_path / "my-api.yaml").read_text()
        assert "template: critical-api" in content


class TestInitCommandErrorHandling:
    """Tests for error handling in init_command."""

    @patch("nthlayer.cli.init.CustomTemplateLoader.load_all_templates")
    def test_handles_template_loading_error(self, mock_load, tmp_path, monkeypatch):
        """Test handling of template loading errors."""
        monkeypatch.chdir(tmp_path)
        mock_load.side_effect = Exception("Template loading failed")

        result = init_command("my-api", "my-team", interactive=False)

        assert result == 1

    def test_handles_file_write_error(self, tmp_path, monkeypatch):
        """Test handling of file write errors."""
        monkeypatch.chdir(tmp_path)
        # Make directory read-only
        (tmp_path / "my-api.yaml").write_text("")  # Create file first

        with patch("pathlib.Path.write_text", side_effect=OSError("Permission denied")):
            result = init_command("new-api", "my-team", interactive=False)

        # Should handle the error
        assert result == 1

    def test_handles_directory_creation_error(self, tmp_path, monkeypatch):
        """Test handling of .nthlayer directory creation errors."""
        monkeypatch.chdir(tmp_path)

        with patch("pathlib.Path.mkdir", side_effect=OSError("Permission denied")):
            # Should still succeed (just warn about directory)
            result = init_command("my-api", "my-team", interactive=False)

        # May or may not fail depending on which mkdir fails
        # But the file should exist if the first part succeeded
        assert (tmp_path / "my-api.yaml").exists() or result == 1


class TestBuildResourcesYaml:
    """Tests for _build_resources_yaml function."""

    def test_builds_slo_for_critical_tier(self):
        """Test SLO generation for critical tier."""
        result = _build_resources_yaml("my-api", "critical", "api", [])

        assert "kind: SLO" in result
        assert "availability" in result
        assert "objective: 99.95" in result  # Critical tier default

    def test_builds_slo_for_standard_tier(self):
        """Test SLO generation for standard tier."""
        result = _build_resources_yaml("my-api", "standard", "api", [])

        assert "kind: SLO" in result
        assert "objective: 99.9" in result

    def test_builds_slo_for_low_tier(self):
        """Test SLO generation for low tier."""
        result = _build_resources_yaml("my-api", "low", "api", [])

        assert "kind: SLO" in result
        # Low tier uses standard defaults (99.9 availability, 99.0 latency)
        assert "availability" in result
        assert "objective: 99.9" in result

    def test_includes_pagerduty_for_critical(self):
        """Test PagerDuty included for critical tier."""
        result = _build_resources_yaml("my-api", "critical", "api", [])

        assert "kind: PagerDuty" in result
        assert "urgency: high" in result

    def test_no_pagerduty_for_low_tier(self):
        """Test PagerDuty not included for low tier."""
        result = _build_resources_yaml("my-api", "low", "api", [])

        assert "kind: PagerDuty" not in result

    def test_builds_database_dependencies(self):
        """Test database dependency generation."""
        result = _build_resources_yaml("my-api", "standard", "api", ["postgresql", "mysql"])

        assert "kind: Dependencies" in result
        assert "databases:" in result
        assert "my-api-postgresql" in result
        assert "my-api-mysql" in result

    def test_builds_cache_dependencies(self):
        """Test cache dependency generation."""
        result = _build_resources_yaml("my-api", "standard", "api", ["redis", "elasticsearch"])

        assert "caches:" in result
        assert "my-api-redis" in result
        assert "my-api-elasticsearch" in result

    def test_builds_queue_dependencies(self):
        """Test queue dependency generation."""
        result = _build_resources_yaml("my-api", "standard", "api", ["kafka", "rabbitmq"])

        assert "queues:" in result
        assert "my-api-kafka" in result
        assert "my-api-rabbitmq" in result

    def test_builds_mixed_dependencies(self):
        """Test mixed dependency types."""
        deps = ["postgresql", "redis", "kafka"]
        result = _build_resources_yaml("my-api", "standard", "api", deps)

        assert "databases:" in result
        assert "caches:" in result
        assert "queues:" in result


class TestGenerateServiceYaml:
    """Tests for legacy _generate_service_yaml function."""

    def test_generates_yaml_with_template(self):
        """Test YAML generation with template."""
        mock_template = MagicMock()
        mock_template.name = "critical-api"
        mock_template.tier = "critical"
        mock_template.type = "api"
        mock_template.resources = []

        result = _generate_service_yaml("my-api", "my-team", mock_template)

        assert "name: my-api" in result
        assert "team: my-team" in result
        assert "tier: critical" in result
        assert "template: critical-api" in result

    def test_includes_template_resources_as_comments(self):
        """Test template resources shown in comments."""
        mock_resource = MagicMock()
        mock_resource.kind = "SLO"
        mock_resource.name = "availability"

        mock_template = MagicMock()
        mock_template.name = "critical-api"
        mock_template.tier = "critical"
        mock_template.type = "api"
        mock_template.resources = [mock_resource]

        result = _generate_service_yaml("my-api", "my-team", mock_template)

        assert "# Template provides:" in result


class TestFormatTemplateResources:
    """Tests for _format_template_resources function."""

    def test_formats_resources(self):
        """Test resource formatting."""
        mock_resource1 = MagicMock()
        mock_resource1.kind = "SLO"
        mock_resource1.name = "availability"

        mock_resource2 = MagicMock()
        mock_resource2.kind = "Alert"
        mock_resource2.name = "high-latency"

        mock_template = MagicMock()
        mock_template.resources = [mock_resource1, mock_resource2]

        result = _format_template_resources(mock_template)

        assert "#   - SLO: availability" in result
        assert "#   - Alert: high-latency" in result

    def test_handles_empty_resources(self):
        """Test formatting with no resources."""
        mock_template = MagicMock()
        mock_template.resources = []

        result = _format_template_resources(mock_template)

        assert "(no resources)" in result


class TestGenerateServiceYamlV2:
    """Tests for _generate_service_yaml_v2 function."""

    def test_generates_yaml_without_template(self):
        """Test YAML generation without template."""
        result = _generate_service_yaml_v2("my-api", "my-team", "standard", "api", [], None)

        assert "name: my-api" in result
        assert "team: my-team" in result
        assert "tier: standard" in result
        assert "type: api" in result
        assert "template:" not in result

    def test_generates_yaml_with_template(self):
        """Test YAML generation with template."""
        mock_template = MagicMock()
        mock_template.name = "critical-api"

        result = _generate_service_yaml_v2(
            "my-api", "my-team", "critical", "api", [], mock_template
        )

        assert "template: critical-api" in result


class TestGenerateConfigYaml:
    """Tests for _generate_config_yaml function."""

    def test_generates_valid_config(self):
        """Test config generation."""
        result = _generate_config_yaml()

        assert "NthLayer Configuration" in result
        assert "error_budgets:" in result
        assert "inherited_attribution" in result
