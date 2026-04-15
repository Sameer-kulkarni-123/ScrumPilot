"""
Scrum Pipeline - Phase 3 (Production Ready)

Orchestrates the daily standup workflow:
1. Extract actions from standup transcript
2. Create approval request
3. Send Telegram notification
4. Pause for Scrum Master approval
5. Update Jira tickets
6. Synchronize database

This automates the daily standup → Jira update workflow.

Author: AI Meeting Automation System
Phase: 3
"""

import json
import os
import sys
import logging
from pathlib import Path
from typing import Optional, Dict, Any, List
from datetime import datetime
from pydantic import BaseModel, Field

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from backend.agents.scrum_extractor import ScrumExtractorAgent
from backend.agents.jira_agent import JiraAgent

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


# ============================================================================
# PIPELINE MODELS
# ============================================================================

class ScrumPipelineResult(BaseModel):
    """Complete pipeline execution result."""
    pipeline_id: str
    start_time: str
    end_time: Optional[str] = None
    status: str  # 'completed', 'failed', 'paused'
    current_phase: str = 'initialization'
    
    # Input
    transcript_path: str
    
    # Extraction result
    actions: Optional[List[Dict]] = None
    extraction_file: Optional[str] = None
    
    # Jira execution result
    jira_report: Optional[str] = None
    
    # Summary
    total_actions: int = 0
    tasks_completed: int = 0
    tasks_updated: int = 0
    
    # Approval
    approval_id: Optional[int] = None
    
    # Errors
    errors: List[str] = Field(default_factory=list)


# ============================================================================
# SCRUM PIPELINE
# ============================================================================

class ScrumPipeline:
    """
    Orchestrates complete daily standup workflow.
    
    Workflow:
    1. Extract actions from transcript
    2. Create approval request
    3. Send Telegram notification
    4. Pause for approval
    5. Update Jira tickets
    6. Synchronize database
    
    Example usage:
        pipeline = ScrumPipeline()
        result = pipeline.run(
            transcript_path="standup_transcript.txt",
            update_jira=True
        )
    """
    
    def __init__(self, require_telegram_approval: bool = True):
        """
        Initialize the Scrum Pipeline.
        
        Args:
            require_telegram_approval: If True, pause for Scrum Master approval
        """
        self.extractor = ScrumExtractorAgent()
        self.jira_agent = None  # Lazy load
        self.require_telegram_approval = require_telegram_approval
        logger.info(f"ScrumPipeline initialized (approval={require_telegram_approval})")
    
    def run(
        self,
        transcript_path: str,
        update_jira: bool = True,
        dry_run: bool = False
    ) -> ScrumPipelineResult:
        """
        Run complete scrum pipeline.
        
        Args:
            transcript_path: Path to standup meeting transcript
            update_jira: Whether to update tickets in Jira
            dry_run: If True, simulate without actual Jira updates
        
        Returns:
            ScrumPipelineResult
        """
        pipeline_id = datetime.now().strftime('%Y%m%d_%H%M%S')
        
        result = ScrumPipelineResult(
            pipeline_id=pipeline_id,
            start_time=datetime.now().isoformat(),
            status='in_progress',
            transcript_path=transcript_path
        )
        
        print("\n" + "=" * 70)
        print("SCRUM PIPELINE - Phase 3 (Production Ready)")
        print("=" * 70)
        print(f"Pipeline ID: {pipeline_id}")
        print(f"Transcript: {transcript_path}")
        print(f"Update Jira: {update_jira}")
        print(f"Dry Run: {dry_run}")
        print("=" * 70 + "\n")
        
        try:
            # Phase 1: Extract actions
            print("Phase 1: Extracting actions from standup transcript...")
            actions = self._extract_actions(transcript_path)
            
            result.actions = actions
            result.total_actions = len(actions)
            
            # Count action types
            result.tasks_completed = sum(1 for a in actions if a.get('action') == 'complete_task')
            result.tasks_updated = sum(1 for a in actions if a.get('action') in ['update_status', 'assign_task'])
            
            # Save extraction result
            date_str = datetime.now().strftime('%Y-%m-%d')
            extraction_file = f"backend/data/scrum_meetings/{date_str}_actions.json"
            Path(extraction_file).parent.mkdir(parents=True, exist_ok=True)
            with open(extraction_file, 'w', encoding='utf-8') as f:
                json.dump(actions, f, indent=2, ensure_ascii=False)
            result.extraction_file = extraction_file
            
            print(f"  Total Actions: {len(actions)}")
            print(f"  Tasks Completed: {result.tasks_completed}")
            print(f"  Tasks Updated: {result.tasks_updated}")
            
            # Phase 2: Create approval request if required
            if self.require_telegram_approval and update_jira:
                print("\nPhase 2: Creating approval request...")
                approval_id = self._create_telegram_approval_for_standup(
                    actions=actions,
                    extraction_file=extraction_file
                )
                result.approval_id = approval_id
                result.status = 'paused'
                result.current_phase = 'action_extraction'
                result.end_time = datetime.now().isoformat()
                
                print("\n" + "=" * 70)
                print("✅ APPROVAL REQUEST CREATED")
                print("=" * 70)
                print(f"Approval ID: #{approval_id}")
                print(f"📱 Telegram notification sent to Scrum Master")
                print(f"⏸️  Pipeline paused. Waiting for approval...")
                print()
                print(f"The Scrum Master will receive a Telegram notification to review:")
                print(f"  - Total Actions: {len(actions)}")
                print(f"  - Tasks Completed: {result.tasks_completed}")
                print(f"  - Tasks Updated: {result.tasks_updated}")
                print()
                print(f"After approval, the system will automatically:")
                print(f"  1. Update Jira tickets")
                print(f"  2. Synchronize database")
                print("=" * 70 + "\n")
                
                return result
            
            # Phase 3: Update Jira (if no approval required)
            if update_jira:
                print("\nPhase 2: Updating Jira tickets...")
                
                if dry_run:
                    print("  DRY RUN MODE - Simulating Jira updates")
                    jira_report = self._simulate_jira_updates(actions)
                else:
                    jira_report = self._update_jira_tickets(actions)
                
                result.jira_report = jira_report
                
                print(f"  Jira updates complete")
            else:
                print("\nSkipping Jira updates (update_jira=False)")
            
            # Mark as complete
            result.status = 'completed'
            result.end_time = datetime.now().isoformat()
            
            print("\n" + "=" * 70)
            print("SCRUM PIPELINE COMPLETE")
            print("=" * 70)
            print(f"Total Actions: {result.total_actions}")
            print(f"Tasks Completed: {result.tasks_completed}")
            print(f"Tasks Updated: {result.tasks_updated}")
            print("=" * 70 + "\n")
            
            return result
        
        except Exception as e:
            logger.error(f"Pipeline failed: {e}")
            result.status = 'failed'
            result.errors.append(str(e))
            result.end_time = datetime.now().isoformat()
            
            print(f"\nPipeline failed: {e}")
            raise
    
    def _extract_actions(self, transcript_path: str) -> List[Dict]:
        """Extract actions from transcript with active sprint context."""
        with open(transcript_path, 'r', encoding='utf-8') as f:
            transcript = f.read()
        
        # Load active sprint context from database
        context = self._load_active_sprint_context()
        
        return self.extractor.extract_actions(transcript, context)
    
    def _load_active_sprint_context(self) -> Dict[str, Any]:
        """
        Load active sprint stories and tasks from database.
        
        Returns:
            Dict with active_stories and active_tasks
        """
        from backend.db.connection import get_session
        from backend.db.models import Story, BacklogTask, Sprint, SprintStory
        
        logger.info("Loading active sprint context from database")
        
        try:
            with get_session() as session:
                # Get active sprint
                active_sprint = session.query(Sprint).filter(
                    Sprint.status == 'active'
                ).first()
                
                if not active_sprint:
                    logger.warning("No active sprint found")
                    return {"active_stories": [], "active_tasks": []}
                
                logger.info(f"Found active sprint: {active_sprint.name}")
                
                # Get stories in active sprint through sprint_stories table
                sprint_story_ids = session.query(SprintStory.story_id).filter(
                    SprintStory.sprint_id == active_sprint.sprint_id
                ).all()
                
                story_ids = [ss[0] for ss in sprint_story_ids]
                
                stories = session.query(Story).filter(
                    Story.id.in_(story_ids)
                ).all() if story_ids else []
                
                logger.info(f"Found {len(stories)} stories in active sprint")
                
                # Get tasks for these stories
                tasks = session.query(BacklogTask).filter(
                    BacklogTask.story_id.in_(story_ids)
                ).all() if story_ids else []
                
                logger.info(f"Found {len(tasks)} tasks in active sprint")
                
                # Format stories
                active_stories = []
                for story in stories:
                    active_stories.append({
                        'story_id': story.jira_key,
                        'title': story.title,
                        'description': story.description,
                        'assigned_to': None,  # Story model doesn't have assigned_to
                        'status': story.jira_status
                    })
                
                # Format tasks
                active_tasks = []
                for task in tasks:
                    active_tasks.append({
                        'task_id': task.jira_key,
                        'title': task.title,
                        'description': task.description,
                        'story_id': task.story.jira_key if task.story else None,
                        'assigned_to': task.assigned_to,
                        'status': task.jira_status
                    })
                
                return {
                    'active_stories': active_stories,
                    'active_tasks': active_tasks
                }
        
        except Exception as e:
            logger.error(f"Failed to load active sprint context: {e}")
            return {"active_stories": [], "active_tasks": []}
    
    def _create_telegram_approval_for_standup(
        self,
        actions: List[Dict],
        extraction_file: str
    ) -> int:
        """
        Create Telegram approval request for standup actions.
        
        Args:
            actions: List of extracted actions
            extraction_file: Path to actions JSON file
        
        Returns:
            approval_id: ID of created approval request
        """
        from backend.telegram.services.approval_service import approval_service
        
        logger.info("Creating Telegram approval request for standup actions")
        
        # Count action types
        action_counts = {}
        for action in actions:
            action_type = action.get('action', 'unknown')
            action_counts[action_type] = action_counts.get(action_type, 0) + 1
        
        logger.info(f"Actions: {action_counts}")
        
        # Get Scrum Master user for approval assignment
        sm_user_id = approval_service.get_pm_user_id()  # Reuse PM role for now
        if not sm_user_id:
            raise Exception(
                "No Scrum Master user found for approval. "
                "Please ensure a user with 'product_owner' role exists and has Telegram linked."
            )
        
        logger.info(f"Assigning approval to Scrum Master user ID: {sm_user_id}")
        
        # Get system/bot user (requester)
        system_user_id = 1  # Bot user ID
        
        # Create approval request with standup data
        approval_data = {
            'actions_file': extraction_file,
            'actions': actions,
            'summary': {
                'total_actions': len(actions),
                'action_counts': action_counts
            }
        }
        
        # Create standup approval (we'll add this method to approval_service)
        approval_id = self._create_standup_approval(
            standup_data=approval_data,
            requested_by_user_id=system_user_id,
            assigned_to_user_id=sm_user_id,
            priority='normal'
        )
        
        logger.info(f"Created approval request #{approval_id}")
        
        # Log summary
        print(f"\nStandup actions submitted for approval:")
        print(f"  Total Actions: {len(actions)}")
        for action_type, count in action_counts.items():
            print(f"  {action_type}: {count}")
        print()
        print(f"Sample actions:")
        for i, action in enumerate(actions[:3], 1):
            print(f"  {i}. [{action.get('action')}] {action.get('summary', 'N/A')}")
        
        if len(actions) > 3:
            print(f"  ... and {len(actions) - 3} more")
        
        return approval_id
    
    def _create_standup_approval(
        self,
        standup_data: Dict[str, Any],
        requested_by_user_id: int,
        assigned_to_user_id: int,
        priority: str = 'normal'
    ) -> int:
        """Create standup approval request."""
        from backend.db.connection import get_session
        from backend.db.models import ApprovalRequest
        from datetime import timezone, timedelta
        
        with get_session() as session:
            approval = ApprovalRequest(
                request_type='standup_update',
                entity_type='task',
                entity_id=0,
                requested_by=requested_by_user_id,
                assigned_to=assigned_to_user_id,
                status='pending',
                priority=priority,
                request_data=standup_data,
                original_data=standup_data,
                created_at=datetime.now(timezone.utc),
                expires_at=datetime.now(timezone.utc) + timedelta(hours=24)
            )
            
            session.add(approval)
            session.commit()
            session.refresh(approval)
            
            approval_id = approval.approval_id
            
            logger.info(f"Created standup approval request #{approval_id}")
            
            # Send Telegram notification
            from backend.db.models import User
            assigned_user = session.query(User).filter(
                User.id == assigned_to_user_id
            ).first()
            
            if assigned_user and assigned_user.telegram_user_id:
                self._send_telegram_notification(
                    telegram_user_id=assigned_user.telegram_user_id,
                    telegram_chat_id=assigned_user.telegram_chat_id,
                    approval_id=approval_id
                )
            
            return approval_id
    
    def _send_telegram_notification(
        self,
        telegram_user_id: int,
        telegram_chat_id: int,
        approval_id: int
    ):
        """Send Telegram notification for approval request."""
        import asyncio
        from backend.telegram.handlers.approval_handler import send_approval_notification
        
        try:
            # Check if there's already a running event loop
            try:
                loop = asyncio.get_running_loop()
                # We're inside an async context, create a task
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor() as executor:
                    future = executor.submit(
                        asyncio.run,
                        send_approval_notification(telegram_user_id, telegram_chat_id, approval_id)
                    )
                    future.result(timeout=10)  # Wait up to 10 seconds
                logger.info(f"Sent Telegram notification for approval #{approval_id}")
            except RuntimeError:
                # No running loop, we can use asyncio.run()
                asyncio.run(
                    send_approval_notification(telegram_user_id, telegram_chat_id, approval_id)
                )
                logger.info(f"Sent Telegram notification for approval #{approval_id}")
        except Exception as e:
            logger.error(f"Failed to send Telegram notification: {e}")
            # Don't fail the pipeline if notification fails
            logger.warning("Pipeline will continue, but manual notification may be needed")
    
    def _update_jira_tickets(self, actions: List[Dict]) -> str:
        """Update Jira tickets based on actions."""
        if not self.jira_agent:
            self.jira_agent = JiraAgent()
        
        return self.jira_agent.execute_actions(actions)
    
    def _simulate_jira_updates(self, actions: List[Dict]) -> str:
        """Simulate Jira updates for dry run mode."""
        report = "DRY RUN - Simulated Jira Updates:\n\n"
        for i, action in enumerate(actions, 1):
            report += f"{i}. [{action.get('action')}] {action.get('summary', 'N/A')}\n"
        return report


# ============================================================================
# CONVENIENCE FUNCTIONS
# ============================================================================

def run_scrum_pipeline(transcript: str, dry_run: bool = False, require_approval: bool = True) -> dict:
    """
    Full pipeline: transcript → extract actions → execute on Jira.
    
    Args:
        transcript: The diarized meeting transcript text.
        dry_run: If True, only extract actions without executing them on Jira.
        require_approval: If True, pause for Telegram approval.
    
    Returns:
        dict with keys: actions (list), report (str | None)
    """
    pipeline = ScrumPipeline(require_telegram_approval=require_approval)
    
    # Save transcript to temp file
    temp_file = f"backend/data/scrum_meetings/temp_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
    Path(temp_file).parent.mkdir(parents=True, exist_ok=True)
    with open(temp_file, 'w', encoding='utf-8') as f:
        f.write(transcript)
    
    result = pipeline.run(
        transcript_path=temp_file,
        update_jira=not dry_run,
        dry_run=dry_run
    )
    
    return {
        "actions": result.actions,
        "report": result.jira_report,
        "approval_id": result.approval_id,
        "status": result.status
    }


def run_from_transcript_file(path: str, dry_run: bool = False, require_approval: bool = True) -> dict:
    """Convenience: read a transcript file and run the pipeline."""
    with open(path, "r", encoding="utf-8") as f:
        transcript = f.read()
    return run_scrum_pipeline(transcript, dry_run=dry_run, require_approval=require_approval)


# ============================================================================
# MAIN EXECUTION
# ============================================================================

if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv()

    # Default to the example transcript for quick testing
    here = os.path.dirname(__file__)
    default_path = os.path.join(here, "..", "data", "scrum_meetings", "test_standup_sprint24.txt")

    # Positional args are non-flag arguments (ignore --dry-run, --json, etc.)
    positional_args = [a for a in sys.argv[1:] if not a.startswith("--")]
    transcript_path = positional_args[0] if positional_args else default_path
    dry = "--dry-run" in sys.argv or "--dry" in sys.argv
    no_approval = "--no-approval" in sys.argv

    pipeline = ScrumPipeline(require_telegram_approval=not no_approval)
    result = pipeline.run(
        transcript_path=transcript_path,
        update_jira=True,
        dry_run=dry
    )

    # Dump raw JSON for piping
    if "--json" in sys.argv:
        print(json.dumps(result.model_dump(), indent=2, default=str))
