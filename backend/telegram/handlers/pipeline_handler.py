"""
Telegram handlers for starting ScrumPilot pipelines.

Supports:
- /meet <google-meet-link> [meeting_type]
- /transcript [meeting_type], followed by pasted transcript text
"""
import asyncio
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional

from telegram import Update
from telegram.ext import ContextTypes

from backend.db.connection import get_session
from backend.db.models import User

logger = logging.getLogger(__name__)

SUPPORTED_TRANSCRIPT_TYPES = {"daily_standup", "sprint_planning"}
SUPPORTED_MEET_TYPES = SUPPORTED_TRANSCRIPT_TYPES | {"auto"}


def _normalise_meeting_type(raw_type: Optional[str]) -> Optional[str]:
    """Normalize user-facing meeting type aliases."""
    if not raw_type:
        return None

    meeting_type = raw_type.strip().lower().replace("-", "_")
    aliases = {
        "standup": "daily_standup",
        "daily": "daily_standup",
        "scrum": "daily_standup",
        "sprint": "sprint_planning",
        "planning": "sprint_planning",
        "auto_detect": "auto",
        "detect": "auto",
    }
    return aliases.get(meeting_type, meeting_type)


async def _get_linked_user(update: Update) -> Optional[User]:
    """Return the linked ScrumPilot user for the Telegram user."""
    tg_user = update.effective_user
    if not tg_user:
        return None

    with get_session() as session:
        user = session.query(User).filter(User.telegram_user_id == tg_user.id).first()
        if not user:
            return None

        session.expunge(user)
        return user


async def _require_linked_user(update: Update) -> Optional[User]:
    user = await _get_linked_user(update)
    if user:
        return user

    await update.effective_message.reply_text(
        "Please link your account first with /start, then try this again."
    )
    return None


async def handle_meet(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Start the full Meet automation from Telegram.

    Usage:
        /meet https://meet.google.com/abc-defg-hij
        /meet https://meet.google.com/abc-defg-hij daily_standup
        /meet https://meet.google.com/abc-defg-hij sprint_planning
    """
    user = await _require_linked_user(update)
    if not user:
        return

    if not context.args:
        await update.message.reply_text(
            "Send a Google Meet link like:\n"
            "/meet https://meet.google.com/abc-defg-hij\n\n"
            "Optional type: daily_standup or sprint_planning"
        )
        return

    meet_link = context.args[0].strip()
    meeting_type = _normalise_meeting_type(context.args[1]) if len(context.args) > 1 else "auto"

    if meeting_type not in SUPPORTED_MEET_TYPES:
        await update.message.reply_text(
            "Unsupported meeting type. Use daily_standup, sprint_planning, or omit it for auto-detect."
        )
        return

    force_type = None if meeting_type == "auto" else meeting_type
    await update.message.reply_text(
        "Got it. I am starting the Meet bot now. I will join, record, transcribe, "
        "detect the meeting type, and submit the pipeline result for approval."
    )

    asyncio.create_task(
        _run_meet_pipeline(update.effective_chat.id, context, meet_link, force_type)
    )


async def _run_meet_pipeline(
    chat_id: int,
    context: ContextTypes.DEFAULT_TYPE,
    meet_link: str,
    force_type: Optional[str],
) -> None:
    try:
        from backend.pipelines.complete_meet_bot import complete_meet_bot_workflow

        result = await complete_meet_bot_workflow(
            meet_link=meet_link,
            force_type=force_type,
        )
        status = result.get("status", "unknown") if isinstance(result, dict) else "completed"
        approval_id = None
        pipeline_result = result.get("pipeline_result", {}) if isinstance(result, dict) else {}
        if isinstance(pipeline_result, dict):
            approval_id = pipeline_result.get("approval_id")

        message = f"Meet pipeline finished with status: {status}."
        if approval_id:
            message += f"\nApproval ID: #{approval_id}"
        await context.bot.send_message(chat_id=chat_id, text=message)
    except Exception as exc:
        logger.exception("Meet pipeline failed")
        await context.bot.send_message(
            chat_id=chat_id,
            text=f"Meet pipeline failed: {exc}",
        )


async def handle_transcript(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Ask the user for a transcript and run the matching pipeline without Meet/audio.

    Usage:
        /transcript daily_standup
        /transcript sprint_planning
        /transcript auto
    """
    user = await _require_linked_user(update)
    if not user:
        return

    meeting_type = _normalise_meeting_type(context.args[0]) if context.args else "auto"
    if meeting_type not in SUPPORTED_TRANSCRIPT_TYPES | {"auto"}:
        await update.message.reply_text(
            "Unsupported transcript type. Use daily_standup, sprint_planning, or auto."
        )
        return

    context.user_data["awaiting_pipeline_transcript"] = True
    context.user_data["pipeline_transcript_type"] = meeting_type

    await update.message.reply_text(
        "Paste the transcript in your next message. I will skip Meet joining and audio processing, "
        "then run the matching pipeline directly."
    )


async def handle_transcript_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle pasted transcript text after /transcript."""
    transcript = update.message.text.strip()
    if not transcript:
        await update.message.reply_text("That transcript looks empty. Please paste the transcript text.")
        return

    meeting_type = context.user_data.get("pipeline_transcript_type", "auto")
    context.user_data["awaiting_pipeline_transcript"] = False
    context.user_data.pop("pipeline_transcript_type", None)

    await update.message.reply_text("Transcript received. I am running the pipeline in the background.")
    asyncio.create_task(
        _run_transcript_pipeline(update.effective_chat.id, context, transcript, meeting_type)
    )


async def _run_transcript_pipeline(
    chat_id: int,
    context: ContextTypes.DEFAULT_TYPE,
    transcript: str,
    meeting_type: str,
) -> None:
    try:
        from run_complete_meet_bot import complete_meet_bot_from_transcript

        force_type = None if meeting_type == "auto" else meeting_type
        transcript_path = _save_transcript(transcript, meeting_type)
        result = await asyncio.to_thread(
            lambda: complete_meet_bot_from_transcript(
                transcript=transcript,
                force_type=force_type,
                transcript_file=str(transcript_path),
            )
        )

        if result.get("status") != "success":
            await context.bot.send_message(
                chat_id=chat_id,
                text=f"Transcript pipeline failed: {result.get('error', 'unknown error')}",
            )
            return

        pipeline_result = result.get("pipeline_result", {})
        pipeline = pipeline_result.get("pipeline", result.get("detected_type", "unknown"))
        approval_id = pipeline_result.get("approval_id")

        summary = (
            "Transcript complete-bot pipeline submitted.\n"
            f"Detected type: {result.get('detected_type')}\n"
            f"Pipeline: {pipeline}\n"
            f"Status: {pipeline_result.get('status')}"
        )
        if approval_id:
            summary += f"\nApproval ID: #{approval_id}"

        await context.bot.send_message(chat_id=chat_id, text=summary)
    except Exception as exc:
        logger.exception("Transcript pipeline failed")
        await context.bot.send_message(
            chat_id=chat_id,
            text=f"Transcript pipeline failed: {exc}",
        )


def _save_transcript(transcript: str, meeting_type: str) -> Path:
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_dir = Path("backend/data/telegram_transcripts")
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / f"{timestamp}_{meeting_type}.txt"
    output_path.write_text(transcript, encoding="utf-8")
    return output_path
