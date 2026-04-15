import os
import time
import logging
from collections import deque
from jira import JIRA
from jira.exceptions import JIRAError
from typing import Optional, List, Dict, Any
from functools import wraps

logger = logging.getLogger(__name__)


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
        
        # Rate limiting configuration
        self.rate_limit_enabled = True
        self.rate_limit_calls = 150  # Conservative: 150/min (Jira allows 200)
        self.rate_limit_period = 60  # seconds
        self.call_timestamps = deque()  # Track recent API calls
        
        # Retry configuration
        self.retry_enabled = True
        self.max_retries = 3
        self.retry_delay_base = 2  # Base delay in seconds (exponential backoff)
        
        logger.info(f"Rate limiting enabled: {self.rate_limit_calls} calls per {self.rate_limit_period}s")
        logger.info(f"Retry enabled: max {self.max_retries} attempts with exponential backoff")

    # ── Retry Logic ───────────────────────────────────────────────────────

    def _is_retryable_error(self, error: Exception) -> bool:
        """
        Determine if an error is retryable.
        
        Retryable errors:
        - Network errors (ConnectionError, TimeoutError)
        - Jira server errors (500, 502, 503, 504)
        - Rate limit errors (429)
        
        Non-retryable errors:
        - Invalid data (400)
        - Permission errors (403)
        - Not found (404)
        """
        if isinstance(error, (ConnectionError, TimeoutError)):
            return True
        
        if isinstance(error, JIRAError):
            # Retry on server errors and rate limits
            return error.status_code in [429, 500, 502, 503, 504]
        
        return False

    def _retry_with_backoff(self, func, *args, **kwargs):
        """
        Execute function with exponential backoff retry logic.
        
        Args:
            func: Function to execute
            *args, **kwargs: Arguments to pass to function
        
        Returns:
            Function result
        
        Raises:
            Last exception if all retries fail
        """
        if not self.retry_enabled:
            return func(*args, **kwargs)
        
        last_exception = None
        
        for attempt in range(self.max_retries):
            try:
                return func(*args, **kwargs)
            
            except Exception as e:
                last_exception = e
                
                # Check if error is retryable
                if not self._is_retryable_error(e):
                    logger.error(f"Non-retryable error: {e}")
                    raise
                
                # Don't retry on last attempt
                if attempt == self.max_retries - 1:
                    logger.error(f"Max retries ({self.max_retries}) exceeded")
                    raise
                
                # Calculate backoff delay (exponential: 2s, 4s, 8s)
                delay = self.retry_delay_base * (2 ** attempt)
                
                logger.warning(
                    f"Retryable error on attempt {attempt + 1}/{self.max_retries}: {e}"
                )
                logger.info(f"Retrying in {delay}s...")
                print(f"    Error: {e}")
                print(f"    Retrying in {delay}s... (attempt {attempt + 2}/{self.max_retries})")
                
                time.sleep(delay)
        
        # Should never reach here, but just in case
        raise last_exception

    # ── Rate Limiting ─────────────────────────────────────────────────────

    def _enforce_rate_limit(self):
        """
        Enforce rate limiting using sliding window algorithm.
        
        Tracks API call timestamps and sleeps if rate limit would be exceeded.
        This prevents hitting Jira's API rate limits (200 calls/minute).
        """
        if not self.rate_limit_enabled:
            return
        
        now = time.time()
        
        # Remove timestamps older than rate_limit_period (sliding window)
        while self.call_timestamps and (now - self.call_timestamps[0]) > self.rate_limit_period:
            self.call_timestamps.popleft()
        
        # Check if we're at the limit
        if len(self.call_timestamps) >= self.rate_limit_calls:
            # Calculate how long to wait
            oldest_call = self.call_timestamps[0]
            wait_time = self.rate_limit_period - (now - oldest_call) + 0.5  # Add 0.5s buffer
            
            if wait_time > 0:
                logger.warning(
                    f"Rate limit reached ({len(self.call_timestamps)} calls in {self.rate_limit_period}s), "
                    f"waiting {wait_time:.1f}s..."
                )
                print(f"    Rate limit: waiting {wait_time:.1f}s...")
                time.sleep(wait_time)
                
                # Clear old timestamps after waiting
                now = time.time()
                while self.call_timestamps and (now - self.call_timestamps[0]) > self.rate_limit_period:
                    self.call_timestamps.popleft()
        
        # Record this call
        self.call_timestamps.append(now)

    # ── Create ────────────────────────────────────────────────────────────

    def create_ticket(
        self,
        summary: str,
        description: str = "",
        issue_type: str = "Task",
        assignee_email: Optional[str] = None,
        parent_key: Optional[str] = None,
        epic_link: Optional[str] = None,
    ) -> Dict:
        """
        Creates a new Jira issue with automatic retry on transient failures.

        Args:
            summary: Short title for the issue.
            description: Detailed description.
            issue_type: Jira issue type name (default "Task").
            assignee_email: Optional email of the user to assign immediately.
            parent_key: Optional parent issue key (for Sub-tasks or Tasks under Stories).
            epic_link: Optional Epic key to link this issue to (for Stories under Epics).

        Returns:
            dict with keys: success (bool), key (str), summary (str), message (str)
        """
        # Wrap the actual creation in retry logic
        return self._retry_with_backoff(
            self._create_ticket_internal,
            summary, description, issue_type, assignee_email, parent_key, epic_link
        )
    
    def _create_ticket_internal(
        self,
        summary: str,
        description: str,
        issue_type: str,
        assignee_email: Optional[str],
        parent_key: Optional[str],
        epic_link: Optional[str],
    ) -> Dict:
        """Internal method that performs the actual ticket creation."""
        # Enforce rate limiting before API call
        self._enforce_rate_limit()
        
        try:
            fields = {
                "project": self.project_key,
                "summary": summary,
                "description": description,
                "issuetype": {"name": issue_type},
            }
            if assignee_email:
                fields["assignee"] = {"name": assignee_email}
            
            # Set parent field for Sub-tasks and Tasks
            if parent_key:
                fields["parent"] = {"key": parent_key}
            
            # For Stories, set parent to Epic (next-gen/team-managed projects)
            # In next-gen projects, Stories link to Epics via the parent field
            if epic_link and issue_type == "Story":
                fields["parent"] = {"key": epic_link}

            new_issue = self.client.create_issue(fields=fields)
            
            return {
                "success": True,
                "key": new_issue.key,
                "summary": summary,
                "message": f"Ticket {new_issue.key} created successfully.",
            }
        except Exception as e:
            return {"success": False, "error": str(e)}

    def create_epic(
        self,
        summary: str,
        description: str = "",
        epic_name: Optional[str] = None,
    ) -> Dict:
        """
        Creates a new Epic in Jira with automatic retry on transient failures.

        Args:
            summary: Epic title/summary.
            description: Detailed Epic description.
            epic_name: Optional Epic name (short identifier) - NOT USED (field varies by Jira config).

        Returns:
            dict with keys: success (bool), key (str), summary (str), message (str)
        """
        # Wrap the actual creation in retry logic
        return self._retry_with_backoff(
            self._create_epic_internal,
            summary, description, epic_name
        )
    
    def _create_epic_internal(
        self,
        summary: str,
        description: str,
        epic_name: Optional[str],
    ) -> Dict:
        """Internal method that performs the actual Epic creation."""
        # Enforce rate limiting before API call
        self._enforce_rate_limit()
        
        try:
            fields = {
                "project": self.project_key,
                "summary": summary,
                "description": description,
                "issuetype": {"name": "Epic"},
            }
            
            # Note: Epic Name field (customfield_10011) is not set because:
            # 1. Field ID varies by Jira configuration
            # 2. Many Jira instances don't have this field configured
            # 3. Epic summary is sufficient for identification
            
            new_epic = self.client.create_issue(fields=fields)
            return {
                "success": True,
                "key": new_epic.key,
                "summary": summary,
                "message": f"Epic {new_epic.key} created successfully.",
            }
        except Exception as e:
            return {"success": False, "error": str(e)}

    # ── Duplicate Detection ───────────────────────────────────────────────

    def find_similar_issues(
        self,
        summary: str,
        issue_type: str = "Epic",
        similarity_threshold: float = 0.85,
        max_results: int = 20
    ) -> List[Dict]:
        """
        Find issues with similar summaries to detect potential duplicates.
        
        Uses fuzzy string matching to find issues that might be duplicates.
        
        Args:
            summary: Summary text to search for
            issue_type: Type of issue to search (Epic, Story, Task, etc.)
            similarity_threshold: Minimum similarity score (0.0-1.0), default 0.85
            max_results: Maximum number of results to check
        
        Returns:
            List of similar issues with similarity scores, sorted by similarity (highest first)
            Each item contains: key, summary, similarity, status, issue_type
        """
        from difflib import SequenceMatcher
        
        # Search for issues with similar text (use first 50 chars for search)
        search_text = summary[:50] if len(summary) > 50 else summary
        result = self.search_tickets(
            summary_query=search_text,
            max_results=max_results
        )
        
        if not result.get('success'):
            logger.warning(f"Failed to search for similar issues: {result.get('error')}")
            return []
        
        similar_issues = []
        
        for issue in result.get('issues', []):
            # Calculate similarity score using SequenceMatcher
            similarity = SequenceMatcher(
                None,
                summary.lower().strip(),
                issue['summary'].lower().strip()
            ).ratio()
            
            if similarity >= similarity_threshold:
                similar_issues.append({
                    'key': issue['key'],
                    'summary': issue['summary'],
                    'similarity': similarity,
                    'status': issue['status'],
                    'issue_type': issue_type  # Note: We don't get issue type from search_tickets
                })
        
        # Sort by similarity (highest first)
        similar_issues.sort(key=lambda x: x['similarity'], reverse=True)
        
        return similar_issues

    def link_issue_to_epic(self, issue_key: str, epic_key: str) -> Dict:
        """
        Links an issue (Story) to an Epic.

        Args:
            issue_key: The issue key to link (e.g., "SP-123").
            epic_key: The Epic key to link to (e.g., "SP-100").

        Returns:
            dict with keys: success (bool), message (str)
        """
        try:
            self.client.add_issues_to_epic(epic_key, [issue_key])
            return {
                "success": True,
                "message": f"Issue {issue_key} linked to Epic {epic_key}.",
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
        # Enforce rate limiting before API call
        self._enforce_rate_limit()
        
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

    # ── Sprint Management ─────────────────────────────────────────────────

    def create_sprint(
        self,
        name: str,
        goal: str,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        board_id: Optional[int] = None
    ) -> Dict:
        """
        Create a new sprint in Jira.
        
        Args:
            name: Sprint name (e.g., "Sprint 23")
            goal: Sprint goal description
            start_date: Start date in YYYY-MM-DD format (optional)
            end_date: End date in YYYY-MM-DD format (optional)
            board_id: Board ID (if None, uses first board found)
        
        Returns:
            dict with keys: success (bool), id (int), name (str), key (str), message (str)
        """
        # Enforce rate limiting before API call
        self._enforce_rate_limit()
        
        try:
            # Get board ID if not provided
            if not board_id:
                boards = self.client.boards()
                if not boards:
                    return {"success": False, "error": "No boards found in project"}
                board_id = boards[0].id
                logger.info(f"Using board ID: {board_id}")
            
            # Create sprint
            sprint = self.client.create_sprint(
                name=name,
                board_id=board_id,
                goal=goal,
                startDate=start_date,
                endDate=end_date
            )
            
            return {
                "success": True,
                "id": sprint.id,
                "name": sprint.name,
                "key": f"SPRINT-{sprint.id}",
                "message": f"Sprint '{name}' created successfully."
            }
        
        except Exception as e:
            logger.error(f"Failed to create sprint: {e}")
            return {"success": False, "error": str(e)}

    def move_issue_to_sprint(self, issue_key: str, sprint_id: int) -> Dict:
        """
        Move an issue to a sprint.
        
        Args:
            issue_key: Issue key (e.g., "SP-123")
            sprint_id: Sprint ID
        
        Returns:
            dict with keys: success (bool), message (str)
        """
        # Enforce rate limiting before API call
        self._enforce_rate_limit()
        
        try:
            self.client.add_issues_to_sprint(sprint_id, [issue_key])
            return {
                "success": True,
                "message": f"Issue {issue_key} moved to sprint {sprint_id}."
            }
        
        except Exception as e:
            logger.error(f"Failed to move issue to sprint: {e}")
            return {"success": False, "error": str(e)}

    def move_issues_to_sprint(self, issue_keys: List[str], sprint_id: int) -> Dict:
        """
        Move multiple issues to a sprint (bulk operation).
        
        Args:
            issue_keys: List of issue keys (e.g., ["SP-123", "SP-124"])
            sprint_id: Sprint ID
        
        Returns:
            dict with keys: success (bool), moved (int), failed (int), errors (list)
        """
        moved = 0
        failed = 0
        errors = []
        
        for issue_key in issue_keys:
            result = self.move_issue_to_sprint(issue_key, sprint_id)
            if result.get('success'):
                moved += 1
            else:
                failed += 1
                errors.append(f"{issue_key}: {result.get('error')}")
        
        return {
            "success": failed == 0,
            "moved": moved,
            "failed": failed,
            "errors": errors,
            "message": f"Moved {moved}/{len(issue_keys)} issues to sprint."
        }

    def assign_issue(self, issue_key: str, assignee: str) -> Dict:
        """
        Assign an issue to a user.
        
        Args:
            issue_key: Issue key (e.g., "SP-123")
            assignee: User email or account ID
        
        Returns:
            dict with keys: success (bool), message (str)
        """
        # Enforce rate limiting before API call
        self._enforce_rate_limit()
        
        try:
            self.client.assign_issue(issue_key, assignee)
            return {
                "success": True,
                "message": f"Issue {issue_key} assigned to {assignee}."
            }
        
        except Exception as e:
            logger.error(f"Failed to assign issue: {e}")
            return {"success": False, "error": str(e)}

    def bulk_assign_issues(self, assignments: List[Dict[str, Any]]) -> Dict:
        """
        Bulk assign issues to developers.
        
        Args:
            assignments: List of dicts with 'issue_key' and 'assignee'
                Example: [{"issue_key": "SP-123", "assignee": "sarah@company.com"}]
        
        Returns:
            dict with keys: success (bool), assigned (int), failed (int), errors (list)
        """
        assigned = 0
        failed = 0
        errors = []
        
        for assignment in assignments:
            issue_key = assignment.get('issue_key')
            assignee = assignment.get('assignee')
            
            if not issue_key or not assignee:
                failed += 1
                errors.append(f"Invalid assignment: {assignment}")
                continue
            
            result = self.assign_issue(issue_key, assignee)
            if result.get('success'):
                assigned += 1
            else:
                failed += 1
                errors.append(f"{issue_key}: {result.get('error')}")
        
        return {
            "success": failed == 0,
            "assigned": assigned,
            "failed": failed,
            "errors": errors,
            "message": f"Assigned {assigned}/{len(assignments)} issues."
        }

    def get_active_sprints(self, board_id: Optional[int] = None) -> Dict:
        """
        Get all active sprints.
        
        Args:
            board_id: Board ID (if None, uses first board found)
        
        Returns:
            dict with keys: success (bool), sprints (list)
        """
        # Enforce rate limiting before API call
        self._enforce_rate_limit()
        
        try:
            # Get board ID if not provided
            if not board_id:
                boards = self.client.boards()
                if not boards:
                    return {"success": False, "error": "No boards found in project"}
                board_id = boards[0].id
            
            sprints = self.client.sprints(board_id, state='active')
            
            sprint_list = []
            for sprint in sprints:
                sprint_list.append({
                    "id": sprint.id,
                    "name": sprint.name,
                    "state": sprint.state,
                    "goal": getattr(sprint, 'goal', None),
                    "startDate": getattr(sprint, 'startDate', None),
                    "endDate": getattr(sprint, 'endDate', None)
                })
            
            return {
                "success": True,
                "sprints": sprint_list
            }
        
        except Exception as e:
            logger.error(f"Failed to get active sprints: {e}")
            return {"success": False, "error": str(e)}


if __name__ == "__main__":
    # For local testing
    # manager = JiraManager()
    # print(manager.create_ticket("Test from ScrumPilot", "Testing Jira API Integration"))
    pass