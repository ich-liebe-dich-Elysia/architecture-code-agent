"""Command-line entry point for the Simple Architecture Code Agent."""

from __future__ import annotations

import argparse
from collections.abc import Sequence
from pathlib import Path

from agent.specification import create_example_specification
from agent.workflow import (
    default_documentation_path,
    default_views_path,
    run_workflow_command,
)


PROJECT_NAME = "Simple Architecture Code Agent"
PROJECT_VERSION = "1.0.0"
PROJECT_ROOT = Path(__file__).resolve().parent.parent


def build_parser() -> argparse.ArgumentParser:
    """Create the command-line parser used by the Agent."""
    parser = argparse.ArgumentParser(
        prog="architecture-agent",
        description="Generate a project starter from architecture documents.",
    )
    parser.add_argument(
        "command",
        choices=("check", "sample-spec", "analyze", "plan", "generate", "validate", "run"),
        help="Run a setup check, create an example spec, or execute the architecture-to-project workflow.",
    )
    parser.add_argument(
        "--output",
        default=None,
        help="JSON output path for sample-spec. It must stay inside output/.",
    )
    parser.add_argument(
        "--documentation",
        default=str(default_documentation_path(PROJECT_ROOT)),
        help="Path to Architecture_Documentation.md.",
    )
    parser.add_argument(
        "--views",
        default=str(default_views_path(PROJECT_ROOT)),
        help="Path to Architecture_View.md.",
    )
    parser.add_argument(
        "--spec",
        default="output/architecture_spec.json",
        help="ArchitectureSpec JSON output/input path.",
    )
    parser.add_argument(
        "--plan",
        default="output/generation_plan.json",
        help="Generation plan JSON output/input path.",
    )
    parser.add_argument(
        "--project-dir",
        default="output/space-fractions",
        help="Generated project directory; it must stay inside output/.",
    )
    parser.add_argument(
        "--report",
        default="output/generation_report.md",
        help="Validation report path; it must stay inside output/.",
    )
    parser.add_argument(
        "--run-npm-tests",
        action="store_true",
        help="Run npm test for the generated project during validate or run.",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {PROJECT_VERSION}",
    )
    return parser


def run_check() -> int:
    """Run the first, deliberately small health check for the project."""
    print(f"{PROJECT_NAME} {PROJECT_VERSION}")
    print("项目骨架检查通过：命令行入口可以正常运行。")
    print("下一步将实现架构文档解析。")
    return 0


def resolve_output_path(user_path: str) -> Path:
    """Resolve an output file and reject paths outside this project's output/."""
    requested_path = Path(user_path)
    candidate = requested_path if requested_path.is_absolute() else PROJECT_ROOT / requested_path
    resolved_path = candidate.resolve()
    output_root = (PROJECT_ROOT / "output").resolve()

    try:
        resolved_path.relative_to(output_root)
    except ValueError as error:
        raise ValueError("输出文件必须位于 AgentProject/output/ 目录内。") from error
    return resolved_path


def run_sample_spec(user_path: str) -> int:
    """Write the hand-designed example JSON used to teach step 2."""
    try:
        output_path = resolve_output_path(user_path)
    except ValueError as error:
        print(f"参数错误：{error}")
        return 2

    specification = create_example_specification()
    specification.write_json(output_path)
    print(f"已写入示例架构规格：{output_path}")
    print("注意：该文件是第 2 步的手工示例，尚未解析输入文档。")
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    """Parse arguments and run the selected command."""
    args = build_parser().parse_args(argv)
    if args.command == "check":
        return run_check()
    if args.command == "sample-spec":
        return run_sample_spec(args.output or "output/architecture_spec.example.json")
    if args.command in {"analyze", "plan", "generate", "validate", "run"}:
        return run_workflow_command(args, PROJECT_ROOT)
    raise AssertionError(f"Unsupported command: {args.command}")


if __name__ == "__main__":
    raise SystemExit(main())
