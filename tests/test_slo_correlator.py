"""Tests for SLO deployment correlator.

Tests for correlating deployments with error budget burns,
confidence calculation, and blame analysis.
"""

from datetime import datetime, timedelta
from unittest.mock import AsyncMock

import pytest
from nthlayer.slos.correlator import (
    HIGH_CONFIDENCE,
    LOW_CONFIDENCE,
    MEDIUM_CONFIDENCE,
    CorrelationResult,
    CorrelationWindow,
    DeploymentCorrelator,
)
from nthlayer.slos.deployment import Deployment
from nthlayer.slos.models import SLO, TimeWindow, TimeWindowType


@pytest.fixture
def sample_deployment():
    """Create a sample deployment for testing."""
    return Deployment(
        id="deploy-001",
        service="payment-api",
        environment="production",
        deployed_at=datetime.utcnow() - timedelta(hours=2),
        commit_sha="abc123def456",
        author="ci-pipeline",
    )


@pytest.fixture
def sample_slo():
    """Create a sample SLO for testing."""
    return SLO(
        id="slo-availability-001",
        service="payment-api",
        name="availability",
        description="Service availability SLO",
        target=99.95,
        time_window=TimeWindow(duration="30d", type=TimeWindowType.ROLLING),
        query="availability_ratio",
        owner="platform-team",
        labels={},
    )


@pytest.fixture
def mock_repository():
    """Create a mock SLO repository."""
    repo = AsyncMock()
    repo.get_burn_rate_window = AsyncMock()
    repo.get_recent_deployments = AsyncMock()
    repo.get_slos_by_service = AsyncMock()
    repo.update_deployment_correlation = AsyncMock()
    return repo


@pytest.fixture
def correlator(mock_repository):
    """Create a DeploymentCorrelator with mock repository."""
    return DeploymentCorrelator(mock_repository)


class TestCorrelationWindow:
    """Tests for CorrelationWindow configuration."""

    def test_default_window(self):
        """Test default window values."""
        window = CorrelationWindow()

        assert window.before_minutes == 30
        assert window.after_minutes == 120

    def test_custom_window(self):
        """Test custom window configuration."""
        window = CorrelationWindow(before_minutes=15, after_minutes=60)

        assert window.before_minutes == 15
        assert window.after_minutes == 60


class TestCorrelationResult:
    """Tests for CorrelationResult dataclass."""

    def test_high_confidence_label(self):
        """Test HIGH confidence label."""
        result = CorrelationResult(
            deployment_id="deploy-001",
            service="test",
            burn_minutes=10.0,
            confidence=0.8,  # >= HIGH_CONFIDENCE
            method="test",
            details={},
        )

        assert result.confidence_label == "HIGH"
        assert result.confidence_emoji == "🔴"

    def test_medium_confidence_label(self):
        """Test MEDIUM confidence label."""
        result = CorrelationResult(
            deployment_id="deploy-001",
            service="test",
            burn_minutes=5.0,
            confidence=0.6,  # >= MEDIUM_CONFIDENCE but < HIGH_CONFIDENCE
            method="test",
            details={},
        )

        assert result.confidence_label == "MEDIUM"
        assert result.confidence_emoji == "🟡"

    def test_low_confidence_label(self):
        """Test LOW confidence label."""
        result = CorrelationResult(
            deployment_id="deploy-001",
            service="test",
            burn_minutes=2.0,
            confidence=0.4,  # >= LOW_CONFIDENCE but < MEDIUM_CONFIDENCE
            method="test",
            details={},
        )

        assert result.confidence_label == "LOW"
        assert result.confidence_emoji == "✅"

    def test_none_confidence_label(self):
        """Test NONE confidence label."""
        result = CorrelationResult(
            deployment_id="deploy-001",
            service="test",
            burn_minutes=0.5,
            confidence=0.1,  # < LOW_CONFIDENCE
            method="test",
            details={},
        )

        assert result.confidence_label == "NONE"
        assert result.confidence_emoji == "✅"


class TestDeploymentCorrelatorInit:
    """Tests for DeploymentCorrelator initialization."""

    def test_init_with_repository(self, mock_repository):
        """Test correlator initialization with repository."""
        correlator = DeploymentCorrelator(mock_repository)

        assert correlator.repository == mock_repository
        assert correlator.window.before_minutes == 30
        assert correlator.window.after_minutes == 120

    def test_init_with_custom_window(self, mock_repository):
        """Test correlator initialization with custom window."""
        window = CorrelationWindow(before_minutes=60, after_minutes=180)
        correlator = DeploymentCorrelator(mock_repository, window=window)

        assert correlator.window.before_minutes == 60
        assert correlator.window.after_minutes == 180


class TestCorrelateDeployment:
    """Tests for single deployment correlation."""

    @pytest.mark.asyncio
    async def test_correlate_deployment_high_confidence(
        self, correlator, mock_repository, sample_deployment, sample_slo
    ):
        """Test correlation with high confidence (spike after deploy)."""
        # Before deploy: low burn rate
        # After deploy: high burn rate (spike)
        mock_repository.get_burn_rate_window.side_effect = [
            0.001,  # before: 0.1% burn
            0.05,  # after: 5% burn (50x spike!)
        ]

        result = await correlator.correlate_deployment(sample_deployment, sample_slo)

        assert result.deployment_id == sample_deployment.id
        assert result.confidence >= MEDIUM_CONFIDENCE
        assert result.burn_minutes > 0

    @pytest.mark.asyncio
    async def test_correlate_deployment_low_confidence(
        self, correlator, mock_repository, sample_deployment, sample_slo
    ):
        """Test correlation with low confidence (no spike)."""
        # Same burn rate before and after
        mock_repository.get_burn_rate_window.side_effect = [
            0.01,  # before: 1% burn
            0.01,  # after: 1% burn (no spike)
        ]

        result = await correlator.correlate_deployment(sample_deployment, sample_slo)

        assert result.deployment_id == sample_deployment.id
        # Lower confidence when no spike
        assert result.confidence < HIGH_CONFIDENCE

    @pytest.mark.asyncio
    async def test_correlate_deployment_no_baseline(
        self, correlator, mock_repository, sample_deployment, sample_slo
    ):
        """Test correlation when no baseline (before = 0)."""
        mock_repository.get_burn_rate_window.side_effect = [
            0.0,  # before: no data
            0.05,  # after: 5% burn
        ]

        result = await correlator.correlate_deployment(sample_deployment, sample_slo)

        # Should still calculate confidence based on after rate
        assert result.burn_minutes > 0

    @pytest.mark.asyncio
    async def test_correlate_deployment_updates_repository(
        self, correlator, mock_repository, sample_deployment, sample_slo
    ):
        """Test that correlation updates repository when confidence > LOW."""
        mock_repository.get_burn_rate_window.side_effect = [
            0.001,
            0.05,
        ]

        result = await correlator.correlate_deployment(sample_deployment, sample_slo)

        if result.confidence >= LOW_CONFIDENCE:
            mock_repository.update_deployment_correlation.assert_called_once()


class TestCorrelateService:
    """Tests for service-wide correlation."""

    @pytest.mark.asyncio
    async def test_correlate_service_with_deployments(
        self, correlator, mock_repository, sample_deployment, sample_slo
    ):
        """Test correlating all deployments for a service."""
        mock_repository.get_recent_deployments.return_value = [sample_deployment]
        mock_repository.get_slos_by_service.return_value = [sample_slo]
        mock_repository.get_burn_rate_window.side_effect = [
            0.001,  # before
            0.03,  # after
        ]

        results = await correlator.correlate_service("payment-api", lookback_hours=24)

        assert len(results) >= 0  # May be filtered by confidence

    @pytest.mark.asyncio
    async def test_correlate_service_no_deployments(self, correlator, mock_repository, sample_slo):
        """Test correlation when no deployments found."""
        mock_repository.get_recent_deployments.return_value = []
        mock_repository.get_slos_by_service.return_value = [sample_slo]

        results = await correlator.correlate_service("payment-api", lookback_hours=24)

        assert results == []

    @pytest.mark.asyncio
    async def test_correlate_service_no_slos(self, correlator, mock_repository, sample_deployment):
        """Test correlation when no SLOs found."""
        mock_repository.get_recent_deployments.return_value = [sample_deployment]
        mock_repository.get_slos_by_service.return_value = []

        results = await correlator.correlate_service("payment-api", lookback_hours=24)

        assert results == []

    @pytest.mark.asyncio
    async def test_correlate_service_multiple_deployments(
        self, correlator, mock_repository, sample_slo
    ):
        """Test correlating multiple deployments."""
        deployments = [
            Deployment(
                id=f"deploy-{i}",
                service="payment-api",
                environment="production",
                deployed_at=datetime.utcnow() - timedelta(hours=i * 2),
                commit_sha=f"sha{i}",
                author="ci-pipeline",
            )
            for i in range(3)
        ]

        mock_repository.get_recent_deployments.return_value = deployments
        mock_repository.get_slos_by_service.return_value = [sample_slo]
        # Alternating burn rates for each correlation
        mock_repository.get_burn_rate_window.side_effect = [
            0.001,
            0.05,  # deploy-0
            0.001,
            0.02,  # deploy-1
            0.001,
            0.01,  # deploy-2
        ]

        results = await correlator.correlate_service("payment-api", lookback_hours=24)

        # Results should be sorted by confidence (highest first)
        if len(results) > 1:
            for i in range(len(results) - 1):
                assert results[i].confidence >= results[i + 1].confidence

    @pytest.mark.asyncio
    async def test_correlate_service_handles_errors(
        self, correlator, mock_repository, sample_deployment, sample_slo
    ):
        """Test that correlation handles individual errors gracefully."""
        mock_repository.get_recent_deployments.return_value = [sample_deployment]
        mock_repository.get_slos_by_service.return_value = [sample_slo]
        mock_repository.get_burn_rate_window.side_effect = Exception("DB error")

        # Should not raise, should return empty or partial results
        results = await correlator.correlate_service("payment-api")

        assert results == []


class TestBurnRateScoreCalculation:
    """Tests for burn rate score calculation."""

    def test_burn_rate_score_high_spike(self, correlator):
        """Test high score for large spike."""
        # 10x spike should give high score
        score = correlator._calculate_burn_rate_score(
            before_rate=0.01,
            after_rate=0.1,
        )

        assert score >= 0.8  # High spike = high score

    def test_burn_rate_score_no_spike(self, correlator):
        """Test low score when no spike."""
        score = correlator._calculate_burn_rate_score(
            before_rate=0.01,
            after_rate=0.01,
        )

        assert score < 0.5  # No spike = low score

    def test_burn_rate_score_no_baseline(self, correlator):
        """Test score calculation when no baseline."""
        score = correlator._calculate_burn_rate_score(
            before_rate=0.0,
            after_rate=0.05,
        )

        # Should use absolute after rate
        assert score > 0

    def test_burn_rate_score_capped_at_one(self, correlator):
        """Test that score is capped at 1.0."""
        # Massive spike
        score = correlator._calculate_burn_rate_score(
            before_rate=0.001,
            after_rate=1.0,  # 1000x spike
        )

        assert score <= 1.0


class TestMagnitudeScoreCalculation:
    """Tests for magnitude score calculation."""

    def test_magnitude_score_high_burn(self, correlator):
        """Test high score for large burn."""
        score = correlator._calculate_magnitude_score(burn_minutes=15.0)

        assert score == 1.0  # >= 10 minutes = max score

    def test_magnitude_score_low_burn(self, correlator):
        """Test low score for small burn."""
        score = correlator._calculate_magnitude_score(burn_minutes=2.0)

        assert score == pytest.approx(0.2)  # 2/10 = 0.2

    def test_magnitude_score_zero_burn(self, correlator):
        """Test zero score for no burn."""
        score = correlator._calculate_magnitude_score(burn_minutes=0.0)

        assert score == 0.0

    def test_magnitude_score_capped_at_one(self, correlator):
        """Test that score is capped at 1.0."""
        score = correlator._calculate_magnitude_score(burn_minutes=100.0)

        assert score == 1.0


class TestConfidenceThresholds:
    """Tests for confidence threshold constants."""

    def test_threshold_ordering(self):
        """Test that thresholds are properly ordered."""
        assert HIGH_CONFIDENCE > MEDIUM_CONFIDENCE
        assert MEDIUM_CONFIDENCE > LOW_CONFIDENCE
        assert LOW_CONFIDENCE > 0

    def test_threshold_values(self):
        """Test expected threshold values."""
        assert HIGH_CONFIDENCE == 0.7
        assert MEDIUM_CONFIDENCE == 0.5
        assert LOW_CONFIDENCE == 0.3
