"""End-to-end tests for architecture analysis, generation, and validation."""

from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from agent.generator import generate_project
from agent.planner import create_generation_plan
from agent.validator import validate_project
from agent.workflow import analyze_architecture
from tests.fixtures import architecture_documents


class PipelineTests(unittest.TestCase):
    def test_pipeline_generates_a_valid_express_starter(self) -> None:
        with architecture_documents() as (documentation, views):
            specification = analyze_architecture(documentation, views)
        plan = create_generation_plan(specification)

        with TemporaryDirectory() as temporary_directory:
            output_directory = Path(temporary_directory)
            project_directory = generate_project(specification, plan, output_directory)
            report = validate_project(specification, plan, project_directory)

            self.assertTrue((project_directory / "src" / "app.js").is_file())
            self.assertTrue((project_directory / "tests" / "app.test.js").is_file())
            self.assertTrue(report.passed, report.to_markdown())
