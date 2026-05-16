"""
Smoke test — Sprint-Aware Jira Project & Team Routing (Phase 4)

Tests the ROUTING MECHANISM generically — not tied to any specific
transcript, domain, or keyword set. A company can configure any projects
and keywords in jira_routing.json; the mechanism must work for all of them.

Tests:
  1. Confidence formula: 3 keyword hits → high conf, 0 hits → triage
  2. Project selection: best-matching project wins
  3. Registry guard: project not in registry → triage fallback, no Jira error
  4. project_creation approval: unknown project triggers approval + Telegram
  5. execute_project_creation wired in execute_approval
  6. handle_editkey_input wired in message_handler

Run:
    python smoke_test_project_routing.py

The bot must be running for test 4 Telegram delivery:
    python -m backend.telegram.bot
"""
import sys
import inspect
from dotenv import load_dotenv
load_dotenv()

PASS = "✅ PASS"
FAIL = "❌ FAIL"
results = []

def check(label, condition, detail=""):
    status = PASS if condition else FAIL
    results.append((status, label, detail))
    print(f"  {status}  {label}" + (f"\n         {detail}" if detail else ""))
    return condition


print("=" * 65)
print("SMOKE TEST — Jira Project & Team Routing (Phase 4)")
print("=" * 65)


# ── Test 1: Confidence formula is generic (not keyword-count-dependent) ──
print("\n[1] Confidence formula: 3 hits = 1.0, independent of keyword list size")
try:
    from backend.tools.jira_routing import JiraRoutingResolver, JiraRoutingConfig, ProjectRoutingRule

    # Build a minimal synthetic config — no business-domain keywords
    config = JiraRoutingConfig(
        default_project_key="ALPHA",
        default_component=None,
        triage_project_key="TRIAGE",
        triage_project_name="Triage",
        triage_component="Triage",
        projects=[
            ProjectRoutingRule(key="ALPHA", name="Alpha Project",
                               keywords=["foo", "bar", "baz", "qux", "quux",
                                         "corge", "grault", "garply", "waldo", "fred"]),
            ProjectRoutingRule(key="BETA",  name="Beta Project",
                               keywords=["xyz", "abc", "def"]),
        ],
        teams=[],
    )
    resolver = JiraRoutingResolver(config)

    d0 = resolver.resolve("nothing matches here at all", "")
    check("0 keyword hits → triage", d0.is_triage and d0.confidence == 0.0,
          f"project={d0.project_key} conf={d0.confidence}")

    d1 = resolver.resolve("foo is here", "")
    check("1 keyword hit → conf=0.33", abs(d1.confidence - 1/3) < 0.01,
          f"conf={d1.confidence:.3f}")

    d3 = resolver.resolve("foo bar baz text", "")
    check("3 keyword hits → conf=1.0", d3.confidence == 1.0,
          f"conf={d3.confidence}")

    # Large-keyword-list project (ALPHA, 10 keywords) vs small (BETA, 3 keywords)
    # BETA should win when its keywords match more precisely
    d_beta = resolver.resolve("xyz abc def", "")
    check("Best-match project wins regardless of list size",
          d_beta.project_key == "BETA",
          f"got project={d_beta.project_key} conf={d_beta.confidence:.2f}")

except Exception as e:
    check("Routing resolver", False, str(e))


# ── Test 2: Registry guard — unknown project falls back to triage ─────
print("\n[2] Registry guard: project not in registry → triage (no Jira error)")
try:
    from backend.db.connection import get_session
    from backend.services.routing_service import is_project_known

    with get_session() as s:
        known_projects = []
        unknown_projects = []

        # Enumerate a few keys and categorise them
        for key in ["SP", "MOBILE", "BACKEND", "TRIAGE", "FAKEXYZ"]:
            known = is_project_known(key, s)
            (known_projects if known else unknown_projects).append(key)

        check("At least one project is registered (SP)",
              "SP" in known_projects, f"known={known_projects}")
        check("Un-seeded projects are correctly unknown",
              len(unknown_projects) >= 1, f"unknown={unknown_projects}")

except Exception as e:
    check("Registry check", False, str(e))


# ── Test 3: project_creation approval DB insert (no NOT NULL violation) ──
print("\n[3] project_creation approval can be inserted into DB")
TEST3_APPROVAL_ID = None
TEST3_PM_USER = None
try:
    from backend.tools.jira_routing import (
        load_jira_routing_config, JiraRoutingResolver, RoutingDecision,
    )
    from backend.db.connection import get_session
    from backend.db.models import ApprovalRequest, User
    from backend.services.routing_service import create_project_approval_request

    # Build a synthetic RoutingDecision for a project that doesn't exist
    synthetic_decision = RoutingDecision(
        project_key="SMOKETEST",
        project_name="Smoke Test Project",
        component="General",
        matched_project=True,
        matched_team=False,
        is_triage=False,
        team_name=None,
        confidence=0.9,
        decision_reason="keyword_match",
        is_new_project_candidate=True,
        suggested_project_name="Smoke Test Project",
    )
    items = [{"summary": "Smoke test epic", "description": "Auto-generated by smoke test"}]

    with get_session() as s:
        pm_user = s.query(User).filter(User.telegram_user_id.isnot(None)).first()
        if not pm_user:
            check("PM user with Telegram exists", False, "No user with telegram_user_id found in DB")
        else:
            # Extract scalar values while session is open
            _tg_user_id = pm_user.telegram_user_id
            _tg_chat_id = pm_user.telegram_chat_id
            _pm_id      = pm_user.id
            TEST3_PM_USER = {"telegram_user_id": _tg_user_id, "telegram_chat_id": _tg_chat_id}

            approval_id = create_project_approval_request(
                synthetic_decision, items, _pm_id, s
            )
            check("Approval inserted without NOT NULL error",
                  approval_id is not None, f"approval_id={approval_id}")

            if approval_id:
                approval = s.query(ApprovalRequest).filter(
                    ApprovalRequest.approval_id == approval_id
                ).first()
                check("request_type = project_creation",
                      approval.request_type == "project_creation")
                check("suggested_key stored correctly",
                      approval.request_data.get("suggested_key") == "SMOKETEST",
                      f"key={approval.request_data.get('suggested_key')}")
                check("entity_id not null",
                      approval.entity_id is not None,
                      f"entity_id={approval.entity_id}")
                TEST3_APPROVAL_ID = approval_id

except Exception as e:
    check("project_creation DB insert", False, str(e))


# ── Test 4: Telegram notification fires (no asyncio crash) ────────────
print("\n[4] Telegram notification delivery (no asyncio error)")
if TEST3_APPROVAL_ID and TEST3_PM_USER:
    try:
        from backend.telegram.services.approval_service import ApprovalService
        ApprovalService._send_telegram_notification(
            telegram_user_id=TEST3_PM_USER["telegram_user_id"],
            telegram_chat_id=TEST3_PM_USER["telegram_chat_id"],
            approval_id=TEST3_APPROVAL_ID,
        )
        check("Telegram notification sent without exception", True)
    except Exception as e:
        check("Telegram notification", False, str(e))
else:
    check("Telegram notification (skipped — no approval created)", False,
          "Test 3 failed; fix DB insert first")


# ── Test 5: execute_project_creation wired in execute_approval ────────
print("\n[5] execute_project_creation wired in execute_approval")
try:
    from backend.telegram.handlers.callback_handler import execute_approval, execute_project_creation
    check("execute_project_creation importable", True)
    src = inspect.getsource(execute_approval)
    check("execute_approval dispatches project_creation", "project_creation" in src)
except Exception as e:
    check("execute_project_creation wiring", False, str(e))


# ── Test 6: handle_editkey_input wired in message_handler ─────────────
print("\n[6] Edit-key conversation flow wired in message_handler")
try:
    from backend.telegram.handlers.message_handler import handle_message
    src = inspect.getsource(handle_message)
    check("pending_editkey_approval_id branch present", "pending_editkey_approval_id" in src)
    check("handle_editkey_input imported",              "handle_editkey_input" in src)
except Exception as e:
    check("message_handler wiring", False, str(e))


# ── Summary ───────────────────────────────────────────────────────────
print("\n" + "=" * 65)
passed = sum(1 for s, *_ in results if s == PASS)
failed = sum(1 for s, *_ in results if s == FAIL)
print(f"RESULT: {passed} passed, {failed} failed out of {len(results)} checks")
if failed:
    print("\nFailed checks:")
    for s, label, detail in results:
        if s == FAIL:
            print(f"  {label}: {detail}")
print("=" * 65)

if TEST3_APPROVAL_ID:
    print(f"\n📱 Telegram card sent for approval #{TEST3_APPROVAL_ID}  (project: SMOKETEST)")
    print("   You should see in Telegram:")
    print("   🆕 New Jira Project Detected")
    print("      Suggested Key: SMOKETEST")
    print("      [✅ Approve] [✏️ Edit Key] [❌ Reject → Triage]")
    print()
    print("   ✅ Approve  → bot calls Jira REST API, creates project, registers in DB")
    print("   ✏️ Edit Key → reply with new key (e.g. MYAPP), then approve")
    print("   ❌ Reject   → items stay in triage")

sys.exit(0 if failed == 0 else 1)
