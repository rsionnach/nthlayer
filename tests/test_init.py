"""Tests for init command."""

from nthlayer.cli.init import _is_valid_service_name, init_command


class TestInitCommand:
    """Tests for init_command function."""
    
    def test_init_creates_service_file(self, tmp_path, monkeypatch):
        """Should create service YAML file."""
        monkeypatch.chdir(tmp_path)
        
        result = init_command(
            service_name="my-api",
            team="my-team",
            template="critical-api",
            interactive=False
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
            service_name=None,
            team="my-team",
            template="critical-api",
            interactive=False
        )
        
        assert result == 1
    
    def test_init_requires_team(self, tmp_path, monkeypatch):
        """Should error if team not provided in non-interactive mode."""
        monkeypatch.chdir(tmp_path)
        
        result = init_command(
            service_name="my-api",
            team=None,
            template="critical-api",
            interactive=False
        )
        
        assert result == 1
    
    def test_init_requires_template(self, tmp_path, monkeypatch):
        """Should error if template not provided in non-interactive mode."""
        monkeypatch.chdir(tmp_path)
        
        result = init_command(
            service_name="my-api",
            team="my-team",
            template=None,
            interactive=False
        )
        
        assert result == 1
    
    def test_init_rejects_unknown_template(self, tmp_path, monkeypatch):
        """Should error on unknown template."""
        monkeypatch.chdir(tmp_path)
        
        result = init_command(
            service_name="my-api",
            team="my-team",
            template="nonexistent-template",
            interactive=False
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
            interactive=False
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
        
        # Should have comments
        assert "# Template provides:" in content
        assert "# Optional:" in content
        assert "# Override" in content  # "Override template defaults or add new resources"
