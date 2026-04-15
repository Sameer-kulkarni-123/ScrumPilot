"""
High-level storage service for ScrumPilot.
Provides a clean interface for agents and pipelines to persist data.
"""

from datetime import datetime, timezone
from typing import Optional, List, Dict, Any

from backend.db.connection import get_session
from backend.db import crud
from backend.db.models import (
    MeetingType,
    RunType,
    RunStatus,
    ArtifactType,
    ActionType,
    ExecutionStatus,
)


class StorageService:
    """
    High-level storage service that wraps database CRUD operations.
    Provides a clean API for agents and pipelines.
    """

    # ── Meeting Management ────────────────────────────────────────────────────

    def create_meeting(
        self,
        meeting_type: str,
        meeting_date: datetime,
        title: Optional[str] = None,
        source_platform: str = "google_meet",
        source_meeting_key: Optional[str] = None,
        started_at: Optional[datetime] = None,
        ended_at: Optional[datetime] = None,
        status: str = "created",
    ) -> int:
        """
        Create a new meeting record.
        
        Args:
            meeting_type: "pm" or "scrum"
            meeting_date: Date of the meeting
            title: Optional meeting title
            source_platform: Platform where meeting occurred (default: "google_meet")
            source_meeting_key: External meeting identifier
            started_at: Meeting start timestamp
            ended_at: Meeting end timestamp
            status: Meeting status (default: "created")
        
        Returns:
            Meeting ID
        """
        # Normalize to lowercase for case-insensitive comparison
        meeting_type_lower = meeting_type.lower()
        meeting_type_enum = MeetingType.PM if meeting_type_lower == "pm" else MeetingType.SCRUM
        meeting_type_value = meeting_type_enum.value
        
        with get_session() as session:
            meeting = crud.create_meeting(
                session=session,
                meeting_type=meeting_type_value,
                meeting_date=meeting_date,
                title=title,
                source_platform=source_platform,
                source_meeting_key=source_meeting_key,
                started_at=started_at,
                ended_at=ended_at,
                status=status,
            )
            session.commit()
            return meeting.id

    def get_meeting(self, meeting_id: int) -> Optional[Dict[str, Any]]:
        """Get meeting by ID."""
        with get_session() as session:
            meeting = crud.get_meeting_by_id(session, meeting_id)
            if not meeting:
                return None
            
            return {
                "id": meeting.id,
                "meeting_uid": str(meeting.meeting_uid),
                "meeting_type": meeting.meeting_type.value,
                "title": meeting.title,
                "meeting_date": meeting.meeting_date,
                "started_at": meeting.started_at,
                "ended_at": meeting.ended_at,
                "source_platform": meeting.source_platform,
                "source_meeting_key": meeting.source_meeting_key,
                "status": meeting.status,
                "created_at": meeting.created_at,
                "updated_at": meeting.updated_at,
            }

    # ── Processing Run Management ─────────────────────────────────────────────

    def start_processing_run(
        self,
        meeting_id: int,
        run_type: str,
    ) -> int:
        """
        Start a new processing run for a meeting.
        
        Args:
            meeting_id: ID of the meeting
            run_type: "pm_backlog" or "scrum_actions"
        
        Returns:
            Processing run ID
        """
        # Normalize to lowercase for case-insensitive comparison
        run_type_lower = run_type.lower()
        run_type_enum = (
            RunType.PM_BACKLOG if run_type_lower == "pm_backlog" else RunType.SCRUM_ACTIONS
        )
        
        with get_session() as session:
            run = crud.create_processing_run(
                session=session,
                meeting_id=meeting_id,
                run_type=run_type_enum.value,
            )
            session.commit()
            return run.id

    def complete_processing_run(self, run_id: int) -> None:
        """Mark a processing run as completed."""
        with get_session() as session:
            crud.update_processing_run_status(
                session=session,
                run_id=run_id,
                status=RunStatus.COMPLETED.value,
                finished_at=datetime.now(timezone.utc),
            )
            session.commit()

    def fail_processing_run(self, run_id: int, error_message: str) -> None:
        """Mark a processing run as failed."""
        with get_session() as session:
            crud.update_processing_run_status(
                session=session,
                run_id=run_id,
                status=RunStatus.FAILED.value,
                error_message=error_message,
                finished_at=datetime.now(timezone.utc),
            )
            session.commit()

    # ── Artifact Management ───────────────────────────────────────────────────

    def save_artifact(
        self,
        meeting_id: int,
        artifact_type: str,
        processing_run_id: Optional[int] = None,
        file_path: Optional[str] = None,
        text_content: Optional[str] = None,
        json_content: Optional[dict] = None,
        metadata: Optional[dict] = None,
    ) -> int:
        """
        Save a meeting artifact.
        
        Args:
            meeting_id: ID of the meeting
            artifact_type: Type of artifact (audio, transcript, diarization, etc.)
            processing_run_id: Optional processing run ID
            file_path: Path to artifact file
            text_content: Text content of artifact
            json_content: JSON content of artifact
            metadata: Additional metadata
        
        Returns:
            Artifact ID
        """
        artifact_type_enum = ArtifactType[artifact_type.upper()]
        
        with get_session() as session:
            artifact = crud.create_artifact(
                session=session,
                meeting_id=meeting_id,
                artifact_type=artifact_type_enum.value,
                processing_run_id=processing_run_id,
                file_path=file_path,
                text_content=text_content,
                json_content=json_content,
                metadata=metadata,
            )
            session.commit()
            return artifact.id

    # ── User Management ───────────────────────────────────────────────────────

    def upsert_user(
        self,
        display_name: str,
        email: Optional[str] = None,
        jira_account_id: Optional[str] = None,
        jira_display_name: Optional[str] = None,
    ) -> int:
        """
        Create or update a user record.
        
        Args:
            display_name: User's display name from transcript
            email: User's email address
            jira_account_id: Jira account ID
            jira_display_name: Display name in Jira
        
        Returns:
            User ID
        """
        with get_session() as session:
            user = crud.upsert_user(
                session=session,
                display_name=display_name,
                email=email,
                jira_account_id=jira_account_id,
                jira_display_name=jira_display_name,
            )
            session.commit()
            return user.id

    def find_user_by_name(self, name: str) -> Optional[int]:
        """Find user ID by display name (case-insensitive)."""
        with get_session() as session:
            user = crud.find_user_by_name(session, name)
            return user.id if user else None

    # ── Scrum Actions ─────────────────────────────────────────────────────────

    def save_scrum_actions(
        self,
        meeting_id: int,
        processing_run_id: int,
        actions: List[Dict[str, Any]],
    ) -> List[int]:
        """
        Save scrum actions extracted from a meeting.
        
        Args:
            meeting_id: ID of the meeting
            processing_run_id: ID of the processing run
            actions: List of action dicts from ScrumExtractorAgent
        
        Returns:
            List of created action IDs
        """
        action_ids = []
        
        with get_session() as session:
            for action_dict in actions:
                # Map action field to action_type enum
                action_type_str = action_dict.get("action", "").upper()
                action_type_enum = ActionType[action_type_str]
                
                # Try to resolve assignee to user ID
                assignee_raw = action_dict.get("assignee")
                resolved_user_id = None
                if assignee_raw:
                    user = crud.find_user_by_name(session, assignee_raw)
                    if user:
                        resolved_user_id = user.id
                
                action = crud.create_scrum_action(
                    session=session,
                    meeting_id=meeting_id,
                    processing_run_id=processing_run_id,
                    action_type=action_type_enum.value,
                    summary=action_dict.get("summary", ""),
                    ticket_key=action_dict.get("ticket_key"),
                    description=action_dict.get("description"),
                    status=action_dict.get("status"),
                    assignee_raw=assignee_raw,
                    resolved_user_id=resolved_user_id,
                    comment=action_dict.get("comment"),
                    execution_status=ExecutionStatus.PENDING.value,
                )
                action_ids.append(action.id)
            
            session.commit()
        
        return action_ids

    def update_scrum_action_execution(
        self,
        action_id: int,
        execution_status: str,
        jira_response: Optional[dict] = None,
    ) -> None:
        """Update scrum action execution status after Jira execution."""
        status_enum = ExecutionStatus[execution_status.upper()]
        
        with get_session() as session:
            crud.update_scrum_action_execution(
                session=session,
                action_id=action_id,
                execution_status=status_enum.value,
                jira_response=jira_response,
            )
            session.commit()

    # ── PM Backlog (Epics/Stories/Tasks) ──────────────────────────────────────

    def save_extracted_epics(
        self,
        meeting_id: int,
        processing_run_id: int,
        extracted_epics_payload: Dict[str, Any],
    ) -> List[int]:
        """
        Save extracted epics from PM meeting.
        
        Expected payload structure:
        {
            "meeting_date": "YYYY-MM-DD",
            "epics": [
                {
                    "title": "string",
                    "description": "string",
                    "wsjf": {
                        "business_value": 1-10,
                        "time_criticality": 1-10,
                        "risk_reduction": 1-10,
                        "job_size": 1-10,
                        "wsjf_score": float
                    },
                    "mentioned_features": ["string"]
                }
            ]
        }
        
        Returns:
            List of created epic IDs
        """
        epic_ids = []
        
        with get_session() as session:
            epics_data = extracted_epics_payload.get("epics", [])
            
            for idx, epic_dict in enumerate(epics_data):
                wsjf = epic_dict.get("wsjf", {})
                
                epic = crud.create_epic(
                    session=session,
                    meeting_id=meeting_id,
                    processing_run_id=processing_run_id,
                    title=epic_dict.get("title", ""),
                    description=epic_dict.get("description"),
                    business_value=wsjf.get("business_value", 1),
                    time_criticality=wsjf.get("time_criticality", 1),
                    risk_reduction=wsjf.get("risk_reduction", 1),
                    job_size=wsjf.get("job_size", 1),
                    wsjf_score=wsjf.get("wsjf_score", 0.0),
                    mentioned_features=epic_dict.get("mentioned_features", []),
                    priority_rank=idx + 1,
                )
                epic_ids.append(epic.id)
            
            session.commit()
        
        return epic_ids

    def save_decomposed_backlog(
        self,
        meeting_id: int,
        processing_run_id: int,
        decomposed_backlog_payload: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Save decomposed backlog (epic with stories and tasks).
        
        Expected payload structure:
        {
            "epic": {
                "title": "string",
                "wsjf_score": float,
                "stories": [
                    {
                        "title": "string",
                        "description": "string",
                        "acceptance_criteria": ["string"],
                        "tasks": [
                            {
                                "title": "string",
                                "description": "string",
                                "estimated_hours": int
                            }
                        ]
                    }
                ]
            }
        }
        
        Returns:
            Dict with epic_id, story_ids, task_ids
        """
        result = {"epic_id": None, "story_ids": [], "task_ids": []}
        
        with get_session() as session:
            epic_data = decomposed_backlog_payload.get("epic", {})
            
            # Create epic (simplified - assumes WSJF already calculated)
            epic = crud.create_epic(
                session=session,
                meeting_id=meeting_id,
                processing_run_id=processing_run_id,
                title=epic_data.get("title", ""),
                description=epic_data.get("description"),
                business_value=epic_data.get("business_value", 5),
                time_criticality=epic_data.get("time_criticality", 5),
                risk_reduction=epic_data.get("risk_reduction", 5),
                job_size=epic_data.get("job_size", 5),
                wsjf_score=epic_data.get("wsjf_score", 0.0),
                mentioned_features=[],
            )
            result["epic_id"] = epic.id
            
            # Create stories
            stories_data = epic_data.get("stories", [])
            for story_idx, story_dict in enumerate(stories_data):
                story = crud.create_story(
                    session=session,
                    epic_id=epic.id,
                    meeting_id=meeting_id,
                    processing_run_id=processing_run_id,
                    title=story_dict.get("title", ""),
                    description=story_dict.get("description"),
                    acceptance_criteria=story_dict.get("acceptance_criteria", []),
                    sequence_no=story_idx + 1,
                )
                result["story_ids"].append(story.id)
                
                # Create tasks
                tasks_data = story_dict.get("tasks", [])
                for task_dict in tasks_data:
                    task = crud.create_backlog_task(
                        session=session,
                        story_id=story.id,
                        meeting_id=meeting_id,
                        processing_run_id=processing_run_id,
                        title=task_dict.get("title", ""),
                        description=task_dict.get("description"),
                        estimated_hours=task_dict.get("estimated_hours"),
                    )
                    result["task_ids"].append(task.id)
            
            session.commit()
        
        return result

    # ── Jira Sync ─────────────────────────────────────────────────────────────

    def set_epic_jira_key(
        self,
        epic_id: int,
        jira_key: str,
        jira_status: Optional[str] = None,
    ) -> None:
        """Update epic with Jira key after creation."""
        with get_session() as session:
            crud.update_epic_jira_info(
                session=session,
                epic_id=epic_id,
                jira_key=jira_key,
                jira_status=jira_status,
                jira_synced_at=datetime.now(timezone.utc),
            )
            session.commit()

    def set_story_jira_key(
        self,
        story_id: int,
        jira_key: str,
        jira_status: Optional[str] = None,
    ) -> None:
        """Update story with Jira key after creation."""
        with get_session() as session:
            crud.update_story_jira_info(
                session=session,
                story_id=story_id,
                jira_key=jira_key,
                jira_status=jira_status,
                jira_synced_at=datetime.now(timezone.utc),
            )
            session.commit()

    def set_task_jira_key(
        self,
        task_id: int,
        jira_key: str,
        jira_status: Optional[str] = None,
    ) -> None:
        """Update task with Jira key after creation."""
        with get_session() as session:
            crud.update_task_jira_info(
                session=session,
                task_id=task_id,
                jira_key=jira_key,
                jira_status=jira_status,
                jira_synced_at=datetime.now(timezone.utc),
            )
            session.commit()

    # ── Query Methods ─────────────────────────────────────────────────────────

    def get_meeting_with_hierarchy(self, meeting_id: int) -> Optional[Dict[str, Any]]:
        """
        Get meeting with full hierarchy (epics, stories, tasks, actions).
        
        Returns:
            Dict with meeting data and all related entities
        """
        with get_session() as session:
            meeting = crud.get_meeting_by_id(session, meeting_id)
            if not meeting:
                return None
            
            result = {
                "id": meeting.id,
                "meeting_uid": str(meeting.meeting_uid),
                "meeting_type": meeting.meeting_type.value,
                "title": meeting.title,
                "meeting_date": meeting.meeting_date,
                "status": meeting.status,
                "epics": [],
                "scrum_actions": [],
            }
            
            # Load epics with stories and tasks
            for epic in meeting.epics:
                epic_dict = {
                    "id": epic.id,
                    "title": epic.title,
                    "wsjf_score": float(epic.wsjf_score),
                    "jira_key": epic.jira_key,
                    "stories": [],
                }
                
                for story in epic.stories:
                    story_dict = {
                        "id": story.id,
                        "title": story.title,
                        "jira_key": story.jira_key,
                        "tasks": [],
                    }
                    
                    for task in story.tasks:
                        task_dict = {
                            "id": task.id,
                            "title": task.title,
                            "jira_key": task.jira_key,
                            "estimated_hours": float(task.estimated_hours) if task.estimated_hours else None,
                        }
                        story_dict["tasks"].append(task_dict)
                    
                    epic_dict["stories"].append(story_dict)
                
                result["epics"].append(epic_dict)
            
            # Load scrum actions
            for action in meeting.scrum_actions:
                action_dict = {
                    "id": action.id,
                    "action_type": action.action_type.value,
                    "summary": action.summary,
                    "ticket_key": action.ticket_key,
                    "execution_status": action.execution_status.value,
                }
                result["scrum_actions"].append(action_dict)
            
            return result


    # ── RBAC Methods ──────────────────────────────────────────────────────────

    def get_user_role(self, user_id: int) -> Optional[str]:
        """Get user's role name."""
        with get_session() as session:
            from backend.db.models import User
            user = session.get(User, user_id)
            if user and user.role:
                return user.role.role_name
            return None

    def check_permission(self, user_id: int, resource: str, action: str) -> bool:
        """Check if user has specific permission."""
        with get_session() as session:
            return crud.check_permission(session, user_id, resource, action)

    # ── Session Management ────────────────────────────────────────────────────

    def create_user_session(
        self,
        user_id: int,
        ip_address: str,
        user_agent: str,
        timeout_minutes: int = 480,
    ) -> str:
        """Create a user session and return session_id."""
        from datetime import datetime, timezone, timedelta
        
        expires_at = datetime.now(timezone.utc) + timedelta(minutes=timeout_minutes)
        
        with get_session() as session:
            user_session = crud.create_session(
                session=session,
                user_id=user_id,
                expires_at=expires_at,
                ip_address=ip_address,
                user_agent=user_agent,
            )
            session.commit()
            return user_session.session_id

    def validate_session(self, session_id: str) -> Optional[int]:
        """Validate session and return user_id if valid."""
        from datetime import datetime, timezone
        
        with get_session() as session:
            user_session = crud.get_session(session, session_id)
            if user_session and user_session.is_active:
                if user_session.expires_at > datetime.now(timezone.utc):
                    return user_session.user_id
        return None

    # ── Approval Workflow ─────────────────────────────────────────────────────

    def create_approval(
        self,
        request_type: str,
        entity_type: str,
        entity_id: int,
        requested_by: int,
        assigned_to: int,
        request_data: dict,
        priority: str = "medium",
    ) -> int:
        """Create an approval request and return approval_id."""
        with get_session() as session:
            approval = crud.create_approval_request(
                session=session,
                request_type=request_type,
                entity_type=entity_type,
                entity_id=entity_id,
                requested_by=requested_by,
                assigned_to=assigned_to,
                request_data=request_data,
                priority=priority,
            )
            session.commit()
            return approval.approval_id

    def approve_request(
        self,
        approval_id: int,
        approved_by: int,
        approved_data: dict,
    ) -> bool:
        """Approve an approval request."""
        with get_session() as session:
            crud.approve_request(
                session=session,
                approval_id=approval_id,
                approved_by=approved_by,
                approved_data=approved_data,
            )
            session.commit()
            return True

    # ── Sprint Planning ───────────────────────────────────────────────────────

    def create_sprint(
        self,
        sprint_name: str,
        sprint_goal: str,
        start_date: datetime,
        end_date: datetime,
        team_id: int,
        created_by: int,
    ) -> int:
        """Create a sprint and return sprint_id."""
        with get_session() as session:
            sprint = crud.create_sprint(
                session=session,
                sprint_name=sprint_name,
                sprint_goal=sprint_goal,
                start_date=start_date,
                end_date=end_date,
                team_id=team_id,
                created_by=created_by,
            )
            session.commit()
            return sprint.sprint_id

    def add_story_to_sprint(
        self,
        sprint_id: int,
        story_id: int,
        committed_by: int,
    ) -> bool:
        """Add a story to a sprint."""
        with get_session() as session:
            crud.add_story_to_sprint(
                session=session,
                sprint_id=sprint_id,
                story_id=story_id,
                committed_by=committed_by,
            )
            session.commit()
            return True

    # ── Settings ──────────────────────────────────────────────────────────────

    def get_setting(self, setting_key: str) -> Optional[str]:
        """Get a system setting value."""
        with get_session() as session:
            setting = crud.get_setting(session, setting_key)
            return setting.setting_value if setting else None

    def set_setting(
        self,
        setting_key: str,
        setting_value: str,
        updated_by: int,
    ) -> bool:
        """Set a system setting value."""
        with get_session() as session:
            crud.set_setting(
                session=session,
                setting_key=setting_key,
                setting_value=setting_value,
                updated_by=updated_by,
            )
            session.commit()
            return True

    # ── Telegram ──────────────────────────────────────────────────────────────

    def update_telegram_state(
        self,
        telegram_user_id: int,
        telegram_chat_id: int,
        current_state: str,
        state_data: dict,
    ) -> bool:
        """Update Telegram chat state."""
        with get_session() as session:
            crud.upsert_chat_state(
                session=session,
                telegram_user_id=telegram_user_id,
                telegram_chat_id=telegram_chat_id,
                current_state=current_state,
                state_data=state_data,
            )
            session.commit()
            return True

    def queue_telegram_message(
        self,
        telegram_user_id: int,
        telegram_chat_id: int,
        message_type: str,
        message_text: str,
        priority: int = 5,
    ) -> int:
        """Queue a Telegram message and return queue_id."""
        with get_session() as session:
            message = crud.queue_telegram_message(
                session=session,
                telegram_user_id=telegram_user_id,
                telegram_chat_id=telegram_chat_id,
                message_type=message_type,
                message_text=message_text,
                priority=priority,
            )
            session.commit()
            return message.queue_id

    # ── Notifications ─────────────────────────────────────────────────────────

    def create_notification(
        self,
        user_id: int,
        notification_type: str,
        title: str,
        message: str,
        priority: str = "normal",
    ) -> int:
        """Create a notification and return notification_id."""
        with get_session() as session:
            notification = crud.create_notification(
                session=session,
                user_id=user_id,
                notification_type=notification_type,
                title=title,
                message=message,
                priority=priority,
            )
            session.commit()
            return notification.notification_id

    # ── Team Management ───────────────────────────────────────────────────────

    def create_team(
        self,
        team_name: str,
        description: str,
        team_lead_id: int,
    ) -> int:
        """Create a team and return team_id."""
        with get_session() as session:
            team = crud.create_team(
                session=session,
                team_name=team_name,
                description=description,
                team_lead_id=team_lead_id,
            )
            session.commit()
            return team.team_id

    def add_team_member(
        self,
        team_id: int,
        user_id: int,
        role_in_team: str,
    ) -> bool:
        """Add a member to a team."""
        with get_session() as session:
            crud.add_team_member(
                session=session,
                team_id=team_id,
                user_id=user_id,
                role_in_team=role_in_team,
            )
            session.commit()
            return True


# Singleton instance for easy import
storage = StorageService()
