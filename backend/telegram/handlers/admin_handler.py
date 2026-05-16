"""
Admin Handler — Phase 7

Telegram commands for managing Jira project/team routing without a code deploy.

Commands (product-owner / admin only):
  /add_project  <KEY> <Name...>           — register a new Jira project
  /remove_project <KEY>                   — archive a project from the registry
  /add_team_keyword <KEY> <team> <word>   — add a routing keyword to a team
  /list_projects                          — show all projects in the registry
"""
import logging
import re

from telegram import Update
from telegram.ext import ContextTypes

from backend.db.connection import get_session
from backend.db.models import JiraProjectRegistry, JiraProjectTeam, User
from sqlalchemy import text

logger = logging.getLogger(__name__)

_ADMIN_ROLES = {"admin", "product_owner"}

_VALID_ROLES = {"admin", "scrum_master", "product_owner", "developer", "viewer"}

_ROLE_EMOJI = {
    "admin":         "🔑",
    "product_owner": "📋",
    "scrum_master":  "🏃",
    "developer":     "💻",
    "viewer":        "👁",
}


def _is_admin(telegram_user_id: int, session) -> bool:
    user = session.query(User).filter(
        User.telegram_user_id == telegram_user_id
    ).first()
    if not user:
        return False
    role = getattr(user, "role", None)
    role_name = getattr(role, "role_name", "") if role else ""
    return role_name.lower() in _ADMIN_ROLES


async def handle_add_project(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    /add_project KEY Project Name Here

    Registers a new project in the local registry.
    Does NOT create the project in Jira — use /add_project only for projects
    that already exist in Jira or that you will create manually.
    """
    args = context.args or []
    if len(args) < 2:
        await update.message.reply_text(
            "Usage: `/add_project KEY Project Name Here`\n"
            "Example: `/add_project CARAPP Car Rental App`",
            parse_mode="Markdown",
        )
        return

    project_key = args[0].strip().upper()
    project_name = " ".join(args[1:]).strip()

    import re
    if not re.match(r"^[A-Z][A-Z0-9]{1,9}$", project_key):
        await update.message.reply_text(
            "❌ Invalid key. Must be 2–10 uppercase letters/digits starting with a letter."
        )
        return

    with get_session() as session:
        if not _is_admin(update.effective_user.id, session):
            await update.message.reply_text("❌ Only admins or product owners can use this command.")
            return

        existing = session.query(JiraProjectRegistry).filter(
            JiraProjectRegistry.project_key == project_key
        ).first()

        if existing and existing.status == "active":
            await update.message.reply_text(
                f"ℹ️ Project `{project_key}` already exists and is active.",
                parse_mode="Markdown",
            )
            return

        if existing:
            existing.status = "active"
            existing.name = project_name
            session.commit()
            await update.message.reply_text(
                f"✅ Project `{project_key}` re-activated as *{project_name}*.",
                parse_mode="Markdown",
            )
        else:
            row = JiraProjectRegistry(
                project_key=project_key,
                name=project_name,
                keywords=[],
                status="active",
                auto_created=False,
                registry_metadata={},
            )
            session.add(row)
            session.commit()
            logger.info(f"Admin registered project '{project_key}' via Telegram")
            await update.message.reply_text(
                f"✅ Project `{project_key}` — *{project_name}* — added to registry.\n\n"
                f"Next pipeline run will route matching epics here automatically.",
                parse_mode="Markdown",
            )


async def handle_remove_project(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    /remove_project KEY

    Archives a project (sets status=archived). Existing Jira tickets are unaffected.
    """
    args = context.args or []
    if not args:
        await update.message.reply_text(
            "Usage: `/remove_project KEY`\nExample: `/remove_project CARAPP`",
            parse_mode="Markdown",
        )
        return

    project_key = args[0].strip().upper()

    with get_session() as session:
        if not _is_admin(update.effective_user.id, session):
            await update.message.reply_text("❌ Only admins or product owners can use this command.")
            return

        row = session.query(JiraProjectRegistry).filter(
            JiraProjectRegistry.project_key == project_key
        ).first()

        if not row:
            await update.message.reply_text(f"❌ Project `{project_key}` not found.", parse_mode="Markdown")
            return

        row.status = "archived"
        session.commit()
        logger.info(f"Admin archived project '{project_key}' via Telegram")
        await update.message.reply_text(
            f"🗄️ Project `{project_key}` archived. New epics will no longer route here.",
            parse_mode="Markdown",
        )


async def handle_add_team_keyword(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    /add_team_keyword KEY team word

    Adds a routing keyword to a team under a project.
    Creates the team row if it doesn't exist yet.

    Example: /add_team_keyword CARAPP backend microservice
    """
    args = context.args or []
    if len(args) < 3:
        await update.message.reply_text(
            "Usage: `/add_team_keyword KEY team keyword`\n"
            "Example: `/add_team_keyword CARAPP backend microservice`",
            parse_mode="Markdown",
        )
        return

    project_key = args[0].strip().upper()
    team_name   = args[1].strip().lower()
    new_keyword = " ".join(args[2:]).strip().lower()

    with get_session() as session:
        if not _is_admin(update.effective_user.id, session):
            await update.message.reply_text("❌ Only admins or product owners can use this command.")
            return

        project = session.query(JiraProjectRegistry).filter(
            JiraProjectRegistry.project_key == project_key,
            JiraProjectRegistry.status == "active",
        ).first()
        if not project:
            await update.message.reply_text(
                f"❌ Project `{project_key}` not found or not active. "
                f"Register it first with `/add_project`.",
                parse_mode="Markdown",
            )
            return

        team_row = session.query(JiraProjectTeam).filter(
            JiraProjectTeam.project_key == project_key,
            JiraProjectTeam.team_name   == team_name,
        ).first()

        if team_row:
            kws = list(team_row.keywords or [])
            if new_keyword in kws:
                await update.message.reply_text(
                    f"ℹ️ `{new_keyword}` already exists in *{project_key}* / *{team_name}* keywords.",
                    parse_mode="Markdown",
                )
                return
            kws.append(new_keyword)
            team_row.keywords = kws
        else:
            team_row = JiraProjectTeam(
                project_key=project_key,
                team_name=team_name,
                jira_component=team_name.capitalize(),
                label_set=[],
                keywords=[new_keyword],
            )
            session.add(team_row)

        session.commit()
        logger.info(f"Admin added keyword '{new_keyword}' to {project_key}/{team_name}")
        await update.message.reply_text(
            f"✅ Keyword `{new_keyword}` added to *{project_key}* → *{team_name}* team.\n\n"
            f"Future epics mentioning this word will route to {project_key}/{team_name}.",
            parse_mode="Markdown",
        )


async def handle_add_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    /add_user email "Display Name" role

    Registers a user in the DB so they can link their Telegram account
    by messaging the bot with /start and entering this email.

    role must be one of: admin, scrum_master, product_owner, developer, viewer

    Example:
      /add_user sameer@company.com "Sameer Kumar" product_owner
    """
    args_raw = update.message.text.partition(" ")[2].strip()   # everything after /add_user

    # Parse: first token = email, last token = role, middle = display name
    # Support quoted names: /add_user a@b.com "First Last" developer
    match = re.match(
        r'^(\S+)\s+"(.+?)"\s+(\S+)$'
        r'|^(\S+)\s+(\S+)\s+(\S+)$',
        args_raw,
    )
    if not match:
        await update.message.reply_text(
            "Usage: `/add_user email \"Display Name\" role`\n"
            "Example: `/add_user sameer@company.com \"Sameer Kumar\" product_owner`\n\n"
            f"Valid roles: {', '.join(sorted(_VALID_ROLES))}",
            parse_mode="Markdown",
        )
        return

    groups = match.groups()
    if groups[0]:   # quoted-name branch
        email, display_name, role = groups[0], groups[1], groups[2]
    else:           # space-separated branch
        email, display_name, role = groups[3], groups[4], groups[5]

    email = email.strip().lower()
    role  = role.strip().lower()

    if "@" not in email:
        await update.message.reply_text("❌ Invalid email address.")
        return

    if role not in _VALID_ROLES:
        await update.message.reply_text(
            f"❌ Unknown role `{role}`.\n"
            f"Valid roles: {', '.join(sorted(_VALID_ROLES))}",
            parse_mode="Markdown",
        )
        return

    with get_session() as session:
        # First user can always add; subsequent additions require admin/PM
        any_user = session.query(User).first()
        if any_user and not _is_admin(update.effective_user.id, session):
            await update.message.reply_text(
                "❌ Only admins or product owners can add users."
            )
            return

        existing = session.query(User).filter(User.email == email).first()
        if existing:
            await update.message.reply_text(
                f"ℹ️ User `{email}` already exists."
                f" Telegram linked: {'Yes' if existing.telegram_user_id else 'No'}",
                parse_mode="Markdown",
            )
            return

        # Resolve role_id
        row = session.execute(
            text("SELECT role_id FROM roles WHERE role_name = :r"), {"r": role}
        ).fetchone()
        role_id = row[0] if row else None

        new_user = User(
            display_name=display_name,
            normalized_name=display_name.lower(),
            email=email,
            role_id=role_id,
            account_status="active",
            email_verified=False,
        )
        session.add(new_user)
        session.commit()
        emoji = _ROLE_EMOJI.get(role, "👤")
        logger.info(f"Admin added user {email} ({role}) via Telegram")
        await update.message.reply_text(
            f"{emoji} User added:\n"
            f"  Email: `{email}`\n"
            f"  Name:  {display_name}\n"
            f"  Role:  {role}\n\n"
            f"Ask them to message the bot and type `/start` to link their Telegram.",
            parse_mode="Markdown",
        )


async def handle_list_users(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    /list_users

    Shows all users, their roles, and Telegram link status.
    """
    with get_session() as session:
        users = session.query(User).order_by(User.id).all()
        if not users:
            await update.message.reply_text("No users registered yet.")
            return

        lines = ["*👥 ScrumPilot Users*\n"]
        for u in users:
            role_name = u.role.role_name if u.role else "no role"
            emoji     = _ROLE_EMOJI.get(role_name, "👤")
            tg_status = f"✅ @{u.telegram_username or u.telegram_user_id}" \
                        if u.telegram_user_id else "❌ not linked"
            lines.append(
                f"{emoji} *{u.display_name}* — `{u.email or 'no email'}`\n"
                f"   Role: {role_name}  |  Telegram: {tg_status}"
            )
        await update.message.reply_text("\n".join(lines), parse_mode="Markdown")


async def handle_set_role(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    /set_role email role

    Changes a user's role.
    Example: /set_role sameer@company.com product_owner
    """
    args = context.args or []
    if len(args) < 2:
        await update.message.reply_text(
            "Usage: `/set_role email role`\n"
            "Example: `/set_role sameer@company.com product_owner`",
            parse_mode="Markdown",
        )
        return

    email = args[0].strip().lower()
    role  = args[1].strip().lower()

    if role not in _VALID_ROLES:
        await update.message.reply_text(
            f"❌ Unknown role `{role}`. Valid: {', '.join(sorted(_VALID_ROLES))}",
            parse_mode="Markdown",
        )
        return

    with get_session() as session:
        if not _is_admin(update.effective_user.id, session):
            await update.message.reply_text("❌ Only admins can change roles.")
            return

        user = session.query(User).filter(User.email == email).first()
        if not user:
            await update.message.reply_text(f"❌ User `{email}` not found.", parse_mode="Markdown")
            return

        row = session.execute(
            text("SELECT role_id FROM roles WHERE role_name = :r"), {"r": role}
        ).fetchone()
        if not row:
            await update.message.reply_text(f"❌ Role `{role}` not found in DB.", parse_mode="Markdown")
            return

        user.role_id = row[0]
        session.commit()
        emoji = _ROLE_EMOJI.get(role, "👤")
        logger.info(f"Admin set role of {email} to {role}")
        await update.message.reply_text(
            f"{emoji} Role updated: `{email}` → *{role}*",
            parse_mode="Markdown",
        )


async def handle_list_projects(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    /list_projects

    Shows all projects in the registry with their status and team count.
    """
    with get_session() as session:
        rows = session.query(JiraProjectRegistry).order_by(
            JiraProjectRegistry.status, JiraProjectRegistry.project_key
        ).all()

        if not rows:
            await update.message.reply_text("No projects registered yet.")
            return

        lines = ["*📋 Jira Project Registry*\n"]
        for r in rows:
            icon = "✅" if r.status == "active" else ("⏳" if r.status == "pending_creation" else "🗄️")
            team_count = len(r.routing_teams)
            auto = " _(auto-created)_" if r.auto_created else ""
            lines.append(
                f"{icon} `{r.project_key}` — {r.name}{auto}\n"
                f"   Teams: {team_count}  |  Keywords: {len(r.keywords)}"
            )

        await update.message.reply_text("\n".join(lines), parse_mode="Markdown")
