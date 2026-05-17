"""
Project selection service for pipeline gating.

Every transcript-driven pipeline must pause until the PM selects either:
- an existing Scrum-compatible Jira project, or
- a new Scrum project to create.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from backend.db.connection import get_session
from backend.db.models import ApprovalRequest, User
from backend.telegram.services.approval_service import ApprovalService
from backend.tools.jira_client import JiraManager

logger = logging.getLogger(__name__)


PIPELINE_LABELS = {
    "backlog": "Backlog",
    "sprint": "Sprint Planning",
    "standup": "Standup",
}


def create_project_selection_approval(
    *,
    pipeline_type: str,
    requested_by_user_id: int,
    assigned_to_user_id: int,
    request_data: Dict[str, Any],
    priority: str = "high",
) -> int:
    """
    Create an approval that pauses execution until the PM selects a Jira Scrum project.

    This approval intentionally has no expiry. The run should resume whenever the PM
    responds.
    """
    payload = dict(request_data)
    payload["pipeline_type"] = pipeline_type

    with get_session() as session:
        approval = ApprovalRequest(
            request_type="project_selection",
            entity_type="jira_project",
            entity_id=0,
            requested_by=requested_by_user_id,
            assigned_to=assigned_to_user_id,
            status="pending",
            priority=priority,
            request_data=payload,
            original_data=payload,
            created_at=datetime.now(timezone.utc),
            expires_at=None,
        )
        session.add(approval)
        session.commit()
        session.refresh(approval)

        approval_id = approval.approval_id
        logger.info(
            "Created project selection approval #%s for pipeline=%s",
            approval_id,
            pipeline_type,
        )

        assigned_user = session.query(User).filter(
            User.id == assigned_to_user_id
        ).first()
        if assigned_user and assigned_user.telegram_user_id:
            ApprovalService._send_telegram_notification(
                telegram_user_id=assigned_user.telegram_user_id,
                telegram_chat_id=assigned_user.telegram_chat_id,
                approval_id=approval_id,
            )
        else:
            logger.warning(
                "User %s has no Telegram account linked for project selection approval #%s",
                assigned_to_user_id,
                approval_id,
            )

        return approval_id


def get_project_selection_summary(data: Dict[str, Any]) -> Dict[str, Any]:
    pipeline_type = data.get("pipeline_type", "unknown")
    summary = dict(data.get("summary", {}))
    summary["pipeline_label"] = PIPELINE_LABELS.get(pipeline_type, pipeline_type.title())
    return summary


def list_scrum_projects() -> List[Dict[str, Any]]:
    """
    Return Jira projects that are plausible targets for ScrumPilot.

    We keep the picker broad so PMs can select projects that already exist even
    when board discovery is flaky or the Scrum board has not been surfaced yet.
    Strict validation still happens later during selection and execution.
    """
    jira = JiraManager()
    projects: List[Dict[str, Any]] = []

    for project in jira.client.projects():
        project_key = project.key
        compatibility = jira.validate_scrum_project(project_key)
        issue_types_ok = not compatibility.get("problems") or all(
            "Missing issue types" not in problem
            for problem in compatibility.get("problems", [])
        )
        if issue_types_ok:
            projects.append({
                "key": project_key,
                "name": project.name,
                "valid": compatibility.get("valid", False),
                "boards": compatibility.get("boards", []),
                "problems": compatibility.get("problems", []),
            })

    projects.sort(key=lambda item: item["key"])
    return projects
