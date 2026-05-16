"""
ProjectTeamClassifier — LLM-based project and team routing classifier.

Used as the fallback stage in HybridRoutingService when keyword confidence is low.
For high-confidence keyword matches, JiraRoutingResolver handles routing without
ever reaching this agent.

Integrates with:
  - backend/tools/jira_routing.py (HybridRoutingService)
  - backend/agents/jira_creator.py (JiraCreatorAgent)
"""

import logging
import os
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field
from langchain_groq import ChatGroq
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import PydanticOutputParser

from backend.tools.jira_routing import RoutingDecision

logger = logging.getLogger(__name__)


# ── Structured output schemas ─────────────────────────────────────────────────


class ItemRouting(BaseModel):
    """Routing decision for a single work item."""

    project_key: str = Field(
        description="Jira project key (e.g. 'MOBILE', 'BACKEND'). Use the triage key if unsure."
    )
    team_name: str = Field(
        description="Team name within the project (e.g. 'backend', 'frontend', 'devops')."
    )
    component: Optional[str] = Field(
        default=None,
        description="Jira component name matching the team (e.g. 'Backend', 'Frontend').",
    )
    confidence: float = Field(
        description="Confidence score between 0.0 and 1.0.",
        ge=0.0,
        le=1.0,
    )
    decision_reason: str = Field(
        description="Short explanation of why this project/team was chosen."
    )
    is_new_project_candidate: bool = Field(
        default=False,
        description="True if none of the known projects match this item well.",
    )
    suggested_project_name: Optional[str] = Field(
        default=None,
        description="Human-readable name for a new project, if is_new_project_candidate is True.",
    )


class BulkClassification(BaseModel):
    """Classification result for a list of work items."""

    items: List[ItemRouting] = Field(
        description="One routing decision per input item, in the same order."
    )


# ── Agent class ───────────────────────────────────────────────────────────────

_SYSTEM_PROMPT = """You are a Jira routing expert for a software engineering team.
You are given:
1. A list of work items (epics, stories, or action items) each with a summary and description.
2. A list of known Jira projects with their keywords.
3. A list of teams per project with their keywords and component names.
4. (Optional) A snippet of the meeting transcript for additional context.

Your task is to assign each work item to the best matching (project, team) pair.

Rules:
- Prefer deterministic keyword matching. Only use inference when keywords are absent.
- If an item does not clearly fit any known project, set is_new_project_candidate=True and provide a suggested_project_name.
- confidence must reflect how certain you are (0.0 = complete guess, 1.0 = exact keyword match).
- Return exactly one ItemRouting per input item, in the same order.
- Do NOT invent project keys. Only use keys from the known_projects list unless is_new_project_candidate is True.

Known projects:
{known_projects}

Known teams (per project):
{known_teams}

Transcript snippet (may be empty):
{transcript_snippet}
"""

_HUMAN_PROMPT = """Classify each of the following {item_count} work items:

{items_text}

Return a BulkClassification JSON with exactly {item_count} items in the same order.
"""


class ProjectTeamClassifier:
    """
    LLM-powered project and team classifier.

    Intended as the fallback in HybridRoutingService when keyword confidence
    is below the KEYWORD_HIGH_CONFIDENCE threshold.
    """

    def __init__(self, model_name: str = "llama-3.3-70b-versatile"):
        api_key = os.getenv("GROQ_API_KEY")
        if not api_key:
            raise ValueError(
                "GROQ_API_KEY is not set. Get a free key at https://console.groq.com"
            )

        llm = ChatGroq(
            model=model_name,
            groq_api_key=api_key,
            temperature=0,
        )

        self._parser = PydanticOutputParser(pydantic_object=BulkClassification)
        format_instructions = self._parser.get_format_instructions()

        self._prompt = ChatPromptTemplate.from_messages(
            [
                ("system", _SYSTEM_PROMPT + f"\n\n{format_instructions}"),
                ("human", _HUMAN_PROMPT),
            ]
        )

        self._chain = self._prompt | llm | self._parser

    def classify(
        self,
        items: List[Dict[str, str]],
        known_projects: Optional[List[Any]] = None,
        known_teams: Optional[List[Any]] = None,
        transcript_snippet: str = "",
    ) -> BulkClassification:
        """
        Classify a list of items into (project, team) pairs.

        Args:
            items: List of dicts with keys 'summary' and 'description'.
            known_projects: List of ProjectRoutingRule or dict objects.
            known_teams: List of TeamRoutingRule or dict objects (global teams as fallback).
            transcript_snippet: Optional snippet from the meeting transcript.

        Returns:
            BulkClassification with one ItemRouting per input item.
        """
        items_text = "\n".join(
            f"{i + 1}. Summary: {item.get('summary', '')}\n"
            f"   Description: {item.get('description', '')[:200]}"
            for i, item in enumerate(items)
        )

        known_projects_text = self._format_projects(known_projects or [])
        known_teams_text = self._format_teams(known_teams or [])

        result = self._chain.invoke(
            {
                "known_projects": known_projects_text,
                "known_teams": known_teams_text,
                "transcript_snippet": transcript_snippet[:1000] if transcript_snippet else "N/A",
                "item_count": len(items),
                "items_text": items_text,
            }
        )
        return result

    def classify_single(
        self,
        summary: str,
        description: str = "",
        transcript_snippet: str = "",
        known_projects: Optional[List[Any]] = None,
        known_teams: Optional[List[Any]] = None,
    ) -> Optional[RoutingDecision]:
        """
        Classify a single item and return a RoutingDecision.

        Returns None if classification fails, allowing callers to fall back
        to triage routing.
        """
        try:
            result = self.classify(
                items=[{"summary": summary, "description": description}],
                known_projects=known_projects,
                known_teams=known_teams,
                transcript_snippet=transcript_snippet,
            )

            if not result.items:
                return None

            item = result.items[0]
            config = self._get_resolver_config(known_projects)

            return RoutingDecision(
                project_key=item.project_key,
                project_name=item.suggested_project_name or item.project_key,
                component=item.component,
                matched_project=not item.is_new_project_candidate,
                matched_team=item.team_name is not None,
                is_triage=item.confidence < 0.40,
                team_name=item.team_name,
                confidence=item.confidence,
                decision_reason=f"llm:{item.decision_reason[:80]}",
                is_new_project_candidate=item.is_new_project_candidate,
                suggested_project_name=item.suggested_project_name,
            )
        except Exception as e:
            logger.warning(f"LLM classifier failed, will fall back to triage: {e}")
            return None

    @staticmethod
    def _format_projects(projects: List[Any]) -> str:
        if not projects:
            return "No projects defined."
        lines = []
        for p in projects:
            key = getattr(p, "key", None) or p.get("key", "?")
            name = getattr(p, "name", None) or p.get("name", key)
            keywords = getattr(p, "keywords", None) or p.get("keywords", [])
            lines.append(f"  - {key} ({name}): keywords={keywords}")
        return "\n".join(lines)

    @staticmethod
    def _format_teams(teams: List[Any]) -> str:
        if not teams:
            return "No teams defined."
        lines = []
        for t in teams:
            name = getattr(t, "name", None) or t.get("name", "?")
            component = getattr(t, "component", None) or t.get("component", "")
            keywords = getattr(t, "keywords", None) or t.get("keywords", [])
            lines.append(f"  - {name} (component={component}): keywords={keywords}")
        return "\n".join(lines)

    @staticmethod
    def _get_resolver_config(known_projects: Optional[List[Any]]) -> Any:
        return known_projects
