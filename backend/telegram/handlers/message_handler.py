"""
Message Handler

Handles text messages for conversation flows:
- Email linking
- Rejection reasons
- Edit flows
"""
from telegram import Update
from telegram.ext import ContextTypes

from backend.telegram.handlers.start_handler import handle_email_linking
from backend.telegram.handlers.callback_handler import handle_rejection_reason


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Handle text messages based on conversation state.
    """
    # Check conversation state
    if context.user_data.get('awaiting_email'):
        await handle_email_linking(update, context)
    
    elif context.user_data.get('awaiting_rejection_reason'):
        await handle_rejection_reason(update, context)
    
    else:
        # No active conversation - show help
        await update.message.reply_text(
            "ℹ️ I didn't understand that.\n\n"
            "Use /help to see available commands."
        )
