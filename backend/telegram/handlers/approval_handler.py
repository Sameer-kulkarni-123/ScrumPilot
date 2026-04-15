"""
Approval Handler - Human-in-the-Loop Workflow

Handles approval requests for:
- Epic creation
- Story creation
- Sprint planning
- Bulk updates
"""
import logging
import json
from datetime import datetime, timezone
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

from backend.db.connection import get_session
from backend.db.models import User, ApprovalRequest
from backend.db import crud

logger = logging.getLogger(__name__)


async def handle_approvals(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Handle /approvals command.
    
    Shows list of pending approval requests assigned to user.
    """
    user = update.effective_user
    
    # Get user from database
    with get_session() as session:
        db_user = session.query(User).filter(
            User.telegram_user_id == user.id
        ).first()
        
        if not db_user:
            await update.message.reply_text(
                "❌ Your account is not linked.\n\n"
                "Use /start to link your account."
            )
            return
        
        # Get pending approvals assigned to this user
        approvals = session.query(ApprovalRequest).filter(
            ApprovalRequest.assigned_to == db_user.id,
            ApprovalRequest.status == 'pending'
        ).order_by(
            ApprovalRequest.priority.desc(),
            ApprovalRequest.created_at.asc()
        ).all()
        
        if not approvals:
            await update.message.reply_text(
                "✅ No pending approvals!\n\n"
                "You're all caught up. 🎉"
            )
            return
        
        # Show each approval
        for approval in approvals:
            await send_approval_message(update, session, approval)


async def send_approval_message(update: Update, session, approval: ApprovalRequest):
    """
    Send approval request message with inline buttons.
    
    This is the core HITL interface.
    """
    # Parse request data
    request_data = approval.request_data or {}
    
    # Format message based on request type
    if approval.request_type == 'epic_creation':
        message = format_epic_approval(approval, request_data)
    elif approval.request_type == 'story_creation':
        message = format_story_approval(approval, request_data)
    elif approval.request_type == 'sprint_planning':
        message = format_sprint_approval(approval, request_data)
    elif approval.request_type == 'standup_update':
        message = format_standup_approval(approval, request_data)
    else:
        message = format_generic_approval(approval, request_data)
    
    # Create inline keyboard with action buttons
    keyboard = [
        [
            InlineKeyboardButton("✅ Approve", callback_data=f"approve_{approval.approval_id}"),
            InlineKeyboardButton("❌ Reject", callback_data=f"reject_{approval.approval_id}")
        ],
        [
            InlineKeyboardButton("✏️ Edit", callback_data=f"edit_{approval.approval_id}"),
            InlineKeyboardButton("👁️ View Details", callback_data=f"view_{approval.approval_id}")
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    # Send message (use markdown only for epic/story/sprint, not standup)
    parse_mode = 'Markdown' if approval.request_type != 'standup_update' else None
    
    await update.effective_message.reply_text(
        message,
        reply_markup=reply_markup,
        parse_mode=parse_mode
    )


def format_epic_approval(approval: ApprovalRequest, data: dict) -> str:
    """Format epic creation approval message."""
    epics = data.get('epics', [])
    epic_count = len(epics)
    
    message = f"📋 *Epic Creation Approval*\n\n"
    message += f"*Request ID*: #{approval.approval_id}\n"
    message += f"*Type*: Epic Creation\n"
    message += f"*Count*: {epic_count} epic(s)\n"
    message += f"*Priority*: {approval.priority.upper()}\n"
    message += f"*Created*: {approval.created_at.strftime('%Y-%m-%d %H:%M')}\n\n"
    
    # Show first 3 epics
    message += "*Epics to Create*:\n"
    for i, epic in enumerate(epics[:3], 1):
        title = epic.get('title', 'Untitled')
        wsjf = epic.get('wsjf', {}).get('wsjf_score', 0)
        message += f"{i}. {title} (WSJF: {wsjf:.1f})\n"
    
    if epic_count > 3:
        message += f"... and {epic_count - 3} more\n"
    
    message += f"\n💡 *Action Required*: Review and approve to create in Jira"
    
    return message


def format_story_approval(approval: ApprovalRequest, data: dict) -> str:
    """Format story creation approval message."""
    stories = data.get('stories', [])
    story_count = len(stories)
    epic_title = data.get('epic_title', 'Unknown Epic')
    
    message = f"📝 *Story Creation Approval*\n\n"
    message += f"*Request ID*: #{approval.approval_id}\n"
    message += f"*Type*: Story Creation\n"
    message += f"*Epic*: {epic_title}\n"
    message += f"*Count*: {story_count} story(ies)\n"
    message += f"*Priority*: {approval.priority.upper()}\n"
    message += f"*Created*: {approval.created_at.strftime('%Y-%m-%d %H:%M')}\n\n"
    
    # Show first 3 stories
    message += "*Stories to Create*:\n"
    for i, story in enumerate(stories[:3], 1):
        title = story.get('title', 'Untitled')
        message += f"{i}. {title}\n"
    
    if story_count > 3:
        message += f"... and {story_count - 3} more\n"
    
    message += f"\n💡 *Action Required*: Review and approve to create in Jira"
    
    return message


def format_sprint_approval(approval: ApprovalRequest, data: dict) -> str:
    """Format sprint planning approval message."""
    sprint_name = data.get('sprint_name', 'Unknown Sprint')
    sprint_goal = data.get('sprint_goal', 'No goal specified')
    story_ids = data.get('story_ids', [])
    
    message = f"🏃 *Sprint Planning Approval*\n\n"
    message += f"*Request ID*: #{approval.approval_id}\n"
    message += f"*Type*: Sprint Planning\n"
    message += f"*Sprint*: {sprint_name}\n"
    message += f"*Goal*: {sprint_goal}\n"
    message += f"*Stories*: {len(story_ids)}\n"
    message += f"*Priority*: {approval.priority.upper()}\n"
    message += f"*Created*: {approval.created_at.strftime('%Y-%m-%d %H:%M')}\n\n"
    
    message += f"💡 *Action Required*: Review and approve to activate sprint"
    
    return message


def format_standup_approval(approval: ApprovalRequest, data: dict) -> str:
    """Format standup update approval message."""
    actions = data.get('actions', [])
    summary = data.get('summary', {})
    total_actions = summary.get('total_actions', len(actions))
    action_counts = summary.get('action_counts', {})
    
    message = f"📊 Daily Standup Update\n\n"
    message += f"Request ID: #{approval.approval_id}\n"
    message += f"Type: Standup Update\n"
    message += f"Total Actions: {total_actions}\n"
    message += f"Priority: {approval.priority.upper()}\n"
    message += f"Created: {approval.created_at.strftime('%Y-%m-%d %H:%M')}\n\n"
    
    # Show action breakdown
    if action_counts:
        message += "Action Breakdown:\n"
        for action_type, count in action_counts.items():
            # Format action type nicely
            formatted_type = action_type.replace('_', ' ').title()
            message += f"  • {formatted_type}: {count}\n"
        message += "\n"
    
    # Show first 3 actions (NO markdown to avoid parsing errors)
    if actions:
        message += "Sample Actions:\n"
        for i, action in enumerate(actions[:3], 1):
            action_type = action.get('action', 'unknown')
            ticket_summary = action.get('summary', 'No summary')
            description = action.get('description', '')
            
            # Format: "1. [complete_task] SP-272 - real-time analytics story"
            if description:
                message += f"{i}. [{action_type}] {ticket_summary} - {description[:40]}\n"
            else:
                message += f"{i}. [{action_type}] {ticket_summary}\n"
        
        if len(actions) > 3:
            message += f"... and {len(actions) - 3} more\n"
        message += "\n"
    
    message += f"💡 Action Required: Review and approve to update Jira"
    
    return message


def format_generic_approval(approval: ApprovalRequest, data: dict) -> str:
    """Format generic approval message."""
    message = f"📌 *Approval Request*\n\n"
    message += f"*Request ID*: #{approval.approval_id}\n"
    message += f"*Type*: {approval.request_type}\n"
    message += f"*Entity*: {approval.entity_type}\n"
    message += f"*Priority*: {approval.priority.upper()}\n"
    message += f"*Created*: {approval.created_at.strftime('%Y-%m-%d %H:%M')}\n\n"
    message += f"💡 *Action Required*: Review and approve"
    
    return message


async def send_approval_notification(telegram_user_id: int, telegram_chat_id: int, approval_id: int):
    """
    Send approval notification to user.
    
    This is called by the pipeline when a new approval is created.
    """
    from telegram import Bot
    from backend.telegram.config import TelegramConfig
    
    bot = Bot(token=TelegramConfig.BOT_TOKEN)
    
    with get_session() as session:
        approval = session.query(ApprovalRequest).filter(
            ApprovalRequest.approval_id == approval_id
        ).first()
        
        if not approval:
            logger.error(f"Approval {approval_id} not found")
            return
        
        # Format message
        request_data = approval.request_data or {}
        
        if approval.request_type == 'epic_creation':
            message = format_epic_approval(approval, request_data)
        elif approval.request_type == 'story_creation':
            message = format_story_approval(approval, request_data)
        elif approval.request_type == 'sprint_planning':
            message = format_sprint_approval(approval, request_data)
        elif approval.request_type == 'standup_update':
            message = format_standup_approval(approval, request_data)
        else:
            message = format_generic_approval(approval, request_data)
        
        # Create inline keyboard
        keyboard = [
            [
                InlineKeyboardButton("✅ Approve", callback_data=f"approve_{approval.approval_id}"),
                InlineKeyboardButton("❌ Reject", callback_data=f"reject_{approval.approval_id}")
            ],
            [
                InlineKeyboardButton("✏️ Edit", callback_data=f"edit_{approval.approval_id}"),
                InlineKeyboardButton("👁️ View Details", callback_data=f"view_{approval.approval_id}")
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        # Send notification
        try:
            # Use markdown only for epic/story/sprint approvals
            # Standup approvals use plain text to avoid parsing errors
            parse_mode = 'Markdown' if approval.request_type != 'standup_update' else None
            
            await bot.send_message(
                chat_id=telegram_chat_id,
                text=message,
                reply_markup=reply_markup,
                parse_mode=parse_mode
            )
            logger.info(f"Sent approval notification for #{approval_id} to user {telegram_user_id}")
        except Exception as e:
            logger.error(f"Failed to send approval notification: {e}")
