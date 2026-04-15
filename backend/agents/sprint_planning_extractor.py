"""
Sprint Planning Extractor Agent - Phase 7

Extracts sprint planning data from meeting transcripts:
- Sprint goal and duration
- Team capacity and velocity
- Committed stories from backlog
- Developer task assignments
- Sprint dates

This agent handles the bridge between backlog and active sprint.

Author: AI Meeting Automation System
Phase: 7
"""

import os
import json
import logging
from pathlib import Path
from typing import List, Optional, Dict, Any
from datetime import datetime, timedelta

from pydantic import BaseModel, Field, validator
from langchain_groq import ChatGroq
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import PydanticOutputParser

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


# ============================================================================
# DATA MODELS
# ============================================================================

class DeveloperAssignment(BaseModel):
    """A developer's task assignment."""
    developer_name: str = Field(description="Name of the developer")
    story_ids: List[str] = Field(
        default_factory=list,
        description="List of story IDs assigned to this developer"
    )
    task_ids: List[str] = Field(
        default_factory=list,
        description="List of task IDs assigned to this developer"
    )
    estimated_hours: Optional[int] = Field(
        default=None,
        description="Total hours assigned to this developer"
    )


class SprintCommitment(BaseModel):
    """Stories and tasks committed to the sprint."""
    story_ids: List[str] = Field(
        description="Story IDs pulled into sprint (e.g., SP-123)"
    )
    story_points: Optional[int] = Field(
        default=None,
        description="Total story points committed"
    )
    estimated_hours: Optional[int] = Field(
        default=None,
        description="Total estimated hours"
    )


class TeamCapacity(BaseModel):
    """Team capacity for the sprint."""
    total_hours: int = Field(
        description="Total team capacity in hours"
    )
    team_size: int = Field(
        description="Number of team members"
    )
    velocity_last_sprint: Optional[int] = Field(
        default=None,
        description="Velocity from previous sprint (story points)"
    )
    availability_notes: Optional[str] = Field(
        default=None,
        description="Notes about availability (PTO, holidays, etc.)"
    )


class SprintPlanningResult(BaseModel):
    """Complete sprint planning extraction result."""
    
    # Sprint metadata
    sprint_goal: str = Field(
        description="The sprint goal - what the team commits to achieving"
    )
    sprint_number: Optional[int] = Field(
        default=None,
        description="Sprint number if mentioned"
    )
    sprint_duration_weeks: int = Field(
        default=2,
        description="Sprint duration in weeks (usually 2)"
    )
    start_date: Optional[str] = Field(
        default=None,
        description="Sprint start date if mentioned (YYYY-MM-DD)"
    )
    end_date: Optional[str] = Field(
        default=None,
        description="Sprint end date if mentioned (YYYY-MM-DD)"
    )
    
    # Capacity and commitment
    team_capacity: TeamCapacity = Field(
        description="Team capacity information"
    )
    commitment: SprintCommitment = Field(
        description="Stories and tasks committed to sprint"
    )
    
    # Assignments
    developer_assignments: List[DeveloperAssignment] = Field(
        default_factory=list,
        description="Developer task assignments"
    )
    
    # Additional context
    risks_identified: List[str] = Field(
        default_factory=list,
        description="Risks or concerns mentioned during planning"
    )
    dependencies: List[str] = Field(
        default_factory=list,
        description="External dependencies identified"
    )
    notes: Optional[str] = Field(
        default=None,
        description="Additional notes from the meeting"
    )
    
    @validator('sprint_duration_weeks')
    def validate_duration(cls, v):
        if v < 1 or v > 4:
            raise ValueError("Sprint duration must be between 1 and 4 weeks")
        return v


# ============================================================================
# SPRINT PLANNING EXTRACTOR AGENT
# ============================================================================

class SprintPlanningExtractor:
    """
    LangChain-powered agent that extracts sprint planning data from transcripts.
    
    This agent listens for:
    - Sprint goals and objectives
    - Team capacity discussions
    - Story commitments ("Let's pull SP-123 into the sprint")
    - Developer assignments ("I'll take the API work")
    - Risks and dependencies
    
    Example usage:
        extractor = SprintPlanningExtractor()
        result = extractor.extract_from_file("sprint_planning_transcript.txt")
    """
    
    def __init__(
        self,
        model_name: str = "llama-3.3-70b-versatile",
        temperature: float = 0
    ):
        """
        Initialize the Sprint Planning Extractor.
        
        Args:
            model_name: Groq model to use
            temperature: LLM temperature (0 for deterministic)
        """
        api_key = os.getenv("GROQ_API_KEY")
        if not api_key:
            raise ValueError(
                "GROQ_API_KEY environment variable is not set. "
                "Get a free key at https://console.groq.com"
            )
        
        self.llm = ChatGroq(
            model=model_name,
            groq_api_key=api_key,
            temperature=temperature
        )
        
        # Setup parser
        self.parser = PydanticOutputParser(pydantic_object=SprintPlanningResult)
        self.format_instructions = self.parser.get_format_instructions()
        
        # Setup prompt
        self.prompt = self._create_prompt()
        
        # Create chain
        self.chain = self.prompt | self.llm | self.parser
        
        logger.info(f"Initialized SprintPlanningExtractor with model: {model_name}")
    
    def _create_prompt(self) -> ChatPromptTemplate:
        """Create the prompt template for sprint planning extraction."""
        return ChatPromptTemplate.from_messages([
            (
                "system",
                """You are a Scrum Master's assistant analyzing a Sprint Planning meeting transcript.

Sprint Planning is a 2-hour meeting where the team:
1. Defines the Sprint Goal (what they want to achieve)
2. Discusses team capacity (available hours, PTO, etc.)
3. Pulls stories from the backlog into the sprint
4. Breaks stories into tasks
5. Assigns work to developers

Your job is to extract structured data from the transcript.

CRITICAL: NATURAL LANGUAGE MAPPING
People will mention features by NAME, not by ticket ID.
Examples:
- "Let's work on the login feature" → Map to Story ID from context
- "I'll handle the payment integration" → Map to Story ID from context
- "I can take the login API task" → Map to Task ID from context

MAPPING RULES:
1. Use the AVAILABLE STORIES AND TASKS list provided in context
2. Match natural language descriptions to story/task titles
3. Match based on keywords and semantic similarity
4. If someone mentions a feature name, find the matching story ID
5. If someone mentions a specific task, find the matching task ID
6. If explicit ID mentioned (SP-123), use it directly
7. If no match found, extract the description as-is

EXTRACTION RULES:
1. Sprint Goal: Listen for phrases like "Our goal is...", "We want to...", "Let's focus on..."
2. Capacity: Listen for "We have X hours", "Team capacity is...", "Bob is on PTO"
3. Story Commitment: Listen for feature names or story IDs being pulled into sprint
4. Task Assignments: Listen for "I'll take...", "Sarah will handle...", "Assign X to Mike"
5. Risks: Listen for "We're blocked by...", "Risk is...", "Dependency on..."

DEVELOPER ASSIGNMENTS:
- Extract actual names mentioned (Sarah, Mike, Bob, etc.)
- Match assignments to specific story/task IDs
- Developers can be assigned both stories AND tasks

OUTPUT FORMAT:
{format_instructions}

Be precise and map natural language to correct IDs using the context provided.
If something is not mentioned, use null or empty list."""
            ),
            (
                "human",
                """Sprint Planning Meeting Transcript:

{transcript}

{context}

Extract the sprint planning data, mapping natural language to story/task IDs:"""
            )
        ])
    
    def extract(
        self,
        transcript: str,
        context: Optional[Dict[str, Any]] = None
    ) -> SprintPlanningResult:
        """
        Extract sprint planning data from transcript.
        
        Args:
            transcript: The meeting transcript text
            context: Optional context (available stories, tasks, team members, etc.)
        
        Returns:
            SprintPlanningResult with extracted data
        
        Raises:
            Exception: If extraction fails
        """
        logger.info("Starting sprint planning extraction")
        
        # Load context from database if not provided
        if not context:
            logger.info("No context provided, loading from database")
            context = self._load_context_from_database()
        
        # Format context for LLM
        context_str = self._format_context(context)
        
        try:
            # Invoke chain
            result = self.chain.invoke({
                "transcript": transcript,
                "context": context_str,
                "format_instructions": self.format_instructions
            })
            
            logger.info("Sprint planning extraction successful")
            logger.info(f"Sprint Goal: {result.sprint_goal}")
            logger.info(f"Committed Stories: {len(result.commitment.story_ids)}")
            logger.info(f"Developer Assignments: {len(result.developer_assignments)}")
            
            return result
        
        except Exception as e:
            logger.error(f"Sprint planning extraction failed: {e}")
            raise
    
    def _load_context_from_database(self) -> Dict[str, Any]:
        """
        Load available stories and tasks from database.
        
        For sprint planning, we load:
        - Stories from backlog (not in any sprint)
        - Tasks under those stories (if already exist)
        
        Returns:
            Dict with available_stories and available_tasks
        """
        from backend.db.connection import get_session
        from backend.db.models import Story, BacklogTask, SprintStory
        
        logger.info("Loading sprint planning context from database")
        
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
                
                return {
                    'available_stories': available_stories,
                    'available_tasks': available_tasks
                }
        
        except Exception as e:
            logger.error(f"Failed to load context from database: {e}")
            return {
                'available_stories': [],
                'available_tasks': []
            }
    
    def _format_context(self, context: Dict[str, Any]) -> str:
        """
        Format context for LLM prompt.
        
        Args:
            context: Dict with available_stories, available_tasks, etc.
        
        Returns:
            Formatted context string for LLM
        """
        context_str = "\n\nCONTEXT FOR NATURAL LANGUAGE MAPPING:\n"
        context_str += "=" * 60 + "\n"
        
        # Add available stories
        if "available_stories" in context and context["available_stories"]:
            stories = context["available_stories"]
            context_str += f"\nAVAILABLE STORIES IN BACKLOG ({len(stories)} total):\n"
            
            # Show top 30 stories
            for story in stories[:30]:
                context_str += f"\n- {story.get('story_id', 'N/A')}: {story.get('title', 'N/A')}"
                if story.get('story_points'):
                    context_str += f" ({story['story_points']} points)"
                if story.get('epic_id'):
                    context_str += f" [Epic: {story['epic_id']}]"
                context_str += "\n"
                if story.get('description'):
                    desc = story['description'][:100]
                    context_str += f"  Description: {desc}...\n"
            
            if len(stories) > 30:
                context_str += f"\n... and {len(stories) - 30} more stories\n"
        else:
            context_str += "\nNo stories available in backlog.\n"
        
        # Add available tasks
        if "available_tasks" in context and context["available_tasks"]:
            tasks = context["available_tasks"]
            context_str += f"\nAVAILABLE TASKS ({len(tasks)} total):\n"
            
            # Show top 30 tasks
            for task in tasks[:30]:
                context_str += f"\n- {task.get('task_id', 'N/A')}: {task.get('title', 'N/A')}"
                if task.get('story_id'):
                    context_str += f" [Story: {task['story_id']}]"
                if task.get('estimated_hours'):
                    context_str += f" ({task['estimated_hours']}h)"
                context_str += "\n"
            
            if len(tasks) > 30:
                context_str += f"\n... and {len(tasks) - 30} more tasks\n"
        
        # Add team members if provided
        if "team_members" in context and context["team_members"]:
            members = context["team_members"]
            context_str += f"\nTEAM MEMBERS: {', '.join(members)}\n"
        
        # Add previous velocity if provided
        if "previous_velocity" in context:
            velocity = context["previous_velocity"]
            context_str += f"\nPREVIOUS SPRINT VELOCITY: {velocity} story points\n"
        
        context_str += "\n" + "=" * 60 + "\n"
        context_str += "\nINSTRUCTIONS:\n"
        context_str += "- When people mention features by name, map to the correct STORY ID from the list above\n"
        context_str += "- When people mention specific tasks, map to the correct TASK ID from the list above\n"
        context_str += "- Match based on keywords and semantic similarity\n"
        context_str += "- If explicit ID mentioned (SP-123), use it directly\n"
        context_str += "- Developers can be assigned both stories AND tasks\n"
        context_str += "=" * 60 + "\n"
        
        return context_str
    
    def extract_from_file(
        self,
        transcript_path: str,
        context: Optional[Dict[str, Any]] = None
    ) -> SprintPlanningResult:
        """
        Extract sprint planning data from transcript file.
        
        Args:
            transcript_path: Path to transcript file
            context: Optional context dictionary
        
        Returns:
            SprintPlanningResult
        """
        logger.info(f"Loading transcript from: {transcript_path}")
        
        transcript_file = Path(transcript_path)
        if not transcript_file.exists():
            raise FileNotFoundError(f"Transcript not found: {transcript_path}")
        
        with open(transcript_file, 'r', encoding='utf-8') as f:
            transcript = f.read()
        
        return self.extract(transcript, context)
    
    def save_result(
        self,
        result: SprintPlanningResult,
        output_path: str
    ) -> str:
        """
        Save extraction result to JSON file.
        
        Args:
            result: SprintPlanningResult to save
            output_path: Path to save JSON file
        
        Returns:
            Path to saved file
        """
        output_file = Path(output_path)
        output_file.parent.mkdir(parents=True, exist_ok=True)
        
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(result.model_dump(), f, indent=2, ensure_ascii=False)
        
        logger.info(f"Saved sprint planning result to: {output_file}")
        return str(output_file)
    
    def generate_report(
        self,
        result: SprintPlanningResult,
        output_path: str
    ) -> str:
        """
        Generate human-readable markdown report.
        
        Args:
            result: SprintPlanningResult to report on
            output_path: Path to save markdown file
        
        Returns:
            Path to saved report
        """
        report = f"""# Sprint Planning Report

**Generated**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

---

## Sprint Overview

**Sprint Goal**: {result.sprint_goal}

"""
        
        if result.sprint_number:
            report += f"**Sprint Number**: {result.sprint_number}\n"
        
        report += f"**Duration**: {result.sprint_duration_weeks} week(s)\n"
        
        if result.start_date:
            report += f"**Start Date**: {result.start_date}\n"
        if result.end_date:
            report += f"**End Date**: {result.end_date}\n"
        
        report += "\n---\n\n## Team Capacity\n\n"
        report += f"- **Total Hours**: {result.team_capacity.total_hours}h\n"
        report += f"- **Team Size**: {result.team_capacity.team_size} members\n"
        
        if result.team_capacity.velocity_last_sprint:
            report += f"- **Previous Velocity**: {result.team_capacity.velocity_last_sprint} story points\n"
        
        if result.team_capacity.availability_notes:
            report += f"- **Availability Notes**: {result.team_capacity.availability_notes}\n"
        
        report += "\n---\n\n## Sprint Commitment\n\n"
        report += f"**Stories Committed**: {len(result.commitment.story_ids)}\n\n"
        
        if result.commitment.story_ids:
            for story_id in result.commitment.story_ids:
                report += f"- {story_id}\n"
        
        if result.commitment.story_points:
            report += f"\n**Total Story Points**: {result.commitment.story_points}\n"
        
        if result.commitment.estimated_hours:
            report += f"**Total Estimated Hours**: {result.commitment.estimated_hours}h\n"
        
        if result.developer_assignments:
            report += "\n---\n\n## Developer Assignments\n\n"
            
            for assignment in result.developer_assignments:
                report += f"### {assignment.developer_name}\n\n"
                
                if assignment.story_ids:
                    report += "**Stories**:\n"
                    for story_id in assignment.story_ids:
                        report += f"- {story_id}\n"
                    report += "\n"
                
                if assignment.task_ids:
                    report += "**Tasks**:\n"
                    for task_id in assignment.task_ids:
                        report += f"- {task_id}\n"
                    report += "\n"
                
                if assignment.estimated_hours:
                    report += f"**Estimated Hours**: {assignment.estimated_hours}h\n\n"
        
        if result.risks_identified:
            report += "\n---\n\n## Risks Identified\n\n"
            for risk in result.risks_identified:
                report += f"- {risk}\n"
        
        if result.dependencies:
            report += "\n---\n\n## Dependencies\n\n"
            for dep in result.dependencies:
                report += f"- {dep}\n"
        
        if result.notes:
            report += f"\n---\n\n## Additional Notes\n\n{result.notes}\n"
        
        report += f"\n---\n\n*Report generated by ScrumPilot Sprint Planning Extractor*\n"
        
        # Save report
        output_file = Path(output_path)
        output_file.parent.mkdir(parents=True, exist_ok=True)
        
        with open(output_file, 'w', encoding='utf-8') as f:
            f.write(report)
        
        logger.info(f"Generated sprint planning report: {output_file}")
        return str(output_file)


# ============================================================================
# STANDALONE TEST
# ============================================================================

def main():
    """Standalone test function."""
    from dotenv import load_dotenv
    load_dotenv()
    
    # Example transcript
    example_transcript = """
Sprint Planning Meeting - Sprint 23
Date: April 12, 2026

Scrum Master: Welcome everyone! Let's start our Sprint 23 planning. 
Our goal for this sprint is to complete the payment gateway integration 
and get it ready for production.

PM: Yes, we need to deliver the Stripe integration by end of sprint. 
This is critical for our Q2 launch.

Tech Lead: Okay, let's talk capacity. We have 5 developers this sprint.
Bob is on PTO for 3 days, so we're looking at about 80 hours total capacity.

Sarah: I can take the Stripe API integration work. That's story SP-187.

Mike: I'll handle the frontend payment form. That's SP-188.

Tech Lead: Great. Let's also pull in SP-192 for the payment confirmation emails.

Sarah: I can take that too after I finish the API work.

PM: What about testing? Do we have capacity?

Mike: Yes, I'll also handle the integration tests. We should pull in SP-195 
for the test suite.

Scrum Master: So we're committing to 4 stories: SP-187, SP-188, SP-192, and SP-195.
That's about 34 story points based on our last grooming session.

Tech Lead: One risk - we're dependent on the DevOps team to set up the 
Stripe webhook endpoints. We need that by Wednesday.

Sarah: Also, the Stripe API documentation is a bit unclear on refunds. 
That might slow us down.

Scrum Master: Noted. I'll follow up with DevOps today. Anything else?

PM: No, I think we're good. Let's commit to this sprint goal and get started!

Scrum Master: Perfect. Sprint 23 starts Monday, April 14th and ends Friday, April 25th.
Let's make it happen!
"""
    
    # Context
    context = {
        "available_stories": [
            {"story_id": "SP-187", "title": "Stripe API Integration"},
            {"story_id": "SP-188", "title": "Payment Form UI"},
            {"story_id": "SP-192", "title": "Payment Confirmation Emails"},
            {"story_id": "SP-195", "title": "Integration Test Suite"}
        ],
        "team_members": ["Sarah", "Mike", "Bob", "Alice", "Tom"],
        "previous_velocity": 38
    }
    
    # Extract
    extractor = SprintPlanningExtractor()
    result = extractor.extract(example_transcript, context)
    
    # Print result
    print("\n" + "=" * 70)
    print("SPRINT PLANNING EXTRACTION RESULT")
    print("=" * 70)
    print(json.dumps(result.model_dump(), indent=2))
    
    # Save files
    date_str = datetime.now().strftime('%Y-%m-%d')
    json_path = f"backend/data/sprint_planning/{date_str}_sprint_plan.json"
    report_path = f"backend/data/sprint_planning/{date_str}_sprint_report.md"
    
    extractor.save_result(result, json_path)
    extractor.generate_report(result, report_path)
    
    print(f"\nSaved to: {json_path}")
    print(f"Report: {report_path}")


if __name__ == "__main__":
    main()
