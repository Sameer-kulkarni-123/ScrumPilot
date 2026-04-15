"""Single company MVP and Telegram integration

Revision ID: 002
Revises: 001
Create Date: 2026-04-12 12:00:00.000000

This migration extends the ScrumPilot database schema from 8 base tables to a
production-ready single-company MVP with Telegram bot integration.

Changes:
- 25 new tables across 4 modules (Auth/RBAC, Teams, Workflow/Planning/Audit/Settings, Telegram)
- 1 table (users) extended with 19 columns (authentication, RBAC, Telegram)
- 6 views for common queries
- 7 PostgreSQL functions for Telegram operations
- Seed data: 5 roles, 25 permissions, 15 system settings

This migration is purely additive - no destructive changes to base schema.
"""
from typing import Sequence, Union
from datetime import datetime

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '002'
down_revision: Union[str, None] = '001'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """
    Upgrade to migration 002: Single Company MVP + Telegram Integration
    
    Execution order respects foreign key dependencies:
    1. RBAC tables (roles, permissions, role_permissions)
    2. Teams tables (teams)
    3. Users table extensions (19 new columns)
    4. Auth tables (user_sessions)
    5. Teams mapping (team_members)
    6. Workflow tables (approval_requests, approval_history)
    7. Sprint tables (sprints, sprint_stories, sprint_assignments, sprint_risks, sprint_dependencies)
    8. Logging tables (activity_logs, audit_trail)
    9. Notification tables (notifications, notification_preferences)
    10. Settings tables (system_settings, user_preferences)
    11. Error/File tables (error_logs, file_storage)
    12. Telegram tables (4 tables, no FKs to users)
    13. Views (6 views)
    14. Functions (7 functions)
    15. Seed data (roles, permissions, settings)
    """
    
    # ========================================================================
    # Phase 1: RBAC Tables
    # ========================================================================
    
    # Create roles table
    op.create_table(
        'roles',
        sa.Column('role_id', sa.Integer(), nullable=False, autoincrement=True),
        sa.Column('role_name', sa.String(length=50), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('is_system_role', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('created_at', postgresql.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('updated_at', postgresql.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.PrimaryKeyConstraint('role_id'),
        sa.UniqueConstraint('role_name', name='uq_roles_role_name')
    )
    
    # Create permissions table
    op.create_table(
        'permissions',
        sa.Column('permission_id', sa.Integer(), nullable=False, autoincrement=True),
        sa.Column('permission_name', sa.String(length=100), nullable=False),
        sa.Column('resource', sa.String(length=50), nullable=False),
        sa.Column('action', sa.String(length=50), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('created_at', postgresql.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.PrimaryKeyConstraint('permission_id'),
        sa.UniqueConstraint('permission_name', name='uq_permissions_permission_name')
    )
    
    # Create role_permissions junction table
    op.create_table(
        'role_permissions',
        sa.Column('role_id', sa.Integer(), nullable=False),
        sa.Column('permission_id', sa.Integer(), nullable=False),
        sa.Column('granted_at', postgresql.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.ForeignKeyConstraint(['role_id'], ['roles.role_id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['permission_id'], ['permissions.permission_id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('role_id', 'permission_id')
    )
    op.create_index('idx_role_permissions_role', 'role_permissions', ['role_id'])
    
    # ========================================================================
    # Phase 2: Teams Tables
    # ========================================================================
    
    # Create teams table
    op.create_table(
        'teams',
        sa.Column('team_id', sa.Integer(), nullable=False, autoincrement=True),
        sa.Column('team_name', sa.String(length=100), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('team_lead_id', sa.BigInteger(), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('created_at', postgresql.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('updated_at', postgresql.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.ForeignKeyConstraint(['team_lead_id'], ['users.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('team_id'),
        sa.UniqueConstraint('team_name', name='uq_teams_team_name')
    )
    op.create_index('idx_teams_active', 'teams', ['is_active'])
    
    # ========================================================================
    # Phase 3: Extend Users Table
    # ========================================================================
    
    # Add authentication columns (9)
    op.add_column('users', sa.Column('password_hash', sa.String(length=255), nullable=True))
    op.add_column('users', sa.Column('password_salt', sa.String(length=255), nullable=True))
    op.add_column('users', sa.Column('last_login', postgresql.TIMESTAMP(timezone=True), nullable=True))
    op.add_column('users', sa.Column('login_count', sa.Integer(), nullable=False, server_default='0'))
    op.add_column('users', sa.Column('account_status', sa.String(length=20), nullable=False, server_default='active'))
    op.add_column('users', sa.Column('email_verified', sa.Boolean(), nullable=False, server_default='false'))
    op.add_column('users', sa.Column('verification_token', sa.String(length=255), nullable=True))
    op.add_column('users', sa.Column('reset_token', sa.String(length=255), nullable=True))
    op.add_column('users', sa.Column('reset_token_expires', postgresql.TIMESTAMP(timezone=True), nullable=True))
    
    # Add RBAC column (1)
    op.add_column('users', sa.Column('role_id', sa.Integer(), nullable=True))
    op.create_foreign_key('fk_users_role_id', 'users', 'roles', ['role_id'], ['role_id'], ondelete='SET NULL')
    op.create_index('idx_users_role', 'users', ['role_id'])
    
    # Add Telegram columns (9)
    op.add_column('users', sa.Column('telegram_user_id', sa.BigInteger(), nullable=True))
    op.add_column('users', sa.Column('telegram_chat_id', sa.BigInteger(), nullable=True))
    op.add_column('users', sa.Column('telegram_username', sa.String(length=100), nullable=True))
    op.add_column('users', sa.Column('telegram_first_name', sa.String(length=100), nullable=True))
    op.add_column('users', sa.Column('telegram_last_name', sa.String(length=100), nullable=True))
    op.add_column('users', sa.Column('telegram_language_code', sa.String(length=10), nullable=True))
    op.add_column('users', sa.Column('telegram_is_bot', sa.Boolean(), nullable=False, server_default='false'))
    op.add_column('users', sa.Column('telegram_linked_at', postgresql.TIMESTAMP(timezone=True), nullable=True))
    op.add_column('users', sa.Column('telegram_notifications_enabled', sa.Boolean(), nullable=False, server_default='true'))
    op.create_unique_constraint('uq_users_telegram_user_id', 'users', ['telegram_user_id'])
    op.create_index('idx_users_telegram_id', 'users', ['telegram_user_id'])
    
    # ========================================================================
    # Phase 4: Auth Tables
    # ========================================================================
    
    # Create user_sessions table
    op.create_table(
        'user_sessions',
        sa.Column('session_id', sa.String(length=255), nullable=False),
        sa.Column('user_id', sa.BigInteger(), nullable=False),
        sa.Column('created_at', postgresql.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('expires_at', postgresql.TIMESTAMP(timezone=True), nullable=False),
        sa.Column('ip_address', sa.String(length=45), nullable=True),
        sa.Column('user_agent', sa.Text(), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('last_activity', postgresql.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('session_id')
    )
    op.create_index('idx_sessions_user_id', 'user_sessions', ['user_id'])
    op.create_index('idx_sessions_expires', 'user_sessions', ['expires_at'])
    
    # ========================================================================
    # Phase 5: Teams Mapping
    # ========================================================================
    
    # Create team_members junction table
    op.create_table(
        'team_members',
        sa.Column('team_id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.BigInteger(), nullable=False),
        sa.Column('role_in_team', sa.String(length=50), nullable=True),
        sa.Column('joined_at', postgresql.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.ForeignKeyConstraint(['team_id'], ['teams.team_id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('team_id', 'user_id')
    )
    op.create_index('idx_team_members_team', 'team_members', ['team_id'])
    op.create_index('idx_team_members_user', 'team_members', ['user_id'])

    
    # ========================================================================
    # Phase 6: Approval Workflow Tables
    # ========================================================================
    
    # Create approval_requests table
    op.create_table(
        'approval_requests',
        sa.Column('approval_id', sa.Integer(), nullable=False, autoincrement=True),
        sa.Column('request_type', sa.String(length=50), nullable=False),
        sa.Column('entity_type', sa.String(length=50), nullable=False),
        sa.Column('entity_id', sa.BigInteger(), nullable=False),
        sa.Column('requested_by', sa.BigInteger(), nullable=True),
        sa.Column('assigned_to', sa.BigInteger(), nullable=True),
        sa.Column('status', sa.String(length=20), nullable=False, server_default='pending'),
        sa.Column('priority', sa.String(length=20), nullable=False, server_default='normal'),
        sa.Column('request_data', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('original_data', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('approved_data', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('rejection_reason', sa.Text(), nullable=True),
        sa.Column('created_at', postgresql.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('reviewed_at', postgresql.TIMESTAMP(timezone=True), nullable=True),
        sa.Column('expires_at', postgresql.TIMESTAMP(timezone=True), nullable=True),
        sa.CheckConstraint("status IN ('pending', 'approved', 'rejected', 'expired')", name='ck_approval_requests_status'),
        sa.ForeignKeyConstraint(['requested_by'], ['users.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['assigned_to'], ['users.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('approval_id')
    )
    op.create_index('idx_approvals_status', 'approval_requests', ['status'])
    op.create_index('idx_approvals_assigned', 'approval_requests', ['assigned_to'])
    op.create_index('idx_approvals_type', 'approval_requests', ['request_type'])
    
    # Create approval_history table
    op.create_table(
        'approval_history',
        sa.Column('history_id', sa.Integer(), nullable=False, autoincrement=True),
        sa.Column('approval_id', sa.Integer(), nullable=False),
        sa.Column('action', sa.String(length=50), nullable=False),
        sa.Column('performed_by', sa.BigInteger(), nullable=True),
        sa.Column('comment', sa.Text(), nullable=True),
        sa.Column('changes', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('created_at', postgresql.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.ForeignKeyConstraint(['approval_id'], ['approval_requests.approval_id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['performed_by'], ['users.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('history_id')
    )
    op.create_index('idx_approval_history_approval', 'approval_history', ['approval_id'])
    
    # ========================================================================
    # Phase 7: Sprint Planning Tables
    # ========================================================================
    
    # Create sprints table
    op.create_table(
        'sprints',
        sa.Column('sprint_id', sa.Integer(), nullable=False, autoincrement=True),
        sa.Column('sprint_number', sa.Integer(), nullable=True),
        sa.Column('sprint_name', sa.String(length=100), nullable=False),
        sa.Column('sprint_goal', sa.Text(), nullable=True),
        sa.Column('start_date', sa.Date(), nullable=False),
        sa.Column('end_date', sa.Date(), nullable=False),
        sa.Column('duration_weeks', sa.Integer(), nullable=True),
        sa.Column('status', sa.String(length=20), nullable=False, server_default='planned'),
        sa.Column('team_capacity_hours', sa.Numeric(precision=10, scale=2), nullable=True),
        sa.Column('team_size', sa.Integer(), nullable=True),
        sa.Column('velocity_target', sa.Numeric(precision=10, scale=2), nullable=True),
        sa.Column('velocity_actual', sa.Numeric(precision=10, scale=2), nullable=True),
        sa.Column('team_id', sa.Integer(), nullable=True),
        sa.Column('created_at', postgresql.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('updated_at', postgresql.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('created_by', sa.BigInteger(), nullable=True),
        sa.CheckConstraint("status IN ('planned', 'active', 'completed', 'cancelled')", name='ck_sprints_status'),
        sa.ForeignKeyConstraint(['team_id'], ['teams.team_id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['created_by'], ['users.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('sprint_id')
    )
    op.create_index('idx_sprints_status', 'sprints', ['status'])
    op.create_index('idx_sprints_dates', 'sprints', ['start_date', 'end_date'])
    op.create_index('idx_sprints_team', 'sprints', ['team_id'])
    
    # Create sprint_stories junction table
    op.create_table(
        'sprint_stories',
        sa.Column('sprint_id', sa.Integer(), nullable=False),
        sa.Column('story_id', sa.BigInteger(), nullable=False),
        sa.Column('committed_at', postgresql.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('committed_by', sa.BigInteger(), nullable=True),
        sa.Column('story_points', sa.Integer(), nullable=True),
        sa.Column('estimated_hours', sa.Numeric(precision=10, scale=2), nullable=True),
        sa.Column('actual_hours', sa.Numeric(precision=10, scale=2), nullable=True),
        sa.Column('status', sa.String(length=20), nullable=True),
        sa.ForeignKeyConstraint(['sprint_id'], ['sprints.sprint_id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['story_id'], ['stories.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['committed_by'], ['users.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('sprint_id', 'story_id')
    )
    op.create_index('idx_sprint_stories_sprint', 'sprint_stories', ['sprint_id'])
    op.create_index('idx_sprint_stories_story', 'sprint_stories', ['story_id'])
    
    # Create sprint_assignments table
    op.create_table(
        'sprint_assignments',
        sa.Column('assignment_id', sa.Integer(), nullable=False, autoincrement=True),
        sa.Column('sprint_id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.BigInteger(), nullable=False),
        sa.Column('story_id', sa.BigInteger(), nullable=True),
        sa.Column('task_id', sa.BigInteger(), nullable=True),
        sa.Column('estimated_hours', sa.Numeric(precision=10, scale=2), nullable=True),
        sa.Column('actual_hours', sa.Numeric(precision=10, scale=2), nullable=True),
        sa.Column('assigned_at', postgresql.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('assigned_by', sa.BigInteger(), nullable=True),
        sa.ForeignKeyConstraint(['sprint_id'], ['sprints.sprint_id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['story_id'], ['stories.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['task_id'], ['tasks.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['assigned_by'], ['users.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('assignment_id')
    )
    op.create_index('idx_sprint_assignments_sprint', 'sprint_assignments', ['sprint_id'])
    op.create_index('idx_sprint_assignments_user', 'sprint_assignments', ['user_id'])
    
    # Create sprint_risks table
    op.create_table(
        'sprint_risks',
        sa.Column('risk_id', sa.Integer(), nullable=False, autoincrement=True),
        sa.Column('sprint_id', sa.Integer(), nullable=False),
        sa.Column('risk_description', sa.Text(), nullable=False),
        sa.Column('severity', sa.String(length=20), nullable=False),
        sa.Column('status', sa.String(length=20), nullable=False, server_default='open'),
        sa.Column('mitigation_plan', sa.Text(), nullable=True),
        sa.Column('identified_by', sa.BigInteger(), nullable=True),
        sa.Column('identified_at', postgresql.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('resolved_at', postgresql.TIMESTAMP(timezone=True), nullable=True),
        sa.CheckConstraint("severity IN ('low', 'medium', 'high', 'critical')", name='ck_sprint_risks_severity'),
        sa.CheckConstraint("status IN ('open', 'mitigated', 'resolved', 'accepted')", name='ck_sprint_risks_status'),
        sa.ForeignKeyConstraint(['sprint_id'], ['sprints.sprint_id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['identified_by'], ['users.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('risk_id')
    )
    op.create_index('idx_sprint_risks_sprint', 'sprint_risks', ['sprint_id'])
    
    # Create sprint_dependencies table
    op.create_table(
        'sprint_dependencies',
        sa.Column('dependency_id', sa.Integer(), nullable=False, autoincrement=True),
        sa.Column('sprint_id', sa.Integer(), nullable=False),
        sa.Column('dependency_description', sa.Text(), nullable=False),
        sa.Column('dependency_type', sa.String(length=50), nullable=True),
        sa.Column('external_team', sa.String(length=100), nullable=True),
        sa.Column('status', sa.String(length=20), nullable=False, server_default='pending'),
        sa.Column('due_date', sa.Date(), nullable=True),
        sa.Column('identified_by', sa.BigInteger(), nullable=True),
        sa.Column('identified_at', postgresql.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('resolved_at', postgresql.TIMESTAMP(timezone=True), nullable=True),
        sa.CheckConstraint("status IN ('pending', 'in_progress', 'resolved', 'blocked')", name='ck_sprint_dependencies_status'),
        sa.ForeignKeyConstraint(['sprint_id'], ['sprints.sprint_id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['identified_by'], ['users.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('dependency_id')
    )
    op.create_index('idx_sprint_dependencies_sprint', 'sprint_dependencies', ['sprint_id'])

    
    # ========================================================================
    # Phase 8: Logging Tables
    # ========================================================================
    
    # Create activity_logs table
    op.create_table(
        'activity_logs',
        sa.Column('log_id', sa.BigInteger(), nullable=False, autoincrement=True),
        sa.Column('user_id', sa.BigInteger(), nullable=True),
        sa.Column('action', sa.String(length=100), nullable=False),
        sa.Column('entity_type', sa.String(length=50), nullable=True),
        sa.Column('entity_id', sa.BigInteger(), nullable=True),
        sa.Column('details', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('ip_address', sa.String(length=45), nullable=True),
        sa.Column('user_agent', sa.Text(), nullable=True),
        sa.Column('created_at', postgresql.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('log_id')
    )
    op.create_index('idx_activity_logs_user', 'activity_logs', ['user_id'])
    op.create_index('idx_activity_logs_created', 'activity_logs', ['created_at'])
    op.create_index('idx_activity_logs_entity', 'activity_logs', ['entity_type', 'entity_id'])
    
    # Create audit_trail table
    op.create_table(
        'audit_trail',
        sa.Column('audit_id', sa.BigInteger(), nullable=False, autoincrement=True),
        sa.Column('table_name', sa.String(length=100), nullable=False),
        sa.Column('record_id', sa.BigInteger(), nullable=False),
        sa.Column('operation', sa.String(length=10), nullable=False),
        sa.Column('old_values', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('new_values', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('changed_by', sa.BigInteger(), nullable=True),
        sa.Column('changed_at', postgresql.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.CheckConstraint("operation IN ('INSERT', 'UPDATE', 'DELETE')", name='ck_audit_trail_operation'),
        sa.ForeignKeyConstraint(['changed_by'], ['users.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('audit_id')
    )
    op.create_index('idx_audit_trail_table', 'audit_trail', ['table_name', 'record_id'])
    op.create_index('idx_audit_trail_changed', 'audit_trail', ['changed_at'])
    
    # ========================================================================
    # Phase 9: Notification Tables
    # ========================================================================
    
    # Create notifications table
    op.create_table(
        'notifications',
        sa.Column('notification_id', sa.Integer(), nullable=False, autoincrement=True),
        sa.Column('user_id', sa.BigInteger(), nullable=False),
        sa.Column('notification_type', sa.String(length=50), nullable=False),
        sa.Column('title', sa.String(length=200), nullable=False),
        sa.Column('message', sa.Text(), nullable=False),
        sa.Column('entity_type', sa.String(length=50), nullable=True),
        sa.Column('entity_id', sa.BigInteger(), nullable=True),
        sa.Column('priority', sa.String(length=20), nullable=False, server_default='normal'),
        sa.Column('is_read', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('read_at', postgresql.TIMESTAMP(timezone=True), nullable=True),
        sa.Column('created_at', postgresql.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('expires_at', postgresql.TIMESTAMP(timezone=True), nullable=True),
        sa.CheckConstraint("priority IN ('low', 'normal', 'high', 'urgent')", name='ck_notifications_priority'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('notification_id')
    )
    op.create_index('idx_notifications_user', 'notifications', ['user_id'])
    op.create_index('idx_notifications_read', 'notifications', ['is_read'])
    op.create_index('idx_notifications_created', 'notifications', ['created_at'])
    
    # Create notification_preferences table
    op.create_table(
        'notification_preferences',
        sa.Column('user_id', sa.BigInteger(), nullable=False),
        sa.Column('notification_type', sa.String(length=50), nullable=False),
        sa.Column('email_enabled', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('in_app_enabled', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('created_at', postgresql.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('updated_at', postgresql.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('user_id', 'notification_type')
    )
    
    # ========================================================================
    # Phase 10: Settings Tables
    # ========================================================================
    
    # Create system_settings table
    op.create_table(
        'system_settings',
        sa.Column('setting_key', sa.String(length=100), nullable=False),
        sa.Column('setting_value', sa.Text(), nullable=True),
        sa.Column('setting_type', sa.String(length=20), nullable=False, server_default='string'),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('is_public', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('updated_by', sa.BigInteger(), nullable=True),
        sa.Column('updated_at', postgresql.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.CheckConstraint("setting_type IN ('string', 'number', 'boolean', 'json')", name='ck_system_settings_type'),
        sa.ForeignKeyConstraint(['updated_by'], ['users.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('setting_key')
    )
    
    # Create user_preferences table
    op.create_table(
        'user_preferences',
        sa.Column('user_id', sa.BigInteger(), nullable=False),
        sa.Column('preference_key', sa.String(length=100), nullable=False),
        sa.Column('preference_value', sa.Text(), nullable=True),
        sa.Column('updated_at', postgresql.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('user_id', 'preference_key')
    )
    op.create_index('idx_user_preferences_user', 'user_preferences', ['user_id'])
    
    # ========================================================================
    # Phase 11: Error and File Storage Tables
    # ========================================================================
    
    # Create error_logs table
    op.create_table(
        'error_logs',
        sa.Column('error_id', sa.BigInteger(), nullable=False, autoincrement=True),
        sa.Column('error_type', sa.String(length=100), nullable=False),
        sa.Column('error_message', sa.Text(), nullable=False),
        sa.Column('stack_trace', sa.Text(), nullable=True),
        sa.Column('severity', sa.String(length=20), nullable=False, server_default='error'),
        sa.Column('user_id', sa.BigInteger(), nullable=True),
        sa.Column('request_path', sa.Text(), nullable=True),
        sa.Column('request_method', sa.String(length=10), nullable=True),
        sa.Column('request_data', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('ip_address', sa.String(length=45), nullable=True),
        sa.Column('user_agent', sa.Text(), nullable=True),
        sa.Column('resolved', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('resolved_by', sa.BigInteger(), nullable=True),
        sa.Column('resolved_at', postgresql.TIMESTAMP(timezone=True), nullable=True),
        sa.Column('created_at', postgresql.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.CheckConstraint("severity IN ('warning', 'error', 'critical')", name='ck_error_logs_severity'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['resolved_by'], ['users.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('error_id')
    )
    op.create_index('idx_error_logs_created', 'error_logs', ['created_at'])
    op.create_index('idx_error_logs_severity', 'error_logs', ['severity'])
    op.create_index('idx_error_logs_resolved', 'error_logs', ['resolved'])
    op.create_index('idx_error_logs_type', 'error_logs', ['error_type'])
    
    # Create file_storage table
    op.create_table(
        'file_storage',
        sa.Column('file_id', sa.Integer(), nullable=False, autoincrement=True),
        sa.Column('file_name', sa.String(length=255), nullable=False),
        sa.Column('file_path', sa.Text(), nullable=False),
        sa.Column('file_type', sa.String(length=50), nullable=True),
        sa.Column('file_size', sa.BigInteger(), nullable=True),
        sa.Column('mime_type', sa.String(length=100), nullable=True),
        sa.Column('entity_type', sa.String(length=50), nullable=True),
        sa.Column('entity_id', sa.BigInteger(), nullable=True),
        sa.Column('uploaded_by', sa.BigInteger(), nullable=True),
        sa.Column('uploaded_at', postgresql.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('is_deleted', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('deleted_at', postgresql.TIMESTAMP(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['uploaded_by'], ['users.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('file_id')
    )
    op.create_index('idx_file_storage_entity', 'file_storage', ['entity_type', 'entity_id'])
    op.create_index('idx_file_storage_uploaded', 'file_storage', ['uploaded_by'])
    op.create_index('idx_file_storage_deleted', 'file_storage', ['is_deleted'])

    
    # ========================================================================
    # Phase 12: Telegram Tables
    # ========================================================================
    
    # Create telegram_chat_states table
    op.create_table(
        'telegram_chat_states',
        sa.Column('state_id', sa.Integer(), nullable=False, autoincrement=True),
        sa.Column('telegram_user_id', sa.BigInteger(), nullable=False),
        sa.Column('telegram_chat_id', sa.BigInteger(), nullable=False),
        sa.Column('current_state', sa.String(length=50), nullable=True),
        sa.Column('state_data', postgresql.JSONB(astext_type=sa.Text()), nullable=True, server_default='{}'),
        sa.Column('created_at', postgresql.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('updated_at', postgresql.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('expires_at', postgresql.TIMESTAMP(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint('state_id'),
        sa.UniqueConstraint('telegram_user_id', 'telegram_chat_id', name='uq_telegram_chat_states_user_chat')
    )
    op.create_index('idx_chat_states_user', 'telegram_chat_states', ['telegram_user_id'])
    op.create_index('idx_chat_states_expires', 'telegram_chat_states', ['expires_at'])
    
    # Create telegram_command_history table
    op.create_table(
        'telegram_command_history',
        sa.Column('command_id', sa.BigInteger(), nullable=False, autoincrement=True),
        sa.Column('telegram_user_id', sa.BigInteger(), nullable=False),
        sa.Column('telegram_chat_id', sa.BigInteger(), nullable=False),
        sa.Column('telegram_message_id', sa.BigInteger(), nullable=True),
        sa.Column('command', sa.String(length=100), nullable=False),
        sa.Column('command_args', sa.Text(), nullable=True),
        sa.Column('response_text', sa.Text(), nullable=True),
        sa.Column('response_message_id', sa.BigInteger(), nullable=True),
        sa.Column('execution_time_ms', sa.Integer(), nullable=True),
        sa.Column('success', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('created_at', postgresql.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.PrimaryKeyConstraint('command_id')
    )
    op.create_index('idx_command_history_user', 'telegram_command_history', ['telegram_user_id'])
    op.create_index('idx_command_history_created', 'telegram_command_history', ['created_at'])
    op.create_index('idx_command_history_command', 'telegram_command_history', ['command'])
    op.create_index('idx_command_history_success', 'telegram_command_history', ['success'])
    
    # Create telegram_message_queue table
    op.create_table(
        'telegram_message_queue',
        sa.Column('queue_id', sa.BigInteger(), nullable=False, autoincrement=True),
        sa.Column('telegram_user_id', sa.BigInteger(), nullable=False),
        sa.Column('telegram_chat_id', sa.BigInteger(), nullable=False),
        sa.Column('message_type', sa.String(length=50), nullable=False),
        sa.Column('message_text', sa.Text(), nullable=False),
        sa.Column('parse_mode', sa.String(length=20), nullable=True, server_default='Markdown'),
        sa.Column('reply_markup', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('priority', sa.Integer(), nullable=False, server_default='5'),
        sa.Column('status', sa.String(length=20), nullable=False, server_default='pending'),
        sa.Column('retry_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('max_retries', sa.Integer(), nullable=False, server_default='3'),
        sa.Column('scheduled_at', postgresql.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('sent_at', postgresql.TIMESTAMP(timezone=True), nullable=True),
        sa.Column('telegram_message_id', sa.BigInteger(), nullable=True),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('created_at', postgresql.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.CheckConstraint("status IN ('pending', 'sent', 'failed', 'cancelled')", name='ck_telegram_message_queue_status'),
        sa.CheckConstraint("priority BETWEEN 1 AND 10", name='ck_telegram_message_queue_priority'),
        sa.PrimaryKeyConstraint('queue_id')
    )
    op.create_index('idx_message_queue_status', 'telegram_message_queue', ['status'])
    op.create_index('idx_message_queue_scheduled', 'telegram_message_queue', ['scheduled_at'])
    op.create_index('idx_message_queue_user', 'telegram_message_queue', ['telegram_user_id'])
    op.create_index('idx_message_queue_priority', 'telegram_message_queue', [sa.text('priority DESC'), sa.text('scheduled_at ASC')])
    
    # Create telegram_webhook_events table
    op.create_table(
        'telegram_webhook_events',
        sa.Column('event_id', sa.BigInteger(), nullable=False, autoincrement=True),
        sa.Column('update_id', sa.BigInteger(), nullable=False),
        sa.Column('event_type', sa.String(length=50), nullable=True),
        sa.Column('telegram_user_id', sa.BigInteger(), nullable=True),
        sa.Column('telegram_chat_id', sa.BigInteger(), nullable=True),
        sa.Column('message_data', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('processed', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('processed_at', postgresql.TIMESTAMP(timezone=True), nullable=True),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('created_at', postgresql.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.PrimaryKeyConstraint('event_id'),
        sa.UniqueConstraint('update_id', name='uq_telegram_webhook_events_update_id')
    )
    op.create_index('idx_webhook_events_processed', 'telegram_webhook_events', ['processed'])
    op.create_index('idx_webhook_events_created', 'telegram_webhook_events', ['created_at'])
    op.create_index('idx_webhook_events_type', 'telegram_webhook_events', ['event_type'])
    op.create_index('idx_webhook_events_user', 'telegram_webhook_events', ['telegram_user_id'])

    
    # ========================================================================
    # Phase 13: Database Views
    # ========================================================================
    
    # Create active_sprints_view
    op.execute("""
        CREATE OR REPLACE VIEW active_sprints_view AS
        SELECT 
            s.sprint_id, s.sprint_name, s.sprint_goal, s.start_date, s.end_date, s.status,
            s.team_capacity_hours, s.velocity_target, t.team_name,
            u.display_name AS created_by_name,
            COUNT(DISTINCT ss.story_id) AS story_count,
            SUM(ss.story_points) AS total_story_points
        FROM sprints s
        LEFT JOIN teams t ON s.team_id = t.team_id
        LEFT JOIN users u ON s.created_by = u.id
        LEFT JOIN sprint_stories ss ON s.sprint_id = ss.sprint_id
        WHERE s.status = 'active'
        GROUP BY s.sprint_id, t.team_name, u.display_name;
    """)
    
    # Create pending_approvals_view
    op.execute("""
        CREATE OR REPLACE VIEW pending_approvals_view AS
        SELECT 
            ar.approval_id, ar.request_type, ar.entity_type, ar.status, ar.priority,
            u1.display_name AS requested_by_name, u1.email AS requested_by_email,
            u2.display_name AS assigned_to_name, u2.email AS assigned_to_email,
            ar.created_at, ar.expires_at
        FROM approval_requests ar
        LEFT JOIN users u1 ON ar.requested_by = u1.id
        LEFT JOIN users u2 ON ar.assigned_to = u2.id
        WHERE ar.status = 'pending'
        ORDER BY ar.priority DESC, ar.created_at ASC;
    """)
    
    # Create user_activity_summary view
    op.execute("""
        CREATE OR REPLACE VIEW user_activity_summary AS
        SELECT 
            u.id AS user_id, u.display_name, u.email, r.role_name,
            u.last_login, u.login_count,
            COUNT(DISTINCT al.log_id) AS activity_count,
            MAX(al.created_at) AS last_activity
        FROM users u
        LEFT JOIN roles r ON u.role_id = r.role_id
        LEFT JOIN activity_logs al ON u.id = al.user_id
        GROUP BY u.id, u.display_name, u.email, r.role_name, u.last_login, u.login_count;
    """)
    
    # Create telegram_pending_approvals view
    op.execute("""
        CREATE OR REPLACE VIEW telegram_pending_approvals AS
        SELECT 
            u.telegram_user_id, u.telegram_chat_id, u.display_name,
            ar.approval_id, ar.request_type, ar.entity_type, ar.priority,
            ar.created_at, ar.expires_at
        FROM users u
        INNER JOIN approval_requests ar ON u.id = ar.assigned_to
        WHERE u.telegram_user_id IS NOT NULL
          AND ar.status = 'pending'
          AND u.telegram_notifications_enabled = TRUE
        ORDER BY ar.priority DESC, ar.created_at ASC;
    """)
    
    # Create telegram_queue_status view
    op.execute("""
        CREATE OR REPLACE VIEW telegram_queue_status AS
        SELECT 
            status,
            COUNT(*) AS message_count,
            MIN(scheduled_at) AS oldest_message,
            MAX(scheduled_at) AS newest_message
        FROM telegram_message_queue
        WHERE status IN ('pending', 'failed')
        GROUP BY status;
    """)
    
    # Create telegram_bot_stats view
    op.execute("""
        CREATE OR REPLACE VIEW telegram_bot_stats AS
        SELECT 
            DATE(created_at) AS date, command,
            COUNT(*) AS usage_count,
            AVG(execution_time_ms) AS avg_execution_time_ms,
            SUM(CASE WHEN success THEN 1 ELSE 0 END) AS success_count,
            SUM(CASE WHEN NOT success THEN 1 ELSE 0 END) AS error_count
        FROM telegram_command_history
        GROUP BY DATE(created_at), command
        ORDER BY date DESC, usage_count DESC;
    """)
    
    # ========================================================================
    # Phase 14: PostgreSQL Functions
    # ========================================================================
    
    # Create get_telegram_chat_state function
    op.execute("""
        CREATE OR REPLACE FUNCTION get_telegram_chat_state(
            p_telegram_user_id BIGINT,
            p_telegram_chat_id BIGINT
        )
        RETURNS TABLE (
            state_id INTEGER,
            current_state VARCHAR(50),
            state_data JSONB,
            created_at TIMESTAMP
        ) AS $$
        BEGIN
            RETURN QUERY
            SELECT 
                tcs.state_id, tcs.current_state, tcs.state_data, tcs.created_at
            FROM telegram_chat_states tcs
            WHERE tcs.telegram_user_id = p_telegram_user_id
              AND tcs.telegram_chat_id = p_telegram_chat_id
              AND (tcs.expires_at IS NULL OR tcs.expires_at > CURRENT_TIMESTAMP);
        END;
        $$ LANGUAGE plpgsql;
    """)
    
    # Create update_telegram_chat_state function
    op.execute("""
        CREATE OR REPLACE FUNCTION update_telegram_chat_state(
            p_telegram_user_id BIGINT,
            p_telegram_chat_id BIGINT,
            p_current_state VARCHAR(50),
            p_state_data JSONB DEFAULT '{}'
        )
        RETURNS INTEGER AS $$
        DECLARE
            v_state_id INTEGER;
        BEGIN
            INSERT INTO telegram_chat_states (
                telegram_user_id, telegram_chat_id, current_state, state_data,
                updated_at, expires_at
            ) VALUES (
                p_telegram_user_id, p_telegram_chat_id, p_current_state, p_state_data,
                CURRENT_TIMESTAMP, CURRENT_TIMESTAMP + INTERVAL '10 minutes'
            )
            ON CONFLICT (telegram_user_id, telegram_chat_id)
            DO UPDATE SET
                current_state = p_current_state,
                state_data = p_state_data,
                updated_at = CURRENT_TIMESTAMP,
                expires_at = CURRENT_TIMESTAMP + INTERVAL '10 minutes'
            RETURNING state_id INTO v_state_id;
            
            RETURN v_state_id;
        END;
        $$ LANGUAGE plpgsql;
    """)
    
    # Create clear_telegram_chat_state function
    op.execute("""
        CREATE OR REPLACE FUNCTION clear_telegram_chat_state(
            p_telegram_user_id BIGINT,
            p_telegram_chat_id BIGINT
        )
        RETURNS BOOLEAN AS $$
        BEGIN
            DELETE FROM telegram_chat_states
            WHERE telegram_user_id = p_telegram_user_id
              AND telegram_chat_id = p_telegram_chat_id;
            
            RETURN FOUND;
        END;
        $$ LANGUAGE plpgsql;
    """)
    
    # Create queue_telegram_message function
    op.execute("""
        CREATE OR REPLACE FUNCTION queue_telegram_message(
            p_telegram_user_id BIGINT,
            p_telegram_chat_id BIGINT,
            p_message_type VARCHAR(50),
            p_message_text TEXT,
            p_parse_mode VARCHAR(20) DEFAULT 'Markdown',
            p_reply_markup JSONB DEFAULT NULL,
            p_priority INTEGER DEFAULT 5,
            p_scheduled_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        RETURNS BIGINT AS $$
        DECLARE
            v_queue_id BIGINT;
        BEGIN
            INSERT INTO telegram_message_queue (
                telegram_user_id, telegram_chat_id, message_type, message_text,
                parse_mode, reply_markup, priority, scheduled_at
            ) VALUES (
                p_telegram_user_id, p_telegram_chat_id, p_message_type, p_message_text,
                p_parse_mode, p_reply_markup, p_priority, p_scheduled_at
            )
            RETURNING queue_id INTO v_queue_id;
            
            RETURN v_queue_id;
        END;
        $$ LANGUAGE plpgsql;
    """)
    
    # Create cleanup_expired_telegram_states function
    op.execute("""
        CREATE OR REPLACE FUNCTION cleanup_expired_telegram_states()
        RETURNS INTEGER AS $$
        DECLARE
            v_deleted_count INTEGER;
        BEGIN
            DELETE FROM telegram_chat_states
            WHERE expires_at IS NOT NULL
              AND expires_at < CURRENT_TIMESTAMP;
            
            GET DIAGNOSTICS v_deleted_count = ROW_COUNT;
            RETURN v_deleted_count;
        END;
        $$ LANGUAGE plpgsql;
    """)
    
    # Create cleanup_old_telegram_events function
    op.execute("""
        CREATE OR REPLACE FUNCTION cleanup_old_telegram_events(p_days_to_keep INTEGER DEFAULT 30)
        RETURNS INTEGER AS $$
        DECLARE
            v_deleted_count INTEGER;
        BEGIN
            DELETE FROM telegram_webhook_events
            WHERE created_at < CURRENT_TIMESTAMP - (p_days_to_keep || ' days')::INTERVAL
              AND processed = TRUE;
            
            GET DIAGNOSTICS v_deleted_count = ROW_COUNT;
            RETURN v_deleted_count;
        END;
        $$ LANGUAGE plpgsql;
    """)
    
    # Create cleanup_old_telegram_commands function
    op.execute("""
        CREATE OR REPLACE FUNCTION cleanup_old_telegram_commands(p_days_to_keep INTEGER DEFAULT 90)
        RETURNS INTEGER AS $$
        DECLARE
            v_deleted_count INTEGER;
        BEGIN
            DELETE FROM telegram_command_history
            WHERE created_at < CURRENT_TIMESTAMP - (p_days_to_keep || ' days')::INTERVAL;
            
            GET DIAGNOSTICS v_deleted_count = ROW_COUNT;
            RETURN v_deleted_count;
        END;
        $$ LANGUAGE plpgsql;
    """)

    
    # ========================================================================
    # Phase 15: Seed Data
    # ========================================================================
    
    # Insert 5 default roles
    op.execute("""
        INSERT INTO roles (role_name, description, is_system_role) VALUES
        ('admin', 'System administrator with full access', TRUE),
        ('scrum_master', 'Scrum Master - manages sprints and ceremonies', TRUE),
        ('product_owner', 'Product Owner - manages backlog and priorities', TRUE),
        ('developer', 'Developer - works on stories and tasks', TRUE),
        ('viewer', 'Read-only access to view data', TRUE)
        ON CONFLICT (role_name) DO NOTHING;
    """)
    
    # Insert 25 default permissions
    op.execute("""
        INSERT INTO permissions (permission_name, resource, action, description) VALUES
        ('meetings:view', 'meetings', 'view', 'View meetings'),
        ('meetings:create', 'meetings', 'create', 'Create meetings'),
        ('meetings:edit', 'meetings', 'edit', 'Edit meetings'),
        ('meetings:delete', 'meetings', 'delete', 'Delete meetings'),
        ('epics:view', 'epics', 'view', 'View epics'),
        ('epics:create', 'epics', 'create', 'Create epics'),
        ('epics:edit', 'epics', 'edit', 'Edit epics'),
        ('epics:delete', 'epics', 'delete', 'Delete epics'),
        ('stories:view', 'stories', 'view', 'View stories'),
        ('stories:create', 'stories', 'create', 'Create stories'),
        ('stories:edit', 'stories', 'edit', 'Edit stories'),
        ('stories:delete', 'stories', 'delete', 'Delete stories'),
        ('sprints:view', 'sprints', 'view', 'View sprints'),
        ('sprints:create', 'sprints', 'create', 'Create sprints'),
        ('sprints:edit', 'sprints', 'edit', 'Edit sprints'),
        ('sprints:delete', 'sprints', 'delete', 'Delete sprints'),
        ('approvals:view', 'approvals', 'view', 'View approval requests'),
        ('approvals:approve', 'approvals', 'approve', 'Approve requests'),
        ('approvals:reject', 'approvals', 'reject', 'Reject requests'),
        ('users:view', 'users', 'view', 'View users'),
        ('users:create', 'users', 'create', 'Create users'),
        ('users:edit', 'users', 'edit', 'Edit users'),
        ('users:delete', 'users', 'delete', 'Delete users'),
        ('settings:view', 'settings', 'view', 'View settings'),
        ('settings:edit', 'settings', 'edit', 'Edit settings')
        ON CONFLICT (permission_name) DO NOTHING;
    """)
    
    # Assign all permissions to admin role
    op.execute("""
        INSERT INTO role_permissions (role_id, permission_id)
        SELECT r.role_id, p.permission_id
        FROM roles r
        CROSS JOIN permissions p
        WHERE r.role_name = 'admin'
        ON CONFLICT DO NOTHING;
    """)
    
    # Assign permissions to scrum_master role
    op.execute("""
        INSERT INTO role_permissions (role_id, permission_id)
        SELECT r.role_id, p.permission_id
        FROM roles r
        CROSS JOIN permissions p
        WHERE r.role_name = 'scrum_master'
          AND p.permission_name IN (
              'meetings:view', 'meetings:create', 'meetings:edit',
              'epics:view', 'stories:view', 'stories:edit',
              'sprints:view', 'sprints:create', 'sprints:edit',
              'approvals:view', 'users:view'
          )
        ON CONFLICT DO NOTHING;
    """)
    
    # Assign permissions to product_owner role
    op.execute("""
        INSERT INTO role_permissions (role_id, permission_id)
        SELECT r.role_id, p.permission_id
        FROM roles r
        CROSS JOIN permissions p
        WHERE r.role_name = 'product_owner'
          AND p.permission_name IN (
              'meetings:view', 'epics:view', 'epics:create', 'epics:edit',
              'stories:view', 'stories:create', 'stories:edit',
              'sprints:view', 'approvals:view', 'approvals:approve', 'approvals:reject',
              'users:view'
          )
        ON CONFLICT DO NOTHING;
    """)
    
    # Assign permissions to developer role
    op.execute("""
        INSERT INTO role_permissions (role_id, permission_id)
        SELECT r.role_id, p.permission_id
        FROM roles r
        CROSS JOIN permissions p
        WHERE r.role_name = 'developer'
          AND p.permission_name IN (
              'meetings:view', 'epics:view', 'stories:view', 'stories:edit',
              'sprints:view', 'users:view'
          )
        ON CONFLICT DO NOTHING;
    """)
    
    # Assign permissions to viewer role
    op.execute("""
        INSERT INTO role_permissions (role_id, permission_id)
        SELECT r.role_id, p.permission_id
        FROM roles r
        CROSS JOIN permissions p
        WHERE r.role_name = 'viewer'
          AND p.permission_name IN (
              'meetings:view', 'epics:view', 'stories:view', 'sprints:view', 'users:view'
          )
        ON CONFLICT DO NOTHING;
    """)
    
    # Insert 8 MVP system settings
    op.execute("""
        INSERT INTO system_settings (setting_key, setting_value, setting_type, description, is_public) VALUES
        ('company_name', 'ScrumPilot', 'string', 'Company name', TRUE),
        ('default_sprint_duration', '2', 'number', 'Default sprint duration in weeks', TRUE),
        ('approval_required', 'true', 'boolean', 'Require approval for AI-generated artifacts', TRUE),
        ('jira_integration_enabled', 'true', 'boolean', 'Enable Jira integration', FALSE),
        ('max_file_upload_size', '10485760', 'number', 'Maximum file upload size in bytes (10MB)', TRUE),
        ('session_timeout_minutes', '480', 'number', 'Session timeout in minutes (8 hours)', FALSE),
        ('password_min_length', '8', 'number', 'Minimum password length', FALSE),
        ('notification_retention_days', '30', 'number', 'Notification retention period in days', FALSE)
        ON CONFLICT (setting_key) DO NOTHING;
    """)
    
    # Insert 7 Telegram system settings
    op.execute("""
        INSERT INTO system_settings (setting_key, setting_value, setting_type, description, is_public) VALUES
        ('telegram_bot_token', '', 'string', 'Telegram bot API token', FALSE),
        ('telegram_webhook_url', '', 'string', 'Telegram webhook URL', FALSE),
        ('telegram_notifications_enabled', 'true', 'boolean', 'Enable Telegram notifications', TRUE),
        ('telegram_rate_limit_per_minute', '30', 'number', 'Telegram API rate limit per minute', FALSE),
        ('telegram_command_timeout_minutes', '10', 'number', 'Telegram command timeout in minutes', FALSE),
        ('telegram_max_message_length', '4096', 'number', 'Maximum Telegram message length', FALSE),
        ('telegram_retry_delay_seconds', '5', 'number', 'Telegram retry delay in seconds', FALSE)
        ON CONFLICT (setting_key) DO NOTHING;
    """)


def downgrade() -> None:
    """
    Downgrade from migration 002 to migration 001
    
    CRITICAL: This downgrade is DESTRUCTIVE and will:
    - Drop all 25 new tables
    - Drop all 19 new columns from users table
    - Drop all 6 views
    - Drop all 7 functions
    - Delete all seed data
    
    Execution order respects foreign key dependencies (reverse of upgrade):
    1. Drop functions (7)
    2. Drop views (6)
    3. Drop Telegram tables (4)
    4. Drop Error/File tables (2)
    5. Drop Settings tables (2)
    6. Drop Notification tables (2)
    7. Drop Logging tables (2)
    8. Drop Sprint tables (5)
    9. Drop Workflow tables (2)
    10. Drop Teams mapping (1)
    11. Drop Auth tables (1)
    12. Drop FK constraints involving users.role_id
    13. Drop unique constraints/indexes involving users.telegram_user_id and users.role_id
    14. Drop 19 columns from users table
    15. Drop Teams tables (1)
    16. Drop RBAC tables (3)
    """
    
    # ========================================================================
    # Phase 1: Drop Functions
    # ========================================================================
    
    op.execute("DROP FUNCTION IF EXISTS cleanup_old_telegram_commands(INTEGER)")
    op.execute("DROP FUNCTION IF EXISTS cleanup_old_telegram_events(INTEGER)")
    op.execute("DROP FUNCTION IF EXISTS cleanup_expired_telegram_states()")
    op.execute("DROP FUNCTION IF EXISTS queue_telegram_message(BIGINT, BIGINT, VARCHAR, TEXT, VARCHAR, JSONB, INTEGER, TIMESTAMP)")
    op.execute("DROP FUNCTION IF EXISTS clear_telegram_chat_state(BIGINT, BIGINT)")
    op.execute("DROP FUNCTION IF EXISTS update_telegram_chat_state(BIGINT, BIGINT, VARCHAR, JSONB)")
    op.execute("DROP FUNCTION IF EXISTS get_telegram_chat_state(BIGINT, BIGINT)")
    
    # ========================================================================
    # Phase 2: Drop Views
    # ========================================================================
    
    op.execute("DROP VIEW IF EXISTS telegram_bot_stats")
    op.execute("DROP VIEW IF EXISTS telegram_queue_status")
    op.execute("DROP VIEW IF EXISTS telegram_pending_approvals")
    op.execute("DROP VIEW IF EXISTS user_activity_summary")
    op.execute("DROP VIEW IF EXISTS pending_approvals_view")
    op.execute("DROP VIEW IF EXISTS active_sprints_view")
    
    # ========================================================================
    # Phase 3: Drop Telegram Tables
    # ========================================================================
    
    op.drop_table('telegram_webhook_events')
    op.drop_table('telegram_message_queue')
    op.drop_table('telegram_command_history')
    op.drop_table('telegram_chat_states')
    
    # ========================================================================
    # Phase 4: Drop Error/File Tables
    # ========================================================================
    
    op.drop_table('file_storage')
    op.drop_table('error_logs')
    
    # ========================================================================
    # Phase 5: Drop Settings Tables
    # ========================================================================
    
    op.drop_table('user_preferences')
    op.drop_table('system_settings')
    
    # ========================================================================
    # Phase 6: Drop Notification Tables
    # ========================================================================
    
    op.drop_table('notification_preferences')
    op.drop_table('notifications')
    
    # ========================================================================
    # Phase 7: Drop Logging Tables
    # ========================================================================
    
    op.drop_table('audit_trail')
    op.drop_table('activity_logs')
    
    # ========================================================================
    # Phase 8: Drop Sprint Tables
    # ========================================================================
    
    op.drop_table('sprint_dependencies')
    op.drop_table('sprint_risks')
    op.drop_table('sprint_assignments')
    op.drop_table('sprint_stories')
    op.drop_table('sprints')
    
    # ========================================================================
    # Phase 9: Drop Workflow Tables
    # ========================================================================
    
    op.drop_table('approval_history')
    op.drop_table('approval_requests')
    
    # ========================================================================
    # Phase 10: Drop Teams Mapping
    # ========================================================================
    
    op.drop_table('team_members')
    
    # ========================================================================
    # Phase 11: Drop Auth Tables
    # ========================================================================
    
    op.drop_table('user_sessions')
    
    # ========================================================================
    # Phase 12: Remove Users Table Extensions
    # CRITICAL: Drop constraints/indexes BEFORE dropping columns
    # ========================================================================
    
    # Drop FK constraint involving users.role_id
    op.drop_constraint('fk_users_role_id', 'users', type_='foreignkey')
    
    # Drop unique constraint and index involving users.telegram_user_id
    op.drop_constraint('uq_users_telegram_user_id', 'users', type_='unique')
    op.drop_index('idx_users_telegram_id', 'users')
    
    # Drop index involving users.role_id
    op.drop_index('idx_users_role', 'users')
    
    # Now drop the 19 columns from users table
    # Telegram columns (9)
    op.drop_column('users', 'telegram_notifications_enabled')
    op.drop_column('users', 'telegram_linked_at')
    op.drop_column('users', 'telegram_is_bot')
    op.drop_column('users', 'telegram_language_code')
    op.drop_column('users', 'telegram_last_name')
    op.drop_column('users', 'telegram_first_name')
    op.drop_column('users', 'telegram_username')
    op.drop_column('users', 'telegram_chat_id')
    op.drop_column('users', 'telegram_user_id')
    
    # RBAC column (1)
    op.drop_column('users', 'role_id')
    
    # Authentication columns (9)
    op.drop_column('users', 'reset_token_expires')
    op.drop_column('users', 'reset_token')
    op.drop_column('users', 'verification_token')
    op.drop_column('users', 'email_verified')
    op.drop_column('users', 'account_status')
    op.drop_column('users', 'login_count')
    op.drop_column('users', 'last_login')
    op.drop_column('users', 'password_salt')
    op.drop_column('users', 'password_hash')
    
    # ========================================================================
    # Phase 13: Drop Teams Tables
    # ========================================================================
    
    op.drop_table('teams')
    
    # ========================================================================
    # Phase 14: Drop RBAC Tables
    # ========================================================================
    
    op.drop_table('role_permissions')
    op.drop_table('permissions')
    op.drop_table('roles')
