"""Initial schema

Revision ID: 001
Revises: 
Create Date: 2026-04-10 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '001'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create enums
    op.execute("CREATE TYPE meeting_type_enum AS ENUM ('pm', 'scrum')")
    op.execute("CREATE TYPE run_type_enum AS ENUM ('pm_backlog', 'scrum_actions')")
    op.execute("CREATE TYPE run_status_enum AS ENUM ('pending', 'running', 'completed', 'failed')")
    op.execute("CREATE TYPE artifact_type_enum AS ENUM ('audio', 'transcript', 'diarization', 'extracted_epics', 'decomposed_backlog', 'scrum_actions')")
    op.execute("CREATE TYPE action_type_enum AS ENUM ('create_task', 'complete_task', 'update_status', 'assign_task', 'add_comment')")
    op.execute("CREATE TYPE execution_status_enum AS ENUM ('pending', 'success', 'failed', 'skipped')")

    # Create meetings table
    op.create_table(
        'meetings',
        sa.Column('id', sa.BigInteger(), nullable=False),
        sa.Column('meeting_uid', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('meeting_type', postgresql.ENUM('pm', 'scrum', name='meeting_type_enum', create_type=False), nullable=False),
        sa.Column('title', sa.Text(), nullable=True),
        sa.Column('meeting_date', sa.Date(), nullable=False),
        sa.Column('started_at', postgresql.TIMESTAMP(timezone=True), nullable=True),
        sa.Column('ended_at', postgresql.TIMESTAMP(timezone=True), nullable=True),
        sa.Column('source_platform', sa.Text(), nullable=False, server_default='google_meet'),
        sa.Column('source_meeting_key', sa.Text(), nullable=True),
        sa.Column('status', sa.Text(), nullable=False, server_default='created'),
        sa.Column('created_at', postgresql.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('updated_at', postgresql.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_meetings_type_date', 'meetings', ['meeting_type', 'meeting_date'])
    op.create_unique_constraint('uq_meetings_meeting_uid', 'meetings', ['meeting_uid'])

    # Create processing_runs table
    op.create_table(
        'processing_runs',
        sa.Column('id', sa.BigInteger(), nullable=False),
        sa.Column('meeting_id', sa.BigInteger(), nullable=False),
        sa.Column('run_number', sa.Integer(), nullable=False),
        sa.Column('run_type', postgresql.ENUM('pm_backlog', 'scrum_actions', name='run_type_enum', create_type=False), nullable=False),
        sa.Column('status', postgresql.ENUM('pending', 'running', 'completed', 'failed', name='run_status_enum', create_type=False), nullable=False, server_default='pending'),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('started_at', postgresql.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('finished_at', postgresql.TIMESTAMP(timezone=True), nullable=True),
        sa.Column('created_at', postgresql.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('updated_at', postgresql.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.ForeignKeyConstraint(['meeting_id'], ['meetings.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('meeting_id', 'run_number', name='uq_meeting_run_number')
    )

    # Create meeting_artifacts table
    op.create_table(
        'meeting_artifacts',
        sa.Column('id', sa.BigInteger(), nullable=False),
        sa.Column('meeting_id', sa.BigInteger(), nullable=False),
        sa.Column('processing_run_id', sa.BigInteger(), nullable=True),
        sa.Column('artifact_type', postgresql.ENUM('audio', 'transcript', 'diarization', 'extracted_epics', 'decomposed_backlog', 'scrum_actions', name='artifact_type_enum', create_type=False), nullable=False),
        sa.Column('file_path', sa.Text(), nullable=True),
        sa.Column('text_content', sa.Text(), nullable=True),
        sa.Column('json_content', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('metadata', postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default='{}'),
        sa.Column('created_at', postgresql.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('updated_at', postgresql.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.ForeignKeyConstraint(['meeting_id'], ['meetings.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['processing_run_id'], ['processing_runs.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_artifacts_meeting_type', 'meeting_artifacts', ['meeting_id', 'artifact_type'])

    # Create users table
    op.create_table(
        'users',
        sa.Column('id', sa.BigInteger(), nullable=False),
        sa.Column('display_name', sa.Text(), nullable=False),
        sa.Column('normalized_name', sa.Text(), nullable=True),
        sa.Column('email', sa.Text(), nullable=True),
        sa.Column('jira_account_id', sa.Text(), nullable=True),
        sa.Column('jira_display_name', sa.Text(), nullable=True),
        sa.Column('created_at', postgresql.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('updated_at', postgresql.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('email', name='uq_users_email'),
        sa.UniqueConstraint('jira_account_id', name='uq_users_jira_account_id')
    )

    # Create epics table
    op.create_table(
        'epics',
        sa.Column('id', sa.BigInteger(), nullable=False),
        sa.Column('meeting_id', sa.BigInteger(), nullable=False),
        sa.Column('processing_run_id', sa.BigInteger(), nullable=False),
        sa.Column('title', sa.Text(), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('business_value', sa.SmallInteger(), nullable=False),
        sa.Column('time_criticality', sa.SmallInteger(), nullable=False),
        sa.Column('risk_reduction', sa.SmallInteger(), nullable=False),
        sa.Column('job_size', sa.SmallInteger(), nullable=False),
        sa.Column('wsjf_score', sa.Numeric(precision=10, scale=2), nullable=False),
        sa.Column('mentioned_features', postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default='[]'),
        sa.Column('priority_rank', sa.Integer(), nullable=True),
        sa.Column('jira_key', sa.String(length=50), nullable=True),
        sa.Column('jira_status', sa.Text(), nullable=True),
        sa.Column('jira_synced_at', postgresql.TIMESTAMP(timezone=True), nullable=True),
        sa.Column('created_at', postgresql.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('updated_at', postgresql.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.CheckConstraint('business_value >= 1 AND business_value <= 10', name='ck_epic_business_value'),
        sa.CheckConstraint('time_criticality >= 1 AND time_criticality <= 10', name='ck_epic_time_criticality'),
        sa.CheckConstraint('risk_reduction >= 1 AND risk_reduction <= 10', name='ck_epic_risk_reduction'),
        sa.CheckConstraint('job_size >= 1 AND job_size <= 10', name='ck_epic_job_size'),
        sa.CheckConstraint('job_size > 0', name='ck_epic_job_size_positive'),
        sa.ForeignKeyConstraint(['meeting_id'], ['meetings.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['processing_run_id'], ['processing_runs.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('jira_key', name='uq_epics_jira_key')
    )

    # Create stories table
    op.create_table(
        'stories',
        sa.Column('id', sa.BigInteger(), nullable=False),
        sa.Column('epic_id', sa.BigInteger(), nullable=False),
        sa.Column('meeting_id', sa.BigInteger(), nullable=False),
        sa.Column('processing_run_id', sa.BigInteger(), nullable=False),
        sa.Column('title', sa.Text(), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('acceptance_criteria', postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default='[]'),
        sa.Column('sequence_no', sa.Integer(), nullable=True),
        sa.Column('jira_key', sa.String(length=50), nullable=True),
        sa.Column('jira_status', sa.Text(), nullable=True),
        sa.Column('jira_synced_at', postgresql.TIMESTAMP(timezone=True), nullable=True),
        sa.Column('created_at', postgresql.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('updated_at', postgresql.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.ForeignKeyConstraint(['epic_id'], ['epics.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['meeting_id'], ['meetings.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['processing_run_id'], ['processing_runs.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('jira_key', name='uq_stories_jira_key')
    )

    # Create tasks table
    op.create_table(
        'tasks',
        sa.Column('id', sa.BigInteger(), nullable=False),
        sa.Column('story_id', sa.BigInteger(), nullable=False),
        sa.Column('meeting_id', sa.BigInteger(), nullable=False),
        sa.Column('processing_run_id', sa.BigInteger(), nullable=False),
        sa.Column('title', sa.Text(), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('estimated_hours', sa.Numeric(precision=6, scale=2), nullable=True),
        sa.Column('assignee_user_id', sa.BigInteger(), nullable=True),
        sa.Column('assignee_raw', sa.Text(), nullable=True),
        sa.Column('jira_key', sa.String(length=50), nullable=True),
        sa.Column('jira_status', sa.Text(), nullable=True),
        sa.Column('jira_synced_at', postgresql.TIMESTAMP(timezone=True), nullable=True),
        sa.Column('created_at', postgresql.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('updated_at', postgresql.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.ForeignKeyConstraint(['assignee_user_id'], ['users.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['meeting_id'], ['meetings.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['processing_run_id'], ['processing_runs.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['story_id'], ['stories.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('jira_key', name='uq_tasks_jira_key')
    )

    # Create scrum_actions table
    op.create_table(
        'scrum_actions',
        sa.Column('id', sa.BigInteger(), nullable=False),
        sa.Column('meeting_id', sa.BigInteger(), nullable=False),
        sa.Column('processing_run_id', sa.BigInteger(), nullable=False),
        sa.Column('action_type', postgresql.ENUM('create_task', 'complete_task', 'update_status', 'assign_task', 'add_comment', name='action_type_enum', create_type=False), nullable=False),
        sa.Column('ticket_key', sa.String(length=50), nullable=True),
        sa.Column('summary', sa.Text(), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('status', sa.Text(), nullable=True),
        sa.Column('assignee_raw', sa.Text(), nullable=True),
        sa.Column('resolved_user_id', sa.BigInteger(), nullable=True),
        sa.Column('comment', sa.Text(), nullable=True),
        sa.Column('execution_status', postgresql.ENUM('pending', 'success', 'failed', 'skipped', name='execution_status_enum', create_type=False), nullable=False, server_default='pending'),
        sa.Column('jira_response', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('created_at', postgresql.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('updated_at', postgresql.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.ForeignKeyConstraint(['meeting_id'], ['meetings.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['processing_run_id'], ['processing_runs.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['resolved_user_id'], ['users.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id')
    )


def downgrade() -> None:
    # Drop tables in reverse order
    op.drop_table('scrum_actions')
    op.drop_table('tasks')
    op.drop_table('stories')
    op.drop_table('epics')
    op.drop_table('users')
    op.drop_table('meeting_artifacts')
    op.drop_table('processing_runs')
    op.drop_table('meetings')
    
    # Drop enums
    op.execute("DROP TYPE IF EXISTS execution_status_enum")
    op.execute("DROP TYPE IF EXISTS action_type_enum")
    op.execute("DROP TYPE IF EXISTS artifact_type_enum")
    op.execute("DROP TYPE IF EXISTS run_status_enum")
    op.execute("DROP TYPE IF EXISTS run_type_enum")
    op.execute("DROP TYPE IF EXISTS meeting_type_enum")
