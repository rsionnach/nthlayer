"""Initial schema

Revision ID: 001
Revises: 
Create Date: 2025-11-03

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '001'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'idempotency_keys',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('team_id', sa.String(length=255), nullable=False),
        sa.Column('idem_key', sa.String(length=255), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('team_id', 'idem_key', name='uq_team_idem')
    )
    op.create_index('idx_idem_key', 'idempotency_keys', ['idem_key'])
    
    op.create_table(
        'runs',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('job_id', sa.String(length=255), nullable=False),
        sa.Column('type', sa.String(length=100), nullable=False),
        sa.Column('requested_by', sa.String(length=255), nullable=True),
        sa.Column('status', sa.String(length=50), nullable=False),
        sa.Column('started_at', sa.Float(), nullable=True),
        sa.Column('finished_at', sa.Float(), nullable=True),
        sa.Column('idempotency_key', sa.String(length=255), nullable=True),
        sa.Column('outcome', sa.String(length=100), nullable=True),
        sa.Column('failure_reason', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('job_id')
    )
    op.create_index('idx_runs_job_id', 'runs', ['job_id'], unique=True)
    op.create_index('idx_runs_status', 'runs', ['status'])
    op.create_index('idx_runs_idem_key', 'runs', ['idempotency_key'])
    op.create_index('idx_runs_status_created', 'runs', ['status', 'created_at'])
    
    op.create_table(
        'findings',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('run_id', sa.String(length=255), nullable=False),
        sa.Column('entity_ref', sa.String(length=500), nullable=False),
        sa.Column('before_state', sa.JSON(), nullable=True),
        sa.Column('after_state', sa.JSON(), nullable=True),
        sa.Column('action', sa.String(length=100), nullable=False),
        sa.Column('api_calls', sa.JSON(), nullable=False),
        sa.Column('outcome', sa.String(length=100), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('idx_findings_run_id', 'findings', ['run_id'])
    op.create_index('idx_findings_run_entity', 'findings', ['run_id', 'entity_ref'])


def downgrade() -> None:
    op.drop_index('idx_findings_run_entity', table_name='findings')
    op.drop_index('idx_findings_run_id', table_name='findings')
    op.drop_table('findings')
    
    op.drop_index('idx_runs_status_created', table_name='runs')
    op.drop_index('idx_runs_idem_key', table_name='runs')
    op.drop_index('idx_runs_status', table_name='runs')
    op.drop_index('idx_runs_job_id', table_name='runs')
    op.drop_table('runs')
    
    op.drop_index('idx_idem_key', table_name='idempotency_keys')
    op.drop_table('idempotency_keys')
