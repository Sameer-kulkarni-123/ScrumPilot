"""
SQLAlchemy ORM models for ScrumPilot database schema.
"""

import enum
import uuid
from datetime import datetime, timezone
from typing import List, Optional

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Column,
    Date,
    Enum,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, TIMESTAMP, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def utc_now():
    """Return current UTC timestamp with timezone."""
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    """Base class for all models."""
    pass


# ── Enums ─────────────────────────────────────────────────────────────────────


class MeetingType(str, enum.Enum):
    PM = "pm"
    SCRUM = "scrum"


class RunType(str, enum.Enum):
    PM_BACKLOG = "pm_backlog"
    SCRUM_ACTIONS = "scrum_actions"


class RunStatus(str, enum.Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class ArtifactType(str, enum.Enum):
    AUDIO = "audio"
    TRANSCRIPT = "transcript"
    DIARIZATION = "diarization"
    EXTRACTED_EPICS = "extracted_epics"
    DECOMPOSED_BACKLOG = "decomposed_backlog"
    SCRUM_ACTIONS = "scrum_actions"


class ActionType(str, enum.Enum):
    CREATE_TASK = "create_task"
    COMPLETE_TASK = "complete_task"
    UPDATE_STATUS = "update_status"
    ASSIGN_TASK = "assign_task"
    ADD_COMMENT = "add_comment"


class ExecutionStatus(str, enum.Enum):
    PENDING = "pending"
    SUCCESS = "success"
    FAILED = "failed"
    SKIPPED = "skipped"


# ── Models ────────────────────────────────────────────────────────────────────


class Meeting(Base):
    """
    Represents a meeting (PM or Scrum) that was recorded and processed.
    """
    __tablename__ = "meetings"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    meeting_uid: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        unique=True,
        nullable=False,
        default=uuid.uuid4,
    )
    meeting_type: Mapped[MeetingType] = mapped_column(
        Enum(MeetingType, name="meeting_type_enum", values_callable=lambda x: [e.value for e in x]),
        nullable=False,
    )
    title: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    meeting_date: Mapped[datetime] = mapped_column(Date, nullable=False)
    started_at: Mapped[Optional[datetime]] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=True,
    )
    ended_at: Mapped[Optional[datetime]] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=True,
    )
    source_platform: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        default="google_meet",
    )
    source_meeting_key: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(Text, nullable=False, default="created")
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=False,
        default=utc_now,
    )
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=False,
        default=utc_now,
        onupdate=utc_now,
    )

    # Relationships
    processing_runs: Mapped[List["ProcessingRun"]] = relationship(
        "ProcessingRun",
        back_populates="meeting",
        cascade="all, delete-orphan",
    )
    artifacts: Mapped[List["MeetingArtifact"]] = relationship(
        "MeetingArtifact",
        back_populates="meeting",
        cascade="all, delete-orphan",
    )
    epics: Mapped[List["Epic"]] = relationship(
        "Epic",
        back_populates="meeting",
        cascade="all, delete-orphan",
    )
    stories: Mapped[List["Story"]] = relationship(
        "Story",
        back_populates="meeting",
        cascade="all, delete-orphan",
    )
    tasks: Mapped[List["BacklogTask"]] = relationship(
        "BacklogTask",
        back_populates="meeting",
        cascade="all, delete-orphan",
    )
    scrum_actions: Mapped[List["ScrumAction"]] = relationship(
        "ScrumAction",
        back_populates="meeting",
        cascade="all, delete-orphan",
    )

    __table_args__ = (
        Index("ix_meetings_type_date", "meeting_type", "meeting_date"),
    )

    def __repr__(self):
        return f"<Meeting(id={self.id}, type={self.meeting_type.value}, date={self.meeting_date})>"


class ProcessingRun(Base):
    """
    Represents a single processing run for a meeting.
    Allows re-processing the same meeting multiple times.
    """
    __tablename__ = "processing_runs"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    meeting_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("meetings.id", ondelete="CASCADE"),
        nullable=False,
    )
    run_number: Mapped[int] = mapped_column(Integer, nullable=False)
    run_type: Mapped[RunType] = mapped_column(
        Enum(RunType, name="run_type_enum", values_callable=lambda x: [e.value for e in x]),
        nullable=False,
    )
    status: Mapped[RunStatus] = mapped_column(
        Enum(RunStatus, name="run_status_enum", values_callable=lambda x: [e.value for e in x]),
        nullable=False,
        default=RunStatus.PENDING,
    )
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=False,
        default=utc_now,
    )
    finished_at: Mapped[Optional[datetime]] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=False,
        default=utc_now,
    )
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=False,
        default=utc_now,
        onupdate=utc_now,
    )

    # Relationships
    meeting: Mapped["Meeting"] = relationship("Meeting", back_populates="processing_runs")
    artifacts: Mapped[List["MeetingArtifact"]] = relationship(
        "MeetingArtifact",
        back_populates="processing_run",
        cascade="all, delete-orphan",
    )
    epics: Mapped[List["Epic"]] = relationship(
        "Epic",
        back_populates="processing_run",
        cascade="all, delete-orphan",
    )
    stories: Mapped[List["Story"]] = relationship(
        "Story",
        back_populates="processing_run",
        cascade="all, delete-orphan",
    )
    tasks: Mapped[List["BacklogTask"]] = relationship(
        "BacklogTask",
        back_populates="processing_run",
        cascade="all, delete-orphan",
    )
    scrum_actions: Mapped[List["ScrumAction"]] = relationship(
        "ScrumAction",
        back_populates="processing_run",
        cascade="all, delete-orphan",
    )

    __table_args__ = (
        UniqueConstraint("meeting_id", "run_number", name="uq_meeting_run_number"),
    )

    def __repr__(self):
        return f"<ProcessingRun(id={self.id}, meeting_id={self.meeting_id}, run={self.run_number}, status={self.status.value})>"


class MeetingArtifact(Base):
    """
    Stores artifacts generated during meeting processing.
    Can store file paths, text content, or JSON data.
    """
    __tablename__ = "meeting_artifacts"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    meeting_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("meetings.id", ondelete="CASCADE"),
        nullable=False,
    )
    processing_run_id: Mapped[Optional[int]] = mapped_column(
        BigInteger,
        ForeignKey("processing_runs.id", ondelete="CASCADE"),
        nullable=True,
    )
    artifact_type: Mapped[ArtifactType] = mapped_column(
        Enum(ArtifactType, name="artifact_type_enum", values_callable=lambda x: [e.value for e in x]),
        nullable=False,
    )
    file_path: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    text_content: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    json_content: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    artifact_metadata: Mapped[dict] = mapped_column(
        "metadata",
        JSONB,
        nullable=False,
        default=dict,
    )
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=False,
        default=utc_now,
    )
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=False,
        default=utc_now,
        onupdate=utc_now,
    )

    # Relationships
    meeting: Mapped["Meeting"] = relationship("Meeting", back_populates="artifacts")
    processing_run: Mapped[Optional["ProcessingRun"]] = relationship(
        "ProcessingRun",
        back_populates="artifacts",
    )

    __table_args__ = (
        Index("ix_artifacts_meeting_type", "meeting_id", "artifact_type"),
    )

    def __repr__(self):
        return f"<MeetingArtifact(id={self.id}, type={self.artifact_type.value}, meeting_id={self.meeting_id})>"


class User(Base):
    """
    Maps display names from transcripts to Jira identities.
    Extended with authentication, RBAC, and Telegram support.
    """
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    display_name: Mapped[str] = mapped_column(Text, nullable=False)
    normalized_name: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    email: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    jira_account_id: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    jira_display_name: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    # Authentication fields
    password_hash: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    password_salt: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    last_login: Mapped[Optional[datetime]] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=True,
    )
    login_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    account_status: Mapped[str] = mapped_column(String(20), nullable=False, default="active")
    email_verified: Mapped[bool] = mapped_column(nullable=False, default=False)
    verification_token: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    reset_token: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    reset_token_expires: Mapped[Optional[datetime]] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=True,
    )
    
    # RBAC
    role_id: Mapped[Optional[int]] = mapped_column(
        Integer,
        ForeignKey("roles.role_id"),
        nullable=True,
    )
    
    # Telegram fields
    telegram_user_id: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    telegram_chat_id: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    telegram_username: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    telegram_first_name: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    telegram_last_name: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    telegram_language_code: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)
    telegram_is_bot: Mapped[bool] = mapped_column(nullable=False, default=False)
    telegram_linked_at: Mapped[Optional[datetime]] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=True,
    )
    telegram_notifications_enabled: Mapped[bool] = mapped_column(nullable=False, default=True)
    
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=False,
        default=utc_now,
    )
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=False,
        default=utc_now,
        onupdate=utc_now,
    )

    # Relationships
    role: Mapped[Optional["Role"]] = relationship("Role", back_populates="users")
    assigned_tasks: Mapped[List["BacklogTask"]] = relationship(
        "BacklogTask",
        back_populates="assignee_user",
        foreign_keys="BacklogTask.assignee_user_id",
    )
    resolved_scrum_actions: Mapped[List["ScrumAction"]] = relationship(
        "ScrumAction",
        back_populates="resolved_user",
        foreign_keys="ScrumAction.resolved_user_id",
    )

    __table_args__ = (
        UniqueConstraint("email", name="uq_users_email"),
        UniqueConstraint("jira_account_id", name="uq_users_jira_account_id"),
        UniqueConstraint("telegram_user_id", name="uq_users_telegram_user_id"),
        Index("idx_users_role", "role_id"),
        Index("idx_users_telegram_id", "telegram_user_id"),
    )

    def __repr__(self):
        return f"<User(id={self.id}, name={self.display_name}, email={self.email})>"


class Epic(Base):
    """
    Represents an Epic extracted from PM meetings with WSJF scoring.
    """
    __tablename__ = "epics"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    meeting_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("meetings.id", ondelete="CASCADE"),
        nullable=False,
    )
    processing_run_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("processing_runs.id", ondelete="CASCADE"),
        nullable=False,
    )
    title: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    business_value: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    time_criticality: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    risk_reduction: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    job_size: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    wsjf_score: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False)
    mentioned_features: Mapped[list] = mapped_column(
        JSONB,
        nullable=False,
        default=list,
    )
    priority_rank: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    jira_key: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    jira_status: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    jira_synced_at: Mapped[Optional[datetime]] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=False,
        default=utc_now,
    )
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=False,
        default=utc_now,
        onupdate=utc_now,
    )

    # Relationships
    meeting: Mapped["Meeting"] = relationship("Meeting", back_populates="epics")
    processing_run: Mapped["ProcessingRun"] = relationship(
        "ProcessingRun",
        back_populates="epics",
    )
    stories: Mapped[List["Story"]] = relationship(
        "Story",
        back_populates="epic",
        cascade="all, delete-orphan",
    )

    __table_args__ = (
        CheckConstraint("business_value >= 1 AND business_value <= 10", name="ck_epic_business_value"),
        CheckConstraint("time_criticality >= 1 AND time_criticality <= 10", name="ck_epic_time_criticality"),
        CheckConstraint("risk_reduction >= 1 AND risk_reduction <= 10", name="ck_epic_risk_reduction"),
        CheckConstraint("job_size >= 1 AND job_size <= 10", name="ck_epic_job_size"),
        CheckConstraint("job_size > 0", name="ck_epic_job_size_positive"),
        UniqueConstraint("jira_key", name="uq_epics_jira_key"),
    )

    def __repr__(self):
        return f"<Epic(id={self.id}, title={self.title[:30]}, wsjf={self.wsjf_score})>"


class Story(Base):
    """
    Represents a User Story decomposed from an Epic.
    """
    __tablename__ = "stories"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    epic_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("epics.id", ondelete="CASCADE"),
        nullable=False,
    )
    meeting_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("meetings.id", ondelete="CASCADE"),
        nullable=False,
    )
    processing_run_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("processing_runs.id", ondelete="CASCADE"),
        nullable=False,
    )
    title: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    acceptance_criteria: Mapped[list] = mapped_column(
        JSONB,
        nullable=False,
        default=list,
    )
    sequence_no: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    jira_key: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    jira_status: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    jira_synced_at: Mapped[Optional[datetime]] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=False,
        default=utc_now,
    )
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=False,
        default=utc_now,
        onupdate=utc_now,
    )

    # Relationships
    epic: Mapped["Epic"] = relationship("Epic", back_populates="stories")
    meeting: Mapped["Meeting"] = relationship("Meeting", back_populates="stories")
    processing_run: Mapped["ProcessingRun"] = relationship(
        "ProcessingRun",
        back_populates="stories",
    )
    tasks: Mapped[List["BacklogTask"]] = relationship(
        "BacklogTask",
        back_populates="story",
        cascade="all, delete-orphan",
    )

    __table_args__ = (
        UniqueConstraint("jira_key", name="uq_stories_jira_key"),
    )

    def __repr__(self):
        return f"<Story(id={self.id}, title={self.title[:30]}, epic_id={self.epic_id})>"


class BacklogTask(Base):
    """
    Represents a Task decomposed from a Story.
    Note: Python class name is BacklogTask, table name is 'tasks'.
    """
    __tablename__ = "tasks"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    story_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("stories.id", ondelete="CASCADE"),
        nullable=False,
    )
    meeting_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("meetings.id", ondelete="CASCADE"),
        nullable=False,
    )
    processing_run_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("processing_runs.id", ondelete="CASCADE"),
        nullable=False,
    )
    title: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    estimated_hours: Mapped[Optional[float]] = mapped_column(
        Numeric(6, 2),
        nullable=True,
    )
    assignee_user_id: Mapped[Optional[int]] = mapped_column(
        BigInteger,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    assignee_raw: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    jira_key: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    jira_status: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    jira_synced_at: Mapped[Optional[datetime]] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=False,
        default=utc_now,
    )
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=False,
        default=utc_now,
        onupdate=utc_now,
    )

    # Relationships
    story: Mapped["Story"] = relationship("Story", back_populates="tasks")
    meeting: Mapped["Meeting"] = relationship("Meeting", back_populates="tasks")
    processing_run: Mapped["ProcessingRun"] = relationship(
        "ProcessingRun",
        back_populates="tasks",
    )
    assignee_user: Mapped[Optional["User"]] = relationship(
        "User",
        back_populates="assigned_tasks",
        foreign_keys=[assignee_user_id],
    )

    __table_args__ = (
        UniqueConstraint("jira_key", name="uq_tasks_jira_key"),
    )

    def __repr__(self):
        return f"<BacklogTask(id={self.id}, title={self.title[:30]}, story_id={self.story_id})>"


class ScrumAction(Base):
    """
    Represents an action extracted from a Scrum meeting transcript.
    """
    __tablename__ = "scrum_actions"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    meeting_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("meetings.id", ondelete="CASCADE"),
        nullable=False,
    )
    processing_run_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("processing_runs.id", ondelete="CASCADE"),
        nullable=False,
    )
    action_type: Mapped[ActionType] = mapped_column(
        Enum(ActionType, name="action_type_enum", values_callable=lambda x: [e.value for e in x]),
        nullable=False,
    )
    ticket_key: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    status: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    assignee_raw: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    resolved_user_id: Mapped[Optional[int]] = mapped_column(
        BigInteger,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    comment: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    execution_status: Mapped[ExecutionStatus] = mapped_column(
        Enum(ExecutionStatus, name="execution_status_enum", values_callable=lambda x: [e.value for e in x]),
        nullable=False,
        default=ExecutionStatus.PENDING,
    )
    jira_response: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=False,
        default=utc_now,
    )
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=False,
        default=utc_now,
        onupdate=utc_now,
    )

    # Relationships
    meeting: Mapped["Meeting"] = relationship("Meeting", back_populates="scrum_actions")
    processing_run: Mapped["ProcessingRun"] = relationship(
        "ProcessingRun",
        back_populates="scrum_actions",
    )
    resolved_user: Mapped[Optional["User"]] = relationship(
        "User",
        back_populates="resolved_scrum_actions",
        foreign_keys=[resolved_user_id],
    )

    def __repr__(self):
        return f"<ScrumAction(id={self.id}, type={self.action_type.value}, summary={self.summary[:30]})>"



# ── New Models (Single Company MVP + Telegram) ───────────────────────────────


class Role(Base):
    """User role for RBAC."""
    __tablename__ = "roles"

    role_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    role_name: Mapped[str] = mapped_column(String(50), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    is_system_role: Mapped[bool] = mapped_column(nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=False,
        default=utc_now,
    )
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=False,
        default=utc_now,
        onupdate=utc_now,
    )

    # Relationships
    permissions: Mapped[List["RolePermission"]] = relationship(
        "RolePermission",
        back_populates="role",
        cascade="all, delete-orphan",
    )
    users: Mapped[List["User"]] = relationship("User", back_populates="role")

    __table_args__ = (
        UniqueConstraint("role_name", name="uq_roles_role_name"),
    )

    def __repr__(self):
        return f"<Role(id={self.role_id}, name={self.role_name})>"


class Permission(Base):
    """System permission for RBAC."""
    __tablename__ = "permissions"

    permission_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    permission_name: Mapped[str] = mapped_column(String(100), nullable=False)
    resource: Mapped[str] = mapped_column(String(50), nullable=False)
    action: Mapped[str] = mapped_column(String(50), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=False,
        default=utc_now,
    )

    # Relationships
    roles: Mapped[List["RolePermission"]] = relationship(
        "RolePermission",
        back_populates="permission",
        cascade="all, delete-orphan",
    )

    __table_args__ = (
        UniqueConstraint("permission_name", name="uq_permissions_permission_name"),
    )

    def __repr__(self):
        return f"<Permission(id={self.permission_id}, name={self.permission_name})>"


class RolePermission(Base):
    """Role-Permission mapping for RBAC."""
    __tablename__ = "role_permissions"

    role_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("roles.role_id", ondelete="CASCADE"),
        primary_key=True,
    )
    permission_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("permissions.permission_id", ondelete="CASCADE"),
        primary_key=True,
    )
    granted_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=False,
        default=utc_now,
    )

    # Relationships
    role: Mapped["Role"] = relationship("Role", back_populates="permissions")
    permission: Mapped["Permission"] = relationship("Permission", back_populates="roles")

    def __repr__(self):
        return f"<RolePermission(role_id={self.role_id}, permission_id={self.permission_id})>"



class UserSession(Base):
    """User authentication session."""
    __tablename__ = "user_sessions"

    session_id: Mapped[str] = mapped_column(String(255), primary_key=True)
    user_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=False,
        default=utc_now,
    )
    expires_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=False,
    )
    ip_address: Mapped[Optional[str]] = mapped_column(String(45), nullable=True)
    user_agent: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(nullable=False, default=True)
    last_activity: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=False,
        default=utc_now,
    )

    __table_args__ = (
        Index("idx_sessions_user_id", "user_id"),
        Index("idx_sessions_expires", "expires_at"),
    )

    def __repr__(self):
        return f"<UserSession(session_id={self.session_id[:8]}..., user_id={self.user_id})>"


class Team(Base):
    """Development team."""
    __tablename__ = "teams"

    team_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    team_name: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    team_lead_id: Mapped[Optional[int]] = mapped_column(
        BigInteger,
        ForeignKey("users.id"),
        nullable=True,
    )
    is_active: Mapped[bool] = mapped_column(nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=False,
        default=utc_now,
    )
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=False,
        default=utc_now,
        onupdate=utc_now,
    )

    # Relationships
    members: Mapped[List["TeamMember"]] = relationship(
        "TeamMember",
        back_populates="team",
        cascade="all, delete-orphan",
    )
    sprints: Mapped[List["Sprint"]] = relationship("Sprint", back_populates="team")

    __table_args__ = (
        UniqueConstraint("team_name", name="uq_teams_team_name"),
        Index("idx_teams_active", "is_active"),
    )

    def __repr__(self):
        return f"<Team(id={self.team_id}, name={self.team_name})>"


class TeamMember(Base):
    """Team membership."""
    __tablename__ = "team_members"

    team_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("teams.team_id", ondelete="CASCADE"),
        primary_key=True,
    )
    user_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("users.id", ondelete="CASCADE"),
        primary_key=True,
    )
    role_in_team: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    joined_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=False,
        default=utc_now,
    )

    # Relationships
    team: Mapped["Team"] = relationship("Team", back_populates="members")

    __table_args__ = (
        Index("idx_team_members_team", "team_id"),
        Index("idx_team_members_user", "user_id"),
    )

    def __repr__(self):
        return f"<TeamMember(team_id={self.team_id}, user_id={self.user_id})>"



class ApprovalRequest(Base):
    """Approval request for HITL workflow."""
    __tablename__ = "approval_requests"

    approval_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    request_type: Mapped[str] = mapped_column(String(50), nullable=False)
    entity_type: Mapped[str] = mapped_column(String(50), nullable=False)
    entity_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    requested_by: Mapped[Optional[int]] = mapped_column(
        BigInteger,
        ForeignKey("users.id"),
        nullable=True,
    )
    assigned_to: Mapped[Optional[int]] = mapped_column(
        BigInteger,
        ForeignKey("users.id"),
        nullable=True,
    )
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")
    priority: Mapped[str] = mapped_column(String(20), nullable=False, default="medium")
    request_data: Mapped[dict] = mapped_column(JSONB, nullable=False)
    original_data: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    approved_data: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    rejection_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=False,
        default=utc_now,
    )
    reviewed_at: Mapped[Optional[datetime]] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=True,
    )
    expires_at: Mapped[Optional[datetime]] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=True,
    )

    # Relationships
    history: Mapped[List["ApprovalHistory"]] = relationship(
        "ApprovalHistory",
        back_populates="approval",
        cascade="all, delete-orphan",
    )

    __table_args__ = (
        CheckConstraint("status IN ('pending', 'approved', 'rejected', 'expired')", name='chk_approval_status'),
        Index("idx_approvals_status", "status"),
        Index("idx_approvals_assigned", "assigned_to"),
        Index("idx_approvals_type", "request_type"),
    )

    def __repr__(self):
        return f"<ApprovalRequest(id={self.approval_id}, type={self.request_type}, status={self.status})>"


class ApprovalHistory(Base):
    """Approval history for audit trail."""
    __tablename__ = "approval_history"

    history_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    approval_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("approval_requests.approval_id", ondelete="CASCADE"),
        nullable=False,
    )
    action: Mapped[str] = mapped_column(String(50), nullable=False)
    performed_by: Mapped[Optional[int]] = mapped_column(
        BigInteger,
        ForeignKey("users.id"),
        nullable=True,
    )
    comment: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    changes: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=False,
        default=utc_now,
    )

    # Relationships
    approval: Mapped["ApprovalRequest"] = relationship("ApprovalRequest", back_populates="history")

    __table_args__ = (
        Index("idx_approval_history_approval", "approval_id"),
    )

    def __repr__(self):
        return f"<ApprovalHistory(id={self.history_id}, approval_id={self.approval_id}, action={self.action})>"



class Sprint(Base):
    """Sprint for agile planning."""
    __tablename__ = "sprints"

    sprint_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    sprint_number: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    sprint_name: Mapped[str] = mapped_column(String(100), nullable=False)
    sprint_goal: Mapped[str] = mapped_column(Text, nullable=False)
    start_date: Mapped[datetime] = mapped_column(Date, nullable=False)
    end_date: Mapped[datetime] = mapped_column(Date, nullable=False)
    duration_weeks: Mapped[int] = mapped_column(Integer, nullable=False, default=2)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="planned")
    team_capacity_hours: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    team_size: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    velocity_target: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    velocity_actual: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    team_id: Mapped[Optional[int]] = mapped_column(
        Integer,
        ForeignKey("teams.team_id"),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=False,
        default=utc_now,
    )
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=False,
        default=utc_now,
        onupdate=utc_now,
    )
    created_by: Mapped[Optional[int]] = mapped_column(
        BigInteger,
        ForeignKey("users.id"),
        nullable=True,
    )

    # Relationships
    team: Mapped[Optional["Team"]] = relationship("Team", back_populates="sprints")
    stories: Mapped[List["SprintStory"]] = relationship(
        "SprintStory",
        back_populates="sprint",
        cascade="all, delete-orphan",
    )
    assignments: Mapped[List["SprintAssignment"]] = relationship(
        "SprintAssignment",
        back_populates="sprint",
        cascade="all, delete-orphan",
    )
    risks: Mapped[List["SprintRisk"]] = relationship(
        "SprintRisk",
        back_populates="sprint",
        cascade="all, delete-orphan",
    )
    dependencies: Mapped[List["SprintDependency"]] = relationship(
        "SprintDependency",
        back_populates="sprint",
        cascade="all, delete-orphan",
    )

    __table_args__ = (
        CheckConstraint("status IN ('planned', 'active', 'completed', 'cancelled')", name='chk_sprint_status'),
        Index("idx_sprints_status", "status"),
        Index("idx_sprints_dates", "start_date", "end_date"),
        Index("idx_sprints_team", "team_id"),
    )

    def __repr__(self):
        return f"<Sprint(id={self.sprint_id}, name={self.sprint_name}, status={self.status})>"



class SprintStory(Base):
    """Story committed to a sprint."""
    __tablename__ = "sprint_stories"

    sprint_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("sprints.sprint_id", ondelete="CASCADE"),
        primary_key=True,
    )
    story_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("stories.id", ondelete="CASCADE"),
        primary_key=True,
    )
    committed_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=False,
        default=utc_now,
    )
    committed_by: Mapped[Optional[int]] = mapped_column(
        BigInteger,
        ForeignKey("users.id"),
        nullable=True,
    )
    story_points: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    estimated_hours: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    actual_hours: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="committed")

    # Relationships
    sprint: Mapped["Sprint"] = relationship("Sprint", back_populates="stories")

    __table_args__ = (
        Index("idx_sprint_stories_sprint", "sprint_id"),
        Index("idx_sprint_stories_story", "story_id"),
    )

    def __repr__(self):
        return f"<SprintStory(sprint_id={self.sprint_id}, story_id={self.story_id})>"


class SprintAssignment(Base):
    """Developer assignment in a sprint."""
    __tablename__ = "sprint_assignments"

    assignment_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    sprint_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("sprints.sprint_id", ondelete="CASCADE"),
        nullable=False,
    )
    user_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    story_id: Mapped[Optional[int]] = mapped_column(
        BigInteger,
        ForeignKey("stories.id"),
        nullable=True,
    )
    task_id: Mapped[Optional[int]] = mapped_column(
        BigInteger,
        ForeignKey("tasks.id"),
        nullable=True,
    )
    estimated_hours: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    actual_hours: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    assigned_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=False,
        default=utc_now,
    )
    assigned_by: Mapped[Optional[int]] = mapped_column(
        BigInteger,
        ForeignKey("users.id"),
        nullable=True,
    )

    # Relationships
    sprint: Mapped["Sprint"] = relationship("Sprint", back_populates="assignments")

    __table_args__ = (
        Index("idx_sprint_assignments_sprint", "sprint_id"),
        Index("idx_sprint_assignments_user", "user_id"),
    )

    def __repr__(self):
        return f"<SprintAssignment(id={self.assignment_id}, sprint_id={self.sprint_id}, user_id={self.user_id})>"



class SprintRisk(Base):
    """Risk identified in a sprint."""
    __tablename__ = "sprint_risks"

    risk_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    sprint_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("sprints.sprint_id", ondelete="CASCADE"),
        nullable=False,
    )
    risk_description: Mapped[str] = mapped_column(Text, nullable=False)
    severity: Mapped[str] = mapped_column(String(20), nullable=False, default="medium")
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="open")
    mitigation_plan: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    identified_by: Mapped[Optional[int]] = mapped_column(
        BigInteger,
        ForeignKey("users.id"),
        nullable=True,
    )
    identified_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=False,
        default=utc_now,
    )
    resolved_at: Mapped[Optional[datetime]] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=True,
    )

    # Relationships
    sprint: Mapped["Sprint"] = relationship("Sprint", back_populates="risks")

    __table_args__ = (
        CheckConstraint("severity IN ('low', 'medium', 'high', 'critical')", name='chk_risk_severity'),
        CheckConstraint("status IN ('open', 'mitigated', 'resolved', 'accepted')", name='chk_risk_status'),
        Index("idx_sprint_risks_sprint", "sprint_id"),
    )

    def __repr__(self):
        return f"<SprintRisk(id={self.risk_id}, sprint_id={self.sprint_id}, severity={self.severity})>"


class SprintDependency(Base):
    """External dependency for a sprint."""
    __tablename__ = "sprint_dependencies"

    dependency_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    sprint_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("sprints.sprint_id", ondelete="CASCADE"),
        nullable=False,
    )
    dependency_description: Mapped[str] = mapped_column(Text, nullable=False)
    dependency_type: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    external_team: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")
    due_date: Mapped[Optional[datetime]] = mapped_column(Date, nullable=True)
    identified_by: Mapped[Optional[int]] = mapped_column(
        BigInteger,
        ForeignKey("users.id"),
        nullable=True,
    )
    identified_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=False,
        default=utc_now,
    )
    resolved_at: Mapped[Optional[datetime]] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=True,
    )

    # Relationships
    sprint: Mapped["Sprint"] = relationship("Sprint", back_populates="dependencies")

    __table_args__ = (
        CheckConstraint("status IN ('pending', 'in_progress', 'resolved', 'blocked')", name='chk_dependency_status'),
        Index("idx_sprint_dependencies_sprint", "sprint_id"),
    )

    def __repr__(self):
        return f"<SprintDependency(id={self.dependency_id}, sprint_id={self.sprint_id}, status={self.status})>"



class ActivityLog(Base):
    """User activity log."""
    __tablename__ = "activity_logs"

    log_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    user_id: Mapped[Optional[int]] = mapped_column(
        BigInteger,
        ForeignKey("users.id"),
        nullable=True,
    )
    action: Mapped[str] = mapped_column(String(100), nullable=False)
    entity_type: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    entity_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    details: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    ip_address: Mapped[Optional[str]] = mapped_column(String(45), nullable=True)
    user_agent: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=False,
        default=utc_now,
    )

    __table_args__ = (
        Index("idx_activity_logs_user", "user_id"),
        Index("idx_activity_logs_created", "created_at"),
        Index("idx_activity_logs_entity", "entity_type", "entity_id"),
    )

    def __repr__(self):
        return f"<ActivityLog(id={self.log_id}, action={self.action})>"


class AuditTrail(Base):
    """Audit trail for critical changes."""
    __tablename__ = "audit_trail"

    audit_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    table_name: Mapped[str] = mapped_column(String(50), nullable=False)
    record_id: Mapped[int] = mapped_column(Integer, nullable=False)
    operation: Mapped[str] = mapped_column(String(10), nullable=False)
    old_values: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    new_values: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    changed_by: Mapped[Optional[int]] = mapped_column(
        BigInteger,
        ForeignKey("users.id"),
        nullable=True,
    )
    changed_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=False,
        default=utc_now,
    )

    __table_args__ = (
        CheckConstraint("operation IN ('INSERT', 'UPDATE', 'DELETE')", name='chk_operation'),
        Index("idx_audit_trail_table", "table_name", "record_id"),
        Index("idx_audit_trail_changed", "changed_at"),
    )

    def __repr__(self):
        return f"<AuditTrail(id={self.audit_id}, table={self.table_name}, operation={self.operation})>"



class Notification(Base):
    """User notification."""
    __tablename__ = "notifications"

    notification_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    notification_type: Mapped[str] = mapped_column(String(50), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    entity_type: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    entity_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    priority: Mapped[str] = mapped_column(String(20), nullable=False, default="normal")
    is_read: Mapped[bool] = mapped_column(nullable=False, default=False)
    read_at: Mapped[Optional[datetime]] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=False,
        default=utc_now,
    )
    expires_at: Mapped[Optional[datetime]] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=True,
    )

    __table_args__ = (
        CheckConstraint("priority IN ('low', 'normal', 'high', 'urgent')", name='chk_notification_priority'),
        Index("idx_notifications_user", "user_id"),
        Index("idx_notifications_read", "is_read"),
        Index("idx_notifications_created", "created_at"),
    )

    def __repr__(self):
        return f"<Notification(id={self.notification_id}, user_id={self.user_id}, type={self.notification_type})>"


class NotificationPreference(Base):
    """User notification preferences."""
    __tablename__ = "notification_preferences"

    user_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("users.id", ondelete="CASCADE"),
        primary_key=True,
    )
    notification_type: Mapped[str] = mapped_column(String(50), primary_key=True)
    email_enabled: Mapped[bool] = mapped_column(nullable=False, default=True)
    in_app_enabled: Mapped[bool] = mapped_column(nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=False,
        default=utc_now,
    )
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=False,
        default=utc_now,
        onupdate=utc_now,
    )

    def __repr__(self):
        return f"<NotificationPreference(user_id={self.user_id}, type={self.notification_type})>"



class SystemSetting(Base):
    """System-wide configuration setting."""
    __tablename__ = "system_settings"

    setting_key: Mapped[str] = mapped_column(String(100), primary_key=True)
    setting_value: Mapped[str] = mapped_column(Text, nullable=False)
    setting_type: Mapped[str] = mapped_column(String(20), nullable=False, default="string")
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    is_public: Mapped[bool] = mapped_column(nullable=False, default=False)
    updated_by: Mapped[Optional[int]] = mapped_column(
        BigInteger,
        ForeignKey("users.id"),
        nullable=True,
    )
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=False,
        default=utc_now,
    )

    __table_args__ = (
        CheckConstraint("setting_type IN ('string', 'number', 'boolean', 'json')", name='chk_setting_type'),
    )

    def __repr__(self):
        return f"<SystemSetting(key={self.setting_key}, type={self.setting_type})>"


class UserPreference(Base):
    """User-specific preference."""
    __tablename__ = "user_preferences"

    user_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("users.id", ondelete="CASCADE"),
        primary_key=True,
    )
    preference_key: Mapped[str] = mapped_column(String(100), primary_key=True)
    preference_value: Mapped[str] = mapped_column(Text, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=False,
        default=utc_now,
    )

    __table_args__ = (
        Index("idx_user_preferences_user", "user_id"),
    )

    def __repr__(self):
        return f"<UserPreference(user_id={self.user_id}, key={self.preference_key})>"


class ErrorLog(Base):
    """Application error log."""
    __tablename__ = "error_logs"

    error_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    error_type: Mapped[str] = mapped_column(String(50), nullable=False)
    error_message: Mapped[str] = mapped_column(Text, nullable=False)
    stack_trace: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    severity: Mapped[str] = mapped_column(String(20), nullable=False, default="error")
    user_id: Mapped[Optional[int]] = mapped_column(
        BigInteger,
        ForeignKey("users.id"),
        nullable=True,
    )
    request_path: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    request_method: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)
    request_data: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    ip_address: Mapped[Optional[str]] = mapped_column(String(45), nullable=True)
    user_agent: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    resolved: Mapped[bool] = mapped_column(nullable=False, default=False)
    resolved_by: Mapped[Optional[int]] = mapped_column(
        BigInteger,
        ForeignKey("users.id"),
        nullable=True,
    )
    resolved_at: Mapped[Optional[datetime]] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=False,
        default=utc_now,
    )

    __table_args__ = (
        CheckConstraint("severity IN ('warning', 'error', 'critical')", name='chk_error_severity'),
        Index("idx_error_logs_created", "created_at"),
        Index("idx_error_logs_severity", "severity"),
        Index("idx_error_logs_resolved", "resolved"),
        Index("idx_error_logs_type", "error_type"),
    )

    def __repr__(self):
        return f"<ErrorLog(id={self.error_id}, type={self.error_type}, severity={self.severity})>"


class FileStorage(Base):
    """File upload metadata."""
    __tablename__ = "file_storage"

    file_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    file_name: Mapped[str] = mapped_column(String(255), nullable=False)
    file_path: Mapped[str] = mapped_column(String(500), nullable=False)
    file_type: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    file_size: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    mime_type: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    entity_type: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    entity_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    uploaded_by: Mapped[Optional[int]] = mapped_column(
        BigInteger,
        ForeignKey("users.id"),
        nullable=True,
    )
    uploaded_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=False,
        default=utc_now,
    )
    is_deleted: Mapped[bool] = mapped_column(nullable=False, default=False)
    deleted_at: Mapped[Optional[datetime]] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=True,
    )

    __table_args__ = (
        Index("idx_file_storage_entity", "entity_type", "entity_id"),
        Index("idx_file_storage_uploaded", "uploaded_by"),
        Index("idx_file_storage_deleted", "is_deleted"),
    )

    def __repr__(self):
        return f"<FileStorage(id={self.file_id}, name={self.file_name})>"



# ── Telegram Models ──────────────────────────────────────────────────────────


class TelegramChatState(Base):
    """Telegram conversation state tracking."""
    __tablename__ = "telegram_chat_states"

    state_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    telegram_user_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    telegram_chat_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    current_state: Mapped[str] = mapped_column(String(50), nullable=False)
    state_data: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=False,
        default=utc_now,
    )
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=False,
        default=utc_now,
        onupdate=utc_now,
    )
    expires_at: Mapped[Optional[datetime]] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=True,
    )

    __table_args__ = (
        UniqueConstraint("telegram_user_id", "telegram_chat_id", name="uq_telegram_chat_states"),
        Index("idx_chat_states_user", "telegram_user_id"),
        Index("idx_chat_states_expires", "expires_at"),
    )

    def __repr__(self):
        return f"<TelegramChatState(id={self.state_id}, user_id={self.telegram_user_id}, state={self.current_state})>"


class TelegramCommandHistory(Base):
    """Telegram bot command history."""
    __tablename__ = "telegram_command_history"

    command_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    telegram_user_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    telegram_chat_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    telegram_message_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    command: Mapped[str] = mapped_column(String(100), nullable=False)
    command_args: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    response_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    response_message_id: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    execution_time_ms: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    success: Mapped[bool] = mapped_column(nullable=False, default=True)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=False,
        default=utc_now,
    )

    __table_args__ = (
        Index("idx_command_history_user", "telegram_user_id"),
        Index("idx_command_history_created", "created_at"),
        Index("idx_command_history_command", "command"),
        Index("idx_command_history_success", "success"),
    )

    def __repr__(self):
        return f"<TelegramCommandHistory(id={self.command_id}, command={self.command}, success={self.success})>"


class TelegramMessageQueue(Base):
    """Telegram outgoing message queue."""
    __tablename__ = "telegram_message_queue"

    queue_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    telegram_user_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    telegram_chat_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    message_type: Mapped[str] = mapped_column(String(50), nullable=False)
    message_text: Mapped[str] = mapped_column(Text, nullable=False)
    parse_mode: Mapped[Optional[str]] = mapped_column(String(20), nullable=True, default="Markdown")
    reply_markup: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    priority: Mapped[int] = mapped_column(Integer, nullable=False, default=5)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")
    retry_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    max_retries: Mapped[int] = mapped_column(Integer, nullable=False, default=3)
    scheduled_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=False,
        default=utc_now,
    )
    sent_at: Mapped[Optional[datetime]] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=True,
    )
    telegram_message_id: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=False,
        default=utc_now,
    )

    __table_args__ = (
        CheckConstraint("status IN ('pending', 'sent', 'failed', 'cancelled')", name='chk_queue_status'),
        CheckConstraint("priority BETWEEN 1 AND 10", name='chk_queue_priority'),
        Index("idx_message_queue_status", "status"),
        Index("idx_message_queue_scheduled", "scheduled_at"),
        Index("idx_message_queue_user", "telegram_user_id"),
    )

    def __repr__(self):
        return f"<TelegramMessageQueue(id={self.queue_id}, type={self.message_type}, status={self.status})>"


class TelegramWebhookEvent(Base):
    """Telegram webhook event log."""
    __tablename__ = "telegram_webhook_events"

    event_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    update_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    event_type: Mapped[str] = mapped_column(String(50), nullable=False)
    telegram_user_id: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    telegram_chat_id: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    message_data: Mapped[dict] = mapped_column(JSONB, nullable=False)
    processed: Mapped[bool] = mapped_column(nullable=False, default=False)
    processed_at: Mapped[Optional[datetime]] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=True,
    )
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=False,
        default=utc_now,
    )

    __table_args__ = (
        UniqueConstraint("update_id", name="uq_telegram_webhook_events_update_id"),
        Index("idx_webhook_events_processed", "processed"),
        Index("idx_webhook_events_created", "created_at"),
        Index("idx_webhook_events_type", "event_type"),
        Index("idx_webhook_events_user", "telegram_user_id"),
    )

    def __repr__(self):
        return f"<TelegramWebhookEvent(id={self.event_id}, type={self.event_type}, processed={self.processed})>"
