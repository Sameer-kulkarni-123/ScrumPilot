"""
/help Command Handler
"""
from telegram import Update
from telegram.ext import ContextTypes


async def handle_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /help command."""
    help_text = """
ScrumPilot Bot Commands

Account
/start - Link your Telegram account
/jira - Link or view your own Jira identity
/adduser email role Display Name - Add a ScrumPilot user for Telegram/Jira assignment
/addjira email jira-id Display Name - Add Jira identity for an existing ScrumPilot user
/updateuser email field value - Update name, role, email, jira, or jira_name
/help - Show this help message

Approvals
/approvals - View pending approval requests
- Review AI-generated epics/stories
- Approve, reject, or edit before Jira creation

Sprint Management
/sprint - View current sprint status
/status - View your assigned tasks
/team - View team members

Run Pipelines
/meet <google-meet-link> [daily_standup|sprint_planning] - Join, record, transcribe, and run a pipeline
/transcript [auto|daily_standup|sprint_planning] - Paste a transcript and run a pipeline without joining Meet

Notifications
You'll receive automatic notifications for:
- Pending approvals
- Sprint updates
- Task assignments
- Epic/story creation

Tip: Use inline buttons to quickly approve or reject requests.
"""

    await update.message.reply_text(help_text)
