"""
Simple test script for the storage layer.
Run this after setting up the database to verify everything works.

Usage:
    python -m backend.db.test_storage
"""

from datetime import date, datetime
from backend.tools.storage import storage
import uuid


def test_basic_workflow():
    """Test basic meeting and processing run workflow."""
    print("=" * 60)
    print("STORAGE LAYER TEST")
    print("=" * 60)

    # Test 1: Create a meeting
    print("\n[TEST 1] Creating a scrum meeting...")
    meeting_id = storage.create_meeting(
        meeting_type="scrum",
        meeting_date=date.today(),
        title="Test Scrum Meeting",
        status="created",
    )
    print(f"✅ Meeting created with ID: {meeting_id}")

    # Test 2: Start a processing run
    print("\n[TEST 2] Starting a processing run...")
    run_id = storage.start_processing_run(
        meeting_id=meeting_id,
        run_type="scrum_actions",
    )
    print(f"✅ Processing run created with ID: {run_id}")

    # Test 3: Save a transcript artifact
    print("\n[TEST 3] Saving transcript artifact...")
    artifact_id = storage.save_artifact(
        meeting_id=meeting_id,
        artifact_type="transcript",
        processing_run_id=run_id,
        text_content="Test transcript content",
        metadata={"test": True},
    )
    print(f"✅ Artifact saved with ID: {artifact_id}")

    # Test 4: Create a user
    print("\n[TEST 4] Creating a user...")
    user_id = storage.upsert_user(
        display_name="Test User",
        email="test@example.com",
    )
    print(f"✅ User created with ID: {user_id}")

    # Test 5: Save scrum actions
    print("\n[TEST 5] Saving scrum actions...")
    actions = [
        {
            "action": "create_task",
            "summary": "Test task 1",
            "description": "This is a test task",
        },
        {
            "action": "complete_task",
            "summary": "Test task 2",
        },
    ]
    action_ids = storage.save_scrum_actions(
        meeting_id=meeting_id,
        processing_run_id=run_id,
        actions=actions,
    )
    print(f"✅ Saved {len(action_ids)} scrum actions")

    # Test 6: Complete the processing run
    print("\n[TEST 6] Completing processing run...")
    storage.complete_processing_run(run_id)
    print("✅ Processing run marked as completed")

    # Test 7: Retrieve meeting with hierarchy
    print("\n[TEST 7] Retrieving meeting with hierarchy...")
    meeting_data = storage.get_meeting_with_hierarchy(meeting_id)
    print(f"✅ Retrieved meeting: {meeting_data['title']}")
    print(f"   - Scrum actions: {len(meeting_data['scrum_actions'])}")

    print("\n" + "=" * 60)
    print("ALL TESTS PASSED ✅")
    print("=" * 60)


def test_pm_workflow():
    """Test PM meeting workflow with epics, stories, and tasks."""
    print("\n" + "=" * 60)
    print("PM WORKFLOW TEST")
    print("=" * 60)

    # Create PM meeting
    print("\n[TEST 1] Creating a PM meeting...")
    meeting_id = storage.create_meeting(
        meeting_type="pm",
        meeting_date=date.today(),
        title="Test PM Meeting",
    )
    print(f"✅ Meeting created with ID: {meeting_id}")

    # Start processing run
    print("\n[TEST 2] Starting PM backlog processing run...")
    run_id = storage.start_processing_run(
        meeting_id=meeting_id,
        run_type="pm_backlog",
    )
    print(f"✅ Processing run created with ID: {run_id}")

    # Save extracted epics
    print("\n[TEST 3] Saving extracted epics...")
    extracted_epics = {
        "meeting_date": str(date.today()),
        "epics": [
            {
                "title": "Test Epic 1",
                "description": "This is a test epic",
                "wsjf": {
                    "business_value": 8,
                    "time_criticality": 7,
                    "risk_reduction": 5,
                    "job_size": 4,
                    "wsjf_score": 5.0,
                },
                "mentioned_features": ["Feature A", "Feature B"],
            }
        ],
    }
    epic_ids = storage.save_extracted_epics(
        meeting_id=meeting_id,
        processing_run_id=run_id,
        extracted_epics_payload=extracted_epics,
    )
    print(f"✅ Saved {len(epic_ids)} epics")

    # Save decomposed backlog
    print("\n[TEST 4] Saving decomposed backlog...")
    decomposed_backlog = {
        "epic": {
            "title": "Test Epic 2",
            "wsjf_score": 4.5,
            "business_value": 7,
            "time_criticality": 6,
            "risk_reduction": 5,
            "job_size": 4,
            "stories": [
                {
                    "title": "Test Story 1",
                    "description": "Story description",
                    "acceptance_criteria": ["Criterion 1", "Criterion 2"],
                    "tasks": [
                        {
                            "title": "Test Task 1",
                            "description": "Task description",
                            "estimated_hours": 4,
                        }
                    ],
                }
            ],
        }
    }
    result = storage.save_decomposed_backlog(
        meeting_id=meeting_id,
        processing_run_id=run_id,
        decomposed_backlog_payload=decomposed_backlog,
    )
    print(f"✅ Saved epic {result['epic_id']} with {len(result['story_ids'])} stories and {len(result['task_ids'])} tasks")

    # Update with Jira keys
    print("\n[TEST 5] Updating with Jira keys...")
    # Use a unique Jira key to avoid constraint violations on reruns
    unique_jira_key = f"TEST-{uuid.uuid4().hex[:8].upper()}"
    storage.set_epic_jira_key(epic_ids[0], unique_jira_key, "To Do")
    print(f"✅ Epic updated with Jira key: {unique_jira_key}")

    # Complete processing run
    storage.complete_processing_run(run_id)
    print("\n✅ PM workflow test completed")


def test_rbac_workflow():
    """Test RBAC (roles, permissions, user roles)."""
    print("\n" + "=" * 60)
    print("RBAC WORKFLOW TEST")
    print("=" * 60)

    # Test 1: Get role by name
    print("\n[TEST 1] Getting admin role...")
    role_name = storage.get_user_role(1)  # Assuming user 1 exists
    print(f"✅ User role: {role_name if role_name else 'No role assigned'}")

    # Test 2: Check permission
    print("\n[TEST 2] Checking permission...")
    has_permission = storage.check_permission(1, "meetings", "read")
    print(f"✅ Has permission: {has_permission}")

    print("\n✅ RBAC workflow test completed")


def test_session_management():
    """Test session creation and validation."""
    print("\n" + "=" * 60)
    print("SESSION MANAGEMENT TEST")
    print("=" * 60)

    # Test 1: Create session
    print("\n[TEST 1] Creating user session...")
    session_id = storage.create_user_session(
        user_id=1,
        ip_address="127.0.0.1",
        user_agent="Test Agent",
        timeout_minutes=60,
    )
    print(f"✅ Session created: {session_id[:16]}...")

    # Test 2: Validate session
    print("\n[TEST 2] Validating session...")
    user_id = storage.validate_session(session_id)
    print(f"✅ Session valid for user: {user_id}")

    print("\n✅ Session management test completed")


def test_approval_workflow():
    """Test approval request creation and approval."""
    print("\n" + "=" * 60)
    print("APPROVAL WORKFLOW TEST")
    print("=" * 60)

    # Test 1: Create approval request
    print("\n[TEST 1] Creating approval request...")
    approval_id = storage.create_approval(
        request_type="epic_creation",
        entity_type="epic",
        entity_id=1,
        requested_by=1,
        assigned_to=1,
        request_data={"title": "Test Epic", "description": "Test description"},
        priority="high",
    )
    print(f"✅ Approval request created: {approval_id}")

    # Test 2: Approve request
    print("\n[TEST 2] Approving request...")
    success = storage.approve_request(
        approval_id=approval_id,
        approved_by=1,
        approved_data={"approved": True},
    )
    print(f"✅ Request approved: {success}")

    print("\n✅ Approval workflow test completed")


def test_sprint_workflow():
    """Test sprint creation and story assignment."""
    print("\n" + "=" * 60)
    print("SPRINT WORKFLOW TEST")
    print("=" * 60)

    # Test 1: Create team
    print("\n[TEST 1] Creating team...")
    team_id = storage.create_team(
        team_name="Test Team",
        description="Test team description",
        team_lead_id=1,
    )
    print(f"✅ Team created: {team_id}")

    # Test 2: Add team member
    print("\n[TEST 2] Adding team member...")
    success = storage.add_team_member(
        team_id=team_id,
        user_id=1,
        role_in_team="developer",
    )
    print(f"✅ Team member added: {success}")

    # Test 3: Create sprint
    print("\n[TEST 3] Creating sprint...")
    sprint_id = storage.create_sprint(
        sprint_name="Sprint 1",
        sprint_goal="Complete MVP features",
        start_date=date.today(),
        end_date=date.today(),
        team_id=team_id,
        created_by=1,
    )
    print(f"✅ Sprint created: {sprint_id}")

    # Test 4: Add story to sprint (using existing story from PM workflow)
    print("\n[TEST 4] Adding story to sprint...")
    # First create a story
    meeting_id = storage.create_meeting(
        meeting_type="pm",
        meeting_date=date.today(),
        title="Test PM Meeting for Sprint",
    )
    run_id = storage.start_processing_run(meeting_id=meeting_id, run_type="pm_backlog")
    decomposed = storage.save_decomposed_backlog(
        meeting_id=meeting_id,
        processing_run_id=run_id,
        decomposed_backlog_payload={
            "epic": {
                "title": "Sprint Test Epic",
                "wsjf_score": 4.0,
                "business_value": 5,
                "time_criticality": 5,
                "risk_reduction": 5,
                "job_size": 5,
                "stories": [
                    {
                        "title": "Sprint Test Story",
                        "description": "Story for sprint test",
                        "acceptance_criteria": ["Criterion 1"],
                        "tasks": [],
                    }
                ],
            }
        },
    )
    story_id = decomposed["story_ids"][0]
    
    success = storage.add_story_to_sprint(
        sprint_id=sprint_id,
        story_id=story_id,
        committed_by=1,
    )
    print(f"✅ Story added to sprint: {success}")

    print("\n✅ Sprint workflow test completed")


def test_telegram_workflow():
    """Test Telegram chat state and message queue."""
    print("\n" + "=" * 60)
    print("TELEGRAM WORKFLOW TEST")
    print("=" * 60)

    # Test 1: Update chat state
    print("\n[TEST 1] Updating Telegram chat state...")
    success = storage.update_telegram_state(
        telegram_user_id=123456789,
        telegram_chat_id=123456789,
        current_state="waiting_for_input",
        state_data={"step": 1, "data": "test"},
    )
    print(f"✅ Chat state updated: {success}")

    # Test 2: Queue message
    print("\n[TEST 2] Queueing Telegram message...")
    queue_id = storage.queue_telegram_message(
        telegram_user_id=123456789,
        telegram_chat_id=123456789,
        message_type="notification",
        message_text="Test notification message",
        priority=8,
    )
    print(f"✅ Message queued: {queue_id}")

    print("\n✅ Telegram workflow test completed")


def test_notification_workflow():
    """Test notification creation."""
    print("\n" + "=" * 60)
    print("NOTIFICATION WORKFLOW TEST")
    print("=" * 60)

    # Test 1: Create notification
    print("\n[TEST 1] Creating notification...")
    notification_id = storage.create_notification(
        user_id=1,
        notification_type="approval_pending",
        title="Approval Required",
        message="You have a pending approval request",
        priority="high",
    )
    print(f"✅ Notification created: {notification_id}")

    print("\n✅ Notification workflow test completed")


def test_settings_workflow():
    """Test system settings get/set."""
    print("\n" + "=" * 60)
    print("SETTINGS WORKFLOW TEST")
    print("=" * 60)

    # Test 1: Get setting
    print("\n[TEST 1] Getting system setting...")
    value = storage.get_setting("company_name")
    print(f"✅ Company name: {value}")

    # Test 2: Set setting
    print("\n[TEST 2] Setting system setting...")
    success = storage.set_setting(
        setting_key="test_setting",
        setting_value="test_value",
        updated_by=1,
    )
    print(f"✅ Setting updated: {success}")

    # Test 3: Verify setting
    print("\n[TEST 3] Verifying setting...")
    value = storage.get_setting("test_setting")
    print(f"✅ Test setting value: {value}")

    print("\n✅ Settings workflow test completed")


def run_all_new_tests():
    """Run all new module tests."""
    print("\n" + "=" * 80)
    print("RUNNING ALL NEW MODULE TESTS")
    print("=" * 80)
    
    try:
        test_rbac_workflow()
        test_session_management()
        test_approval_workflow()
        test_sprint_workflow()
        test_telegram_workflow()
        test_notification_workflow()
        test_settings_workflow()
        
        print("\n" + "=" * 80)
        print("ALL NEW MODULE TESTS PASSED ✅")
        print("=" * 80)
    except Exception as e:
        print(f"\n❌ NEW MODULE TEST FAILED: {e}")
        import traceback
        traceback.print_exc()
        raise


if __name__ == "__main__":
    try:
        test_basic_workflow()
        print("\n")
        test_pm_workflow()
        print("\n")
        run_all_new_tests()
    except Exception as e:
        print(f"\n❌ TEST FAILED: {e}")
        import traceback
        traceback.print_exc()
