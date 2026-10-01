"""The structured, intermediate specification used by the Code Agent.

The parsers read Markdown and PlantUML, then create an ``ArchitectureSpec``.
The generator only reads this structure.
Keeping this contract in one module prevents the parser and generator from
depending directly on one another.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


class SpecificationValidationError(ValueError):
    """Raised when data does not satisfy the ArchitectureSpec contract."""


def _require_text(value: object, field_name: str) -> str:
    """Return a non-empty string or raise a helpful validation error."""
    if not isinstance(value, str) or not value.strip():
        raise SpecificationValidationError(f"{field_name} 必须是非空文本。")
    return value


def _require_unique_text_list(value: object, field_name: str) -> list[str]:
    """Validate a list of unique, non-empty strings."""
    if not isinstance(value, list):
        raise SpecificationValidationError(f"{field_name} 必须是文本列表。")

    for item in value:
        _require_text(item, f"{field_name} 中的元素")

    if len(value) != len(set(value)):
        raise SpecificationValidationError(f"{field_name} 不能包含重复项。")
    return value


@dataclass
class ApiEndpoint:
    """One externally visible HTTP API endpoint."""

    method: str
    path: str
    summary: str

    def __post_init__(self) -> None:
        self.method = _require_text(self.method, "API method").upper()
        self.path = _require_text(self.path, "API path")
        self.summary = _require_text(self.summary, "API summary")
        if not self.path.startswith("/"):
            raise SpecificationValidationError("API path 必须以 '/' 开头。")

    def to_dict(self) -> dict[str, str]:
        """Convert this endpoint to JSON-compatible data."""
        return {"method": self.method, "path": self.path, "summary": self.summary}

    @classmethod
    def from_dict(cls, data: object) -> "ApiEndpoint":
        """Create an endpoint from JSON-compatible data."""
        if not isinstance(data, dict):
            raise SpecificationValidationError("每个 API 必须是对象。")
        try:
            return cls(
                method=data["method"],
                path=data["path"],
                summary=data["summary"],
            )
        except KeyError as error:
            raise SpecificationValidationError(
                f"API 缺少字段：{error.args[0]}。"
            ) from error


@dataclass
class ArchitectureSpec:
    """The single source of truth between document parsing and generation."""

    project_name: str
    architecture_style: str
    technology_stack: dict[str, str] = field(default_factory=dict)
    actors: list[str] = field(default_factory=list)
    components: list[str] = field(default_factory=list)
    entities: list[str] = field(default_factory=list)
    use_cases: list[str] = field(default_factory=list)
    api_endpoints: list[ApiEndpoint] = field(default_factory=list)
    data_entities: list[str] = field(default_factory=list)
    deployment_notes: list[str] = field(default_factory=list)
    relationships: list[str] = field(default_factory=list)
    interactions: list[str] = field(default_factory=list)
    states: list[str] = field(default_factory=list)
    requirements: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.project_name = _require_text(self.project_name, "project_name")
        self.architecture_style = _require_text(
            self.architecture_style, "architecture_style"
        )

        if not isinstance(self.technology_stack, dict):
            raise SpecificationValidationError("technology_stack 必须是键值对象。")
        for name, version in self.technology_stack.items():
            _require_text(name, "technology_stack 的键")
            _require_text(version, f"technology_stack[{name}]")

        self.actors = _require_unique_text_list(self.actors, "actors")
        self.components = _require_unique_text_list(self.components, "components")
        self.entities = _require_unique_text_list(self.entities, "entities")
        self.use_cases = _require_unique_text_list(self.use_cases, "use_cases")
        self.data_entities = _require_unique_text_list(
            self.data_entities, "data_entities"
        )
        self.deployment_notes = _require_unique_text_list(
            self.deployment_notes, "deployment_notes"
        )
        self.relationships = _require_unique_text_list(
            self.relationships, "relationships"
        )
        self.interactions = _require_unique_text_list(
            self.interactions, "interactions"
        )
        self.states = _require_unique_text_list(self.states, "states")
        self.requirements = _require_unique_text_list(
            self.requirements, "requirements"
        )

        if not isinstance(self.api_endpoints, list):
            raise SpecificationValidationError("api_endpoints 必须是 API 列表。")
        if not all(isinstance(endpoint, ApiEndpoint) for endpoint in self.api_endpoints):
            raise SpecificationValidationError(
                "api_endpoints 中的每个元素都必须是 ApiEndpoint。"
            )

    def to_dict(self) -> dict[str, Any]:
        """Convert the specification to JSON-compatible built-in types."""
        return {
            "project_name": self.project_name,
            "architecture_style": self.architecture_style,
            "technology_stack": dict(self.technology_stack),
            "actors": list(self.actors),
            "components": list(self.components),
            "entities": list(self.entities),
            "use_cases": list(self.use_cases),
            "api_endpoints": [endpoint.to_dict() for endpoint in self.api_endpoints],
            "data_entities": list(self.data_entities),
            "deployment_notes": list(self.deployment_notes),
            "relationships": list(self.relationships),
            "interactions": list(self.interactions),
            "states": list(self.states),
            "requirements": list(self.requirements),
        }

    def to_json(self) -> str:
        """Return readable UTF-8 JSON text without escaping Chinese text."""
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=2) + "\n"

    def write_json(self, destination: Path) -> None:
        """Write this specification to the requested JSON file."""
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(self.to_json(), encoding="utf-8")

    @classmethod
    def from_dict(cls, data: object) -> "ArchitectureSpec":
        """Recreate a specification from JSON-compatible data."""
        if not isinstance(data, dict):
            raise SpecificationValidationError("架构规格必须是 JSON 对象。")

        try:
            raw_endpoints = data["api_endpoints"]
            if not isinstance(raw_endpoints, list):
                raise SpecificationValidationError("api_endpoints 必须是 API 列表。")

            return cls(
                project_name=data["project_name"],
                architecture_style=data["architecture_style"],
                technology_stack=data["technology_stack"],
                actors=data["actors"],
                components=data["components"],
                entities=data["entities"],
                use_cases=data["use_cases"],
                api_endpoints=[ApiEndpoint.from_dict(item) for item in raw_endpoints],
                data_entities=data.get("data_entities", []),
                deployment_notes=data.get("deployment_notes", []),
                relationships=data.get("relationships", []),
                interactions=data.get("interactions", []),
                states=data.get("states", []),
                requirements=data.get("requirements", []),
            )
        except KeyError as error:
            raise SpecificationValidationError(
                f"架构规格缺少字段：{error.args[0]}。"
            ) from error


def create_example_specification() -> ArchitectureSpec:
    """Return the hand-designed target JSON for the supplied task documents.

    This function deliberately does not parse any file. It exists so that we
    can inspect and test the JSON contract before writing parsers in later
    steps.
    """
    return ArchitectureSpec(
        project_name="space-fractions",
        architecture_style="microservices",
        technology_stack={
            "runtime": "Node.js 18",
            "web_framework": "Express.js 4",
            "database": "PostgreSQL 14",
            "cache": "Redis 6",
        },
        actors=["EndUser", "Admin"],
        components=["GameComponent", "QuestionComponent", "UserComponent"],
        entities=["Game", "Question", "User", "Admin"],
        use_cases=["PlayGame", "ViewScore", "UpdateQuestions", "ViewHelp"],
        api_endpoints=[
            ApiEndpoint(method="GET", path="/play", summary="Start the game")
        ],
        data_entities=["games"],
        deployment_notes=["Kubernetes deployment", "3 replicas"],
        relationships=["Game --* Question", "User --* Game", "Admin --* Question"],
        interactions=["User -> Game: play()", "Game -> Question: getPrompt()"],
        states=["Playing", "Paused", "GameOver"],
        requirements=["FR-1: Play game", "NFR-1: Performance"],
    )
