"""
LLM-Based Project Router

Replaces keyword-matching with an LLM that reads the epic content and the
list of *actual* Jira projects that exist (or are configured) and decides:

  1. Which existing project the epic belongs to  (confidence ≥ 0.5)
  2. OR — it's a new project → suggests key + name from transcript context

This makes routing completely domain-agnostic.  A car company, a bank, or a
hospital can all use the pipeline without touching jira_routing.json.

jira_routing.json is still respected when present: its project list is merged
into the context as additional project hints so the LLM is aware of projects
the company *intends* to have, even before they exist in Jira.
"""
import json
import logging
import os
import re
from typing import Dict, List, Optional

from langchain_groq import ChatGroq
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import JsonOutputParser

from backend.tools.jira_routing import RoutingDecision

logger = logging.getLogger(__name__)

_NEW_KEY_CONFIDENCE_THRESHOLD = 0.50  # below this → treat as new project


class LLMProjectRouter:
    """
    Routes epics to Jira projects using an LLM.

    Args:
        live_projects:  list of {"key": str, "name": str} from live Jira
        hint_projects:  optional extra list from jira_routing.json (may include
                        projects not yet created in Jira)
        model:          Groq model name
    """

    def __init__(
        self,
        live_projects: List[Dict],
        hint_projects: Optional[List[Dict]] = None,
        model: str = "llama-3.3-70b-versatile",
    ):
        self.live_projects = live_projects          # exist in Jira right now
        self.hint_projects = hint_projects or []    # from jira_routing.json
        self._all_projects = self._merge_projects()

        self.llm = ChatGroq(
            model=model,
            temperature=0,
            api_key=os.getenv("GROQ_API_KEY"),
        )
        self.parser = JsonOutputParser()
        self._chain = self._build_chain()

    # ── Public API ────────────────────────────────────────────────────────────

    def route(self, title: str, description: str = "") -> RoutingDecision:
        """
        Route a single epic.

        Returns a RoutingDecision.  If no existing project fits, the decision
        has is_new_project_candidate=True and suggested_project_name set.
        """
        projects_block = self._format_projects_block()

        try:
            result: Dict = self._chain.invoke({
                "projects_block": projects_block,
                "title": title,
                "description": description or "(no description)",
            })
        except Exception as exc:
            logger.warning(f"LLM routing failed for '{title}': {exc}")
            return self._fallback_decision(title)

        return self._parse_llm_result(result, title)

    # ── Private helpers ───────────────────────────────────────────────────────

    def _merge_projects(self) -> List[Dict]:
        """Merge live + hint lists; live takes precedence on key conflicts."""
        merged: Dict[str, Dict] = {}
        for p in self.hint_projects:
            merged[p["key"].upper()] = p
        for p in self.live_projects:
            merged[p["key"].upper()] = p   # live overrides hints
        return list(merged.values())

    def _format_projects_block(self) -> str:
        if not self._all_projects:
            return "(none — this Jira instance has no projects yet)"
        lines = []
        for p in self._all_projects:
            live_tag = "" if p in self.live_projects else " [configured, not in Jira yet]"
            lines.append(f'  - key="{p["key"]}"  name="{p["name"]}"{live_tag}')
        return "\n".join(lines)

    def _build_chain(self):
        prompt = ChatPromptTemplate.from_messages([
            (
                "system",
                "You are a Jira project router for a software company. "
                "Your job is to decide which Jira project an epic belongs to, "
                "or detect that it needs a brand-new project. "
                "Be domain-agnostic — the company could be building anything. "
                "Return ONLY a single valid JSON object, no markdown, no extra text.",
            ),
            (
                "human",
                "EXISTING JIRA PROJECTS:\n"
                "{projects_block}\n\n"
                "EPIC TO ROUTE:\n"
                "Title: {title}\n"
                "Description: {description}\n\n"
                "INSTRUCTIONS:\n"
                "1. If the epic clearly belongs to one of the existing projects, "
                "   set is_new=false and return that project's key and name.\n"
                "2. If the epic belongs to a project configured but not yet in Jira "
                "   (marked [configured, not in Jira yet]), set is_new=true so the "
                "   system sends an approval request to create it.\n"
                "3. If the epic does NOT fit any listed project at all, "
                "   set is_new=true and suggest an appropriate project key "
                "   (2-10 UPPERCASE letters) and name from the epic context.\n"
                "4. confidence: 0.0-1.0 — how certain you are about the project match.\n\n"
                "Return JSON with exactly these fields:\n"
                "{{\n"
                '  "project_key":    "<existing key or null if is_new>",\n'
                '  "project_name":   "<existing name or null if is_new>",\n'
                '  "is_new":         <true|false>,\n'
                '  "suggested_key":  "<NEW_KEY or null — UPPERCASE, no spaces, no special chars, 2-10 chars>",\n'
                '  "suggested_name": "<New Project Name or null>",\n'
                '  "confidence":     <0.0-1.0>,\n'
                '  "reason":         "<one sentence>"\n'
                "}}"
            ),
        ])
        return prompt | self.llm | self.parser

    def _parse_llm_result(self, result: Dict, title: str) -> RoutingDecision:
        is_new     = bool(result.get("is_new", False))
        confidence = float(result.get("confidence", 0.5))
        reason     = result.get("reason", "llm_routing")

        # Treat low-confidence existing-project matches as "new" too
        if not is_new and confidence < _NEW_KEY_CONFIDENCE_THRESHOLD:
            is_new = True

        if is_new:
            raw_key = result.get("suggested_key") or ""
            # Sanitize: uppercase, strip spaces and non-alphanumeric chars
            sanitized_key = re.sub(r"[^A-Z0-9]", "", raw_key.upper())
            suggested_key  = sanitized_key[:10] if sanitized_key else _derive_key(title)
            suggested_name = result.get("suggested_name") or title
            return RoutingDecision(
                project_key=suggested_key,
                project_name=suggested_name,
                component=None,
                matched_project=False,
                matched_team=False,
                is_triage=False,
                confidence=confidence,
                decision_reason="llm_new_project",
                is_new_project_candidate=True,
                suggested_project_name=suggested_name,
            )

        project_key  = (result.get("project_key") or "").strip().upper()
        project_name = result.get("project_name") or project_key

        if not project_key:
            return self._fallback_decision(title)

        return RoutingDecision(
            project_key=project_key,
            project_name=project_name,
            component=None,
            matched_project=True,
            matched_team=False,
            is_triage=False,
            team_name=None,
            confidence=confidence,
            decision_reason=f"llm:{reason[:60]}",
            is_new_project_candidate=False,
            suggested_project_name=None,
        )

    def _fallback_decision(self, title: str) -> RoutingDecision:
        """Used when LLM call fails entirely."""
        return RoutingDecision(
            project_key=_derive_key(title),
            project_name=title,
            component=None,
            matched_project=False,
            matched_team=False,
            is_triage=False,
            confidence=0.0,
            decision_reason="llm_fallback",
            is_new_project_candidate=True,
            suggested_project_name=title,
        )


# ── Utility ───────────────────────────────────────────────────────────────────

def _derive_key(name: str) -> str:
    """Generate a safe Jira project key from a name (up to 8 chars, uppercase, no spaces)."""
    # Strip everything except letters and digits, then uppercase
    clean = re.sub(r"[^a-zA-Z0-9 ]", "", name).upper()
    words = clean.split()
    if not words:
        return "PROJ"
    if len(words) == 1:
        key = words[0][:8]
    else:
        # Acronym from first letters of each word
        acronym = "".join(w[0] for w in words if w)[:8]
        key = acronym if len(acronym) >= 2 else words[0][:8]
    # Final guard: remove any remaining non-alphanumeric characters
    key = re.sub(r"[^A-Z0-9]", "", key)
    return key or "PROJ"
