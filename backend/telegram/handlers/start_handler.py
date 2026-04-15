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
            await update.message.reply_text(
                f"❌ No user found with email: {email}\n\n"
                f"Please contact your administrator to create an account first."
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
