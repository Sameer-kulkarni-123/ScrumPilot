import os
from jira import JIRA
from typing import Optional, List, Dict

class JiraManager:
    def __init__(self):
        """
        Initializes the Jira client using environment variables.
        Requires: JIRA_URL, JIRA_EMAIL, JIRA_API_TOKEN
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

    def create_ticket(self, summary: str, description: str, issue_type: str = "Task") -> str:
        """Creates a new issue in Jira."""
        new_issue = self.client.create_issue(
            project=self.project_key,
            summary=summary,
            description=description,
            issuetype={'name': issue_type}
        )
        return f"Ticket created: {new_issue.key}"

    def update_ticket_status(self, ticket_key: str, transition_name: str) -> bool:
        """Moves a ticket (e.g., 'To Do' -> 'In Progress')."""
        try:
            self.client.transition_issue(ticket_key, transition_name)
            return True
        except Exception as e:
            print(f"Error updating ticket {ticket_key}: {e}")
            return False

    def get_user_tickets(self, email: str) -> List[Dict]:
        """Fetches all open tickets assigned to a specific user."""
        jql = f'project = "{self.project_key}" AND assignee = "{email}" AND status != "Done"'
        issues = self.client.search_issues(jql)
        return [{"key": i.key, "summary": i.fields.summary, "status": i.fields.status.name} for i in issues]

    def add_comment(self, ticket_key: str, comment_text: str):
        """Adds a comment to an existing ticket."""
        self.client.add_comment(ticket_key, comment_text)

if __name__ == "__main__":
    # For local testing
    # manager = JiraManager()
    # print(manager.create_ticket("Test from ScrumPilot", "Testing Jira API Integration"))
    pass