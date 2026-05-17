"""
ScrumPilot - Full E2E Workflow Test
=====================================
Tests the complete 3-step flow:

  STEP 1 : Project Routing Pre-Check
           -> New project? Telegram approval (Scrum template)
  STEP 2 : Meeting Type Classification
  STEP 3 : Backlog Pipeline
           -> Extract epics -> WSJF -> Decompose -> Telegram gate -> Jira

USAGE
-----
# Mode 1: Dry run  (no Jira writes, no Telegram bot needed)
  python test_workflow.py --dry-run

# Mode 2: Full E2E (Telegram bot must be running in another terminal)
  python test_workflow.py --full

# Mode 3: Just start the Telegram bot
  python test_workflow.py --start-bot

# Mode 4: Use a custom transcript
  python test_workflow.py --full --pm-transcript path/to/transcript.txt

REQUIREMENTS FOR --full
-----------------------
  Terminal 1: python test_workflow.py --start-bot
  Terminal 2: python test_workflow.py --full
  Then: Open Telegram and approve/reject the messages sent by the bot
"""

import os, sys, json, logging, argparse, time, threading
from pathlib import Path
from datetime import datetime

# ── project root on path ─────────────────────────────────────────────────────
ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv
load_dotenv()

# Force UTF-8 stdout on Windows
if sys.platform == "win32":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("e2e_test")

# Suppress noisy libraries
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)
logging.getLogger("telegram").setLevel(logging.WARNING)

W = 68  # banner width

def banner(title, char="="):
    print(f"\n{char*W}")
    print(f"  {title}")
    print(f"{char*W}\n")

def ok(msg):   print(f"  [OK]   {msg}")
def warn(msg): print(f"  [WARN] {msg}")
def fail(msg): print(f"  [FAIL] {msg}")
def info(msg): print(f"  [INFO] {msg}")
def step(n, msg): print(f"\n  --- Step {n}: {msg} ---")


# =============================================================================
# ENV CHECK
# =============================================================================

def check_env(full_mode: bool) -> bool:
    banner("ENVIRONMENT CHECK")
    required = ["JIRA_URL", "JIRA_EMAIL", "JIRA_API_TOKEN", "GROQ_API_KEY"]
    if full_mode:
        required.append("TELEGRAM_BOT_TOKEN")

    ok_all = True
    for var in required:
        val = os.getenv(var)
        if val:
            ok(f"{var} = {'*'*8}")
        else:
            fail(f"{var} MISSING")
            ok_all = False

    # Optional
    for var in ["JIRA_PROJECT_KEY", "JIRA_ROUTING_CONFIG_PATH"]:
        val = os.getenv(var)
        info(f"{var} = {val or '(not set - will use defaults)'}")

    return ok_all


# =============================================================================
# GROQ RATE LIMIT CHECK
# =============================================================================

def check_groq() -> bool:
    """Return True if Groq API is available."""
    try:
        import httpx
        api_key = os.environ["GROQ_API_KEY"]
        r = httpx.get(
            "https://api.groq.com/openai/v1/models",
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=8,
        )
        if r.status_code == 200:
            ok("Groq API: available")
            return True
        elif r.status_code == 429:
            body = r.json().get("error", {})
            msg = body.get("message", "")
            warn(f"Groq rate limit: {msg[:120]}")
            return False
        else:
            warn(f"Groq API returned {r.status_code}")
            return False
    except Exception as e:
        warn(f"Groq check failed: {e}")
        return False


# =============================================================================
# START TELEGRAM BOT  (--start-bot mode)
# =============================================================================

def start_bot():
    """Start the Telegram bot in polling mode. Blocks until Ctrl+C."""
    banner("TELEGRAM BOT - Starting (Ctrl+C to stop)")
    from backend.telegram.bot import ScrumPilotBot
    bot = ScrumPilotBot()
    print("  Bot is running. Open Telegram and try /start")
    print("  When the pipeline sends an approval, tap the button in Telegram.\n")
    bot.run_polling()


# =============================================================================
# STEP 1 - PROJECT PRE-CHECK
# =============================================================================

def step1_preflight(transcript_path: str, dry_run: bool) -> dict:
    banner("STEP 1: Project Routing Pre-Check")
    result = {"new_project_needed": False, "suggested_key": None}

    step(1, "Load transcript")
    with open(transcript_path, encoding="utf-8") as f:
        text = f.read()
    info(f"Loaded {len(text)} chars from {transcript_path}")

    step(2, "Check DB registry for known projects")
    try:
        from backend.db.connection import get_session
        from backend.services.routing_service import get_known_project_keys
        with get_session() as s:
            known = get_known_project_keys(s)
        ok(f"Known projects in registry: {known or '(none yet)'}")
    except Exception as e:
        warn(f"DB registry check skipped: {e}")
        known = []

    step(3, "LLM domain sniff (fast, single call)")
    try:
        from backend.tools.llm_project_router import LLMProjectRouter
        router = LLMProjectRouter()
        d = router.route(
            title="Domain sniff",
            description=text[:600],
        )
        info(f"Detected: project_key={d.project_key!r}  is_new={d.is_new_project_candidate}  confidence={d.confidence:.2f}")

        if d.is_new_project_candidate:
            result["new_project_needed"] = True
            result["suggested_key"]  = d.project_key
            result["suggested_name"] = getattr(d, "suggested_project_name", None) or d.project_key
            warn(f"New Scrum project needed: {result['suggested_key']!r}")

            if dry_run:
                warn("DRY RUN - skipping Telegram project approval")
                info("In production, PM sees:")
                print(f"""
    +------------------------------------------------+
    | New Jira Project Request                       |
    | Key:      {result['suggested_key']:<36} |
    | Name:     {result['suggested_name']:<36} |
    | Template: Scrum (enforced)                     |
    | [Approve]  [Reject]  [Edit Key]                |
    +------------------------------------------------+
""")
            else:
                info("Project approval will be triggered inside the pipeline (Step 3)")
        else:
            ok("All detected projects exist - no new project approval needed")
    except Exception as e:
        warn(f"LLM router error: {e}")

    return result


# =============================================================================
# STEP 2 - MEETING TYPE
# =============================================================================

def step2_classify(transcript_path: str) -> str:
    banner("STEP 2: Meeting Type Classification")
    with open(transcript_path, encoding="utf-8") as f:
        text = f.read().lower()

    scores = {
        "pm_backlog":      sum(1 for k in ["epic","q2","roadmap","stakeholder","launch","business value","priority","scope"] if k in text),
        "sprint_planning": sum(1 for k in ["sprint planning","sprint goal","velocity","story points","sprint backlog"] if k in text),
        "standup":         sum(1 for k in ["standup","yesterday","today","blocker","blocked","impediment","in progress"] if k in text),
    }
    meeting_type = max(scores, key=scores.get)
    info(f"Keyword scores: {scores}")
    ok(f"Meeting type: {meeting_type.upper()}")
    return meeting_type


# =============================================================================
# STEP 3 - RUN PIPELINE
# =============================================================================

def step3_pipeline(meeting_type, pm_path, grooming_path, create_in_jira, dry_run):
    banner("STEP 3: Pipeline Execution + Telegram Approval Gate")

    if meeting_type != "pm_backlog":
        info(f"Meeting type is '{meeting_type}' - only pm_backlog is tested here")
        return

    info(f"create_in_jira={create_in_jira}  dry_run={dry_run}")

    if dry_run:
        warn("DRY RUN: Jira writes are simulated, Telegram approvals are logged only")

    from backend.pipelines.backlog_pipeline import BacklogPipeline
    pipeline = BacklogPipeline()

    start = time.time()
    result = pipeline.run(
        pm_transcript_path=pm_path,
        grooming_transcript_path=grooming_path,
        create_in_jira=create_in_jira,
        dry_run=dry_run,
    )
    elapsed = time.time() - start

    banner("Pipeline Result", "-")
    print(f"  Status          : {result.status}")
    print(f"  Epics           : {result.total_epics}")
    print(f"  Stories         : {result.total_stories}")
    print(f"  Tasks           : {result.total_tasks}")
    print(f"  Jira Created    : {result.jira_items_created}")
    print(f"  Elapsed         : {elapsed:.1f}s")

    if hasattr(result, "approval_id") and result.approval_id:
        ok(f"Telegram approval #{result.approval_id} sent to PM")
        print()
        print("  >>> Open Telegram now and approve/reject the message <<<")
        print("  >>> Once approved, Jira items will be created automatically <<<")
    else:
        if dry_run:
            warn("Dry run - no Telegram message sent")
        else:
            info("No pending approval (check logs above)")

    if result.errors:
        print("\n  Errors:")
        for e in result.errors: print(f"    - {e}")
    if result.warnings:
        print("\n  Warnings:")
        for w in result.warnings: print(f"    - {w}")

    return result


# =============================================================================
# DRY-RUN SMOKE TEST  (--dry-run)
# =============================================================================

def run_dry(args):
    banner("ScrumPilot E2E - DRY RUN (no Jira writes)", "=")
    info("Nothing will be created in Jira. Telegram messages are logged only.\n")

    if not check_env(full_mode=False):
        fail("Fix .env and retry"); sys.exit(1)

    if not check_groq():
        warn("Groq not available. Waiting 60s then retrying once...")
        time.sleep(60)
        if not check_groq():
            fail("Groq still rate-limited. Try again in ~15 minutes."); sys.exit(1)

    preflight = step1_preflight(args.pm_transcript, dry_run=True)
    meeting   = step2_classify(args.pm_transcript)
    step3_pipeline(meeting, args.pm_transcript, args.grooming,
                   create_in_jira=False, dry_run=True)
    banner("Dry Run Complete", "=")


# =============================================================================
# FULL E2E (--full)
# =============================================================================

def run_full(args):
    banner("ScrumPilot E2E - FULL TEST (real Jira + Telegram)", "=")
    print("  REQUIREMENTS:")
    print("    1. Telegram bot must be running in ANOTHER terminal:")
    print("       python test_workflow.py --start-bot")
    print("    2. You (the PM) must be registered in the bot (/start)")
    print("    3. Groq API must be available")
    print()

    if not check_env(full_mode=True):
        fail("Fix .env and retry"); sys.exit(1)

    banner("Groq API Check")
    if not check_groq():
        warn("Groq is rate-limited. Checking every 30s...")
        for attempt in range(20):
            time.sleep(30)
            print(f"  Attempt {attempt+1}/20...")
            if check_groq():
                break
        else:
            fail("Groq still unavailable after 10 minutes. Exiting."); sys.exit(1)

    preflight = step1_preflight(args.pm_transcript, dry_run=False)
    meeting   = step2_classify(args.pm_transcript)
    result    = step3_pipeline(meeting, args.pm_transcript, args.grooming,
                                create_in_jira=True, dry_run=False)

    if result and hasattr(result, "approval_id") and result.approval_id:
        banner("WAITING FOR TELEGRAM APPROVAL", "-")
        print("  The pipeline has PAUSED at the Telegram approval gate.")
        print("  Open Telegram and tap [Approve] on the pending request.")
        print("  Once approved, Jira items will be created automatically.\n")
        print("  This test script exits here.")
        print("  Watch the Telegram bot terminal for Jira creation logs.\n")

    banner("Full E2E Test Complete", "=")


# =============================================================================
# MAIN
# =============================================================================

def main():
    p = argparse.ArgumentParser(description="ScrumPilot full E2E workflow test")
    mode = p.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run",    action="store_true", help="Dry run - no Jira writes, no bot needed")
    mode.add_argument("--full",       action="store_true", help="Full E2E - real Jira + Telegram (bot must be running)")
    mode.add_argument("--start-bot",  action="store_true", help="Start the Telegram bot (run in a separate terminal)")

    p.add_argument("--pm-transcript", default="backend/data/pm_meetings/example_pm_transcript.txt")
    p.add_argument("--grooming",      default="backend/data/grooming_meetings/example_grooming_transcript.txt")
    args = p.parse_args()

    print(f"\n  ScrumPilot E2E Test  |  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"  PM transcript : {args.pm_transcript}")

    if args.start_bot:
        start_bot()
    elif args.dry_run:
        run_dry(args)
    elif args.full:
        run_full(args)


if __name__ == "__main__":
    main()
