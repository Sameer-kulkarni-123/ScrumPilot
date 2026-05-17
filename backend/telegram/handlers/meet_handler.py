"""
Meet Bot & Transcript Pipeline Handlers

Two pipelines triggered from Telegram:

1. /meet (or "Start Meet Bot" button) — End-to-End Pipeline
   Join Google Meet → Record → Transcribe → Detect type → Run pipeline → Jira

2. /transcript (or "Send Transcript" button) — Shortcut Pipeline
   User pastes transcript → Detect meeting type → Run pipeline → Jira
"""
import re
import os
import asyncio
import logging
from pathlib import Path
from datetime import datetime
from telegram import Update
from telegram.ext import ContextTypes

logger = logging.getLogger(__name__)

# Track running meet bot tasks so we can report status / prevent duplicates
_active_meet_task: asyncio.Task | None = None


# ══════════════════════════════════════════════════════════════════════════════
#  PIPELINE 1 — End-to-End Meet Bot
# ══════════════════════════════════════════════════════════════════════════════

async def handle_meet(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Handle /meet command.

    Usage:
        /meet                          → prompts for a link
        /meet https://meet.google.com/abc-defg-hij  → starts immediately
    """
    global _active_meet_task

    if _active_meet_task and not _active_meet_task.done():
        await update.message.reply_text(
            "⚠️ A Meet bot is already running.\n\n"
            "Wait for it to finish or use /meetstop to cancel it."
        )
        return

    # Check if a link was passed inline:  /meet <link>
    args = context.args  # list of words after /meet
    if args:
        link = args[0]
        if _is_valid_meet_link(link):
            await _launch_meet_bot(update, context, link)
            return
        else:
            await update.message.reply_text(
                "❌ That doesn't look like a valid Google Meet link.\n\n"
                "Please send a link like:\n"
                "`https://meet.google.com/abc-defg-hij`",
                parse_mode="Markdown",
            )
            return

    # No link supplied — ask for one
    await update.message.reply_text(
        "🎥 *Start Meet Bot (End-to-End)*\n\n"
        "Please send the Google Meet link:\n"
        "`https://meet.google.com/xxx-yyyy-zzz`",
        parse_mode="Markdown",
    )
    context.user_data["awaiting_meet_link"] = True


async def handle_meet_link_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Called from message_handler when awaiting_meet_link is True.
    Validates the link and launches the meet bot.
    """
    link = update.message.text.strip()

    if not _is_valid_meet_link(link):
        await update.message.reply_text(
            "❌ Invalid Google Meet link.\n\n"
            "Please send a valid link like:\n"
            "`https://meet.google.com/abc-defg-hij`",
            parse_mode="Markdown",
        )
        return

    context.user_data["awaiting_meet_link"] = False
    await _launch_meet_bot(update, context, link)


async def handle_meet_stop(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /meetstop command — cancel a running meet bot."""
    global _active_meet_task

    if _active_meet_task and not _active_meet_task.done():
        _active_meet_task.cancel()
        _active_meet_task = None
        await update.message.reply_text("🛑 Meet bot has been stopped.")
    else:
        await update.message.reply_text("ℹ️ No meet bot is currently running.")


async def handle_meet_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /meetstatus command — check if a meet bot is running."""
    global _active_meet_task

    if _active_meet_task and not _active_meet_task.done():
        await update.message.reply_text("🟢 Meet bot is currently running.")
    else:
        await update.message.reply_text("⚪ No meet bot is running.")


# ══════════════════════════════════════════════════════════════════════════════
#  PIPELINE 2 — Send Transcript (Shortcut)
# ══════════════════════════════════════════════════════════════════════════════

async def handle_transcript(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Handle /transcript command.
    Prompts user to paste their meeting transcript text.
    """
    await update.message.reply_text(
        "📝 *Send Transcript (Shortcut Pipeline)*\n\n"
        "Paste your meeting transcript below.\n\n"
        "The bot will:\n"
        "1️⃣ Detect meeting type (standup / sprint planning / backlog)\n"
        "2️⃣ Run the appropriate pipeline\n"
        "3️⃣ Send approval request\n"
        "4️⃣ Update Jira on approval\n\n"
        "_Send your transcript as a single message:_",
        parse_mode="Markdown",
    )
    context.user_data["awaiting_transcript"] = True


async def handle_transcript_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Called from message_handler when awaiting_transcript or awaiting_second_transcript is True.
    Takes the pasted transcript and runs the detect → pipeline → Jira flow.
    """
    transcript = update.message.text.strip()

    if len(transcript) < 50:
        await update.message.reply_text(
            "⚠️ That transcript seems too short (< 50 characters).\n"
            "Please paste the full meeting transcript.\n\n"
            "Use /transcript to try again.",
        )
        context.user_data["awaiting_transcript"] = False
        context.user_data["awaiting_second_transcript_pm"] = False
        context.user_data["awaiting_second_transcript_grooming"] = False
        return

    chat_id = update.effective_chat.id

    # -- Check if we are receiving the second transcript --
    if context.user_data.get("awaiting_second_transcript_pm"):
        context.user_data["awaiting_second_transcript_pm"] = False
        pm_transcript_text = transcript
        grooming_transcript_text = context.user_data.get("first_transcript_text", "")
        await _run_backlog_pipeline_from_texts(update, context, pm_transcript_text, grooming_transcript_text)
        return

    if context.user_data.get("awaiting_second_transcript_grooming"):
        context.user_data["awaiting_second_transcript_grooming"] = False
        grooming_transcript_text = transcript
        pm_transcript_text = context.user_data.get("first_transcript_text", "")
        await _run_backlog_pipeline_from_texts(update, context, pm_transcript_text, grooming_transcript_text)
        return

    # -- Normal first transcript processing --
    context.user_data["awaiting_transcript"] = False

    await update.message.reply_text(
        "⏳ *Processing transcript…*\n\n"
        "🔍 Detecting meeting type…",
        parse_mode="Markdown",
    )

    from backend.pipelines.intelligent_meet_bot import MeetingTypeDetector
    detector = MeetingTypeDetector()
    detection = detector.detect(transcript)
    detected_type = detection.meeting_type
    confidence = detection.confidence
    keywords = ', '.join(detection.keywords_found[:5]) or 'none'

    await context.bot.send_message(
        chat_id=chat_id,
        text=(
            f"🔍 *Meeting Type Detected*\n\n"
            f"Type: `{detected_type}`\n"
            f"Confidence: {confidence:.0%}\n"
            f"Keywords: {keywords}\n"
        ),
        parse_mode="Markdown",
    )

    if detected_type == 'pm_backlog':
        await context.bot.send_message(
            chat_id=chat_id,
            text=(
                "⚠️ *Backlog Pipeline requires two transcripts!*\n\n"
                "I have the *PM Backlog* transcript.\n"
                "Please paste your *Grooming* meeting transcript now:"
            ),
            parse_mode="Markdown",
        )
        context.user_data["first_transcript_text"] = transcript
        context.user_data["awaiting_second_transcript_grooming"] = True
        return

    elif detected_type == 'grooming':
        await context.bot.send_message(
            chat_id=chat_id,
            text=(
                "⚠️ *Backlog Pipeline requires two transcripts!*\n\n"
                "I have the *Grooming* transcript.\n"
                "Please paste your *PM Backlog* meeting transcript now:"
            ),
            parse_mode="Markdown",
        )
        context.user_data["first_transcript_text"] = transcript
        context.user_data["awaiting_second_transcript_pm"] = True
        return

    elif detected_type == 'unknown':
        await context.bot.send_message(
            chat_id=chat_id,
            text=(
                "❌ *Could not detect meeting type*\n\n"
                "The transcript didn't match any known meeting pattern.\n"
                "Try pasting a more detailed transcript."
            ),
            parse_mode="Markdown",
        )
        return

    # -- Single-transcript pipelines (Scrum, Sprint Planning) --
    async def _run_single_transcript_pipeline():
        """Run single-transcript pipeline (Scrum or Sprint Planning) in background."""
        try:
            from backend.pipelines.scrum_pipeline import ScrumPipeline
            from backend.pipelines.sprint_planning_pipeline import SprintPlanningPipeline

            bot_id = datetime.now().strftime('%Y%m%d_%H%M%S')
            output_dir = "backend/data/meetings"
            Path(output_dir).mkdir(parents=True, exist_ok=True)
            transcript_file = os.path.join(output_dir, f"{bot_id}_transcript.txt")

            with open(transcript_file, 'w', encoding='utf-8') as f:
                f.write(transcript)

            if detected_type in ('daily_standup', 'sprint_planning'):
                from backend.telegram.services.approval_service import approval_service

                pipeline_type = 'standup' if detected_type == 'daily_standup' else 'sprint'
                pm_user_id = approval_service.get_pm_user_id()
                if not pm_user_id:
                    raise Exception(
                        "No PM user found for approval. "
                        "Please ensure a product_owner user exists and has Telegram linked."
                    )

                requester_user_id = approval_service.get_requester_user_id(pm_user_id)
                transcript_preview = transcript[:280].replace("`", "'").strip()
                approval_data = {
                    "pipeline_type": pipeline_type,
                    "transcript_file": transcript_file,
                    "detected_type": detected_type,
                    "transcript_preview": transcript_preview,
                    "summary": {
                        "extraction_pending": True,
                    },
                }

                approval_id = approval_service.create_project_selection_approval(
                    request_data=approval_data,
                    requested_by_user_id=requester_user_id,
                    assigned_to_user_id=pm_user_id,
                    priority='high',
                )

                pipeline_info = (
                    "Pipeline: Scrum (Standup)\n"
                    if pipeline_type == 'standup'
                    else "Pipeline: Sprint Planning\n"
                )
                pipeline_info += (
                    "Status: paused\n"
                    "Step: project selection pending\n"
                    f"Approval ID: #{approval_id}"
                )

                await context.bot.send_message(
                    chat_id=chat_id,
                    text=(
                        f"*Project Selection Requested*\n\n"
                        f"{pipeline_info}\n\n"
                        "Check Telegram approvals and choose the Jira project.\n"
                        "Extraction and Jira updates will run only after that selection."
                    ),
                    parse_mode="Markdown",
                )
                return

            await context.bot.send_message(
                chat_id=chat_id,
                text=f"⏳ Running `{detected_type}` pipeline…",
                parse_mode="Markdown",
            )

            if detected_type == 'daily_standup':
                pipeline = ScrumPipeline(require_telegram_approval=True)
                result = pipeline.run(
                    transcript_path=transcript_file,
                    update_jira=True,
                    dry_run=False
                )
                pipeline_info = (
                    f"Pipeline: Scrum (Standup)\n"
                    f"Status: {result.status}\n"
                    f"Actions: {result.total_actions}\n"
                    f"Approval ID: #{result.approval_id}"
                )

            elif detected_type == 'sprint_planning':
                pipeline = SprintPlanningPipeline(require_telegram_approval=True)
                result = pipeline.run(
                    transcript_path=transcript_file,
                    create_in_jira=True,
                    dry_run=False
                )
                sprint_goal = result.sprint_goal if hasattr(result, 'sprint_goal') else 'N/A'
                pipeline_info = (
                    f"Pipeline: Sprint Planning\n"
                    f"Status: {result.status}\n"
                    f"Sprint Goal: {sprint_goal}\n"
                    f"Approval ID: #{result.approval_id}"
                )
            else:
                return

            await context.bot.send_message(
                chat_id=chat_id,
                text=(
                    f"✅ *Pipeline Complete!*\n\n"
                    f"{pipeline_info}\n\n"
                    f"📱 Check /approvals to approve and update Jira."
                ),
                parse_mode="Markdown",
            )

        except Exception as e:
            logger.error(f"Single transcript pipeline error: {e}", exc_info=True)
            await context.bot.send_message(
                chat_id=chat_id,
                text=f"❌ *Pipeline Error*\n\n`{str(e)[:500]}`",
                parse_mode="Markdown",
            )

    asyncio.create_task(_run_single_transcript_pipeline())

async def _run_backlog_pipeline_from_texts(update: Update, context: ContextTypes.DEFAULT_TYPE, pm_text: str, grooming_text: str):
    """Run the backlog pipeline taking both PM and Grooming texts."""
    chat_id = update.effective_chat.id
    
    await update.message.reply_text(
        "⏳ *Both transcripts received!*\n\n"
        "Running `Backlog` pipeline (PM + Grooming)…",
        parse_mode="Markdown",
    )

    async def _run():
        try:
            from backend.pipelines.backlog_pipeline import BacklogPipeline
            
            bot_id = datetime.now().strftime('%Y%m%d_%H%M%S')
            pm_file = f"backend/data/meetings/{bot_id}_pm.txt"
            grooming_file = f"backend/data/meetings/{bot_id}_grooming.txt"
            Path("backend/data/meetings").mkdir(parents=True, exist_ok=True)
            
            with open(pm_file, 'w', encoding='utf-8') as f:
                f.write(pm_text)
            with open(grooming_file, 'w', encoding='utf-8') as f:
                f.write(grooming_text)
                
            pipeline = BacklogPipeline()
            result = pipeline.run(
                pm_transcript_path=pm_file,
                grooming_transcript_path=grooming_file,
                create_in_jira=True,
                dry_run=False
            )
            
            total_epics = result.total_epics if hasattr(result, 'total_epics') else 0
            pipeline_info = (
                f"Pipeline: Backlog\n"
                f"Status: {result.status}\n"
                f"Epics: {total_epics}\n"
                f"Approval ID: #{result.approval_id if hasattr(result, 'approval_id') else 'N/A'}"
            )
            
            await context.bot.send_message(
                chat_id=chat_id,
                text=(
                    f"✅ *Pipeline Complete!*\n\n"
                    f"{pipeline_info}\n\n"
                    f"📱 Check /approvals to approve and update Jira."
                ),
                parse_mode="Markdown",
            )

        except Exception as e:
            logger.error(f"Backlog pipeline error: {e}", exc_info=True)
            await context.bot.send_message(
                chat_id=chat_id,
                text=f"❌ *Pipeline Error*\n\n`{str(e)[:500]}`",
                parse_mode="Markdown",
            )

    asyncio.create_task(_run())


# ══════════════════════════════════════════════════════════════════════════════
#  INTERNAL HELPERS
# ══════════════════════════════════════════════════════════════════════════════

def _is_valid_meet_link(link: str) -> bool:
    """Return True if *link* looks like a Google Meet URL."""
    return bool(re.match(r"https?://meet\.google\.com/[a-z]{3}-[a-z]{4}-[a-z]{3}", link))


async def _launch_meet_bot(update: Update, context: ContextTypes.DEFAULT_TYPE, meet_link: str):
    """Spin up the complete_meet_bot_workflow as a background asyncio task."""
    global _active_meet_task

    await update.message.reply_text(
        f"🚀 *Meet Bot Starting (End-to-End)!*\n\n"
        f"🔗 Link: `{meet_link}`\n\n"
        f"The bot will:\n"
        f"1️⃣ Join the meeting\n"
        f"2️⃣ Record audio\n"
        f"3️⃣ Transcribe when the meeting ends\n"
        f"4️⃣ Detect meeting type\n"
        f"5️⃣ Run the appropriate pipeline\n"
        f"6️⃣ Send approval → Update Jira\n\n"
        f"Use /meetstatus to check progress.\n"
        f"Use /meetstop to cancel.",
        parse_mode="Markdown",
    )

    chat_id = update.effective_chat.id

    async def _run_and_notify():
        """Run the complete pipeline and send updates via Telegram."""
        from backend.pipelines.complete_meet_bot import complete_meet_bot_workflow

        try:
            result = await complete_meet_bot_workflow(meet_link)

            status = result.get('status', 'unknown')

            if status == 'success':
                pipeline_result = result.get('pipeline_result', {})
                await context.bot.send_message(
                    chat_id=chat_id,
                    text=(
                        f"✅ *Meet Bot Complete!*\n\n"
                        f"Meeting Type: `{result.get('detected_type', 'N/A')}`\n"
                        f"Confidence: {result.get('confidence', 0):.0%}\n"
                        f"Pipeline: `{pipeline_result.get('pipeline', 'N/A')}`\n"
                        f"Status: {pipeline_result.get('status', 'N/A')}\n"
                        f"Approval ID: #{pipeline_result.get('approval_id', 'N/A')}\n\n"
                        f"📱 Check /approvals to review and update Jira."
                    ),
                    parse_mode="Markdown",
                )
            else:
                error = result.get('error', 'Unknown error')
                transcript_file = result.get('transcript_file', '')
                msg = f"❌ *Meet Bot Failed*\n\n`{error}`"
                if transcript_file:
                    msg += f"\n\nTranscript saved: `{transcript_file}`"
                await context.bot.send_message(
                    chat_id=chat_id,
                    text=msg,
                    parse_mode="Markdown",
                )

        except asyncio.CancelledError:
            await context.bot.send_message(
                chat_id=chat_id,
                text="🛑 Meet bot was cancelled.",
            )
        except Exception as e:
            logger.error(f"Meet bot pipeline error: {e}", exc_info=True)
            await context.bot.send_message(
                chat_id=chat_id,
                text=f"❌ *Meet Bot Error*\n\n`{str(e)[:500]}`",
                parse_mode="Markdown",
            )

    _active_meet_task = asyncio.create_task(_run_and_notify())
