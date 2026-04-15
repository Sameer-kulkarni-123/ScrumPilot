"""
Run Sprint Planning Pipeline

This script runs the sprint planning pipeline:
1. Extracts sprint plan from transcript
2. Creates Telegram approval request
3. After approval: Creates sprint in Jira and moves stories
"""
from dotenv import load_dotenv
load_dotenv()

from backend.pipelines.sprint_planning_pipeline import SprintPlanningPipeline

def main():
    """Run sprint planning pipeline with example transcript."""
    
    print("=" * 80)
    print("SPRINT PLANNING PIPELINE - Direct Run")
    print("=" * 80)
    
    # Configure pipeline
    pipeline = SprintPlanningPipeline(
        require_telegram_approval=True  # Will pause for Telegram approval
    )
    
    # Run pipeline with example transcript
    result = pipeline.run(
        transcript_path="backend/data/sprint_planning/example_sprint_planning_transcript.txt",
        create_in_jira=True,  # Will create sprint in Jira after approval
        dry_run=False
    )
    
    print("\n" + "=" * 80)
    print("PIPELINE RESULT")
    print("=" * 80)
    print(f"Status: {result.status}")
    
    if hasattr(result, 'sprint_goal'):
        print(f"Sprint Goal: {result.sprint_goal}")
    if hasattr(result, 'stories_committed'):
        print(f"Stories Committed: {result.stories_committed}")
    
    if result.status == "paused":
        print("\n📱 Telegram notification sent!")
        print("Check your Telegram and click 'Approve' to create sprint in Jira")
    elif result.status == "completed":
        print(f"\n✅ Sprint created in Jira!")
    
    print("=" * 80)

if __name__ == "__main__":
    main()
