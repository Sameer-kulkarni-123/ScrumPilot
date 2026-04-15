"""
/help Command Handler
"""
from telegram import Update
from telegram.ext import ContextTypes


async def handle_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /help command."""
    help_text = """
🤖 *ScrumPilot Bot Commands*

*Account*
/start - Link your Telegram account
/help - Show this help message

*Approvals* (Human-in-the-Loop)
/approvals - View pending approval requests
• Review AI-generated epics/stories
• Approve, reject, or edit before Jira creation

*Sprint Management*
/sprint - View current sprint status
/status - View your assigned tasks
/team - View team members

*Notifications*
You'll receive automatic notifications for:
• Pending approvals
• Sprint updates
• Task assignments
• Epic/story creation

---

💡 *Tip*: Use inline buttons to quickly approve or reject requests!
"""
    
    await update.message.reply_text(help_text, parse_mode='Markdown')
