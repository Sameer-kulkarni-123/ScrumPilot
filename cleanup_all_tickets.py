"""
Clean up all epics, stories, and tasks from Jira and database.

This script deletes all tickets from Jira and clears the database
so you can start fresh with the backlog pipeline.
"""

from backend.tools.jira_client import JiraManager
from backend.db.connection import get_session
from backend.db.models import Epic, Story, BacklogTask

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
                ticket.delete()
                deleted += 1
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
    
    print("\n" + "=" * 70)
    print("CLEANUP COMPLETE")
    print("=" * 70)
    print("\n✅ All tickets deleted from Jira and database")
    print("\nYou can now run the backlog pipeline:")
    print("  python run_backlog_pipeline.py")
    print("=" * 70 + "\n")


if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv()
    
    cleanup_all()
