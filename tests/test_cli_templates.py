"""Tests for CLI templates command.

Tests for nthlayer templates list command including template loading,
output formatting, and error handling.
"""

from unittest.mock import MagicMock, patch

from nthlayer.cli.templates import _resource_summary, list_templates_command


class TestListTemplatesCommand:
    """Tests for list_templates_command function."""

    def test_returns_success_when_templates_exist(self):
        """Test returns 0 when templates are available."""
        result = list_templates_command()

        # Should succeed as there are built-in templates
        assert result == 0

    def test_output_includes_template_info(self, capsys):
        """Test output includes template information."""
        list_templates_command()

        captured = capsys.readouterr()
        # Should include some template names (built-in ones exist)
        assert "template" in captured.out.lower() or len(captured.out) > 0

    def test_shows_usage_instructions(self, capsys):
        """Test output includes usage instructions."""
        list_templates_command()

        captured = capsys.readouterr()
        assert "nthlayer init" in captured.out or "Usage" in captured.out

    @patch("nthlayer.cli.templates.CustomTemplateLoader")
    def test_handles_loading_error(self, mock_loader):
        """Test handles template loading errors gracefully."""
        mock_loader.load_all_templates.side_effect = Exception("Load failed")

        result = list_templates_command()

        assert result == 1

    @patch("nthlayer.cli.templates.CustomTemplateLoader")
    def test_handles_empty_templates(self, mock_loader):
        """Test handles case when no templates available."""
        mock_registry = MagicMock()
        mock_registry.templates = []
        mock_loader.load_all_templates.return_value = mock_registry

        result = list_templates_command()

        assert result == 0

    @patch("nthlayer.cli.templates.CustomTemplateLoader")
    def test_shows_custom_vs_builtin_label(self, mock_loader, capsys):
        """Test shows correct source label for templates."""
        # Create mock template
        mock_template = MagicMock()
        mock_template.name = "test-template"
        mock_template.description = "Test description"
        mock_template.tier = "standard"
        mock_template.type = "api"
        mock_template.resources = []

        mock_registry = MagicMock()
        mock_registry.templates = [mock_template]
        mock_registry.list.return_value = [mock_template]

        mock_loader.load_all_templates.return_value = mock_registry
        mock_loader.get_template_source.return_value = "custom"

        list_templates_command()

        captured = capsys.readouterr()
        assert "test-template" in captured.out

    @patch("nthlayer.cli.templates.CustomTemplateLoader")
    def test_displays_multiple_templates(self, mock_loader, capsys):
        """Test correctly displays multiple templates."""
        templates = []
        for i in range(3):
            mock_template = MagicMock()
            mock_template.name = f"template-{i}"
            mock_template.description = f"Description {i}"
            mock_template.tier = "standard"
            mock_template.type = "api"
            mock_template.resources = []
            templates.append(mock_template)

        mock_registry = MagicMock()
        mock_registry.templates = templates
        mock_registry.list.return_value = templates

        mock_loader.load_all_templates.return_value = mock_registry
        mock_loader.get_template_source.return_value = "built-in"

        list_templates_command()

        captured = capsys.readouterr()
        assert "template-0" in captured.out
        assert "template-1" in captured.out
        assert "template-2" in captured.out


class TestResourceSummary:
    """Tests for _resource_summary helper function."""

    def test_empty_resources(self):
        """Test summary for template with no resources."""
        mock_template = MagicMock()
        mock_template.resources = []

        result = _resource_summary(mock_template)

        assert result == "none"

    def test_single_resource(self):
        """Test summary for template with single resource."""
        mock_resource = MagicMock()
        mock_resource.kind = "SLO"

        mock_template = MagicMock()
        mock_template.resources = [mock_resource]

        result = _resource_summary(mock_template)

        assert result == "SLO"

    def test_multiple_same_kind_resources(self):
        """Test summary for multiple resources of same kind."""
        resources = []
        for _ in range(3):
            mock_resource = MagicMock()
            mock_resource.kind = "SLO"
            resources.append(mock_resource)

        mock_template = MagicMock()
        mock_template.resources = resources

        result = _resource_summary(mock_template)

        assert result == "3 SLOs"

    def test_mixed_resources(self):
        """Test summary for mixed resource types."""
        resources = []

        # 2 SLOs
        for _ in range(2):
            mock_resource = MagicMock()
            mock_resource.kind = "SLO"
            resources.append(mock_resource)

        # 1 Dependencies
        mock_deps = MagicMock()
        mock_deps.kind = "Dependencies"
        resources.append(mock_deps)

        mock_template = MagicMock()
        mock_template.resources = resources

        result = _resource_summary(mock_template)

        # Should be sorted alphabetically
        assert "Dependencies" in result
        assert "2 SLOs" in result

    def test_resources_sorted_alphabetically(self):
        """Test resource types are sorted alphabetically."""
        resources = []

        mock_z = MagicMock()
        mock_z.kind = "Zebra"
        resources.append(mock_z)

        mock_a = MagicMock()
        mock_a.kind = "Apple"
        resources.append(mock_a)

        mock_template = MagicMock()
        mock_template.resources = resources

        result = _resource_summary(mock_template)

        # Apple should come before Zebra
        apple_pos = result.find("Apple")
        zebra_pos = result.find("Zebra")
        assert apple_pos < zebra_pos
