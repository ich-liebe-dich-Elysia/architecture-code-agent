"""Tests for the public command-line interface."""

from __future__ import annotations

import unittest
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from agent.cli import PROJECT_VERSION, main


class CliTests(unittest.TestCase):
    def test_check_command_returns_success_and_version(self) -> None:
        output = StringIO()

        with patch("sys.stdout", output):
            exit_code = main(["check"])

        self.assertEqual(exit_code, 0)
        self.assertIn(PROJECT_VERSION, output.getvalue())

    def test_sample_spec_writes_json_inside_output_directory(self) -> None:
        output = StringIO()

        with TemporaryDirectory() as temporary_directory:
            project_root = Path(temporary_directory)
            with patch("agent.cli.PROJECT_ROOT", project_root), patch(
                "sys.stdout", output
            ):
                exit_code = main(
                    ["sample-spec", "--output", "output/example.json"]
                )

            generated_file = project_root / "output" / "example.json"
            self.assertTrue(generated_file.is_file())
            self.assertIn('"project_name": "space-fractions"', generated_file.read_text(encoding="utf-8"))

        self.assertEqual(exit_code, 0)
        self.assertIn("已写入示例架构规格", output.getvalue())

    def test_sample_spec_rejects_path_outside_output_directory(self) -> None:
        output = StringIO()

        with patch("sys.stdout", output):
            exit_code = main(["sample-spec", "--output", "../unsafe.json"])

        self.assertEqual(exit_code, 2)
        self.assertIn("输出文件必须位于", output.getvalue())


if __name__ == "__main__":
    unittest.main()
