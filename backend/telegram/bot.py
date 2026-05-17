"""
Main Telegram Bot Application

Handles:
- User authentication and linking
- Human-in-the-loop approval workflow
- Sprint status queries
- Notifications
"""
import logging
import time as _time
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
    meet_handler,
)
from backend.telegram.handlers import admin_handler

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
        """Build application and register all handlers."""
        logger.info("Setting up ScrumPilot Telegram Bot...")

        from telegram.request import HTTPXRequest

        # Bot API calls (sendMessage, editMessage, etc.)
        bot_request = HTTPXRequest(
            read_timeout=30,
            write_timeout=30,
            connect_timeout=15,
            pool_timeout=3,
        )
        # Updater's getUpdates long-poll — needs its own pool with slightly
        # longer read_timeout than Telegram's 30s server-side timeout.
        updater_request = HTTPXRequest(
            read_timeout=35,
            write_timeout=30,
            connect_timeout=15,
            pool_timeout=3,
        )

        self.application = (
            Application.builder()
            .token(self.config.BOT_TOKEN)
            .request(bot_request)
            .get_updates_request(updater_request)
            .build()
        )

        # ── Command handlers ──────────────────────────────────────────────────
        self.application.add_handler(CommandHandler("start",   start_handler.handle_start))
        self.application.add_handler(CommandHandler("help",    help_handler.handle_help))
        self.application.add_handler(CommandHandler("approvals", approval_handler.handle_approvals))
        self.application.add_handler(CommandHandler("sprint",  sprint_handler.handle_sprint))
        self.application.add_handler(CommandHandler("status",  sprint_handler.handle_status))
        self.application.add_handler(CommandHandler("team",    sprint_handler.handle_team))
        self.application.add_handler(CommandHandler("routing_status", sprint_handler.handle_routing_status))

        # ── Meet bot commands ─────────────────────────────────────────────────
        self.application.add_handler(CommandHandler("meet",       meet_handler.handle_meet))
        self.application.add_handler(CommandHandler("meetstop",   meet_handler.handle_meet_stop))
        self.application.add_handler(CommandHandler("meetstatus", meet_handler.handle_meet_status))
        self.application.add_handler(CommandHandler("transcript", meet_handler.handle_transcript))

        # ── Admin / routing-registry commands ─────────────────────────────────
        self.application.add_handler(CommandHandler("add_project",      admin_handler.handle_add_project))
        self.application.add_handler(CommandHandler("remove_project",   admin_handler.handle_remove_project))
        self.application.add_handler(CommandHandler("add_team_keyword", admin_handler.handle_add_team_keyword))
        self.application.add_handler(CommandHandler("list_projects",    admin_handler.handle_list_projects))

        # ── User management commands ──────────────────────────────────────────
        self.application.add_handler(CommandHandler("add_user",   admin_handler.handle_add_user))
        self.application.add_handler(CommandHandler("list_users", admin_handler.handle_list_users))
        self.application.add_handler(CommandHandler("set_role",   admin_handler.handle_set_role))

        # ── Inline button callbacks ───────────────────────────────────────────
        self.application.add_handler(CallbackQueryHandler(callback_handler.handle_callback))

        # ── Free-text message handler (conversation flows) ────────────────────
        self.application.add_handler(
            MessageHandler(filters.TEXT & ~filters.COMMAND, message_handler.handle_message)
        )

        # ── Error handler ─────────────────────────────────────────────────────
        self.application.add_error_handler(self._error_handler)

        logger.info("Bot setup complete")
        return self.application

    async def _error_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle errors."""
        error = context.error
        error_str = str(error)

        # 409 Conflict on startup is transient — the previous instance's
        # long-poll is still held by Telegram's server for up to 30s.
        # It self-resolves; no action needed.
        if "Conflict" in error_str and "getUpdates" in error_str:
            logger.debug(f"Transient startup conflict (will self-resolve): {error_str[:80]}")
            return

        logger.error(f"Update {update} caused error {error}")

        if update and update.effective_message:
            await update.effective_message.reply_text(
                "An error occurred. Please try again or contact support."
            )

    def run_polling(self):
        """Run bot in polling mode (for development).

        Calls /close first to evict any stale long-poll session that Telegram
        still holds from a previous (crashed/killed) instance, then starts fresh.
        """
        import httpx as _httpx
        token = self.config.BOT_TOKEN
        try:
            r = _httpx.post(f"https://api.telegram.org/bot{token}/close", timeout=10)
            logger.info(f"Called /close: {r.json().get('description', 'OK')}")
        except Exception as e:
            logger.debug(f"/close call failed (non-fatal): {e}")

        _time.sleep(2)  # Give Telegram 2s to release the connection

        logger.info("Starting bot in polling mode...")
        self.setup()
        self.application.run_polling(
            allowed_updates=Update.ALL_TYPES,
            drop_pending_updates=True,  # Clear queued updates from previous runs
        )

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

    if TelegramConfig.WEBHOOK_URL:
        bot.run_webhook(TelegramConfig.WEBHOOK_URL)
    else:
        logger.info("No webhook URL configured, using polling mode")
        bot.run_polling()


if __name__ == "__main__":
    main()
