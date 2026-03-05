"""Tests for nthlayer.cloudwatch — CloudWatch metrics collector."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

aioboto3 = pytest.importorskip("aioboto3", reason="aioboto3 is required for cloudwatch tests")

from nthlayer.cloudwatch import MetricsCollector, get_metrics_collector


class TestMetricsCollector:
    def test_init_defaults(self):
        mc = MetricsCollector()
        assert mc.namespace == "NthLayer"
        assert mc.region == "eu-west-1"
        assert mc._metrics_buffer == []

    def test_init_custom(self):
        mc = MetricsCollector(namespace="Custom", region="us-east-1")
        assert mc.namespace == "Custom"
        assert mc.region == "us-east-1"

    @pytest.mark.asyncio
    async def test_emit_buffers_metric(self):
        mc = MetricsCollector()
        await mc.emit("test_metric", 1.0, unit="Count", service="checkout")
        assert len(mc._metrics_buffer) == 1
        entry = mc._metrics_buffer[0]
        assert entry["MetricName"] == "test_metric"
        assert entry["Value"] == 1.0
        assert entry["Unit"] == "Count"
        dims = entry["Dimensions"]
        assert any(d["Name"] == "service" and d["Value"] == "checkout" for d in dims)

    @pytest.mark.asyncio
    async def test_emit_flushes_at_threshold(self):
        mc = MetricsCollector()
        mc._flush = AsyncMock()
        for i in range(20):
            await mc.emit(f"metric_{i}", float(i))
        mc._flush.assert_called_once()

    @pytest.mark.asyncio
    async def test_emit_does_not_flush_below_threshold(self):
        mc = MetricsCollector()
        mc._flush = AsyncMock()
        for i in range(19):
            await mc.emit(f"metric_{i}", float(i))
        mc._flush.assert_not_called()

    @pytest.mark.asyncio
    async def test_timer_emits_duration(self):
        mc = MetricsCollector()
        async with mc.timer("op_duration", service="svc"):
            pass
        assert len(mc._metrics_buffer) == 1
        entry = mc._metrics_buffer[0]
        assert entry["MetricName"] == "op_duration"
        assert entry["Unit"] == "Seconds"
        assert entry["Value"] >= 0

    @pytest.mark.asyncio
    async def test_flush_empty_is_noop(self):
        mc = MetricsCollector()
        # Should not raise when buffer is empty
        await mc._flush()
        assert mc._metrics_buffer == []

    @pytest.mark.asyncio
    async def test_flush_sends_to_cloudwatch(self):
        mc = MetricsCollector()
        mc._metrics_buffer = [{"MetricName": "test", "Value": 1.0}]

        mock_cw_client = AsyncMock()
        mock_cw_client.put_metric_data = AsyncMock()
        mock_cw_client.__aenter__ = AsyncMock(return_value=mock_cw_client)
        mock_cw_client.__aexit__ = AsyncMock()

        mock_session = MagicMock()
        mock_session.client.return_value = mock_cw_client

        with patch("nthlayer.cloudwatch.aioboto3.Session", return_value=mock_session):
            await mc._flush()

        mock_cw_client.put_metric_data.assert_called_once()
        assert mc._metrics_buffer == []

    @pytest.mark.asyncio
    async def test_flush_error_logs_and_continues(self):
        """Flush errors should be logged, not raised."""
        mc = MetricsCollector()
        mc._metrics_buffer = [{"MetricName": "test", "Value": 1.0}]

        mock_cw_client = AsyncMock()
        mock_cw_client.put_metric_data = AsyncMock(side_effect=Exception("AWS error"))
        mock_cw_client.__aenter__ = AsyncMock(return_value=mock_cw_client)
        mock_cw_client.__aexit__ = AsyncMock()

        mock_session = MagicMock()
        mock_session.client.return_value = mock_cw_client

        with patch("nthlayer.cloudwatch.aioboto3.Session", return_value=mock_session):
            await mc._flush()  # Should not raise

    @pytest.mark.asyncio
    async def test_close_flushes(self):
        mc = MetricsCollector()
        mc._flush = AsyncMock()
        await mc.close()
        mc._flush.assert_called_once()


class TestGetMetricsCollector:
    def test_returns_singleton(self):
        # Reset global state
        import nthlayer.cloudwatch as cw_mod

        cw_mod._metrics_collector = None

        mc1 = get_metrics_collector()
        mc2 = get_metrics_collector()
        assert mc1 is mc2

        # Cleanup
        cw_mod._metrics_collector = None

    def test_custom_params(self):
        import nthlayer.cloudwatch as cw_mod

        cw_mod._metrics_collector = None

        mc = get_metrics_collector(namespace="Custom", region="us-east-1")
        assert mc.namespace == "Custom"
        assert mc.region == "us-east-1"

        # Cleanup
        cw_mod._metrics_collector = None
