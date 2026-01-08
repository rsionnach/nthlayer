"""Tests for user_config.py.

Tests for NthLayer configuration management.
"""

import tempfile
from pathlib import Path
from unittest.mock import patch

import yaml
from nthlayer.user_config import (
    ErrorBudgetConfig,
    NthLayerConfig,
    get_config,
)


class TestErrorBudgetConfig:
    """Tests for ErrorBudgetConfig dataclass."""

    def test_default_values(self):
        """Test default configuration values."""
        config = ErrorBudgetConfig()

        assert config.inherited_attribution is False
        assert config.min_correlation_confidence == 0.8
        assert config.time_window_minutes == 5

    def test_custom_values(self):
        """Test custom configuration values."""
        config = ErrorBudgetConfig(
            inherited_attribution=True,
            min_correlation_confidence=0.9,
            time_window_minutes=10,
        )

        assert config.inherited_attribution is True
        assert config.min_correlation_confidence == 0.9
        assert config.time_window_minutes == 10


class TestNthLayerConfig:
    """Tests for NthLayerConfig dataclass."""

    def test_load_defaults(self):
        """Test loading default configuration when no file exists."""
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.object(Path, "cwd", return_value=Path(tmpdir)):
                with patch.object(Path, "home", return_value=Path(tmpdir)):
                    config = NthLayerConfig.load()

        assert config.error_budget.inherited_attribution is False
        assert config.error_budget.min_correlation_confidence == 0.8

    def test_load_from_explicit_path(self):
        """Test loading from explicit config file path."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config_file = Path(tmpdir) / "config.yaml"
            config_file.write_text(
                yaml.dump(
                    {
                        "error_budget": {
                            "inherited_attribution": True,
                            "min_correlation_confidence": 0.95,
                            "time_window_minutes": 15,
                        }
                    }
                )
            )

            config = NthLayerConfig.load(config_file)

            assert config.error_budget.inherited_attribution is True
            assert config.error_budget.min_correlation_confidence == 0.95
            assert config.error_budget.time_window_minutes == 15

    def test_load_from_cwd_config(self):
        """Test loading from .nthlayer/config.yaml in cwd."""
        with tempfile.TemporaryDirectory() as tmpdir:
            cwd_path = Path(tmpdir)
            config_dir = cwd_path / ".nthlayer"
            config_dir.mkdir()
            config_file = config_dir / "config.yaml"
            config_file.write_text(
                yaml.dump(
                    {
                        "error_budget": {
                            "inherited_attribution": True,
                        }
                    }
                )
            )

            with patch.object(Path, "cwd", return_value=cwd_path):
                with patch.object(Path, "home", return_value=Path("/nonexistent")):
                    config = NthLayerConfig.load()

            assert config.error_budget.inherited_attribution is True

    def test_load_from_home_config(self):
        """Test loading from ~/.nthlayer/config.yaml."""
        with tempfile.TemporaryDirectory() as tmpdir:
            home_path = Path(tmpdir)
            config_dir = home_path / ".nthlayer"
            config_dir.mkdir()
            config_file = config_dir / "config.yaml"
            config_file.write_text(
                yaml.dump(
                    {
                        "error_budget": {
                            "time_window_minutes": 20,
                        }
                    }
                )
            )

            with patch.object(Path, "cwd", return_value=Path("/nonexistent")):
                with patch.object(Path, "home", return_value=home_path):
                    config = NthLayerConfig.load()

            assert config.error_budget.time_window_minutes == 20

    def test_load_explicit_path_not_exists_uses_default(self):
        """Test loading non-existent explicit path uses defaults."""
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.object(Path, "cwd", return_value=Path(tmpdir)):
                with patch.object(Path, "home", return_value=Path(tmpdir)):
                    config = NthLayerConfig.load("/nonexistent/config.yaml")

        assert config.error_budget.inherited_attribution is False

    def test_load_empty_file(self):
        """Test loading empty config file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config_file = Path(tmpdir) / "config.yaml"
            config_file.write_text("")

            config = NthLayerConfig.load(config_file)

            # Should use defaults for missing values
            assert config.error_budget.inherited_attribution is False

    def test_load_partial_config(self):
        """Test loading config with only some values."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config_file = Path(tmpdir) / "config.yaml"
            config_file.write_text(
                yaml.dump(
                    {
                        "error_budget": {
                            "inherited_attribution": True,
                            # Other values missing
                        }
                    }
                )
            )

            config = NthLayerConfig.load(config_file)

            assert config.error_budget.inherited_attribution is True
            # Defaults for missing
            assert config.error_budget.min_correlation_confidence == 0.8
            assert config.error_budget.time_window_minutes == 5

    def test_save_config(self):
        """Test saving configuration to file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config_file = Path(tmpdir) / "config.yaml"

            config = NthLayerConfig(
                error_budget=ErrorBudgetConfig(
                    inherited_attribution=True,
                    min_correlation_confidence=0.9,
                    time_window_minutes=10,
                )
            )
            config.save(config_file)

            assert config_file.exists()
            saved_data = yaml.safe_load(config_file.read_text())
            assert saved_data["error_budget"]["inherited_attribution"] is True
            assert saved_data["error_budget"]["min_correlation_confidence"] == 0.9
            assert saved_data["error_budget"]["time_window_minutes"] == 10

    def test_save_creates_parent_directories(self):
        """Test save creates parent directories if needed."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config_file = Path(tmpdir) / "nested" / "dir" / "config.yaml"

            config = NthLayerConfig(error_budget=ErrorBudgetConfig())
            config.save(config_file)

            assert config_file.exists()

    def test_save_load_roundtrip(self):
        """Test save and load roundtrip."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config_file = Path(tmpdir) / "config.yaml"

            original = NthLayerConfig(
                error_budget=ErrorBudgetConfig(
                    inherited_attribution=True,
                    min_correlation_confidence=0.85,
                    time_window_minutes=7,
                )
            )
            original.save(config_file)
            loaded = NthLayerConfig.load(config_file)

            assert (
                loaded.error_budget.inherited_attribution
                == original.error_budget.inherited_attribution
            )
            assert (
                loaded.error_budget.min_correlation_confidence
                == original.error_budget.min_correlation_confidence
            )
            assert (
                loaded.error_budget.time_window_minutes == original.error_budget.time_window_minutes
            )


class TestGetConfig:
    """Tests for get_config function."""

    def test_returns_config(self):
        """Test get_config returns NthLayerConfig."""
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.object(Path, "cwd", return_value=Path(tmpdir)):
                with patch.object(Path, "home", return_value=Path(tmpdir)):
                    config = get_config()

        assert isinstance(config, NthLayerConfig)
