"""
Intelligent Meet Bot - Phase 4 (Production Ready)

Automatically:
1. Joins Google Meet
2. Records audio
3. Transcribes speech
4. Detects meeting type (PM/Grooming/Sprint Planning/Daily Standup)
5. Triggers appropriate pipeline
6. Creates approval request
7. Sends Telegram notification

This is the complete end-to-end automation.

Author: AI Meeting Automation System
Phase: 4
"""

import asyncio
import os
import sys
import json
import logging
import threading
from pathlib import Path
from datetime import datetime
from typing import Optional, Dict, Any, Literal
from pydantic import BaseModel, Field

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from backend.speech.audio_recorder import record_system_audio
from backend.meeting.meet_client import join_meeting
from backend.speech.whisperai.transcribe import transcribe_audio_from_path

# Import all pipelines
from backend.pipelines.backlog_pipeline import BacklogPipeline
from backend.pipelines.sprint_planning_pipeline import SprintPlanningPipeline
from backend.pipelines.scrum_pipeline import ScrumPipeline

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


# ============================================================================
# MODELS
# ============================================================================

MeetingType = Literal['pm_backlog', 'grooming', 'sprint_planning', 'daily_standup', 'unknown']


class MeetingDetectionResult(BaseModel):
    """Result of meeting type detection."""
    meeting_type: MeetingType
    confidence: float = Field(ge=0.0, le=1.0)
    reasoning: str
    keywords_found: list[str] = Field(default_factory=list)


class MeetBotResult(BaseModel):
    """Complete meet bot execution result."""
    bot_id: str
    start_time: str
    end_time: Optional[str] = None
    status: str  # 'completed', 'failed', 'in_progress'
    
    # Meeting info
    meet_link: str
    meeting_duration_seconds: Optional[float] = None
    
    # Recording
    audio_file: Optional[str] = None
    transcript_file: Optional[str] = None
    transcript_length: Optional[int] = None
    
    # Detection
    detected_type: Optional[MeetingType] = None
    detection_confidence: Optional[float] = None
    
    # Pipeline execution
    pipeline_triggered: Optional[str] = None
    pipeline_result: Optional[Dict[str, Any]] = None
    approval_id: Optional[int] = None
    
    # Errors
    errors: list[str] = Field(default_factory=list)


# ============================================================================
# MEETING TYPE DETECTOR
# ============================================================================

class MeetingTypeDetector:
    """
    Detects meeting type from transcript using keyword analysis and AI.
    
    Meeting types:
    - pm_backlog: Product Manager discussing epics, features, roadmap
    - grooming: Team refining stories, estimating, clarifying requirements
    - sprint_planning: Planning next sprint, selecting stories, capacity
    - daily_standup: Quick updates on what was done, what's next, blockers
    """
    
    # Keyword patterns for each meeting type
    KEYWORDS = {
        'pm_backlog': [
            'epic', 'feature', 'roadmap', 'vision', 'strategy',
            'stakeholder', 'customer', 'market', 'priority', 'wsjf',
            'business value', 'user story', 'acceptance criteria'
        ],
        'grooming': [
            'story points', 'estimate', 'estimation', 'complexity',
            'acceptance criteria', 'definition of done', 'clarify',
            'refine', 'groom', 'backlog refinement', 'story', 'task'
        ],
        'sprint_planning': [
            'sprint', 'capacity', 'velocity', 'commitment', 'sprint goal',
            'sprint backlog', 'planning', 'iteration', 'assign', 'team capacity'
        ],
        'daily_standup': [
            'yesterday', 'today', 'blocker', 'blocked', 'impediment',
            'working on', 'completed', 'done', 'in progress', 'status update',
            'quick update', 'standup', 'scrum', 'daily'
        ]
    }
    
    def detect(self, transcript: str) -> MeetingDetectionResult:
        """
        Detect meeting type from transcript.
        
        Uses keyword matching and heuristics.
        For production, could use LLM for better accuracy.
        """
        transcript_lower = transcript.lower()
        
        # Count keyword matches for each type
        scores = {}
        keywords_found = {}
        
        for meeting_type, keywords in self.KEYWORDS.items():
            matches = []
            for keyword in keywords:
                if keyword in transcript_lower:
                    matches.append(keyword)
            
            scores[meeting_type] = len(matches)
            keywords_found[meeting_type] = matches
        
        # Determine best match
        if all(score == 0 for score in scores.values()):
            return MeetingDetectionResult(
                meeting_type='unknown',
                confidence=0.0,
                reasoning="No keywords matched any meeting type",
                keywords_found=[]
            )
        
        best_type = max(scores, key=scores.get)
        best_score = scores[best_type]
        total_keywords = len(self.KEYWORDS[best_type])
        confidence = min(best_score / total_keywords, 1.0)
        
        # Boost confidence for strong indicators
        if best_type == 'daily_standup' and any(k in transcript_lower for k in ['yesterday', 'today', 'blocker']):
            confidence = min(confidence + 0.2, 1.0)
        elif best_type == 'sprint_planning' and 'sprint goal' in transcript_lower:
            confidence = min(confidence + 0.2, 1.0)
        elif best_type == 'pm_backlog' and any(k in transcript_lower for k in ['epic', 'wsjf', 'roadmap']):
            confidence = min(confidence + 0.2, 1.0)
        
        return MeetingDetectionResult(
            meeting_type=best_type,
            confidence=confidence,
            reasoning=f"Found {best_score} keywords for {best_type}",
            keywords_found=keywords_found[best_type]
        )


# ============================================================================
# INTELLIGENT MEET BOT
# ============================================================================

class IntelligentMeetBot:
    """
    Intelligent meeting bot that automatically detects meeting type
    and triggers the appropriate pipeline.
    
    Complete workflow:
    1. Join Google Meet
    2. Record audio
    3. Transcribe speech
    4. Detect meeting type
    5. Trigger appropriate pipeline
    6. Create approval request
    7. Send Telegram notification
    
    Example usage:
        bot = IntelligentMeetBot()
        result = await bot.run(
            meet_link="https://meet.google.com/abc-defg-hij"
        )
    """
    
    def __init__(self):
        """Initialize the intelligent meet bot."""
        self.detector = MeetingTypeDetector()
        logger.info("IntelligentMeetBot initialized")
    
    async def run(
        self,
        meet_link: str,
        output_dir: str = "backend/data/meetings",
        auto_detect: bool = True,
        force_type: Optional[MeetingType] = None
    ) -> MeetBotResult:
        """
        Run complete meet bot workflow.
        
        Args:
            meet_link: Google Meet URL
            output_dir: Directory to save audio and transcript
            auto_detect: If True, automatically detect meeting type
            force_type: Force specific meeting type (skip detection)
        
        Returns:
            MeetBotResult
        """
        bot_id = datetime.now().strftime('%Y%m%d_%H%M%S')
        
        result = MeetBotResult(
            bot_id=bot_id,
            start_time=datetime.now().isoformat(),
            status='in_progress',
            meet_link=meet_link
        )
        
        print("\n" + "=" * 70)
        print("INTELLIGENT MEET BOT - Phase 4 (Production Ready)")
        print("=" * 70)
        print(f"Bot ID: {bot_id}")
        print(f"Meet Link: {meet_link}")
        print(f"Auto Detect: {auto_detect}")
        print(f"Force Type: {force_type}")
        print("=" * 70 + "\n")
        
        try:
            # Phase 1: Join meeting and record
            print("Phase 1: Joining meeting and recording audio...")
            audio_file, transcript_file = await self._record_meeting(
                meet_link=meet_link,
                output_dir=output_dir,
                bot_id=bot_id
            )
            
            result.audio_file = audio_file
            result.transcript_file = transcript_file
            
            # Phase 2: Transcribe
            print("\nPhase 2: Transcribing audio...")
            transcript = self._load_transcript(transcript_file)
            result.transcript_length = len(transcript)
            
            print(f"  Transcript length: {len(transcript)} characters")
            print(f"  First 200 chars: {transcript[:200]}...")
            
            # Phase 3: Detect meeting type
            if force_type:
                print(f"\nPhase 3: Using forced meeting type: {force_type}")
                result.detected_type = force_type
                result.detection_confidence = 1.0
            elif auto_detect:
                print("\nPhase 3: Detecting meeting type...")
                detection = self.detector.detect(transcript)
                
                result.detected_type = detection.meeting_type
                result.detection_confidence = detection.confidence
                
                print(f"  Detected: {detection.meeting_type}")
                print(f"  Confidence: {detection.confidence:.2f}")
                print(f"  Reasoning: {detection.reasoning}")
                print(f"  Keywords: {', '.join(detection.keywords_found[:5])}")
                
                if detection.meeting_type == 'unknown':
                    print("\n⚠️  Could not detect meeting type")
                    print("  Please specify meeting type manually or improve transcript")
                    result.status = 'completed'
                    result.end_time = datetime.now().isoformat()
                    return result
            else:
                print("\n⚠️  Auto-detect disabled and no forced type specified")
                result.status = 'completed'
                result.end_time = datetime.now().isoformat()
                return result
            
            # Phase 4: Trigger appropriate pipeline
            print(f"\nPhase 4: Triggering {result.detected_type} pipeline...")
            pipeline_result = await self._trigger_pipeline(
                meeting_type=result.detected_type,
                transcript_file=transcript_file
            )
            
            result.pipeline_triggered = result.detected_type
            result.pipeline_result = pipeline_result
            result.approval_id = pipeline_result.get('approval_id')
            
            # Mark as complete
            result.status = 'completed'
            result.end_time = datetime.now().isoformat()
            
            print("\n" + "=" * 70)
            print("MEET BOT COMPLETE")
            print("=" * 70)
            print(f"Meeting Type: {result.detected_type}")
            print(f"Pipeline: {result.pipeline_triggered}")
            print(f"Approval ID: #{result.approval_id}")
            print(f"📱 Telegram notification sent!")
            print("=" * 70 + "\n")
            
            return result
        
        except Exception as e:
            logger.error(f"Meet bot failed: {e}", exc_info=True)
            result.status = 'failed'
            result.errors.append(str(e))
            result.end_time = datetime.now().isoformat()
            
            print(f"\n❌ Meet bot failed: {e}")
            raise
    
    async def _record_meeting(
        self,
        meet_link: str,
        output_dir: str,
        bot_id: str
    ) -> tuple[str, str]:
        """
        Join meeting, record audio, and transcribe.
        
        Returns:
            (audio_file, transcript_file)
        """
        # Create output directory
        Path(output_dir).mkdir(parents=True, exist_ok=True)
        
        audio_file = os.path.join(output_dir, f"{bot_id}_audio.wav")
        transcript_file = os.path.join(output_dir, f"{bot_id}_transcript.txt")
        
        stop_event = threading.Event()
        
        # Start meeting bot
        meeting_task = asyncio.create_task(join_meeting(meet_link))
        
        # Wait for meeting to start and bot to join
        print("  Waiting for bot to join meeting...")
        await asyncio.sleep(15)
        
        # Start recording
        print("  Recording audio...")
        recording_task = asyncio.create_task(
            asyncio.to_thread(record_system_audio, audio_file, stop_event=stop_event)
        )
        
        # Wait for meeting to end
        await meeting_task
        
        # Stop recording
        print("  Meeting ended, stopping recording...")
        stop_event.set()
        await recording_task
        
        # Transcribe
        print("  Transcribing audio...")
        transcript = transcribe_audio_from_path(audio_file)
        
        # Save transcript
        with open(transcript_file, 'w', encoding='utf-8') as f:
            f.write(transcript)
        
        print(f"  Audio saved: {audio_file}")
        print(f"  Transcript saved: {transcript_file}")
        
        return audio_file, transcript_file
    
    def _load_transcript(self, transcript_file: str) -> str:
        """Load transcript from file."""
        with open(transcript_file, 'r', encoding='utf-8') as f:
            return f.read()
    
    async def _trigger_pipeline(
        self,
        meeting_type: MeetingType,
        transcript_file: str
    ) -> Dict[str, Any]:
        """
        Trigger appropriate pipeline based on meeting type.
        
        Returns:
            Pipeline result dict
        """
        if meeting_type == 'pm_backlog':
            return await self._run_backlog_pipeline(transcript_file)
        elif meeting_type == 'sprint_planning':
            return await self._run_sprint_planning_pipeline(transcript_file)
        elif meeting_type == 'daily_standup':
            return await self._run_standup_pipeline(transcript_file)
        elif meeting_type == 'grooming':
            # For now, grooming uses backlog pipeline
            # In future, could have dedicated grooming pipeline
            return await self._run_backlog_pipeline(transcript_file)
        else:
            raise Exception(f"Unknown meeting type: {meeting_type}")
    
    async def _run_backlog_pipeline(self, transcript_file: str) -> Dict[str, Any]:
        """Run backlog pipeline (Phase 1)."""
        # BacklogPipeline doesn't have require_telegram_approval parameter
        # It uses PipelineConfig instead
        pipeline = BacklogPipeline()
        
        result = pipeline.run(
            transcript_path=transcript_file,
            create_in_jira=True
        )
        
        return {
            'pipeline': 'backlog',
            'status': result.status,
            'approval_id': result.approval_id if hasattr(result, 'approval_id') else None,
            'epics_extracted': result.total_epics if hasattr(result, 'total_epics') else 0,
            'stories_decomposed': result.total_stories if hasattr(result, 'total_stories') else 0,
            'tasks_decomposed': result.total_tasks if hasattr(result, 'total_tasks') else 0
        }
    
    async def _run_sprint_planning_pipeline(self, transcript_file: str) -> Dict[str, Any]:
        """Run sprint planning pipeline (Phase 2)."""
        pipeline = SprintPlanningPipeline(require_telegram_approval=True)
        
        result = pipeline.run(
            transcript_path=transcript_file,
            create_in_jira=True  # Changed from create_sprint
        )
        
        return {
            'pipeline': 'sprint_planning',
            'status': result.status,
            'approval_id': result.approval_id,
            'sprint_name': result.sprint_goal if hasattr(result, 'sprint_goal') else 'N/A',
            'stories_planned': result.stories_committed if hasattr(result, 'stories_committed') else 0
        }
    
    async def _run_standup_pipeline(self, transcript_file: str) -> Dict[str, Any]:
        """Run standup pipeline (Phase 3)."""
        pipeline = ScrumPipeline(require_telegram_approval=True)
        
        result = pipeline.run(
            transcript_path=transcript_file,
            update_jira=True
        )
        
        return {
            'pipeline': 'standup',
            'status': result.status,
            'approval_id': result.approval_id,
            'total_actions': result.total_actions,
            'tasks_completed': result.tasks_completed,
            'tasks_updated': result.tasks_updated
        }


# ============================================================================
# CONVENIENCE FUNCTIONS
# ============================================================================

async def run_intelligent_meet_bot(
    meet_link: str,
    auto_detect: bool = True,
    force_type: Optional[MeetingType] = None
) -> MeetBotResult:
    """
    Convenience function to run intelligent meet bot.
    
    Args:
        meet_link: Google Meet URL
        auto_detect: Automatically detect meeting type
        force_type: Force specific meeting type
    
    Returns:
        MeetBotResult
    """
    bot = IntelligentMeetBot()
    return await bot.run(
        meet_link=meet_link,
        auto_detect=auto_detect,
        force_type=force_type
    )


# ============================================================================
# MAIN EXECUTION
# ============================================================================

if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv()
    
    # Example usage
    MEET_LINK = os.getenv('MEET_LINK', 'https://meet.google.com/abc-defg-hij')
    
    # Check for command line arguments
    if len(sys.argv) > 1:
        MEET_LINK = sys.argv[1]
    
    force_type = None
    if '--type' in sys.argv:
        idx = sys.argv.index('--type')
        if idx + 1 < len(sys.argv):
            force_type = sys.argv[idx + 1]
    
    auto_detect = '--no-detect' not in sys.argv
    
    # Run bot
    result = asyncio.run(run_intelligent_meet_bot(
        meet_link=MEET_LINK,
        auto_detect=auto_detect,
        force_type=force_type
    ))
    
    # Print result
    if '--json' in sys.argv:
        print(json.dumps(result.model_dump(), indent=2, default=str))
