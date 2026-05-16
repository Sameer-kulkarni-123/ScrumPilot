"""
Clean up all epics, stories, and tasks from Jira and database.

This script deletes all tickets from Jira and clears the database
so you can start fresh with the backlog pipeline.
"""

import glob
import os
import requests

from backend.tools.jira_client import JiraManager
from backend.db.connection import get_session
from backend.db.models import Epic, Story, BacklogTask


def _delete_issue_with_subtasks(jira: JiraManager, issue_key: str) -> tuple[bool, str]:
    """Delete a Jira issue using REST API with deleteSubtasks=true."""
    url = f"{jira.url}/rest/api/3/issue/{issue_key}"
    response = requests.delete(
        url,
        params={"deleteSubtasks": "true"},
        auth=(jira.email, jira.token),
        headers={"Accept": "application/json"},
        timeout=30,
    )

    if response.status_code in (200, 202, 204, 404):
        return True, ""

    try:
        details = response.json()
    except Exception:
        details = response.text

    return False, f"HTTP {response.status_code}: {details}"


def cleanup_all():
    """Delete all tickets from Jira and database."""
    
    print("\n" + "=" * 70)
    print("CLEANUP: DELETE ALL TICKETS")
    print("=" * 70)
    print("\n⚠️  WARNING: This will delete ALL epics, stories, and tasks!")
    print("   - From Jira")
    print("   - From Database")
    print()
    
    confirm = input("Are you sure? Type 'yes' to continue: ")
    if confirm.lower() != 'yes':
        print("\n❌ Cleanup cancelled")
        return
    
    jira = JiraManager()
    
    # Step 1: Delete from Jira
    print("\n" + "=" * 70)
    print("STEP 1: DELETING FROM JIRA")
    print("=" * 70)
    
    # Get all tickets from Jira
    print("\nFetching all tickets from Jira...")
    all_tickets = jira.client.search_issues(
        f'project = {jira.project_key}',
        maxResults=1000,
        fields='summary,issuetype'
    )
    
    print(f"Found {len(all_tickets)} tickets in Jira")
    
    if all_tickets:
        print("\nDeleting tickets from Jira...")
        deleted = 0
        failed = 0
        
        for ticket in all_tickets:
            try:
                print(f"  Deleting {ticket.key}: {ticket.fields.summary[:50]}...")
                success, error = _delete_issue_with_subtasks(jira, ticket.key)
                if success:
                    deleted += 1
                else:
                    print(f"  ❌ Failed to delete {ticket.key}: {error}")
                    failed += 1
            except Exception as e:
                print(f"  ❌ Failed to delete {ticket.key}: {e}")
                failed += 1
        
        print(f"\n✅ Deleted {deleted} tickets from Jira")
        if failed > 0:
            print(f"⚠️  Failed to delete {failed} tickets")
    else:
        print("\n✅ No tickets found in Jira")
    
    # Step 2: Delete from Database
    print("\n" + "=" * 70)
    print("STEP 2: DELETING FROM DATABASE")
    print("=" * 70)
    
    with get_session() as session:
        # Count before deletion
        epic_count = session.query(Epic).count()
        story_count = session.query(Story).count()
        task_count = session.query(BacklogTask).count()
        
        print(f"\nFound in database:")
        print(f"  Epics: {epic_count}")
        print(f"  Stories: {story_count}")
        print(f"  Tasks: {task_count}")
        
        if epic_count > 0 or story_count > 0 or task_count > 0:
            print("\nDeleting from database...")
            
            # Delete tasks first (foreign key constraint)
            if task_count > 0:
                session.query(BacklogTask).delete()
                print(f"  ✅ Deleted {task_count} tasks")
            
            # Delete stories
            if story_count > 0:
                session.query(Story).delete()
                print(f"  ✅ Deleted {story_count} stories")
            
            # Delete epics
            if epic_count > 0:
                session.query(Epic).delete()
                print(f"  ✅ Deleted {epic_count} epics")
            
            session.commit()
            print("\n✅ Database cleaned")
        else:
            print("\n✅ Database is already empty")
    
    # Step 3: Delete stale idempotency mapping files
    print("\n" + "=" * 70)
    print("STEP 3: DELETING STALE MAPPING FILES")
    print("=" * 70)
    mapping_pattern = os.path.join("backend", "data", "decomposed", "*_mapping.json")
    mapping_files = glob.glob(mapping_pattern)
    if mapping_files:
        for mf in mapping_files:
            os.remove(mf)
            print(f"  ✅ Deleted {mf}")
    else:
        print("\n✅ No mapping files found")

    print("\n" + "=" * 70)
    print("CLEANUP COMPLETE")
    print("=" * 70)
    print("\n✅ All tickets deleted from Jira and database")
    print("\nYou can now run the backlog pipeline:")
    print("  python run_test_pipeline.py               # direct Jira creation")
    print("  python run_test_pipeline.py --telegram    # human-in-the-loop approval")
    print("=" * 70 + "\n")


if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv()
    
    cleanup_all()
