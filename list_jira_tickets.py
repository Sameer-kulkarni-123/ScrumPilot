"""
List all tickets in Jira project
"""
import os
import sys
from dotenv import load_dotenv

load_dotenv()

sys.path.insert(0, os.path.join(os.path.dirname(__file__)))

from backend.tools.jira_client import JiraManager


def main():
    print("\n" + "=" * 80)
    print("LISTING ALL JIRA TICKETS")
    print("=" * 80 + "\n")
    
    jira = JiraManager()
    
    try:
        # Search for all issues (no filters)
        results = jira.search_tickets(max_results=50)
        
        issues = results.get('issues', [])
        
        if not issues:
            print("❌ No tickets found in project")
            return
        
        print(f"Found {len(issues)} tickets:\n")
        print("-" * 80)
        
        for issue in issues:
            key = issue.get('key', 'N/A')
            summary = issue.get('summary', 'N/A')
            status = issue.get('status', 'N/A')
            assignee = issue.get('assignee', 'Unassigned')
            
            print(f"{key}: {status} - {summary[:60]} (Assignee: {assignee})")
        
        print("-" * 80)
        print(f"\nTotal: {len(issues)} tickets")
        
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()
