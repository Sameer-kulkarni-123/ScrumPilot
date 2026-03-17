import os
from jira import JIRA
from typing import Optional, List, Dict


class JiraManager:
    def __init__(self):
        """
        Initializes the Jira client using environment variables.
        Requires: JIRA_URL, JIRA_EMAIL, JIRA_API_TOKEN, JIRA_PROJECT_KEY
        """
        self.url = os.getenv("JIRA_URL")
        self.email = os.getenv("JIRA_EMAIL")
        self.token = os.getenv("JIRA_API_TOKEN")
        self.project_key = os.getenv("JIRA_PROJECT_KEY")

        if not all([self.url, self.email, self.token]):
            raise ValueError("Jira credentials missing in environment variables.")

        self.client = JIRA(
            server=self.url,
            basic_auth=(self.email, self.token)
        )

    # ── Create ────────────────────────────────────────────────────────────

    def create_ticket(
        self,
        summary: str,
        description: str = "",
        issue_type: str = "Task",
        assignee_email: Optional[str] = None,
    ) -> Dict:
        """
        Creates a new Jira issue.

        Args:
            summary: Short title for the issue.
            description: Detailed description.
            issue_type: Jira issue type name (default "Task").
            assignee_email: Optional email of the user to assign immediately.

        Returns:
            dict with keys: success (bool), key (str), summary (str), message (str)
        """
        try:
            fields = {
                "project": self.project_key,
                "summary": summary,
                "description": description,
                "issuetype": {"name": issue_type},
            }
            if assignee_email:
                fields["assignee"] = {"name": assignee_email}

            new_issue = self.client.create_issue(fields=fields)
            return {
                "success": True,
                "key": new_issue.key,
                "summary": summary,
                "message": f"Ticket {new_issue.key} created successfully.",
            }
        except Exception as e:
            return {"success": False, "error": str(e)}

    # ── Status transitions ────────────────────────────────────────────────

    def get_transitions(self, ticket_key: str) -> Dict:
        """
        Lists the available workflow transitions for a ticket.

        Returns:
            dict with keys: success (bool), transitions (list of {id, name})
        """
        try:
            raw = self.client.transitions(ticket_key)
            transitions = [{"id": t["id"], "name": t["name"]} for t in raw]
            return {"success": True, "transitions": transitions}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def update_ticket_status(self, ticket_key: str, transition_name: str) -> Dict:
        """
        Moves a ticket through a workflow transition (e.g. 'In Progress', 'Done').

        Args:
            ticket_key: e.g. "SCRUM-42"
            transition_name: The display name of the target transition.

        Returns:
            dict with keys: success (bool), message (str)
        """
        try:
            self.client.transition_issue(ticket_key, transition_name)
            return {
                "success": True,
                "message": f"Ticket {ticket_key} transitioned to '{transition_name}'.",
            }
        except Exception as e:
            return {"success": False, "error": str(e)}

    # ── Assignment ────────────────────────────────────────────────────────

    def assign_ticket(self, ticket_key: str, assignee_email: str) -> Dict:
        """
        Assigns a ticket to a user.

        Args:
            ticket_key: e.g. "SCRUM-42"
            assignee_email: The Jira user's email / account name.

        Returns:
            dict with keys: success (bool), message (str)
        """
        try:
            self.client.assign_issue(ticket_key, assignee_email)
            return {
                "success": True,
                "message": f"Ticket {ticket_key} assigned to {assignee_email}.",
            }
        except Exception as e:
            return {"success": False, "error": str(e)}

    # ── Search / Query ────────────────────────────────────────────────────

    def search_tickets(
        self,
        summary_query: Optional[str] = None,
        assignee_email: Optional[str] = None,
        status: Optional[str] = None,
        max_results: int = 10,
    ) -> Dict:
        """
        Searches for tickets in the project using optional filters.

        Args:
            summary_query: Text to search for in the summary field.
            assignee_email: Filter by assignee.
            status: Filter by status name (e.g. "To Do", "In Progress", "Done").
            max_results: Maximum number of results.

        Returns:
            dict with keys: success (bool), issues (list of dicts with key, summary, status, assignee)
        """
        try:
            clauses = [f'project = "{self.project_key}"']
            if summary_query:
                clauses.append(f'summary ~ "{summary_query}"')
            if assignee_email:
                clauses.append(f'assignee = "{assignee_email}"')
            if status:
                clauses.append(f'status = "{status}"')

            jql = " AND ".join(clauses)
            issues = self.client.search_issues(jql, maxResults=max_results)
            results = []
            for i in issues:
                results.append({
                    "key": i.key,
                    "summary": i.fields.summary,
                    "status": i.fields.status.name,
                    "assignee": (
                        getattr(i.fields.assignee, "emailAddress", None)
                        or getattr(i.fields.assignee, "displayName", None)
                        if i.fields.assignee
                        else None
                    ),
                })
            return {"success": True, "issues": results}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def get_user_tickets(self, email: str) -> Dict:
        """
        Fetches all open tickets assigned to a specific user.

        Args:
            email: The user's email address.

        Returns:
            dict with keys: success (bool), issues (list)
        """
        return self.search_tickets(assignee_email=email, status=None)

    # ── Comments ──────────────────────────────────────────────────────────

    def add_comment(self, ticket_key: str, comment_text: str) -> Dict:
        """
        Adds a comment to an existing ticket.

        Returns:
            dict with keys: success (bool), message (str)
        """
        try:
            self.client.add_comment(ticket_key, comment_text)
            return {
                "success": True,
                "message": f"Comment added to {ticket_key}.",
            }
        except Exception as e:
            return {"success": False, "error": str(e)}


if __name__ == "__main__":
    # For local testing
    # manager = JiraManager()
    # print(manager.create_ticket("Test from ScrumPilot", "Testing Jira API Integration"))
    pass