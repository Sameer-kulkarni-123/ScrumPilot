"""
Sprint and Status Handlers
"""
from telegram import Update
from telegram.ext import ContextTypes

from backend.db.connection import get_session
from backend.db.models import User, Sprint, SprintStory


async def handle_sprint(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /sprint command - show current sprint."""
    user = update.effective_user
    
    with get_session() as session:
        db_user = session.query(User).filter(
            User.telegram_user_id == user.id
        ).first()
        
        if not db_user:
            await update.message.reply_text(
                "❌ Your account is not linked.\n\nUse /start to link your account."
            )
            return
        
        # Get active sprint
        sprint = session.query(Sprint).filter(
            Sprint.status == 'active'
        ).first()
        
        if not sprint:
            await update.message.reply_text(
                "ℹ️ No active sprint found.\n\n"
                "Sprint planning may not have been completed yet."
            )
            return
        
        # Get sprint stories
        sprint_stories = session.query(SprintStory).filter(
            SprintStory.sprint_id == sprint.sprint_id
        ).all()
        
        # Format message
        message = f"🏃 *{sprint.sprint_name}*\n\n"
        message += f"*Goal*: {sprint.sprint_goal}\n"
        message += f"*Duration*: {sprint.start_date} to {sprint.end_date}\n"
        message += f"*Status*: {sprint.status.upper()}\n\n"
        message += f"*Committed Stories*: {len(sprint_stories)}\n"
        
        if sprint.velocity_target:
            message += f"*Target Velocity*: {sprint.velocity_target} points\n"
        
        if sprint.team_capacity_hours:
            message += f"*Team Capacity*: {sprint.team_capacity_hours} hours\n"
        
        await update.message.reply_text(message, parse_mode='Markdown')


async def handle_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /status command - show user's assigned tasks."""
    user = update.effective_user
    
    with get_session() as session:
        db_user = session.query(User).filter(
            User.telegram_user_id == user.id
        ).first()
        
        if not db_user:
            await update.message.reply_text(
                "❌ Your account is not linked.\n\nUse /start to link your account."
            )
            return
        
        # Get user's assigned tasks in active sprint
        from backend.db.models import Task, Story, SprintStory, Sprint
        
        active_sprint = session.query(Sprint).filter(
            Sprint.status == 'active'
        ).first()
        
        if not active_sprint:
            await update.message.reply_text(
                "ℹ️ No active sprint.\n\n"
                "You don't have any assigned tasks yet."
            )
            return
        
        # Get tasks assigned to user in active sprint
        tasks = session.query(Task).join(
            Story, Task.story_id == Story.id
        ).join(
            SprintStory, Story.id == SprintStory.story_id
        ).filter(
            SprintStory.sprint_id == active_sprint.sprint_id,
            Task.assignee_user_id == db_user.id
        ).all()
        
        if not tasks:
            await update.message.reply_text(
                f"✅ No tasks assigned to you in {active_sprint.sprint_name}.\n\n"
                f"You're all clear! 🎉"
            )
            return
        
        # Format message
        message = f"📋 *Your Tasks in {active_sprint.sprint_name}*\n\n"
        
        for task in tasks:
            status_emoji = {
                'To Do': '⚪',
                'In Progress': '🔵',
                'Done': '✅'
            }.get(task.jira_status, '⚪')
            
            message += f"{status_emoji} *{task.jira_key}*: {task.title}\n"
            message += f"   Status: {task.jira_status or 'To Do'}\n"
            if task.estimated_hours:
                message += f"   Estimate: {task.estimated_hours}h\n"
            message += "\n"
        
        await update.message.reply_text(message, parse_mode='Markdown')


async def handle_team(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /team command - show team members."""
    user = update.effective_user
    
    with get_session() as session:
        db_user = session.query(User).filter(
            User.telegram_user_id == user.id
        ).first()
        
        if not db_user:
            await update.message.reply_text(
                "❌ Your account is not linked.\n\nUse /start to link your account."
            )
            return
        
        # Get all users with Telegram linked
        team_members = session.query(User).filter(
            User.telegram_user_id.isnot(None)
        ).all()
        
        if not team_members:
            await update.message.reply_text(
                "ℹ️ No team members found with linked Telegram accounts."
            )
            return
        
        # Format message
        message = f"👥 *Team Members*\n\n"
        
        for member in team_members:
            role = member.role.role_name if member.role else 'No role'
            telegram_username = f"@{member.telegram_username}" if member.telegram_username else "No username"
            
            message += f"• *{member.display_name}*\n"
            message += f"  Role: {role}\n"
            message += f"  Telegram: {telegram_username}\n"
            message += f"  Email: {member.email or 'N/A'}\n\n"
        
        await update.message.reply_text(message, parse_mode='Markdown')
