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
from backend.telegram.handlers.callback_handler import (
    handle_editkey_input,
    handle_project_key_input,
    handle_project_name_input,
    handle_rejection_reason,
)
from backend.telegram.handlers.meet_handler import handle_meet_link_input, handle_transcript_input


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Handle text messages based on conversation state.
    """
    # Check conversation state
    if context.user_data.get('awaiting_meet_link'):
        await handle_meet_link_input(update, context)

    elif context.user_data.get('awaiting_transcript') or \
         context.user_data.get('awaiting_second_transcript_pm') or \
         context.user_data.get('awaiting_second_transcript_grooming'):
        await handle_transcript_input(update, context)

    elif context.user_data.get('awaiting_email'):
        await handle_email_linking(update, context)

    elif context.user_data.get('pending_editkey_approval_id'):
        await handle_editkey_input(update, context)

    elif context.user_data.get('pending_project_name_approval_id'):
        await handle_project_name_input(update, context)

    elif context.user_data.get('pending_project_key_approval_id'):
        await handle_project_key_input(update, context)

    elif context.user_data.get('awaiting_rejection_reason'):
        await handle_rejection_reason(update, context)

    else:
        # No active conversation - show help
        await update.message.reply_text(
            "ℹ️ I didn't understand that.\n\n"
            "Use /help to see available commands."
        )
