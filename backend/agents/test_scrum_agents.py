"""
Test script for the LangChain-based ScrumExtractorAgent and JiraAgent.

- Tests the extractor with the example diarized transcript.
- Tests the JiraAgent with a mock JiraManager (no real Jira connection).
"""

import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))


# ═══════════════════════════════════════════════════════════════════════════════
#  Mock JiraManager (no real Jira connection needed)
# ═══════════════════════════════════════════════════════════════════════════════

class MockJiraManager:
    """Mimics JiraManager but logs calls and returns fake successes."""

    def __init__(self):
        self.call_log: list[dict] = []
        self.project_key = "MOCK"
        self._ticket_counter = 0

    def _log(self, method: str, **kwargs) -> dict:
        entry = {"method": method, **kwargs}
        self.call_log.append(entry)
        return entry

    def create_ticket(self, summary, description="", issue_type="Task", assignee_email=None):
        self._ticket_counter += 1
        key = f"MOCK-{self._ticket_counter}"
        self._log("create_ticket", summary=summary, description=description, key=key)
        return {"success": True, "key": key, "summary": summary, "message": f"Ticket {key} created."}

    def update_ticket_status(self, ticket_key, transition_name):
        self._log("update_ticket_status", ticket_key=ticket_key, transition_name=transition_name)
        return {"success": True, "message": f"Ticket {ticket_key} → {transition_name}"}

    def assign_ticket(self, ticket_key, assignee_email):
        self._log("assign_ticket", ticket_key=ticket_key, assignee_email=assignee_email)
        return {"success": True, "message": f"Ticket {ticket_key} assigned to {assignee_email}."}

    def search_tickets(self, summary_query=None, assignee_email=None, status=None, max_results=10):
        fake_key = "MOCK-FOUND"
        return {
            "success": True,
            "issues": [{"key": fake_key, "summary": summary_query or "?", "status": "To Do", "assignee": None}],
        }

    def add_comment(self, ticket_key, comment_text):
        self._log("add_comment", ticket_key=ticket_key, comment_text=comment_text)
        return {"success": True, "message": f"Comment added to {ticket_key}."}

    def get_transitions(self, ticket_key):
        self._log("get_transitions", ticket_key=ticket_key)
        return {
            "success": True,
            "transitions": [
                {"id": "1", "name": "To Do"},
                {"id": "2", "name": "In Progress"},
                {"id": "3", "name": "Done"},
            ],
        }


# ═══════════════════════════════════════════════════════════════════════════════
#  Tests
# ═══════════════════════════════════════════════════════════════════════════════

def test_extractor():
    """Test ScrumExtractorAgent with the example transcript."""
    from dotenv import load_dotenv
    load_dotenv()

    from backend.agents.scrum_extractor import ScrumExtractorAgent

    print("=" * 60)
    print("TEST 1 — ScrumExtractorAgent (LangChain + Gemini)")
    print("=" * 60)

    here = os.path.dirname(__file__)
    with open(os.path.join(here, "example_transcript.txt"), "r", encoding="utf-8") as f:
        transcript = f.read()

    agent = ScrumExtractorAgent()
    actions = agent.extract_actions(transcript)

    print(f"\n✅ Extracted {len(actions)} actions:\n")
    print(json.dumps(actions, indent=2))

    # Sanity checks
    action_types = {a["action"] for a in actions}
    assert "create_task" in action_types, "Expected at least one create_task action"
    assert "complete_task" in action_types, "Expected at least one complete_task action"
    print("\n✅ Sanity checks passed.\n")

    return actions


def test_jira_agent(actions: list[dict]):
    """Test JiraAgent (LangChain tool-calling) with a MockJiraManager."""
    from dotenv import load_dotenv
    load_dotenv()

    from backend.agents.jira_agent import JiraAgent

    print("=" * 60)
    print("TEST 2 — JiraAgent (LangChain tool-calling + MockJiraManager)")
    print("=" * 60)

    mock = MockJiraManager()
    agent = JiraAgent(jira_manager=mock)

    report = agent.execute_actions(actions)

    print(f"\n📋 Agent Report:\n{report}")

    print(f"\n📌 Total JiraManager calls logged: {len(mock.call_log)}")
    for c in mock.call_log:
        print(f"   → {c}")

    assert len(mock.call_log) > 0, "Expected at least one JiraManager call"
    print("\n✅ JiraAgent test passed.\n")


# ═══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    actions = test_extractor()
    print()
    test_jira_agent(actions)
    print("\n🎉 ALL TESTS PASSED!")
