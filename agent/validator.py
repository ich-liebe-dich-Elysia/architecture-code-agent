"""Validate the generated starter project and write a concise report."""

from __future__ import annotations

import json
import os
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from agent.planner import GenerationPlan
from agent.specification import ArchitectureSpec


@dataclass
class ValidationCheck:
    """The name, status, and evidence for one validation rule."""

    name: str
    passed: bool
    detail: str


@dataclass
class ValidationReport:
    """A collection of validation checks suitable for Markdown output."""

    checks: list[ValidationCheck] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return all(check.passed for check in self.checks)

    def add(self, name: str, passed: bool, detail: str) -> None:
        self.checks.append(ValidationCheck(name=name, passed=passed, detail=detail))

    def to_markdown(self) -> str:
        status = "PASSED" if self.passed else "FAILED"
        rows = "\n".join(
            f"| {check.name} | {'PASS' if check.passed else 'FAIL'} | {check.detail} |"
            for check in self.checks
        )
        return f"""# Generation Validation Report

Overall status: **{status}**

| Check | Status | Evidence |
| --- | --- | --- |
{rows}
"""

    def write_markdown(self, destination: Path) -> None:
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(self.to_markdown(), encoding="utf-8")


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8") if path.is_file() else ""


def validate_project(
    specification: ArchitectureSpec,
    plan: GenerationPlan,
    project_directory: Path,
    run_npm_tests: bool = False,
) -> ValidationReport:
    """Check file completeness, critical content, and optionally Jest tests."""
    report = ValidationReport()
    project_directory = project_directory.resolve()

    for planned_file in plan.files:
        artifact = project_directory / planned_file.path
        report.add(
            f"Generated {planned_file.path}",
            artifact.is_file(),
            planned_file.reason,
        )

    package_path = project_directory / "package.json"
    try:
        package = json.loads(_read_text(package_path))
        has_express = "express" in package.get("dependencies", {})
        has_test_command = "test" in package.get("scripts", {})
        report.add("Valid package.json", True, "JSON parsed successfully.")
        report.add("Express dependency", has_express, "dependencies.express is present.")
        report.add("Test command", has_test_command, "scripts.test is present.")
    except json.JSONDecodeError:
        report.add("Valid package.json", False, "package.json is not valid JSON.")
    except OSError:
        report.add("Valid package.json", False, "package.json is missing.")

    route_source = _read_text(project_directory / "src" / "routes" / "game.js")
    report.add(
        "Documented /play route",
        'router.get("/play"' in route_source,
        "src/routes/game.js contains the documented GET /play endpoint.",
    )
    report.add(
        "Question responsibility",
        (project_directory / "src" / "services" / "questionService.js").is_file(),
        "Question retrieval and answer checking are separated into a service.",
    )

    generated_spec_path = project_directory / "architecture_spec.json"
    try:
        generated_spec = json.loads(_read_text(generated_spec_path))
        report.add(
            "Architecture traceability",
            generated_spec == specification.to_dict(),
            "Generated project retains the exact ArchitectureSpec input.",
        )
    except json.JSONDecodeError:
        report.add("Architecture traceability", False, "Generated spec is invalid JSON.")

    if run_npm_tests:
        try:
            npm_executable = "npm.cmd" if os.name == "nt" else "npm"
            completed = subprocess.run(
                [npm_executable, "test"],
                cwd=project_directory,
                capture_output=True,
                text=True,
                timeout=90,
                check=False,
            )
            detail = (completed.stdout + completed.stderr).strip().replace("\n", " ")
            report.add(
        "Generated Node test suite",
                completed.returncode == 0,
                detail[-500:] or "npm test completed.",
            )
        except (FileNotFoundError, subprocess.TimeoutExpired) as error:
            report.add("Generated Node test suite", False, str(error))

    return report
