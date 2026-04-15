"""
Verify Database vs Jira Sync

This script checks:
1. What's in the database
2. What's actually in Jira
3. Which database records don't exist in Jira (orphaned)
4. Sync status
"""
from dotenv import load_dotenv
load_dotenv()

from backend.db.connection import get_session
from backend.db.models import Epic, Story, BacklogTask
from backend.tools.jira_client import JiraManager

def main():
    """Verify database vs Jira sync."""
    
    print("=" * 80)
    print("DATABASE vs JIRA VERIFICATION")
    print("=" * 80)
    
    jira = JiraManager()
    
    with get_session() as session:
        # 1. Check Epics
        print("\n1. EPICS:")
        print("-" * 80)
        
        epics = session.query(Epic).all()
        print(f"   Database: {len(epics)} epic(s)")
        
        if epics:
            print("\n   Checking each epic in Jira...")
            epics_in_jira = 0
            epics_missing = 0
            
            for epic in epics:
                jira_key = epic.jira_key
                title = epic.title[:50]
                
                if not jira_key:
                    print(f"   ⚠️  {epic.epic_id:15} | No Jira key | {title}")
                    epics_missing += 1
                    continue
                
                # Check if exists in Jira
                try:
                    issue = jira.client.issue(jira_key)
                    status = issue.fields.status.name
                    print(f"   ✅ {jira_key:10} | {status:15} | {title}")
                    epics_in_jira += 1
                except Exception as e:
                    print(f"   ❌ {jira_key:10} | NOT IN JIRA    | {title}")
                    epics_missing += 1
            
            print(f"\n   Summary:")
            print(f"   - In Jira: {epics_in_jira}/{len(epics)}")
            print(f"   - Missing: {epics_missing}/{len(epics)}")
        
        # 2. Check Stories
        print("\n2. STORIES:")
        print("-" * 80)
        
        stories = session.query(Story).all()
        print(f"   Database: {len(stories)} story(ies)")
        
        if stories:
            print("\n   Checking each story in Jira...")
            stories_in_jira = 0
            stories_missing = 0
            
            for story in stories[:10]:  # Check first 10
                jira_key = story.jira_key
                title = story.title[:50] if story.title else "No title"
                
                if not jira_key:
                    print(f"   ⚠️  {story.story_id:20} | No Jira key | {title}")
                    stories_missing += 1
                    continue
                
                # Check if exists in Jira
                try:
                    issue = jira.client.issue(jira_key)
                    status = issue.fields.status.name
                    print(f"   ✅ {jira_key:10} | {status:15} | {title}")
                    stories_in_jira += 1
                except Exception as e:
                    print(f"   ❌ {jira_key:10} | NOT IN JIRA    | {title}")
                    stories_missing += 1
            
            if len(stories) > 10:
                print(f"   ... and {len(stories) - 10} more stories")
            
            print(f"\n   Summary (first 10):")
            print(f"   - In Jira: {stories_in_jira}/10")
            print(f"   - Missing: {stories_missing}/10")
        
        # 3. Check Tasks
        print("\n3. TASKS:")
        print("-" * 80)
        
        tasks = session.query(BacklogTask).all()
        print(f"   Database: {len(tasks)} task(s)")
        
        if len(tasks) == 0:
            print("   ⚠️  No tasks in database!")
            print("   Note: Tasks might not be saved to database, only to Jira")
        
        # 4. Overall Statistics
        print("\n4. OVERALL STATISTICS:")
        print("-" * 80)
        
        # Count items with Jira keys
        epics_with_keys = session.query(Epic).filter(Epic.jira_key.isnot(None)).count()
        stories_with_keys = session.query(Story).filter(Story.jira_key.isnot(None)).count()
        tasks_with_keys = session.query(BacklogTask).filter(BacklogTask.jira_key.isnot(None)).count()
        
        print(f"   Epics with Jira keys: {epics_with_keys}/{len(epics)}")
        print(f"   Stories with Jira keys: {stories_with_keys}/{len(stories)}")
        print(f"   Tasks with Jira keys: {tasks_with_keys}/{len(tasks)}")
        
        # 5. Check Jira for items NOT in database
        print("\n5. JIRA ITEMS NOT IN DATABASE:")
        print("-" * 80)
        
        # Get all epics from Jira
        try:
            jira_epics = jira.client.search_issues(
                'project = SP AND type = Epic',
                maxResults=50
            )
            
            print(f"   Jira: {len(jira_epics)} epic(s)")
            
            # Get all Jira keys from database
            db_epic_keys = {epic.jira_key for epic in epics if epic.jira_key}
            
            # Find epics in Jira but not in database
            orphaned_epics = []
            for jira_epic in jira_epics:
                if jira_epic.key not in db_epic_keys:
                    orphaned_epics.append(jira_epic)
            
            if orphaned_epics:
                print(f"\n   ⚠️  {len(orphaned_epics)} epic(s) in Jira but NOT in database:")
                for epic in orphaned_epics[:5]:
                    print(f"      - {epic.key}: {epic.fields.summary[:50]}")
                if len(orphaned_epics) > 5:
                    print(f"      ... and {len(orphaned_epics) - 5} more")
            else:
                print(f"   ✅ All Jira epics are in database")
        
            orphaned_epics = []
        except Exception as e:
            print(f"   ❌ Error checking Jira: {e}")
            orphaned_epics = []
        
        # 6. Recommendations
        print("\n6. RECOMMENDATIONS:")
        print("-" * 80)
        
        if epics_missing > 0:
            print("   ⚠️  Some database records don't exist in Jira!")
            print("   Possible reasons:")
            print("   1. Tickets were deleted from Jira manually")
            print("   2. Jira creation failed but database was updated")
            print("   3. Database has stale data")
            print("\n   Solutions:")
            print("   - Clean up database: Remove records without Jira keys")
            print("   - Sync database with Jira: Update Jira keys")
            print("   - Use Jira as source of truth: Check Jira before database")
        
        if len(orphaned_epics) > 0:
            print("\n   ⚠️  Some Jira tickets are not in database!")
            print("   Possible reasons:")
            print("   1. Tickets were created manually in Jira")
            print("   2. Database sync failed")
            print("\n   Solutions:")
            print("   - Import from Jira: Add missing tickets to database")
            print("   - Ignore: Database only tracks pipeline-created items")
        
        if epics_missing == 0 and len(orphaned_epics) == 0:
            print("   ✅ Database and Jira are in sync!")
            print("   All database records exist in Jira")
            print("   All Jira epics are tracked in database")
        
        print("\n" + "=" * 80)
        print("VERIFICATION COMPLETE")
        print("=" * 80)
        
        # Summary
        sync_percentage = (epics_in_jira / len(epics) * 100) if len(epics) > 0 else 0
        print(f"\nSync Status: {sync_percentage:.0f}%")
        print(f"Database → Jira: {epics_in_jira}/{len(epics)} epics exist")
        print(f"Jira → Database: {len(jira_epics) - len(orphaned_epics)}/{len(jira_epics)} epics tracked")
        
        if sync_percentage == 100 and len(orphaned_epics) == 0:
            print("\n✅ PERFECT SYNC!")
        elif sync_percentage >= 80:
            print("\n⚠️  MOSTLY SYNCED (some issues)")
        else:
            print("\n❌ OUT OF SYNC (needs attention)")
        
        print("=" * 80)

if __name__ == "__main__":
    main()
