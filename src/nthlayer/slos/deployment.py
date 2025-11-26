"""
Deployment event recording.

Records deployment events and stores them in the database for correlation analysis.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

import structlog

from nthlayer.slos.storage import SLORepository

logger = structlog.get_logger()


@dataclass
class Deployment:
    """Deployment event data."""
    
    id: str
    service: str
    environment: str
    deployed_at: datetime
    commit_sha: str | None = None
    author: str | None = None
    pr_number: str | None = None
    source: str = "manual"
    extra_data: dict[str, Any] = field(default_factory=dict)
    
    # Populated by correlator
    correlated_burn_minutes: float | None = None
    correlation_confidence: float | None = None
    
    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for storage."""
        return {
            "id": self.id,
            "service": self.service,
            "environment": self.environment,
            "deployed_at": self.deployed_at,
            "commit_sha": self.commit_sha,
            "author": self.author,
            "pr_number": self.pr_number,
            "source": self.source,
            "extra_data": self.extra_data,
            "correlated_burn_minutes": self.correlated_burn_minutes,
            "correlation_confidence": self.correlation_confidence,
        }


class DeploymentRecorder:
    """Records deployment events to database."""
    
    def __init__(self, repository: SLORepository) -> None:
        self.repository = repository
    
    async def record_manual(
        self,
        service: str,
        commit_sha: str,
        author: str | None = None,
        environment: str = "production",
        pr_number: str | None = None,
        deployed_at: datetime | None = None,
    ) -> Deployment:
        """
        Record a deployment manually (for testing or non-webhook sources).
        
        Args:
            service: Service name
            commit_sha: Git commit SHA
            author: Deploy author email
            environment: Environment (production, staging, etc.)
            pr_number: Pull request number
            deployed_at: Deployment timestamp (defaults to now)
            
        Returns:
            Recorded deployment
        """
        if deployed_at is None:
            deployed_at = datetime.utcnow()
        
        deployment = Deployment(
            id=commit_sha[:12],  # Use first 12 chars of SHA as ID
            service=service,
            environment=environment,
            deployed_at=deployed_at,
            commit_sha=commit_sha,
            author=author,
            pr_number=pr_number,
            source="manual",
        )
        
        logger.info(
            "recording_deployment",
            deployment_id=deployment.id,
            service=service,
            commit_sha=commit_sha,
            author=author,
        )
        
        await self.repository.create_deployment(deployment)
        
        return deployment
    
    async def record_from_argocd(self, payload: dict[str, Any]) -> Deployment:
        """
        Record deployment from ArgoCD webhook payload.
        
        ArgoCD webhook structure:
        {
            "type": "app.sync.succeeded",
            "app": {
                "metadata": {"name": "service-name"},
                "spec": {"source": {"targetRevision": "abc123"}}
            },
            "timestamp": "2025-01-10T14:23:00Z"
        }
        
        Args:
            payload: ArgoCD webhook payload
            
        Returns:
            Recorded deployment
        """
        app = payload.get("app", {})
        metadata = app.get("metadata", {})
        spec = app.get("spec", {})
        source = spec.get("source", {})
        
        service = metadata.get("name", "unknown")
        commit_sha = source.get("targetRevision", "unknown")
        deployed_at_str = payload.get("timestamp")
        
        deployed_at = (
            datetime.fromisoformat(deployed_at_str.replace("Z", "+00:00"))
            if deployed_at_str
            else datetime.utcnow()
        )
        
        deployment = Deployment(
            id=f"argocd-{commit_sha[:12]}",
            service=service,
            environment="production",  # Could parse from app metadata
            deployed_at=deployed_at,
            commit_sha=commit_sha,
            source="argocd",
            extra_data={"sync_type": payload.get("type")},
        )
        
        logger.info(
            "recording_argocd_deployment",
            deployment_id=deployment.id,
            service=service,
            commit_sha=commit_sha,
        )
        
        await self.repository.create_deployment(deployment)
        
        return deployment
    
    async def record_from_github(self, payload: dict[str, Any]) -> Deployment:
        """
        Record deployment from GitHub Actions webhook payload.
        
        GitHub Actions webhook structure:
        {
            "action": "completed",
            "workflow_run": {
                "name": "Deploy to Production",
                "head_sha": "abc123",
                "conclusion": "success",
                "created_at": "2025-01-10T14:23:00Z"
            },
            "repository": {"name": "service-name"},
            "sender": {"login": "username"}
        }
        
        Args:
            payload: GitHub Actions webhook payload
            
        Returns:
            Recorded deployment
        """
        workflow_run = payload.get("workflow_run", {})
        repository = payload.get("repository", {})
        sender = payload.get("sender", {})
        
        service = repository.get("name", "unknown")
        commit_sha = workflow_run.get("head_sha", "unknown")
        author = f"{sender.get('login')}@github.com"
        deployed_at_str = workflow_run.get("created_at")
        
        deployed_at = (
            datetime.fromisoformat(deployed_at_str.replace("Z", "+00:00"))
            if deployed_at_str
            else datetime.utcnow()
        )
        
        # Extract PR number from workflow_run if available
        pr_number = None
        pull_requests = workflow_run.get("pull_requests", [])
        if pull_requests:
            pr_number = str(pull_requests[0].get("number"))
        
        deployment = Deployment(
            id=f"gh-{commit_sha[:12]}",
            service=service,
            environment="production",
            deployed_at=deployed_at,
            commit_sha=commit_sha,
            author=author,
            pr_number=pr_number,
            source="github-actions",
            extra_data={
                "workflow_name": workflow_run.get("name"),
                "conclusion": workflow_run.get("conclusion"),
            },
        )
        
        logger.info(
            "recording_github_deployment",
            deployment_id=deployment.id,
            service=service,
            commit_sha=commit_sha,
            author=author,
        )
        
        await self.repository.create_deployment(deployment)
        
        return deployment
    
    async def get_recent_deployments(
        self,
        service: str,
        hours: int = 24,
        environment: str = "production",
    ) -> list[Deployment]:
        """
        Get recent deployments for a service.
        
        Args:
            service: Service name
            hours: Lookback period in hours
            environment: Environment filter
            
        Returns:
            List of recent deployments
        """
        return await self.repository.get_recent_deployments(
            service=service,
            hours=hours,
            environment=environment,
        )
