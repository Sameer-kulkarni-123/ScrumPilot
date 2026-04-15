"""
JiraAgent — Executes structured scrum actions against Jira.

Simplified version that directly executes actions without LangChain agent framework.
"""

import os
import sys
from typing import List, Dict, Optional
import logging

# Ensure project root is importable when running standalone
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from backend.tools.jira_client import JiraManager

logger = logging.getLogger(__name__)


class JiraAgent:
    """
    Executes scrum actions against Jira.
    
    Simplified implementation that directly processes actions without
    the LangChain agent framework complexity.
    """

    def __init__(self, jira_manager=None):
        """
        Args:
            jira_manager: A JiraManager instance (or mock). If None, a real
                          JiraManager is created from environment variables.
        """
        if jira_manager is None:
            self.jira = JiraManager()
        else:
            self.jira = jira_manager
        
        logger.info("JiraAgent initialized")

    def execute_actions(self, actions: List[Dict]) -> str:
        """
        Execute a list of scrum actions against Jira.

        Args:
            actions: List of action dicts as produced by ScrumExtractorAgent.
                Each action has: action, summary, status?, assignee?, comment?

        Returns:
            Summary report string.
        """
        print("\n" + "=" * 70)
        print("JIRA AGENT - Executing Actions")
        print("=" * 70)
        
        results = []
        successful = 0
        failed = 0
        
        for i, action in enumerate(actions, 1):
            action_type = action.get('action')
            summary = action.get('summary', 'N/A')
            
            print(f"\n[{i}/{len(actions)}] Processing: {action_type} - {summary}")
            
            try:
                if action_type == "create_task":
                    result = self._create_task(action)
                elif action_type == "complete_task":
                    result = self._complete_task(action)
                elif action_type == "update_status":
                    result = self._update_status(action)
                elif action_type == "assign_task":
                    result = self._assign_task(action)
                elif action_type == "add_comment":
                    result = self._add_comment(action)
                else:
                    result = f"Unknown action type: {action_type}"
                    failed += 1
                    print(f"  ERROR: {result}")
                    results.append(f"❌ {summary}: {result}")
                    continue
                
                successful += 1
                print(f"  SUCCESS: {result}")
                results.append(f"✅ {summary}: {result}")
            
            except Exception as e:
                failed += 1
                error_msg = str(e)
                print(f"  ERROR: {error_msg}")
                results.append(f"❌ {summary}: {error_msg}")
                logger.error(f"Action failed: {action_type} - {summary}: {e}")
        
        # Generate summary report
        print("\n" + "=" * 70)
        print("EXECUTION SUMMARY")
        print("=" * 70)
        print(f"Total Actions: {len(actions)}")
        print(f"Successful: {successful}")
        print(f"Failed: {failed}")
        print("=" * 70)
        
        report = f"""
Jira Action Execution Report
=============================

Total Actions: {len(actions)}
Successful: {successful}
Failed: {failed}

Details:
{chr(10).join(results)}

Summary:
- Processed {len(actions)} scrum actions from standup meeting
- {successful} actions completed successfully
- {failed} actions failed
"""
        
        return report

    def _create_task(self, action: Dict) -> str:
        """Create a new Jira ticket."""
        summary = action.get('summary')
        description = action.get('description', '')
        assignee = action.get('assignee')
        
        result = self.jira.create_ticket(
            summary=summary,
            description=description,
            issue_type="Task",
            assignee_email=assignee
        )
        
        if result.get('success'):
            return f"Created ticket {result.get('key')}"
        else:
            raise Exception(result.get('error', 'Unknown error'))

    def _complete_task(self, action: Dict) -> str:
        """Mark a task as complete (Done)."""
        summary = action.get('summary')
        
        # Extract ticket ID from summary (e.g., "SP-189 (Login Form UI)" -> "SP-189")
        ticket_key = self._extract_ticket_key(summary)
        
        if not ticket_key:
            # Search for ticket by summary
            search_result = self.jira.search_tickets(summary_query=summary, max_results=1)
            if search_result.get('success') and search_result.get('issues'):
                ticket_key = search_result['issues'][0]['key']
            else:
                raise Exception(f"Ticket not found: {summary}")
        
        # Update status to Done
        result = self.jira.update_ticket_status(ticket_key, "Done")
        
        if result.get('success'):
            return f"Marked {ticket_key} as Done"
        else:
            raise Exception(result.get('error', 'Unknown error'))

    def _update_status(self, action: Dict) -> str:
        """Update task status."""
        summary = action.get('summary')
        status = action.get('status', 'In Progress')
        
        # Extract ticket ID from summary
        ticket_key = self._extract_ticket_key(summary)
        
        if not ticket_key:
            # Search for ticket by summary
            search_result = self.jira.search_tickets(summary_query=summary, max_results=1)
            if search_result.get('success') and search_result.get('issues'):
                ticket_key = search_result['issues'][0]['key']
            else:
                raise Exception(f"Ticket not found: {summary}")
        
        # Update status
        result = self.jira.update_ticket_status(ticket_key, status)
        
        if result.get('success'):
            return f"Updated {ticket_key} to '{status}'"
        else:
            raise Exception(result.get('error', 'Unknown error'))

    def _assign_task(self, action: Dict) -> str:
        """Assign task to a user."""
        summary = action.get('summary')
        assignee = action.get('assignee')
        
        if not assignee:
            raise Exception("No assignee specified")
        
        # Extract ticket ID from summary
        ticket_key = self._extract_ticket_key(summary)
        
        if not ticket_key:
            # Search for ticket by summary
            search_result = self.jira.search_tickets(summary_query=summary, max_results=1)
            if search_result.get('success') and search_result.get('issues'):
                ticket_key = search_result['issues'][0]['key']
            else:
                raise Exception(f"Ticket not found: {summary}")
        
        # Assign ticket
        result = self.jira.assign_ticket(ticket_key, assignee)
        
        if result.get('success'):
            return f"Assigned {ticket_key} to {assignee}"
        else:
            raise Exception(result.get('error', 'Unknown error'))

    def _add_comment(self, action: Dict) -> str:
        """Add comment to a ticket."""
        summary = action.get('summary')
        comment = action.get('comment', '')
        
        if not comment:
            raise Exception("No comment text provided")
        
        # Extract ticket ID from summary
        ticket_key = self._extract_ticket_key(summary)
        
        if not ticket_key:
            # Search for ticket by summary
            search_result = self.jira.search_tickets(summary_query=summary, max_results=1)
            if search_result.get('success') and search_result.get('issues'):
                ticket_key = search_result['issues'][0]['key']
            else:
                raise Exception(f"Ticket not found: {summary}")
        
        # Add comment
        result = self.jira.add_comment(ticket_key, comment)
        
        if result.get('success'):
            return f"Added comment to {ticket_key}"
        else:
            raise Exception(result.get('error', 'Unknown error'))

    def _extract_ticket_key(self, summary: str) -> Optional[str]:
        """
        Extract Jira ticket key from summary text.
        
        Examples:
        - "SP-189 (Login Form UI)" -> "SP-189"
        - "SP-198: User Login" -> "SP-198"
        - "Complete SP-207" -> "SP-207"
        
        Returns:
            Ticket key or None if not found
        """
        import re
        
        # Pattern: PROJECT-NUMBER (e.g., SP-189, PROJ-123)
        pattern = r'\b([A-Z]+-\d+)\b'
        match = re.search(pattern, summary)
        
        if match:
            return match.group(1)
        
        return None
