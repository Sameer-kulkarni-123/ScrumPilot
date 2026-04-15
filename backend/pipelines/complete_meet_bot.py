"""
Complete Meet Bot - Production Ready

This is the COMPLETE end-to-end automation:
1. Join Google Meet
2. Record audio
3. Transcribe speech
4. Detect meeting type
5. Run appropriate pipeline
6. Create approval request
7. Send Telegram notification (AUTOMATICALLY)
8. Wait for approval
9. Update Jira

This is the real production system - no manual steps needed!
"""
import asyncio
import os
import sys
import json
import logging
import threading
from pathlib import Path
from datetime import datetime
from typing import Optional

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from backend.speech.audio_recorder import record_system_audio
from backend.meeting.meet_client import join_meeting
from backend.speech.whisperai.transcribe import transcribe_audio_from_path
from backend.pipelines.intelligent_meet_bot import MeetingTypeDetector
from backend.pipelines.scrum_pipeline import ScrumPipeline
from backend.pipelines.sprint_planning_pipeline import SprintPlanningPipeline

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


async def complete_meet_bot_workflow(
    meet_link: str,
    output_dir: str = "backend/data/meetings",
    auto_detect: bool = True,
    force_type: Optional[str] = None
):
    """
    Complete meet bot workflow - joins meeting, records, transcribes,
    detects type, runs pipeline, sends notification.
    
    Args:
        meet_link: Google Meet URL
        output_dir: Directory to save audio and transcript
        auto_detect: Automatically detect meeting type
        force_type: Force specific meeting type (pm_backlog, sprint_planning, daily_standup)
    
    Returns:
        dict with results
    """
    bot_id = datetime.now().strftime('%Y%m%d_%H%M%S')
    
    print("\n" + "=" * 80)
    print("COMPLETE MEET BOT - Production Ready")
    print("=" * 80)
    print(f"Bot ID: {bot_id}")
    print(f"Meet Link: {meet_link}")
    print(f"Auto Detect: {auto_detect}")
    print(f"Force Type: {force_type}")
    print("=" * 80 + "\n")
    
    # Create output directory
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
        meeting_task = asyncio.create_task(join_meeting(meet_link))
        
        # Wait for bot to join
        print("2. Waiting for bot to join (15 seconds)...")
        await asyncio.sleep(15)
        
        # Start recording
        print(f"3. Recording audio to: {audio_file}")
        recording_task = asyncio.create_task(
            asyncio.to_thread(record_system_audio, audio_file, stop_event=stop_event)
        )
        
        # Wait for meeting to end
        print("4. Meeting in progress... (bot will leave when alone for 30s)")
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
        elif auto_detect:
            detector = MeetingTypeDetector()
            detection = detector.detect(transcript)
            detected_type = detection.meeting_type
            confidence = detection.confidence
            
            print(f"Detected: {detected_type}")
            print(f"Confidence: {confidence:.0%}")
            print(f"Keywords: {', '.join(detection.keywords_found[:5])}")
            
            if detected_type == 'unknown':
                print("\nERROR: Could not detect meeting type")
                print("Please specify meeting type manually with --type parameter")
                return {
                    'status': 'failed',
                    'error': 'Unknown meeting type',
                    'transcript_file': transcript_file
                }
        else:
            print("ERROR: Auto-detect disabled and no forced type specified")
            return {
                'status': 'failed',
                'error': 'No meeting type specified',
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
        # PHASE 5: RESULTS
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
        logger.error(f"Meet bot failed: {e}", exc_info=True)
        print(f"\nERROR: {e}")
        return {
            'status': 'failed',
            'error': str(e)
        }


async def main():
    """Main entry point."""
    from dotenv import load_dotenv
    load_dotenv()
    
    # Get meet link from command line or environment
    if len(sys.argv) > 1:
        meet_link = sys.argv[1]
    else:
        meet_link = os.getenv('MEET_LINK')
        if not meet_link:
            print("ERROR: No meet link provided")
            print("Usage: python complete_meet_bot.py <meet_link>")
            print("   or: Set MEET_LINK in .env file")
            sys.exit(1)
    
    # Check for force type
    force_type = None
    if '--type' in sys.argv:
        idx = sys.argv.index('--type')
        if idx + 1 < len(sys.argv):
            force_type = sys.argv[idx + 1]
    
    auto_detect = '--no-detect' not in sys.argv
    
    # Run complete workflow
    result = await complete_meet_bot_workflow(
        meet_link=meet_link,
        auto_detect=auto_detect,
        force_type=force_type
    )
    
    # Print result
    if '--json' in sys.argv:
        print(json.dumps(result, indent=2, default=str))
    
    return result


if __name__ == "__main__":
    result = asyncio.run(main())
    sys.exit(0 if result.get('status') == 'success' else 1)
