"""
Functional tests for the Jira Routing System.

Covers:
  1. RoutingDecision dataclass fields
  2. JiraRoutingResolver  — keyword matching, confidence, triage fallback
  3. HybridRoutingService — keyword path, triage path, confidence thresholds
  4. routing_service      — approval data builders, persist helpers (mocked DB)
  5. Telegram formatters  — format_project_creation_approval, format_routing_card
  6. JiraCreationResult   — routing_decisions field
  7. JiraManager          — project field format (monkey-patched, no live Jira)
  8. Migration 003        — importable and has upgrade/downgrade

Run from project root:
    python -m pytest backend/tests/test_routing_system.py -v
"""

import json
import os
import sys
import types
from dataclasses import asdict
from datetime import datetime, timezone
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

# ── Make sure project root is on PYTHONPATH ───────────────────────────────────
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

# ── Fake minimal jira_routing.json config ─────────────────────────────────────
# The Jira tests in this module monkey-patch JiraManager internals and do not
# need the third-party jira package or network access.
if "jira" not in sys.modules:
    fake_jira_module = types.ModuleType("jira")
    fake_jira_module.JIRA = MagicMock()
    sys.modules["jira"] = fake_jira_module

if "jira.exceptions" not in sys.modules:
    fake_jira_exceptions = types.ModuleType("jira.exceptions")
    fake_jira_exceptions.JIRAError = Exception
    sys.modules["jira.exceptions"] = fake_jira_exceptions

ROUTING_CONFIG = {
    "default_project_key": "SP",
    "default_component": "General",
    "triage_project_key": "TRIAGE",
    "triage_project_name": "ScrumPilot Triage",
    "triage_component": "Triage",
    "projects": [
        {"key": "SP",     "name": "ScrumPilot Core", "keywords": ["scrum", "sprint", "backlog", "core", "platform"]},
        {"key": "MOBILE", "name": "Mobile App",       "keywords": ["mobile", "android", "ios", "app", "react native"]},
    ],
    "teams": [
        {"name": "backend",  "component": "Backend",  "keywords": ["backend", "api", "database", "server", "service", "migration"]},
        {"name": "frontend", "component": "Frontend",  "keywords": ["frontend", "ui", "ux", "react", "css", "page", "component"]},
        {"name": "devops",   "component": "DevOps",    "keywords": ["devops", "infra", "kubernetes", "docker", "deployment", "ci/cd"]},
    ],
}


# ═══════════════════════════════════════════════════════════════════════════════
# 1. RoutingDecision — dataclass fields
# ═══════════════════════════════════════════════════════════════════════════════

class TestRoutingDecision:
    def test_default_fields(self):
        from backend.tools.jira_routing import RoutingDecision
        d = RoutingDecision(
            project_key="SP",
            project_name="ScrumPilot Core",
            component="Backend",
            matched_project=True,
            matched_team=True,
        )
        assert d.confidence == 1.0
        assert d.team_name is None
        assert d.decision_reason == "keyword_match"  # dataclass default
        assert d.is_new_project_candidate is False
        assert d.is_triage is False
        assert d.labels == []

    def test_custom_fields(self):
        from backend.tools.jira_routing import RoutingDecision
        d = RoutingDecision(
            project_key="MOBILE",
            project_name="Mobile App",
            component="Frontend",
            matched_project=True,
            matched_team=True,
            team_name="frontend",
            confidence=0.85,
            decision_reason="keyword_match",
            labels=["mobile"],
        )
        assert d.confidence == 0.85
        assert d.team_name == "frontend"
        assert d.labels == ["mobile"]


# ═══════════════════════════════════════════════════════════════════════════════
# 2. JiraRoutingResolver — keyword matching, confidence, triage
# ═══════════════════════════════════════════════════════════════════════════════

class TestJiraRoutingResolver:
    @pytest.fixture
    def resolver(self):
        from backend.tools.jira_routing import JiraRoutingResolver, JiraRoutingConfig
        cfg = JiraRoutingConfig.from_dict(ROUTING_CONFIG)
        return JiraRoutingResolver(cfg)

    def test_matches_sp_project_by_keyword(self, resolver):
        d = resolver.resolve("Sprint backlog grooming session", "")
        assert d.project_key == "SP"
        assert d.matched_project is True

    def test_matches_mobile_project_by_keyword(self, resolver):
        d = resolver.resolve("Mobile Android login screen", "")
        assert d.project_key == "MOBILE"

    def test_matches_backend_team(self, resolver):
        # Must include SP project keywords ("sprint"/"platform") AND backend keywords
        d = resolver.resolve("Implement backend API service for the sprint platform core", "")
        assert d.team_name == "backend"
        assert d.component == "Backend"

    def test_matches_frontend_team(self, resolver):
        # Must include SP project keywords AND frontend keywords
        d = resolver.resolve("Build React UI frontend component for the sprint platform", "")
        assert d.team_name == "frontend"

    def test_matches_devops_team(self, resolver):
        # Must include SP project keywords AND devops keywords
        d = resolver.resolve("Deploy Kubernetes docker deployment for sprint platform core", "")
        assert d.team_name == "devops"

    def test_no_keyword_falls_to_triage(self, resolver):
        d = resolver.resolve("Completely unrelated marketing campaign budget", "")
        assert d.project_key == "TRIAGE"
        assert d.is_triage is True
        assert d.matched_project is False

    def test_confidence_high_on_keyword_match(self, resolver):
        # SP has 5 keywords; need >=4 hits for >=0.75 confidence
        # Text hits: scrum, sprint, backlog, core, platform (5/5 = 1.0)
        from backend.tools.jira_routing import KEYWORD_HIGH_CONFIDENCE
        d = resolver.resolve("scrum sprint backlog core platform review", "")
        assert d.confidence >= KEYWORD_HIGH_CONFIDENCE

    def test_confidence_zero_on_no_match(self, resolver):
        d = resolver.resolve("quarterly sales forecast report", "")
        assert d.confidence == 0.0

    def test_case_insensitive_matching(self, resolver):
        d = resolver.resolve("MOBILE Android APP features", "")
        assert d.project_key == "MOBILE"

    def test_description_also_matched(self, resolver):
        # Description must also contain SP project keywords for project to match
        d = resolver.resolve(
            "New feature",
            "This uses the scrum sprint platform backend api service layer",
        )
        assert d.team_name == "backend"


# ═══════════════════════════════════════════════════════════════════════════════
# 3. HybridRoutingService — keyword path, triage, confidence thresholds
# ═══════════════════════════════════════════════════════════════════════════════

class TestHybridRoutingService:
    @pytest.fixture
    def hybrid(self):
        from backend.tools.jira_routing import (
            JiraRoutingResolver, JiraRoutingConfig, HybridRoutingService,
        )
        cfg = JiraRoutingConfig.from_dict(ROUTING_CONFIG)
        resolver = JiraRoutingResolver(cfg)
        return HybridRoutingService(resolver)

    def test_high_confidence_returns_immediately(self, hybrid):
        d = hybrid.resolve("sprint backlog planning", "core platform improvement")
        assert d.project_key == "SP"
        assert d.decision_reason == "keyword_match"

    def test_triage_on_no_keywords(self, hybrid):
        d = hybrid.resolve("random unrelated stuff", "")
        assert d.is_triage is True

    def test_medium_confidence_routes_to_project_not_triage(self, hybrid):
        """Medium-confidence items are routed to the matched project (not triage).
        is_new_project_candidate is only set on the triage (low confidence) path."""
        from backend.tools.jira_routing import (
            JiraRoutingResolver, JiraRoutingConfig, HybridRoutingService,
            KEYWORD_MEDIUM_CONFIDENCE, KEYWORD_HIGH_CONFIDENCE, RoutingDecision,
        )
        mock_resolver = MagicMock()
        mid_conf = (KEYWORD_MEDIUM_CONFIDENCE + KEYWORD_HIGH_CONFIDENCE) / 2
        mock_resolver.resolve.return_value = RoutingDecision(
            project_key="SP",
            project_name="ScrumPilot Core",
            component=None,
            matched_project=True,
            matched_team=False,
            confidence=mid_conf,
            decision_reason="keyword_match",
        )
        svc = HybridRoutingService(mock_resolver)
        d = svc.resolve("some text", "")
        # Medium confidence → returned as-is (not triage, not new_project_candidate)
        assert d.project_key == "SP"
        assert d.is_triage is False
        assert d.is_new_project_candidate is False

    def test_llm_fallback_invoked_on_low_confidence(self, hybrid):
        """HybridRoutingService calls classifier when confidence < medium threshold."""
        from backend.tools.jira_routing import (
            HybridRoutingService, JiraRoutingResolver, JiraRoutingConfig, RoutingDecision,
        )
        cfg = JiraRoutingConfig.from_dict(ROUTING_CONFIG)
        resolver = JiraRoutingResolver(cfg)

        mock_classifier = MagicMock()
        mock_decision = RoutingDecision(
            project_key="SP",
            project_name="ScrumPilot Core",
            component="Backend",
            matched_project=True,
            matched_team=True,
            team_name="backend",
            confidence=0.80,
            decision_reason="llm",
        )
        mock_classifier.classify_single.return_value = mock_decision

        svc = HybridRoutingService(resolver, classifier=mock_classifier)
        d = svc.resolve("quarterly marketing budget planning", "")
        mock_classifier.classify_single.assert_called_once()
        assert d.decision_reason == "llm"


# ═══════════════════════════════════════════════════════════════════════════════
# 4. routing_service — approval data builders + persist helpers
# ═══════════════════════════════════════════════════════════════════════════════

class TestRoutingService:
    @pytest.fixture
    def decision(self):
        from backend.tools.jira_routing import RoutingDecision
        return RoutingDecision(
            project_key="NEWPROJ",
            project_name="New Project",
            component=None,
            matched_project=False,
            matched_team=False,
            team_name=None,
            confidence=0.20,
            decision_reason="triage_low_confidence",
            is_new_project_candidate=True,
        )

    def test_build_project_creation_approval_data(self, decision):
        from backend.services.routing_service import build_project_creation_approval_data
        items = [{"summary": "Feature A"}, {"summary": "Feature B"}]
        data = build_project_creation_approval_data(decision, items)
        assert data["suggested_key"] == "NEWPROJ"
        assert data["items_count"] == 2
        assert "Feature A" in data["sample_summaries"]
        assert 0.0 <= data["confidence"] <= 1.0

    def test_build_routing_card_data_confidence_counts(self):
        from backend.tools.jira_routing import RoutingDecision
        from backend.services.routing_service import build_routing_card_data

        decisions = [
            RoutingDecision("SP", "ScrumPilot", None, True, True, confidence=0.9, decision_reason="keyword_match"),
            RoutingDecision("SP", "ScrumPilot", None, True, True, confidence=0.55, decision_reason="keyword_match"),
            RoutingDecision("TRIAGE", "Triage", None, False, False, confidence=0.1, decision_reason="triage_fallback", is_triage=True),
        ]
        items = [{"summary": f"Item {i}"} for i in range(3)]
        data = build_routing_card_data(decisions, items)
        assert data["high_confidence_count"] == 1
        assert data["medium_confidence_count"] == 1
        assert data["low_confidence_count"] == 1
        assert data["total"] == 3

    def test_persist_routing_on_epic_sets_fields(self):
        from backend.tools.jira_routing import RoutingDecision
        from backend.services.routing_service import persist_routing_on_epic

        epic = MagicMock()
        d = RoutingDecision(
            project_key="SP", project_name="Core", component="Backend",
            matched_project=True, matched_team=True, team_name="backend",
            confidence=0.90, decision_reason="keyword_match",
        )
        persist_routing_on_epic(epic, d)
        assert epic.jira_project_key == "SP"
        assert epic.team_name == "backend"
        assert epic.jira_component is None  # Components removed: items live directly under project
        assert epic.routing_confidence == 0.9
        assert epic.routing_source == "keyword_match"

    def test_persist_routing_on_story_sets_fields(self):
        from backend.tools.jira_routing import RoutingDecision
        from backend.services.routing_service import persist_routing_on_story

        story = MagicMock()
        d = RoutingDecision("MOBILE", "Mobile", "Frontend", True, True,
                            team_name="frontend", confidence=0.75, decision_reason="llm")
        persist_routing_on_story(story, d)
        assert story.jira_project_key == "MOBILE"
        assert story.routing_source == "llm"

    def test_persist_routing_truncates_source_to_20_chars(self):
        from backend.tools.jira_routing import RoutingDecision
        from backend.services.routing_service import persist_routing_on_task

        task = MagicMock()
        d = RoutingDecision("SP", "Core", None, True, False,
                            confidence=0.5, decision_reason="this_is_a_very_long_reason_string")
        persist_routing_on_task(task, d)
        assert len(task.routing_source) <= 20


# ═══════════════════════════════════════════════════════════════════════════════
# 5. Telegram formatters
# ═══════════════════════════════════════════════════════════════════════════════

def _mock_approval(request_type: str, request_data: dict):
    """Return a mock ApprovalRequest with required attributes."""
    m = MagicMock()
    m.approval_id = 42
    m.request_type = request_type
    m.entity_type = "jira_project"
    m.priority = "high"
    m.status = "pending"
    m.created_at = datetime(2026, 5, 16, 12, 0, 0, tzinfo=timezone.utc)
    m.request_data = request_data
    return m


class TestTelegramFormatters:
    def test_format_project_creation_approval_contains_key(self):
        from backend.telegram.handlers.approval_handler import format_project_creation_approval
        data = {
            "suggested_key": "NEWPROJ",
            "suggested_name": "New Project",
            "confidence": 0.20,
            "items_count": 5,
            "sample_summaries": ["Feature X", "Feature Y", "Feature Z"],
        }
        approval = _mock_approval("project_creation", data)
        msg = format_project_creation_approval(approval, data)
        assert "NEWPROJ" in msg
        assert "New Project" in msg
        assert "Feature X" in msg
        assert "20%" in msg
        assert "5" in msg

    def test_format_project_creation_shows_truncated_samples(self):
        from backend.telegram.handlers.approval_handler import format_project_creation_approval
        data = {
            "suggested_key": "PROJ",
            "suggested_name": "Proj",
            "confidence": 0.5,
            "items_count": 10,
            "sample_summaries": [f"Item {i}" for i in range(10)],
        }
        approval = _mock_approval("project_creation", data)
        msg = format_project_creation_approval(approval, data)
        assert "and 7 more" in msg

    def test_format_routing_card_confidence_breakdown(self):
        from backend.telegram.handlers.approval_handler import format_routing_card
        data = {
            "project_key": "SP",
            "decision_reason": "keyword_match",
            "overall_confidence": 0.82,
            "total": 6,
            "high_confidence_count": 4,
            "medium_confidence_count": 1,
            "low_confidence_count": 1,
            "items": [
                {"summary": "Build API", "team_name": "backend", "confidence": 0.9},
                {"summary": "Design UI", "team_name": "frontend", "confidence": 0.6},
                {"summary": "Unknown task", "team_name": "unknown", "confidence": 0.15},
            ],
        }
        approval = _mock_approval("routing_classification", data)
        msg = format_routing_card(approval, data)
        assert "SP" in msg
        assert "keyword match" in msg
        assert "High" in msg
        assert "Low" in msg
        assert "backend" in msg
        assert "🔴" in msg   # low confidence flag

    def test_format_routing_card_empty_items(self):
        from backend.telegram.handlers.approval_handler import format_routing_card
        data = {
            "project_key": "SP",
            "decision_reason": "triage_fallback",
            "overall_confidence": 0.0,
            "total": 0,
            "high_confidence_count": 0,
            "medium_confidence_count": 0,
            "low_confidence_count": 0,
            "items": [],
        }
        approval = _mock_approval("routing_classification", data)
        msg = format_routing_card(approval, data)
        assert "SP" in msg
        assert "triage" in msg


# ═══════════════════════════════════════════════════════════════════════════════
# 6. JiraCreationResult — routing_decisions field
# ═══════════════════════════════════════════════════════════════════════════════

class TestJiraCreationResult:
    def test_routing_decisions_default_empty(self):
        from backend.agents.jira_creator import JiraCreationResult
        r = JiraCreationResult(creation_date="2026-05-16")
        assert isinstance(r.routing_decisions, dict)
        assert len(r.routing_decisions) == 0

    def test_routing_decisions_stores_data(self):
        from backend.agents.jira_creator import JiraCreationResult
        r = JiraCreationResult(creation_date="2026-05-16")
        r.routing_decisions["epic_001"] = {
            "project_key": "SP",
            "team_name": "backend",
            "component": "Backend",
            "confidence": 0.9,
            "source": "keyword_match",
        }
        assert r.routing_decisions["epic_001"]["project_key"] == "SP"


# ═══════════════════════════════════════════════════════════════════════════════
# 7. JiraManager — project field is a dict not a string
# ═══════════════════════════════════════════════════════════════════════════════

class TestJiraClientProjectField:
    def test_create_ticket_sends_project_as_dict(self):
        """Ensure the project field is formatted as {"key": ...} not a plain string."""
        from backend.tools.jira_client import JiraManager

        captured = {}

        def fake_create_issue(fields):
            captured["fields"] = fields
            mock_issue = MagicMock()
            mock_issue.key = "SP-999"
            return mock_issue

        with patch.dict(os.environ, {
            "JIRA_URL": "https://fake.atlassian.net",
            "JIRA_EMAIL": "test@test.com",
            "JIRA_API_TOKEN": "faketoken",
            "JIRA_PROJECT_KEY": "SP",
        }):
            mgr = JiraManager.__new__(JiraManager)
            mgr.project_key = "SP"
            mgr.jira_url = "https://fake.atlassian.net"
            mgr.client = MagicMock()
            mgr.client.create_issue.side_effect = fake_create_issue
            mgr.rate_limit_enabled = False  # bypass __init__
            mgr._api_call_timestamps = []

            mgr._create_ticket_internal(
                "Test summary", "Test description", "Story",
                None, None, None,  # assignee_email, parent_key, epic_link
            )

        project_field = captured["fields"].get("project")
        assert isinstance(project_field, dict), f"Expected dict, got {type(project_field)}: {project_field}"
        assert "key" in project_field
        assert project_field["key"] == "SP"

    def test_create_ticket_respects_project_key_override(self):
        """project_key parameter overrides the default self.project_key."""
        from backend.tools.jira_client import JiraManager

        captured = {}

        def fake_create_issue(fields):
            captured["fields"] = fields
            mock_issue = MagicMock()
            mock_issue.key = "MOBILE-10"
            return mock_issue

        mgr = JiraManager.__new__(JiraManager)
        mgr.project_key = "SP"
        mgr.jira_url = "https://fake.atlassian.net"
        mgr.client = MagicMock()
        mgr.client.create_issue.side_effect = fake_create_issue
        mgr.rate_limit_enabled = False  # bypass __init__
        mgr._api_call_timestamps = []

        mgr._create_ticket_internal(
            "Mobile feature", "Description", "Story",
            None, None, None,  # assignee_email, parent_key, epic_link
            project_key="MOBILE",
        )
        assert captured["fields"]["project"]["key"] == "MOBILE"

    def test_create_sprint_does_not_reuse_active_sprint_when_creating_future(self):
        """Sprint planning should create a backlog-ready future sprint, not reuse active one."""
        from backend.tools.jira_client import JiraManager

        mgr = JiraManager.__new__(JiraManager)
        mgr.project_key = "TEST3"
        mgr.url = "https://fake.atlassian.net"
        mgr.client = MagicMock()
        mgr._enforce_rate_limit = MagicMock()
        mgr.get_project_boards = MagicMock(return_value=[{"id": 110, "name": "TEST3 Scrum Board"}])

        active_sprint = MagicMock()
        active_sprint.id = 362
        active_sprint.name = "Sprint 24"
        active_sprint.state = "active"

        future_sprints_by_state = {
            "future": [],
            "active": [active_sprint],
        }
        mgr.client.sprints.side_effect = lambda board_id, state: future_sprints_by_state[state]

        created_sprint = MagicMock()
        created_sprint.id = 363
        created_sprint.name = "Sprint 24"
        created_sprint.state = "future"
        mgr.client.create_sprint.return_value = created_sprint

        result = mgr.create_sprint(
            name="Sprint 24",
            goal="Payment gateway",
            start_date="2026-05-20",
            end_date="2026-06-03",
            project_key="TEST3",
            auto_start=False,
        )

        assert result["success"] is True
        assert result["id"] == 363
        assert result["state"] == "future"
        mgr.client.create_sprint.assert_called_once()


# ═══════════════════════════════════════════════════════════════════════════════
# 8. Migration 003 — importable and has upgrade/downgrade
# ═══════════════════════════════════════════════════════════════════════════════

class TestSprintPlanningProjectRouting:
    def test_direct_sprint_creation_uses_context_project_key(self):
        """Direct sprint creation must use the selected project, not the .env default."""
        from backend.agents.sprint_planning_extractor import (
            SprintCommitment,
            SprintPlanningResult,
            TeamCapacity,
        )

        fake_jira_module = types.ModuleType("jira")
        fake_jira_module.JIRA = MagicMock()
        fake_jira_exceptions = types.ModuleType("jira.exceptions")
        fake_jira_exceptions.JIRAError = Exception
        with patch.dict(
            sys.modules,
            {"jira": fake_jira_module, "jira.exceptions": fake_jira_exceptions},
        ):
            from backend.pipelines.sprint_planning_pipeline import SprintPlanningPipeline

        sprint_plan = SprintPlanningResult(
            sprint_goal="Ship project-routed sprint planning",
            sprint_number=42,
            team_capacity=TeamCapacity(total_hours=80, team_size=4),
            commitment=SprintCommitment(story_ids=["MOBILE-10"]),
            developer_assignments=[],
        )

        pipeline = SprintPlanningPipeline.__new__(SprintPlanningPipeline)
        pipeline.require_telegram_approval = False
        pipeline.extractor = MagicMock()
        pipeline._extract_sprint_plan = MagicMock(return_value=sprint_plan)

        captured = {}

        def fake_create_sprint(plan, project_key=None):
            captured["project_key"] = project_key
            return {
                "sprint_id": 123,
                "sprint_name": "Sprint 42",
                "sprint_key": "SPRINT-123",
                "project_key": project_key,
                "board_id": 456,
                "stories_moved": 1,
                "tasks_assigned": 0,
                "developers_assigned": 0,
                "errors": [],
            }

        pipeline._create_sprint_in_jira = fake_create_sprint

        result = pipeline.run(
            transcript_path="dummy_transcript.txt",
            create_in_jira=True,
            dry_run=False,
            context={"project_key": " mobile "},
        )

        assert result.status == "completed"
        assert captured["project_key"] == "MOBILE"
        assert result.jira_result["project_key"] == "MOBILE"

    def test_extract_sprint_plan_loads_project_scoped_context(self):
        """Project selection should constrain the backlog context given to the extractor."""
        from backend.agents.sprint_planning_extractor import SprintPlanningResult
        from backend.pipelines.sprint_planning_pipeline import SprintPlanningPipeline

        pipeline = SprintPlanningPipeline.__new__(SprintPlanningPipeline)
        pipeline.extractor = MagicMock()
        pipeline.extractor.extract_from_file.return_value = MagicMock(spec=SprintPlanningResult)
        pipeline._load_backlog_context = MagicMock(
            return_value={
                "available_stories": [{"story_id": "TEST3-1", "title": "Payment"}],
                "available_tasks": [],
            }
        )

        pipeline._extract_sprint_plan(
            "dummy_transcript.txt",
            {"project_key": " test3 "},
        )

        pipeline._load_backlog_context.assert_called_once_with(project_key="TEST3")
        passed_context = pipeline.extractor.extract_from_file.call_args.args[1]
        assert passed_context["project_key"] == "TEST3"
        assert passed_context["available_stories"][0]["story_id"] == "TEST3-1"

    def test_resolve_issue_key_rejects_direct_key_from_other_project(self):
        """A selected project must not move literal issue keys from another project."""
        from backend.pipelines.sprint_planning_pipeline import SprintPlanningPipeline

        pipeline = SprintPlanningPipeline.__new__(SprintPlanningPipeline)
        pipeline.jira = MagicMock()

        assert pipeline._resolve_issue_key("TEST-2", project_key="TEST3") is None
        pipeline.jira.search_tickets.assert_not_called()


class TestMigration003:
    def test_importable(self):
        import importlib.util
        path = os.path.join(ROOT, "alembic", "versions", "003_project_team_registry.py")
        spec = importlib.util.spec_from_file_location("migration_003", path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        assert hasattr(module, "upgrade")
        assert hasattr(module, "downgrade")
        assert module.revision == "003"
        assert module.down_revision == "002"

    def test_revision_chain(self):
        import importlib.util
        path = os.path.join(ROOT, "alembic", "versions", "003_project_team_registry.py")
        spec = importlib.util.spec_from_file_location("migration_003", path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        assert module.down_revision == "002", "Migration 003 must chain from 002"


# ═══════════════════════════════════════════════════════════════════════════════
# 9. Confidence threshold env-var override
# ═══════════════════════════════════════════════════════════════════════════════

class TestConfidenceThresholds:
    def test_defaults_without_env(self):
        """Without env overrides the defaults are 0.75 / 0.40."""
        # Re-import after clearing env to check defaults
        import importlib
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("ROUTING_HIGH_CONFIDENCE", None)
            os.environ.pop("ROUTING_MEDIUM_CONFIDENCE", None)
            import backend.tools.jira_routing as routing_mod
            importlib.reload(routing_mod)
            assert routing_mod.KEYWORD_HIGH_CONFIDENCE == 0.75
            assert routing_mod.KEYWORD_MEDIUM_CONFIDENCE == 0.40

    def test_env_override_applied(self):
        import importlib
        with patch.dict(os.environ, {
            "ROUTING_HIGH_CONFIDENCE": "0.90",
            "ROUTING_MEDIUM_CONFIDENCE": "0.50",
        }):
            import backend.tools.jira_routing as routing_mod
            importlib.reload(routing_mod)
            assert routing_mod.KEYWORD_HIGH_CONFIDENCE == 0.90
            assert routing_mod.KEYWORD_MEDIUM_CONFIDENCE == 0.50
        # Restore
        import backend.tools.jira_routing as routing_mod
        importlib.reload(routing_mod)


# ═══════════════════════════════════════════════════════════════════════════════
# 10. Callback handler — editkey action dispatch exists
# ═══════════════════════════════════════════════════════════════════════════════

class TestCallbackHandlerEditkey:
    def test_handle_editkey_function_exists(self):
        from backend.telegram.handlers import callback_handler
        assert hasattr(callback_handler, "handle_editkey"), \
            "handle_editkey must be defined in callback_handler"

    def test_handle_editkey_is_coroutine(self):
        import asyncio
        from backend.telegram.handlers import callback_handler
        assert asyncio.iscoroutinefunction(callback_handler.handle_editkey)

    def test_routing_status_handler_is_coroutine(self):
        import asyncio
        from backend.telegram.handlers import sprint_handler
        assert asyncio.iscoroutinefunction(sprint_handler.handle_routing_status)
