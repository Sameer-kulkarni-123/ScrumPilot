"""
Run Backlog Pipeline

This script runs the complete backlog pipeline:
1. Extracts epics from PM meeting transcript
2. Extracts grooming details from grooming transcript
3. Calculates WSJF scores
4. Decomposes epics into stories and tasks
5. Creates Telegram approval request
6. After approval: Creates complete hierarchy in Jira
"""
from dotenv import load_dotenv
load_dotenv()

from backend.pipelines.backlog_pipeline import BacklogPipeline, PipelineConfig

def main():
    """Run backlog pipeline with example transcripts."""
    
    print("=" * 80)
    print("BACKLOG PIPELINE - Direct Run")
    print("=" * 80)
    
    # Configure pipeline
    config = PipelineConfig(
        require_telegram_approval=True,  # Will pause for Telegram approval
        create_in_jira=True,
        jira_dry_run=False
    )
    pipeline = BacklogPipeline(config=config)
    
    # Run pipeline with example transcripts
    result = pipeline.run(
        pm_transcript_path="backend/data/pm_meetings/example_pm_transcript.txt",
        grooming_transcript_path="backend/data/grooming_meetings/example_grooming_transcript.txt",
        create_in_jira=True,  # Will create in Jira after approval
        dry_run=False
    )
    
    print("\n" + "=" * 80)
    print("PIPELINE RESULT")
    print("=" * 80)
    print(f"Status: {result.status}")
    print(f"Pipeline ID: {result.pipeline_id}")
    print(f"Total Epics: {result.total_epics}")
    print(f"Total Stories: {result.total_stories}")
    print(f"Total Tasks: {result.total_tasks}")
    
    if result.status == "paused":
        print("\n📱 Telegram notification sent!")
        print("Check your Telegram and click 'Approve' to create in Jira")
    elif result.status == "completed":
        print(f"\n✅ Jira items created: {result.jira_items_created}")
    
    print("=" * 80)

if __name__ == "__main__":
    main()
