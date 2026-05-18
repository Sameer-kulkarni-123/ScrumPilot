"""
/jira command handler.

Lets a linked Telegram user attach their Jira identity to the ScrumPilot user
record so pipeline-extracted assignments can be resolved before Jira updates.
"""
import logging
from datetime import datetime, timezone

from telegram import Update
from telegram.ext import ContextTypes

from backend.db.connection import get_session
from backend.db.models import User

logger = logging.getLogger(__name__)


async def handle_jira(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Link or show the current user's Jira identity.

    Usage:
        /jira
        /jira <jira-account-id-or-email> [Jira Display Name]
    """
    tg_user = update.effective_user
    if not tg_user:
        return

    with get_session() as session:
        db_user = session.query(User).filter(User.telegram_user_id == tg_user.id).first()
        if not db_user:
            await update.message.reply_text(
                "Please link your ScrumPilot account first with /start."
            )
            return

        if not context.args:
            jira_identity = db_user.jira_account_id or db_user.email or "not set"
            jira_name = db_user.jira_display_name or db_user.display_name
            await update.message.reply_text(
                f"Current Jira identity: {jira_identity}\n"
                f"Jira display name: {jira_name}\n\n"
                "To update it, send:\n"
                "/jira <jira-account-id-or-email> [Jira Display Name]"
            )
            return

        jira_identity = context.args[0].strip()
        jira_display_name = " ".join(context.args[1:]).strip() or db_user.display_name

        db_user.jira_account_id = jira_identity
        db_user.jira_display_name = jira_display_name
        db_user.updated_at = datetime.now(timezone.utc)
        session.commit()

        logger.info("Linked Jira identity for user %s", db_user.id)

        await update.message.reply_text(
            "Jira account linked.\n\n"
            f"ScrumPilot user: {db_user.display_name}\n"
            f"Jira identity: {jira_identity}\n"
            f"Jira display name: {jira_display_name}\n\n"
            "Future pipeline assignments that mention your name will use this Jira identity."
        )


async def handle_addjira(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Add or update a Jira identity for any ScrumPilot user.

    Usage:
        /addjira <scrumpilot-email> <jira-account-id-or-email> [Jira Display Name]
    """
    requester = update.effective_user
    if not requester:
        return

    if len(context.args) < 2:
        await update.message.reply_text(
            "Usage:\n"
            "/addjira scrumpilot-email jira-account-id-or-email [Jira Display Name]\n\n"
            "Example:\n"
            "/addjira sameerk2214@gmail.com sameerk2214@gmail.com Sameer Kulkarni"
        )
        return

    user_email = context.args[0].strip().lower()
    jira_identity = context.args[1].strip()
    jira_display_name = " ".join(context.args[2:]).strip()

    if "@" not in user_email or "." not in user_email:
        await update.message.reply_text("Please provide a valid ScrumPilot user email.")
        return

    with get_session() as session:
        requester_user = session.query(User).filter(User.telegram_user_id == requester.id).first()
        if not requester_user:
            await update.message.reply_text("Please link your account first with /start.")
            return

        requester_role = requester_user.role.role_name if requester_user.role else ""
        if requester_role not in {"admin", "product_owner", "scrum_master"}:
            await update.message.reply_text(
                "Only admins, product owners, or scrum masters can add Jira identities."
            )
            return

        user = session.query(User).filter(User.email == user_email).first()
        if not user:
            await update.message.reply_text(
                "No ScrumPilot user found for that email.\n\n"
                "Create them first with:\n"
                "/adduser email role Display Name"
            )
            return

        user.jira_account_id = jira_identity
        user.jira_display_name = jira_display_name or user.display_name
        user.updated_at = datetime.now(timezone.utc)
        session.commit()

        logger.info("Linked Jira identity for user %s by requester %s", user.id, requester_user.id)

        await update.message.reply_text(
            "Jira identity linked.\n\n"
            f"ScrumPilot user: {user.display_name}\n"
            f"Email: {user.email}\n"
            f"Jira identity: {user.jira_account_id}\n"
            f"Jira display name: {user.jira_display_name}\n\n"
            "Future pipeline assignments that mention this user's name will use this Jira identity."
        )
