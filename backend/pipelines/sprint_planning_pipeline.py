"""
Sprint Planning Pipeline - Phase 7

Orchestrates the sprint planning workflow:
1. Extract sprint plan from meeting transcript
2. Create sprint in Jira
3. Move committed stories to active sprint
4. Assign developers to tasks
5. Set sprint dates and goals

This bridges the gap between backlog and active sprint.

Author: AI Meeting Automation System
Phase: 7
"""

import os
import json
import logging
from pathlib import Path
from typing import Optional, Dict, Any, List
from datetime import datetime, timedelta

from pydantic import BaseModel, Field

from backend.agents.sprint_planning_extractor import (
    SprintPlanningExtractor,
    SprintPlanningResult
)
from backend.tools.jira_client import JiraManager

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


# ============================================================================
# PIPELINE MODELS
# ============================================================================

class SprintCreationResult(BaseModel):
    """Result of sprint creation in Jira."""
    sprint_id: str = Field(description="Jira sprint ID")
    sprint_name: str = Field(description="Sprint name")
    sprint_key: str = Field(description="Sprint key (e.g., SP-23)")
    stories_moved: int = Field(description="Number of stories moved to sprint")
    tasks_assigned: int = Field(description="Number of tasks assigned")
    developers_assigned: int = Field(description="Number of developers with assignments")
    errors: List[str] = Field(default_factory=list)


class SprintPlanningPipelineResult(BaseModel):
    """Complete pipeline execution result."""
    pipeline_id: str
    start_time: str
    end_time: Optional[str] = None
    status: str  # 'completed', 'failed', 'partial', 'paused'
    current_phase: str = 'initialization'
    
    # Input
    transcript_path: str
    
    # Extraction result
    sprint_plan: Optional[Dict] = None
    extraction_file: Optional[str] = None
    
    # Jira creation result
    jira_result: Optional[Dict] = None
    jira_creation_file: Optional[str] = None
    
    # Summary
    sprint_goal: Optional[str] = None
    stories_committed: int = 0
    developers_assigned: int = 0
    
    # Approval
    approval_id: Optional[int] = None
    
    # Errors
    errors: List[str] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)


# ============================================================================
# SPRINT PLANNING PIPELINE
# ============================================================================

class SprintPlanningPipeline:
    """
    Orchestrates complete sprint planning workflow.
    
    Workflow:
    1. Extract sprint plan from transcript
    2. Validate extracted data
    3. Create sprint in Jira
    4. Move stories to sprint
    5. Assign developers
    6. Generate reports
    
    Example usage:
        pipeline = SprintPlanningPipeline()
        result = pipeline.run(
            transcript_path="sprint_planning_transcript.txt",
            create_in_jira=True
        )
    """
    
    def __init__(self, require_telegram_approval: bool = True):
        """
        Initialize the Sprint Planning Pipeline.
        
        Args:
            require_telegram_approval: If True, pause for PM approval before Jira creation
        """
        self.extractor = SprintPlanningExtractor()
        self.jira = None  # Lazy load
        self.require_telegram_approval = require_telegram_approval
        logger.info(f"SprintPlanningPipeline initialized (approval={require_telegram_approval})")
    
    def run(
        self,
        transcript_path: str,
        create_in_jira: bool = True,
        dry_run: bool = False,
        context: Optional[Dict[str, Any]] = None
    ) -> SprintPlanningPipelineResult:
        """
        Run complete sprint planning pipeline.
        
        Args:
            transcript_path: Path to sprint planning transcript
            create_in_jira: Whether to create sprint in Jira
            dry_run: If True, simulate without actual Jira creation
            context: Optional context (available stories, team members, etc.)
        
        Returns:
            SprintPlanningPipelineResult
        """
        pipeline_id = datetime.now().strftime('%Y%m%d_%H%M%S')
        
        result = SprintPlanningPipelineResult(
            pipeline_id=pipeline_id,
            start_time=datetime.now().isoformat(),
            status='in_progress',
            transcript_path=transcript_path
        )
        
        print("\n" + "=" * 70)
        print("SPRINT PLANNING PIPELINE - Phase 7")
        print("=" * 70)
        print(f"Pipeline ID: {pipeline_id}")
        print(f"Transcript: {transcript_path}")
        print(f"Create in Jira: {create_in_jira}")
        print(f"Dry Run: {dry_run}")
        print("=" * 70 + "\n")
        
        try:
            # Phase 1: Extract sprint plan
            print("Phase 1: Extracting sprint plan from transcript...")
            sprint_plan = self._extract_sprint_plan(transcript_path, context)
            
            result.sprint_plan = sprint_plan.model_dump()
            result.sprint_goal = sprint_plan.sprint_goal
            result.stories_committed = len(sprint_plan.commitment.story_ids)
            result.developers_assigned = len(sprint_plan.developer_assignments)
            
            # Save extraction result
            date_str = datetime.now().strftime('%Y-%m-%d')
            extraction_file = f"backend/data/sprint_planning/{date_str}_sprint_plan.json"
            self.extractor.save_result(sprint_plan, extraction_file)
            result.extraction_file = extraction_file
            
            print(f"  Sprint Goal: {sprint_plan.sprint_goal}")
            print(f"  Stories Committed: {len(sprint_plan.commitment.story_ids)}")
            print(f"  Developers: {len(sprint_plan.developer_assignments)}")
            
            # Phase 2: Create approval request if required
            if self.require_telegram_approval and create_in_jira:
                print("\nPhase 2: Creating approval request...")
                approval_id = self._create_telegram_approval_for_sprint(
                    sprint_plan=sprint_plan,
                    extraction_file=extraction_file
                )
                result.approval_id = approval_id
                result.status = 'paused'
                result.current_phase = 'sprint_extraction'
                result.end_time = datetime.now().isoformat()
                
                print("\n" + "=" * 70)
                print("✅ APPROVAL REQUEST CREATED")
                print("=" * 70)
                print(f"Approval ID: #{approval_id}")
                print(f"📱 Telegram notification sent to PM")
                print(f"⏸️  Pipeline paused. Waiting for approval...")
                print()
                print(f"The PM will receive a Telegram notification to review:")
                print(f"  - Sprint Goal: {sprint_plan.sprint_goal}")
                print(f"  - Stories: {len(sprint_plan.commitment.story_ids)}")
                print(f"  - Developers: {len(sprint_plan.developer_assignments)}")
                print()
                print(f"After approval, the system will automatically:")
                print(f"  1. Create sprint in Jira")
                print(f"  2. Move stories to sprint")
                print(f"  3. Assign developers")
                print(f"  4. Update database")
                print("=" * 70 + "\n")
                
                return result
            
            # Phase 3: Create in Jira (if no approval required)
            if create_in_jira:
                print("\nPhase 2: Creating sprint in Jira...")
                
                if dry_run:
                    print("  DRY RUN MODE - Simulating Jira creation")
                    jira_result = self._simulate_jira_creation(sprint_plan)
                else:
                    jira_result = self._create_sprint_in_jira(sprint_plan)
                
                result.jira_result = jira_result
                
                # Save Jira result
                jira_file = f"backend/data/sprint_planning/{date_str}_jira_creation.json"
                Path(jira_file).parent.mkdir(parents=True, exist_ok=True)
                with open(jira_file, 'w', encoding='utf-8') as f:
                    json.dump(jira_result, f, indent=2, ensure_ascii=False)
                result.jira_creation_file = jira_file
                
                print(f"  Sprint Created: {jira_result.get('sprint_name', 'N/A')}")
                print(f"  Stories Moved: {jira_result.get('stories_moved', 0)}")
                print(f"  Tasks Assigned: {jira_result.get('tasks_assigned', 0)}")
            else:
                print("\nSkipping Jira creation (create_in_jira=False)")
            
            # Phase 4: Generate report
            print("\nPhase 4: Generating report...")
            report_file = f"backend/data/sprint_planning/{date_str}_sprint_report.md"
            self.extractor.generate_report(sprint_plan, report_file)
            print(f"  Report saved: {report_file}")
            
            # Mark as complete
            result.status = 'completed'
            result.end_time = datetime.now().isoformat()
            
            print("\n" + "=" * 70)
            print("SPRINT PLANNING PIPELINE COMPLETE")
            print("=" * 70)
            print(f"Sprint Goal: {result.sprint_goal}")
            print(f"Stories Committed: {result.stories_committed}")
            print(f"Developers Assigned: {result.developers_assigned}")
            print("=" * 70 + "\n")
            
            return result
        
        except Exception as e:
            logger.error(f"Pipeline failed: {e}")
            result.status = 'failed'
            result.errors.append(str(e))
            result.end_time = datetime.now().isoformat()
            
            print(f"\nPipeline failed: {e}")
            raise
    
    def _extract_sprint_plan(
        self,
        transcript_path: str,
        context: Optional[Dict[str, Any]]
    ) -> SprintPlanningResult:
        """Extract sprint plan from transcript."""
        
        # If no context provided, try to load from backlog
        if not context:
            context = self._load_backlog_context()
        
        return self.extractor.extract_from_file(transcript_path, context)
    
    def _load_backlog_context(self) -> Dict[str, Any]:
        """
        Load context from existing backlog data.
        
        Loads:
        - Stories from backlog (not in any sprint)
        - Tasks under those stories
        - Latest WSJF data for priorities
        
        Returns:
            Dict with available_stories, available_tasks, previous_velocity
        """
        from backend.db.connection import get_session
        from backend.db.models import Story, BacklogTask, SprintStory
        
        context = {}
        
        logger.info("Loading backlog context from database")
        
        try:
            with get_session() as session:
                # Get stories not in any sprint (backlog)
                # Stories in sprint have entries in sprint_stories table
                stories_in_sprint = session.query(SprintStory.story_id).distinct()
                
                stories = session.query(Story).filter(
                    ~Story.id.in_(stories_in_sprint),
                    Story.jira_key.isnot(None)
                ).all()
                
                logger.info(f"Found {len(stories)} stories in backlog")
                
                # Get tasks for these stories
                story_ids = [s.id for s in stories]
                tasks = session.query(BacklogTask).filter(
                    BacklogTask.story_id.in_(story_ids),
                    BacklogTask.jira_key.isnot(None)
                ).all() if story_ids else []
                
                logger.info(f"Found {len(tasks)} tasks for backlog stories")
                
                # Format stories
                available_stories = []
                for story in stories:
                    available_stories.append({
                        'story_id': story.jira_key,
                        'title': story.title,
                        'description': story.description,
                        'story_points': None,  # Story model doesn't have story_points
                        'epic_id': story.epic.jira_key if story.epic else None
                    })
                
                # Format tasks
                available_tasks = []
                for task in tasks:
                    available_tasks.append({
                        'task_id': task.jira_key,
                        'title': task.title,
                        'description': task.description,
                        'story_id': task.story.jira_key if task.story else None,
                        'estimated_hours': task.estimated_hours
                    })
                
                context['available_stories'] = available_stories
                context['available_tasks'] = available_tasks
                
                # Calculate velocity estimate from story points in sprint_stories
                velocity_query = session.query(SprintStory).all()
                total_points = sum(ss.story_points or 0 for ss in velocity_query)
                if total_points > 0:
                    context['previous_velocity'] = total_points
        
        except Exception as e:
            logger.error(f"Failed to load backlog context from database: {e}")
            context['available_stories'] = []
            context['available_tasks'] = []
        
        # Fallback: Try to load from latest decomposed backlog file
        if not context.get('available_stories'):
            logger.info("No stories in database, trying to load from decomposed backlog file")
            decomposed_dir = Path("backend/data/decomposed")
            if decomposed_dir.exists():
                json_files = sorted(decomposed_dir.glob("*_decomposed_backlog.json"), reverse=True)
                if json_files:
                    latest_backlog = json_files[0]
                    logger.info(f"Loading backlog context from: {latest_backlog}")
                    
                    try:
                        with open(latest_backlog, 'r', encoding='utf-8') as f:
                            backlog_data = json.load(f)
                        
                        # Extract available stories
                        available_stories = []
                        for epic in backlog_data.get('epics', []):
                            for story in epic.get('stories', []):
                                available_stories.append({
                                    'story_id': story.get('story_id', 'N/A'),
                                    'title': story.get('title', 'N/A'),
                                    'story_points': story.get('story_points', 0),
                                    'epic_id': epic.get('epic_id', 'N/A')
                                })
                        
                        context['available_stories'] = available_stories
                        logger.info(f"Loaded {len(available_stories)} available stories from file")
                    except Exception as e:
                        logger.error(f"Failed to load from file: {e}")
        
        # Try to load latest WSJF data for velocity
        if 'previous_velocity' not in context:
            wsjf_dir = Path("backend/data/wsjf")
            if wsjf_dir.exists():
                json_files = sorted(wsjf_dir.glob("*_wsjf_scores.json"), reverse=True)
                if json_files:
                    latest_wsjf = json_files[0]
                    try:
                        with open(latest_wsjf, 'r', encoding='utf-8') as f:
                            wsjf_data = json.load(f)
                        
                        # Calculate total story points as velocity estimate
                        total_points = sum(
                            epic.get('wsjf_components', {}).get('effort', 0)
                            for epic in wsjf_data.get('epics_with_wsjf', [])
                        )
                        context['previous_velocity'] = total_points
                    except Exception as e:
                        logger.error(f"Failed to load WSJF data: {e}")
        
        return context
    
    def _create_telegram_approval_for_sprint(
        self,
        sprint_plan: SprintPlanningResult,
        extraction_file: str
    ) -> int:
        """
        Create Telegram approval request for sprint planning.
        
        This sends the complete sprint plan (goal, stories, assignments)
        for PM approval before Jira creation.
        
        Args:
            sprint_plan: Extracted sprint planning result
            extraction_file: Path to sprint plan JSON file
        
        Returns:
            approval_id: ID of created approval request
        
        Raises:
            Exception: If no PM user found or approval creation fails
        """
        from backend.telegram.services.approval_service import approval_service
        
        logger.info("Creating Telegram approval request for sprint planning")
        
        # Count stories and assignments
        total_stories = len(sprint_plan.commitment.story_ids)
        total_developers = len(sprint_plan.developer_assignments)
        total_assignments = sum(
            len(a.story_ids) + len(a.task_ids)
            for a in sprint_plan.developer_assignments
        )
        
        logger.info(f"Sprint plan: {total_stories} stories, {total_developers} developers, {total_assignments} assignments")
        
        # Get PM user for approval assignment
        pm_user_id = approval_service.get_pm_user_id()
        if not pm_user_id:
            raise Exception(
                "No PM user found for approval. "
                "Please ensure a user with 'product_owner' role exists and has Telegram linked."
            )
        
        logger.info(f"Assigning approval to PM user ID: {pm_user_id}")
        
        # Get system/bot user (requester)
        system_user_id = 1  # Bot user ID
        
        # Create approval request with sprint plan data
        approval_data = {
            'sprint_plan_file': extraction_file,
            'sprint_goal': sprint_plan.sprint_goal,
            'sprint_number': sprint_plan.sprint_number,
            'start_date': sprint_plan.start_date,
            'end_date': sprint_plan.end_date,
            'duration_weeks': sprint_plan.sprint_duration_weeks,
            'story_ids': sprint_plan.commitment.story_ids,
            'developer_assignments': [
                {
                    'developer_name': a.developer_name,
                    'story_ids': a.story_ids,
                    'task_ids': a.task_ids,
                    'estimated_hours': a.estimated_hours
                }
                for a in sprint_plan.developer_assignments
            ],
            'summary': {
                'total_stories': total_stories,
                'total_developers': total_developers,
                'total_assignments': total_assignments,
                'team_capacity_hours': sprint_plan.team_capacity.total_hours
            }
        }
        
        approval_id = approval_service.create_sprint_approval(
            sprint_data=approval_data,
            requested_by_user_id=system_user_id,
            assigned_to_user_id=pm_user_id,
            priority='high'
        )
        
        logger.info(f"Created approval request #{approval_id}")
        
        # Log summary
        print(f"\nSprint plan submitted for approval:")
        print(f"  Sprint Goal: {sprint_plan.sprint_goal}")
        print(f"  Stories: {total_stories}")
        print(f"  Developers: {total_developers}")
        print(f"  Assignments: {total_assignments}")
        print()
        print(f"Stories to commit:")
        for i, story_id in enumerate(sprint_plan.commitment.story_ids[:5], 1):
            print(f"  {i}. {story_id}")
        
        if len(sprint_plan.commitment.story_ids) > 5:
            print(f"  ... and {len(sprint_plan.commitment.story_ids) - 5} more")
        
        return approval_id
    
    def _create_sprint_in_jira(
        self,
        sprint_plan: SprintPlanningResult
    ) -> Dict[str, Any]:
        """
        Create sprint in Jira and move stories.
        
        Steps:
        1. Create sprint with goal
        2. Move stories to sprint
        3. Assign developers
        4. Set sprint dates
        """
        if not self.jira:
            self.jira = JiraManager()
        
        result = {
            'sprint_id': None,
            'sprint_name': None,
            'sprint_key': None,
            'stories_moved': 0,
            'tasks_assigned': 0,
            'developers_assigned': 0,
            'errors': []
        }
        
        try:
            # Step 1: Create sprint
            sprint_name = f"Sprint {sprint_plan.sprint_number}" if sprint_plan.sprint_number else f"Sprint {datetime.now().strftime('%Y-%m-%d')}"
            
            print(f"  Creating sprint: {sprint_name}")
            print(f"  Goal: {sprint_plan.sprint_goal}")
            
            # Calculate dates
            start_date = sprint_plan.start_date or datetime.now().strftime('%Y-%m-%d')
            if sprint_plan.end_date:
                end_date = sprint_plan.end_date
            else:
                # Calculate end date based on duration
                start = datetime.strptime(start_date, '%Y-%m-%d')
                end = start + timedelta(weeks=sprint_plan.sprint_duration_weeks)
                end_date = end.strftime('%Y-%m-%d')
            
            # Create sprint using Jira API
            sprint_data = self.jira.create_sprint(
                name=sprint_name,
                goal=sprint_plan.sprint_goal,
                start_date=start_date,
                end_date=end_date
            )
            
            result['sprint_id'] = sprint_data.get('id')
            result['sprint_name'] = sprint_name
            result['sprint_key'] = sprint_data.get('key', sprint_name)
            
            print(f"  Sprint created: {result['sprint_id']}")
            
            # Step 2: Move stories to sprint
            if sprint_plan.commitment.story_ids:
                print(f"  Moving {len(sprint_plan.commitment.story_ids)} stories to sprint...")
                
                for story_id in sprint_plan.commitment.story_ids:
                    try:
                        self.jira.move_issue_to_sprint(story_id, result['sprint_id'])
                        result['stories_moved'] += 1
                        print(f"    Moved: {story_id}")
                    except Exception as e:
                        error_msg = f"Failed to move {story_id}: {str(e)}"
                        result['errors'].append(error_msg)
                        logger.error(error_msg)
            
            # Step 3: Assign developers
            if sprint_plan.developer_assignments:
                print(f"  Assigning tasks to {len(sprint_plan.developer_assignments)} developers...")
                
                for assignment in sprint_plan.developer_assignments:
                    dev_name = assignment.developer_name
                    result['developers_assigned'] += 1
                    
                    # Assign stories
                    for story_id in assignment.story_ids:
                        try:
                            self.jira.assign_issue(story_id, dev_name)
                            result['tasks_assigned'] += 1
                            print(f"    Assigned {story_id} to {dev_name}")
                        except Exception as e:
                            error_msg = f"Failed to assign {story_id} to {dev_name}: {str(e)}"
                            result['errors'].append(error_msg)
                            logger.error(error_msg)
                    
                    # Assign tasks
                    for task_id in assignment.task_ids:
                        try:
                            self.jira.assign_issue(task_id, dev_name)
                            result['tasks_assigned'] += 1
                            print(f"    Assigned {task_id} to {dev_name}")
                        except Exception as e:
                            error_msg = f"Failed to assign {task_id} to {dev_name}: {str(e)}"
                            result['errors'].append(error_msg)
                            logger.error(error_msg)
            
            print(f"  Sprint creation complete!")
            
        except Exception as e:
            error_msg = f"Sprint creation failed: {str(e)}"
            result['errors'].append(error_msg)
            logger.error(error_msg)
            raise
        
        return result
    
    def _simulate_jira_creation(
        self,
        sprint_plan: SprintPlanningResult
    ) -> Dict[str, Any]:
        """Simulate Jira creation for dry run mode."""
        sprint_name = f"Sprint {sprint_plan.sprint_number}" if sprint_plan.sprint_number else "Sprint (Simulated)"
        
        total_tasks = sum(
            len(a.story_ids) + len(a.task_ids)
            for a in sprint_plan.developer_assignments
        )
        
        return {
            'sprint_id': 'SIMULATED-123',
            'sprint_name': sprint_name,
            'sprint_key': 'SIM-23',
            'stories_moved': len(sprint_plan.commitment.story_ids),
            'tasks_assigned': total_tasks,
            'developers_assigned': len(sprint_plan.developer_assignments),
            'errors': []
        }


# ============================================================================
# MAIN EXECUTION
# ============================================================================

def main():
    """Main execution function for testing."""
    from dotenv import load_dotenv
    load_dotenv()
    
    import sys
    
    # Parse arguments
    dry_run = '--dry-run' in sys.argv or '--dry' in sys.argv
    no_jira = '--no-jira' in sys.argv
    
    # Default transcript path
    transcript_path = "backend/data/sprint_planning/example_sprint_planning_transcript.txt"
    
    # Check if custom path provided
    args = [a for a in sys.argv[1:] if not a.startswith('--')]
    if args:
        transcript_path = args[0]
    
    # Run pipeline
    pipeline = SprintPlanningPipeline()
    
    try:
        result = pipeline.run(
            transcript_path=transcript_path,
            create_in_jira=not no_jira,
            dry_run=dry_run
        )
        
        print("\n" + "=" * 70)
        print("PIPELINE RESULT")
        print("=" * 70)
        print(f"Status: {result.status}")
        print(f"Sprint Goal: {result.sprint_goal}")
        print(f"Stories Committed: {result.stories_committed}")
        print(f"Developers Assigned: {result.developers_assigned}")
        
        if result.errors:
            print(f"\nErrors: {len(result.errors)}")
            for error in result.errors:
                print(f"  - {error}")
        
        print("=" * 70)
        
    except Exception as e:
        print(f"\nPipeline failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
