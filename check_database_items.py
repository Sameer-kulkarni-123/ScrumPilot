"""Check database for epics, stories, and tasks."""

from backend.db.connection import get_session
from backend.db.models import Epic, Story, BacklogTask

with get_session() as session:
    # Get epics
    epics = session.query(Epic).filter(Epic.jira_key.isnot(None)).all()
    print("\n=== EPICS ===")
    for epic in epics[:5]:
        print(f"{epic.jira_key}: {epic.title}")
    
    # Get stories
    stories = session.query(Story).filter(Story.jira_key.isnot(None)).all()
    print(f"\n=== STORIES ({len(stories)} total) ===")
    for story in stories[:10]:
        epic_key = story.epic.jira_key if story.epic else "N/A"
        print(f"{story.jira_key}: {story.title} [Epic: {epic_key}]")
    
    # Get tasks
    tasks = session.query(BacklogTask).filter(BacklogTask.jira_key.isnot(None)).all()
    print(f"\n=== TASKS ({len(tasks)} total) ===")
    for task in tasks[:10]:
        story_key = task.story.jira_key if task.story else "N/A"
        print(f"{task.jira_key}: {task.title} [Story: {story_key}]")
