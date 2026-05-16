"""Project and team routing registry

Revision ID: 003
Revises: 002
Create Date: 2026-05-16 12:00:00.000000

Changes:
- New table: jira_projects_registry  (project key + keywords + status)
- New table: jira_project_teams      (team taxonomy per project)
- Routing metadata columns on epics, stories, tasks, scrum_actions:
    jira_project_key, team_name, jira_component, routing_confidence, routing_source
- Seeds jira_projects_registry and jira_project_teams from
  JIRA_ROUTING_CONFIG_PATH (or backend/config/jira_routing.json) if present.

This migration is purely additive — no existing columns or tables are modified.
"""
import json
import os
from pathlib import Path
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "003"
down_revision: Union[str, None] = "002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# ── Helpers ───────────────────────────────────────────────────────────────────

def _routing_metadata_columns():
    """Return the 5 routing metadata columns shared across work-item tables."""
    return [
        sa.Column("jira_project_key", sa.String(20), nullable=True),
        sa.Column("team_name", sa.String(100), nullable=True),
        sa.Column("jira_component", sa.String(100), nullable=True),
        sa.Column("routing_confidence", sa.Numeric(4, 3), nullable=True),
        sa.Column("routing_source", sa.String(20), nullable=True),
    ]


def _load_routing_config():
    """Return parsed jira_routing.json if available, otherwise None."""
    config_path = os.getenv("JIRA_ROUTING_CONFIG_PATH", "backend/config/jira_routing.json")
    resolved = Path(config_path)
    if not resolved.is_absolute():
        resolved = Path.cwd() / resolved
    if not resolved.exists():
        return None
    try:
        with open(resolved, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except Exception:
        return None


# ── Upgrade ───────────────────────────────────────────────────────────────────

def upgrade() -> None:
    # ── 1. jira_projects_registry ─────────────────────────────────────────────
    op.create_table(
        "jira_projects_registry",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("project_key", sa.String(20), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column(
            "keywords",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default="[]",
        ),
        sa.Column("status", sa.String(30), nullable=False, server_default="active"),
        sa.Column("board_id", sa.String(50), nullable=True),
        sa.Column("owning_domain", sa.Text(), nullable=True),
        sa.Column("auto_created", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column(
            "metadata",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default="{}",
        ),
        sa.Column(
            "created_at",
            postgresql.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.UniqueConstraint("project_key", name="uq_jira_projects_registry_key"),
    )
    op.create_index("idx_jira_projects_status", "jira_projects_registry", ["status"])

    # ── 2. jira_project_teams ─────────────────────────────────────────────────
    op.create_table(
        "jira_project_teams",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column(
            "project_key",
            sa.String(20),
            sa.ForeignKey(
                "jira_projects_registry.project_key",
                ondelete="CASCADE",
                name="fk_jira_project_teams_project_key",
            ),
            nullable=False,
        ),
        sa.Column("team_name", sa.String(100), nullable=False),
        sa.Column("jira_component", sa.String(100), nullable=True),
        sa.Column(
            "label_set",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default="[]",
        ),
        sa.Column(
            "keywords",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default="[]",
        ),
        sa.Column("lead_jira_account_id", sa.Text(), nullable=True),
        sa.UniqueConstraint("project_key", "team_name", name="uq_jira_project_teams"),
    )
    op.create_index("idx_jira_project_teams_key", "jira_project_teams", ["project_key"])

    # ── 3. Routing metadata on work-item tables ───────────────────────────────
    for table in ("epics", "stories", "tasks", "scrum_actions"):
        op.add_column(table, sa.Column("jira_project_key", sa.String(20), nullable=True))
        op.add_column(table, sa.Column("team_name", sa.String(100), nullable=True))
        op.add_column(table, sa.Column("jira_component", sa.String(100), nullable=True))
        op.add_column(table, sa.Column("routing_confidence", sa.Numeric(4, 3), nullable=True))
        op.add_column(table, sa.Column("routing_source", sa.String(20), nullable=True))

    # ── 4. Seed from jira_routing.json if present ────────────────────────────
    config = _load_routing_config()
    if config:
        conn = op.get_bind()
        now = sa.func.now()

        for project in config.get("projects", []):
            key = str(project.get("key", "")).strip().upper()
            name = str(project.get("name", key)).strip() or key
            keywords = project.get("keywords", [])
            if not key:
                continue

            conn.execute(
                sa.text(
                    "INSERT INTO jira_projects_registry "
                    "(project_key, name, keywords, status, auto_created, metadata, created_at) "
                    "VALUES (:key, :name, CAST(:keywords AS jsonb), 'active', false, '{}'::jsonb, now()) "
                    "ON CONFLICT (project_key) DO NOTHING"
                ),
                {"key": key, "name": name, "keywords": json.dumps(keywords)},
            )

            # Per-project teams (if defined)
            for team in project.get("teams", []):
                team_name = str(team.get("name", "")).strip()
                component = str(team.get("component", "")).strip() or None
                team_keywords = team.get("keywords", [])
                if not team_name:
                    continue
                conn.execute(
                    sa.text(
                        "INSERT INTO jira_project_teams "
                        "(project_key, team_name, jira_component, label_set, keywords) "
                        "VALUES (:key, :team, :component, '[]'::jsonb, CAST(:keywords AS jsonb)) "
                        "ON CONFLICT (project_key, team_name) DO NOTHING"
                    ),
                    {
                        "key": key,
                        "team": team_name,
                        "component": component,
                        "keywords": json.dumps(team_keywords),
                    },
                )

        # Seed global teams under the default project key
        default_key = str(config.get("default_project_key", "")).strip().upper()
        if default_key:
            for team in config.get("teams", []):
                team_name = str(team.get("name", "")).strip()
                component = str(team.get("component", "")).strip() or None
                team_keywords = team.get("keywords", [])
                if not team_name:
                    continue
                conn.execute(
                    sa.text(
                        "INSERT INTO jira_project_teams "
                        "(project_key, team_name, jira_component, label_set, keywords) "
                        "VALUES (:key, :team, :component, '[]'::jsonb, CAST(:keywords AS jsonb)) "
                        "ON CONFLICT (project_key, team_name) DO NOTHING"
                    ),
                    {
                        "key": default_key,
                        "team": team_name,
                        "component": component,
                        "keywords": json.dumps(team_keywords),
                    },
                )


# ── Downgrade ─────────────────────────────────────────────────────────────────

def downgrade() -> None:
    for table in ("epics", "stories", "tasks", "scrum_actions"):
        op.drop_column(table, "routing_source")
        op.drop_column(table, "routing_confidence")
        op.drop_column(table, "jira_component")
        op.drop_column(table, "team_name")
        op.drop_column(table, "jira_project_key")

    op.drop_index("idx_jira_project_teams_key", table_name="jira_project_teams")
    op.drop_table("jira_project_teams")
    op.drop_index("idx_jira_projects_status", table_name="jira_projects_registry")
    op.drop_table("jira_projects_registry")
