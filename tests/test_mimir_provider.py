"""
Tests for Mimir Ruler API provider.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from nthlayer.providers.mimir import (
    MimirRulerError,
    MimirRulerProvider,
    RulerPushResult,
)


class TestMimirRulerProvider:
    """Test Mimir Ruler API provider."""

    def test_init_basic(self):
        """Test basic initialization."""
        provider = MimirRulerProvider("https://mimir:8080")
        assert provider._base_url == "https://mimir:8080"
        assert provider._tenant_id is None
        assert provider._api_key is None

    def test_init_with_tenant(self):
        """Test initialization with tenant ID."""
        provider = MimirRulerProvider(
            "https://mimir:8080",
            tenant_id="my-tenant",
            api_key="secret-key",
        )
        assert provider._tenant_id == "my-tenant"
        assert provider._api_key == "secret-key"

    def test_init_strips_trailing_slash(self):
        """Test that trailing slash is stripped from URL."""
        provider = MimirRulerProvider("https://mimir:8080/")
        assert provider._base_url == "https://mimir:8080"

    def test_build_headers_basic(self):
        """Test header building without auth."""
        provider = MimirRulerProvider("https://mimir:8080")
        headers = provider._build_headers()

        assert "User-Agent" in headers
        assert "X-Scope-OrgID" not in headers
        assert "Authorization" not in headers

    def test_build_headers_with_tenant(self):
        """Test header building with tenant ID."""
        provider = MimirRulerProvider(
            "https://mimir:8080",
            tenant_id="my-tenant",
        )
        headers = provider._build_headers()

        assert headers["X-Scope-OrgID"] == "my-tenant"

    def test_build_headers_with_api_key(self):
        """Test header building with API key."""
        provider = MimirRulerProvider(
            "https://mimir:8080",
            api_key="secret-key",
        )
        headers = provider._build_headers()

        assert headers["Authorization"] == "Bearer secret-key"


class TestPushRules:
    """Test pushing rules to Mimir."""

    @pytest.mark.asyncio
    async def test_push_rules_success(self):
        """Test successful rule push."""
        provider = MimirRulerProvider("https://mimir:8080")

        mock_response = MagicMock()
        mock_response.status_code = 202
        mock_response.text = ""

        with patch("httpx.AsyncClient") as mock_client:
            mock_client.return_value.__aenter__ = AsyncMock(
                return_value=MagicMock(post=AsyncMock(return_value=mock_response))
            )
            mock_client.return_value.__aexit__ = AsyncMock(return_value=None)

            rules_yaml = """
groups:
  - name: test-service
    rules:
      - alert: HighErrorRate
        expr: rate(http_errors[5m]) > 0.1
"""
            result = await provider.push_rules("test-service", rules_yaml)

        assert result.success
        assert result.namespace == "test-service"
        assert result.status_code == 202
        assert result.groups_pushed == 1

    @pytest.mark.asyncio
    async def test_push_rules_failure(self):
        """Test failed rule push."""
        provider = MimirRulerProvider("https://mimir:8080")

        mock_response = MagicMock()
        mock_response.status_code = 400
        mock_response.text = "Invalid YAML"

        with patch("httpx.AsyncClient") as mock_client:
            mock_client.return_value.__aenter__ = AsyncMock(
                return_value=MagicMock(post=AsyncMock(return_value=mock_response))
            )
            mock_client.return_value.__aexit__ = AsyncMock(return_value=None)

            result = await provider.push_rules("test-service", "invalid yaml")

        assert not result.success
        assert result.status_code == 400
        assert "Invalid YAML" in result.message

    @pytest.mark.asyncio
    async def test_push_rules_connection_error(self):
        """Test connection error handling."""
        import httpx

        provider = MimirRulerProvider("https://mimir:8080")

        with patch("httpx.AsyncClient") as mock_client:
            mock_client.return_value.__aenter__ = AsyncMock(
                return_value=MagicMock(
                    post=AsyncMock(side_effect=httpx.ConnectError("Connection refused"))
                )
            )
            mock_client.return_value.__aexit__ = AsyncMock(return_value=None)

            with pytest.raises(MimirRulerError) as exc_info:
                await provider.push_rules("test-service", "rules: []")

        assert "Failed to connect" in str(exc_info.value)


class TestRulerPushResult:
    """Test RulerPushResult dataclass."""

    def test_success_result(self):
        """Test successful result."""
        result = RulerPushResult(
            success=True,
            namespace="payment-api",
            status_code=202,
            message="Rules pushed successfully",
            groups_pushed=3,
        )

        assert result.success
        assert result.namespace == "payment-api"
        assert result.groups_pushed == 3

    def test_failure_result(self):
        """Test failure result."""
        result = RulerPushResult(
            success=False,
            namespace="payment-api",
            status_code=500,
            message="Internal server error",
        )

        assert not result.success
        assert result.groups_pushed == 0


class TestDeleteRules:
    """Test deleting rules from Mimir."""

    @pytest.mark.asyncio
    async def test_delete_namespace(self):
        """Test deleting all rules in a namespace."""
        provider = MimirRulerProvider("https://mimir:8080")

        mock_response = MagicMock()
        mock_response.status_code = 202

        with patch("httpx.AsyncClient") as mock_client:
            mock_client.return_value.__aenter__ = AsyncMock(
                return_value=MagicMock(delete=AsyncMock(return_value=mock_response))
            )
            mock_client.return_value.__aexit__ = AsyncMock(return_value=None)

            result = await provider.delete_rules("test-service")

        assert result is True

    @pytest.mark.asyncio
    async def test_delete_specific_group(self):
        """Test deleting a specific rule group."""
        provider = MimirRulerProvider("https://mimir:8080")

        mock_response = MagicMock()
        mock_response.status_code = 204

        with patch("httpx.AsyncClient") as mock_client:
            mock_instance = MagicMock()
            mock_instance.delete = AsyncMock(return_value=mock_response)
            mock_client.return_value.__aenter__ = AsyncMock(return_value=mock_instance)
            mock_client.return_value.__aexit__ = AsyncMock(return_value=None)

            result = await provider.delete_rules("test-service", "alerts-group")

        assert result is True
        # Verify the URL included the group name
        mock_instance.delete.assert_called_once()
        call_args = mock_instance.delete.call_args
        assert "test-service/alerts-group" in call_args[0][0]


class TestListRules:
    """Test listing rules from Mimir."""

    @pytest.mark.asyncio
    async def test_list_rules_success(self):
        """Test successful rule listing."""
        provider = MimirRulerProvider("https://mimir:8080")

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "payment-api": [{"name": "alerts", "rules": []}],
            "checkout-api": [{"name": "alerts", "rules": []}],
        }

        with patch("httpx.AsyncClient") as mock_client:
            mock_client.return_value.__aenter__ = AsyncMock(
                return_value=MagicMock(get=AsyncMock(return_value=mock_response))
            )
            mock_client.return_value.__aexit__ = AsyncMock(return_value=None)

            result = await provider.list_rules()

        assert "payment-api" in result
        assert "checkout-api" in result

    @pytest.mark.asyncio
    async def test_list_rules_error(self):
        """Test error handling in list rules."""
        provider = MimirRulerProvider("https://mimir:8080")

        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.text = "Internal error"

        with patch("httpx.AsyncClient") as mock_client:
            mock_client.return_value.__aenter__ = AsyncMock(
                return_value=MagicMock(get=AsyncMock(return_value=mock_response))
            )
            mock_client.return_value.__aexit__ = AsyncMock(return_value=None)

            with pytest.raises(MimirRulerError):
                await provider.list_rules()


class TestHealthCheck:
    """Test health check."""

    @pytest.mark.asyncio
    async def test_health_check_healthy(self):
        """Test health check when Mimir is healthy."""
        provider = MimirRulerProvider("https://mimir:8080")

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {}

        with patch("httpx.AsyncClient") as mock_client:
            mock_client.return_value.__aenter__ = AsyncMock(
                return_value=MagicMock(get=AsyncMock(return_value=mock_response))
            )
            mock_client.return_value.__aexit__ = AsyncMock(return_value=None)

            result = await provider.health_check()

        assert result is True

    @pytest.mark.asyncio
    async def test_health_check_unhealthy(self):
        """Test health check when Mimir is unreachable."""
        import httpx

        provider = MimirRulerProvider("https://mimir:8080")

        with patch("httpx.AsyncClient") as mock_client:
            mock_client.return_value.__aenter__ = AsyncMock(
                return_value=MagicMock(
                    get=AsyncMock(side_effect=httpx.ConnectError("Connection refused"))
                )
            )
            mock_client.return_value.__aexit__ = AsyncMock(return_value=None)

            result = await provider.health_check()

        assert result is False
