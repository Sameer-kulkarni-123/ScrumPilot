"""
Telegram Bot Configuration
"""
import os
from typing import Optional


class TelegramConfig:
    """Telegram bot configuration."""
    
    # Bot credentials
    BOT_TOKEN: str = os.getenv("TELEGRAM_BOT_TOKEN", "")
    WEBHOOK_URL: Optional[str] = os.getenv("TELEGRAM_WEBHOOK_URL")
    
    # Bot settings
    COMMAND_TIMEOUT_MINUTES: int = int(os.getenv("TELEGRAM_COMMAND_TIMEOUT_MINUTES", "10"))
    MAX_MESSAGE_LENGTH: int = int(os.getenv("TELEGRAM_MAX_MESSAGE_LENGTH", "4096"))
    RATE_LIMIT_PER_MINUTE: int = int(os.getenv("TELEGRAM_RATE_LIMIT_PER_MINUTE", "30"))
    
    # Approval settings
    APPROVAL_TIMEOUT_HOURS: int = int(os.getenv("APPROVAL_TIMEOUT_HOURS", "24"))
    APPROVAL_REMINDER_HOURS: int = int(os.getenv("APPROVAL_REMINDER_HOURS", "4"))
    
    # Notification settings
    NOTIFICATIONS_ENABLED: bool = os.getenv("TELEGRAM_NOTIFICATIONS_ENABLED", "true").lower() == "true"
    
    @classmethod
    def validate(cls) -> bool:
        """Validate configuration."""
        if not cls.BOT_TOKEN:
            raise ValueError("TELEGRAM_BOT_TOKEN environment variable is required")
        return True


# Validate on import
TelegramConfig.validate()
