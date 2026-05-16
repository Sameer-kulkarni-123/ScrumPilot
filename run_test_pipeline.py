"""
Real-time test runner for the backlog pipeline.

Modes:
  Default   — bypasses Telegram approval, creates Jira tickets directly.
  --telegram — enables human-in-the-loop: pipeline pauses after decomposition,
               sends Telegram notification to PM, waits for approval before
               creating Jira tickets.

Usage:
    python run_test_pipeline.py                          # direct Jira creation
    python run_test_pipeline.py --telegram               # HITL Telegram approval
    python run_test_pipeline.py --dry-run                # no actual Jira writes
    python run_test_pipeline.py --pm   path/to/pm_transcript.txt
    python run_test_pipeline.py --groom path/to/grooming_transcript.txt

For --telegram mode, the bot must be running in a separate terminal:
    python backend/telegram/bot.py
"""
import argparse
import sys
from dotenv import load_dotenv
load_dotenv()

from backend.pipelines.backlog_pipeline import BacklogPipeline, PipelineConfig


DEFAULT_PM_TRANSCRIPT    = "backend/data/pm_meetings/example_pm_transcript.txt"
DEFAULT_GROOM_TRANSCRIPT = "backend/data/grooming_meetings/example_grooming_transcript.txt"


def main():
    parser = argparse.ArgumentParser(description="ScrumPilot — real-time E2E test runner")
    parser.add_argument("--pm",       default=DEFAULT_PM_TRANSCRIPT,    help="Path to PM meeting transcript")
    parser.add_argument("--groom",    default=DEFAULT_GROOM_TRANSCRIPT, help="Path to grooming transcript")
    parser.add_argument("--dry-run",  action="store_true",              help="Skip actual Jira writes")
    parser.add_argument("--telegram", action="store_true",
                        help="Enable human-in-the-loop Telegram approval (requires bot running)")
    args = parser.parse_args()

    use_telegram = args.telegram

    print("=" * 80)
    print("SCRUMPILOT — REAL-TIME E2E TEST")
    print("=" * 80)
    print(f"PM transcript   : {args.pm}")
    print(f"Groom transcript: {args.groom}")
    print(f"Dry run         : {args.dry_run}")
    if use_telegram:
        print("Telegram approval: ENABLED  ← pipeline will pause for PM approval")
        print()
        print("  Make sure the bot is running in another terminal:")
        print("    python backend/telegram/bot.py")
        print()
        print("  Flow:")
        print("    1. Pipeline extracts + decomposes backlog")
        print("    2. Telegram notification sent to PM with ✅ Approve / ❌ Reject")
        print("    3. PM approves → bot creates Jira tickets + saves to DB")
        print("    4. Run verify_routing.py to inspect results")
    else:
        print("Telegram approval: DISABLED (direct Jira creation)")
    print("=" * 80 + "\n")

    config = PipelineConfig(
        require_telegram_approval=use_telegram,
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
        print(f"\n⚠️  Warnings ({len(result.warnings)}):")
        for w in result.warnings:
            print(f"   - {w}")

    if result.errors:
        print(f"\n❌ Errors ({len(result.errors)}):")
        for e in result.errors:
            print(f"   - {e}")

    print("\n" + "=" * 80)

    status_str = str(result.status).lower()
    if "completed" in status_str or "paused" in status_str:
        print("\n✅ Done. Run verify_routing.py to inspect routing metadata:")
        print("   python verify_routing.py")
    else:
        print(f"\n❌ Pipeline ended with status: {result.status}")
        sys.exit(1)


if __name__ == "__main__":
    main()
