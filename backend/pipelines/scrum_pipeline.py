"""
Scrum Pipeline — Wires the meet_bot transcript through the ScrumExtractorAgent
and JiraAgent to automatically update Jira from a scrum meeting.
"""

import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from backend.agents.scrum_extractor import ScrumExtractorAgent
from backend.agents.jira_agent import JiraAgent


def run_scrum_pipeline(transcript: str, dry_run: bool = False) -> dict:
    """
    Full pipeline: transcript → extract actions → execute on Jira.

    Args:
        transcript: The diarized meeting transcript text.
        dry_run: If True, only extract actions without executing them on Jira.

    Returns:
        dict with keys: actions (list), report (str | None)
    """
    print("=" * 50)
    print("SCRUM PIPELINE — Starting")
    print("=" * 50)

    # ── Step 1: Extract actions ───────────────────────────────────────────
    print("\n🔍 Step 1: Extracting scrum actions from transcript...")
    extractor = ScrumExtractorAgent()
    actions = extractor.extract_actions(transcript)

    print(f"   Found {len(actions)} action(s):")
    for i, a in enumerate(actions, 1):
        print(f"   {i}. [{a.get('action')}] {a.get('summary', 'N/A')}")

    if dry_run:
        print("\n⏸️  Dry-run mode — skipping Jira execution.")
        print("\n📋 Extracted actions:")
        print(json.dumps(actions, indent=2))
        return {"actions": actions, "report": None}

    # ── Step 2: Execute on Jira ───────────────────────────────────────────
    print("\n🚀 Step 2: Executing actions on Jira via LangChain agent...")
    jira_agent = JiraAgent()
    report = jira_agent.execute_actions(actions)

    print("\n📋 Agent Report:")
    print(report)

    print("\n" + "=" * 50)
    print("SCRUM PIPELINE — Complete")
    print("=" * 50)

    return {"actions": actions, "report": report}


def run_from_transcript_file(path: str, dry_run: bool = False) -> dict:
    """Convenience: read a transcript file and run the pipeline."""
    with open(path, "r", encoding="utf-8") as f:
        transcript = f.read()
    return run_scrum_pipeline(transcript, dry_run=dry_run)


# ── CLI entry point ──────────────────────────────────────────────────────────

if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv()

    # Default to the example transcript for quick testing
    here = os.path.dirname(__file__)
    default_path = os.path.join(here, "..", "agents", "example_transcript.txt")

    # Positional args are non-flag arguments (ignore --dry-run, --json, etc.)
    positional_args = [a for a in sys.argv[1:] if not a.startswith("--")]
    transcript_path = positional_args[0] if positional_args else default_path
    dry = "--dry-run" in sys.argv or "--dry" in sys.argv

    result = run_from_transcript_file(transcript_path, dry_run=dry)

    # Dump raw JSON for piping
    if "--json" in sys.argv:
        print(json.dumps(result, indent=2, default=str))
