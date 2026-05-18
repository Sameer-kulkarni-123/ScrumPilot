"""Helpers for resolving transcript names to Jira identities."""
from typing import Optional

from sqlalchemy import or_

from backend.db.connection import get_session
from backend.db.models import User


def resolve_jira_assignee(name_or_account: Optional[str]) -> Optional[str]:
    """
    Resolve a transcript/display name to a Jira account identifier.

    Returns the best value to pass to Jira assignment APIs. Jira Cloud usually
    prefers accountId, but this also falls back to email/name for older setups.
    """
    if not name_or_account:
        return None

    raw = name_or_account.strip()
    normalized = raw.lower()

    try:
        with get_session() as session:
            user = (
                session.query(User)
                .filter(
                    or_(
                        User.normalized_name == normalized,
                        User.email == normalized,
                        User.jira_account_id == raw,
                        User.jira_display_name.ilike(raw),
                    )
                )
                .first()
            )
            if not user:
                return raw

            return user.jira_account_id or user.email or user.jira_display_name or raw
    except Exception:
        return raw
