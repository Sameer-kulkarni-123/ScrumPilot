"""
CRUD operations for ScrumPilot database.
Low-level database operations used by the storage service.
"""

from datetime import datetime
from typing import Optional, List
from sqlalchemy.orm import Session
from sqlalchemy import select

from backend.db.models import (
    Meeting,
    ProcessingRun,
    MeetingArtifact,
    User,
    Epic,
    Story,
    BacklogTask,
    ScrumAction,
    MeetingType,
    RunType,
    RunStatus,
    ArtifactType,
    ActionType,
    ExecutionStatus,
)


# ── Meeting CRUD ──────────────────────────────────────────────────────────────


def create_meeting(
    session: Session,
    meeting_type: str,  # Changed from MeetingType to str
    meeting_date: datetime,
    title: Optional[str] = None,
    source_platform: str = "google_meet",
    source_meeting_key: Optional[str] = None,
    started_at: Optional[datetime] = None,
    ended_at: Optional[datetime] = None,
    status: str = "created",
) -> Meeting:
    """Create a new meeting record."""
    meeting = Meeting(
        meeting_type=meeting_type,
        meeting_date=meeting_date,
        title=title,
        source_platform=source_platform,
        source_meeting_key=source_meeting_key,
        started_at=started_at,
        ended_at=ended_at,
        status=status,
    )
    session.add(meeting)
    session.flush()
    return meeting


def get_meeting_by_id(session: Session, meeting_id: int) -> Optional[Meeting]:
    """Get meeting by ID."""
    return session.get(Meeting, meeting_id)


# ── ProcessingRun CRUD ────────────────────────────────────────────────────────


def create_processing_run(
    session: Session,
    meeting_id: int,
    run_type: str,  # Changed from RunType to str
    run_number: Optional[int] = None,
) -> ProcessingRun:
    """Create a new processing run for a meeting."""
    if run_number is None:
        # Auto-increment run number
        stmt = select(ProcessingRun).where(ProcessingRun.meeting_id == meeting_id)
        existing_runs = session.execute(stmt).scalars().all()
        run_number = len(existing_runs) + 1

    processing_run = ProcessingRun(
        meeting_id=meeting_id,
        run_number=run_number,
        run_type=run_type,
        status=RunStatus.RUNNING.value,  # Use .value
    )
    session.add(processing_run)
    session.flush()
    return processing_run


def update_processing_run_status(
    session: Session,
    run_id: int,
    status: str,  # Changed from RunStatus to str
    error_message: Optional[str] = None,
    finished_at: Optional[datetime] = None,
) -> ProcessingRun:
    """Update processing run status."""
    run = session.get(ProcessingRun, run_id)
    if not run:
        raise ValueError(f"ProcessingRun {run_id} not found")
    
    run.status = status
    if error_message:
        run.error_message = error_message
    if finished_at:
        run.finished_at = finished_at
    
    session.flush()
    return run


# ── MeetingArtifact CRUD ──────────────────────────────────────────────────────


def create_artifact(
    session: Session,
    meeting_id: int,
    artifact_type: str,  # Changed from ArtifactType to str
    processing_run_id: Optional[int] = None,
    file_path: Optional[str] = None,
    text_content: Optional[str] = None,
    json_content: Optional[dict] = None,
    metadata: Optional[dict] = None,
) -> MeetingArtifact:
    """Create a new meeting artifact."""
    artifact = MeetingArtifact(
        meeting_id=meeting_id,
        processing_run_id=processing_run_id,
        artifact_type=artifact_type,
        file_path=file_path,
        text_content=text_content,
        json_content=json_content,
        artifact_metadata=metadata or {},
    )
    session.add(artifact)
    session.flush()
    return artifact


# ── User CRUD ─────────────────────────────────────────────────────────────────


def upsert_user(
    session: Session,
    display_name: str,
    email: Optional[str] = None,
    jira_account_id: Optional[str] = None,
    jira_display_name: Optional[str] = None,
) -> User:
    """Create or update a user record."""
    # Try to find existing user by email or jira_account_id
    user = None
    if email:
        stmt = select(User).where(User.email == email)
        user = session.execute(stmt).scalar_one_or_none()
    
    if not user and jira_account_id:
        stmt = select(User).where(User.jira_account_id == jira_account_id)
        user = session.execute(stmt).scalar_one_or_none()
    
    if user:
        # Update existing user
        user.display_name = display_name
        if email:
            user.email = email
        if jira_account_id:
            user.jira_account_id = jira_account_id
        if jira_display_name:
            user.jira_display_name = jira_display_name
        user.normalized_name = display_name.lower().strip()
    else:
        # Create new user
        user = User(
            display_name=display_name,
            normalized_name=display_name.lower().strip(),
            email=email,
            jira_account_id=jira_account_id,
            jira_display_name=jira_display_name,
        )
        session.add(user)
    
    session.flush()
    return user


def find_user_by_name(session: Session, name: str) -> Optional[User]:
    """Find user by display name (case-insensitive)."""
    normalized = name.lower().strip()
    stmt = select(User).where(User.normalized_name == normalized)
    return session.execute(stmt).scalar_one_or_none()


# ── Epic CRUD ─────────────────────────────────────────────────────────────────


def create_epic(
    session: Session,
    meeting_id: int,
    processing_run_id: int,
    title: str,
    business_value: int,
    time_criticality: int,
    risk_reduction: int,
    job_size: int,
    wsjf_score: float,
    description: Optional[str] = None,
    mentioned_features: Optional[list] = None,
    priority_rank: Optional[int] = None,
) -> Epic:
    """Create a new epic."""
    epic = Epic(
        meeting_id=meeting_id,
        processing_run_id=processing_run_id,
        title=title,
        description=description,
        business_value=business_value,
        time_criticality=time_criticality,
        risk_reduction=risk_reduction,
        job_size=job_size,
        wsjf_score=wsjf_score,
        mentioned_features=mentioned_features or [],
        priority_rank=priority_rank,
    )
    session.add(epic)
    session.flush()
    return epic


def update_epic_jira_info(
    session: Session,
    epic_id: int,
    jira_key: str,
    jira_status: Optional[str] = None,
    jira_synced_at: Optional[datetime] = None,
) -> Epic:
    """Update epic with Jira information."""
    epic = session.get(Epic, epic_id)
    if not epic:
        raise ValueError(f"Epic {epic_id} not found")
    
    epic.jira_key = jira_key
    if jira_status:
        epic.jira_status = jira_status
    if jira_synced_at:
        epic.jira_synced_at = jira_synced_at
    
    session.flush()
    return epic


# ── Story CRUD ────────────────────────────────────────────────────────────────


def create_story(
    session: Session,
    epic_id: int,
    meeting_id: int,
    processing_run_id: int,
    title: str,
    description: Optional[str] = None,
    acceptance_criteria: Optional[list] = None,
    sequence_no: Optional[int] = None,
) -> Story:
    """Create a new story."""
    story = Story(
        epic_id=epic_id,
        meeting_id=meeting_id,
        processing_run_id=processing_run_id,
        title=title,
        description=description,
        acceptance_criteria=acceptance_criteria or [],
        sequence_no=sequence_no,
    )
    session.add(story)
    session.flush()
    return story


def update_story_jira_info(
    session: Session,
    story_id: int,
    jira_key: str,
    jira_status: Optional[str] = None,
    jira_synced_at: Optional[datetime] = None,
) -> Story:
    """Update story with Jira information."""
    story = session.get(Story, story_id)
    if not story:
        raise ValueError(f"Story {story_id} not found")
    
    story.jira_key = jira_key
    if jira_status:
        story.jira_status = jira_status
    if jira_synced_at:
        story.jira_synced_at = jira_synced_at
    
    session.flush()
    return story


# ── BacklogTask CRUD ──────────────────────────────────────────────────────────


def create_backlog_task(
    session: Session,
    story_id: int,
    meeting_id: int,
    processing_run_id: int,
    title: str,
    description: Optional[str] = None,
    estimated_hours: Optional[float] = None,
    assignee_user_id: Optional[int] = None,
    assignee_raw: Optional[str] = None,
) -> BacklogTask:
    """Create a new backlog task."""
    task = BacklogTask(
        story_id=story_id,
        meeting_id=meeting_id,
        processing_run_id=processing_run_id,
        title=title,
        description=description,
        estimated_hours=estimated_hours,
        assignee_user_id=assignee_user_id,
        assignee_raw=assignee_raw,
    )
    session.add(task)
    session.flush()
    return task


def update_task_jira_info(
    session: Session,
    task_id: int,
    jira_key: str,
    jira_status: Optional[str] = None,
    jira_synced_at: Optional[datetime] = None,
) -> BacklogTask:
    """Update task with Jira information."""
    task = session.get(BacklogTask, task_id)
    if not task:
        raise ValueError(f"BacklogTask {task_id} not found")
    
    task.jira_key = jira_key
    if jira_status:
        task.jira_status = jira_status
    if jira_synced_at:
        task.jira_synced_at = jira_synced_at
    
    session.flush()
    return task


# ── ScrumAction CRUD ──────────────────────────────────────────────────────────


def create_scrum_action(
    session: Session,
    meeting_id: int,
    processing_run_id: int,
    action_type: str,  # Changed from ActionType to str
    summary: str,
    ticket_key: Optional[str] = None,
    description: Optional[str] = None,
    status: Optional[str] = None,
    assignee_raw: Optional[str] = None,
    resolved_user_id: Optional[int] = None,
    comment: Optional[str] = None,
    execution_status: str = "pending",  # Changed from ExecutionStatus to str with default
) -> ScrumAction:
    """Create a new scrum action."""
    action = ScrumAction(
        meeting_id=meeting_id,
        processing_run_id=processing_run_id,
        action_type=action_type,
        ticket_key=ticket_key,
        summary=summary,
        description=description,
        status=status,
        assignee_raw=assignee_raw,
        resolved_user_id=resolved_user_id,
        comment=comment,
        execution_status=execution_status,
    )
    session.add(action)
    session.flush()
    return action


def update_scrum_action_execution(
    session: Session,
    action_id: int,
    execution_status: str,  # Changed from ExecutionStatus to str
    jira_response: Optional[dict] = None,
) -> ScrumAction:
    """Update scrum action execution status."""
    action = session.get(ScrumAction, action_id)
    if not action:
        raise ValueError(f"ScrumAction {action_id} not found")
    
    action.execution_status = execution_status
    if jira_response:
        action.jira_response = jira_response
    
    session.flush()
    return action



# ── RBAC CRUD ─────────────────────────────────────────────────────────────────


def get_role_by_name(session: Session, role_name: str) -> Optional["Role"]:
    """Get role by name."""
    from backend.db.models import Role
    stmt = select(Role).where(Role.role_name == role_name)
    return session.execute(stmt).scalar_one_or_none()


def get_user_permissions(session: Session, user_id: int) -> List["Permission"]:
    """Get all permissions for a user based on their role."""
    from backend.db.models import User, Role, Permission, RolePermission
    stmt = (
        select(Permission)
        .join(RolePermission, Permission.permission_id == RolePermission.permission_id)
        .join(Role, RolePermission.role_id == Role.role_id)
        .join(User, User.role_id == Role.role_id)
        .where(User.id == user_id)
    )
    return list(session.execute(stmt).scalars().all())


def check_permission(session: Session, user_id: int, resource: str, action: str) -> bool:
    """Check if user has specific permission."""
    from backend.db.models import User, Role, Permission, RolePermission
    stmt = (
        select(Permission)
        .join(RolePermission, Permission.permission_id == RolePermission.permission_id)
        .join(Role, RolePermission.role_id == Role.role_id)
        .join(User, User.role_id == Role.role_id)
        .where(User.id == user_id)
        .where(Permission.resource == resource)
        .where(Permission.action == action)
    )
    result = session.execute(stmt).scalar_one_or_none()
    return result is not None


# ── Session Management CRUD ───────────────────────────────────────────────────


def create_session(
    session: Session,
    user_id: int,
    expires_at: datetime,
    ip_address: Optional[str] = None,
    user_agent: Optional[str] = None,
) -> "UserSession":
    """Create a new user session."""
    from backend.db.models import UserSession
    import secrets
    
    session_id = secrets.token_urlsafe(32)
    user_session = UserSession(
        session_id=session_id,
        user_id=user_id,
        expires_at=expires_at,
        ip_address=ip_address,
        user_agent=user_agent,
    )
    session.add(user_session)
    session.flush()
    return user_session


def get_session(session: Session, session_id: str) -> Optional["UserSession"]:
    """Get session by ID."""
    from backend.db.models import UserSession
    return session.get(UserSession, session_id)


def invalidate_session(session: Session, session_id: str) -> bool:
    """Invalidate a session."""
    from backend.db.models import UserSession
    user_session = session.get(UserSession, session_id)
    if user_session:
        user_session.is_active = False
        session.flush()
        return True
    return False


# ── Approval Workflow CRUD ────────────────────────────────────────────────────


def create_approval_request(
    session: Session,
    request_type: str,
    entity_type: str,
    entity_id: int,
    requested_by: int,
    assigned_to: int,
    request_data: dict,
    priority: str = "medium",
) -> "ApprovalRequest":
    """Create a new approval request."""
    from backend.db.models import ApprovalRequest
    
    approval = ApprovalRequest(
        request_type=request_type,
        entity_type=entity_type,
        entity_id=entity_id,
        requested_by=requested_by,
        assigned_to=assigned_to,
        request_data=request_data,
        priority=priority,
    )
    session.add(approval)
    session.flush()
    return approval


def approve_request(
    session: Session,
    approval_id: int,
    approved_by: int,
    approved_data: dict,
) -> "ApprovalRequest":
    """Approve an approval request."""
    from backend.db.models import ApprovalRequest
    from datetime import datetime, timezone
    
    approval = session.get(ApprovalRequest, approval_id)
    if not approval:
        raise ValueError(f"ApprovalRequest {approval_id} not found")
    
    approval.status = "approved"
    approval.approved_data = approved_data
    approval.reviewed_at = datetime.now(timezone.utc)
    session.flush()
    return approval


# ── Sprint Planning CRUD ──────────────────────────────────────────────────────


def create_sprint(
    session: Session,
    sprint_name: str,
    sprint_goal: str,
    start_date: datetime,
    end_date: datetime,
    team_id: int,
    created_by: int,
) -> "Sprint":
    """Create a new sprint."""
    from backend.db.models import Sprint
    
    sprint = Sprint(
        sprint_name=sprint_name,
        sprint_goal=sprint_goal,
        start_date=start_date,
        end_date=end_date,
        team_id=team_id,
        created_by=created_by,
    )
    session.add(sprint)
    session.flush()
    return sprint


def add_story_to_sprint(
    session: Session,
    sprint_id: int,
    story_id: int,
    committed_by: int,
) -> "SprintStory":
    """Add a story to a sprint."""
    from backend.db.models import SprintStory
    
    sprint_story = SprintStory(
        sprint_id=sprint_id,
        story_id=story_id,
        committed_by=committed_by,
    )
    session.add(sprint_story)
    session.flush()
    return sprint_story


# ── Settings CRUD ─────────────────────────────────────────────────────────────


def get_setting(session: Session, setting_key: str) -> Optional["SystemSetting"]:
    """Get a system setting by key."""
    from backend.db.models import SystemSetting
    return session.get(SystemSetting, setting_key)


def set_setting(
    session: Session,
    setting_key: str,
    setting_value: str,
    updated_by: int,
) -> "SystemSetting":
    """Set a system setting value."""
    from backend.db.models import SystemSetting
    
    setting = session.get(SystemSetting, setting_key)
    if setting:
        setting.setting_value = setting_value
        setting.updated_by = updated_by
    else:
        setting = SystemSetting(
            setting_key=setting_key,
            setting_value=setting_value,
            updated_by=updated_by,
        )
        session.add(setting)
    
    session.flush()
    return setting


# ── Telegram CRUD ─────────────────────────────────────────────────────────────


def upsert_chat_state(
    session: Session,
    telegram_user_id: int,
    telegram_chat_id: int,
    current_state: str,
    state_data: dict,
) -> "TelegramChatState":
    """Create or update Telegram chat state."""
    from backend.db.models import TelegramChatState
    from datetime import datetime, timezone, timedelta
    
    stmt = select(TelegramChatState).where(
        TelegramChatState.telegram_user_id == telegram_user_id,
        TelegramChatState.telegram_chat_id == telegram_chat_id,
    )
    chat_state = session.execute(stmt).scalar_one_or_none()
    
    if chat_state:
        chat_state.current_state = current_state
        chat_state.state_data = state_data
        chat_state.updated_at = datetime.now(timezone.utc)
        chat_state.expires_at = datetime.now(timezone.utc) + timedelta(minutes=10)
    else:
        chat_state = TelegramChatState(
            telegram_user_id=telegram_user_id,
            telegram_chat_id=telegram_chat_id,
            current_state=current_state,
            state_data=state_data,
            expires_at=datetime.now(timezone.utc) + timedelta(minutes=10),
        )
        session.add(chat_state)
    
    session.flush()
    return chat_state


def queue_telegram_message(
    session: Session,
    telegram_user_id: int,
    telegram_chat_id: int,
    message_type: str,
    message_text: str,
    priority: int = 5,
) -> "TelegramMessageQueue":
    """Queue a Telegram message for sending."""
    from backend.db.models import TelegramMessageQueue
    
    message = TelegramMessageQueue(
        telegram_user_id=telegram_user_id,
        telegram_chat_id=telegram_chat_id,
        message_type=message_type,
        message_text=message_text,
        priority=priority,
    )
    session.add(message)
    session.flush()
    return message


# ── Notification CRUD ─────────────────────────────────────────────────────────


def create_notification(
    session: Session,
    user_id: int,
    notification_type: str,
    title: str,
    message: str,
    priority: str = "normal",
) -> "Notification":
    """Create a new notification."""
    from backend.db.models import Notification
    
    notification = Notification(
        user_id=user_id,
        notification_type=notification_type,
        title=title,
        message=message,
        priority=priority,
    )
    session.add(notification)
    session.flush()
    return notification


# ── Team Management CRUD ──────────────────────────────────────────────────────


def create_team(
    session: Session,
    team_name: str,
    description: str,
    team_lead_id: int,
) -> "Team":
    """Create a new team."""
    from backend.db.models import Team
    
    team = Team(
        team_name=team_name,
        description=description,
        team_lead_id=team_lead_id,
    )
    session.add(team)
    session.flush()
    return team


def add_team_member(
    session: Session,
    team_id: int,
    user_id: int,
    role_in_team: str,
) -> "TeamMember":
    """Add a member to a team."""
    from backend.db.models import TeamMember
    
    member = TeamMember(
        team_id=team_id,
        user_id=user_id,
        role_in_team=role_in_team,
    )
    session.add(member)
    session.flush()
    return member



# ── Additional RBAC CRUD ──────────────────────────────────────────────────────


def assign_role_to_user(session: Session, user_id: int, role_id: int) -> User:
    """Assign a role to a user."""
    user = session.get(User, user_id)
    if not user:
        raise ValueError(f"User {user_id} not found")
    
    user.role_id = role_id
    session.flush()
    return user


# ── Additional Session Management CRUD ────────────────────────────────────────


def cleanup_expired_sessions(session: Session) -> int:
    """Cleanup expired sessions."""
    from backend.db.models import UserSession
    from datetime import datetime, timezone
    
    stmt = select(UserSession).where(UserSession.expires_at < datetime.now(timezone.utc))
    expired_sessions = session.execute(stmt).scalars().all()
    
    count = len(expired_sessions)
    for user_session in expired_sessions:
        session.delete(user_session)
    
    session.flush()
    return count


# ── Additional Approval Workflow CRUD ─────────────────────────────────────────


def reject_request(
    session: Session,
    approval_id: int,
    rejected_by: int,
    rejection_reason: str,
) -> "ApprovalRequest":
    """Reject an approval request."""
    from backend.db.models import ApprovalRequest
    from datetime import datetime, timezone
    
    approval = session.get(ApprovalRequest, approval_id)
    if not approval:
        raise ValueError(f"ApprovalRequest {approval_id} not found")
    
    approval.status = "rejected"
    approval.rejection_reason = rejection_reason
    approval.reviewed_at = datetime.now(timezone.utc)
    session.flush()
    return approval


def add_approval_history(
    session: Session,
    approval_id: int,
    action: str,
    performed_by: int,
    comment: Optional[str] = None,
    changes: Optional[dict] = None,
) -> "ApprovalHistory":
    """Add an approval history entry."""
    from backend.db.models import ApprovalHistory
    
    history = ApprovalHistory(
        approval_id=approval_id,
        action=action,
        performed_by=performed_by,
        comment=comment,
        changes=changes or {},
    )
    session.add(history)
    session.flush()
    return history


def get_pending_approvals(session: Session, assigned_to: int) -> List["ApprovalRequest"]:
    """Get pending approvals assigned to a user."""
    from backend.db.models import ApprovalRequest
    
    stmt = (
        select(ApprovalRequest)
        .where(ApprovalRequest.assigned_to == assigned_to)
        .where(ApprovalRequest.status == "pending")
    )
    return list(session.execute(stmt).scalars().all())


# ── Additional Sprint Planning CRUD ───────────────────────────────────────────


def assign_task_to_user(
    session: Session,
    sprint_id: int,
    user_id: int,
    task_id: int,
    assigned_by: int,
    estimated_hours: Optional[float] = None,
) -> "SprintAssignment":
    """Assign a task to a user in a sprint."""
    from backend.db.models import SprintAssignment
    
    assignment = SprintAssignment(
        sprint_id=sprint_id,
        user_id=user_id,
        task_id=task_id,
        assigned_by=assigned_by,
        estimated_hours=estimated_hours,
    )
    session.add(assignment)
    session.flush()
    return assignment


def add_sprint_risk(
    session: Session,
    sprint_id: int,
    risk_description: str,
    severity: str,
    identified_by: int,
    mitigation_plan: Optional[str] = None,
) -> "SprintRisk":
    """Add a risk to a sprint."""
    from backend.db.models import SprintRisk
    
    risk = SprintRisk(
        sprint_id=sprint_id,
        risk_description=risk_description,
        severity=severity,
        identified_by=identified_by,
        mitigation_plan=mitigation_plan,
    )
    session.add(risk)
    session.flush()
    return risk


def add_sprint_dependency(
    session: Session,
    sprint_id: int,
    dependency_description: str,
    identified_by: int,
    dependency_type: Optional[str] = None,
    external_team: Optional[str] = None,
    due_date: Optional[datetime] = None,
) -> "SprintDependency":
    """Add a dependency to a sprint."""
    from backend.db.models import SprintDependency
    
    dependency = SprintDependency(
        sprint_id=sprint_id,
        dependency_description=dependency_description,
        dependency_type=dependency_type,
        external_team=external_team,
        identified_by=identified_by,
        due_date=due_date,
    )
    session.add(dependency)
    session.flush()
    return dependency


def get_active_sprints(session: Session) -> List["Sprint"]:
    """Get all active sprints."""
    from backend.db.models import Sprint
    
    stmt = select(Sprint).where(Sprint.status == "active")
    return list(session.execute(stmt).scalars().all())


# ── Additional Team Management CRUD ───────────────────────────────────────────


def remove_team_member(session: Session, team_id: int, user_id: int) -> bool:
    """Remove a member from a team."""
    from backend.db.models import TeamMember
    
    stmt = select(TeamMember).where(
        TeamMember.team_id == team_id,
        TeamMember.user_id == user_id,
    )
    member = session.execute(stmt).scalar_one_or_none()
    
    if member:
        session.delete(member)
        session.flush()
        return True
    return False


# ── Additional Settings CRUD ──────────────────────────────────────────────────


def get_user_preference(
    session: Session,
    user_id: int,
    preference_key: str,
) -> Optional["UserPreference"]:
    """Get a user preference."""
    from backend.db.models import UserPreference
    
    return session.get(UserPreference, (user_id, preference_key))


def set_user_preference(
    session: Session,
    user_id: int,
    preference_key: str,
    preference_value: str,
) -> "UserPreference":
    """Set a user preference."""
    from backend.db.models import UserPreference
    
    preference = session.get(UserPreference, (user_id, preference_key))
    if preference:
        preference.preference_value = preference_value
    else:
        preference = UserPreference(
            user_id=user_id,
            preference_key=preference_key,
            preference_value=preference_value,
        )
        session.add(preference)
    
    session.flush()
    return preference


# ── Additional Telegram CRUD ──────────────────────────────────────────────────


def get_chat_state(
    session: Session,
    telegram_user_id: int,
    telegram_chat_id: int,
) -> Optional["TelegramChatState"]:
    """Get Telegram chat state."""
    from backend.db.models import TelegramChatState
    from datetime import datetime, timezone
    
    stmt = select(TelegramChatState).where(
        TelegramChatState.telegram_user_id == telegram_user_id,
        TelegramChatState.telegram_chat_id == telegram_chat_id,
    )
    chat_state = session.execute(stmt).scalar_one_or_none()
    
    # Check if expired
    if chat_state and chat_state.expires_at:
        if chat_state.expires_at < datetime.now(timezone.utc):
            return None
    
    return chat_state


def clear_chat_state(
    session: Session,
    telegram_user_id: int,
    telegram_chat_id: int,
) -> bool:
    """Clear Telegram chat state."""
    from backend.db.models import TelegramChatState
    
    stmt = select(TelegramChatState).where(
        TelegramChatState.telegram_user_id == telegram_user_id,
        TelegramChatState.telegram_chat_id == telegram_chat_id,
    )
    chat_state = session.execute(stmt).scalar_one_or_none()
    
    if chat_state:
        session.delete(chat_state)
        session.flush()
        return True
    return False


def log_telegram_command(
    session: Session,
    telegram_user_id: int,
    telegram_chat_id: int,
    telegram_message_id: int,
    command: str,
    success: bool,
    command_args: Optional[str] = None,
    response_text: Optional[str] = None,
    response_message_id: Optional[int] = None,
    execution_time_ms: Optional[int] = None,
    error_message: Optional[str] = None,
) -> "TelegramCommandHistory":
    """Log a Telegram command."""
    from backend.db.models import TelegramCommandHistory
    
    command_history = TelegramCommandHistory(
        telegram_user_id=telegram_user_id,
        telegram_chat_id=telegram_chat_id,
        telegram_message_id=telegram_message_id,
        command=command,
        command_args=command_args,
        response_text=response_text,
        response_message_id=response_message_id,
        execution_time_ms=execution_time_ms,
        success=success,
        error_message=error_message,
    )
    session.add(command_history)
    session.flush()
    return command_history


def get_pending_telegram_messages(session: Session, limit: int = 100) -> List["TelegramMessageQueue"]:
    """Get pending Telegram messages."""
    from backend.db.models import TelegramMessageQueue
    
    stmt = (
        select(TelegramMessageQueue)
        .where(TelegramMessageQueue.status == "pending")
        .order_by(TelegramMessageQueue.priority.desc(), TelegramMessageQueue.scheduled_at)
        .limit(limit)
    )
    return list(session.execute(stmt).scalars().all())


# ── Additional Notification CRUD ──────────────────────────────────────────────


def mark_notification_read(session: Session, notification_id: int) -> "Notification":
    """Mark a notification as read."""
    from backend.db.models import Notification
    from datetime import datetime, timezone
    
    notification = session.get(Notification, notification_id)
    if not notification:
        raise ValueError(f"Notification {notification_id} not found")
    
    notification.is_read = True
    notification.read_at = datetime.now(timezone.utc)
    session.flush()
    return notification


def get_unread_notifications(session: Session, user_id: int) -> List["Notification"]:
    """Get unread notifications for a user."""
    from backend.db.models import Notification
    
    stmt = (
        select(Notification)
        .where(Notification.user_id == user_id)
        .where(Notification.is_read == False)
        .order_by(Notification.created_at.desc())
    )
    return list(session.execute(stmt).scalars().all())


# ── Logging CRUD ──────────────────────────────────────────────────────────────


def log_activity(
    session: Session,
    user_id: int,
    action: str,
    entity_type: str,
    entity_id: int,
    details: Optional[dict] = None,
    ip_address: Optional[str] = None,
    user_agent: Optional[str] = None,
) -> "ActivityLog":
    """Log user activity."""
    from backend.db.models import ActivityLog
    
    activity = ActivityLog(
        user_id=user_id,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        details=details or {},
        ip_address=ip_address,
        user_agent=user_agent,
    )
    session.add(activity)
    session.flush()
    return activity


def log_error(
    session: Session,
    error_type: str,
    error_message: str,
    severity: str,
    stack_trace: Optional[str] = None,
    user_id: Optional[int] = None,
    request_path: Optional[str] = None,
    request_method: Optional[str] = None,
    request_data: Optional[dict] = None,
    ip_address: Optional[str] = None,
    user_agent: Optional[str] = None,
) -> "ErrorLog":
    """Log an error."""
    from backend.db.models import ErrorLog
    
    error = ErrorLog(
        error_type=error_type,
        error_message=error_message,
        stack_trace=stack_trace,
        severity=severity,
        user_id=user_id,
        request_path=request_path,
        request_method=request_method,
        request_data=request_data or {},
        ip_address=ip_address,
        user_agent=user_agent,
    )
    session.add(error)
    session.flush()
    return error


def resolve_error(session: Session, error_id: int, resolved_by: int) -> "ErrorLog":
    """Mark an error as resolved."""
    from backend.db.models import ErrorLog
    from datetime import datetime, timezone
    
    error = session.get(ErrorLog, error_id)
    if not error:
        raise ValueError(f"ErrorLog {error_id} not found")
    
    error.resolved = True
    error.resolved_by = resolved_by
    error.resolved_at = datetime.now(timezone.utc)
    session.flush()
    return error


# ── File Storage CRUD ─────────────────────────────────────────────────────────


def create_file_record(
    session: Session,
    file_name: str,
    file_path: str,
    uploaded_by: int,
    file_type: Optional[str] = None,
    file_size: Optional[int] = None,
    mime_type: Optional[str] = None,
    entity_type: Optional[str] = None,
    entity_id: Optional[int] = None,
) -> "FileStorage":
    """Create a file storage record."""
    from backend.db.models import FileStorage
    
    file_record = FileStorage(
        file_name=file_name,
        file_path=file_path,
        file_type=file_type,
        file_size=file_size,
        mime_type=mime_type,
        entity_type=entity_type,
        entity_id=entity_id,
        uploaded_by=uploaded_by,
    )
    session.add(file_record)
    session.flush()
    return file_record


def soft_delete_file(session: Session, file_id: int) -> "FileStorage":
    """Soft delete a file record."""
    from backend.db.models import FileStorage
    from datetime import datetime, timezone
    
    file_record = session.get(FileStorage, file_id)
    if not file_record:
        raise ValueError(f"FileStorage {file_id} not found")
    
    file_record.is_deleted = True
    file_record.deleted_at = datetime.now(timezone.utc)
    session.flush()
    return file_record


# ── Utility CRUD ──────────────────────────────────────────────────────────────


def get_user_by_id(session: Session, user_id: int) -> Optional[User]:
    """Get user by ID."""
    return session.get(User, user_id)


def get_all_users(session: Session) -> List[User]:
    """Get all users."""
    stmt = select(User)
    return list(session.execute(stmt).scalars().all())


def count_users(session: Session) -> int:
    """Count total users."""
    from sqlalchemy import func
    stmt = select(func.count()).select_from(User)
    return session.execute(stmt).scalar()


def count_roles(session: Session) -> int:
    """Count total roles."""
    from backend.db.models import Role
    from sqlalchemy import func
    stmt = select(func.count()).select_from(Role)
    return session.execute(stmt).scalar()


def count_permissions(session: Session) -> int:
    """Count total permissions."""
    from backend.db.models import Permission
    from sqlalchemy import func
    stmt = select(func.count()).select_from(Permission)
    return session.execute(stmt).scalar()


def count_settings(session: Session) -> int:
    """Count total system settings."""
    from backend.db.models import SystemSetting
    from sqlalchemy import func
    stmt = select(func.count()).select_from(SystemSetting)
    return session.execute(stmt).scalar()


def count_tables(session: Session) -> int:
    """Count total tables in database (PostgreSQL specific)."""
    from sqlalchemy import text
    stmt = text("""
        SELECT COUNT(*)
        FROM information_schema.tables
        WHERE table_schema = 'public'
        AND table_type = 'BASE TABLE'
    """)
    return session.execute(stmt).scalar()



# ── Jira Synchronization Functions ───────────────────────────────────────────


def verify_jira_ticket_exists(jira_key: str) -> bool:
    """
    Verify that a Jira ticket actually exists.
    
    This function checks if a ticket exists in Jira by attempting to fetch it.
    Used to detect when tickets have been manually deleted from Jira.
    
    Args:
        jira_key: Jira ticket key (e.g., 'SP-123')
    
    Returns:
        True if ticket exists in Jira, False otherwise
    """
    from backend.tools.jira_client import JiraManager
    import logging
    
    logger = logging.getLogger(__name__)
    
    try:
        jira = JiraManager()
        jira.client.issue(jira_key)
        return True
    except Exception as e:
        logger.debug(f"Ticket {jira_key} not found in Jira: {e}")
        return False


def sync_epic_with_jira(session: Session, epic_id: int) -> bool:
    """
    Verify epic exists in Jira and remove from database if not.
    
    Args:
        session: Database session
        epic_id: Epic ID
    
    Returns:
        True if epic exists in Jira, False if deleted from database
    """
    import logging
    logger = logging.getLogger(__name__)
    
    epic = session.query(Epic).filter(Epic.id == epic_id).first()
    
    if not epic:
        return False
    
    if not epic.jira_key:
        # No Jira key, can't verify
        return True
    
    # Check if exists in Jira
    if not verify_jira_ticket_exists(epic.jira_key):
        logger.warning(f"Epic {epic.jira_key} not found in Jira, removing from database")
        session.delete(epic)
        session.commit()
        return False
    
    return True


def sync_story_with_jira(session: Session, story_id: int) -> bool:
    """
    Verify story exists in Jira and remove from database if not.
    
    Args:
        session: Database session
        story_id: Story ID
    
    Returns:
        True if story exists in Jira, False if deleted from database
    """
    import logging
    logger = logging.getLogger(__name__)
    
    story = session.query(Story).filter(Story.id == story_id).first()
    
    if not story:
        return False
    
    if not story.jira_key:
        # No Jira key, can't verify
        return True
    
    # Check if exists in Jira
    if not verify_jira_ticket_exists(story.jira_key):
        logger.warning(f"Story {story.jira_key} not found in Jira, removing from database")
        session.delete(story)
        session.commit()
        return False
    
    return True


def sync_task_with_jira(session: Session, task_id: int) -> bool:
    """
    Verify task exists in Jira and remove from database if not.
    
    Args:
        session: Database session
        task_id: Task ID
    
    Returns:
        True if task exists in Jira, False if deleted from database
    """
    import logging
    logger = logging.getLogger(__name__)
    
    task = session.query(BacklogTask).filter(BacklogTask.id == task_id).first()
    
    if not task:
        return False
    
    if not task.jira_key:
        # No Jira key, can't verify
        return True
    
    # Check if exists in Jira
    if not verify_jira_ticket_exists(task.jira_key):
        logger.warning(f"Task {task.jira_key} not found in Jira, removing from database")
        session.delete(task)
        session.commit()
        return False
    
    return True


def sync_all_with_jira(session: Session) -> dict:
    """
    Sync all database records with Jira.
    
    Removes records that don't exist in Jira anymore.
    This should be run periodically (e.g., daily) to keep database clean.
    
    Args:
        session: Database session
    
    Returns:
        dict with sync statistics:
        - epics_checked: Number of epics checked
        - epics_deleted: Number of epics deleted
        - stories_checked: Number of stories checked
        - stories_deleted: Number of stories deleted
        - tasks_checked: Number of tasks checked
        - tasks_deleted: Number of tasks deleted
    """
    import logging
    logger = logging.getLogger(__name__)
    
    stats = {
        'epics_checked': 0,
        'epics_deleted': 0,
        'stories_checked': 0,
        'stories_deleted': 0,
        'tasks_checked': 0,
        'tasks_deleted': 0
    }
    
    logger.info("Starting database sync with Jira...")
    
    # Check epics
    epics = session.query(Epic).filter(Epic.jira_key.isnot(None)).all()
    stats['epics_checked'] = len(epics)
    logger.info(f"Checking {len(epics)} epic(s)...")
    
    for epic in epics:
        if not verify_jira_ticket_exists(epic.jira_key):
            logger.warning(f"Deleting stale epic: {epic.jira_key} (ID: {epic.id})")
            session.delete(epic)
            stats['epics_deleted'] += 1
    
    # Check stories
    stories = session.query(Story).filter(Story.jira_key.isnot(None)).all()
    stats['stories_checked'] = len(stories)
    logger.info(f"Checking {len(stories)} story(ies)...")
    
    for story in stories:
        if not verify_jira_ticket_exists(story.jira_key):
            logger.warning(f"Deleting stale story: {story.jira_key} (ID: {story.id})")
            session.delete(story)
            stats['stories_deleted'] += 1
    
    # Check tasks
    tasks = session.query(BacklogTask).filter(BacklogTask.jira_key.isnot(None)).all()
    stats['tasks_checked'] = len(tasks)
    logger.info(f"Checking {len(tasks)} task(s)...")
    
    for task in tasks:
        if not verify_jira_ticket_exists(task.jira_key):
            logger.warning(f"Deleting stale task: {task.jira_key} (ID: {task.id})")
            session.delete(task)
            stats['tasks_deleted'] += 1
    
    # Commit all deletions
    session.commit()
    
    logger.info(f"Sync complete: Deleted {stats['epics_deleted']} epics, "
                f"{stats['stories_deleted']} stories, {stats['tasks_deleted']} tasks")
    
    return stats
