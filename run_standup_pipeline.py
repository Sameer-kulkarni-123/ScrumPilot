"""
Run Standup Pipeline Manually

This script runs the standup pipeline and pauses for real Telegram approval.
NO auto-approval - you must approve via Telegram.
"""
import os
import sys
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

sys.path.insert(0, os.path.join(os.path.dirname(__file__)))

from backend.pipelines.scrum_pipeline import ScrumPipeline


def main():
    print("\n" + "=" * 80)
    print("MANUAL STANDUP PIPELINE EXECUTION")
    print("=" * 80)
    print("\nThis will:")
    print("  1. Extract actions from standup transcript")
    print("  2. Create approval request")
    print("  3. Send Telegram notification")
    print("  4. PAUSE and wait for your approval via Telegram")
    print("  5. (After you approve) Jira updates happen automatically")
    print("\n" + "=" * 80 + "\n")
    
    # Use the REAL transcript with actual ticket IDs
    transcript_path = "backend/data/scrum_meetings/test_standup_sprint24.txt"
    
    if not Path(transcript_path).exists():
        print(f"❌ Transcript not found: {transcript_path}")
        return 1
    
    print(f"📄 Using transcript: {transcript_path}\n")
    
    # Create pipeline with approval required
    pipeline = ScrumPipeline(require_telegram_approval=True)
    
    # Run pipeline
    result = pipeline.run(
        transcript_path=transcript_path,
        update_jira=True,
        dry_run=False
    )
    
    print("\n" + "=" * 80)
    print("PIPELINE EXECUTION COMPLETE")
    print("=" * 80)
    print(f"Status: {result.status}")
    print(f"Approval ID: #{result.approval_id}")
    print("\n📱 Check your Telegram for the approval notification!")
    print("👆 Click 'Approve' button to execute Jira updates")
    print("=" * 80 + "\n")
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
