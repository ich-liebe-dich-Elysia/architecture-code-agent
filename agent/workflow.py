"""Orchestrate parsing, planning, generation, and validation commands."""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path

from agent.documentation_parser import parse_documentation
from agent.generator import generate_project
from agent.planner import GenerationPlan, create_generation_plan
from agent.specification import ArchitectureSpec
from agent.uml_parser import parse_uml_views
from agent.validator import validate_project


def default_documentation_path(project_root: Path) -> Path:
    """Return the supplied architecture-document location relative to AgentProject."""
    return project_root.parent / "RotationTask(1)" / "Architecture_Documentation.md"


def default_views_path(project_root: Path) -> Path:
    """Return the supplied UML-view location relative to AgentProject."""
    return project_root.parent / "RotationTask(1)" / "Architecture_View.md"


def resolve_output_path(project_root: Path, user_path: str) -> Path:
    """Resolve a file or directory while enforcing the output/ safety boundary."""
    requested_path = Path(user_path)
    candidate = requested_path if requested_path.is_absolute() else project_root / requested_path
    resolved_path = candidate.resolve()
    output_root = (project_root / "output").resolve()
    try:
        resolved_path.relative_to(output_root)
    except ValueError as error:
        raise ValueError("All generated artifacts must remain inside AgentProject/output/.") from error
    return resolved_path


def _unique(values: list[str]) -> list[str]:
    result: list[str] = []
    for value in values:
        if value not in result:
            result.append(value)
    return result


def analyze_architecture(documentation_path: Path, views_path: Path) -> ArchitectureSpec:
    """Combine facts from the two supplied input documents into one spec."""
    documentation = parse_documentation(documentation_path)
    views = parse_uml_views(views_path)
    return ArchitectureSpec(
        project_name=documentation.project_name,
        architecture_style=documentation.architecture_style,
        technology_stack=documentation.technology_stack,
        actors=views.actors,
        components=_unique(documentation.components + views.components),
        entities=views.entities,
        use_cases=views.use_cases,
        api_endpoints=documentation.api_endpoints,
        data_entities=documentation.data_entities,
        deployment_notes=documentation.deployment_notes,
        relationships=views.relationships,
        interactions=views.interactions,
        states=views.states,
        requirements=documentation.requirements,
    )


def _load_specification(path: Path) -> ArchitectureSpec:
    if not path.is_file():
        raise FileNotFoundError(f"Architecture specification does not exist: {path}")
    return ArchitectureSpec.from_dict(json.loads(path.read_text(encoding="utf-8")))


def _load_plan(path: Path) -> GenerationPlan:
    if not path.is_file():
        raise FileNotFoundError(f"Generation plan does not exist: {path}")
    return GenerationPlan.from_dict(json.loads(path.read_text(encoding="utf-8")))


@dataclass(frozen=True)
class WorkflowPaths:
    """All paths required by a single command invocation."""

    documentation: Path
    views: Path
    specification: Path
    plan: Path
    project: Path
    report: Path


def build_workflow_paths(args: argparse.Namespace, project_root: Path) -> WorkflowPaths:
    """Convert user-facing command arguments to resolved, safe paths."""
    documentation = Path(args.documentation).resolve()
    views = Path(args.views).resolve()
    return WorkflowPaths(
        documentation=documentation,
        views=views,
        specification=resolve_output_path(project_root, args.spec),
        plan=resolve_output_path(project_root, args.plan),
        project=resolve_output_path(project_root, args.project_dir),
        report=resolve_output_path(project_root, args.report),
    )


def _write_analysis(paths: WorkflowPaths) -> ArchitectureSpec:
    specification = analyze_architecture(paths.documentation, paths.views)
    specification.write_json(paths.specification)
    return specification


def _write_plan(specification: ArchitectureSpec, paths: WorkflowPaths) -> GenerationPlan:
    plan = create_generation_plan(specification, target_directory=paths.project.name)
    plan.write_json(paths.plan)
    return plan


def run_workflow_command(args: argparse.Namespace, project_root: Path) -> int:
    """Execute one public workflow command and return a process-style exit code."""
    try:
        paths = build_workflow_paths(args, project_root)

        if args.command == "analyze":
            _write_analysis(paths)
            print(f"Architecture specification written to: {paths.specification}")
            return 0

        if args.command == "plan":
            specification = _load_specification(paths.specification)
            _write_plan(specification, paths)
            print(f"Generation plan written to: {paths.plan}")
            return 0

        if args.command == "generate":
            specification = _load_specification(paths.specification)
            plan = _load_plan(paths.plan) if paths.plan.is_file() else _write_plan(specification, paths)
            project_directory = generate_project(specification, plan, paths.project.parent)
            print(f"Generated project: {project_directory}")
            return 0

        if args.command == "validate":
            specification = _load_specification(paths.specification)
            plan = _load_plan(paths.plan)
            report = validate_project(
                specification,
                plan,
                paths.project,
                run_npm_tests=args.run_npm_tests,
            )
            report.write_markdown(paths.report)
            print(f"Validation report written to: {paths.report}")
            return 0 if report.passed else 1

        if args.command == "run":
            specification = _write_analysis(paths)
            plan = _write_plan(specification, paths)
            project_directory = generate_project(specification, plan, paths.project.parent)
            report = validate_project(
                specification,
                plan,
                project_directory,
                run_npm_tests=args.run_npm_tests,
            )
            report.write_markdown(paths.report)
            print(f"Architecture specification: {paths.specification}")
            print(f"Generation plan: {paths.plan}")
            print(f"Generated project: {project_directory}")
            print(f"Validation report: {paths.report}")
            return 0 if report.passed else 1

        raise ValueError(f"Unsupported workflow command: {args.command}")
    except (OSError, ValueError, json.JSONDecodeError) as error:
        print(f"Agent error: {error}")
        return 2
