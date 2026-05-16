import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict, List, Optional


@dataclass
class TeamRoutingRule:
    name: str
    component: str
    keywords: List[str] = field(default_factory=list)


@dataclass
class ProjectRoutingRule:
    key: str
    name: str
    keywords: List[str] = field(default_factory=list)
    teams: List[TeamRoutingRule] = field(default_factory=list)


@dataclass
class RoutingDecision:
    project_key: str
    project_name: str
    component: Optional[str]
    matched_project: bool
    matched_team: bool
    is_triage: bool = False
    team_name: Optional[str] = None
    labels: List[str] = field(default_factory=list)
    confidence: float = 1.0
    decision_reason: str = "keyword_match"
    is_new_project_candidate: bool = False
    suggested_project_name: Optional[str] = None


@dataclass
class JiraRoutingConfig:
    default_project_key: str
    default_component: Optional[str]
    triage_project_key: str
    triage_project_name: str
    triage_component: Optional[str]
    projects: List[ProjectRoutingRule] = field(default_factory=list)
    teams: List[TeamRoutingRule] = field(default_factory=list)

    @staticmethod
    def _normalize_keywords(raw_keywords: Any) -> List[str]:
        if not raw_keywords:
            return []
        if not isinstance(raw_keywords, list):
            raise ValueError("keywords must be a list of strings")
        normalized = []
        for keyword in raw_keywords:
            if not isinstance(keyword, str):
                raise ValueError("keywords must be a list of strings")
            cleaned = keyword.strip().lower()
            if cleaned:
                normalized.append(cleaned)
        return normalized

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "JiraRoutingConfig":
        if not isinstance(data, dict):
            raise ValueError("Routing config must be a JSON object")

        default_project_key = str(data.get("default_project_key", "")).strip().upper()
        if not default_project_key:
            raise ValueError("default_project_key is required in routing config")

        triage_project_key = str(
            data.get("triage_project_key", "TRIAGE")
        ).strip().upper()
        triage_project_name = str(
            data.get("triage_project_name", "ScrumPilot Triage")
        ).strip()
        if not triage_project_name:
            triage_project_name = "ScrumPilot Triage"

        default_component = data.get("default_component")
        if default_component is not None:
            default_component = str(default_component).strip() or None

        triage_component = data.get("triage_component")
        if triage_component is not None:
            triage_component = str(triage_component).strip() or None

        projects: List[ProjectRoutingRule] = []
        for raw_project in data.get("projects", []):
            if not isinstance(raw_project, dict):
                raise ValueError("Each project entry must be an object")

            key = str(raw_project.get("key", "")).strip().upper()
            if not key:
                raise ValueError("Each project must define a non-empty key")

            name = str(raw_project.get("name", key)).strip() or key
            keywords = cls._normalize_keywords(raw_project.get("keywords"))

            teams: List[TeamRoutingRule] = []
            for raw_team in raw_project.get("teams", []):
                if not isinstance(raw_team, dict):
                    raise ValueError("Each team entry must be an object")
                team_name = str(raw_team.get("name", "")).strip()
                component = str(raw_team.get("component", "")).strip()
                if not team_name or not component:
                    raise ValueError("Each team must define name and component")
                teams.append(
                    TeamRoutingRule(
                        name=team_name,
                        component=component,
                        keywords=cls._normalize_keywords(raw_team.get("keywords")),
                    )
                )

            projects.append(
                ProjectRoutingRule(
                    key=key,
                    name=name,
                    keywords=keywords,
                    teams=teams,
                )
            )

        global_teams: List[TeamRoutingRule] = []
        for raw_team in data.get("teams", []):
            if not isinstance(raw_team, dict):
                raise ValueError("Each global team entry must be an object")
            team_name = str(raw_team.get("name", "")).strip()
            component = str(raw_team.get("component", "")).strip()
            if not team_name or not component:
                raise ValueError("Each global team must define name and component")
            global_teams.append(
                TeamRoutingRule(
                    name=team_name,
                    component=component,
                    keywords=cls._normalize_keywords(raw_team.get("keywords")),
                )
            )

        return cls(
            default_project_key=default_project_key,
            default_component=default_component,
            triage_project_key=triage_project_key,
            triage_project_name=triage_project_name,
            triage_component=triage_component,
            projects=projects,
            teams=global_teams,
        )


class JiraRoutingResolver:
    def __init__(self, config: JiraRoutingConfig):
        self.config = config

    @staticmethod
    def _score_keywords(text: str, keywords: List[str]) -> int:
        if not keywords:
            return 0

        lowered = text.lower()
        score = 0
        for keyword in keywords:
            if keyword and keyword in lowered:
                score += 1
        return score

    def _find_project_by_key(self, key: str) -> Optional[ProjectRoutingRule]:
        wanted = key.upper()
        for project in self.config.projects:
            if project.key.upper() == wanted:
                return project
        return None

    def _select_project(self, text: str) -> Optional[ProjectRoutingRule]:
        best_project = None
        best_score = 0
        for project in self.config.projects:
            score = self._score_keywords(text, project.keywords)
            if score > best_score:
                best_score = score
                best_project = project
        return best_project

    def _select_team(
        self,
        text: str,
        project: Optional[ProjectRoutingRule] = None,
    ) -> Optional[TeamRoutingRule]:
        team_rules = project.teams if project and project.teams else self.config.teams
        best_team = None
        best_score = 0
        for team in team_rules:
            score = self._score_keywords(text, team.keywords)
            if score > best_score:
                best_score = score
                best_team = team
        return best_team

    def resolve(
        self,
        summary: str,
        description: str = "",
        force_project_key: Optional[str] = None,
    ) -> RoutingDecision:
        text = f"{summary}\n{description}".strip()

        if force_project_key:
            forced_project_key = force_project_key.strip().upper()
            project = self._find_project_by_key(forced_project_key)
            project_name = project.name if project else forced_project_key
            team = self._select_team(text, project)

            return RoutingDecision(
                project_key=forced_project_key,
                project_name=project_name,
                component=(team.component if team else self.config.default_component),
                matched_project=project is not None,
                matched_team=team is not None,
                is_triage=False,
                team_name=team.name if team else None,
                confidence=1.0,
                decision_reason="forced",
            )

        project = self._select_project(text)
        if not project:
            return RoutingDecision(
                project_key=self.config.triage_project_key,
                project_name=self.config.triage_project_name,
                component=self.config.triage_component,
                matched_project=False,
                matched_team=False,
                is_triage=True,
                confidence=0.0,
                decision_reason="triage_fallback",
            )

        # Score confidence: 3 keyword hits → full confidence, independent
        # of how many keywords the project has configured.  This avoids
        # penalising projects that happen to have large keyword lists.
        project_score = self._score_keywords(text, project.keywords)
        confidence = min(project_score / 3.0, 1.0)

        team = self._select_team(text, project)
        return RoutingDecision(
            project_key=project.key,
            project_name=project.name,
            component=(team.component if team else self.config.default_component),
            matched_project=True,
            matched_team=team is not None,
            is_triage=False,
            team_name=team.name if team else None,
            confidence=confidence,
            decision_reason="keyword_match",
        )


# ── Confidence thresholds ─────────────────────────────────────────────────────
# Override via ROUTING_HIGH_CONFIDENCE and ROUTING_MEDIUM_CONFIDENCE env vars.

KEYWORD_HIGH_CONFIDENCE: float = float(os.getenv("ROUTING_HIGH_CONFIDENCE", "0.75"))
KEYWORD_MEDIUM_CONFIDENCE: float = float(os.getenv("ROUTING_MEDIUM_CONFIDENCE", "0.40"))


class HybridRoutingService:
    """
    Hybrid routing service: keyword-first, LLM fallback.

    Strategy:
      - Run JiraRoutingResolver (fast, deterministic).
      - If confidence >= KEYWORD_HIGH_CONFIDENCE  → return immediately.
      - If confidence >= KEYWORD_MEDIUM_CONFIDENCE → return with is_new_project_candidate hint.
      - If confidence <  KEYWORD_MEDIUM_CONFIDENCE → call LLM classifier if available,
        otherwise triage.
    """

    def __init__(
        self,
        resolver: JiraRoutingResolver,
        classifier: Optional[Any] = None,
    ):
        self.resolver = resolver
        self.classifier = classifier

    def resolve(
        self,
        summary: str,
        description: str = "",
        transcript_snippet: str = "",
        known_projects: Optional[List[Any]] = None,
        known_teams: Optional[List[Any]] = None,
    ) -> RoutingDecision:
        decision = self.resolver.resolve(summary, description)

        if decision.confidence >= KEYWORD_HIGH_CONFIDENCE:
            return decision

        if self.classifier is not None:
            try:
                llm_decision = self.classifier.classify_single(
                    summary=summary,
                    description=description,
                    transcript_snippet=transcript_snippet,
                    known_projects=known_projects or [],
                    known_teams=known_teams or [],
                )
                if llm_decision is not None:
                    return llm_decision
            except Exception:
                pass

        if decision.confidence >= KEYWORD_MEDIUM_CONFIDENCE:
            return decision

        return RoutingDecision(
            project_key=self.resolver.config.triage_project_key,
            project_name=self.resolver.config.triage_project_name,
            component=self.resolver.config.triage_component,
            matched_project=False,
            matched_team=False,
            is_triage=True,
            confidence=decision.confidence,
            decision_reason="triage_low_confidence",
            is_new_project_candidate=True,
            suggested_project_name=None,
        )


def load_jira_routing_config(
    config_path: Optional[str] = None,
) -> Optional[JiraRoutingConfig]:
    resolved_path = config_path or os.getenv("JIRA_ROUTING_CONFIG_PATH")
    if not resolved_path:
        return None

    path = Path(resolved_path).expanduser()
    if not path.is_absolute():
        path = Path.cwd() / path
    if not path.exists():
        raise FileNotFoundError(f"Jira routing config not found: {path}")

    with open(path, "r", encoding="utf-8") as file:
        raw_data = json.load(file)

    return JiraRoutingConfig.from_dict(raw_data)
