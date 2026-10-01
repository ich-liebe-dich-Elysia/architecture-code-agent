"""Turn an ArchitectureSpec into an explicit, reviewable generation plan."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from agent.specification import ArchitectureSpec


class PlanValidationError(ValueError):
    """Raised when a generation plan is malformed."""


@dataclass
class PlannedFile:
    """One generated file and the architectural reason it exists."""

    path: str
    reason: str

    def __post_init__(self) -> None:
        if not self.path or Path(self.path).is_absolute() or ".." in Path(self.path).parts:
            raise PlanValidationError(f"Unsafe generated file path: {self.path!r}")
        if not self.reason:
            raise PlanValidationError("Every planned file needs a reason.")

    def to_dict(self) -> dict[str, str]:
        return {"path": self.path, "reason": self.reason}

    @classmethod
    def from_dict(cls, data: object) -> "PlannedFile":
        if not isinstance(data, dict):
            raise PlanValidationError("A planned file must be a JSON object.")
        return cls(path=data["path"], reason=data["reason"])


@dataclass
class GenerationPlan:
    """A deterministic list of files to produce for one target project."""

    project_name: str
    target_directory: str
    files: list[PlannedFile] = field(default_factory=list)

    def __post_init__(self) -> None:
        if not self.project_name:
            raise PlanValidationError("project_name cannot be empty.")
        if not self.target_directory or Path(self.target_directory).is_absolute():
            raise PlanValidationError("target_directory must be a relative directory.")
        if ".." in Path(self.target_directory).parts:
            raise PlanValidationError("target_directory cannot escape output/.")
        if not self.files:
            raise PlanValidationError("A generation plan must contain files.")

        paths = [planned_file.path for planned_file in self.files]
        if len(paths) != len(set(paths)):
            raise PlanValidationError("A generation plan cannot contain duplicate paths.")

    def to_dict(self) -> dict[str, Any]:
        return {
            "project_name": self.project_name,
            "target_directory": self.target_directory,
            "files": [planned_file.to_dict() for planned_file in self.files],
        }

    def write_json(self, destination: Path) -> None:
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(
            json.dumps(self.to_dict(), ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

    @classmethod
    def from_dict(cls, data: object) -> "GenerationPlan":
        if not isinstance(data, dict):
            raise PlanValidationError("The generation plan must be a JSON object.")
        try:
            return cls(
                project_name=data["project_name"],
                target_directory=data["target_directory"],
                files=[PlannedFile.from_dict(item) for item in data["files"]],
            )
        except KeyError as error:
            raise PlanValidationError(
                f"The generation plan is missing: {error.args[0]}."
            ) from error


def create_generation_plan(
    specification: ArchitectureSpec, target_directory: str | None = None
) -> GenerationPlan:
    """Create the fixed Express starter plan required by this assignment."""
    files = [
        PlannedFile("package.json", "Node.js runtime and Express dependencies."),
        PlannedFile("src/app.js", "Express application entry point and health endpoint."),
        PlannedFile("src/routes/game.js", "Implements the documented /play game API."),
        PlannedFile(
            "src/services/questionService.js",
            "Separates question retrieval and answer evaluation from HTTP routing.",
        ),
        PlannedFile(
            "src/data/questions.js",
            "Provides initial fraction questions owned by QuestionComponent.",
        ),
        PlannedFile("tests/app.test.js", "Node HTTP checks for /health and /play."),
        PlannedFile("README.md", "Explains architecture, setup, run, and test commands."),
        PlannedFile("Dockerfile", "Optional container execution path requested by the task."),
        PlannedFile(".dockerignore", "Keeps local dependencies out of container builds."),
        PlannedFile("architecture_spec.json", "Preserves the exact architecture input used."),
    ]
    return GenerationPlan(
        project_name=specification.project_name,
        target_directory=target_directory or specification.project_name,
        files=files,
    )
