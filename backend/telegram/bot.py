"""
Main Telegram Bot Application

Handles:
- User authentication and linking
- Human-in-the-loop approval workflow
- Sprint status queries
- Notifications
"""
import logging
from dotenv import load_dotenv

# Load environment variables FIRST
load_dotenv()

from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    filters,
    ContextTypes,
)

from backend.telegram.config import TelegramConfig
from backend.telegram.handlers import (
    start_handler,
    help_handler,
    approval_handler,
    sprint_handler,
    callback_handler,
    message_handler,
)

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)


class ScrumPilotBot:
    """Main Telegram bot application."""
    
    def __init__(self):
        """Initialize bot."""
        self.config = TelegramConfig
        self.application = None
    
    def setup(self) -> Application:
        """Setup bot application with handlers."""
        logger.info("Setting up ScrumPilot Telegram Bot...")
        
        # Create application
        self.application = Application.builder().token(self.config.BOT_TOKEN).build()
        
        # Register command handlers
        self.application.add_handler(CommandHandler("start", start_handler.handle_start))
        self.application.add_handler(CommandHandler("help", help_handler.handle_help))
        self.application.add_handler(CommandHandler("approvals", approval_handler.handle_approvals))
        self.application.add_handler(CommandHandler("sprint", sprint_handler.handle_sprint))
        self.application.add_handler(CommandHandler("status", sprint_handler.handle_status))
        self.application.add_handler(CommandHandler("team", sprint_handler.handle_team))
        
        # Register callback query handler (for inline buttons)
        self.application.add_handler(CallbackQueryHandler(callback_handler.handle_callback))
        
        # Register message handler (for conversation flows)
        self.application.add_handler(
            MessageHandler(filters.TEXT & ~filters.COMMAND, message_handler.handle_message)
        )
        
        # Error handler
        self.application.add_error_handler(self._error_handler)
        
        logger.info("Bot setup complete")
        return self.application
    
    async def _error_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle errors."""
        logger.error(f"Update {update} caused error {context.error}")
        
        if update and update.effective_message:
            await update.effective_message.reply_text(
                "❌ An error occurred. Please try again or contact support."
            )
    
    def run_polling(self):
        """Run bot in polling mode (for development)."""
        logger.info("Starting bot in polling mode...")
        self.setup()
        self.application.run_polling(allowed_updates=Update.ALL_TYPES)
    
    def run_webhook(self, webhook_url: str, port: int = 8443):
        """Run bot in webhook mode (for production)."""
        logger.info(f"Starting bot in webhook mode: {webhook_url}")
        self.setup()
        self.application.run_webhook(
            listen="0.0.0.0",
            port=port,
            url_path="telegram",
            webhook_url=f"{webhook_url}/telegram"
        )


def main():
    """Main entry point."""
    bot = ScrumPilotBot()
    
    # Use webhook if URL is configured, otherwise polling
    if TelegramConfig.WEBHOOK_URL:
        bot.run_webhook(TelegramConfig.WEBHOOK_URL)
    else:
        logger.info("No webhook URL configured, using polling mode")
        bot.run_polling()


if __name__ == "__main__":
    main()
