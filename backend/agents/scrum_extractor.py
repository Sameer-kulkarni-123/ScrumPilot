"""
ScrumExtractorAgent — Uses a LangChain chain (Gemini LLM + PydanticOutputParser)
to parse a diarized meeting transcript into a list of scrum actions.

Compatible with langchain==0.1.x / langchain-core==0.1.x
"""

import os
import json
from typing import List, Optional, Literal, Dict

from pydantic import BaseModel, Field
from langchain_groq import ChatGroq
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import PydanticOutputParser


# ── Structured output schemas ─────────────────────────────────────────────────

class ScrumAction(BaseModel):
    """A single scrum action extracted from the meeting transcript."""

    action: Literal[
        "create_task",
        "complete_task",
        "update_status",
        "assign_task",
        "add_comment",
    ] = Field(description="The type of scrum action.")
    summary: Optional[str] = Field(
        default=None,
        description="Short title of the task as mentioned in the transcript (ticket ID like SP-123)."
    )
    description: Optional[str] = Field(
        default=None,
        description="Longer description of the task, only if the speaker provided one.",
    )
    assignee: Optional[str] = Field(
        default=None,
        description="Name of the person responsible, if mentioned.",
    )
    status: Optional[str] = Field(
        default=None,
        description="Target status for update_status actions (e.g. 'In Progress', 'Done').",
    )
    comment: Optional[str] = Field(
        default=None,
        description="The comment text for add_comment actions.",
    )


class ScrumActionList(BaseModel):
    """The complete list of scrum actions extracted from a meeting."""

    actions: List[ScrumAction] = Field(
        description="All actionable scrum items identified in the transcript."
    )


# ── Agent class ───────────────────────────────────────────────────────────────

class ScrumExtractorAgent:
    """LangChain-powered agent that extracts scrum actions from transcripts."""

    def __init__(self, model_name: str = "llama-3.3-70b-versatile"):
        api_key = os.getenv("GROQ_API_KEY")
        if not api_key:
            raise ValueError(
                "GROQ_API_KEY environment variable is not set. "
                "Get a free key at https://console.groq.com"
            )

        llm = ChatGroq(
            model=model_name,
            groq_api_key=api_key,
            temperature=0,
        )

        # PydanticOutputParser works with all langchain-core versions
        parser = PydanticOutputParser(pydantic_object=ScrumActionList)
        format_instructions = parser.get_format_instructions()

        prompt = ChatPromptTemplate.from_messages([
            (
                "system",
                (
                    "You are a Scrum Action Extractor. You receive the diarized transcript of a "
                    "scrum / standup meeting and identify every actionable scrum item.\n\n"
                    "CRITICAL: NATURAL LANGUAGE MAPPING\n"
                    "People will mention tasks by DESCRIPTION, not by ticket ID.\n"
                    "Examples:\n"
                    "- 'I'm working on the login feature' → Map to Story/Task ID from context\n"
                    "- 'The payment integration is blocked' → Map to Story/Task ID from context\n"
                    "- 'I finished the authentication task' → Map to Story/Task ID from context\n\n"
                    "MAPPING RULES:\n"
                    "- Use the ACTIVE STORIES AND TASKS list provided in context\n"
                    "- Match natural language descriptions to story/task titles\n"
                    "- Match based on keywords and semantic similarity\n"
                    "- If explicit ID mentioned (SP-123), use it directly\n"
                    "- If someone mentions high-level feature → Story ID\n"
                    "- If someone mentions specific implementation → Task ID\n"
                    "- If no match found, extract description as-is\n\n"
                    "ACTION RULES:\n"
                    "- 'complete_task' means the speaker said the task is finished / done.\n"
                    "- 'update_status' means moving a task to a specific non-Done status.\n"
                    "- If someone says 'I'll pick up X' or 'I'm working on X', that is "
                    "'update_status' with status 'In Progress'.\n"
                    "- If someone says 'assign X to Y' or 'Y can take X', that is 'assign_task'.\n"
                    "- Only include optional fields when the speaker explicitly mentioned them.\n\n"
                    "Output format instructions:\n{format_instructions}"
                ),
            ),
            ("human", """Active Stories and Tasks in Sprint:
{context}

Meeting Transcript:
{transcript}

Extract all scrum actions, mapping natural language to story/task IDs:"""),
        ])

        self.chain = prompt | llm | parser
        self._prompt = prompt
        self._parser = parser
        self._format_instructions = format_instructions

    def extract_actions(self, transcript: str, context: Optional[dict] = None) -> List[dict]:
        """
        Send the transcript through the chain and return a list of action dicts.

        Args:
            transcript: The full diarized meeting transcript.
            context: Optional context with active stories and tasks.

        Returns:
            A list of action dicts (serialized from ScrumAction models).
        """
        # Load context from database if not provided
        if not context:
            context = self._load_active_sprint_context()
        
        # Format context for LLM
        context_str = self._format_context(context)
        
        result: ScrumActionList = self.chain.invoke({
            "transcript": transcript,
            "context": context_str,
            "format_instructions": self._format_instructions,
        })
        return [action.model_dump(exclude_none=True) for action in result.actions]
    
    def _load_active_sprint_context(self) -> dict:
        """
        Load active sprint stories and tasks from database.
        
        Returns:
            Dict with active_stories and active_tasks
        """
        from backend.db.connection import get_session
        from backend.db.models import Story, BacklogTask, Sprint, SprintStory
        
        try:
            with get_session() as session:
                # Get active sprint
                active_sprint = session.query(Sprint).filter(
                    Sprint.status == 'active'
                ).first()
                
                if not active_sprint:
                    return {"active_stories": [], "active_tasks": []}
                
                # Get stories in active sprint through sprint_stories table
                sprint_story_ids = session.query(SprintStory.story_id).filter(
                    SprintStory.sprint_id == active_sprint.sprint_id
                ).all()
                
                story_ids = [ss[0] for ss in sprint_story_ids]
                
                stories = session.query(Story).filter(
                    Story.id.in_(story_ids)
                ).all() if story_ids else []
                
                # Get tasks for these stories
                tasks = session.query(BacklogTask).filter(
                    BacklogTask.story_id.in_(story_ids)
                ).all() if story_ids else []
                
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
            print(f"Failed to load active sprint context: {e}")
            return {"active_stories": [], "active_tasks": []}
    
    def _format_context(self, context: dict) -> str:
        """
        Format context for LLM prompt.
        
        Args:
            context: Dict with active_stories and active_tasks
        
        Returns:
            Formatted context string
        """
        context_str = "\n" + "=" * 60 + "\n"
        
        # Add active stories
        if "active_stories" in context and context["active_stories"]:
            stories = context["active_stories"]
            context_str += f"\nACTIVE STORIES ({len(stories)} total):\n"
            
            for story in stories:
                context_str += f"\n- {story.get('story_id', 'N/A')}: {story.get('title', 'N/A')}"
                if story.get('assigned_to'):
                    context_str += f" [Assigned: {story['assigned_to']}]"
                if story.get('status'):
                    context_str += f" [Status: {story['status']}]"
                context_str += "\n"
        else:
            context_str += "\nNo active stories found.\n"
        
        # Add active tasks
        if "active_tasks" in context and context["active_tasks"]:
            tasks = context["active_tasks"]
            context_str += f"\nACTIVE TASKS ({len(tasks)} total):\n"
            
            for task in tasks:
                context_str += f"\n- {task.get('task_id', 'N/A')}: {task.get('title', 'N/A')}"
                if task.get('story_id'):
                    context_str += f" [Story: {task['story_id']}]"
                if task.get('assigned_to'):
                    context_str += f" [Assigned: {task['assigned_to']}]"
                if task.get('status'):
                    context_str += f" [Status: {task['status']}]"
                context_str += "\n"
        else:
            context_str += "\nNo active tasks found.\n"
        
        context_str += "\n" + "=" * 60 + "\n"
        context_str += "\nINSTRUCTIONS:\n"
        context_str += "- Map natural language descriptions to correct Story/Task IDs from the list above\n"
        context_str += "- High-level features → Story IDs\n"
        context_str += "- Specific implementation work → Task IDs\n"
        context_str += "- If explicit ID mentioned (SP-123), use it directly\n"
        context_str += "=" * 60 + "\n"
        
        return context_str


# ── Quick standalone test ─────────────────────────────────────────────────────

if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv()

    here = os.path.dirname(__file__)
    transcript_path = os.path.join(here, "example_transcript.txt")
    with open(transcript_path, "r", encoding="utf-8") as f:
        transcript = f.read()

    agent = ScrumExtractorAgent()
    actions = agent.extract_actions(transcript)
    print(json.dumps(actions, indent=2))
