"""Tests for the ArchitectureSpec JSON contract."""

from __future__ import annotations

import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from agent.specification import (
    ArchitectureSpec,
    SpecificationValidationError,
    create_example_specification,
)


class ArchitectureSpecTests(unittest.TestCase):
    def test_example_contains_the_key_task_information(self) -> None:
        specification = create_example_specification()

        self.assertEqual(specification.project_name, "space-fractions")
        self.assertIn("GameComponent", specification.components)
        self.assertIn("EndUser", specification.actors)
        self.assertEqual(specification.api_endpoints[0].path, "/play")

    def test_json_can_be_written_and_read_back(self) -> None:
        original = create_example_specification()

        with TemporaryDirectory() as temporary_directory:
            destination = Path(temporary_directory) / "architecture_spec.json"
            original.write_json(destination)
            restored = ArchitectureSpec.from_dict(
                json.loads(destination.read_text(encoding="utf-8"))
            )

        self.assertEqual(restored.to_dict(), original.to_dict())

    def test_empty_project_name_is_rejected(self) -> None:
        with self.assertRaises(SpecificationValidationError):
            ArchitectureSpec(project_name="", architecture_style="microservices")

    def test_duplicate_components_are_rejected(self) -> None:
        with self.assertRaises(SpecificationValidationError):
            ArchitectureSpec(
                project_name="demo",
                architecture_style="microservices",
                components=["GameComponent", "GameComponent"],
            )


if __name__ == "__main__":
    unittest.main()
