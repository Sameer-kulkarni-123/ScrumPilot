"""Telegram commands for managing ScrumPilot users."""
from datetime import datetime, timezone

from telegram import Update
from telegram.ext import ContextTypes

from backend.db.connection import get_session
from backend.db.models import Role, User


async def handle_adduser(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Create or update a ScrumPilot user from Telegram.

    Usage:
        /adduser email role Display Name
        /adduser sameer@example.com developer Sameer Kulkarni
    """
    requester = update.effective_user
    if not requester:
        return

    if len(context.args) < 3:
        await update.message.reply_text(
            "Usage:\n/adduser email role Display Name\n\n"
            "Example:\n/adduser sameer@example.com developer Sameer Kulkarni"
        )
        return

    email = context.args[0].strip().lower()
    role_name = context.args[1].strip().lower()
    display_name = " ".join(context.args[2:]).strip()

    if "@" not in email or "." not in email:
        await update.message.reply_text("Please provide a valid email address.")
        return

    with get_session() as session:
        requester_user = session.query(User).filter(User.telegram_user_id == requester.id).first()
        if not requester_user:
            await update.message.reply_text("Please link your account first with /start.")
            return

        requester_role = requester_user.role.role_name if requester_user.role else ""
        if requester_role not in {"admin", "product_owner", "scrum_master"}:
            await update.message.reply_text("Only admins, product owners, or scrum masters can add users.")
            return

        role = session.query(Role).filter(Role.role_name == role_name).first()
        if not role:
            known_roles = ", ".join(r.role_name for r in session.query(Role).order_by(Role.role_name).all())
            await update.message.reply_text(f"Unknown role '{role_name}'. Available roles: {known_roles}")
            return

        user = session.query(User).filter(User.email == email).first()
        created = user is None
        if not user:
            user = User(
                display_name=display_name,
                normalized_name=display_name.lower().strip(),
                email=email,
                role_id=role.role_id,
            )
            session.add(user)
        else:
            user.display_name = display_name
            user.normalized_name = display_name.lower().strip()
            user.role_id = role.role_id

        session.commit()

    action = "Created" if created else "Updated"
    await update.message.reply_text(
        f"{action} ScrumPilot user.\n\n"
        f"Name: {display_name}\n"
        f"Email: {email}\n"
        f"Role: {role_name}\n\n"
        "Ask them to message this bot with /start and enter the same email."
    )


async def handle_updateuser(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Update one ScrumPilot user field from Telegram.

    Usage:
        /updateuser email field value

    Fields:
        name, role, email, jira, jira_name
    """
    requester = update.effective_user
    if not requester:
        return

    if len(context.args) < 3:
        await update.message.reply_text(
            "Usage:\n"
            "/updateuser email field value\n\n"
            "Fields: name, role, email, jira, jira_name\n\n"
            "Examples:\n"
            "/updateuser sameer@example.com role scrum_master\n"
            "/updateuser sameer@example.com name Sameer Kulkarni\n"
            "/updateuser sameer@example.com jira sameer@company.com"
        )
        return

    lookup_email = context.args[0].strip().lower()
    field = context.args[1].strip().lower()
    value = " ".join(context.args[2:]).strip()

    if "@" not in lookup_email or "." not in lookup_email:
        await update.message.reply_text("Please provide a valid user email.")
        return

    if field not in {"name", "role", "email", "jira", "jira_name"}:
        await update.message.reply_text("Unknown field. Use: name, role, email, jira, jira_name")
        return

    if not value:
        await update.message.reply_text("Please provide a value to update.")
        return

    with get_session() as session:
        requester_user = session.query(User).filter(User.telegram_user_id == requester.id).first()
        if not requester_user:
            await update.message.reply_text("Please link your account first with /start.")
            return

        requester_role = requester_user.role.role_name if requester_user.role else ""
        if requester_role not in {"admin", "product_owner", "scrum_master"}:
            await update.message.reply_text("Only admins, product owners, or scrum masters can update users.")
            return

        user = session.query(User).filter(User.email == lookup_email).first()
        if not user:
            await update.message.reply_text("No ScrumPilot user found for that email.")
            return

        if field == "name":
            user.display_name = value
            user.normalized_name = value.lower().strip()
        elif field == "role":
            role = session.query(Role).filter(Role.role_name == value.lower()).first()
            if not role:
                known_roles = ", ".join(r.role_name for r in session.query(Role).order_by(Role.role_name).all())
                await update.message.reply_text(f"Unknown role '{value}'. Available roles: {known_roles}")
                return
            user.role_id = role.role_id
        elif field == "email":
            new_email = value.lower()
            if "@" not in new_email or "." not in new_email:
                await update.message.reply_text("Please provide a valid new email address.")
                return
            existing = session.query(User).filter(User.email == new_email, User.id != user.id).first()
            if existing:
                await update.message.reply_text("Another ScrumPilot user already has that email.")
                return
            user.email = new_email
        elif field == "jira":
            user.jira_account_id = value
        elif field == "jira_name":
            user.jira_display_name = value

        user.updated_at = datetime.now(timezone.utc)
        session.commit()

        role_name = user.role.role_name if user.role else "No role"
        await update.message.reply_text(
            "User updated.\n\n"
            f"Name: {user.display_name}\n"
            f"Role: {role_name}\n"
            f"Email: {user.email or 'Not set'}\n"
            f"Jira: {user.jira_account_id or 'Not set'}\n"
            f"Jira display name: {user.jira_display_name or 'Not set'}"
        )
