"""Tests for providers/lock.py.

Tests for provider lock file operations.
"""

import json
import tempfile
from pathlib import Path

from nthlayer.providers.lock import (
    ProviderLock,
    load_lock,
    save_lock,
)


class TestProviderLock:
    """Tests for ProviderLock dataclass."""

    def test_default_providers_empty(self):
        """Test default providers is empty dict."""
        lock = ProviderLock()
        assert lock.providers == {}

    def test_set_provider(self):
        """Test setting a provider version."""
        lock = ProviderLock()
        lock.set("prometheus", "2.45.0")

        assert lock.providers["prometheus"] == "2.45.0"

    def test_get_provider_exists(self):
        """Test getting an existing provider version."""
        lock = ProviderLock(providers={"grafana": "10.0.0"})

        assert lock.get("grafana") == "10.0.0"

    def test_get_provider_not_exists(self):
        """Test getting a non-existent provider."""
        lock = ProviderLock()

        assert lock.get("unknown") is None

    def test_multiple_providers(self):
        """Test managing multiple providers."""
        lock = ProviderLock()
        lock.set("prometheus", "2.45.0")
        lock.set("grafana", "10.0.0")
        lock.set("mimir", "2.10.0")

        assert len(lock.providers) == 3
        assert lock.get("prometheus") == "2.45.0"
        assert lock.get("grafana") == "10.0.0"
        assert lock.get("mimir") == "2.10.0"

    def test_update_provider_version(self):
        """Test updating a provider version."""
        lock = ProviderLock(providers={"prometheus": "2.44.0"})
        lock.set("prometheus", "2.45.0")

        assert lock.get("prometheus") == "2.45.0"


class TestLoadLock:
    """Tests for load_lock function."""

    def test_load_nonexistent_returns_empty(self):
        """Test loading non-existent lock file returns empty lock."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "nonexistent.lock"
            lock = load_lock(path)

            assert lock.providers == {}

    def test_load_existing_lock(self):
        """Test loading existing lock file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "providers.lock"
            path.write_text(
                json.dumps(
                    {
                        "providers": {
                            "prometheus": "2.45.0",
                            "grafana": "10.0.0",
                        }
                    }
                )
            )

            lock = load_lock(path)

            assert lock.get("prometheus") == "2.45.0"
            assert lock.get("grafana") == "10.0.0"

    def test_load_default_path(self):
        """Test loading with default path."""
        # This will return empty since DEFAULT_LOCK_PATH likely doesn't exist
        lock = load_lock()
        assert isinstance(lock, ProviderLock)

    def test_load_empty_providers(self):
        """Test loading lock with empty providers."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "providers.lock"
            path.write_text(json.dumps({"providers": {}}))

            lock = load_lock(path)

            assert lock.providers == {}


class TestSaveLock:
    """Tests for save_lock function."""

    def test_save_lock(self):
        """Test saving lock file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "providers.lock"
            lock = ProviderLock(
                providers={
                    "prometheus": "2.45.0",
                    "grafana": "10.0.0",
                }
            )

            save_lock(lock, path)

            assert path.exists()
            data = json.loads(path.read_text())
            assert data["providers"]["prometheus"] == "2.45.0"
            assert data["providers"]["grafana"] == "10.0.0"

    def test_save_empty_lock(self):
        """Test saving empty lock file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "providers.lock"
            lock = ProviderLock()

            save_lock(lock, path)

            assert path.exists()
            data = json.loads(path.read_text())
            assert data["providers"] == {}

    def test_save_overwrites_existing(self):
        """Test saving overwrites existing lock file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "providers.lock"
            path.write_text(json.dumps({"providers": {"old": "1.0.0"}}))

            lock = ProviderLock(providers={"new": "2.0.0"})
            save_lock(lock, path)

            data = json.loads(path.read_text())
            assert "old" not in data["providers"]
            assert data["providers"]["new"] == "2.0.0"

    def test_save_formatted_json(self):
        """Test saved JSON is formatted with indentation."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "providers.lock"
            lock = ProviderLock(providers={"a": "1", "b": "2"})

            save_lock(lock, path)

            content = path.read_text()
            # Should have newlines (pretty printed)
            assert "\n" in content
            # Should end with newline
            assert content.endswith("\n")

    def test_roundtrip(self):
        """Test save and load roundtrip."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "providers.lock"
            original = ProviderLock(
                providers={
                    "prometheus": "2.45.0",
                    "grafana": "10.0.0",
                    "mimir": "2.10.0",
                }
            )

            save_lock(original, path)
            loaded = load_lock(path)

            assert loaded.providers == original.providers
