"""
Callback Query Handler

Handles inline button clicks for:
- Approve/Reject approval requests
- Edit approval data
- View approval details
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


async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Handle callback queries from inline buttons.
    
    Callback data formats:
    - "action_approval_id": approve_123, reject_123, edit_123, view_123, back_123
    - "edit_epic_approval_id_epic_index": edit_epic_123_0
    """
    query = update.callback_query
    await query.answer()  # Acknowledge button click
    
    user = update.effective_user
    callback_data = query.data
    
    # Handle special edit_epic callback
    if callback_data.startswith('edit_epic_'):
        parts = callback_data.split('_')
        if len(parts) >= 4:  # edit_epic_approval_id_epic_index
            try:
                approval_id = int(parts[2])
                epic_index = int(parts[3])
                await handle_edit_epic_item(update, context, approval_id, epic_index)
                return
            except (ValueError, IndexError):
                await query.edit_message_text("❌ Invalid edit request")
                return
    
    # Parse standard callback data
    parts = callback_data.split('_', 1)
    if len(parts) != 2:
        await query.edit_message_text("❌ Invalid action")
        return
    
    action, approval_id_str = parts
    
    try:
        approval_id = int(approval_id_str)
    except ValueError:
        await query.edit_message_text("❌ Invalid approval ID")
        return
    
    # Get user from database
    with get_session() as session:
        db_user = session.query(User).filter(
            User.telegram_user_id == user.id
        ).first()
        
        if not db_user:
            await query.edit_message_text(
                "❌ Your account is not linked.\n\n"
                "Use /start to link your account."
            )
            return
        
        # Get approval request
        approval = session.query(ApprovalRequest).filter(
            ApprovalRequest.approval_id == approval_id
        ).first()
        
        if not approval:
            await query.edit_message_text("❌ Approval request not found")
            return
        
        # Check if user is assigned to this approval
        if approval.assigned_to != db_user.id:
            await query.edit_message_text(
                "❌ You are not assigned to this approval request"
            )
            return
        
        # Check if already processed (skip for view and back actions)
        if approval.status != 'pending' and action not in ['view', 'back']:
            await query.edit_message_text(
                f"ℹ️ This approval has already been {approval.status}"
            )
            return
        
        # Handle action
        if action == 'approve':
            await handle_approve(query, session, approval, db_user)
        elif action == 'reject':
            await handle_reject(query, session, approval, db_user, context)
        elif action == 'edit':
            await handle_edit(query, session, approval, db_user, context)
        elif action == 'view':
            await handle_view(query, session, approval)
        elif action == 'back':
            await handle_back(query, session, approval)
        else:
            await query.edit_message_text(f"❌ Unknown action: {action}")


async def handle_approve(query, session, approval: ApprovalRequest, user: User):
    """
    Handle approval action.
    
    Marks approval as approved and triggers Jira creation.
    """
    logger.info(f"User {user.display_name} approved request #{approval.approval_id}")
    
    # Update approval status
    approval.status = 'approved'
    approval.reviewed_at = datetime.now(timezone.utc)
    approval.approved_data = approval.request_data  # Use original data
    
    # Log in approval history
    crud.add_approval_history(
        session=session,
        approval_id=approval.approval_id,
        action='approved',
        performed_by=user.id,
        comment=None
    )
    
    session.commit()
    
    # Update message
    await query.edit_message_text(
        f"✅ *Approved by {user.display_name}*\n\n"
        f"{query.message.text}\n\n"
        f"⏳ Creating in Jira...",
        parse_mode='Markdown'
    )
    
    # Trigger Jira creation (async)
    try:
        created_keys = await execute_approval(approval)
        
        # Build success message with Jira keys (avoid markdown parsing issues)
        success_msg = f"✅ Approved by {user.display_name}\n\n"
        
        if created_keys:
            success_msg += f"✅ Successfully created in Jira:\n"
            for key in created_keys:
                success_msg += f"  • {key}\n"
        else:
            success_msg += f"✅ Successfully processed!"
        
        await query.edit_message_text(
            success_msg,
            parse_mode=None  # Disable markdown to avoid parsing errors
        )
    except Exception as e:
        logger.error(f"Failed to execute approval: {e}")
        error_msg = str(e)[:200]  # Limit error message length
        await query.edit_message_text(
            f"✅ Approved by {user.display_name}\n\n"
            f"❌ Error creating in Jira:\n{error_msg}",
            parse_mode=None
        )


async def handle_reject(query, session, approval: ApprovalRequest, user: User, context: ContextTypes.DEFAULT_TYPE):
    """
    Handle rejection action.
    
    Asks for rejection reason.
    """
    logger.info(f"User {user.display_name} rejected request #{approval.approval_id}")
    
    # Ask for rejection reason
    await query.edit_message_text(
        f"❌ *Rejecting Approval #{approval.approval_id}*\n\n"
        f"Please send the rejection reason:",
        parse_mode='Markdown'
    )
    
    # Set conversation state
    context.user_data['awaiting_rejection_reason'] = approval.approval_id


async def handle_rejection_reason(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Handle rejection reason input.
    
    Called from message_handler when awaiting_rejection_reason is set.
    """
    approval_id = context.user_data.get('awaiting_rejection_reason')
    if not approval_id:
        return
    
    reason = update.message.text.strip()
    user = update.effective_user
    
    with get_session() as session:
        db_user = session.query(User).filter(
            User.telegram_user_id == user.id
        ).first()
        
        if not db_user:
            await update.message.reply_text("❌ User not found")
            return
        
        approval = session.query(ApprovalRequest).filter(
            ApprovalRequest.approval_id == approval_id
        ).first()
        
        if not approval:
            await update.message.reply_text("❌ Approval not found")
            return
        
        # Update approval status
        approval.status = 'rejected'
        approval.reviewed_at = datetime.now(timezone.utc)
        approval.rejection_reason = reason
        
        # Log in approval history
        crud.add_approval_history(
            session=session,
            approval_id=approval.approval_id,
            action='rejected',
            performed_by=db_user.id,
            comment=reason
        )
        
        session.commit()
        
        await update.message.reply_text(
            f"❌ *Approval #{approval_id} Rejected*\n\n"
            f"Reason: {reason}\n\n"
            f"The request has been cancelled.",
            parse_mode='Markdown'
        )
        
        context.user_data['awaiting_rejection_reason'] = None


async def handle_edit(query, session, approval: ApprovalRequest, user: User, context: ContextTypes.DEFAULT_TYPE):
    """
    Handle edit action.
    
    Allows user to modify approval data before approving.
    """
    logger.info(f"User {user.display_name} editing request #{approval.approval_id}")
    
    # Show edit options based on request type
    if approval.request_type == 'epic_creation':
        await show_epic_edit_options(query, approval, context)
    elif approval.request_type == 'story_creation':
        await show_story_edit_options(query, approval, context)
    else:
        await query.edit_message_text(
            "✏️ Editing is not yet supported for this request type.\n\n"
            "You can approve or reject."
        )


async def show_epic_edit_options(query, approval: ApprovalRequest, context: ContextTypes.DEFAULT_TYPE):
    """Show edit options for epic creation."""
    request_data = approval.request_data or {}
    epics = request_data.get('epics', [])
    
    message = "✏️ Edit Epic Creation\n\n"
    message += "Select an epic to edit:\n\n"
    
    # Create keyboard with epic options
    keyboard = []
    for i, epic in enumerate(epics[:10], 1):  # Limit to 10
        title = epic.get('title', 'Untitled')[:30]  # Truncate
        wsjf = epic.get('wsjf', {}).get('wsjf_score', 0)
        keyboard.append([
            InlineKeyboardButton(
                f"{i}. {title} (WSJF: {wsjf:.1f})",
                callback_data=f"edit_epic_{approval.approval_id}_{i-1}"
            )
        ])
    
    keyboard.append([
        InlineKeyboardButton("« Back", callback_data=f"back_{approval.approval_id}")
    ])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        message,
        reply_markup=reply_markup
    )


async def handle_edit_epic_item(update: Update, context: ContextTypes.DEFAULT_TYPE, approval_id: int, epic_index: int):
    """Handle editing a specific epic item."""
    query = update.callback_query
    user = update.effective_user
    
    with get_session() as session:
        db_user = session.query(User).filter(
            User.telegram_user_id == user.id
        ).first()
        
        if not db_user:
            await query.edit_message_text("❌ User not found")
            return
        
        approval = session.query(ApprovalRequest).filter(
            ApprovalRequest.approval_id == approval_id
        ).first()
        
        if not approval:
            await query.edit_message_text("❌ Approval not found")
            return
        
        request_data = approval.request_data or {}
        epics = request_data.get('epics', [])
        
        if epic_index >= len(epics):
            await query.edit_message_text("❌ Epic not found")
            return
        
        epic = epics[epic_index]
        wsjf = epic.get('wsjf', {})
        
        # Show epic details with edit options
        message = f"✏️ Edit Epic\n\n"
        message += f"Title: {epic.get('title', 'Untitled')}\n"
        message += f"Description: {epic.get('description', 'No description')[:100]}...\n\n"
        message += f"WSJF Breakdown:\n"
        message += f"• Business Value: {wsjf.get('business_value', 0)}/10\n"
        message += f"• Time Criticality: {wsjf.get('time_criticality', 0)}/10\n"
        message += f"• Risk Reduction: {wsjf.get('risk_reduction', 0)}/10\n"
        message += f"• Job Size: {wsjf.get('job_size', 0)}\n"
        message += f"• WSJF Score: {wsjf.get('wsjf_score', 0):.1f}\n\n"
        message += "⚠️ Note: Full editing functionality coming soon.\n"
        message += "For now, you can approve or reject the entire request."
        
        keyboard = [
            [InlineKeyboardButton("« Back to List", callback_data=f"edit_{approval_id}")],
            [InlineKeyboardButton("« Back to Approval", callback_data=f"back_{approval_id}")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            message,
            reply_markup=reply_markup
        )


async def show_story_edit_options(query, approval: ApprovalRequest, context: ContextTypes.DEFAULT_TYPE):
    """Show edit options for story creation."""
    await query.edit_message_text(
        "✏️ Story editing coming soon...\n\n"
        "For now, you can approve or reject."
    )


async def handle_view(query, session, approval: ApprovalRequest):
    """
    Handle view details action.
    
    Shows full approval details.
    """
    request_data = approval.request_data or {}
    
    # Format detailed view based on request type
    if approval.request_type == 'epic_creation':
        message = format_epic_details(approval, request_data)
    elif approval.request_type == 'story_creation':
        message = format_story_details(approval, request_data)
    else:
        message = format_generic_details(approval, request_data)
    
    # Add back button
    keyboard = [[
        InlineKeyboardButton("« Back to Actions", callback_data=f"back_{approval.approval_id}")
    ]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        message,
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )


async def handle_back(query, session, approval: ApprovalRequest):
    """
    Handle back button action.
    
    Returns to the main approval message with action buttons.
    """
    from backend.telegram.handlers.approval_handler import (
        format_epic_approval,
        format_story_approval,
        format_sprint_approval,
        format_generic_approval,
    )
    
    request_data = approval.request_data or {}
    
    # Format message based on request type
    if approval.request_type == 'epic_creation':
        message = format_epic_approval(approval, request_data)
    elif approval.request_type == 'story_creation':
        message = format_story_approval(approval, request_data)
    elif approval.request_type == 'sprint_planning':
        message = format_sprint_approval(approval, request_data)
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
    
    await query.edit_message_text(
        message,
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )


def format_epic_details(approval: ApprovalRequest, data: dict) -> str:
    """Format detailed epic view."""
    epics = data.get('epics', [])
    
    message = f"📋 *Epic Creation Details*\n\n"
    message += f"*Request ID*: #{approval.approval_id}\n"
    message += f"*Count*: {len(epics)} epic(s)\n\n"
    
    for i, epic in enumerate(epics, 1):
        title = epic.get('title', 'Untitled')
        description = epic.get('description', 'No description')[:100]
        wsjf = epic.get('wsjf', {})
        
        message += f"*{i}. {title}*\n"
        message += f"Description: {description}...\n"
        message += f"WSJF Score: {wsjf.get('wsjf_score', 0):.1f}\n"
        message += f"Business Value: {wsjf.get('business_value', 0)}/10\n"
        message += f"Time Criticality: {wsjf.get('time_criticality', 0)}/10\n"
        message += f"\n"
    
    return message


def format_story_details(approval: ApprovalRequest, data: dict) -> str:
    """Format detailed story view."""
    stories = data.get('stories', [])
    
    message = f"📝 *Story Creation Details*\n\n"
    message += f"*Request ID*: #{approval.approval_id}\n"
    message += f"*Count*: {len(stories)} story(ies)\n\n"
    
    for i, story in enumerate(stories[:5], 1):  # Show first 5
        title = story.get('title', 'Untitled')
        description = story.get('description', 'No description')[:80]
        
        message += f"*{i}. {title}*\n"
        message += f"{description}...\n\n"
    
    return message


def format_generic_details(approval: ApprovalRequest, data: dict) -> str:
    """Format generic details view."""
    message = f"📌 *Approval Details*\n\n"
    message += f"*Request ID*: #{approval.approval_id}\n"
    message += f"*Type*: {approval.request_type}\n"
    message += f"*Entity*: {approval.entity_type}\n\n"
    message += f"*Data*:\n```json\n{json.dumps(data, indent=2)[:500]}\n```"
    
    return message


async def execute_approval(approval: ApprovalRequest):
    """
    Execute approved request.
    
    Creates items in Jira based on approval type.
    
    Returns:
        List of created Jira keys
    """
    if approval.request_type == 'epic_creation':
        return await execute_epic_creation(approval)
    elif approval.request_type == 'story_creation':
        return await execute_story_creation(approval)
    elif approval.request_type == 'sprint_planning':
        return await execute_sprint_planning(approval)
    elif approval.request_type == 'standup_update':
        return await execute_standup_update(approval)
    else:
        logger.warning(f"Unknown approval type: {approval.request_type}")
        return []


async def execute_epic_creation(approval: ApprovalRequest):
    """
    Execute Jira creation using JiraCreatorAgent.
    
    This is called when PM approves the decomposed backlog.
    It uses the existing JiraCreatorAgent to create the complete hierarchy.
    
    The decomposition was already done by the pipeline, so we just need
    to create everything in Jira using the decomposed data.
    
    CRITICAL: After creating in Jira, we MUST update the database so that
    natural language extraction can work in sprint planning and standup.
    """
    from backend.agents.jira_creator import JiraCreatorAgent
    from backend.db.connection import get_session
    from backend.db import crud
    from backend.db.models import Meeting, ProcessingRun, Epic, Story, BacklogTask
    from datetime import datetime, timezone
    import json
    
    # Use approved_data (which may have been edited)
    data = approval.approved_data or approval.request_data
    
    # Get the decomposition file path
    decomposition_file = data.get('decomposition_file')
    
    if not decomposition_file:
        raise Exception("No decomposition file found in approval data")
    
    logger.info(f"Creating Jira hierarchy from decomposition file: {decomposition_file}")
    
    # Use JiraCreatorAgent to create everything in Jira
    agent = JiraCreatorAgent()
    
    try:
        # Create backlog in Jira using the decomposed data
        result = agent.create_backlog_in_jira(
            backlog_path=decomposition_file,
            dry_run=False,
            resume=True  # Enable idempotency
        )
        
        logger.info(f"Jira creation complete:")
        logger.info(f"  Epics created: {result.epics_created}/{result.total_epics}")
        logger.info(f"  Stories created: {result.stories_created}/{result.total_stories}")
        logger.info(f"  Tasks created: {result.tasks_created}/{result.total_tasks}")
        
        # ═══════════════════════════════════════════════════════════════════
        # CRITICAL: Update database with created tickets
        # ═══════════════════════════════════════════════════════════════════
        logger.info("Updating database with created Jira tickets...")
        
        # Load the decomposed backlog to get full details
        with open(decomposition_file, 'r') as f:
            decomposed_data = json.load(f)
        
        with get_session() as session:
            # Get or create meeting and processing run
            meeting = session.query(Meeting).filter(
                Meeting.meeting_type == 'pm',
                Meeting.title.like('%Backlog%')
            ).order_by(Meeting.created_at.desc()).first()
            
            if not meeting:
                # Create a meeting record for this backlog
                from backend.db.models import MeetingType
                meeting = Meeting(
                    meeting_type=MeetingType.PM,
                    title='Backlog Pipeline - Telegram Approval',
                    meeting_date=datetime.now(timezone.utc).date(),
                    source_platform='telegram',
                    status='completed',
                    created_at=datetime.now(timezone.utc)
                )
                session.add(meeting)
                session.flush()
            
            # Get or create processing run
            from backend.db.models import RunType, RunStatus
            processing_run = session.query(ProcessingRun).filter(
                ProcessingRun.meeting_id == meeting.id,
                ProcessingRun.run_type == RunType.PM_BACKLOG
            ).order_by(ProcessingRun.created_at.desc()).first()
            
            if not processing_run:
                # Get the next run number
                max_run = session.query(ProcessingRun).filter(
                    ProcessingRun.meeting_id == meeting.id
                ).order_by(ProcessingRun.run_number.desc()).first()
                next_run_number = (max_run.run_number + 1) if max_run else 1
                
                processing_run = ProcessingRun(
                    meeting_id=meeting.id,
                    run_number=next_run_number,
                    run_type=RunType.PM_BACKLOG,
                    status=RunStatus.COMPLETED,
                    started_at=datetime.now(timezone.utc),
                    finished_at=datetime.now(timezone.utc),
                    created_at=datetime.now(timezone.utc)
                )
                session.add(processing_run)
                session.flush()
            
            # Process each epic from the result
            epics_created = 0
            stories_created = 0
            tasks_created = 0
            
            for jira_epic in result.epics:
                if not jira_epic.success or not jira_epic.jira_key:
                    continue
                
                # Find the epic data from decomposed file
                epic_data = next(
                    (e for e in decomposed_data['epics'] if e['epic_id'] == jira_epic.epic_id),
                    None
                )
                if not epic_data:
                    logger.warning(f"Epic {jira_epic.epic_id} not found in decomposed data")
                    continue
                
                # Check if epic already exists in database
                existing_epic = session.query(Epic).filter(
                    Epic.jira_key == jira_epic.jira_key
                ).first()
                
                if existing_epic:
                    logger.info(f"Epic {jira_epic.jira_key} already exists in database, skipping")
                    db_epic = existing_epic
                    epics_created += 1
                else:
                    # Create Epic in database
                    db_epic = crud.create_epic(
                        session=session,
                        meeting_id=meeting.id,
                        processing_run_id=processing_run.id,
                        title=jira_epic.title,
                        description=epic_data.get('description', ''),
                        business_value=epic_data.get('business_value', 5),  # Default to 5 if missing
                        time_criticality=epic_data.get('time_criticality', 5),  # Default to 5 if missing
                        risk_reduction=epic_data.get('risk_reduction', 5),  # Default to 5 if missing
                        job_size=epic_data.get('job_size', 5),  # Default to 5 if missing
                        wsjf_score=jira_epic.wsjf_score,
                        priority_rank=jira_epic.priority_rank,
                    )
                    
                    # Update with Jira key
                    crud.update_epic_jira_info(
                        session=session,
                        epic_id=db_epic.id,
                        jira_key=jira_epic.jira_key,
                        jira_status='To Do',
                        jira_synced_at=datetime.now(timezone.utc)
                    )
                    epics_created += 1
                
                # Process stories
                for jira_story in jira_epic.stories:
                    if not jira_story.success or not jira_story.jira_key:
                        continue
                    
                    # Find story data from decomposed file
                    story_data = next(
                        (s for s in epic_data['stories'] if s['story_id'] == jira_story.story_id),
                        None
                    )
                    if not story_data:
                        logger.warning(f"Story {jira_story.story_id} not found in decomposed data")
                        continue
                    
                    # Check if story already exists in database
                    existing_story = session.query(Story).filter(
                        Story.jira_key == jira_story.jira_key
                    ).first()
                    
                    if existing_story:
                        logger.info(f"Story {jira_story.jira_key} already exists in database, skipping")
                        db_story = existing_story
                        stories_created += 1
                    else:
                        # Create Story in database
                        db_story = crud.create_story(
                            session=session,
                            epic_id=db_epic.id,
                            meeting_id=meeting.id,
                            processing_run_id=processing_run.id,
                            title=jira_story.title,
                            description=story_data.get('description', ''),
                            acceptance_criteria=story_data.get('acceptance_criteria', []),
                        )
                        
                        # Update with Jira key
                        crud.update_story_jira_info(
                            session=session,
                            story_id=db_story.id,
                            jira_key=jira_story.jira_key,
                            jira_status='To Do',
                            jira_synced_at=datetime.now(timezone.utc)
                        )
                        stories_created += 1
                    
                    # Process tasks
                    for jira_task in jira_story.tasks:
                        if not jira_task.success or not jira_task.jira_key:
                            continue
                        
                        # Find task data from decomposed file
                        task_data = next(
                            (t for t in story_data['tasks'] if t['task_id'] == jira_task.task_id),
                            None
                        )
                        if not task_data:
                            logger.warning(f"Task {jira_task.task_id} not found in decomposed data")
                            continue
                        
                        # Check if task already exists in database
                        existing_task = session.query(BacklogTask).filter(
                            BacklogTask.jira_key == jira_task.jira_key
                        ).first()
                        
                        if existing_task:
                            logger.info(f"Task {jira_task.jira_key} already exists in database, skipping")
                            tasks_created += 1
                        else:
                            # Create Task in database
                            db_task = crud.create_backlog_task(
                                session=session,
                                story_id=db_story.id,
                                meeting_id=meeting.id,
                                processing_run_id=processing_run.id,
                                title=jira_task.title,
                                description=task_data.get('description', ''),
                                estimated_hours=jira_task.estimated_hours,
                            )
                            
                            # Update with Jira key
                            crud.update_task_jira_info(
                                session=session,
                                task_id=db_task.id,
                                jira_key=jira_task.jira_key,
                                jira_status='To Do',
                                jira_synced_at=datetime.now(timezone.utc)
                            )
                            tasks_created += 1
            
            session.commit()
            
            logger.info(f"✅ Database updated:")
            logger.info(f"  Epics: {epics_created}")
            logger.info(f"  Stories: {stories_created}")
            logger.info(f"  Tasks: {tasks_created}")
        
        # Collect all created Jira keys from the result
        created_keys = []
        
        # Get keys from id_mapping (this has all created items)
        for internal_id, jira_key in result.id_mapping.items():
            if jira_key:  # Only add if Jira key exists
                created_keys.append(jira_key)
        
        if result.errors:
            # Some items failed but continue
            error_summary = "\n".join(f"• {err[:80]}" for err in result.errors[:3])
            if len(result.errors) > 3:
                error_summary += f"\n• ... and {len(result.errors) - 3} more"
            logger.warning(f"Jira creation completed with errors:\n{error_summary}")
        
        logger.info(f"✅ Successfully created {len(created_keys)} items in Jira and updated database")
        return created_keys
    
    except Exception as e:
        logger.error(f"Failed to create Jira hierarchy: {e}", exc_info=True)
        raise Exception(f"Failed to create Jira hierarchy: {str(e)}")


async def execute_story_creation(approval: ApprovalRequest):
    """Execute story creation in Jira."""
    from backend.tools.jira_client import JiraManager
    from backend.db.connection import get_session
    from backend.db import crud
    from backend.db.models import Meeting, ProcessingRun
    from datetime import datetime, timezone
    
    data = approval.approved_data or approval.request_data
    stories_data = data.get('stories', [])
    
    logger.info(f"Creating {len(stories_data)} story(ies) in Jira")
    
    jira = JiraManager()
    created_keys = []
    errors = []
    
    # Get or create meeting and processing run
    with get_session() as session:
        meeting = session.query(Meeting).filter(
            Meeting.meeting_type == 'pm',
            Meeting.title == 'Telegram Bot Approval'
        ).first()
        
        if not meeting:
            meeting = Meeting(
                meeting_type='pm',
                meeting_date=datetime.now(timezone.utc),
                title='Telegram Bot Approval',
                source_platform='telegram',
                status='completed'
            )
            session.add(meeting)
            session.flush()
            
            processing_run = ProcessingRun(
                meeting_id=meeting.id,
                run_number=1,
                run_type='pm_backlog',
                status='completed'
            )
            session.add(processing_run)
            session.commit()
            session.refresh(meeting)
            session.refresh(processing_run)
        else:
            processing_run = session.query(ProcessingRun).filter(
                ProcessingRun.meeting_id == meeting.id
            ).first()
        
        meeting_id = meeting.id
        processing_run_id = processing_run.id
    
    # Create each story
    for idx, story_data in enumerate(stories_data, 1):
        try:
            title = story_data.get('title', 'Untitled Story')
            description_text = story_data.get('description', '')
            epic_key = story_data.get('epic_key')  # Parent epic
            story_points = story_data.get('story_points', 0)
            acceptance_criteria = story_data.get('acceptance_criteria', [])
            
            # Build story description
            story_description = f"""**Description**:
{description_text}

**Acceptance Criteria**:
"""
            for i, criterion in enumerate(acceptance_criteria, 1):
                story_description += f"{i}. {criterion}\n"
            
            if story_points:
                story_description += f"\n**Story Points**: {story_points}\n"
            
            story_description += f"""
---
*Created by ScrumPilot via Telegram Approval*
*Approval ID*: #{approval.approval_id}
"""
            
            # Create story in Jira
            logger.info(f"Creating story in Jira: {title}")
            result = jira.create_ticket(
                summary=title,
                description=story_description,
                issue_type="Story",
                epic_link=epic_key
            )
            
            if result.get('success'):
                jira_key = result.get('key')
                created_keys.append(jira_key)
                logger.info(f"Created story in Jira: {jira_key}")
                
                # Save to database
                with get_session() as session:
                    # Get epic_id if epic_key provided
                    epic_id = None
                    if epic_key:
                        from backend.db.models import Epic
                        epic = session.query(Epic).filter(Epic.jira_key == epic_key).first()
                        if epic:
                            epic_id = epic.id
                    
                    db_story = crud.create_story(
                        session=session,
                        epic_id=epic_id or meeting_id,  # Fallback to meeting_id
                        meeting_id=meeting_id,
                        processing_run_id=processing_run_id,
                        title=title,
                        description=description_text,
                        acceptance_criteria=acceptance_criteria,
                        sequence_no=idx,
                    )
                    
                    crud.update_story_jira_info(
                        session=session,
                        story_id=db_story.id,
                        jira_key=jira_key,
                        jira_status='To Do',
                        jira_synced_at=datetime.now(timezone.utc),
                    )
                    
                    session.commit()
                    logger.info(f"Saved story to database: Story #{db_story.id} -> {jira_key}")
            else:
                error_msg = result.get('error', 'Unknown error')
                errors.append(f"{title}: {error_msg}")
                logger.error(f"Failed to create story '{title}': {error_msg}")
        
        except Exception as e:
            error_msg = str(e)
            errors.append(f"{story_data.get('title', 'Unknown')}: {error_msg}")
            logger.error(f"Exception creating story: {e}", exc_info=True)
    
    if errors:
        error_summary = "\n".join(f"• {err[:80]}" for err in errors[:2])
        if len(errors) > 2:
            error_summary += f"\n• ... and {len(errors) - 2} more"
        raise Exception(f"Failed to create stories:\n{error_summary}")
    
    return created_keys


async def execute_sprint_planning(approval: ApprovalRequest):
    """
    Execute sprint planning in Jira.
    
    This is called when PM approves the sprint plan.
    It creates the sprint, moves stories, and assigns developers.
    
    The sprint plan was already extracted by the pipeline, so we just need
    to create everything in Jira using the sprint plan data.
    """
    from backend.pipelines.sprint_planning_pipeline import SprintPlanningPipeline
    import json
    from pathlib import Path
    
    # Use approved_data (which may have been edited)
    data = approval.approved_data or approval.request_data
    
    # Get the sprint plan file path
    sprint_plan_file = data.get('sprint_plan_file')
    
    if not sprint_plan_file:
        raise Exception("No sprint plan file found in approval data")
    
    logger.info(f"Creating sprint in Jira from plan file: {sprint_plan_file}")
    
    # Load sprint plan
    if not Path(sprint_plan_file).exists():
        raise Exception(f"Sprint plan file not found: {sprint_plan_file}")
    
    with open(sprint_plan_file, 'r', encoding='utf-8') as f:
        sprint_plan_data = json.load(f)
    
    # Use the pipeline's Jira creation method
    pipeline = SprintPlanningPipeline(require_telegram_approval=False)
    
    try:
        # Import the sprint planning result model
        from backend.agents.sprint_planning_extractor import SprintPlanningResult
        
        # Reconstruct the sprint plan object
        sprint_plan = SprintPlanningResult(**sprint_plan_data)
        
        # Create sprint in Jira
        jira_result = pipeline._create_sprint_in_jira(sprint_plan)
        
        logger.info(f"Sprint creation complete:")
        logger.info(f"  Sprint: {jira_result.get('sprint_name')}")
        logger.info(f"  Stories moved: {jira_result.get('stories_moved', 0)}")
        logger.info(f"  Tasks assigned: {jira_result.get('tasks_assigned', 0)}")
        logger.info(f"  Developers: {jira_result.get('developers_assigned', 0)}")
        
        # Collect created/updated Jira keys
        created_keys = []
        
        # Add sprint key
        if jira_result.get('sprint_key'):
            created_keys.append(jira_result['sprint_key'])
        
        # Add story keys
        for story_id in sprint_plan.commitment.story_ids:
            created_keys.append(story_id)
        
        if jira_result.get('errors'):
            # Some items failed but continue
            error_summary = "\n".join(f"• {err[:80]}" for err in jira_result['errors'][:3])
            if len(jira_result['errors']) > 3:
                error_summary += f"\n• ... and {len(jira_result['errors']) - 3} more"
            logger.warning(f"Sprint creation completed with errors:\n{error_summary}")
        
        logger.info(f"✅ Successfully created sprint with {len(created_keys)} items")
        return created_keys
    
    except Exception as e:
        logger.error(f"Failed to create sprint: {e}", exc_info=True)
        raise Exception(f"Failed to create sprint: {str(e)}")
    story_ids = data.get('story_ids', [])
    start_date = data.get('start_date')
    end_date = data.get('end_date')
    
    logger.info(f"Creating sprint: {sprint_name}")
    
    jira = JiraManager()
    
    # Calculate dates if not provided
    if not start_date:
        start_date = datetime.now().strftime('%Y-%m-%d')
    if not end_date:
        start = datetime.strptime(start_date, '%Y-%m-%d')
        end = start + timedelta(weeks=2)
        end_date = end.strftime('%Y-%m-%d')
    
    # Create sprint
    result = jira.create_sprint(
        name=sprint_name,
        goal=sprint_goal,
        start_date=start_date,
        end_date=end_date
    )
    
    if not result.get('success'):
        raise Exception(f"Failed to create sprint: {result.get('error')}")
    
    sprint_id = result.get('id')
    sprint_key = result.get('key')
    
    logger.info(f"Created sprint: {sprint_key}")
    
    # Move stories to sprint
    if story_ids:
        move_result = jira.move_issues_to_sprint(story_ids, sprint_id)
        logger.info(f"Moved {move_result.get('moved', 0)} stories to sprint")
    
    return [sprint_key]



async def execute_standup_update(approval: ApprovalRequest):
    """
    Execute standup updates in Jira AND synchronize database.
    
    This is called when Scrum Master approves the standup actions.
    It updates Jira tickets AND updates the database to keep them in sync.
    
    NEW: Now includes database synchronization!
    """
    from backend.agents.jira_agent import JiraAgent
    from backend.db.connection import get_session
    from backend.db.models import Story, BacklogTask
    from datetime import datetime, timezone
    import json
    from pathlib import Path
    import re
    
    # Use approved_data (which may have been edited)
    data = approval.approved_data or approval.request_data
    
    # Get the actions file path
    actions_file = data.get('actions_file')
    
    if not actions_file:
        # Try to get actions directly from data
        actions = data.get('actions', [])
        if not actions:
            raise Exception("No actions found in approval data")
    else:
        # Load actions from file
        if not Path(actions_file).exists():
            raise Exception(f"Actions file not found: {actions_file}")
        
        with open(actions_file, 'r', encoding='utf-8') as f:
            actions = json.load(f)
    
    logger.info(f"Updating Jira tickets from {len(actions)} standup actions")
    
    # Use JiraAgent to execute actions
    jira_agent = JiraAgent()
    
    try:
        # Execute all actions in Jira
        report = jira_agent.execute_actions(actions)
        
        logger.info(f"Standup updates complete in Jira")
        logger.info(f"Report: {report[:200]}...")  # Log first 200 chars
        
        # NEW: Synchronize database with Jira updates
        logger.info("Synchronizing database with Jira updates...")
        
        db_updates = 0
        db_errors = 0
        affected_keys = []
        
        with get_session() as session:
            for action in actions:
                try:
                    action_type = action.get('action')
                    summary = action.get('summary', '')
                    
                    # Extract ticket key from summary (e.g., "SP-189")
                    match = re.search(r'(SP-\d+)', summary)
                    if not match:
                        logger.warning(f"No ticket key found in action: {summary}")
                        continue
                    
                    jira_key = match.group(1)
                    affected_keys.append(jira_key)
                    
                    # Find the story or task in database
                    story = session.query(Story).filter(
                        Story.jira_key == jira_key
                    ).first()
                    
                    task = None
                    if not story:
                        task = session.query(BacklogTask).filter(
                            BacklogTask.jira_key == jira_key
                        ).first()
                    
                    if not story and not task:
                        logger.warning(f"Ticket {jira_key} not found in database (may be created manually in Jira)")
                        continue
                    
                    # Update based on action type
                    if action_type == 'complete_task':
                        if story:
                            story.jira_status = 'Done'
                            story.jira_synced_at = datetime.now(timezone.utc)
                            logger.info(f"Updated story {jira_key} status to Done in database")
                        if task:
                            task.jira_status = 'Done'
                            task.jira_synced_at = datetime.now(timezone.utc)
                            logger.info(f"Updated task {jira_key} status to Done in database")
                        db_updates += 1
                    
                    elif action_type == 'update_status':
                        new_status = action.get('new_status', 'In Progress')
                        if story:
                            story.jira_status = new_status
                            story.jira_synced_at = datetime.now(timezone.utc)
                            logger.info(f"Updated story {jira_key} status to {new_status} in database")
                        if task:
                            task.jira_status = new_status
                            task.jira_synced_at = datetime.now(timezone.utc)
                            logger.info(f"Updated task {jira_key} status to {new_status} in database")
                        db_updates += 1
                    
                    elif action_type == 'assign_task':
                        assignee = action.get('assignee')
                        if assignee:
                            if story:
                                story.assigned_to = assignee
                                story.jira_synced_at = datetime.now(timezone.utc)
                                logger.info(f"Updated story {jira_key} assignee to {assignee} in database")
                            if task:
                                task.assigned_to = assignee
                                task.jira_synced_at = datetime.now(timezone.utc)
                                logger.info(f"Updated task {jira_key} assignee to {assignee} in database")
                            db_updates += 1
                    
                    elif action_type == 'add_comment':
                        # Comments are tracked in Jira, no database update needed
                        logger.debug(f"Comment added to {jira_key} (tracked in Jira only)")
                    
                    else:
                        logger.warning(f"Unknown action type: {action_type}")
                
                except Exception as e:
                    logger.error(f"Failed to update database for action {action}: {e}")
                    db_errors += 1
                    # Continue with other actions
            
            # Commit all database updates
            session.commit()
            logger.info(f"✅ Database synchronized: {db_updates} updates, {db_errors} errors")
        
        logger.info(f"✅ Successfully updated {len(affected_keys)} tickets in Jira and database")
        return affected_keys
    
    except Exception as e:
        logger.error(f"Failed to update Jira tickets: {e}", exc_info=True)
        raise Exception(f"Failed to update Jira tickets: {str(e)}")
