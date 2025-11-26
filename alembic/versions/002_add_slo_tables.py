"""add slo tables

Revision ID: 002
Revises: 001
Create Date: 2025-11-14

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '002'
down_revision = '001'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create SLOs table
    op.create_table(
        'slos',
        sa.Column('id', sa.String(255), primary_key=True),
        sa.Column('service', sa.String(255), nullable=False, index=True),
        sa.Column('name', sa.String(255), nullable=False),
        sa.Column('description', sa.Text, nullable=True),
        sa.Column('target', sa.Float, nullable=False),  # e.g., 0.9995 for 99.95%
        sa.Column('time_window_duration', sa.String(50), nullable=False),  # e.g., "30d"
        sa.Column('time_window_type', sa.String(50), nullable=False, default='rolling'),
        sa.Column('query', sa.Text, nullable=False),  # Prometheus query
        sa.Column('owner', sa.String(255), nullable=True),
        sa.Column('labels', postgresql.JSONB, nullable=True),
        sa.Column('created_at', sa.DateTime, nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime, nullable=False, server_default=sa.func.now(), onupdate=sa.func.now()),
    )
    
    # Create index on service for faster lookups
    op.create_index('idx_slos_service', 'slos', ['service'])
    
    # Create error_budgets table
    op.create_table(
        'error_budgets',
        sa.Column('id', sa.Integer, primary_key=True, autoincrement=True),
        sa.Column('slo_id', sa.String(255), sa.ForeignKey('slos.id', ondelete='CASCADE'), nullable=False),
        sa.Column('service', sa.String(255), nullable=False, index=True),
        sa.Column('period_start', sa.DateTime, nullable=False),
        sa.Column('period_end', sa.DateTime, nullable=False),
        sa.Column('total_budget_minutes', sa.Float, nullable=False),
        sa.Column('burned_minutes', sa.Float, nullable=False, default=0.0),
        sa.Column('remaining_minutes', sa.Float, nullable=False),
        sa.Column('incident_burn_minutes', sa.Float, nullable=False, default=0.0),
        sa.Column('deployment_burn_minutes', sa.Float, nullable=False, default=0.0),
        sa.Column('slo_breach_burn_minutes', sa.Float, nullable=False, default=0.0),
        sa.Column('status', sa.String(50), nullable=False, default='healthy'),
        sa.Column('burn_rate', sa.Float, nullable=False, default=0.0),
        sa.Column('updated_at', sa.DateTime, nullable=False, server_default=sa.func.now(), onupdate=sa.func.now()),
    )
    
    # Create composite index for time-range queries
    op.create_index('idx_error_budgets_service_period', 'error_budgets', ['service', 'period_start', 'period_end'])
    op.create_index('idx_error_budgets_slo_period', 'error_budgets', ['slo_id', 'period_start'])
    
    # Create slo_history table for tracking budget burns over time
    op.create_table(
        'slo_history',
        sa.Column('id', sa.Integer, primary_key=True, autoincrement=True),
        sa.Column('slo_id', sa.String(255), sa.ForeignKey('slos.id', ondelete='CASCADE'), nullable=False),
        sa.Column('service', sa.String(255), nullable=False, index=True),
        sa.Column('timestamp', sa.DateTime, nullable=False, index=True),
        sa.Column('sli_value', sa.Float, nullable=False),  # Measured SLI value
        sa.Column('target_value', sa.Float, nullable=False),  # Target SLI value
        sa.Column('compliant', sa.Boolean, nullable=False),  # Whether SLI met target
        sa.Column('budget_burn_minutes', sa.Float, nullable=False, default=0.0),  # Minutes burned in this period
        sa.Column('extra_data', postgresql.JSONB, nullable=True),  # Additional context
        sa.Column('created_at', sa.DateTime, nullable=False, server_default=sa.func.now()),
    )
    
    # Create index for time-series queries
    op.create_index('idx_slo_history_slo_timestamp', 'slo_history', ['slo_id', 'timestamp'])
    op.create_index('idx_slo_history_service_timestamp', 'slo_history', ['service', 'timestamp'])
    
    # Create deployments table for tracking deployments and correlating with budget burns
    op.create_table(
        'deployments',
        sa.Column('id', sa.String(255), primary_key=True),  # e.g., commit SHA or ArgoCD sync ID
        sa.Column('service', sa.String(255), nullable=False, index=True),
        sa.Column('environment', sa.String(50), nullable=False, default='production'),
        sa.Column('deployed_at', sa.DateTime, nullable=False, index=True),
        sa.Column('commit_sha', sa.String(255), nullable=True),
        sa.Column('author', sa.String(255), nullable=True),
        sa.Column('pr_number', sa.String(50), nullable=True),
        sa.Column('source', sa.String(50), nullable=False),  # e.g., "argocd", "github-actions"
        sa.Column('extra_data', postgresql.JSONB, nullable=True),
        sa.Column('correlated_burn_minutes', sa.Float, nullable=True),  # Budget burn attributed to this deploy
        sa.Column('correlation_confidence', sa.Float, nullable=True),  # 0.0-1.0 confidence score
        sa.Column('created_at', sa.DateTime, nullable=False, server_default=sa.func.now()),
    )
    
    # Create index for correlation queries
    op.create_index('idx_deployments_service_deployed', 'deployments', ['service', 'deployed_at'])
    
    # Create incidents table for tracking PagerDuty incidents
    op.create_table(
        'incidents',
        sa.Column('id', sa.String(255), primary_key=True),  # PagerDuty incident ID
        sa.Column('service', sa.String(255), nullable=False, index=True),
        sa.Column('title', sa.String(500), nullable=True),
        sa.Column('severity', sa.String(50), nullable=True),
        sa.Column('started_at', sa.DateTime, nullable=False, index=True),
        sa.Column('resolved_at', sa.DateTime, nullable=True),
        sa.Column('duration_minutes', sa.Float, nullable=True),
        sa.Column('budget_burn_minutes', sa.Float, nullable=True),  # Budget burn from this incident
        sa.Column('source', sa.String(50), nullable=False, default='pagerduty'),
        sa.Column('extra_data', postgresql.JSONB, nullable=True),
        sa.Column('created_at', sa.DateTime, nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime, nullable=False, server_default=sa.func.now(), onupdate=sa.func.now()),
    )
    
    # Create index for time-range queries
    op.create_index('idx_incidents_service_started', 'incidents', ['service', 'started_at'])


def downgrade() -> None:
    op.drop_table('incidents')
    op.drop_table('deployments')
    op.drop_table('slo_history')
    op.drop_table('error_budgets')
    op.drop_table('slos')
