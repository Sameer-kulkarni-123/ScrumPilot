"""
Backlog Pipeline - Phase 6

Orchestrates the complete workflow from PM meeting transcript to Jira backlog:
1. Extract Epics from PM meeting (Phase 1)
2. Extract estimates from Grooming meeting (Phase 2)
3. Calculate WSJF scores (Phase 3)
4. Decompose Epics into Stories and Tasks (Phase 4)
5. Create complete hierarchy in Jira (Phase 5)

Features:
- Checkpoint system for crash recovery
- Error handling and retry logic
- Optional human approval gates
- Progress tracking
- Comprehensive reporting

Author: AI Meeting Automation System
Phase: 6
"""

import os
import json
import logging
from pathlib import Path
from typing import Dict, List, Optional, Any
from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field

# Import all agents from previous phases
from backend.agents.backlog_extractor import BacklogExtractorAgent
from backend.agents.grooming_extractor import GroomingExtractorAgent
from backend.agents.wsjf_calculator import WSJFCalculatorAgent
from backend.agents.epic_decomposer import EpicDecomposerAgent
from backend.agents.jira_creator import JiraCreatorAgent

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


# ============================================================================
# ENUMS AND MODELS
# ============================================================================

class PipelinePhase(str, Enum):
    """Pipeline execution phases."""
    VALIDATION = "validation"
    PM_EXTRACTION = "pm_extraction"
    GROOMING_EXTRACTION = "grooming_extraction"
    WSJF_CALCULATION = "wsjf_calculation"
    DECOMPOSITION = "decomposition"
    JIRA_CREATION = "jira_creation"
    COMPLETE = "complete"


class PipelineStatus(str, Enum):
    """Pipeline execution status."""
    NOT_STARTED = "not_started"
    IN_PROGRESS = "in_progress"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"


class PipelineConfig(BaseModel):
    """Pipeline configuration options."""
    
    # Approval gates
    require_approval_after_wsjf: bool = False
    require_approval_after_decomposition: bool = False
    require_telegram_approval: bool = True  # NEW: Enable Telegram approval integration
    
    # Jira options
    create_in_jira: bool = True
    jira_dry_run: bool = False
    
    # Checkpointing
    save_checkpoints: bool = True
    checkpoint_dir: str = "backend/data/checkpoints"
    
    # Error handling
    retry_on_failure: bool = True
    max_retries: int = 3
    
    # Timeouts (in seconds)
    phase_timeout: int = 300  # 5 minutes per phase
    pipeline_timeout: int = 900  # 15 minutes total
    llm_timeout: int = 120  # 2 minutes per LLM call
    
    # Reporting
    generate_final_report: bool = True
    report_dir: str = "backend/data/pipeline_reports"


class PhaseResult(BaseModel):
    """Result of a single pipeline phase."""
    phase: PipelinePhase
    status: PipelineStatus
    success: bool
    output_file: Optional[str] = None
    error: Optional[str] = None
    duration_seconds: float = 0.0
    timestamp: str = Field(default_factory=lambda: datetime.now().isoformat())


class PipelineResult(BaseModel):
    """Complete pipeline execution result."""
    pipeline_id: str
    start_time: str
    end_time: Optional[str] = None
    status: PipelineStatus
    current_phase: PipelinePhase
    phases: List[PhaseResult] = Field(default_factory=list)
    
    # Input files
    pm_transcript_path: str
    grooming_transcript_path: str
    
    # Output files
    pm_extraction_file: Optional[str] = None
    grooming_extraction_file: Optional[str] = None
    wsjf_calculation_file: Optional[str] = None
    decomposition_file: Optional[str] = None
    jira_creation_file: Optional[str] = None
    
    # Summary
    total_epics: int = 0
    total_stories: int = 0
    total_tasks: int = 0
    jira_items_created: int = 0
    
    # Errors
    errors: List[str] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)


# ============================================================================
# BACKLOG PIPELINE
# ============================================================================

class BacklogPipeline:
    """
    Orchestrates complete PM meeting to Jira backlog workflow.
    
    Phases:
    1. Validation - Check input files exist
    2. PM Extraction - Extract Epics from PM meeting
    3. Grooming Extraction - Extract estimates from Grooming meeting
    4. WSJF Calculation - Calculate and rank priorities
    5. Decomposition - Break Epics into Stories and Tasks
    6. Jira Creation - Create complete hierarchy in Jira
    
    Features:
    - Checkpoint system for crash recovery
    - Optional human approval gates
    - Comprehensive error handling
    - Progress tracking
    - Final report generation
    """

    def __init__(self, config: Optional[PipelineConfig] = None):
        """
        Initialize the Backlog Pipeline.
        
        Args:
            config: Optional pipeline configuration
        """
        self.config = config or PipelineConfig()
        self.result: Optional[PipelineResult] = None
        
        # Create checkpoint directory
        if self.config.save_checkpoints:
            Path(self.config.checkpoint_dir).mkdir(parents=True, exist_ok=True)
        
        # Create report directory
        if self.config.generate_final_report:
            Path(self.config.report_dir).mkdir(parents=True, exist_ok=True)
        
        logger.info("BacklogPipeline initialized")

    def run(
        self,
        pm_transcript_path: str,
        grooming_transcript_path: str,
        create_in_jira: bool = True,
        dry_run: bool = False
    ) -> PipelineResult:
        """
        Run complete pipeline from transcripts to Jira with timeout protection.
        
        Args:
            pm_transcript_path: Path to PM meeting transcript
            grooming_transcript_path: Path to Grooming meeting transcript
            create_in_jira: Whether to create items in Jira
            dry_run: If True, simulate without actual Jira creation
        
        Returns:
            PipelineResult with complete execution details
            
        Raises:
            TimeoutError: If pipeline exceeds overall timeout
            EnvironmentError: If environment validation fails
            Exception: If any phase fails
        """
        import time
        from threading import Thread, Event
        
        pipeline_id = datetime.now().strftime('%Y%m%d_%H%M%S')
        pipeline_start_time = time.time()
        
        # Initialize result
        self.result = PipelineResult(
            pipeline_id=pipeline_id,
            start_time=datetime.now().isoformat(),
            status=PipelineStatus.IN_PROGRESS,
            current_phase=PipelinePhase.VALIDATION,
            pm_transcript_path=pm_transcript_path,
            grooming_transcript_path=grooming_transcript_path
        )
        
        print("\n" + "=" * 70)
        print("BACKLOG PIPELINE - Phase 6 (Production Ready)")
        print("=" * 70)
        print(f"Pipeline ID: {pipeline_id}")
        print(f"PM Transcript: {pm_transcript_path}")
        print(f"Grooming Transcript: {grooming_transcript_path}")
        print(f"Create in Jira: {create_in_jira}")
        print(f"Dry Run: {dry_run}")
        print(f"Pipeline Timeout: {self.config.pipeline_timeout}s")
        print(f"Phase Timeout: {self.config.phase_timeout}s")
        print("=" * 70 + "\n")
        
        # Wrapper function for pipeline execution
        pipeline_error = {'error': None}
        
        def run_pipeline():
            try:
                self._run_pipeline_phases(
                    pm_transcript_path,
                    grooming_transcript_path,
                    create_in_jira,
                    dry_run
                )
            except Exception as e:
                pipeline_error['error'] = e
        
        # Run pipeline with overall timeout
        pipeline_thread = Thread(target=run_pipeline, daemon=True)
        pipeline_thread.start()
        pipeline_thread.join(timeout=self.config.pipeline_timeout)
        
        # Check if pipeline timed out
        if pipeline_thread.is_alive():
            duration = time.time() - pipeline_start_time
            error_msg = (
                f"Pipeline exceeded overall timeout of {self.config.pipeline_timeout}s "
                f"(ran for {duration:.1f}s)"
            )
            
            self.result.status = PipelineStatus.FAILED
            self.result.errors.append(error_msg)
            self.result.end_time = datetime.now().isoformat()
            
            logger.error(error_msg)
            print(f"\n{'=' * 70}")
            print("PIPELINE TIMEOUT")
            print(f"{'=' * 70}")
            print(f"Exceeded timeout of {self.config.pipeline_timeout}s")
            
            # Save checkpoint on timeout
            if self.config.save_checkpoints:
                self._save_checkpoint()
            
            raise TimeoutError(error_msg)
        
        # Check if pipeline had an error
        if pipeline_error['error']:
            raise pipeline_error['error']
        
        return self.result
    
    def _run_pipeline_phases(
        self,
        pm_transcript_path: str,
        grooming_transcript_path: str,
        create_in_jira: bool,
        dry_run: bool
    ) -> None:
        """Execute all pipeline phases (called by run() with timeout)."""
        try:
            # Phase 1: Validation
            self._run_phase(
                PipelinePhase.VALIDATION,
                self._validate_inputs,
                pm_transcript_path,
                grooming_transcript_path
            )
            
            # Phase 2: PM Extraction
            pm_output = self._run_phase(
                PipelinePhase.PM_EXTRACTION,
                self._extract_pm_meeting,
                pm_transcript_path
            )
            self.result.pm_extraction_file = pm_output
            
            # Phase 3: Grooming Extraction
            grooming_output = self._run_phase(
                PipelinePhase.GROOMING_EXTRACTION,
                self._extract_grooming_meeting,
                grooming_transcript_path,
                pm_output  # Pass PM output for matching
            )
            self.result.grooming_extraction_file = grooming_output
            
            # Phase 4: WSJF Calculation
            wsjf_output = self._run_phase(
                PipelinePhase.WSJF_CALCULATION,
                self._calculate_wsjf,
                pm_output,
                grooming_output
            )
            self.result.wsjf_calculation_file = wsjf_output
            
            # Optional: Human approval after WSJF (old method)
            if self.config.require_approval_after_wsjf:
                self._request_approval("WSJF calculation")
            
            # Phase 5: Decomposition
            decomposition_output = self._run_phase(
                PipelinePhase.DECOMPOSITION,
                self._decompose_epics,
                wsjf_output
            )
            self.result.decomposition_file = decomposition_output
            
            # Update summary counts
            self._update_summary_counts(decomposition_output)
            
            # NEW: Telegram approval integration AFTER decomposition
            if self.config.require_telegram_approval:
                approval_id = self._create_telegram_approval_after_decomposition(decomposition_output)
                print(f"\n{'=' * 70}")
                print(f"✅ APPROVAL REQUEST CREATED")
                print(f"{'=' * 70}")
                print(f"Approval ID: #{approval_id}")
                print(f"📱 Telegram notification sent to PM")
                print(f"⏸️  Pipeline paused. Waiting for approval...")
                print(f"\nThe PM will receive a Telegram notification to review:")
                print(f"  - {self.result.total_epics} Epic(s)")
                print(f"  - {self.result.total_stories} Story(ies)")
                print(f"  - {self.result.total_tasks} Task(s)")
                print(f"\nAfter approval, the system will automatically:")
                print(f"  1. Create complete hierarchy in Jira using JiraCreatorAgent")
                print(f"  2. Update database with Jira keys")
                print(f"{'=' * 70}\n")
                
                # Mark pipeline as paused and exit
                self.result.status = PipelineStatus.PAUSED
                self.result.current_phase = PipelinePhase.DECOMPOSITION
                self.result.end_time = datetime.now().isoformat()
                
                # Save checkpoint
                if self.config.save_checkpoints:
                    self._save_checkpoint()
                
                # Generate report
                if self.config.generate_final_report:
                    self._generate_final_report()
                
                return self.result
            
            # Optional: Human approval after decomposition (old method)
            if self.config.require_approval_after_decomposition:
                self._request_approval("decomposition")
            
            # Phase 6: Jira Creation
            if create_in_jira:
                jira_output = self._run_phase(
                    PipelinePhase.JIRA_CREATION,
                    self._create_in_jira,
                    decomposition_output,
                    dry_run
                )
                self.result.jira_creation_file = jira_output
                
                # Update Jira items count
                self._update_jira_counts(jira_output)
            else:
                print("\nSkipping Jira creation (create_in_jira=False)")
            
            # Mark as complete
            self.result.status = PipelineStatus.COMPLETED
            self.result.current_phase = PipelinePhase.COMPLETE
            self.result.end_time = datetime.now().isoformat()
            
            print("\n" + "=" * 70)
            print("PIPELINE COMPLETE")
            print("=" * 70)
            
            # Generate final report
            if self.config.generate_final_report:
                self._generate_final_report()
            
            # Save final checkpoint
            if self.config.save_checkpoints:
                self._save_checkpoint()
        
        except Exception as e:
            logger.error(f"Pipeline failed: {e}")
            self.result.status = PipelineStatus.FAILED
            self.result.errors.append(str(e))
            self.result.end_time = datetime.now().isoformat()
            
            # Save checkpoint on failure
            if self.config.save_checkpoints:
                self._save_checkpoint()
            
            print(f"\nPipeline failed: {e}")
            raise


    def _run_phase(
        self,
        phase: PipelinePhase,
        func,
        *args,
        **kwargs
    ) -> Any:
        """
        Run a single pipeline phase with error handling, timeout, and tracking.
        
        Args:
            phase: Pipeline phase to run
            func: Function to execute
            *args, **kwargs: Arguments to pass to function
        
        Returns:
            Function result
            
        Raises:
            TimeoutError: If phase exceeds timeout
            Exception: If phase fails
        """
        import time
        import signal
        from threading import Thread, Event
        
        self.result.current_phase = phase
        start_time = time.time()
        
        print(f"\n{'=' * 70}")
        print(f"PHASE: {phase.value.upper()}")
        print(f"{'=' * 70}")
        
        phase_result = PhaseResult(
            phase=phase,
            status=PipelineStatus.IN_PROGRESS,
            success=False
        )
        
        # Timeout handling using threading (works on Windows)
        result_container = {'result': None, 'error': None}
        timeout_event = Event()
        
        def run_with_timeout():
            try:
                result_container['result'] = func(*args, **kwargs)
            except Exception as e:
                result_container['error'] = e
            finally:
                timeout_event.set()
        
        # Start phase execution in thread
        thread = Thread(target=run_with_timeout, daemon=True)
        thread.start()
        
        # Wait for completion or timeout
        timed_out = not timeout_event.wait(timeout=self.config.phase_timeout)
        
        if timed_out:
            duration = time.time() - start_time
            error_msg = (
                f"Phase {phase.value} exceeded timeout of {self.config.phase_timeout}s "
                f"(ran for {duration:.1f}s)"
            )
            
            phase_result.status = PipelineStatus.FAILED
            phase_result.success = False
            phase_result.error = error_msg
            phase_result.duration_seconds = duration
            
            self.result.phases.append(phase_result)
            self.result.errors.append(f"{phase.value}: {error_msg}")
            
            logger.error(error_msg)
            print(f"\nPhase TIMEOUT after {duration:.1f}s")
            
            raise TimeoutError(error_msg)
        
        # Check if phase had an error
        if result_container['error']:
            duration = time.time() - start_time
            phase_result.status = PipelineStatus.FAILED
            phase_result.success = False
            phase_result.error = str(result_container['error'])
            phase_result.duration_seconds = duration
            
            self.result.phases.append(phase_result)
            self.result.errors.append(f"{phase.value}: {str(result_container['error'])}")
            
            logger.error(f"Phase {phase.value} failed: {result_container['error']}")
            raise result_container['error']
        
        # Phase succeeded
        output = result_container['result']
        duration = time.time() - start_time
        
        phase_result.status = PipelineStatus.COMPLETED
        phase_result.success = True
        phase_result.duration_seconds = duration
        
        if isinstance(output, str):
            phase_result.output_file = output
        
        self.result.phases.append(phase_result)
        
        print(f"\nPhase completed in {duration:.2f}s")
        
        # Save checkpoint after each phase
        if self.config.save_checkpoints:
            self._save_checkpoint()
        
        return output

    # ========================================================================
    # PHASE IMPLEMENTATIONS
    # ========================================================================

    def _validate_inputs(
        self,
        pm_transcript_path: str,
        grooming_transcript_path: str
    ) -> None:
        """
        Validate environment and input files before execution.
        
        Checks:
        - Input files exist and are readable
        - API keys are set
        - Jira connectivity
        - Groq API connectivity
        - Disk space
        - Required directories
        """
        print("Validating environment and inputs...")
        errors = []
        warnings = []
        
        # 1. Validate input files
        print("  Checking input files...")
        pm_path = Path(pm_transcript_path)
        grooming_path = Path(grooming_transcript_path)
        
        if not pm_path.exists():
            errors.append(f"PM transcript not found: {pm_transcript_path}")
        elif not pm_path.is_file():
            errors.append(f"PM transcript is not a file: {pm_transcript_path}")
        elif pm_path.stat().st_size == 0:
            errors.append(f"PM transcript is empty: {pm_transcript_path}")
        else:
            print(f"    PM transcript: OK ({pm_path.stat().st_size} bytes)")
        
        if not grooming_path.exists():
            errors.append(f"Grooming transcript not found: {grooming_transcript_path}")
        elif not grooming_path.is_file():
            errors.append(f"Grooming transcript is not a file: {grooming_transcript_path}")
        elif grooming_path.stat().st_size == 0:
            errors.append(f"Grooming transcript is empty: {grooming_transcript_path}")
        else:
            print(f"    Grooming transcript: OK ({grooming_path.stat().st_size} bytes)")
        
        # 2. Validate API keys
        print("  Checking API keys...")
        if not os.getenv('GROQ_API_KEY'):
            errors.append("GROQ_API_KEY environment variable not set")
        else:
            print("    GROQ_API_KEY: OK")
        
        if not os.getenv('JIRA_URL'):
            errors.append("JIRA_URL environment variable not set")
        else:
            print(f"    JIRA_URL: OK ({os.getenv('JIRA_URL')})")
        
        if not os.getenv('JIRA_EMAIL'):
            errors.append("JIRA_EMAIL environment variable not set")
        else:
            print("    JIRA_EMAIL: OK")
        
        if not os.getenv('JIRA_API_TOKEN'):
            errors.append("JIRA_API_TOKEN environment variable not set")
        else:
            print("    JIRA_API_TOKEN: OK")
        
        jira_project_key = os.getenv('JIRA_PROJECT_KEY')
        jira_routing_config_path = os.getenv('JIRA_ROUTING_CONFIG_PATH')

        if jira_project_key:
            print(f"    JIRA_PROJECT_KEY: OK ({jira_project_key})")

        if jira_routing_config_path:
            routing_path = Path(jira_routing_config_path)
            if not routing_path.is_absolute():
                routing_path = Path.cwd() / routing_path

            if not routing_path.exists():
                errors.append(
                    f"JIRA_ROUTING_CONFIG_PATH does not exist: {routing_path}"
                )
            else:
                print(f"    JIRA_ROUTING_CONFIG_PATH: OK ({routing_path})")

        if not jira_project_key and not jira_routing_config_path:
            errors.append(
                "Either JIRA_PROJECT_KEY or JIRA_ROUTING_CONFIG_PATH must be set"
            )
        
        # 3. Test Jira connectivity (only if keys are set)
        if not any('JIRA' in e for e in errors):
            print("  Testing Jira connectivity...")
            try:
                from backend.tools.jira_client import JiraManager
                jira = JiraManager()
                # Test connection by getting current user
                user = jira.client.myself()
                print(f"    Jira connection: OK (logged in as {user.get('displayName', 'Unknown')})")
            except Exception as e:
                errors.append(f"Jira connection failed: {str(e)}")
                print(f"    Jira connection: FAILED ({str(e)})")
        
        # 4. Test Groq API connectivity (only if key is set)
        if not any('GROQ' in e for e in errors):
            print("  Testing Groq API connectivity...")
            try:
                from langchain_groq import ChatGroq
                llm = ChatGroq(
                    model="llama-3.3-70b-versatile",
                    groq_api_key=os.getenv('GROQ_API_KEY'),
                    temperature=0
                )
                # Simple test call
                response = llm.invoke("Say 'OK'")
                print("    Groq API connection: OK")
            except Exception as e:
                errors.append(f"Groq API connection failed: {str(e)}")
                print(f"    Groq API connection: FAILED ({str(e)})")
        
        # 5. Check disk space
        print("  Checking disk space...")
        try:
            import shutil
            stats = shutil.disk_usage(Path.cwd())
            free_mb = stats.free / (1024 * 1024)
            
            if free_mb < 100:  # Less than 100MB
                errors.append(f"Insufficient disk space: {free_mb:.1f}MB free (need at least 100MB)")
            elif free_mb < 500:  # Less than 500MB
                warnings.append(f"Low disk space: {free_mb:.1f}MB free")
                print(f"    Disk space: WARNING ({free_mb:.1f}MB free)")
            else:
                print(f"    Disk space: OK ({free_mb:.1f}MB free)")
        except Exception as e:
            warnings.append(f"Could not check disk space: {str(e)}")
        
        # 6. Check/create required directories
        print("  Checking required directories...")
        required_dirs = [
            'backend/data/pm_meetings',
            'backend/data/grooming_meetings',
            'backend/data/wsjf',
            'backend/data/decomposed',
            'backend/data/jira',
            self.config.checkpoint_dir,
            self.config.report_dir
        ]
        
        for dir_path in required_dirs:
            try:
                Path(dir_path).mkdir(parents=True, exist_ok=True)
            except Exception as e:
                errors.append(f"Cannot create directory {dir_path}: {str(e)}")
        
        print("    Required directories: OK")
        
        # Report results
        print()
        if errors:
            print("VALIDATION FAILED:")
            for error in errors:
                print(f"  ERROR: {error}")
            raise EnvironmentError(
                f"Environment validation failed with {len(errors)} error(s):\n" +
                "\n".join(f"  - {e}" for e in errors)
            )
        
        if warnings:
            print("VALIDATION WARNINGS:")
            for warning in warnings:
                print(f"  WARNING: {warning}")
            self.result.warnings.extend(warnings)
        
        print("Validation passed")

    def _extract_pm_meeting(self, transcript_path: str) -> str:
        """Extract Epics from PM meeting transcript."""
        print("Extracting Epics from PM meeting...")
        
        agent = BacklogExtractorAgent()
        result = agent.extract_epics_from_file(transcript_path)
        
        # Generate output path
        output_path = self._generate_output_path(transcript_path, "extracted_epics.json")
        
        # Save result
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(result, f, indent=2, ensure_ascii=False)
        
        print(f"  Extracted {len(result.get('epics', []))} Epic(s)")
        print(f"  Saved to: {output_path}")
        
        return output_path

    def _extract_grooming_meeting(self, transcript_path: str, pm_file: str) -> str:
        """Extract estimates from Grooming meeting transcript."""
        print("Extracting estimates from Grooming meeting...")
        
        agent = GroomingExtractorAgent()
        result = agent.extract_estimates_from_file(
            transcript_path=transcript_path,
            pm_epics_path=pm_file
        )
        
        # Generate output path
        output_path = self._generate_output_path(transcript_path, "grooming_data.json")
        
        # Save result
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(result, f, indent=2, ensure_ascii=False)
        
        print(f"  Extracted estimates for {len(result.get('epic_estimates', []))} Epic(s)")
        print(f"  Saved to: {output_path}")
        
        return output_path

    def _calculate_wsjf(self, pm_file: str, grooming_file: str) -> str:
        """Calculate WSJF scores and rank Epics."""
        print("Calculating WSJF scores...")
        
        agent = WSJFCalculatorAgent()
        wsjf_data = agent.calculate_wsjf(
            pm_data_path=pm_file,
            grooming_data_path=grooming_file,
            allow_incomplete=False
        )
        
        # Generate output path
        date_str = datetime.now().strftime('%Y-%m-%d')
        output_path = f"backend/data/wsjf/{date_str}_wsjf_scores.json"
        agent.save_wsjf_data(output_path)
        
        print(f"  Calculated WSJF for {len(wsjf_data.epics_with_wsjf)} Epic(s)")
        print(f"  Saved to: {output_path}")
        
        # Show top priorities
        print("\n  Top priorities:")
        for epic in wsjf_data.epics_with_wsjf[:3]:
            print(f"    {epic.priority_rank}. {epic.title} - WSJF: {epic.wsjf_score:.2f}")
        
        return output_path

    def _decompose_epics(self, wsjf_file: str) -> str:
        """
        Decompose Epics into Stories and Tasks with partial failure handling.
        
        If one Epic fails, continues with remaining Epics and reports failures.
        """
        print("Decomposing Epics into Stories and Tasks...")
        print("(Partial failure handling enabled)")
        
        # Load WSJF data
        with open(wsjf_file, 'r', encoding='utf-8') as f:
            wsjf_data = json.load(f)
        
        epics = wsjf_data.get('epics_with_wsjf', [])
        
        agent = EpicDecomposerAgent()
        
        successful_epics = []
        failed_epics = []
        
        print(f"\nProcessing {len(epics)} Epic(s)...")
        
        for i, epic in enumerate(epics, 1):
            epic_id = epic.get('epic_id', 'unknown')
            epic_title = epic.get('title', 'Unknown')
            
            try:
                print(f"\n[{i}/{len(epics)}] Decomposing: {epic_title}")
                
                # Decompose single Epic
                decomposed = agent.decompose_epic(
                    epic,
                    num_stories=agent._calculate_story_count(epic),
                    num_criteria=agent._calculate_criteria_count(
                        epic.get('wsjf_components', {}).get('effort', 5)
                    ),
                    num_tasks=3  # Will vary per story
                )
                
                successful_epics.append(decomposed)
                print(f"  SUCCESS: {len(decomposed.stories)} Stories, "
                      f"{sum(len(s.tasks) for s in decomposed.stories)} Tasks")
            
            except Exception as e:
                logger.error(f"Failed to decompose Epic '{epic_title}' ({epic_id}): {e}")
                
                failed_epics.append({
                    'epic_id': epic_id,
                    'title': epic_title,
                    'error': str(e),
                    'wsjf_score': epic.get('wsjf_score', 0)
                })
                
                print(f"  FAILED: {str(e)}")
                print(f"  Continuing with remaining Epics...")
                
                # Add to warnings
                self.result.warnings.append(
                    f"Epic '{epic_title}' ({epic_id}) failed decomposition: {str(e)}"
                )
        
        # Check if we have any successful decompositions
        if not successful_epics:
            error_msg = f"All {len(epics)} Epic(s) failed decomposition"
            logger.error(error_msg)
            raise Exception(error_msg)
        
        # Create decomposed backlog from successful Epics
        from backend.agents.epic_decomposer import DecomposedBacklog
        
        total_stories = sum(len(e.stories) for e in successful_epics)
        total_tasks = sum(
            len(s.tasks) for e in successful_epics for s in e.stories
        )
        total_hours = sum(
            t.estimated_hours
            for e in successful_epics
            for s in e.stories
            for t in s.tasks
        )
        
        decomposed_backlog = DecomposedBacklog(
            decomposition_date=datetime.now().strftime('%Y-%m-%d'),
            total_epics=len(successful_epics),
            total_stories=total_stories,
            total_tasks=total_tasks,
            total_estimated_hours=total_hours,
            epics=successful_epics
        )
        
        # Generate output path
        date_str = datetime.now().strftime('%Y-%m-%d')
        output_path = f"backend/data/decomposed/{date_str}_decomposed_backlog.json"
        
        # Save decomposed backlog
        output_file = Path(output_path)
        output_file.parent.mkdir(parents=True, exist_ok=True)
        
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(decomposed_backlog.model_dump(), f, indent=2, ensure_ascii=False)
        
        # Print summary
        print(f"\n{'=' * 70}")
        print("DECOMPOSITION SUMMARY")
        print(f"{'=' * 70}")
        print(f"Successful: {len(successful_epics)}/{len(epics)} Epic(s)")
        print(f"Failed: {len(failed_epics)}/{len(epics)} Epic(s)")
        print(f"Generated: {total_stories} Stories, {total_tasks} Tasks")
        print(f"Total hours: {total_hours}h")
        
        if failed_epics:
            print(f"\nFailed Epics:")
            for failed in failed_epics:
                print(f"  - {failed['title']} ({failed['epic_id']})")
                print(f"    Error: {failed['error'][:100]}...")
        
        print(f"\nSaved to: {output_path}")
        
        return output_path

    def _create_in_jira(self, decomposed_file: str, dry_run: bool = False) -> str:
        """
        Create complete hierarchy in Jira with partial failure handling.
        
        If one Epic fails, continues with remaining Epics and reports failures.
        Runs a pre-flight routing check: unknown projects trigger a PM approval
        request and those items are routed to triage in the meantime.
        """
        print("Creating backlog in Jira...")
        print("(Partial failure handling enabled)")
        
        if dry_run:
            print("  DRY RUN MODE - No actual Jira creation")

        self._preflight_routing_check(decomposed_file, dry_run)

        agent = JiraCreatorAgent()
        
        # Use partial failure mode
        try:
            result = agent.create_backlog_in_jira(
                backlog_path=decomposed_file,
                dry_run=dry_run,
                resume=True  # Enable idempotency
            )
        except Exception as e:
            # Even if some items failed, try to save what we have
            logger.error(f"Jira creation had errors: {e}")
            
            if agent.creation_result:
                result = agent.creation_result
                
                # Add error to warnings
                self.result.warnings.append(
                    f"Jira creation completed with errors: {str(e)}"
                )
            else:
                raise
        
        # Generate output path
        date_str = datetime.now().strftime('%Y-%m-%d')
        output_path = f"backend/data/jira/{date_str}_jira_creation.json"
        agent.save_creation_result(output_path)
        
        # Print summary
        print(f"\n{'=' * 70}")
        print("JIRA CREATION SUMMARY")
        print(f"{'=' * 70}")
        print(f"Epics created: {result.epics_created}/{result.total_epics}")
        print(f"Stories created: {result.stories_created}/{result.total_stories}")
        print(f"Tasks created: {result.tasks_created}/{result.total_tasks}")
        
        if result.errors:
            print(f"\nErrors: {len(result.errors)}")
            for error in result.errors[:5]:
                print(f"  - {error}")
            if len(result.errors) > 5:
                print(f"  ... and {len(result.errors) - 5} more")
            
            # Add to pipeline warnings
            self.result.warnings.append(
                f"Jira creation had {len(result.errors)} error(s)"
            )
        
        print(f"\nSaved to: {output_path}")

        # Save Epic/Story/Task rows to DB, then persist routing metadata
        self._save_jira_result_to_db(result, decomposed_file)
        self._persist_routing_metadata(result)
        
        return output_path

    def _save_jira_result_to_db(self, result, decomposed_file: str) -> None:
        """
        Persist Epic / Story / Task ORM rows to DB after direct Jira creation.

        Mirrors the DB-save logic inside execute_epic_creation (Telegram path)
        so that `verify_routing.py` and sprint planning can query the DB even
        when Telegram approval is bypassed.
        """
        try:
            import json as _json
            from backend.db.connection import get_session
            from backend.db import crud
            from backend.db.models import (
                Meeting, ProcessingRun, Epic, Story, BacklogTask,
                MeetingType, RunType, RunStatus,
            )
            from datetime import timezone

            with open(decomposed_file, "r") as f:
                decomposed_data = _json.load(f)

            with get_session() as session:
                # Reuse or create a Meeting row
                meeting = (
                    session.query(Meeting)
                    .filter(Meeting.meeting_type == MeetingType.PM)
                    .filter(Meeting.title.like("%Backlog%"))
                    .order_by(Meeting.created_at.desc())
                    .first()
                )
                if not meeting:
                    meeting = Meeting(
                        meeting_type=MeetingType.PM,
                        title="Backlog Pipeline - Direct Run",
                        meeting_date=datetime.now().date(),
                        source_platform="pipeline",
                        status="completed",
                        created_at=datetime.now(timezone.utc),
                    )
                    session.add(meeting)
                    session.flush()

                # Reuse or create a ProcessingRun row
                processing_run = (
                    session.query(ProcessingRun)
                    .filter(ProcessingRun.meeting_id == meeting.id)
                    .filter(ProcessingRun.run_type == RunType.PM_BACKLOG)
                    .order_by(ProcessingRun.created_at.desc())
                    .first()
                )
                if not processing_run:
                    max_run = (
                        session.query(ProcessingRun)
                        .filter(ProcessingRun.meeting_id == meeting.id)
                        .order_by(ProcessingRun.run_number.desc())
                        .first()
                    )
                    processing_run = ProcessingRun(
                        meeting_id=meeting.id,
                        run_number=(max_run.run_number + 1) if max_run else 1,
                        run_type=RunType.PM_BACKLOG,
                        status=RunStatus.COMPLETED,
                        started_at=datetime.now(timezone.utc),
                        finished_at=datetime.now(timezone.utc),
                        created_at=datetime.now(timezone.utc),
                    )
                    session.add(processing_run)
                    session.flush()

                epics_saved = stories_saved = tasks_saved = 0

                for jira_epic in result.epics:
                    if not jira_epic.success or not jira_epic.jira_key:
                        continue

                    epic_data = next(
                        (e for e in decomposed_data["epics"] if e["epic_id"] == jira_epic.epic_id),
                        None,
                    )
                    if not epic_data:
                        continue

                    db_epic = session.query(Epic).filter(
                        Epic.jira_key == jira_epic.jira_key
                    ).first()

                    if not db_epic:
                        db_epic = crud.create_epic(
                            session=session,
                            meeting_id=meeting.id,
                            processing_run_id=processing_run.id,
                            title=jira_epic.title,
                            description=epic_data.get("description", ""),
                            business_value=epic_data.get("business_value", 5),
                            time_criticality=epic_data.get("time_criticality", 5),
                            risk_reduction=epic_data.get("risk_reduction", 5),
                            job_size=epic_data.get("job_size", 5),
                            wsjf_score=jira_epic.wsjf_score,
                            priority_rank=jira_epic.priority_rank,
                        )
                        crud.update_epic_jira_info(
                            session=session,
                            epic_id=db_epic.id,
                            jira_key=jira_epic.jira_key,
                            jira_status="To Do",
                            jira_synced_at=datetime.now(timezone.utc),
                        )
                    epics_saved += 1

                    for jira_story in jira_epic.stories:
                        if not jira_story.success or not jira_story.jira_key:
                            continue

                        story_data = next(
                            (s for s in epic_data["stories"] if s["story_id"] == jira_story.story_id),
                            None,
                        )
                        if not story_data:
                            continue

                        db_story = session.query(Story).filter(
                            Story.jira_key == jira_story.jira_key
                        ).first()

                        if not db_story:
                            db_story = crud.create_story(
                                session=session,
                                epic_id=db_epic.id,
                                meeting_id=meeting.id,
                                processing_run_id=processing_run.id,
                                title=jira_story.title,
                                description=story_data.get("description", ""),
                                acceptance_criteria=story_data.get("acceptance_criteria", []),
                            )
                            crud.update_story_jira_info(
                                session=session,
                                story_id=db_story.id,
                                jira_key=jira_story.jira_key,
                                jira_status="To Do",
                                jira_synced_at=datetime.now(timezone.utc),
                            )
                        stories_saved += 1

                        for jira_task in jira_story.tasks:
                            if not jira_task.success or not jira_task.jira_key:
                                continue

                            task_data = next(
                                (t for t in story_data["tasks"] if t["task_id"] == jira_task.task_id),
                                None,
                            )
                            if not task_data:
                                continue

                            db_task = session.query(BacklogTask).filter(
                                BacklogTask.jira_key == jira_task.jira_key
                            ).first()

                            if not db_task:
                                db_task = crud.create_backlog_task(
                                    session=session,
                                    story_id=db_story.id,
                                    meeting_id=meeting.id,
                                    processing_run_id=processing_run.id,
                                    title=jira_task.title,
                                    description=task_data.get("description", ""),
                                    estimated_hours=jira_task.estimated_hours,
                                )
                                crud.update_task_jira_info(
                                    session=session,
                                    task_id=db_task.id,
                                    jira_key=jira_task.jira_key,
                                    jira_status="To Do",
                                    jira_synced_at=datetime.now(timezone.utc),
                                )
                            tasks_saved += 1

                session.commit()
                logger.info(
                    f"DB save complete: {epics_saved} epics, "
                    f"{stories_saved} stories, {tasks_saved} tasks"
                )
        except Exception as e:
            logger.warning(f"Failed to save Jira result to DB (non-fatal): {e}")

    def _persist_routing_metadata(self, result) -> None:
        """
        Update Epic / Story / Task DB rows with routing metadata after Jira creation.

        Uses routing_decisions (epic_id → routing dict) and id_mapping
        (epic_id → jira_key) from JiraCreationResult to find and update rows.
        """
        if not result.routing_decisions:
            return
        try:
            from backend.db.connection import get_session
            from backend.db.models import Epic, Story, BacklogTask
            from backend.services.routing_service import (
                persist_routing_on_epic,
                persist_routing_on_story,
                persist_routing_on_task,
            )
            from backend.tools.jira_routing import RoutingDecision

            with get_session() as session:
                for epic_result in result.epics:
                    epic_id = epic_result.epic_id
                    jira_key = epic_result.jira_key
                    routing_data = result.routing_decisions.get(epic_id)
                    if not routing_data or not jira_key:
                        continue

                    decision = RoutingDecision(
                        project_key=routing_data.get("project_key", ""),
                        project_name=routing_data.get("project_key", ""),
                        component=routing_data.get("component"),
                        matched_project=True,
                        matched_team=routing_data.get("team_name") is not None,
                        team_name=routing_data.get("team_name"),
                        confidence=routing_data.get("confidence", 1.0),
                        decision_reason=routing_data.get("source", "keyword_match"),
                    )

                    # Update Epic row
                    epic_row = session.query(Epic).filter(Epic.jira_key == jira_key).first()
                    if epic_row:
                        persist_routing_on_epic(epic_row, decision)

                    # Update Story rows
                    for story_result in epic_result.stories:
                        story_jira_key = story_result.jira_key
                        if story_jira_key:
                            story_row = session.query(Story).filter(
                                Story.jira_key == story_jira_key
                            ).first()
                            if story_row:
                                persist_routing_on_story(story_row, decision)

                        # Update Task rows
                        for task_result in story_result.tasks:
                            task_jira_key = task_result.jira_key
                            if task_jira_key:
                                task_row = session.query(BacklogTask).filter(
                                    BacklogTask.jira_key == task_jira_key
                                ).first()
                                if task_row:
                                    persist_routing_on_task(task_row, decision)

                session.commit()
                logger.info("Routing metadata persisted for all created Jira items")
        except Exception as e:
            logger.warning(f"Failed to persist routing metadata (non-fatal): {e}")

    # ========================================================================
    # ROUTING PRE-FLIGHT
    # ========================================================================

    def _preflight_routing_check(self, decomposed_file: str, dry_run: bool = False) -> None:
        """
        Pre-flight routing check before Jira creation.

        Steps:
        1. Load backlog JSON and resolve routing per epic using HybridRoutingService.
        2. Collect unique project keys that are not in the local registry.
        3. For each unknown project: create a project_creation ApprovalRequest
           and warn that those items will be routed to triage until approved.
        4. If any items have low confidence: create a routing_classification
           ApprovalRequest for PM review (non-blocking warning).

        This method is a best-effort guard and never raises — failures are logged
        and execution continues so Jira creation can still proceed.
        """
        try:
            import json
            from collections import defaultdict
            from backend.db.connection import get_session
            from backend.db.models import User
            from backend.services.routing_service import (
                create_project_approval_request,
                create_routing_card_approval_request,
            )
            from backend.tools.jira_client import JiraManager
            from backend.tools.llm_project_router import LLMProjectRouter
            from backend.tools.jira_routing import load_jira_routing_config

            # ── Load decomposed backlog ───────────────────────────────────────
            with open(decomposed_file, "r", encoding="utf-8") as fh:
                backlog = json.load(fh)
            epics = backlog.get("epics", [])
            if not epics:
                return

            # ── Fetch live Jira projects ──────────────────────────────────────
            # None  = API failed → optimistic
            # []    = Jira has no projects → all epics need new projects
            live_jira_projects: Optional[list] = None
            live_jira_keys:     Optional[set]  = None
            try:
                _jm = JiraManager()
                raw = _jm.client.projects()
                live_jira_projects = [{"key": p.key, "name": p.name} for p in raw]
                live_jira_keys     = {p["key"] for p in live_jira_projects}
                logger.info(f"Preflight: live Jira projects = {live_jira_keys or '(none)'}")
            except Exception as _je:
                logger.warning(f"Preflight: could not fetch live Jira project list: {_je}")

            # ── Load optional jira_routing.json hints ─────────────────────────
            hint_projects: list = []
            try:
                routing_config = load_jira_routing_config()
                if routing_config:
                    hint_projects = [
                        {"key": p.key, "name": p.name}
                        for p in routing_config.projects
                    ]
            except Exception:
                pass

            # ── Build LLM router with live context ───────────────────────────
            llm_router = LLMProjectRouter(
                live_projects=live_jira_projects or [],
                hint_projects=hint_projects,
            )

            # ── Route each epic ───────────────────────────────────────────────
            items_by_decision: list = []
            for epic in epics:
                summary     = epic.get("title", "")
                description = epic.get("description", "")
                decision    = llm_router.route(summary, description)
                items_by_decision.append(
                    {"summary": summary, "description": description, "decision": decision}
                )

            # Group by suggested/resolved project key
            per_project: dict = defaultdict(list)
            for entry in items_by_decision:
                per_project[entry["decision"].project_key].append(entry)

            decisions  = [e["decision"] for e in items_by_decision]
            flat_items = [
                {"summary": e["summary"], "description": e["description"]}
                for e in items_by_decision
            ]

            low_confidence_count = sum(
                1 for d in decisions if d.confidence < 0.5
            )

            # ── Find PM user ──────────────────────────────────────────────────
            with get_session() as session:
                try:
                    from sqlalchemy import case
                    # Prefer product_owner → admin → any linked user
                    pm_user = (
                        session.query(User)
                        .filter(User.telegram_user_id.isnot(None))
                        .join(User.role, isouter=True)
                        .order_by(
                            case(
                                (User.role_id.isnot(None), 0),
                                else_=1
                            ),
                            User.id.asc(),
                        )
                        .first()
                    )
                    assigned_to = pm_user.id if pm_user else None
                    pm_tg_user  = pm_user.telegram_user_id if pm_user else None
                    pm_tg_chat  = pm_user.telegram_chat_id  if pm_user else None
                except Exception:
                    assigned_to = pm_tg_user = pm_tg_chat = None

                if assigned_to is None:
                    logger.warning(
                        "No PM user with Telegram ID found — "
                        "routing approvals will not be sent"
                    )
                    return

                # ── Create project_creation approvals for missing projects ────
                for project_key, epic_entries in per_project.items():
                    # live_jira_keys is None → fetch failed, optimistic
                    # live_jira_keys is set() → Jira empty, all are missing
                    in_jira = live_jira_keys is None or project_key in live_jira_keys
                    decision_for_key = epic_entries[0]["decision"]
                    is_new = decision_for_key.is_new_project_candidate or not in_jira

                    if not is_new:
                        continue

                    items_for_key = [
                        {"summary": e["summary"], "description": e["description"]}
                        for e in epic_entries
                    ]
                    approval_id = create_project_approval_request(
                        decision_for_key, items_for_key, assigned_to, session
                    )
                    if approval_id:
                        msg = (
                            f"New Jira project '{project_key}' needed — "
                            f"approval #{approval_id} created for PM. "
                            f"{len(items_for_key)} epic(s) held until approved."
                        )
                        self.result.warnings.append(msg)
                        logger.warning(msg)
                        if not dry_run:
                            try:
                                from backend.telegram.services.approval_service import ApprovalService
                                ApprovalService._send_telegram_notification(
                                    telegram_user_id=pm_tg_user,
                                    telegram_chat_id=pm_tg_chat,
                                    approval_id=approval_id,
                                )
                                logger.info(
                                    f"Telegram notification sent to PM "
                                    f"(user_id={pm_tg_user}) "
                                    f"for project_creation approval #{approval_id}"
                                )
                            except Exception as notify_err:
                                logger.warning(
                                    f"Could not send Telegram notification: {notify_err}"
                                )

                # ── Routing card for low-confidence items ─────────────────────
                if low_confidence_count > 0:
                    card_id = create_routing_card_approval_request(
                        decisions, flat_items, assigned_to, session
                    )
                    if card_id:
                        logger.info(
                            f"Routing card approval #{card_id} created — "
                            f"{low_confidence_count} low-confidence epic(s) flagged"
                        )
                        if not dry_run:
                            try:
                                from backend.telegram.services.approval_service import ApprovalService
                                ApprovalService._send_telegram_notification(
                                    telegram_user_id=pm_tg_user,
                                    telegram_chat_id=pm_tg_chat,
                                    approval_id=card_id,
                                )
                            except Exception as _notify_err:
                                logger.warning(
                                    f"Could not send routing card notification: {_notify_err}"
                                )

        except Exception as e:
            logger.warning(f"Pre-flight routing check failed (non-fatal): {e}")

    # ========================================================================
    # HELPER METHODS
    # ========================================================================

    def _generate_output_path(self, input_path: str, suffix: str) -> str:
        """Generate output file path based on input path."""
        input_file = Path(input_path)
        date_str = datetime.now().strftime('%Y-%m-%d')
        output_dir = input_file.parent
        return str(output_dir / f"{date_str}_{suffix}")

    def _create_telegram_approval(self, wsjf_file: str) -> int:
        """
        Create Telegram approval request for WSJF-ranked epics.
        
        This is the key integration point between pipeline and Telegram bot.
        After WSJF calculation, we create an approval request that:
        1. Saves to database
        2. Sends Telegram notification to PM
        3. Pauses pipeline until approval
        
        Args:
            wsjf_file: Path to WSJF scores JSON file
        
        Returns:
            approval_id: ID of created approval request
        
        Raises:
            Exception: If no PM user found or approval creation fails
        """
        from backend.telegram.services.approval_service import approval_service
        
        logger.info("Creating Telegram approval request for WSJF-ranked epics")
        
        # Load WSJF data
        with open(wsjf_file, 'r', encoding='utf-8') as f:
            wsjf_data = json.load(f)
        
        epics = wsjf_data.get('epics_with_wsjf', [])
        
        if not epics:
            raise Exception("No epics found in WSJF data")
        
        logger.info(f"Found {len(epics)} epic(s) for approval")
        
        # Get PM user for approval assignment
        pm_user_id = approval_service.get_pm_user_id()
        if not pm_user_id:
            raise Exception(
                "No PM user found for approval. "
                "Please ensure a user with 'product_owner' role exists and has Telegram linked."
            )
        
        logger.info(f"Assigning approval to PM user ID: {pm_user_id}")
        
        # Get system/bot user (requester)
        system_user_id = 1  # Bot user ID
        
        # Create approval request
        approval_id = approval_service.create_epic_approval(
            epics_data={'epics': epics},
            requested_by_user_id=system_user_id,
            assigned_to_user_id=pm_user_id,
            priority='high'
        )
        
        logger.info(f"Created approval request #{approval_id}")
        
        # Log epic details
        print(f"\nEpics submitted for approval:")
        for i, epic in enumerate(epics[:5], 1):  # Show first 5
            title = epic.get('title', 'Untitled')
            wsjf_score = epic.get('wsjf_score', 0)
            print(f"  {i}. {title} (WSJF: {wsjf_score:.1f})")
        
        if len(epics) > 5:
            print(f"  ... and {len(epics) - 5} more")
        
        return approval_id

    def _create_telegram_approval_after_decomposition(self, decomposition_file: str) -> int:
        """
        Create Telegram approval request AFTER decomposition.
        
        This sends the complete decomposed backlog (epics + stories + tasks)
        for PM approval before Jira creation.
        
        Args:
            decomposition_file: Path to decomposed backlog JSON file
        
        Returns:
            approval_id: ID of created approval request
        
        Raises:
            Exception: If no PM user found or approval creation fails
        """
        from backend.telegram.services.approval_service import approval_service
        
        logger.info("Creating Telegram approval request for decomposed backlog")
        
        # Load decomposed data
        with open(decomposition_file, 'r', encoding='utf-8') as f:
            decomposed_data = json.load(f)
        
        epics = decomposed_data.get('epics', [])
        
        if not epics:
            raise Exception("No epics found in decomposed data")
        
        total_stories = sum(len(e.get('stories', [])) for e in epics)
        total_tasks = sum(
            len(s.get('tasks', []))
            for e in epics
            for s in e.get('stories', [])
        )
        
        logger.info(f"Found {len(epics)} epic(s), {total_stories} stories, {total_tasks} tasks for approval")
        
        # Get PM user for approval assignment
        pm_user_id = approval_service.get_pm_user_id()
        if not pm_user_id:
            raise Exception(
                "No PM user found for approval. "
                "Please ensure a user with 'product_owner' role exists and has Telegram linked."
            )
        
        logger.info(f"Assigning approval to PM user ID: {pm_user_id}")
        
        # Get system/bot user (requester)
        system_user_id = 1  # Bot user ID
        
        # Create approval request with decomposed data
        # Store the decomposition file path so we can use it for Jira creation
        approval_data = {
            'decomposition_file': decomposition_file,
            'epics': epics,
            'summary': {
                'total_epics': len(epics),
                'total_stories': total_stories,
                'total_tasks': total_tasks
            }
        }
        
        approval_id = approval_service.create_epic_approval(
            epics_data=approval_data,
            requested_by_user_id=system_user_id,
            assigned_to_user_id=pm_user_id,
            priority='high'
        )
        
        logger.info(f"Created approval request #{approval_id}")
        
        # Log summary
        print(f"\nDecomposed backlog submitted for approval:")
        print(f"  Total Epics: {len(epics)}")
        print(f"  Total Stories: {total_stories}")
        print(f"  Total Tasks: {total_tasks}")
        print()
        print(f"Epics:")
        for i, epic in enumerate(epics[:5], 1):  # Show first 5
            title = epic.get('title', 'Untitled')
            num_stories = len(epic.get('stories', []))
            print(f"  {i}. {title} ({num_stories} stories)")
        
        if len(epics) > 5:
            print(f"  ... and {len(epics) - 5} more")
        
        return approval_id

    def _update_summary_counts(self, decomposed_file: str) -> None:
        """Update summary counts from decomposed backlog."""
        with open(decomposed_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        epics = data.get('epics', [])
        self.result.total_epics = len(epics)
        self.result.total_stories = sum(len(e.get('stories', [])) for e in epics)
        self.result.total_tasks = sum(
            len(s.get('tasks', []))
            for e in epics
            for s in e.get('stories', [])
        )

    def _update_jira_counts(self, jira_file: str) -> None:
        """Update Jira creation counts."""
        with open(jira_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        self.result.jira_items_created = (
            data.get('epics_created', 0) +
            data.get('stories_created', 0) +
            data.get('tasks_created', 0)
        )

    def _request_approval(self, phase_name: str) -> None:
        """Request human approval to continue."""
        print(f"\n{'=' * 70}")
        print(f"APPROVAL REQUIRED: {phase_name.upper()}")
        print(f"{'=' * 70}")
        print(f"\nPipeline paused after {phase_name}.")
        print("Review the output files before continuing.")
        
        while True:
            response = input("\nType 'approve' to continue or 'reject' to stop: ").strip().lower()
            if response == 'approve':
                print("Approved. Continuing pipeline...")
                return
            elif response == 'reject':
                raise Exception(f"Pipeline rejected by user after {phase_name}")
            else:
                print("Invalid input. Please type 'approve' or 'reject'.")

    def _save_checkpoint(self) -> str:
        """Save pipeline checkpoint for recovery."""
        checkpoint_file = Path(self.config.checkpoint_dir) / f"{self.result.pipeline_id}_checkpoint.json"
        
        with open(checkpoint_file, 'w', encoding='utf-8') as f:
            json.dump(self.result.model_dump(), f, indent=2, ensure_ascii=False)
        
        logger.debug(f"Checkpoint saved: {checkpoint_file}")
        return str(checkpoint_file)

    def _generate_final_report(self) -> str:
        """Generate final pipeline report."""
        report_file = Path(self.config.report_dir) / f"{self.result.pipeline_id}_pipeline_report.md"
        
        # Calculate total duration
        if self.result.end_time:
            start = datetime.fromisoformat(self.result.start_time)
            end = datetime.fromisoformat(self.result.end_time)
            total_duration = (end - start).total_seconds()
        else:
            total_duration = 0
        
        # Generate report
        report = f"""# Pipeline Execution Report

**Pipeline ID**: {self.result.pipeline_id}
**Status**: {self.result.status.value}
**Start Time**: {self.result.start_time}
**End Time**: {self.result.end_time or 'N/A'}
**Total Duration**: {total_duration:.2f}s

---

## Input Files

- **PM Transcript**: {self.result.pm_transcript_path}
- **Grooming Transcript**: {self.result.grooming_transcript_path}

---

## Output Files

- **PM Extraction**: {self.result.pm_extraction_file or 'N/A'}
- **Grooming Extraction**: {self.result.grooming_extraction_file or 'N/A'}
- **WSJF Calculation**: {self.result.wsjf_calculation_file or 'N/A'}
- **Decomposition**: {self.result.decomposition_file or 'N/A'}
- **Jira Creation**: {self.result.jira_creation_file or 'N/A'}

---

## Summary

- **Total Epics**: {self.result.total_epics}
- **Total Stories**: {self.result.total_stories}
- **Total Tasks**: {self.result.total_tasks}
- **Jira Items Created**: {self.result.jira_items_created}

---

## Phase Execution

"""
        
        for phase_result in self.result.phases:
            status_icon = "✅" if phase_result.success else "❌"
            report += f"""### {status_icon} {phase_result.phase.value.upper()}

- **Status**: {phase_result.status.value}
- **Duration**: {phase_result.duration_seconds:.2f}s
- **Output**: {phase_result.output_file or 'N/A'}
"""
            if phase_result.error:
                report += f"- **Error**: {phase_result.error}\n"
            report += "\n"
        
        # Errors and warnings
        if self.result.errors:
            report += "---\n\n## Errors\n\n"
            for error in self.result.errors:
                report += f"- {error}\n"
        
        if self.result.warnings:
            report += "\n---\n\n## Warnings\n\n"
            for warning in self.result.warnings:
                report += f"- {warning}\n"
        
        report += f"""
---

*Report generated on {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}*
"""
        
        # Save report
        with open(report_file, 'w', encoding='utf-8') as f:
            f.write(report)
        
        print(f"\nFinal report saved: {report_file}")
        return str(report_file)

    def resume_from_checkpoint(self, checkpoint_path: str) -> PipelineResult:
        """
        Resume pipeline from saved checkpoint.
        
        Args:
            checkpoint_path: Path to checkpoint file
        
        Returns:
            PipelineResult
            
        Raises:
            FileNotFoundError: If checkpoint file doesn't exist
            ValueError: If checkpoint is invalid
        """
        print(f"\n{'=' * 70}")
        print("RESUMING PIPELINE FROM CHECKPOINT")
        print(f"{'=' * 70}")
        print(f"Checkpoint: {checkpoint_path}\n")
        
        # Load checkpoint
        checkpoint_file = Path(checkpoint_path)
        if not checkpoint_file.exists():
            raise FileNotFoundError(f"Checkpoint not found: {checkpoint_path}")
        
        with open(checkpoint_file, 'r', encoding='utf-8') as f:
            checkpoint_data = json.load(f)
        
        # Restore pipeline result
        self.result = PipelineResult(**checkpoint_data)
        
        print(f"Pipeline ID: {self.result.pipeline_id}")
        print(f"Original start time: {self.result.start_time}")
        print(f"Status: {self.result.status}")
        
        # Find last successful phase
        last_successful_phase = None
        for phase_result in self.result.phases:
            if phase_result.success:
                last_successful_phase = phase_result.phase
        
        if not last_successful_phase:
            print("\nNo successful phases found. Starting from beginning.")
            return self.run(
                pm_transcript_path=self.result.pm_transcript_path,
                grooming_transcript_path=self.result.grooming_transcript_path,
                create_in_jira=True
            )
        
        print(f"Last successful phase: {last_successful_phase}")
        
        # Determine next phase to run
        phase_order = [
            PipelinePhase.VALIDATION,
            PipelinePhase.PM_EXTRACTION,
            PipelinePhase.GROOMING_EXTRACTION,
            PipelinePhase.WSJF_CALCULATION,
            PipelinePhase.DECOMPOSITION,
            PipelinePhase.JIRA_CREATION
        ]
        
        try:
            last_phase_index = phase_order.index(last_successful_phase)
            next_phase_index = last_phase_index + 1
            
            if next_phase_index >= len(phase_order):
                print("\nAll phases already completed!")
                self.result.status = PipelineStatus.COMPLETED
                self.result.end_time = datetime.now().isoformat()
                return self.result
            
            next_phase = phase_order[next_phase_index]
            print(f"Resuming from phase: {next_phase}")
            
        except ValueError:
            raise ValueError(f"Invalid phase in checkpoint: {last_successful_phase}")
        
        # Resume execution from next phase
        print(f"\n{'=' * 70}")
        print(f"RESUMING FROM PHASE: {next_phase.value.upper()}")
        print(f"{'=' * 70}\n")
        
        try:
            # Resume based on next phase
            if next_phase == PipelinePhase.PM_EXTRACTION:
                pm_output = self._run_phase(
                    PipelinePhase.PM_EXTRACTION,
                    self._extract_pm_meeting,
                    self.result.pm_transcript_path
                )
                self.result.pm_extraction_file = pm_output
                next_phase_index += 1
            
            if next_phase_index <= phase_order.index(PipelinePhase.GROOMING_EXTRACTION):
                if next_phase == PipelinePhase.GROOMING_EXTRACTION:
                    grooming_output = self._run_phase(
                        PipelinePhase.GROOMING_EXTRACTION,
                        self._extract_grooming_meeting,
                        self.result.grooming_transcript_path,
                        self.result.pm_extraction_file
                    )
                    self.result.grooming_extraction_file = grooming_output
                    next_phase_index += 1
            
            if next_phase_index <= phase_order.index(PipelinePhase.WSJF_CALCULATION):
                if next_phase == PipelinePhase.WSJF_CALCULATION:
                    wsjf_output = self._run_phase(
                        PipelinePhase.WSJF_CALCULATION,
                        self._calculate_wsjf,
                        self.result.pm_extraction_file,
                        self.result.grooming_extraction_file
                    )
                    self.result.wsjf_calculation_file = wsjf_output
                    next_phase_index += 1
            
            if next_phase_index <= phase_order.index(PipelinePhase.DECOMPOSITION):
                if next_phase == PipelinePhase.DECOMPOSITION:
                    decomposition_output = self._run_phase(
                        PipelinePhase.DECOMPOSITION,
                        self._decompose_epics,
                        self.result.wsjf_calculation_file
                    )
                    self.result.decomposition_file = decomposition_output
                    self._update_summary_counts(decomposition_output)
                    next_phase_index += 1
            
            if next_phase_index <= phase_order.index(PipelinePhase.JIRA_CREATION):
                if next_phase == PipelinePhase.JIRA_CREATION:
                    jira_output = self._run_phase(
                        PipelinePhase.JIRA_CREATION,
                        self._create_in_jira,
                        self.result.decomposition_file,
                        False  # dry_run
                    )
                    self.result.jira_creation_file = jira_output
                    self._update_jira_counts(jira_output)
            
            # Mark as complete
            self.result.status = PipelineStatus.COMPLETED
            self.result.current_phase = PipelinePhase.COMPLETE
            self.result.end_time = datetime.now().isoformat()
            
            print("\n" + "=" * 70)
            print("PIPELINE RESUME COMPLETE")
            print("=" * 70)
            
            # Generate final report
            if self.config.generate_final_report:
                self._generate_final_report()
            
            # Save final checkpoint
            if self.config.save_checkpoints:
                self._save_checkpoint()
            
            return self.result
        
        except Exception as e:
            logger.error(f"Pipeline resume failed: {e}")
            self.result.status = PipelineStatus.FAILED
            self.result.errors.append(f"Resume failed: {str(e)}")
            self.result.end_time = datetime.now().isoformat()
            
            # Save checkpoint on failure
            if self.config.save_checkpoints:
                self._save_checkpoint()
            
            print(f"\nPipeline resume failed: {e}")
            raise


# ============================================================================
# MAIN EXECUTION
# ============================================================================

def main():
    """Main execution function for testing the pipeline."""
    from dotenv import load_dotenv
    load_dotenv()
    
    # Example usage
    pipeline = BacklogPipeline()
    
    result = pipeline.run(
        pm_transcript_path="backend/data/pm_meetings/example_pm_transcript.txt",
        grooming_transcript_path="backend/data/grooming_meetings/example_grooming_transcript.txt",
        create_in_jira=True,
        dry_run=False
    )
    
    print("\n" + "=" * 70)
    print("PIPELINE RESULT")
    print("=" * 70)
    print(f"Status: {result.status}")
    print(f"Epics: {result.total_epics}")
    print(f"Stories: {result.total_stories}")
    print(f"Tasks: {result.total_tasks}")
    print(f"Jira Items Created: {result.jira_items_created}")


if __name__ == "__main__":
    main()
