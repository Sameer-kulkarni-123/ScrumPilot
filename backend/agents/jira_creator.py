"""
Jira Creator Agent - Phase 5

Creates Epics, Stories, and Sub-tasks in Jira from decomposed backlog.
Maintains parent-child relationships and includes WSJF data, story points,
and all metadata from Phase 4.

This agent handles Workflow 1 (PM Meetings) - creating new backlog items.
For Workflow 2 (Scrum Meetings) - updating existing items, see jira_agent.py.

Author: AI Meeting Automation System
Phase: 5
"""

import os
import json
import logging
from pathlib import Path
from typing import Dict, List, Optional
from datetime import datetime

from pydantic import BaseModel, Field
from backend.tools.jira_client import JiraManager
from backend.tools.jira_routing import load_jira_routing_config, JiraRoutingResolver, RoutingDecision

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


# ============================================================================
# PYDANTIC MODELS FOR JIRA RESULTS
# ============================================================================

class JiraTask(BaseModel):
    """Jira Sub-task creation result."""
    task_id: str
    jira_key: Optional[str] = None
    title: str
    estimated_hours: int
    story_points: Optional[int] = None
    success: bool = False
    error: Optional[str] = None


class JiraStory(BaseModel):
    """Jira Story creation result."""
    story_id: str
    jira_key: Optional[str] = None
    title: str
    story_points: Optional[int] = None
    tasks: List[JiraTask] = Field(default_factory=list)
    success: bool = False
    error: Optional[str] = None


class JiraEpic(BaseModel):
    """Jira Epic creation result."""
    epic_id: str
    jira_key: Optional[str] = None
    title: str
    wsjf_score: float
    priority_rank: int
    stories: List[JiraStory] = Field(default_factory=list)
    success: bool = False
    error: Optional[str] = None


class JiraCreationResult(BaseModel):
    """Complete Jira creation result."""
    creation_date: str
    total_epics: int = 0
    total_stories: int = 0
    total_tasks: int = 0
    epics_created: int = 0
    stories_created: int = 0
    tasks_created: int = 0
    epics: List[JiraEpic] = Field(default_factory=list)
    errors: List[str] = Field(default_factory=list)
    
    # Idempotency: Track mapping of internal IDs to Jira keys
    id_mapping: Dict[str, str] = Field(default_factory=dict)
    # Example: {"epic_001": "SP-97", "story_001_01": "SP-98", "task_001_01_01": "SP-99"}

    # Routing decisions keyed by epic_id for downstream DB persistence
    routing_decisions: Dict[str, Dict] = Field(default_factory=dict)
    # Example: {"epic_001": {"project_key": "MOBILE", "team_name": "backend", ...}}
    
    last_updated: str = Field(default="")
    resume_point: Optional[str] = None


# ============================================================================
# JIRA CREATOR AGENT
# ============================================================================

class JiraCreatorAgent:
    """
    Agent to create Epics, Stories, and Sub-tasks in Jira from decomposed backlog.
    
    Responsibilities:
    - Load decomposed backlog from Phase 4
    - Create Epics in Jira with WSJF data
    - Create Stories linked to Epics
    - Create Sub-tasks linked to Stories
    - Maintain parent-child relationships
    - Track creation results and errors
    - Generate Jira creation report
    """

    def __init__(self):
        """Initialize the Jira Creator Agent."""
        logger.info("Initializing JiraCreatorAgent")
        
        try:
            self.jira = JiraManager()
            logger.info(f"Connected to Jira: {self.jira.url}")
            logger.info(f"Project: {self.jira.project_key}")
        except Exception as e:
            logger.error(f"Failed to initialize Jira client: {e}")
            raise

        # ── Load optional keyword-hint config (jira_routing.json) ────────────
        self.routing_resolver: Optional[JiraRoutingResolver] = None
        _hint_projects: list = []
        try:
            routing_config = load_jira_routing_config()
            if routing_config:
                self.routing_resolver = JiraRoutingResolver(routing_config)
                _hint_projects = [
                    {"key": p.key, "name": p.name}
                    for p in routing_config.projects
                ]
                logger.info(
                    f"jira_routing.json loaded — {len(_hint_projects)} project hint(s)"
                )
        except Exception as e:
            logger.warning(f"jira_routing.json not loaded (optional): {e}")

        # ── Fetch live Jira projects + auto-seed DB registry ─────────────────
        # None  = Jira API call failed  → optimistic (skip guard)
        # set() = Jira has no projects  → all routing is new-project
        self._live_jira_keys: Optional[set] = None
        self._live_jira_projects: list = []   # [{"key": ..., "name": ...}]
        try:
            raw = self.jira.client.projects()
            self._live_jira_projects = [{"key": p.key, "name": p.name} for p in raw]
            self._live_jira_keys     = {p["key"] for p in self._live_jira_projects}
            logger.info(
                f"Live Jira projects: {self._live_jira_keys or '(none)'}"
            )
            # Auto-seed DB registry so existing Jira projects are always known
            self._seed_registry_from_jira(self._live_jira_projects)
        except Exception as _e:
            logger.warning(f"Could not fetch live Jira project list: {_e}")

        # ── Build LLM-based project router (domain-agnostic) ─────────────────
        self._llm_router = None
        try:
            from backend.tools.llm_project_router import LLMProjectRouter
            self._llm_router = LLMProjectRouter(
                live_projects=self._live_jira_projects,
                hint_projects=_hint_projects,
            )
            logger.info(
                f"LLM project router ready — "
                f"{len(self._live_jira_projects)} live project(s), "
                f"{len(_hint_projects)} hint(s)"
            )
        except Exception as _e:
            logger.warning(f"LLM project router not available: {_e}")

        self.decomposed_backlog: Optional[Dict] = None
        self.creation_result: Optional[JiraCreationResult] = None
        self.mapping_file: Optional[Path] = None  # For idempotency
        
        # Duplicate detection configuration
        self.check_duplicates = True
        self.duplicate_threshold = 0.85  # 85% similarity = duplicate
        self.duplicate_action = "skip"  # warn, skip, or error
        # "skip" = Use existing epic instead of creating duplicate
        # "warn" = Create anyway but show warning
        # "error" = Stop execution if duplicate found

    def load_decomposed_backlog(self, backlog_path: str) -> Dict:
        """
        Load decomposed backlog from Phase 4 JSON file.

        Args:
            backlog_path: Path to decomposed backlog JSON

        Returns:
            Decomposed backlog dictionary

        Raises:
            FileNotFoundError: If backlog file doesn't exist
            json.JSONDecodeError: If JSON is invalid
        """
        logger.info(f"Loading decomposed backlog from: {backlog_path}")
        
        backlog_file = Path(backlog_path)
        if not backlog_file.exists():
            logger.error(f"Decomposed backlog not found: {backlog_path}")
            raise FileNotFoundError(
                f"Decomposed backlog not found: {backlog_path}\n"
                f"Please run Epic Decomposition (Phase 4) first."
            )

        with open(backlog_file, 'r', encoding='utf-8') as f:
            self.decomposed_backlog = json.load(f)

        epics_count = len(self.decomposed_backlog.get('epics', []))
        logger.info(f"Successfully loaded {epics_count} Epic(s) from decomposed backlog")
        
        print(f"Loaded decomposed backlog: {epics_count} Epic(s)")
        return self.decomposed_backlog

    def load_existing_mapping(self, mapping_path: Path) -> Dict[str, str]:
        """
        Load existing ID mapping from previous run to enable resume.
        
        Args:
            mapping_path: Path to mapping JSON file
        
        Returns:
            Dictionary mapping internal IDs to Jira keys
        """
        if not mapping_path.exists():
            logger.info("No existing mapping found, starting fresh")
            return {}
        
        try:
            with open(mapping_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                mapping = data.get('id_mapping', {})
            
            logger.info(f"Loaded existing mapping: {len(mapping)} items already created")
            print(f"Resuming from previous run ({len(mapping)} items already created)")
            
            return mapping
        
        except Exception as e:
            logger.warning(f"Failed to load mapping: {e}")
            return {}
    
    def save_mapping(self):
        """
        Save ID mapping after each item for crash recovery.
        
        This enables idempotency - if the script crashes, we can resume
        without creating duplicates.
        """
        if not self.mapping_file or not self.creation_result:
            return
        
        try:
            with open(self.mapping_file, 'w', encoding='utf-8') as f:
                json.dump({
                    'id_mapping': self.creation_result.id_mapping,
                    'last_updated': datetime.now().isoformat(),
                    'resume_point': self.creation_result.resume_point
                }, f, indent=2, ensure_ascii=False)
            
            logger.debug(f"Saved mapping: {len(self.creation_result.id_mapping)} items")
        
        except Exception as e:
            logger.warning(f"Failed to save mapping: {e}")

    def _seed_registry_from_jira(self, live_projects: list) -> None:
        """
        Register any Jira project not yet in the local DB registry.
        Runs once at startup so the registry always reflects reality.
        """
        if not live_projects:
            return
        try:
            from backend.db.connection import get_session
            from backend.db.models import JiraProjectRegistry
            with get_session() as session:
                for proj in live_projects:
                    key  = proj["key"]
                    name = proj["name"]
                    existing = session.query(JiraProjectRegistry).filter(
                        JiraProjectRegistry.project_key == key
                    ).first()
                    if not existing:
                        session.add(JiraProjectRegistry(
                            project_key=key,
                            name=name,
                            keywords=[],
                            status="active",
                            auto_created=False,
                            registry_metadata={},
                        ))
                        logger.info(f"Auto-registered Jira project '{key}' in DB registry")
                    elif existing.status != "active":
                        existing.status = "active"
                session.commit()
        except Exception as _e:
            logger.warning(f"Could not seed DB registry from Jira: {_e}")

    def resolve_routing(self, summary: str, description: str = "") -> RoutingDecision:
        """
        Resolve project routing using LLM (domain-agnostic).
        Falls back to keyword matching (jira_routing.json) if LLM unavailable.
        """
        # 1. LLM router — primary, domain-agnostic
        if self._llm_router is not None:
            try:
                return self._llm_router.route(summary, description)
            except Exception as _e:
                logger.warning(f"LLM routing failed for '{summary}': {_e}; falling back")

        # 2. Keyword resolver — fallback (requires jira_routing.json)
        if self.routing_resolver:
            return self.routing_resolver.resolve(summary, description)

        # 3. Last resort
        return RoutingDecision(
            project_key=self.jira.project_key or "",
            project_name=self.jira.project_key or "",
            component=None,
            matched_project=False,
            matched_team=False,
            is_triage=False,
        )

    def create_epic_in_jira(self, epic: Dict, project_key: Optional[str] = None, component: Optional[str] = None) -> JiraEpic:
        """
        Create an Epic in Jira with WSJF data.
        
        Features:
        - Idempotency: Checks if already created
        - Duplicate detection: Warns about similar Epics
        - Automatic retry on transient failures

        Args:
            epic: Epic dictionary from decomposed backlog

        Returns:
            JiraEpic with creation result
        """
        epic_id = epic.get('epic_id', 'unknown')
        epic_title = epic.get('title', 'Untitled Epic')
        
        # ═══════════════════════════════════════════════════════════════════
        # IDEMPOTENCY CHECK: Skip if already created (with Jira verification)
        # ═══════════════════════════════════════════════════════════════════
        if epic_id in self.creation_result.id_mapping:
            existing_key = self.creation_result.id_mapping[epic_id]
            
            # IMPORTANT: Verify ticket actually exists in Jira
            from backend.db.crud import verify_jira_ticket_exists
            
            if verify_jira_ticket_exists(existing_key):
                logger.info(f"Epic {epic_id} already created as {existing_key} (verified in Jira), skipping")
                print(f"    Epic already exists: {existing_key} ✅")
                
                return JiraEpic(
                    epic_id=epic_id,
                    jira_key=existing_key,
                    title=epic_title,
                    wsjf_score=epic.get('wsjf_score', 0.0),
                    priority_rank=epic.get('priority_rank', 0),
                    success=True
                )
            else:
                logger.warning(
                    f"Epic {epic_id} was mapped to {existing_key}, "
                    f"but ticket no longer exists in Jira. Will recreate."
                )
                print(f"    Epic {existing_key} not found in Jira, recreating...")
                # Remove from mapping and continue with creation
                del self.creation_result.id_mapping[epic_id]
        
        logger.info(f"Creating Epic in Jira: {epic_title} ({epic_id})")
        print(f"  Creating Epic: {epic_title}")
        
        # ═══════════════════════════════════════════════════════════════════
        # DUPLICATE DETECTION: Check for similar Epics
        # ═══════════════════════════════════════════════════════════════════
        if self.check_duplicates:
            similar = self.jira.find_similar_issues(
                epic_title,
                issue_type="Epic",
                similarity_threshold=self.duplicate_threshold
            )
            
            if similar:
                print(f"    WARNING: Found {len(similar)} similar Epic(s):")
                for s in similar[:3]:  # Show top 3
                    print(f"       {s['key']}: {s['summary']}")
                    print(f"       Similarity: {s['similarity']:.0%} | Status: {s['status']}")
                
                if self.duplicate_action == "error":
                    error_msg = f"Duplicate detected: {similar[0]['key']}"
                    logger.error(error_msg)
                    return JiraEpic(
                        epic_id=epic_id,
                        title=epic_title,
                        wsjf_score=epic.get('wsjf_score', 0.0),
                        priority_rank=epic.get('priority_rank', 0),
                        success=False,
                        error=error_msg
                    )
                elif self.duplicate_action == "skip":
                    # Use existing Epic
                    existing_key = similar[0]['key']
                    print(f"    Using existing Epic: {existing_key}")
                    
                    # Save mapping
                    self.creation_result.id_mapping[epic_id] = existing_key
                    self.save_mapping()
                    
                    return JiraEpic(
                        epic_id=epic_id,
                        jira_key=existing_key,
                        title=epic_title,
                        wsjf_score=epic.get('wsjf_score', 0.0),
                        priority_rank=epic.get('priority_rank', 0),
                        success=True
                    )
                # else: "warn" - just log and continue

        # Build Epic description with WSJF data
        wsjf_score = epic.get('wsjf_score', 0.0)
        priority_rank = epic.get('priority_rank', 0)
        description = epic.get('description', '')

        epic_description = f"""**WSJF Score**: {wsjf_score:.2f} (Priority #{priority_rank})

**Description**:
{description}

---
*Created by ScrumPilot - AI Meeting Automation System*
*Epic ID*: {epic_id}
"""

        # Create Epic in Jira using extended JiraManager
        try:
            result = self.jira.create_epic(
                summary=epic_title,
                description=epic_description,
                epic_name=epic_title[:50],  # Short name for Epic
                project_key=project_key,
                component=component,
            )

            if result.get('success'):
                jira_key = result.get('key')
                
                # ═══════════════════════════════════════════════════════════
                # SAVE MAPPING IMMEDIATELY for idempotency
                # ═══════════════════════════════════════════════════════════
                self.creation_result.id_mapping[epic_id] = jira_key
                self.save_mapping()
                
                logger.info(f"Epic created successfully: {jira_key}")
                print(f"    Epic created: {jira_key}")
                
                return JiraEpic(
                    epic_id=epic_id,
                    jira_key=jira_key,
                    title=epic_title,
                    wsjf_score=wsjf_score,
                    priority_rank=priority_rank,
                    success=True
                )
            else:
                error_msg = result.get('error', 'Unknown error')
                logger.error(f"Failed to create Epic '{epic_title}': {error_msg}")
                print(f"    Failed to create Epic: {error_msg}")
                
                return JiraEpic(
                    epic_id=epic_id,
                    title=epic_title,
                    wsjf_score=wsjf_score,
                    priority_rank=priority_rank,
                    success=False,
                    error=error_msg
                )

        except Exception as e:
            logger.error(f"Exception creating Epic '{epic_title}': {e}")
            print(f"    Exception: {e}")
            
            return JiraEpic(
                epic_id=epic_id,
                title=epic_title,
                wsjf_score=wsjf_score,
                priority_rank=priority_rank,
                success=False,
                error=str(e)
            )

    def create_story_in_jira(self, story: Dict, epic_key: str, project_key: Optional[str] = None, component: Optional[str] = None) -> JiraStory:
        """
        Create a Story in Jira linked to an Epic.
        
        Features:
        - Idempotency: Checks if already created
        - Automatic retry on transient failures

        Args:
            story: Story dictionary from decomposed backlog
            epic_key: Jira key of the parent Epic

        Returns:
            JiraStory with creation result
        """
        story_id = story.get('story_id', 'unknown')
        story_title = story.get('title', 'Untitled Story')
        mapping_key = f"{epic_key}:{story_id}"
        
        # ═══════════════════════════════════════════════════════════════════
        # IDEMPOTENCY CHECK: Skip if already created (with Jira verification)
        # ═══════════════════════════════════════════════════════════════════
        if mapping_key in self.creation_result.id_mapping:
            existing_key = self.creation_result.id_mapping[mapping_key]
            
            # IMPORTANT: Verify ticket actually exists in Jira
            from backend.db.crud import verify_jira_ticket_exists
            
            if verify_jira_ticket_exists(existing_key):
                logger.debug(f"Story {story_id} already created as {existing_key} (verified in Jira), skipping")
                print(f"      Story already exists: {existing_key} ✅")
                
                return JiraStory(
                    story_id=story_id,
                    jira_key=existing_key,
                    title=story_title,
                    story_points=story.get('story_points'),
                    success=True
                )
            else:
                logger.warning(
                    f"Story {story_id} was mapped to {existing_key}, "
                    f"but ticket no longer exists in Jira. Will recreate."
                )
                print(f"      Story {existing_key} not found in Jira, recreating...")
                # Remove from mapping and continue with creation
                del self.creation_result.id_mapping[mapping_key]
        
        logger.debug(f"Creating Story in Jira: {story_title} ({story_id})")
        print(f"    Creating Story: {story_title[:60]}...")

        # Build Story description with acceptance criteria
        description = story.get('description', '')
        acceptance_criteria = story.get('acceptance_criteria', [])
        story_points = story.get('story_points')

        story_description = f"""**Description**:
{description}

**Acceptance Criteria**:
"""
        for i, criterion in enumerate(acceptance_criteria, 1):
            story_description += f"{i}. {criterion}\n"

        if story_points:
            story_description += f"\n**Story Points**: {story_points}\n"

        story_description += f"""
---
*Created by ScrumPilot*
*Story ID*: {story_id}
*Epic*: {epic_key}
"""

        # Create Story in Jira with Epic link
        try:
            result = self.jira.create_ticket(
                summary=story_title,
                description=story_description,
                issue_type="Story",
                epic_link=epic_key,
                project_key=project_key,
                component=component,
            )

            if result.get('success'):
                jira_key = result.get('key')
                
                # ═══════════════════════════════════════════════════════════
                # SAVE MAPPING IMMEDIATELY for idempotency
                # ═══════════════════════════════════════════════════════════
                self.creation_result.id_mapping[mapping_key] = jira_key
                self.save_mapping()
                
                logger.debug(f"Story created successfully: {jira_key}")
                print(f"      Story created: {jira_key}")
                
                return JiraStory(
                    story_id=story_id,
                    jira_key=jira_key,
                    title=story_title,
                    story_points=story_points,
                    success=True
                )
            else:
                error_msg = result.get('error', 'Unknown error')
                logger.error(f"Failed to create Story '{story_title}': {error_msg}")
                print(f"      Failed to create Story: {error_msg}")
                
                return JiraStory(
                    story_id=story_id,
                    title=story_title,
                    story_points=story_points,
                    success=False,
                    error=error_msg
                )

        except Exception as e:
            logger.error(f"Exception creating Story '{story_title}': {e}")
            print(f"      Exception: {e}")
            
            return JiraStory(
                story_id=story_id,
                title=story_title,
                story_points=story_points,
                success=False,
                error=str(e)
            )

    def create_task_in_jira(self, task: Dict, story_key: str, project_key: Optional[str] = None, component: Optional[str] = None) -> JiraTask:
        """
        Create a Sub-task in Jira linked to a Story.
        
        Features:
        - Idempotency: Checks if already created
        - Automatic retry on transient failures

        Args:
            task: Task dictionary from decomposed backlog
            story_key: Jira key of the parent Story

        Returns:
            JiraTask with creation result
        """
        task_id = task.get('task_id', 'unknown')
        task_title = task.get('title', 'Untitled Task')
        mapping_key = f"{story_key}:{task_id}"
        
        # ═══════════════════════════════════════════════════════════════════
        # IDEMPOTENCY CHECK: Skip if already created (with Jira verification)
        # ═══════════════════════════════════════════════════════════════════
        if mapping_key in self.creation_result.id_mapping:
            existing_key = self.creation_result.id_mapping[mapping_key]
            
            # IMPORTANT: Verify ticket actually exists in Jira
            from backend.db.crud import verify_jira_ticket_exists
            
            if verify_jira_ticket_exists(existing_key):
                logger.debug(f"Task {task_id} already created as {existing_key} (verified in Jira), skipping")
                print(f"          Task already exists: {existing_key} ✅")
                
                return JiraTask(
                    task_id=task_id,
                    jira_key=existing_key,
                    title=task_title,
                    estimated_hours=task.get('estimated_hours', 0),
                    story_points=task.get('story_points'),
                    success=True
                )
            else:
                logger.warning(
                    f"Task {task_id} was mapped to {existing_key}, "
                    f"but ticket no longer exists in Jira. Will recreate."
                )
                print(f"          Task {existing_key} not found in Jira, recreating...")
                # Remove from mapping and continue with creation
                del self.creation_result.id_mapping[mapping_key]
        
        logger.debug(f"Creating Sub-task in Jira: {task_title} ({task_id})")
        print(f"        Creating Sub-task: {task_title[:50]}...")

        # Build Task description
        description = task.get('description', '')
        estimated_hours = task.get('estimated_hours', 0)
        story_points = task.get('story_points')

        task_description = f"""**Description**:
{description}

**Estimated Hours**: {estimated_hours}h
"""
        if story_points:
            task_description += f"**Story Points**: {story_points}\n"

        task_description += f"""
---
*Created by ScrumPilot*
*Task ID*: {task_id}
*Parent Story*: {story_key}
"""

        # Create Task in Jira with parent link
        # Note: Using "Task" instead of "Sub-task" because some Jira projects
        # don't have Sub-task configured. We still link it to the parent Story.
        try:
            result = self.jira.create_ticket(
                summary=task_title,
                description=task_description,
                issue_type="Subtask",  # Subtasks are children of Stories (hierarchy level -1)
                parent_key=story_key,
                project_key=project_key,
                component=component,
            )

            if result.get('success'):
                jira_key = result.get('key')
                
                # ═══════════════════════════════════════════════════════════
                # SAVE MAPPING IMMEDIATELY for idempotency
                # ═══════════════════════════════════════════════════════════
                self.creation_result.id_mapping[mapping_key] = jira_key
                self.save_mapping()
                
                logger.debug(f"Task created successfully: {jira_key}")
                print(f"          Task created: {jira_key}")
                
                return JiraTask(
                    task_id=task_id,
                    jira_key=jira_key,
                    title=task_title,
                    estimated_hours=estimated_hours,
                    story_points=story_points,
                    success=True
                )
            else:
                error_msg = result.get('error', 'Unknown error')
                logger.error(f"Failed to create Task '{task_title}': {error_msg}")
                print(f"          Failed to create Task: {error_msg}")
                
                return JiraTask(
                    task_id=task_id,
                    title=task_title,
                    estimated_hours=estimated_hours,
                    story_points=story_points,
                    success=False,
                    error=error_msg
                )

        except Exception as e:
            logger.error(f"Exception creating Task '{task_title}': {e}")
            print(f"          Exception: {e}")
            
            return JiraTask(
                task_id=task_id,
                title=task_title,
                estimated_hours=estimated_hours,
                story_points=story_points,
                success=False,
                error=str(e)
            )

    def create_backlog_in_jira(
        self,
        backlog_path: str,
        dry_run: bool = False,
        resume: bool = True,
        forced_project_key: Optional[str] = None,
    ) -> JiraCreationResult:
        """
        Create complete backlog in Jira from decomposed backlog file.
        
        Features:
        - Idempotency: Can safely re-run after failures
        - Duplicate detection: Warns about similar items
        - Rate limiting: Respects Jira API limits
        - Automatic retry: Handles transient failures

        Args:
            backlog_path: Path to decomposed backlog JSON
            dry_run: If True, simulate creation without actually creating in Jira
            resume: If True, resume from previous run using saved mapping
            forced_project_key: Jira project key selected by the PM. When set,
                all backlog items are created in that Scrum project.

        Returns:
            JiraCreationResult with all creation results

        Raises:
            FileNotFoundError: If backlog file doesn't exist
        """
        logger.info(f"Starting Jira backlog creation (dry_run={dry_run}, resume={resume})")
        print("\n" + "=" * 70)
        print("JIRA BACKLOG CREATION - Phase 5 (Enhanced)")
        print("=" * 70)

        if dry_run:
            print("DRY RUN MODE - No actual Jira creation")
            print("=" * 70)

        # Load decomposed backlog
        self.load_decomposed_backlog(backlog_path)

        epics_data = self.decomposed_backlog.get('epics', [])
        
        # Initialize result
        self.creation_result = JiraCreationResult(
            creation_date=datetime.now().strftime('%Y-%m-%d'),
            total_epics=len(epics_data),
            total_stories=sum(len(e.get('stories', [])) for e in epics_data),
            total_tasks=sum(
                len(t.get('tasks', []))
                for e in epics_data
                for t in e.get('stories', [])
            )
        )
        
        # ═══════════════════════════════════════════════════════════════════
        # IDEMPOTENCY: Setup mapping file and load existing mapping
        # ═══════════════════════════════════════════════════════════════════
        self.mapping_file = Path(backlog_path).parent / (Path(backlog_path).stem + '_mapping.json')
        
        if resume:
            existing_mapping = self.load_existing_mapping(self.mapping_file)
            self.creation_result.id_mapping = existing_mapping

        print(f"\nTotal to create: {self.creation_result.total_epics} Epics, "
              f"{self.creation_result.total_stories} Stories, "
              f"{self.creation_result.total_tasks} Sub-tasks\n")

        # Create each Epic with its Stories and Tasks
        for epic_data in epics_data:
            epic_id = epic_data.get('epic_id', '')
            epic_title = epic_data.get('title', '')
            epic_description_text = epic_data.get('description', '')

            if dry_run:
                routing = self.resolve_routing(epic_title, epic_description_text)
                if forced_project_key:
                    routing = routing.model_copy(
                        update={
                            "project_key": forced_project_key,
                            "project_name": forced_project_key,
                            "component": None,
                            "matched_project": True,
                            "matched_team": False,
                            "is_triage": False,
                            "decision_reason": "pm_selected_project",
                        }
                    )
                print(
                    f"  [DRY RUN] Would create Epic: {epic_title} "
                    f"→ project={routing.project_key}, component={routing.component}"
                )
                continue

            # Resolve routing for this epic (stories and tasks inherit same project/component)
            routing = self.resolve_routing(epic_title, epic_description_text)
            epic_project_key = routing.project_key or None
            epic_component = routing.component or None
            if forced_project_key:
                epic_project_key = forced_project_key
                epic_component = None

            if routing.is_triage:
                logger.warning(
                    f"Epic '{epic_title}' routed to triage project '{routing.project_key}' "
                    f"— no keyword match found"
                )

            # ── Live-Jira guard: skip epics whose target project doesn't exist ──
            # Checks two sources:
            #   1. DB registry  — project known to the system
            #   2. Live Jira    — project actually exists in Jira right now
            # If either check fails, skip this epic (a project_creation approval
            # was (or will be) sent to the PM via the preflight check).
            if epic_project_key:
                project_exists_in_jira = (
                    self._live_jira_keys is None          # unknown → optimistic
                    or epic_project_key in self._live_jira_keys
                )
                if not project_exists_in_jira:
                    logger.warning(
                        f"Skipping '{epic_title}': project '{epic_project_key}' "
                        f"does not exist in Jira — awaiting project_creation approval"
                    )
                    self.creation_result.errors.append(
                        f"Epic '{epic_title}': project '{epic_project_key}' not in Jira "
                        f"(pending project_creation approval)"
                    )
                    continue

            logger.info(
                f"Routing epic '{epic_title}' → project={routing.project_key}, "
                f"component={routing.component}, matched={routing.matched_project}"
            )

            # Store routing decision for downstream DB persistence
            self.creation_result.routing_decisions[epic_id] = {
                "project_key": routing.project_key,
                "team_name": routing.team_name,
                "component": routing.component,
                "confidence": round(routing.confidence, 3),
                "source": (routing.decision_reason or "keyword_match")[:20],
            }
            if forced_project_key:
                self.creation_result.routing_decisions[epic_id] = {
                    "project_key": forced_project_key,
                    "team_name": None,
                    "component": None,
                    "confidence": 1.0,
                    "source": "pm_selected_project",
                }

            # Create Epic
            epic_result = self.create_epic_in_jira(
                epic_data,
                project_key=epic_project_key,
                component=epic_component,
            )
            
            if epic_result.success:
                self.creation_result.epics_created += 1
                
                # Create Stories for this Epic (inherit routing from epic)
                for story_data in epic_data.get('stories', []):
                    story_result = self.create_story_in_jira(
                        story_data,
                        epic_result.jira_key,
                        project_key=epic_project_key,
                        component=epic_component,
                    )
                    
                    if story_result.success:
                        self.creation_result.stories_created += 1
                        
                        # Create Tasks for this Story (inherit routing from epic)
                        for task_data in story_data.get('tasks', []):
                            task_result = self.create_task_in_jira(
                                task_data,
                                story_result.jira_key,
                                project_key=epic_project_key,
                                component=epic_component,
                            )
                            
                            if task_result.success:
                                self.creation_result.tasks_created += 1
                            else:
                                self.creation_result.errors.append(
                                    f"Task '{task_data.get('title')}': {task_result.error}"
                                )
                            
                            story_result.tasks.append(task_result)
                    else:
                        self.creation_result.errors.append(
                            f"Story '{story_data.get('title')}': {story_result.error}"
                        )
                    
                    epic_result.stories.append(story_result)
            else:
                self.creation_result.errors.append(
                    f"Epic '{epic_data.get('title')}': {epic_result.error}"
                )
            
            self.creation_result.epics.append(epic_result)

        # Print summary
        print("\n" + "=" * 70)
        print("CREATION SUMMARY")
        print("=" * 70)
        print(f"Epics created: {self.creation_result.epics_created}/{self.creation_result.total_epics}")
        print(f"Stories created: {self.creation_result.stories_created}/{self.creation_result.total_stories}")
        print(f"Sub-tasks created: {self.creation_result.tasks_created}/{self.creation_result.total_tasks}")
        
        if self.creation_result.errors:
            print(f"\nErrors encountered: {len(self.creation_result.errors)}")
            for error in self.creation_result.errors[:5]:  # Show first 5 errors
                print(f"  - {error}")
            if len(self.creation_result.errors) > 5:
                print(f"  ... and {len(self.creation_result.errors) - 5} more")
        else:
            print("\nAll items created successfully!")

        logger.info(f"Jira creation complete: {self.creation_result.epics_created} Epics, "
                   f"{self.creation_result.stories_created} Stories, "
                   f"{self.creation_result.tasks_created} Sub-tasks")

        return self.creation_result

    def save_creation_result(self, output_path: str) -> str:
        """
        Save Jira creation result to JSON file.

        Args:
            output_path: Path to save the JSON file

        Returns:
            Absolute path to the saved file

        Raises:
            ValueError: If no creation result exists
        """
        if self.creation_result is None:
            logger.error("No creation result to save")
            raise ValueError(
                "No creation result to save. Run create_backlog_in_jira() first."
            )

        output_file = Path(output_path)
        output_file.parent.mkdir(parents=True, exist_ok=True)

        logger.info(f"Saving creation result to: {output_file}")

        # Convert to dict for JSON serialization
        result_dict = self.creation_result.model_dump()

        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(result_dict, f, indent=2, ensure_ascii=False)

        logger.info(f"Successfully saved creation result: {output_file.absolute()}")
        print(f"\nSaved creation result to: {output_file.absolute()}")
        
        return str(output_file.absolute())


# ============================================================================
# MAIN EXECUTION
# ============================================================================

def main():
    """Main execution function for testing the Jira Creator Agent."""
    import sys
    from dotenv import load_dotenv
    load_dotenv()

    from backend.tools.report_generator import ReportGenerator

    # Paths
    backlog_path = "backend/data/decomposed/2026-04-12_decomposed_backlog.json"
    output_json_path = "backend/data/jira/2026-04-12_jira_creation.json"
    output_report_path = "backend/data/jira/2026-04-12_jira_report.md"

    try:
        # Initialize agent
        agent = JiraCreatorAgent()

        # Create backlog in Jira
        result = agent.create_backlog_in_jira(
            backlog_path=backlog_path,
            dry_run=False  # Set to True to test without creating
        )

        # Save result
        agent.save_creation_result(output_json_path)

        # Generate report
        print("\n" + "=" * 70)
        print("JIRA CREATION REPORT")
        print("=" * 70)
        report = ReportGenerator.generate_jira_report(result.model_dump())
        print(report)

        # Save report
        report_file = Path(output_report_path)
        report_file.parent.mkdir(parents=True, exist_ok=True)
        with open(report_file, 'w', encoding='utf-8') as f:
            f.write(report)
        print(f"\nSaved report to: {report_file.absolute()}")

        print("\nJira backlog creation complete!")

    except FileNotFoundError as e:
        print(f"\nError: {e}")
        sys.exit(1)
    except ValueError as e:
        print(f"\nError: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"\nUnexpected error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
