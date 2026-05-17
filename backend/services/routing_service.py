"""
RoutingService — Project registry checks, approval creation, routing card helpers.

Used by the backlog pipeline and JiraCreatorAgent to:
  - Verify project keys against the DB registry and live Jira
  - Create ApprovalRequest records for new-project creation
  - Build structured data for the Telegram routing card
  - Persist routing metadata on Epic / Story / Task / ScrumAction rows
"""

import logging
from typing import Any, Dict, List, Optional, TYPE_CHECKING

from backend.tools.jira_routing import (
    KEYWORD_HIGH_CONFIDENCE,
    KEYWORD_MEDIUM_CONFIDENCE,
    RoutingDecision,
)

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


# ── Project registry helpers ──────────────────────────────────────────────────


def get_known_project_keys(session: "Session") -> List[str]:
    """Return all active project keys from the local registry."""
    try:
        from backend.db.models import JiraProjectRegistry
        rows = session.query(JiraProjectRegistry.project_key).filter(
            JiraProjectRegistry.status == "active"
        ).all()
        return [r[0] for r in rows]
    except Exception as e:
        logger.warning(f"Could not query jira_projects_registry: {e}")
        return []


def is_project_known(project_key: str, session: "Session") -> bool:
    """Return True if the project key is active in the local registry."""
    try:
        from backend.db.models import JiraProjectRegistry
        return session.query(JiraProjectRegistry).filter(
            JiraProjectRegistry.project_key == project_key,
            JiraProjectRegistry.status == "active",
        ).count() > 0
    except Exception as e:
        logger.warning(f"Registry check failed for '{project_key}': {e}")
        return False


def register_project(
    project_key: str,
    name: str,
    keywords: Optional[List[str]] = None,
    session: Optional["Session"] = None,
    auto_created: bool = False,
) -> bool:
    """
    Insert a new project into the registry.

    Returns True on success, False on failure (e.g. already exists).
    """
    if session is None:
        return False
    try:
        from backend.db.models import JiraProjectRegistry
        from sqlalchemy import select
        existing = session.query(JiraProjectRegistry).filter(
            JiraProjectRegistry.project_key == project_key
        ).first()
        if existing:
            if existing.status != "active":
                existing.status = "active"
                session.commit()
            return True
        row = JiraProjectRegistry(
            project_key=project_key,
            name=name,
            keywords=keywords or [],
            status="active",
            auto_created=auto_created,
            registry_metadata={},
        )
        session.add(row)
        session.commit()
        logger.info(f"Registered new project '{project_key}' in registry")
        return True
    except Exception as e:
        logger.error(f"Failed to register project '{project_key}': {e}")
        session.rollback()
        return False


# ── Approval creation helpers ─────────────────────────────────────────────────


def build_project_creation_approval_data(
    decision: RoutingDecision,
    items: List[Dict[str, str]],
) -> Dict[str, Any]:
    """Build request_data dict for an ApprovalRequest of type 'project_creation'."""
    sample_summaries = [i.get("summary", "") for i in items[:5]]
    return {
        "suggested_key": decision.project_key,
        "suggested_name": decision.suggested_project_name or decision.project_name or decision.project_key,
        "confidence": round(decision.confidence, 3),
        "items_count": len(items),
        "sample_summaries": sample_summaries,
        "routing_decision": {
            "project_key": decision.project_key,
            "team_name": decision.team_name,
            "decision_reason": decision.decision_reason,
        },
    }


def build_routing_card_data(decisions: List[RoutingDecision], items: List[Dict]) -> Dict[str, Any]:
    """
    Build request_data dict for an ApprovalRequest of type 'routing_classification'.

    items should be parallel to decisions (same index order).
    """
    high = sum(1 for d in decisions if d.confidence >= KEYWORD_HIGH_CONFIDENCE)
    medium = sum(
        1 for d in decisions
        if KEYWORD_MEDIUM_CONFIDENCE <= d.confidence < KEYWORD_HIGH_CONFIDENCE
    )
    low = sum(1 for d in decisions if d.confidence < KEYWORD_MEDIUM_CONFIDENCE)

    unique_projects = list({d.project_key for d in decisions})
    primary_project = decisions[0].project_key if decisions else "N/A"
    overall_confidence = (sum(d.confidence for d in decisions) / len(decisions)) if decisions else 1.0
    primary_reason = decisions[0].decision_reason if decisions else "keyword_match"

    card_items = [
        {
            "summary": items[i].get("summary", "") if i < len(items) else "",
            "project_key": d.project_key,
            "team_name": d.team_name or "unknown",
            "confidence": round(d.confidence, 3),
            "decision_reason": d.decision_reason,
        }
        for i, d in enumerate(decisions)
    ]

    return {
        "project_key": primary_project,
        "projects": unique_projects,
        "decision_reason": primary_reason,
        "overall_confidence": round(overall_confidence, 3),
        "total": len(decisions),
        "high_confidence_count": high,
        "medium_confidence_count": medium,
        "low_confidence_count": low,
        "items": card_items,
    }


def create_project_approval_request(
    decision: RoutingDecision,
    items: List[Dict[str, str]],
    assigned_to_user_id: int,
    session: "Session",
) -> Optional[int]:
    """
    Create an ApprovalRequest of type 'project_creation' and return its ID.

    Returns None if creation fails.
    """
    try:
        from backend.db.models import ApprovalRequest
        request_data = build_project_creation_approval_data(decision, items)
        approval = ApprovalRequest(
            request_type="project_creation",
            entity_type="jira_project",
            entity_id=0,
            requested_by=assigned_to_user_id,
            assigned_to=assigned_to_user_id,
            request_data=request_data,
            status="pending",
            priority="high",
        )
        session.add(approval)
        session.commit()
        logger.info(
            f"Created project_creation approval #{approval.approval_id} "
            f"for project '{decision.project_key}'"
        )
        return approval.approval_id
    except Exception as e:
        logger.error(f"Failed to create project_creation approval: {e}")
        session.rollback()
        return None


def create_routing_card_approval_request(
    decisions: List[RoutingDecision],
    items: List[Dict],
    assigned_to_user_id: int,
    session: "Session",
) -> Optional[int]:
    """
    Create an ApprovalRequest of type 'routing_classification' and return its ID.

    Returns None if creation fails.
    """
    try:
        from backend.db.models import ApprovalRequest
        request_data = build_routing_card_data(decisions, items)
        low_count = request_data.get("low_confidence_count", 0)
        priority = "high" if low_count > 0 else "medium"
        approval = ApprovalRequest(
            request_type="routing_classification",
            entity_type="backlog_batch",
            request_data=request_data,
            status="pending",
            priority=priority,
            assigned_to=assigned_to_user_id,
        )
        session.add(approval)
        session.commit()
        logger.info(
            f"Created routing_classification approval #{approval.approval_id} "
            f"for {len(decisions)} items"
        )
        return approval.approval_id
    except Exception as e:
        logger.error(f"Failed to create routing_classification approval: {e}")
        session.rollback()
        return None


# ── Routing metadata persistence ──────────────────────────────────────────────


def persist_routing_on_epic(epic_db_obj: Any, decision: RoutingDecision) -> None:
    """Apply routing metadata fields to an Epic ORM object (does NOT commit)."""
    epic_db_obj.jira_project_key = decision.project_key
    epic_db_obj.team_name = decision.team_name
    epic_db_obj.jira_component = None  # Components removed: items live directly under project
    epic_db_obj.routing_confidence = round(decision.confidence, 3)
    epic_db_obj.routing_source = (decision.decision_reason or "keyword_match")[:20]


def persist_routing_on_story(story_db_obj: Any, decision: RoutingDecision) -> None:
    """Apply routing metadata fields to a Story ORM object (does NOT commit)."""
    story_db_obj.jira_project_key = decision.project_key
    story_db_obj.team_name = decision.team_name
    story_db_obj.jira_component = None  # Components removed: items live directly under project
    story_db_obj.routing_confidence = round(decision.confidence, 3)
    story_db_obj.routing_source = (decision.decision_reason or "keyword_match")[:20]


def persist_routing_on_task(task_db_obj: Any, decision: RoutingDecision) -> None:
    """Apply routing metadata fields to a BacklogTask ORM object (does NOT commit)."""
    task_db_obj.jira_project_key = decision.project_key
    task_db_obj.team_name = decision.team_name
    task_db_obj.jira_component = None  # Components removed: items live directly under project
    task_db_obj.routing_confidence = round(decision.confidence, 3)
    task_db_obj.routing_source = (decision.decision_reason or "keyword_match")[:20]


def persist_routing_on_scrum_action(action_db_obj: Any, decision: RoutingDecision) -> None:
    """Apply routing metadata fields to a ScrumAction ORM object (does NOT commit)."""
    action_db_obj.jira_project_key = decision.project_key
    action_db_obj.team_name = decision.team_name
    action_db_obj.jira_component = None  # Components removed: items live directly under project
    action_db_obj.routing_confidence = round(decision.confidence, 3)
    action_db_obj.routing_source = (decision.decision_reason or "keyword_match")[:20]
