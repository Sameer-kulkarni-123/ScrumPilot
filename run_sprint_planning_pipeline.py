"""
Run Sprint Planning Pipeline

This script runs the sprint planning pipeline:
1. Extracts sprint plan from the provided transcript
2. Creates Telegram project-selection request
3. After PM project selection: creates sprint in Jira and moves stories
"""

import argparse
import sys
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

from backend.pipelines.sprint_planning_pipeline import SprintPlanningPipeline


def main() -> None:
    """Run sprint planning pipeline from a transcript path."""
    parser = argparse.ArgumentParser(description="Run the Sprint Planning pipeline")
    parser.add_argument(
        "transcript",
        nargs="?",
        help="Path to the sprint planning transcript file",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Skip actual Jira writes",
    )
    args = parser.parse_args()

    if not args.transcript:
        print("Usage:")
        print("  python .\\run_sprint_planning_pipeline.py <transcript_path>")
        print()
        print("Example:")
        print("  python .\\run_sprint_planning_pipeline.py backend\\data\\meetings\\my_sprint_transcript.txt")
        sys.exit(1)

    transcript_path = args.transcript
    if not Path(transcript_path).exists():
        print(f"Transcript not found: {transcript_path}")
        sys.exit(1)

    print("=" * 80)
    print("SPRINT PLANNING PIPELINE - DIRECT RUN")
    print("=" * 80)
    print(f"Transcript: {transcript_path}")
    print(f"Dry run   : {args.dry_run}")
    print("=" * 80)

    pipeline = SprintPlanningPipeline(require_telegram_approval=True)
    result = pipeline.run(
        transcript_path=transcript_path,
        create_in_jira=not args.dry_run,
        dry_run=args.dry_run,
    )

    print("\n" + "=" * 80)
    print("PIPELINE RESULT")
    print("=" * 80)
    print(f"Status: {result.status}")

    if hasattr(result, "sprint_goal"):
        print(f"Sprint Goal: {result.sprint_goal}")
    if hasattr(result, "stories_committed"):
        print(f"Stories Committed: {result.stories_committed}")

    if result.status == "paused":
        print("\nTelegram notification sent.")
        print("Check Telegram and choose an existing Scrum project or create a new one.")
    elif result.status == "completed":
        print("\nSprint pipeline completed.")

    print("=" * 80)


if __name__ == "__main__":
    main()
