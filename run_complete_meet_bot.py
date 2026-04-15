"""
Complete Meet Bot - Production Ready

This is the COMPLETE end-to-end automation:
1. Join Google Meet
2. Record audio
3. Transcribe speech
4. Detect meeting type
5. Run appropriate pipeline
6. Create approval request
7. Send Telegram notification AUTOMATICALLY
8. Wait for approval
9. Update Jira

Usage:
    python run_complete_meet_bot.py <meet_link>
    python run_complete_meet_bot.py <meet_link> --type daily_standup
    python run_complete_meet_bot.py <meet_link> --no-detect

Example:
    python run_complete_meet_bot.py https://meet.google.com/abc-defg-hij
"""
import asyncio
import os
import sys
import threading
from pathlib import Path
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

sys.path.insert(0, os.path.join(os.path.dirname(__file__)))

from backend.speech.audio_recorder import record_system_audio
from backend.meeting.meet_client import join_meeting
from backend.speech.whisperai.transcribe import transcribe_audio_from_path
from backend.pipelines.intelligent_meet_bot import MeetingTypeDetector
from backend.pipelines.scrum_pipeline import ScrumPipeline
from backend.pipelines.sprint_planning_pipeline import SprintPlanningPipeline


async def complete_meet_bot(meet_link: str, force_type: str = None):
    """
    Complete meet bot workflow.
    
    Args:
        meet_link: Google Meet URL
        force_type: Force specific meeting type (daily_standup, sprint_planning)
    """
    bot_id = datetime.now().strftime('%Y%m%d_%H%M%S')
    
    print("\n" + "=" * 80)
    print("COMPLETE MEET BOT - Production Ready")
    print("=" * 80)
    print(f"Bot ID: {bot_id}")
    print(f"Meet Link: {meet_link}")
    print(f"Force Type: {force_type or 'Auto-detect'}")
    print("=" * 80 + "\n")
    
    # Create output directory
    output_dir = "backend/data/meetings"
    Path(output_dir).mkdir(parents=True, exist_ok=True)
    
    audio_file = os.path.join(output_dir, f"{bot_id}_audio.wav")
    transcript_file = os.path.join(output_dir, f"{bot_id}_transcript.txt")
    
    try:
        # ====================================================================
        # PHASE 1: JOIN MEETING AND RECORD
        # ====================================================================
        print("=" * 80)
        print("PHASE 1: JOIN MEETING AND RECORD")
        print("=" * 80 + "\n")
        
        stop_event = threading.Event()
        
        # Start meeting bot
        print("1. Joining Google Meet...")
        print("   (Chrome will open, bot will join as 'bot')")
        meeting_task = asyncio.create_task(join_meeting(meet_link))
        
        # Wait for bot to join
        print("2. Waiting for bot to join (15 seconds)...")
        await asyncio.sleep(15)
        
        # Start recording
        print(f"3. Recording audio to: {audio_file}")
        print("   (Recording system audio...)")
        recording_task = asyncio.create_task(
            asyncio.to_thread(record_system_audio, audio_file, stop_event=stop_event)
        )
        
        # Wait for meeting to end
        print("4. Meeting in progress...")
        print("   (Bot will leave when alone for 30 seconds)")
        await meeting_task
        
        # Stop recording
        print("5. Meeting ended, stopping recording...")
        stop_event.set()
        await recording_task
        
        print(f"\nAudio saved: {audio_file}\n")
        
        # ====================================================================
        # PHASE 2: TRANSCRIBE
        # ====================================================================
        print("=" * 80)
        print("PHASE 2: TRANSCRIBE AUDIO")
        print("=" * 80 + "\n")
        
        print(f"Transcribing: {audio_file}")
        print("(This may take a few minutes...)")
        transcript = transcribe_audio_from_path(audio_file)
        
        # Save transcript
        with open(transcript_file, 'w', encoding='utf-8') as f:
            f.write(transcript)
        
        print(f"Transcript saved: {transcript_file}")
        print(f"Length: {len(transcript)} characters")
        print(f"Preview: {transcript[:200]}...\n")
        
        # ====================================================================
        # PHASE 3: DETECT MEETING TYPE
        # ====================================================================
        print("=" * 80)
        print("PHASE 3: DETECT MEETING TYPE")
        print("=" * 80 + "\n")
        
        if force_type:
            detected_type = force_type
            confidence = 1.0
            print(f"Using forced type: {detected_type}")
        else:
            detector = MeetingTypeDetector()
            detection = detector.detect(transcript)
            detected_type = detection.meeting_type
            confidence = detection.confidence
            
            print(f"Detected: {detected_type}")
            print(f"Confidence: {confidence:.0%}")
            print(f"Keywords: {', '.join(detection.keywords_found[:5])}")
            
            if detected_type == 'unknown':
                print("\nERROR: Could not detect meeting type")
                print("Please run again with --type parameter")
                print("Example: python run_complete_meet_bot.py <link> --type daily_standup")
                return {
                    'status': 'failed',
                    'error': 'Unknown meeting type',
                    'transcript_file': transcript_file
                }
        
        print()
        
        # ====================================================================
        # PHASE 4: RUN PIPELINE
        # ====================================================================
        print("=" * 80)
        print(f"PHASE 4: RUN {detected_type.upper()} PIPELINE")
        print("=" * 80 + "\n")
        
        if detected_type == 'daily_standup':
            print("Running Scrum Pipeline...")
            pipeline = ScrumPipeline(require_telegram_approval=True)
            result = pipeline.run(
                transcript_path=transcript_file,
                update_jira=True,
                dry_run=False
            )
            
            pipeline_result = {
                'pipeline': 'scrum',
                'status': result.status,
                'approval_id': result.approval_id,
                'total_actions': result.total_actions,
                'tasks_completed': result.tasks_completed,
                'tasks_updated': result.tasks_updated
            }
        
        elif detected_type == 'sprint_planning':
            print("Running Sprint Planning Pipeline...")
            pipeline = SprintPlanningPipeline(require_telegram_approval=True)
            result = pipeline.run(
                transcript_path=transcript_file,
                create_in_jira=True,
                dry_run=False
            )
            
            pipeline_result = {
                'pipeline': 'sprint_planning',
                'status': result.status,
                'approval_id': result.approval_id,
                'sprint_goal': result.sprint_goal if hasattr(result, 'sprint_goal') else 'N/A',
                'stories_committed': result.stories_committed if hasattr(result, 'stories_committed') else 0
            }
        
        elif detected_type in ['pm_backlog', 'grooming']:
            print("ERROR: Backlog pipeline not yet integrated")
            print("Please use sprint_planning or daily_standup for now")
            return {
                'status': 'failed',
                'error': 'Backlog pipeline not integrated',
                'transcript_file': transcript_file
            }
        
        else:
            print(f"ERROR: Unknown meeting type: {detected_type}")
            return {
                'status': 'failed',
                'error': f'Unknown meeting type: {detected_type}',
                'transcript_file': transcript_file
            }
        
        # ====================================================================
        # PHASE 5: SUCCESS
        # ====================================================================
        print("\n" + "=" * 80)
        print("COMPLETE MEET BOT - SUCCESS!")
        print("=" * 80)
        print(f"Meeting Type: {detected_type}")
        print(f"Confidence: {confidence:.0%}")
        print(f"Pipeline: {pipeline_result['pipeline']}")
        print(f"Status: {pipeline_result['status']}")
        print(f"Approval ID: #{pipeline_result['approval_id']}")
        print()
        print("Telegram notification sent automatically!")
        print("Check your Telegram and click 'Approve' to update Jira")
        print("=" * 80 + "\n")
        
        return {
            'status': 'success',
            'bot_id': bot_id,
            'audio_file': audio_file,
            'transcript_file': transcript_file,
            'detected_type': detected_type,
            'confidence': confidence,
            'pipeline_result': pipeline_result
        }
    
    except Exception as e:
        print(f"\nERROR: {e}")
        import traceback
        traceback.print_exc()
        return {
            'status': 'failed',
            'error': str(e)
        }


def main():
    """Main entry point."""
    
    # Check for meet link
    if len(sys.argv) < 2:
        print("ERROR: No meet link provided")
        print()
        print("Usage:")
        print("  python run_complete_meet_bot.py <meet_link>")
        print("  python run_complete_meet_bot.py <meet_link> --type daily_standup")
        print("  python run_complete_meet_bot.py <meet_link> --no-detect")
        print()
        print("Example:")
        print("  python run_complete_meet_bot.py https://meet.google.com/abc-defg-hij")
        sys.exit(1)
    
    meet_link = sys.argv[1]
    
    # Check for force type
    force_type = None
    if '--type' in sys.argv:
        idx = sys.argv.index('--type')
        if idx + 1 < len(sys.argv):
            force_type = sys.argv[idx + 1]
            if force_type not in ['daily_standup', 'sprint_planning', 'pm_backlog', 'grooming']:
                print(f"ERROR: Invalid type: {force_type}")
                print("Valid types: daily_standup, sprint_planning, pm_backlog, grooming")
                sys.exit(1)
    
    # Run complete workflow
    result = asyncio.run(complete_meet_bot(meet_link, force_type))
    
    sys.exit(0 if result.get('status') == 'success' else 1)


if __name__ == "__main__":
    main()
