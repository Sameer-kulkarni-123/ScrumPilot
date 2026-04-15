"""Check for duplicate jira_keys in database."""

from backend.db.connection import get_session
from backend.db.models import Epic, Story, BacklogTask
from sqlalchemy import func

with get_session() as session:
    # Check for duplicate jira_keys
    print("\n=== CHECKING FOR DUPLICATE JIRA KEYS ===\n")
    
    # Epics
    epic_dupes = session.query(
        Epic.jira_key, func.count(Epic.jira_key)
    ).group_by(Epic.jira_key).having(func.count(Epic.jira_key) > 1).all()
    
    if epic_dupes:
        print(f"❌ Found {len(epic_dupes)} duplicate epic jira_keys:")
        for key, count in epic_dupes:
            print(f"  {key}: {count} times")
    else:
        print("✅ No duplicate epic jira_keys")
    
    # Stories
    story_dupes = session.query(
        Story.jira_key, func.count(Story.jira_key)
    ).group_by(Story.jira_key).having(func.count(Story.jira_key) > 1).all()
    
    if story_dupes:
        print(f"❌ Found {len(story_dupes)} duplicate story jira_keys:")
        for key, count in story_dupes:
            print(f"  {key}: {count} times")
    else:
        print("✅ No duplicate story jira_keys")
    
    # Tasks
    task_dupes = session.query(
        BacklogTask.jira_key, func.count(BacklogTask.jira_key)
    ).group_by(BacklogTask.jira_key).having(func.count(BacklogTask.jira_key) > 1).all()
    
    if task_dupes:
        print(f"❌ Found {len(task_dupes)} duplicate task jira_keys:")
        for key, count in task_dupes:
            print(f"  {key}: {count} times")
    else:
        print("✅ No duplicate task jira_keys")
    
    # Check all jira_keys (including NULL)
    print("\n=== ALL JIRA KEYS IN DATABASE ===\n")
    
    epics = session.query(Epic).all()
    stories = session.query(Story).all()
    tasks = session.query(BacklogTask).all()
    
    print(f"Epics: {len(epics)}")
    for epic in epics:
        print(f"  ID {epic.id}: {epic.jira_key} - {epic.title[:50]}")
    
    print(f"\nStories: {len(stories)}")
    for story in stories:
        print(f"  ID {story.id}: {story.jira_key} - {story.title[:50]}")
    
    print(f"\nTasks: {len(tasks)}")
    for task in tasks:
        print(f"  ID {task.id}: {task.jira_key} - {task.title[:50]}")
