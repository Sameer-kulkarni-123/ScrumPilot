"""
Verify routing metadata on all Jira items in the database.

Shows: jira_key | title | project_key | team | component | confidence | source
Run after the backlog pipeline to confirm routing decisions are persisted.

Usage:
    python verify_routing.py
"""
from dotenv import load_dotenv
load_dotenv()

from backend.db.connection import get_session
from backend.db.models import Epic, Story, BacklogTask, ScrumAction


def _conf_flag(conf):
    if conf is None:
        return "❓"
    if conf >= 0.75:
        return "🟢"
    if conf >= 0.40:
        return "🟡"
    return "🔴"


def show_routing():
    with get_session() as session:
        epics = session.query(Epic).order_by(Epic.jira_key).all()

        if not epics:
            print("\n⚠️  No epics in database. Run the pipeline first.")
            return

        print("\n" + "=" * 100)
        print("ROUTING METADATA VERIFICATION")
        print("=" * 100)

        total = 0
        routed = 0
        high = medium = low = unset = 0

        for epic in epics:
            conf = epic.routing_confidence
            flag = _conf_flag(conf)
            total += 1
            if conf is not None:
                routed += 1
                if conf >= 0.75:
                    high += 1
                elif conf >= 0.40:
                    medium += 1
                else:
                    low += 1
            else:
                unset += 1

            print(
                f"\n{flag} EPIC  {epic.jira_key or 'NO-KEY':<12} "
                f"project={epic.jira_project_key or '?':<10} "
                f"team={epic.team_name or '?':<12} "
                f"comp={epic.jira_component or '?':<12} "
                f"conf={f'{conf:.2f}' if conf else '?':<6} "
                f"src={epic.routing_source or '?'}"
            )
            print(f"         {epic.title[:80]}")

            stories = session.query(Story).filter(Story.epic_id == epic.id).all()
            for story in stories:
                s_conf = story.routing_confidence
                s_flag = _conf_flag(s_conf)
                total += 1
                if s_conf is not None:
                    routed += 1
                    if s_conf >= 0.75:
                        high += 1
                    elif s_conf >= 0.40:
                        medium += 1
                    else:
                        low += 1
                else:
                    unset += 1

                print(
                    f"  {s_flag} STORY {story.jira_key or 'NO-KEY':<12} "
                    f"project={story.jira_project_key or '?':<10} "
                    f"team={story.team_name or '?':<12} "
                    f"conf={f'{s_conf:.2f}' if s_conf else '?':<6} "
                    f"src={story.routing_source or '?'}"
                )
                print(f"         {story.title[:75]}")

                tasks = session.query(BacklogTask).filter(BacklogTask.story_id == story.id).all()
                for task in tasks:
                    t_conf = task.routing_confidence
                    t_flag = _conf_flag(t_conf)
                    total += 1
                    if t_conf is not None:
                        routed += 1
                    else:
                        unset += 1

                    print(
                        f"    {t_flag} TASK  {task.jira_key or 'NO-KEY':<12} "
                        f"project={task.jira_project_key or '?':<10} "
                        f"conf={f'{t_conf:.2f}' if t_conf else '?'}"
                    )
                    print(f"           {task.title[:70]}")

        print("\n" + "=" * 100)
        print(f"SUMMARY: {total} items total | {routed} routed | {unset} unset")
        print(f"  🟢 High (>=0.75): {high}  |  🟡 Medium (0.40-0.74): {medium}  |  🔴 Low (<0.40): {low}")
        print("=" * 100 + "\n")


if __name__ == "__main__":
    show_routing()
