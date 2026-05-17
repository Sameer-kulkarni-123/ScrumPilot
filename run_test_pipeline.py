"""
Real-time test runner for the backlog pipeline.

Modes:
  Default    - bypasses Telegram approval and creates Jira tickets directly.
  --telegram - enables human-in-the-loop: the pipeline pauses after
               decomposition, asks the PM to select an existing Scrum project
               or create a new Scrum project, then resumes Jira creation.

Usage:
    python run_test_pipeline.py
    python run_test_pipeline.py --telegram
    python run_test_pipeline.py --dry-run
    python run_test_pipeline.py --pm path/to/pm_transcript.txt
    python run_test_pipeline.py --groom path/to/grooming_transcript.txt

For --telegram mode, the bot must be running in a separate terminal:
    .\\.venv\\Scripts\\python.exe backend\\telegram\\bot.py
"""

import argparse
import sys

from dotenv import load_dotenv

load_dotenv()

from backend.pipelines.backlog_pipeline import BacklogPipeline, PipelineConfig


DEFAULT_PM_TRANSCRIPT = "backend/data/pm_meetings/example_pm_transcript.txt"
DEFAULT_GROOM_TRANSCRIPT = "backend/data/grooming_meetings/example_grooming_transcript.txt"


def print_intro(use_telegram: bool, dry_run: bool, pm_path: str, groom_path: str) -> None:
    print("=" * 80)
    print("SCRUMPILOT - REAL-TIME BACKLOG E2E TEST")
    print("=" * 80)
    print(f"PM transcript   : {pm_path}")
    print(f"Groom transcript: {groom_path}")
    print(f"Dry run         : {dry_run}")

    if use_telegram:
        print("Telegram project selection: ENABLED")
        print()
        print("  Make sure the bot is running in another terminal:")
        print("    .\\.venv\\Scripts\\python.exe backend\\telegram\\bot.py")
        print()
        print("  Flow:")
        print("    1. Pipeline extracts and decomposes the backlog")
        print("    2. Telegram asks PM to use an existing Scrum project or create a new one")
        print("    3. PM selects the project")
        print("    4. Bot resumes automatically and creates Jira epics, stories, and subtasks")
    else:
        print("Telegram project selection: DISABLED (direct Jira creation)")

    print("=" * 80)
    print()


def print_result(result) -> None:
    print("\n" + "=" * 80)
    print("PIPELINE RESULT")
    print("=" * 80)
    print(f"Status       : {result.status}")
    print(f"Pipeline ID  : {result.pipeline_id}")
    print(f"Epics        : {result.total_epics}")
    print(f"Stories      : {result.total_stories}")
    print(f"Tasks        : {result.total_tasks}")

    if hasattr(result, "jira_items_created"):
        print(f"Jira items   : {result.jira_items_created}")

    if result.warnings:
        print(f"\nWarnings ({len(result.warnings)}):")
        for warning in result.warnings:
            print(f"  - {warning}")

    if result.errors:
        print(f"\nErrors ({len(result.errors)}):")
        for error in result.errors:
            print(f"  - {error}")

    print("\n" + "=" * 80)

    status_str = str(result.status).lower()
    if "paused" in status_str:
        print("\nPipeline paused for PM project selection.")
        print("Check Telegram and choose an existing Scrum project or create a new one.")
        print("After PM input, the bot will resume Jira creation automatically.")
        return

    if "completed" in status_str:
        print("\nPipeline completed.")
        print("Check the newest files in backend\\data\\checkpoints and backend\\data\\jira.")
        print("Example:")
        print("  Get-ChildItem backend\\data\\checkpoints | Sort-Object LastWriteTime -Descending | Select-Object -First 3 Name,LastWriteTime")
        print("  Get-ChildItem backend\\data\\jira | Sort-Object LastWriteTime -Descending | Select-Object -First 3 Name,LastWriteTime")
        return

    print(f"\nPipeline ended with status: {result.status}")
    sys.exit(1)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="ScrumPilot - real-time backlog E2E test runner"
    )
    parser.add_argument(
        "--pm",
        default=DEFAULT_PM_TRANSCRIPT,
        help="Path to PM meeting transcript",
    )
    parser.add_argument(
        "--groom",
        default=DEFAULT_GROOM_TRANSCRIPT,
        help="Path to grooming transcript",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Skip actual Jira writes",
    )
    parser.add_argument(
        "--telegram",
        action="store_true",
        help="Enable Telegram project selection (requires bot running)",
    )
    args = parser.parse_args()

    print_intro(
        use_telegram=args.telegram,
        dry_run=args.dry_run,
        pm_path=args.pm,
        groom_path=args.groom,
    )

    config = PipelineConfig(
        require_telegram_approval=args.telegram,
        create_in_jira=not args.dry_run,
        jira_dry_run=args.dry_run,
    )
    pipeline = BacklogPipeline(config=config)

    result = pipeline.run(
        pm_transcript_path=args.pm,
        grooming_transcript_path=args.groom,
        create_in_jira=not args.dry_run,
        dry_run=args.dry_run,
    )

    print_result(result)


if __name__ == "__main__":
    main()
