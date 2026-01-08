"""Tests for slos/deployment.py.

Tests for deployment event recording and correlation.
"""

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

import pytest
from nthlayer.slos.deployment import Deployment, DeploymentRecorder


@pytest.fixture
def sample_deployment():
    """Create a sample deployment."""
    return Deployment(
        id="abc123def456",
        service="test-service",
        environment="production",
        deployed_at=datetime(2025, 1, 10, 14, 30, 0),
        commit_sha="abc123def456789012345678901234567890abcd",
        author="developer@example.com",
        pr_number="123",
        source="manual",
    )


@pytest.fixture
def mock_repository():
    """Create a mock SLORepository."""
    repo = MagicMock()
    repo.create_deployment = AsyncMock()
    repo.get_recent_deployments = AsyncMock(return_value=[])
    return repo


class TestDeployment:
    """Tests for Deployment dataclass."""

    def test_create_minimal_deployment(self):
        """Test creating deployment with minimal fields."""
        deployment = Deployment(
            id="deploy-001",
            service="my-service",
            environment="staging",
            deployed_at=datetime(2025, 1, 10, 12, 0, 0),
        )

        assert deployment.id == "deploy-001"
        assert deployment.service == "my-service"
        assert deployment.environment == "staging"
        assert deployment.commit_sha is None
        assert deployment.author is None
        assert deployment.pr_number is None
        assert deployment.source == "manual"
        assert deployment.extra_data == {}
        assert deployment.correlated_burn_minutes is None
        assert deployment.correlation_confidence is None

    def test_create_full_deployment(self, sample_deployment):
        """Test creating deployment with all fields."""
        assert sample_deployment.id == "abc123def456"
        assert sample_deployment.service == "test-service"
        assert sample_deployment.environment == "production"
        assert sample_deployment.commit_sha == "abc123def456789012345678901234567890abcd"
        assert sample_deployment.author == "developer@example.com"
        assert sample_deployment.pr_number == "123"
        assert sample_deployment.source == "manual"

    def test_to_dict(self, sample_deployment):
        """Test converting deployment to dictionary."""
        result = sample_deployment.to_dict()

        assert result["id"] == "abc123def456"
        assert result["service"] == "test-service"
        assert result["environment"] == "production"
        assert result["deployed_at"] == datetime(2025, 1, 10, 14, 30, 0)
        assert result["commit_sha"] == "abc123def456789012345678901234567890abcd"
        assert result["author"] == "developer@example.com"
        assert result["pr_number"] == "123"
        assert result["source"] == "manual"
        assert result["extra_data"] == {}
        assert result["correlated_burn_minutes"] is None
        assert result["correlation_confidence"] is None

    def test_to_dict_with_correlation_data(self, sample_deployment):
        """Test to_dict with correlation data populated."""
        sample_deployment.correlated_burn_minutes = 15.5
        sample_deployment.correlation_confidence = 0.85

        result = sample_deployment.to_dict()

        assert result["correlated_burn_minutes"] == 15.5
        assert result["correlation_confidence"] == 0.85

    def test_extra_data(self):
        """Test deployment with extra_data."""
        deployment = Deployment(
            id="deploy-001",
            service="my-service",
            environment="production",
            deployed_at=datetime(2025, 1, 10, 12, 0, 0),
            extra_data={"workflow_name": "Deploy", "conclusion": "success"},
        )

        assert deployment.extra_data["workflow_name"] == "Deploy"
        assert deployment.extra_data["conclusion"] == "success"


class TestDeploymentRecorder:
    """Tests for DeploymentRecorder class."""

    def test_init(self, mock_repository):
        """Test DeploymentRecorder initialization."""
        recorder = DeploymentRecorder(mock_repository)

        assert recorder.repository is mock_repository

    @pytest.mark.asyncio
    async def test_record_manual(self, mock_repository):
        """Test recording manual deployment."""
        recorder = DeploymentRecorder(mock_repository)

        deployment = await recorder.record_manual(
            service="test-service",
            commit_sha="abc123def456789012345678901234567890abcd",
            author="developer@example.com",
            environment="production",
            pr_number="456",
        )

        assert deployment.id == "abc123def456"  # First 12 chars of SHA
        assert deployment.service == "test-service"
        assert deployment.environment == "production"
        assert deployment.commit_sha == "abc123def456789012345678901234567890abcd"
        assert deployment.author == "developer@example.com"
        assert deployment.pr_number == "456"
        assert deployment.source == "manual"
        mock_repository.create_deployment.assert_called_once()

    @pytest.mark.asyncio
    async def test_record_manual_minimal(self, mock_repository):
        """Test recording manual deployment with minimal fields."""
        recorder = DeploymentRecorder(mock_repository)

        deployment = await recorder.record_manual(
            service="test-service",
            commit_sha="abc123def456789012345678901234567890abcd",
        )

        assert deployment.service == "test-service"
        assert deployment.environment == "production"  # Default
        assert deployment.author is None
        assert deployment.pr_number is None
        assert deployment.deployed_at is not None  # Auto-generated

    @pytest.mark.asyncio
    async def test_record_manual_custom_deployed_at(self, mock_repository):
        """Test recording manual deployment with custom deployed_at."""
        recorder = DeploymentRecorder(mock_repository)
        custom_time = datetime(2025, 1, 5, 10, 30, 0)

        deployment = await recorder.record_manual(
            service="test-service",
            commit_sha="abc123",
            deployed_at=custom_time,
        )

        assert deployment.deployed_at == custom_time

    @pytest.mark.asyncio
    async def test_record_from_argocd(self, mock_repository):
        """Test recording ArgoCD deployment."""
        recorder = DeploymentRecorder(mock_repository)
        payload = {
            "type": "app.sync.succeeded",
            "app": {
                "metadata": {"name": "my-service"},
                "spec": {"source": {"targetRevision": "def456789012345678901234567890abcdef01"}},
            },
            "timestamp": "2025-01-10T14:23:00Z",
        }

        deployment = await recorder.record_from_argocd(payload)

        assert deployment.id == "argocd-def456789012"
        assert deployment.service == "my-service"
        assert deployment.commit_sha == "def456789012345678901234567890abcdef01"
        assert deployment.environment == "production"
        assert deployment.source == "argocd"
        assert deployment.extra_data["sync_type"] == "app.sync.succeeded"
        mock_repository.create_deployment.assert_called_once()

    @pytest.mark.asyncio
    async def test_record_from_argocd_missing_fields(self, mock_repository):
        """Test recording ArgoCD deployment with missing fields."""
        recorder = DeploymentRecorder(mock_repository)
        payload = {}  # Empty payload

        deployment = await recorder.record_from_argocd(payload)

        assert deployment.service == "unknown"
        assert deployment.commit_sha == "unknown"
        assert deployment.deployed_at is not None  # Falls back to utcnow

    @pytest.mark.asyncio
    async def test_record_from_argocd_partial_payload(self, mock_repository):
        """Test recording ArgoCD deployment with partial payload."""
        recorder = DeploymentRecorder(mock_repository)
        payload = {
            "app": {
                "metadata": {"name": "partial-service"},
            },
        }

        deployment = await recorder.record_from_argocd(payload)

        assert deployment.service == "partial-service"
        assert deployment.commit_sha == "unknown"

    @pytest.mark.asyncio
    async def test_record_from_github(self, mock_repository):
        """Test recording GitHub Actions deployment."""
        recorder = DeploymentRecorder(mock_repository)
        payload = {
            "action": "completed",
            "workflow_run": {
                "name": "Deploy to Production",
                "head_sha": "gh123456789012345678901234567890abcdefgh",
                "conclusion": "success",
                "created_at": "2025-01-10T14:23:00Z",
                "pull_requests": [{"number": 789}],
            },
            "repository": {"name": "my-app"},
            "sender": {"login": "developer"},
        }

        deployment = await recorder.record_from_github(payload)

        assert deployment.id == "gh-gh1234567890"
        assert deployment.service == "my-app"
        assert deployment.commit_sha == "gh123456789012345678901234567890abcdefgh"
        assert deployment.author == "developer@github.com"
        assert deployment.pr_number == "789"
        assert deployment.environment == "production"
        assert deployment.source == "github-actions"
        assert deployment.extra_data["workflow_name"] == "Deploy to Production"
        assert deployment.extra_data["conclusion"] == "success"
        mock_repository.create_deployment.assert_called_once()

    @pytest.mark.asyncio
    async def test_record_from_github_no_pr(self, mock_repository):
        """Test recording GitHub deployment without PR."""
        recorder = DeploymentRecorder(mock_repository)
        payload = {
            "workflow_run": {
                "head_sha": "abc123def456",
                "pull_requests": [],
            },
            "repository": {"name": "my-app"},
            "sender": {"login": "user"},
        }

        deployment = await recorder.record_from_github(payload)

        assert deployment.pr_number is None

    @pytest.mark.asyncio
    async def test_record_from_github_missing_fields(self, mock_repository):
        """Test recording GitHub deployment with missing fields."""
        recorder = DeploymentRecorder(mock_repository)
        payload = {}  # Empty payload

        deployment = await recorder.record_from_github(payload)

        assert deployment.service == "unknown"
        assert deployment.commit_sha == "unknown"
        assert deployment.author == "None@github.com"

    @pytest.mark.asyncio
    async def test_record_from_github_partial_payload(self, mock_repository):
        """Test recording GitHub deployment with partial payload."""
        recorder = DeploymentRecorder(mock_repository)
        payload = {
            "repository": {"name": "partial-repo"},
            "sender": {},
        }

        deployment = await recorder.record_from_github(payload)

        assert deployment.service == "partial-repo"

    @pytest.mark.asyncio
    async def test_get_recent_deployments(self, mock_repository):
        """Test getting recent deployments."""
        expected_deployments = [
            Deployment(
                id="deploy-001",
                service="test-service",
                environment="production",
                deployed_at=datetime(2025, 1, 10, 12, 0, 0),
            ),
        ]
        mock_repository.get_recent_deployments = AsyncMock(return_value=expected_deployments)

        recorder = DeploymentRecorder(mock_repository)
        deployments = await recorder.get_recent_deployments(
            service="test-service",
            hours=48,
            environment="staging",
        )

        assert deployments == expected_deployments
        mock_repository.get_recent_deployments.assert_called_once_with(
            service="test-service",
            hours=48,
            environment="staging",
        )

    @pytest.mark.asyncio
    async def test_get_recent_deployments_defaults(self, mock_repository):
        """Test getting recent deployments with default parameters."""
        mock_repository.get_recent_deployments = AsyncMock(return_value=[])

        recorder = DeploymentRecorder(mock_repository)
        await recorder.get_recent_deployments(service="test-service")

        mock_repository.get_recent_deployments.assert_called_once_with(
            service="test-service",
            hours=24,
            environment="production",
        )

    @pytest.mark.asyncio
    async def test_get_recent_deployments_empty(self, mock_repository):
        """Test getting recent deployments when none exist."""
        mock_repository.get_recent_deployments = AsyncMock(return_value=[])

        recorder = DeploymentRecorder(mock_repository)
        deployments = await recorder.get_recent_deployments(service="test-service")

        assert deployments == []
