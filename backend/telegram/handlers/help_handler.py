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
/start - Action menu & account linking
/help - Show this help message

*Pipeline 1 — End-to-End Meet Bot* 🎥
/meet - Join a Meet, record, transcribe & update Jira
/meet `<link>` - Start immediately with a link
/meetstatus - Check if a Meet bot is running
/meetstop - Stop the running Meet bot

*Pipeline 2 — Send Transcript* 📝
/transcript - Paste a transcript to detect type & update Jira
_(Skips meeting join/record — starts at type detection)_

*Approvals* (Human-in-the-Loop)
/approvals - View pending approval requests
• Review AI-generated epics/stories
• Approve, reject, or edit before Jira creation

*Sprint Management*
/sprint - View current sprint status
/status - View your assigned tasks
/team - View team members

---

💡 *Tip*: Use /start to see the quick-action buttons!
"""
    
    await update.effective_message.reply_text(help_text, parse_mode='Markdown')
