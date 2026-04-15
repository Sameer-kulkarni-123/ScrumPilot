"""
Epic Decomposer Agent

Breaks prioritized Epics (from WSJF Phase 3) into User Stories and Sub-tasks
for Jira creation. Each Epic is decomposed into 3-5 User Stories, each with
2-4 Sub-tasks and 2-4 Acceptance Criteria.

Uses LangChain with Groq LLM for intelligent decomposition based on
Epic context, features, and business value.

Author: AI Meeting Automation System
Phase: 4
"""

import os
import json
import logging
from pathlib import Path
from typing import Dict, List, Optional
from datetime import datetime

from pydantic import BaseModel, Field, field_validator
from langchain_groq import ChatGroq
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import JsonOutputParser
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


# ============================================================================
# PYDANTIC MODELS
# ============================================================================

class SubTask(BaseModel):
    """A single actionable sub-task within a User Story.

    Attributes:
        task_id: Unique identifier for the sub-task (e.g., 'task_001')
        title: Clear, specific title of the sub-task
        description: Detailed description of what needs to be done
        estimated_hours: Estimated hours to complete (4-16 hours)
        story_points: Fibonacci story points (1, 2, 3, 5, 8, 13)
    """
    task_id: str = Field(
        ...,
        description="Unique identifier for the sub-task (e.g., 'task_001')"
    )
    title: str = Field(
        ...,
        description="Clear, specific title of the sub-task"
    )
    description: str = Field(
        ...,
        description="Detailed description of what needs to be done"
    )
    estimated_hours: int = Field(
        ...,
        ge=4,
        le=16,
        description="Estimated hours to complete (4-16 hours)"
    )
    story_points: Optional[int] = Field(
        default=None,
        description="Fibonacci story points (1, 2, 3, 5, 8, 13) - calculated from hours"
    )


class UserStory(BaseModel):
    """A User Story within an Epic.

    Attributes:
        story_id: Unique identifier for the story (e.g., 'story_001')
        title: User story title in 'As a [user], I want to [action]' format
        description: Detailed description of the story
        acceptance_criteria: List of 2-4 testable acceptance criteria
        tasks: List of 2-4 actionable sub-tasks
        story_points: Fibonacci story points (1, 2, 3, 5, 8, 13)
    """
    story_id: str = Field(
        ...,
        description="Unique identifier for the story (e.g., 'story_001')"
    )
    title: str = Field(
        ...,
        description="User story in 'As a [user], I want to [action], so that [benefit]' format"
    )
    description: str = Field(
        ...,
        description="Detailed description of the user story"
    )
    acceptance_criteria: List[str] = Field(
        ...,
        min_length=2,
        max_length=4,
        description="List of 2-4 testable acceptance criteria"
    )
    tasks: List[SubTask] = Field(
        ...,
        min_length=2,
        max_length=4,
        description="List of 2-4 actionable sub-tasks"
    )
    story_points: Optional[int] = Field(
        default=None,
        description="Fibonacci story points (1, 2, 3, 5, 8, 13) - calculated from total hours"
    )

    @field_validator('title')
    @classmethod
    def validate_story_format(cls, v: str) -> str:
        """Validate that story title follows 'As a ...' format."""
        if not v.lower().startswith("as a"):
            raise ValueError(
                f"Story title must start with 'As a [user]'. Got: '{v}'"
            )
        return v


class DecomposedEpic(BaseModel):
    """An Epic decomposed into User Stories and Sub-tasks.

    Attributes:
        epic_id: Epic identifier from WSJF data
        title: Epic title
        description: Epic description
        wsjf_score: Calculated WSJF score
        priority_rank: Priority ranking (1 = highest)
        stories: List of 3-5 User Stories
    """
    epic_id: str = Field(
        ...,
        description="Epic identifier from WSJF data"
    )
    title: str = Field(
        ...,
        description="Epic title"
    )
    description: str = Field(
        ...,
        description="Epic description"
    )
    wsjf_score: float = Field(
        ...,
        description="Calculated WSJF score from Phase 3"
    )
    priority_rank: int = Field(
        ...,
        ge=1,
        description="Priority ranking (1 = highest)"
    )
    stories: List[UserStory] = Field(
        ...,
        min_length=3,
        max_length=5,
        description="List of 3-5 User Stories"
    )


class DecomposedBacklog(BaseModel):
    """Complete decomposed backlog with all Epics broken into Stories and Sub-tasks.

    Attributes:
        decomposition_date: Date the decomposition was performed
        total_epics: Total number of Epics decomposed
        total_stories: Total number of User Stories generated
        total_tasks: Total number of Sub-tasks generated
        total_estimated_hours: Total estimated hours across all Sub-tasks
        epics: List of decomposed Epics
    """
    decomposition_date: str = Field(
        ...,
        description="Date the decomposition was performed (YYYY-MM-DD)"
    )
    total_epics: int = Field(
        default=0,
        description="Total number of Epics decomposed"
    )
    total_stories: int = Field(
        default=0,
        description="Total number of User Stories generated"
    )
    total_tasks: int = Field(
        default=0,
        description="Total number of Sub-tasks generated"
    )
    total_estimated_hours: int = Field(
        default=0,
        description="Total estimated hours across all Sub-tasks"
    )
    epics: List[DecomposedEpic] = Field(
        ...,
        description="List of decomposed Epics"
    )


# ============================================================================
# EPIC DECOMPOSER AGENT
# ============================================================================

class EpicDecomposerAgent:
    """
    Agent to decompose prioritized Epics into User Stories and Sub-tasks.

    Takes WSJF-prioritized Epics from Phase 3 and uses LangChain + Groq LLM
    to generate structured, actionable User Stories with Sub-tasks and
    Acceptance Criteria for each Epic.

    Responsibilities:
    - Load WSJF data from Phase 3
    - Decompose each Epic into 3-5 User Stories
    - Generate 2-4 Sub-tasks per Story (4-16 hours each)
    - Add 2-4 Acceptance Criteria per Story
    - Validate all output against Pydantic models
    - Save decomposed backlog as JSON
    - Generate Markdown report
    """

    def __init__(self, model_name: str = "llama-3.3-70b-versatile"):
        """
        Initialize the EpicDecomposerAgent.

        Args:
            model_name: Groq model to use for decomposition
        
        Raises:
            ValueError: If GROQ_API_KEY environment variable is not set
        """
        api_key = os.getenv("GROQ_API_KEY")
        if not api_key:
            logger.error("GROQ_API_KEY environment variable is not set")
            raise ValueError(
                "GROQ_API_KEY environment variable is not set. "
                "Get a free key at https://console.groq.com"
            )

        logger.info(f"Initializing EpicDecomposerAgent with model: {model_name}")
        
        self.llm = ChatGroq(
            model=model_name,
            groq_api_key=api_key,
            temperature=0.3,
        )

        self.parser = JsonOutputParser()

        self.prompt = ChatPromptTemplate.from_messages([
            (
                "system",
                (
                    "You are an expert Agile Product Owner and Technical Architect. "
                    "Your job is to decompose Epics into well-structured User Stories "
                    "and actionable Sub-tasks.\n\n"
                    "DECOMPOSITION RULES:\n"
                    "1. Generate exactly {num_stories} User Stories for this Epic\n"
                    "2. Each Story MUST follow the format: 'As a [user], I want to [action], so that [benefit]'\n"
                    "3. Each Story must be independently valuable and deliverable\n"
                    "4. Stories should collectively cover the entire Epic scope\n"
                    "5. Each Story must have {num_criteria} Acceptance Criteria that are:\n"
                    "   - Testable and specific\n"
                    "   - Define 'done' clearly\n"
                    "   - Cover happy path and edge cases\n"
                    "6. Each Story must have {num_tasks} Sub-tasks that:\n"
                    "   - Are specific, actionable technical tasks\n"
                    "   - Have realistic hour estimates (4-16 hours each)\n"
                    "   - Complete the Story when all done\n"
                    "   - A developer should know exactly what to do\n\n"
                    "STORY QUALITY:\n"
                    "- Stories should be INVEST compliant (Independent, Negotiable, Valuable, "
                    "Estimable, Small, Testable)\n"
                    "- Each Story delivers real user value\n"
                    "- Stories can be done in any order\n\n"
                    "SUB-TASK QUALITY:\n"
                    "- Tasks should be concrete development tasks\n"
                    "- Include setup, implementation, testing, and documentation tasks\n"
                    "- Hours must be between 4 and 16 (inclusive)\n\n"
                    "OUTPUT FORMAT:\n"
                    "Return a JSON object with this exact structure:\n"
                    "{{\n"
                    "  \"stories\": [\n"
                    "    {{\n"
                    "      \"story_id\": \"story_001\",\n"
                    "      \"title\": \"As a [user], I want to [action], so that [benefit]\",\n"
                    "      \"description\": \"Detailed description\",\n"
                    "      \"acceptance_criteria\": [\"Criterion 1\", \"Criterion 2\"],\n"
                    "      \"tasks\": [\n"
                    "        {{\n"
                    "          \"task_id\": \"task_001\",\n"
                    "          \"title\": \"Task title\",\n"
                    "          \"description\": \"Task description\",\n"
                    "          \"estimated_hours\": 8\n"
                    "        }}\n"
                    "      ]\n"
                    "    }}\n"
                    "  ]\n"
                    "}}\n\n"
                    "IMPORTANT:\n"
                    "- Return ONLY valid JSON, no markdown or additional text\n"
                    "- story_id format: story_001, story_002, etc.\n"
                    "- task_id format: task_001, task_002, etc. (sequential across all stories)\n"
                    "- estimated_hours must be an integer between 4 and 16\n"
                    "- All acceptance criteria must be testable statements"
                ),
            ),
            (
                "human",
                "Decompose the following Epic into User Stories and Sub-tasks:\n\n"
                "EPIC DETAILS:\n"
                "- Title: {epic_title}\n"
                "- Description: {epic_description}\n"
                "- WSJF Score: {wsjf_score}\n"
                "- Priority Rank: #{priority_rank}\n"
                "- Key Features: {mentioned_features}\n\n"
                "Generate {num_stories} User Stories, each with {num_criteria} "
                "Acceptance Criteria and {num_tasks} Sub-tasks.\n\n"
                "Return ONLY valid JSON."
            ),
        ])

        self.chain = self.prompt | self.llm | self.parser

        # Store decomposition results
        self.wsjf_data: Optional[Dict] = None
        self.decomposed_backlog: Optional[DecomposedBacklog] = None

    @staticmethod
    def calculate_story_points(hours: int) -> int:
        """
        Calculate Fibonacci story points from estimated hours.
        
        Uses standard Agile mapping:
        - 1-8 hours = 1 point (very small)
        - 9-16 hours = 2 points (small)
        - 17-24 hours = 3 points (medium)
        - 25-40 hours = 5 points (large)
        - 41-80 hours = 8 points (very large)
        - 80+ hours = 13 points (extra large, should be split)
        
        Args:
            hours: Estimated hours
            
        Returns:
            Fibonacci story points (1, 2, 3, 5, 8, or 13)
        """
        if hours <= 8:
            return 1
        elif hours <= 16:
            return 2
        elif hours <= 24:
            return 3
        elif hours <= 40:
            return 5
        elif hours <= 80:
            return 8
        else:
            return 13

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception_type((Exception,)),
        reraise=True
    )
    def _call_llm_with_retry(self, **kwargs) -> Dict:
        """
        Call LLM with automatic retry logic for transient failures.
        
        Retries up to 3 times with exponential backoff (2s, 4s, 8s).
        Handles network errors, rate limits, and temporary API issues.
        
        Args:
            **kwargs: Parameters to pass to the LLM chain
            
        Returns:
            LLM response dictionary
            
        Raises:
            Exception: If all retry attempts fail
        """
        try:
            logger.debug(f"Calling LLM for Epic: {kwargs.get('epic_title', 'Unknown')}")
            result = self.chain.invoke(kwargs)
            logger.debug(f"LLM call successful for Epic: {kwargs.get('epic_title', 'Unknown')}")
            return result
        except Exception as e:
            logger.warning(f"LLM call failed (will retry): {e}")
            raise

    def load_wsjf_data(self, wsjf_data_path: str) -> Dict:
        """
        Load WSJF data from Phase 3 JSON file.

        Args:
            wsjf_data_path: Path to WSJF scores JSON file

        Returns:
            WSJF data dictionary

        Raises:
            FileNotFoundError: If WSJF data file doesn't exist
            json.JSONDecodeError: If JSON is invalid
            ValueError: If WSJF data has no Epics
        """
        logger.info(f"Loading WSJF data from: {wsjf_data_path}")
        
        wsjf_path = Path(wsjf_data_path)
        if not wsjf_path.exists():
            logger.error(f"WSJF data file not found: {wsjf_data_path}")
            raise FileNotFoundError(
                f"WSJF data not found: {wsjf_data_path}\n"
                f"Please run WSJF calculation (Phase 3) first."
            )

        with open(wsjf_path, 'r', encoding='utf-8') as f:
            self.wsjf_data = json.load(f)

        epics = self.wsjf_data.get('epics_with_wsjf', [])
        if not epics:
            logger.error("WSJF data contains no Epics")
            raise ValueError(
                "WSJF data contains no Epics. "
                "Please run WSJF calculation (Phase 3) first."
            )

        logger.info(f"Successfully loaded {len(epics)} Epic(s) from WSJF data")
        print(f"✅ Loaded WSJF data: {len(epics)} Epic(s) sorted by priority")
        return self.wsjf_data

    def decompose_epic(
        self,
        epic: Dict,
        num_stories: int = 4,
        num_criteria: int = 3,
        num_tasks: int = 3
    ) -> DecomposedEpic:
        """
        Decompose a single Epic into User Stories and Sub-tasks using LLM.

        Args:
            epic: Epic dictionary from WSJF data
            num_stories: Number of User Stories to generate (3-5)
            num_criteria: Number of Acceptance Criteria per Story (2-4)
            num_tasks: Number of Sub-tasks per Story (2-4)

        Returns:
            DecomposedEpic with validated Stories and Sub-tasks

        Raises:
            ValueError: If decomposition fails validation
            Exception: If LLM call fails
        """
        # Validate story/criteria/task counts
        num_stories = max(3, min(5, num_stories))
        num_criteria = max(2, min(4, num_criteria))
        num_tasks = max(2, min(4, num_tasks))

        epic_title = epic.get('title', 'Unknown Epic')
        epic_id = epic.get('epic_id', 'unknown')

        logger.info(f"Starting decomposition for Epic: {epic_title} ({epic_id})")
        print(f"  🔄 Decomposing: {epic_title} ({epic_id})...")

        # Prepare features string
        features = epic.get('mentioned_features', [])
        features_str = ", ".join(features) if features else "No specific features listed"

        # Call LLM for decomposition with retry logic
        try:
            result = self._call_llm_with_retry(
                epic_title=epic_title,
                epic_description=epic.get('description', ''),
                wsjf_score=epic.get('wsjf_score', 0),
                priority_rank=epic.get('priority_rank', 0),
                mentioned_features=features_str,
                num_stories=num_stories,
                num_criteria=num_criteria,
                num_tasks=num_tasks,
            )
        except Exception as e:
            logger.error(f"LLM decomposition failed for '{epic_title}' after retries: {e}")
            raise Exception(
                f"LLM decomposition failed for '{epic_title}': {e}"
            )

        # Validate and fix the LLM output
        stories = result.get('stories', [])
        if not stories:
            logger.error(f"LLM returned no stories for Epic '{epic_title}'")
            raise ValueError(
                f"LLM returned no stories for Epic '{epic_title}'"
            )

        logger.debug(f"LLM returned {len(stories)} stories for Epic '{epic_title}'")

        # Validate and fix each story
        validated_stories = self._validate_stories(stories, epic_title)

        # Create DecomposedEpic with Pydantic validation
        decomposed_epic = DecomposedEpic(
            epic_id=epic_id,
            title=epic_title,
            description=epic.get('description', ''),
            wsjf_score=epic.get('wsjf_score', 0.0),
            priority_rank=epic.get('priority_rank', 0),
            stories=validated_stories
        )

        total_tasks = sum(len(s.tasks) for s in decomposed_epic.stories)
        total_hours = sum(
            t.estimated_hours
            for s in decomposed_epic.stories
            for t in s.tasks
        )

        print(f"  ✅ {epic_title}: {len(decomposed_epic.stories)} Stories, "
              f"{total_tasks} Sub-tasks, {total_hours} total hours")

        return decomposed_epic

    def _validate_stories(
        self,
        stories: List[Dict],
        epic_title: str,
        min_stories: int = 1  # Allow single Story validation
    ) -> List[UserStory]:
        """
        Validate and fix LLM-generated stories.

        Ensures all stories meet the required format and constraints:
        - Story title starts with 'As a'
        - 2-4 acceptance criteria per story
        - 2-4 sub-tasks per story
        - Sub-task hours between 4-16

        Args:
            stories: Raw story dictionaries from LLM
            epic_title: Epic title for error context
            min_stories: Minimum number of stories required (default: 1)

        Returns:
            List of validated UserStory objects

        Raises:
            ValueError: If stories cannot be validated
        """
        validated = []
        task_counter = 1  # Global task counter across all stories

        for i, story in enumerate(stories):
            story_id = story.get('story_id', f'story_{i + 1:03d}')

            # Fix story title format if needed
            title = story.get('title', '')
            if not title.lower().startswith('as a'):
                title = f"As a user, I want to {title.lower()}"

            # Ensure description exists
            description = story.get('description', title)

            # Validate acceptance criteria count (2-4)
            criteria = story.get('acceptance_criteria', [])
            if len(criteria) < 2:
                criteria.extend([
                    f"Feature works as described in the story"
                    for _ in range(2 - len(criteria))
                ])
            criteria = criteria[:4]  # Cap at 4

            # Validate and fix sub-tasks
            raw_tasks = story.get('tasks', [])
            fixed_tasks = []

            for j, task in enumerate(raw_tasks):
                task_id = task.get('task_id', f'task_{task_counter:03d}')
                task_counter += 1

                # Fix estimated hours to be within range
                hours = task.get('estimated_hours', 8)
                if isinstance(hours, str):
                    try:
                        hours = int(hours)
                    except ValueError:
                        hours = 8
                hours = max(4, min(16, hours))

                # Calculate story points for sub-task
                task_points = self.calculate_story_points(hours)

                fixed_tasks.append(SubTask(
                    task_id=task_id,
                    title=task.get('title', f'Task {j + 1}'),
                    description=task.get('description', task.get('title', '')),
                    estimated_hours=hours,
                    story_points=task_points
                ))

            # Ensure 2-4 tasks
            if len(fixed_tasks) < 2:
                while len(fixed_tasks) < 2:
                    task_id = f'task_{task_counter:03d}'
                    task_counter += 1
                    fixed_tasks.append(SubTask(
                        task_id=task_id,
                        title=f"Write unit tests for {title[:50]}",
                        description="Write comprehensive unit and integration tests",
                        estimated_hours=6,
                        story_points=1
                    ))
            fixed_tasks = fixed_tasks[:4]  # Cap at 4

            # Calculate total story points for the User Story
            story_total_hours = sum(t.estimated_hours for t in fixed_tasks)
            story_points = self.calculate_story_points(story_total_hours)

            logger.debug(f"Story '{story_id}': {story_total_hours}h = {story_points} points")

            validated.append(UserStory(
                story_id=story_id,
                title=title,
                description=description,
                acceptance_criteria=criteria,
                tasks=fixed_tasks,
                story_points=story_points
            ))

        # Ensure minimum stories
        if len(validated) < min_stories:
            raise ValueError(
                f"Only {len(validated)} stories generated for Epic "
                f"'{epic_title}'. Minimum is {min_stories}."
            )
        validated = validated[:5]  # Cap at 5

        return validated

    def _calculate_story_count(self, epic: Dict) -> int:
        """
        Calculate optimal number of Stories based on Epic complexity.
        
        Uses Epic effort score and feature count to determine complexity:
        - Low complexity (effort 1-3, few features): 3 Stories
        - Medium complexity (effort 4-6, moderate features): 4 Stories
        - High complexity (effort 7-10, many features): 5 Stories
        
        Args:
            epic: Epic dictionary from WSJF data
            
        Returns:
            Number of Stories to generate (3-5)
        """
        effort = epic.get('wsjf_components', {}).get('effort', 5)
        features = epic.get('mentioned_features', [])
        feature_count = len(features)
        
        # Calculate complexity score (0-10)
        # Effort contributes 70%, feature count contributes 30%
        effort_score = effort  # Already 1-10
        feature_score = min(10, feature_count)  # Cap at 10
        complexity = (effort_score * 0.7) + (feature_score * 0.3)
        
        # Map complexity to Story count
        if complexity <= 4:
            return 3  # Low complexity
        elif complexity <= 7:
            return 4  # Medium complexity
        else:
            return 5  # High complexity
    
    def _calculate_task_count(self, story_index: int, total_stories: int, epic_effort: int) -> int:
        """
        Calculate optimal number of Sub-tasks based on Story position and Epic effort.
        
        Strategy:
        - First story (setup/foundation): More tasks (3-4)
        - Middle stories (implementation): Medium tasks (2-3)
        - Last story (polish/testing): Fewer tasks (2-3)
        - Higher effort Epics get more tasks per Story
        
        Args:
            story_index: Index of the Story (0-based)
            total_stories: Total number of Stories in Epic
            epic_effort: Epic effort score (1-10)
            
        Returns:
            Number of Sub-tasks to generate (2-4)
        """
        # Base task count on Epic effort
        if epic_effort <= 3:
            base_tasks = 2  # Low effort
        elif epic_effort <= 6:
            base_tasks = 3  # Medium effort
        else:
            base_tasks = 3  # High effort (but not 4 to avoid overload)
        
        # Adjust based on Story position
        if story_index == 0:
            # First story often needs setup/foundation work
            return min(4, base_tasks + 1)
        elif story_index == total_stories - 1:
            # Last story often simpler (polish, documentation)
            return max(2, base_tasks - 1)
        else:
            # Middle stories get base count
            return base_tasks
    
    def _calculate_criteria_count(self, epic_effort: int) -> int:
        """
        Calculate optimal number of Acceptance Criteria based on Epic effort.
        
        Higher effort Epics need more detailed acceptance criteria.
        
        Args:
            epic_effort: Epic effort score (1-10)
            
        Returns:
            Number of Acceptance Criteria to generate (2-4)
        """
        if epic_effort <= 3:
            return 2  # Low effort - simpler criteria
        elif epic_effort <= 6:
            return 3  # Medium effort - standard criteria
        else:
            return 4  # High effort - detailed criteria

    def decompose_all_epics(
        self,
        wsjf_data_path: str,
        use_intelligent_sizing: bool = True
    ) -> DecomposedBacklog:
        """
        Decompose all Epics from WSJF data into User Stories and Sub-tasks.
        
        Uses intelligent sizing based on Epic complexity when use_intelligent_sizing=True:
        - Story count varies by Epic effort and feature count (3-5)
        - Sub-task count varies by Story position and Epic effort (2-4)
        - Acceptance criteria count varies by Epic effort (2-4)

        Args:
            wsjf_data_path: Path to WSJF scores JSON file
            use_intelligent_sizing: If True, vary counts based on complexity (default: True)

        Returns:
            DecomposedBacklog with all Epics decomposed

        Raises:
            FileNotFoundError: If WSJF data file doesn't exist
            ValueError: If decomposition fails
        """
        # Load WSJF data
        print("🔍 Loading WSJF data from Phase 3...")
        logger.info(f"Starting decomposition of all Epics from: {wsjf_data_path}")
        self.load_wsjf_data(wsjf_data_path)

        epics = self.wsjf_data.get('epics_with_wsjf', [])

        sizing_mode = "intelligent" if use_intelligent_sizing else "fixed"
        logger.info(f"Using {sizing_mode} sizing for {len(epics)} Epic(s)")
        print(f"\n🧩 Decomposing {len(epics)} Epic(s) with {sizing_mode} sizing...")
        print("=" * 60)

        decomposed_epics = []
        for epic in epics:
            try:
                if use_intelligent_sizing:
                    # Calculate optimal counts based on Epic complexity
                    num_stories = self._calculate_story_count(epic)
                    num_criteria = self._calculate_criteria_count(
                        epic.get('wsjf_components', {}).get('effort', 5)
                    )
                    epic_effort = epic.get('wsjf_components', {}).get('effort', 5)
                    
                    print(f"  📐 {epic.get('title', 'Unknown')}: "
                          f"{num_stories} Stories, {num_criteria} Criteria/Story "
                          f"(Effort: {epic_effort}/10)")
                    
                    # Decompose with varying task counts per Story
                    decomposed = self._decompose_epic_intelligent(
                        epic, num_stories, num_criteria, epic_effort
                    )
                else:
                    # Fixed counts (original behavior)
                    decomposed = self.decompose_epic(
                        epic,
                        num_stories=4,
                        num_criteria=3,
                        num_tasks=3
                    )
                
                decomposed_epics.append(decomposed)
            except Exception as e:
                logger.error(f"Failed to decompose Epic '{epic.get('title', 'Unknown')}': {e}")
                print(f"  ❌ Failed to decompose '{epic.get('title', 'Unknown')}': {e}")
                raise

        # Calculate totals
        total_stories = sum(len(e.stories) for e in decomposed_epics)
        total_tasks = sum(
            len(s.tasks) for e in decomposed_epics for s in e.stories
        )
        total_hours = sum(
            t.estimated_hours
            for e in decomposed_epics
            for s in e.stories
            for t in s.tasks
        )
        total_story_points = sum(
            s.story_points or 0
            for e in decomposed_epics
            for s in e.stories
        )

        logger.info(f"Decomposition complete: {len(decomposed_epics)} Epics, {total_stories} Stories, "
                   f"{total_tasks} Sub-tasks, {total_hours}h, {total_story_points} points")

        # Create DecomposedBacklog
        self.decomposed_backlog = DecomposedBacklog(
            decomposition_date=datetime.now().strftime('%Y-%m-%d'),
            total_epics=len(decomposed_epics),
            total_stories=total_stories,
            total_tasks=total_tasks,
            total_estimated_hours=total_hours,
            epics=decomposed_epics
        )

        print("\n" + "=" * 60)
        print(f"✅ Decomposition complete!")
        print(f"   📊 {len(decomposed_epics)} Epics → {total_stories} Stories → "
              f"{total_tasks} Sub-tasks")
        print(f"   ⏱️  Total estimated: {total_hours} hours ({total_story_points} story points)")

        return self.decomposed_backlog
    
    def _decompose_epic_intelligent(
        self,
        epic: Dict,
        num_stories: int,
        num_criteria: int,
        epic_effort: int
    ) -> DecomposedEpic:
        """
        Decompose Epic with intelligent task count variation per Story.
        
        Args:
            epic: Epic dictionary from WSJF data
            num_stories: Number of Stories to generate
            num_criteria: Number of Acceptance Criteria per Story
            epic_effort: Epic effort score for task count calculation
            
        Returns:
            DecomposedEpic with varied task counts per Story
        """
        epic_title = epic.get('title', 'Unknown Epic')
        epic_id = epic.get('epic_id', 'unknown')

        logger.info(f"Starting intelligent decomposition for Epic: {epic_title} ({epic_id})")
        print(f"  🔄 Decomposing: {epic_title} ({epic_id})...")

        # Prepare features string
        features = epic.get('mentioned_features', [])
        features_str = ", ".join(features) if features else "No specific features listed"

        # Decompose each Story with varying task counts
        all_stories = []
        task_counter = 1
        
        for story_idx in range(num_stories):
            # Calculate task count for this specific Story
            num_tasks = self._calculate_task_count(story_idx, num_stories, epic_effort)
            
            logger.debug(f"Generating Story {story_idx + 1}/{num_stories} with {num_tasks} tasks")
            
            # Call LLM for this Story with retry logic
            try:
                result = self._call_llm_with_retry(
                    epic_title=epic_title,
                    epic_description=epic.get('description', ''),
                    wsjf_score=epic.get('wsjf_score', 0),
                    priority_rank=epic.get('priority_rank', 0),
                    mentioned_features=features_str,
                    num_stories=1,  # Generate one Story at a time
                    num_criteria=num_criteria,
                    num_tasks=num_tasks,
                )
            except Exception as e:
                logger.error(f"LLM decomposition failed for '{epic_title}' Story {story_idx + 1} after retries: {e}")
                raise Exception(
                    f"LLM decomposition failed for '{epic_title}' Story {story_idx + 1}: {e}"
                )

            # Validate and fix the Story
            stories = result.get('stories', [])
            if stories:
                story = stories[0]
                
                # Fix story ID
                story['story_id'] = f'story_{story_idx + 1:03d}'
                
                # Fix task IDs
                for task in story.get('tasks', []):
                    task['task_id'] = f'task_{task_counter:03d}'
                    task_counter += 1
                
                # Validate and fix
                validated = self._validate_stories([story], epic_title, min_stories=1)
                all_stories.extend(validated)

        # Create DecomposedEpic
        decomposed_epic = DecomposedEpic(
            epic_id=epic_id,
            title=epic_title,
            description=epic.get('description', ''),
            wsjf_score=epic.get('wsjf_score', 0.0),
            priority_rank=epic.get('priority_rank', 0),
            stories=all_stories
        )

        total_tasks = sum(len(s.tasks) for s in decomposed_epic.stories)
        total_hours = sum(
            t.estimated_hours
            for s in decomposed_epic.stories
            for t in s.tasks
        )

        print(f"  ✅ {epic_title}: {len(decomposed_epic.stories)} Stories, "
              f"{total_tasks} Sub-tasks, {total_hours} total hours")

        return decomposed_epic

    def save_decomposed_backlog(self, output_path: str) -> str:
        """
        Save decomposed backlog to JSON file.

        Args:
            output_path: Path to save the JSON file

        Returns:
            Absolute path to the saved file

        Raises:
            ValueError: If no decomposed data exists
        """
        if self.decomposed_backlog is None:
            logger.error("Attempted to save decomposed backlog but no data exists")
            raise ValueError(
                "No decomposed data to save. Run decompose_all_epics() first."
            )

        output_file = Path(output_path)
        output_file.parent.mkdir(parents=True, exist_ok=True)

        # Convert to dict for JSON serialization
        backlog_dict = self.decomposed_backlog.model_dump()

        logger.info(f"Saving decomposed backlog to: {output_file}")
        
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(backlog_dict, f, indent=2, ensure_ascii=False)

        logger.info(f"Successfully saved decomposed backlog: {output_file.absolute()}")
        print(f"💾 Saved decomposed backlog to: {output_file.absolute()}")
        return str(output_file.absolute())

    def get_decomposition_summary(self) -> str:
        """
        Get a quick summary of the decomposition results.

        Returns:
            Formatted string with decomposition summary

        Raises:
            ValueError: If no decomposed data exists
        """
        if self.decomposed_backlog is None:
            raise ValueError(
                "No decomposed data available. Run decompose_all_epics() first."
            )

        summary = [
            "Epic Decomposition Summary:",
            "=" * 50
        ]

        for epic in self.decomposed_backlog.epics:
            total_hours = sum(
                t.estimated_hours for s in epic.stories for t in s.tasks
            )
            summary.append(
                f"  #{epic.priority_rank}. {epic.title} "
                f"(WSJF: {epic.wsjf_score:.2f}) — "
                f"{len(epic.stories)} Stories, {total_hours}h"
            )

        summary.append("")
        summary.append(
            f"Total: {self.decomposed_backlog.total_epics} Epics, "
            f"{self.decomposed_backlog.total_stories} Stories, "
            f"{self.decomposed_backlog.total_tasks} Sub-tasks, "
            f"{self.decomposed_backlog.total_estimated_hours}h"
        )

        return "\n".join(summary)


# ============================================================================
# MAIN EXECUTION
# ============================================================================

def main():
    """Main execution function for testing the Epic Decomposer Agent."""
    import sys
    from dotenv import load_dotenv
    load_dotenv()

    from backend.tools.report_generator import ReportGenerator

    # Paths
    wsjf_data_path = "backend/data/wsjf/2026-04-12_wsjf_scores.json"
    output_json_path = "backend/data/decomposed/2026-04-12_decomposed_backlog.json"
    output_report_path = "backend/data/decomposed/2026-04-12_decomposition_report.md"

    print("=" * 70)
    print("EPIC DECOMPOSER AGENT — Phase 4")
    print("=" * 70)

    try:
        # Initialize agent
        agent = EpicDecomposerAgent()

        # Decompose all Epics with intelligent sizing
        backlog = agent.decompose_all_epics(
            wsjf_data_path=wsjf_data_path,
            use_intelligent_sizing=True  # Use complexity-based sizing
        )

        # Save decomposed backlog
        agent.save_decomposed_backlog(output_json_path)

        # Generate decomposition report
        print("\n" + "=" * 70)
        print("DECOMPOSITION REPORT")
        print("=" * 70)
        report = ReportGenerator.generate_decomposition_report(
            backlog.model_dump()
        )
        print(report)

        # Save report
        report_file = Path(output_report_path)
        report_file.parent.mkdir(parents=True, exist_ok=True)
        with open(report_file, 'w', encoding='utf-8') as f:
            f.write(report)
        print(f"\n💾 Saved report to: {report_file.absolute()}")

        # Print summary
        print("\n" + "=" * 70)
        print("DECOMPOSITION SUMMARY")
        print("=" * 70)
        print(agent.get_decomposition_summary())

        print("\n🎉 Epic decomposition complete!")

    except FileNotFoundError as e:
        print(f"\n❌ Error: {e}")
        sys.exit(1)
    except ValueError as e:
        print(f"\n❌ Error: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
