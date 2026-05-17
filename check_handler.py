"""
Runtime test for callback_handler functions.
Simulates approval button presses without Telegram.
"""
import sys, os, asyncio
sys.path.insert(0, os.path.dirname(__file__))
from dotenv import load_dotenv; load_dotenv()

from unittest.mock import MagicMock, AsyncMock, patch
from datetime import datetime, timezone

print("=== Importing callback_handler ===")
from backend.telegram.handlers.callback_handler import (
    handle_approve, handle_reject, handle_rejection_reason,
    handle_edit, execute_approval, execute_project_creation,
)
print("Import: OK\n")

# ── Helpers ────────────────────────────────────────────────────────────────────

def make_approval(request_type, request_data):
    m = MagicMock()
    m.approval_id = 99
    m.request_type = request_type
    m.request_data = request_data
    m.approved_data = request_data
    m.assigned_to = 5
    m.status = 'pending'
    return m

def make_user(uid=5, name="Sameer K"):
    u = MagicMock()
    u.id = uid
    u.display_name = name
    u.role_id = 3  # product_owner
    return u

def make_query(text="Test approval message"):
    q = MagicMock()
    q.data = "approve_99"
    q.edit_message_text = AsyncMock()
    q.message = MagicMock()
    q.message.text = text
    q.answer = AsyncMock()
    return q

def make_session(user, approval):
    s = MagicMock()
    s.query.return_value.filter.return_value.first.side_effect = [user, approval]
    s.commit = MagicMock()
    s.__enter__ = lambda self: self
    s.__exit__ = MagicMock(return_value=False)
    return s

# ── Tests ──────────────────────────────────────────────────────────────────────

async def test_handle_approve_routing_classification():
    print("--- test: handle_approve (routing_classification) ---")
    approval = make_approval('routing_classification', {
        'decisions': [
            {'project_key': 'SP', 'summary': 'Auth system', 'confidence': 0.9},
        ]
    })
    user = make_user()
    query = make_query()
    session = MagicMock()
    session.commit = MagicMock()

    with patch('backend.db.crud.add_approval_history'):
        await handle_approve(query, session, approval, user)

    query.edit_message_text.assert_called()
    last_call = query.edit_message_text.call_args_list[-1]
    text = last_call[0][0] if last_call[0] else str(last_call)
    print(f"  Final message: {text[:80]!r}")
    print("  PASS\n")


async def test_handle_reject_sets_user_data():
    print("--- test: handle_reject sets awaiting_rejection_reason ---")
    approval = make_approval('epic_creation', {})
    user = make_user()
    query = make_query()
    session = MagicMock()
    context = MagicMock()
    context.user_data = {}

    await handle_reject(query, session, approval, user, context)

    assert context.user_data.get('awaiting_rejection_reason') == 99
    query.edit_message_text.assert_called_once()
    print(f"  context.user_data: {context.user_data}")
    print("  PASS\n")


async def test_handle_rejection_reason_project_creation():
    print("--- test: handle_rejection_reason (project_creation - Option A) ---")
    approval = make_approval('project_creation', {
        'suggested_key': 'NEWPROJ',
        'items_count': 3,
        'sample_summaries': ['Auth', 'Payment', 'Dashboard'],
    })
    approval.rejection_reason = None
    approval.reviewed_at = None

    user_mock = MagicMock()
    user_mock.id = 42
    user_mock.id = 42

    update = MagicMock()
    update.message.text = "Not needed right now"
    update.message.reply_text = AsyncMock()
    update.effective_user.id = 42

    context = MagicMock()
    context.user_data = {'awaiting_rejection_reason': 99}

    db_user = make_user(uid=5, name="Sameer K")
    db_user.telegram_user_id = 42

    with patch('backend.telegram.handlers.callback_handler.get_session') as mock_gs, \
         patch('backend.db.crud.add_approval_history'):
        mock_session = MagicMock()
        mock_session.__enter__ = lambda s: s
        mock_session.__exit__ = MagicMock(return_value=False)
        mock_session.query.return_value.filter.return_value.first.side_effect = [db_user, approval]
        mock_session.commit = MagicMock()
        mock_gs.return_value = mock_session

        await handle_rejection_reason(update, context)

    update.message.reply_text.assert_called_once()
    call_text = update.message.reply_text.call_args[0][0]
    assert 'NEWPROJ' in call_text
    assert 'dropped' in call_text.lower() or 'Rejected' in call_text
    print(f"  Reply text: {call_text[:120]!r}")
    assert context.user_data['awaiting_rejection_reason'] is None
    print("  context cleared: OK")
    print("  PASS\n")


async def test_execute_project_creation_bad_key():
    print("--- test: execute_project_creation (bad key raises) ---")
    approval = make_approval('project_creation', {
        'suggested_key': '',   # empty = should raise
        'suggested_name': 'Test Project',
    })

    try:
        await execute_project_creation(approval)
        print("  ERROR: should have raised")
    except Exception as e:
        print(f"  Raised as expected: {e}")
        print("  PASS\n")


async def test_execute_approval_dispatch():
    print("--- test: execute_approval dispatch ---")
    for rtype, expected_prefix in [
        ('routing_classification', 'ROUTING'),
        ('unknown_type', None),
    ]:
        approval = make_approval(rtype, {'decisions': []})
        result = await execute_approval(approval)
        print(f"  {rtype}: result={result}")
        if expected_prefix:
            assert any(expected_prefix in str(r) for r in result), f"Expected {expected_prefix} in {result}"
    print("  PASS\n")


async def main():
    print("=" * 60)
    print("  callback_handler RUNTIME TESTS")
    print("=" * 60 + "\n")

    tests = [
        test_handle_approve_routing_classification,
        test_handle_reject_sets_user_data,
        test_handle_rejection_reason_project_creation,
        test_execute_project_creation_bad_key,
        test_execute_approval_dispatch,
    ]

    passed = 0
    failed = 0
    for t in tests:
        try:
            await t()
            passed += 1
        except Exception as e:
            print(f"  FAILED: {e}")
            import traceback; traceback.print_exc()
            failed += 1

    print("=" * 60)
    print(f"  Results: {passed} passed, {failed} failed")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
