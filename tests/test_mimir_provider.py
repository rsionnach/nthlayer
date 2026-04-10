"""Tests for Mimir Ruler API provider (BaseHTTPClient-based)."""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import httpx
import pytest

from nthlayer.providers.mimir import (
    MimirRulerError,
    MimirRulerProvider,
    RulerPushResult,
)
from nthlayer_common.clients.base import BaseHTTPClient


class TestMimirRulerProvider:
    def test_init_basic(self) -> None:
        provider = MimirRulerProvider(ruler_url="https://mimir:8080")
        assert provider._base_url == "https://mimir:8080"
        assert provider._tenant_id is None
        assert provider._api_key is None

    def test_init_with_tenant(self) -> None:
        provider = MimirRulerProvider(
            ruler_url="https://mimir:8080",
            tenant_id="my-tenant",
            api_key="secret-key",
        )
        assert provider._tenant_id == "my-tenant"
        assert provider._api_key == "secret-key"

    def test_init_strips_trailing_slash(self) -> None:
        provider = MimirRulerProvider(ruler_url="https://mimir:8080/")
        assert provider._base_url == "https://mimir:8080"

    def test_is_base_http_client(self) -> None:
        provider = MimirRulerProvider(ruler_url="https://mimir:8080")
        assert isinstance(provider, BaseHTTPClient)

    def test_headers_basic(self) -> None:
        provider = MimirRulerProvider(ruler_url="https://mimir:8080")
        headers = provider._headers()
        assert "User-Agent" in headers
        assert "X-Scope-OrgID" not in headers
        assert "Authorization" not in headers

    def test_headers_with_tenant(self) -> None:
        provider = MimirRulerProvider(
            ruler_url="https://mimir:8080", tenant_id="my-tenant"
        )
        headers = provider._headers()
        assert headers["X-Scope-OrgID"] == "my-tenant"

    def test_headers_with_api_key(self) -> None:
        provider = MimirRulerProvider(
            ruler_url="https://mimir:8080", api_key="secret-key"
        )
        headers = provider._headers()
        assert headers["Authorization"] == "Bearer secret-key"


class TestPushRules:
    @pytest.mark.asyncio
    async def test_push_rules_success(self) -> None:
        provider = MimirRulerProvider(ruler_url="https://mimir:8080")
        with patch.object(provider, "_request", new_callable=AsyncMock) as mock_req:
            mock_req.return_value = {}
            rules_yaml = "groups:\n  - name: test-service\n    rules: []\n"
            result = await provider.push_rules("test-service", rules_yaml)

        assert result.success
        assert result.namespace == "test-service"
        assert result.groups_pushed == 1

    @pytest.mark.asyncio
    async def test_push_rules_connection_error(self) -> None:
        provider = MimirRulerProvider(ruler_url="https://mimir:8080")
        with patch.object(provider, "_request", new_callable=AsyncMock) as mock_req:
            mock_req.side_effect = httpx.ConnectError("Connection refused")
            with pytest.raises(MimirRulerError, match="connect"):
                await provider.push_rules("test-service", "rules: []")


class TestRulerPushResult:
    def test_success_result(self) -> None:
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

    def test_failure_result(self) -> None:
        result = RulerPushResult(
            success=False,
            namespace="payment-api",
            status_code=500,
            message="Internal server error",
        )
        assert not result.success
        assert result.groups_pushed == 0


class TestDeleteRules:
    @pytest.mark.asyncio
    async def test_delete_namespace(self) -> None:
        provider = MimirRulerProvider(ruler_url="https://mimir:8080")
        with patch.object(provider, "_request", new_callable=AsyncMock) as mock_req:
            mock_req.return_value = {}
            result = await provider.delete_rules("test-service")

        assert result is True

    @pytest.mark.asyncio
    async def test_delete_specific_group(self) -> None:
        provider = MimirRulerProvider(ruler_url="https://mimir:8080")
        with patch.object(provider, "_request", new_callable=AsyncMock) as mock_req:
            mock_req.return_value = {}
            result = await provider.delete_rules("test-service", "alerts-group")

        assert result is True
        mock_req.assert_called_once()
        call_args = mock_req.call_args
        assert "test-service/alerts-group" in call_args[0][1]


class TestListRules:
    @pytest.mark.asyncio
    async def test_list_rules_success(self) -> None:
        provider = MimirRulerProvider(ruler_url="https://mimir:8080")
        with patch.object(provider, "_request", new_callable=AsyncMock) as mock_req:
            mock_req.return_value = {
                "payment-api": [{"name": "alerts", "rules": []}],
                "checkout-api": [{"name": "alerts", "rules": []}],
            }
            result = await provider.list_rules()

        assert "payment-api" in result
        assert "checkout-api" in result

    @pytest.mark.asyncio
    async def test_list_rules_error(self) -> None:
        provider = MimirRulerProvider(ruler_url="https://mimir:8080")
        with patch.object(provider, "_request", new_callable=AsyncMock) as mock_req:
            mock_req.side_effect = httpx.HTTPError("Internal error")
            with pytest.raises(MimirRulerError):
                await provider.list_rules()


class TestHealthCheck:
    @pytest.mark.asyncio
    async def test_health_check_healthy(self) -> None:
        provider = MimirRulerProvider(ruler_url="https://mimir:8080")
        with patch.object(provider, "list_rules", new_callable=AsyncMock):
            result = await provider.health_check()
        assert result is True

    @pytest.mark.asyncio
    async def test_health_check_unhealthy(self) -> None:
        provider = MimirRulerProvider(ruler_url="https://mimir:8080")
        with patch.object(
            provider, "list_rules", new_callable=AsyncMock,
            side_effect=MimirRulerError("down"),
        ):
            result = await provider.health_check()
        assert result is False


class TestBackwardCompat:
    def test_import_from_providers(self) -> None:
        from nthlayer.providers.mimir import MimirRulerProvider as P
        assert P is MimirRulerProvider

    def test_import_from_common_providers(self) -> None:
        from nthlayer_common.providers.mimir import MimirRulerProvider as P
        assert P is MimirRulerProvider

    def test_import_from_common_clients(self) -> None:
        from nthlayer_common.clients.mimir import MimirRulerProvider as P
        assert P is MimirRulerProvider
