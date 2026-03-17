"""
JiraAgent — A LangChain tool-calling agent that receives structured scrum
actions and executes them against Jira via JiraManager tools.
"""

import os
import sys
from typing import List, Dict, Optional

from langchain_groq import ChatGroq
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.tools import tool
from langchain.agents import create_tool_calling_agent, AgentExecutor

# Ensure project root is importable when running standalone
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))


# ═══════════════════════════════════════════════════════════════════════════════
#  Jira Tools — each wraps a JiraManager method for the LangChain agent
# ═══════════════════════════════════════════════════════════════════════════════

# Module-level JiraManager instance — set by JiraAgent.__init__
_jira_manager = None


@tool
def create_jira_ticket(
    summary: str,
    description: str = "",
    issue_type: str = "Task",
    assignee_email: Optional[str] = None,
) -> dict:
    """Create a new Jira ticket.

    Args:
        summary: Short title for the ticket.
        description: Detailed description of the task.
        issue_type: Jira issue type (default "Task").
        assignee_email: Email of the person to assign the ticket to.
    """
    return _jira_manager.create_ticket(
        summary=summary,
        description=description,
        issue_type=issue_type,
        assignee_email=assignee_email,
    )


@tool
def search_jira_tickets(
    summary_query: Optional[str] = None,
    assignee_email: Optional[str] = None,
    status: Optional[str] = None,
) -> dict:
    """Search for existing Jira tickets by summary text, assignee, or status.

    Args:
        summary_query: Text to search for in ticket summaries.
        assignee_email: Filter by assignee email.
        status: Filter by status (e.g. "To Do", "In Progress", "Done").
    """
    return _jira_manager.search_tickets(
        summary_query=summary_query,
        assignee_email=assignee_email,
        status=status,
    )


@tool
def update_jira_ticket_status(ticket_key: str, transition_name: str) -> dict:
    """Move a Jira ticket to a new status via a workflow transition.

    Args:
        ticket_key: The ticket key, e.g. "SCRUM-42".
        transition_name: The target transition name, e.g. "In Progress", "Done".
    """
    return _jira_manager.update_ticket_status(ticket_key, transition_name)


@tool
def assign_jira_ticket(ticket_key: str, assignee_email: str) -> dict:
    """Assign a Jira ticket to a user.

    Args:
        ticket_key: The ticket key, e.g. "SCRUM-42".
        assignee_email: The email or username of the person to assign.
    """
    return _jira_manager.assign_ticket(ticket_key, assignee_email)


@tool
def add_jira_comment(ticket_key: str, comment_text: str) -> dict:
    """Add a comment to an existing Jira ticket.

    Args:
        ticket_key: The ticket key, e.g. "SCRUM-42".
        comment_text: The comment to add.
    """
    return _jira_manager.add_comment(ticket_key, comment_text)


@tool
def get_jira_transitions(ticket_key: str) -> dict:
    """Get the available workflow transitions for a Jira ticket.

    Args:
        ticket_key: The ticket key, e.g. "SCRUM-42".
    """
    return _jira_manager.get_transitions(ticket_key)


# All tools the agent can use
JIRA_TOOLS = [
    create_jira_ticket,
    search_jira_tickets,
    update_jira_ticket_status,
    assign_jira_ticket,
    add_jira_comment,
    get_jira_transitions,
]

# ── Agent prompt ──────────────────────────────────────────────────────────────

SYSTEM_PROMPT = """\
You are a Jira Automation Agent. You receive a list of scrum actions extracted \
from a meeting transcript and you must execute each one using the available \
Jira tools.

Workflow for each action:
1. **create_task** → Call create_jira_ticket directly.
2. **complete_task** → First search_jira_tickets to find the ticket by summary, \
   then call update_jira_ticket_status with transition_name "Done".
3. **update_status** → First search_jira_tickets, then update_jira_ticket_status.
4. **assign_task** → First search_jira_tickets, then assign_jira_ticket.
5. **add_comment** → First search_jira_tickets, then add_jira_comment.

If search_jira_tickets returns no results for a task, report that the ticket \
was not found and move on to the next action.

Process ALL actions in the list. After all actions are done, provide a concise \
summary of what was accomplished and any errors encountered.\
"""


# ═══════════════════════════════════════════════════════════════════════════════
#  JiraAgent class
# ═══════════════════════════════════════════════════════════════════════════════

class JiraAgent:
    """
    LangChain tool-calling agent that executes scrum actions on Jira.
    """

    def __init__(self, jira_manager=None, model_name: str = "llama-3.3-70b-versatile"):
        """
        Args:
            jira_manager: A JiraManager instance (or mock). If None, a real
                          JiraManager is created from environment variables.
            model_name: The Gemini model to use for the agent.
        """
        global _jira_manager

        if jira_manager is None:
            from backend.tools.jira_client import JiraManager
            jira_manager = JiraManager()
        _jira_manager = jira_manager

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

        prompt = ChatPromptTemplate.from_messages([
            ("system", SYSTEM_PROMPT),
            ("human", "{input}"),
            MessagesPlaceholder(variable_name="agent_scratchpad"),
        ])

        agent = create_tool_calling_agent(llm, JIRA_TOOLS, prompt)
        self.executor = AgentExecutor(
            agent=agent,
            tools=JIRA_TOOLS,
            verbose=True,
            handle_parsing_errors=True,
            max_iterations=25,  # enough for multiple actions
        )

    def execute_actions(self, actions: List[Dict]) -> str:
        """
        Execute a list of scrum actions against Jira.

        Args:
            actions: List of action dicts as produced by ScrumExtractorAgent.

        Returns:
            The agent's summary report string.
        """
        import json
        actions_text = json.dumps(actions, indent=2)
        prompt = (
            f"Here are the scrum actions to execute:\n\n"
            f"```json\n{actions_text}\n```\n\n"
            f"Process each action using the available Jira tools."
        )

        result = self.executor.invoke({"input": prompt})
        return result["output"]
