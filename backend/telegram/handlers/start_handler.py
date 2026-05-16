"""
/start Command Handler

Handles user account linking.
"""
import logging
from telegram import Update
from telegram.ext import ContextTypes

from backend.db.connection import get_session
from backend.db.models import User

logger = logging.getLogger(__name__)


async def handle_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Handle /start command.
    
    Links Telegram account to ScrumPilot user account.
    """
    user = update.effective_user
    chat_id = update.effective_chat.id
    
    logger.info(f"User {user.id} ({user.username}) started bot")
    
    # Check if already linked
    with get_session() as session:
        existing_user = session.query(User).filter(
            User.telegram_user_id == user.id
        ).first()
        
        if existing_user:
            await update.message.reply_text(
                f"✅ Welcome back, {existing_user.display_name}!\n\n"
                f"Your account is already linked.\n\n"
                f"Use /help to see available commands."
            )
            return
    
    # Not linked - ask for email
    await update.message.reply_text(
        "👋 Welcome to ScrumPilot!\n\n"
        "To link your Telegram account, please send me your email address.\n\n"
        "Example: sarah@company.com"
    )
    
    # Set conversation state
    context.user_data['awaiting_email'] = True


async def handle_email_linking(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Handle email for account linking.
    
    Called from message_handler when awaiting_email is True.
    """
    email = update.message.text.strip().lower()
    user = update.effective_user
    chat_id = update.effective_chat.id
    
    # Validate email format
    if '@' not in email or '.' not in email:
        await update.message.reply_text(
            "❌ Invalid email format. Please send a valid email address.\n\n"
            "Example: sarah@company.com"
        )
        return
    
    # Find user by email
    with get_session() as session:
        db_user = session.query(User).filter(User.email == email).first()
        
        if not db_user:
            from sqlalchemy import text as _text
            from datetime import datetime, timezone

            display_name = (
                f"{user.first_name or ''} {user.last_name or ''}".strip()
                or user.username
                or email.split("@")[0]
            )

            # ── First-ever user: auto-approve as admin (bootstrapping) ────────
            any_existing = session.query(User).first()
            if not any_existing:
                row = session.execute(
                    _text("SELECT role_id FROM roles WHERE role_name = 'admin'")
                ).fetchone()
                db_user = User(
                    display_name=display_name,
                    normalized_name=display_name.lower(),
                    email=email,
                    role_id=row[0] if row else None,
                    account_status="active",
                    email_verified=True,
                    telegram_user_id=user.id,
                    telegram_chat_id=chat_id,
                    telegram_username=user.username,
                    telegram_first_name=user.first_name,
                    telegram_last_name=user.last_name,
                    telegram_language_code=user.language_code,
                    telegram_linked_at=datetime.now(timezone.utc),
                    telegram_notifications_enabled=True,
                )
                session.add(db_user)
                session.commit()
                logger.info(f"First user {email} registered as admin")
                await update.message.reply_text(
                    f"✅ *Welcome, {display_name}!*\n\n"
                    f"You are the first user — registered as *admin*.\n\n"
                    f"You can now approve other users with `/list_users` and manage the system.\n"
                    f"Use /help to see all commands.",
                    parse_mode="Markdown",
                )
                context.user_data['awaiting_email'] = False
                return

            # ── Subsequent users: send approval request to admin ──────────────
            from backend.db.models import ApprovalRequest

            # Store pending registration in ApprovalRequest table
            admin_user = session.query(User).filter(
                User.telegram_user_id.isnot(None),
            ).join(User.role).filter(
                User.role.has(role_name="admin") | User.role.has(role_name="product_owner")
            ).first()

            if not admin_user:
                # Fallback: send to any linked user
                admin_user = session.query(User).filter(
                    User.telegram_user_id.isnot(None)
                ).first()

            pending = ApprovalRequest(
                request_type="user_registration",
                entity_type="user",
                entity_id=0,
                status="pending",
                request_data={
                    "email":            email,
                    "display_name":     display_name,
                    "telegram_user_id": user.id,
                    "telegram_chat_id": chat_id,
                    "telegram_username": user.username,
                },
                assigned_to=admin_user.id if admin_user else None,
                requested_by=admin_user.id if admin_user else None,
            )
            session.add(pending)
            session.commit()
            approval_id = pending.approval_id
            logger.info(
                f"User registration request #{approval_id} for {email} "
                f"sent to admin {admin_user.email if admin_user else 'none'}"
            )

            # Notify admin via Telegram
            if admin_user and admin_user.telegram_user_id:
                from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Bot
                from backend.telegram.config import TelegramConfig
                kb = InlineKeyboardMarkup([
                    [
                        InlineKeyboardButton("📋 Accept as PM",  callback_data=f"uacc_{approval_id}_pm"),
                        InlineKeyboardButton("💻 Accept as Dev", callback_data=f"uacc_{approval_id}_dev"),
                    ],
                    [
                        InlineKeyboardButton("❌ Reject",        callback_data=f"urej_{approval_id}"),
                    ],
                ])
                try:
                    bot = Bot(token=TelegramConfig.BOT_TOKEN)
                    await bot.send_message(
                        chat_id=admin_user.telegram_chat_id,
                        text=(
                            f"👤 *New User Registration Request*\n\n"
                            f"Name:  {display_name}\n"
                            f"Email: `{email}`\n\n"
                            f"Select a role to approve or reject:"
                        ),
                        reply_markup=kb,
                        parse_mode="Markdown",
                    )
                except Exception as _ne:
                    logger.warning(f"Could not notify admin of registration: {_ne}")

            await update.message.reply_text(
                f"⏳ *Registration request sent!*\n\n"
                f"Your request for `{email}` is pending admin approval.\n"
                f"You will be notified here once approved.",
                parse_mode="Markdown",
            )
            context.user_data['awaiting_email'] = False
            return
        
        # Link Telegram account
        from datetime import datetime, timezone
        db_user.telegram_user_id = user.id
        db_user.telegram_chat_id = chat_id
        db_user.telegram_username = user.username
        db_user.telegram_first_name = user.first_name
        db_user.telegram_last_name = user.last_name
        db_user.telegram_language_code = user.language_code
        db_user.telegram_linked_at = datetime.now(timezone.utc)
        db_user.telegram_notifications_enabled = True
        
        session.commit()
        
        logger.info(f"Linked Telegram user {user.id} to {db_user.display_name} ({email})")
        
        await update.message.reply_text(
            f"✅ Account linked successfully!\n\n"
            f"Welcome, {db_user.display_name}!\n"
            f"Role: {db_user.role.role_name if db_user.role else 'No role'}\n\n"
            f"You will now receive notifications for:\n"
            f"• Pending approvals\n"
            f"• Sprint updates\n"
            f"• Task assignments\n\n"
            f"Use /help to see available commands."
        )
        
        context.user_data['awaiting_email'] = False
