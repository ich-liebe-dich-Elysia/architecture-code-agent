"""Coding-loop tests use a fake model; no real credentials or API calls are needed."""

from contextlib import ExitStack
import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch

from agent.generation_prompts import ALLOWED_FILES, GROUPS
from agent.llm_workflow import (
    GenerationCancelled,
    GenerationFailure,
    package_error,
    run_generation,
    verify_project,
    write_model_files,
)
from tests.fixtures import architecture_documents


def valid_package():
    return {
        "name": "space-fractions",
        "private": True,
        "type": "commonjs",
        "scripts": {"start": "node src/app.js", "test": "node --test"},
        "dependencies": {"express": "4.22.3"},
    }


class ModelFileTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name) / "generated"
        self.root.mkdir()
        (self.root / "README.md").write_text("existing documentation\n", encoding="utf-8")

    def assert_untouched(self):
        self.assertEqual((self.root / "README.md").read_text(encoding="utf-8"), "existing documentation\n")
        self.assertEqual(sorted(path.name for path in self.root.iterdir()), ["README.md"])

    def test_path_traversal_rejects_entire_batch_before_writes(self):
        for bad_path in ("../escape.txt", "src/../../escape.txt", "C:/escape.txt", "src\\app.js", "/etc/test"):
            with self.subTest(path=bad_path):
                response = {"files": [
                    {"path": "README.md", "content": "would overwrite existing file"},
                    {"path": bad_path, "content": "must not be written"},
                ]}
                with self.assertRaises(GenerationFailure):
                    write_model_files(self.root, response)
                self.assert_untouched()
                self.assertFalse((self.root.parent / "escape.txt").exists())

    def test_duplicate_paths_leave_existing_file_unchanged(self):
        with self.assertRaises(GenerationFailure):
            write_model_files(self.root, {"files": [
                {"path": "README.md", "content": "one"},
                {"path": "README.md", "content": "two"},
            ]})
        self.assert_untouched()

    def test_incomplete_group_leaves_no_partial_files(self):
        with self.assertRaises(GenerationFailure):
            write_model_files(self.root, {"files": [{"path": "src/app.js", "content": "model output"}]},
                              required=["src/app.js", "src/questions.js"])
        self.assert_untouched()

    def test_success_preserves_model_content(self):
        content = "// Different model output, not a template\nmodule.exports = {value: 713};"
        paths = write_model_files(self.root, {"files": [{"path": "src/app.js", "content": content}]},
                                  required=["src/app.js"])
        self.assertEqual(paths, ["src/app.js"])
        self.assertEqual((self.root / "src/app.js").read_text(encoding="utf-8"), content + "\n")


class PackageAndVerificationTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)

    def write_package(self, package):
        (self.root / "package.json").write_text(json.dumps(package), encoding="utf-8")

    def test_exact_contract_package_is_accepted(self):
        self.write_package(valid_package())
        self.assertIsNone(package_error(self.root))

    def test_extra_npm_script_is_rejected(self):
        package = valid_package()
        package["scripts"]["postinstall"] = "node unwanted.js"
        self.write_package(package)
        self.assertIsNotNone(package_error(self.root))

    def test_additional_dependency_is_rejected(self):
        package = valid_package()
        package["dependencies"]["another-package"] = "1.0.0"
        self.write_package(package)
        self.assertIsNotNone(package_error(self.root))

    def test_nonruntime_dependency_sections_cannot_bypass_allowlist(self):
        for section in ("devDependencies", "optionalDependencies", "peerDependencies"):
            with self.subTest(section=section):
                package = valid_package()
                package[section] = {"another-package": "1.0.0"}
                self.write_package(package)
                self.assertIsNotNone(package_error(self.root), section + " bypassed Express-only contract")

    def test_zero_or_missing_test_count_cannot_pass(self):
        for path in ALLOWED_FILES:
            target = self.root / path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text("// test fixture\n", encoding="utf-8")
        self.write_package(valid_package())
        for output in ("TAP version 13\n1..0\n# tests 0\n# pass 0", "process exited without running tests"):
            with self.subTest(output=output), ExitStack() as stack:
                stack.enter_context(patch("agent.llm_workflow.shutil.which", return_value="node"))
                execute = stack.enter_context(patch("agent.llm_workflow.execute"))
                execute.side_effect = lambda command, *_args: {
                    "passed": True, "returncode": 0, "output": output if "--test" in command else "",
                }
                stack.enter_context(patch("agent.acceptance.run_acceptance", return_value={
                    "passed": True, "checks": [], "output": "independent checks passed",
                }))
                result = verify_project(self.root)
                self.assertFalse(result["passed"])
                self.assertFalse(result["tests"]["passed"])
                self.assertIn("At least six", result["output"])


class GenerationLifecycleTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.model_files = {
            path: json.dumps(valid_package()) if path == "package.json" else f"unique model content for {path}"
            for path in ALLOWED_FILES
        }
        self.plan = {"summary": "A model-selected implementation", "assumptions": ["local persistence"]}
        self.events = []

    def responses(self):
        return [self.plan] + [{"files": [{"path": path, "content": self.model_files[path]} for path in paths]}
                              for _, paths in GROUPS]

    def mocked_tools(self, stack, responses=None, results=None):
        stack.enter_context(patch("agent.llm_workflow.shutil.which", side_effect=lambda command: command))
        model = stack.enter_context(patch("agent.llm_workflow.DeepSeekClient")).return_value
        model.complete_json.side_effect = responses or self.responses()
        execute = stack.enter_context(patch("agent.llm_workflow.execute", return_value={
            "passed": True, "returncode": 0, "output": "installed",
        }))
        verify = stack.enter_context(patch("agent.llm_workflow.verify_project"))
        verify.side_effect = results or [{"passed": True, "output": "all checks passed"}]
        return model, execute, verify

    def test_full_generation_writes_model_sources_and_complete_lifecycle(self):
        with architecture_documents() as (documentation, views), ExitStack() as stack:
            model, execute, verify = self.mocked_tools(stack)
            target = run_generation(documentation, views, self.root, api_key="sk-unit-test-secret",
                                    on_event=self.events.append)
        self.assertEqual(target, self.root / "space-fractions-llm")
        for path, content in self.model_files.items():
            self.assertEqual((target / path).read_text(encoding="utf-8"), content + "\n")
        self.assertEqual(model.complete_json.call_count, 1 + len(GROUPS))
        self.assertEqual([event["stage"] for event in self.events],
                         ["analyze", "plan", *[group for group, _ in GROUPS], "install", "test", "complete"])
        self.assertEqual(json.loads((target / ".agent-plan.json").read_text(encoding="utf-8")), self.plan)
        state = json.loads((target / ".agent-state.json").read_text(encoding="utf-8"))
        self.assertEqual(state["status"], "passed")
        self.assertEqual(state["completed_groups"], [group for group, _ in GROUPS])
        self.assertEqual(state["repairs"], 0)
        self.assertEqual(json.loads((self.root / "latest-project.json").read_text())["path"], target.name)
        self.assertTrue((target / "Start-Game.cmd").is_file())
        execute.assert_called_once()
        self.assertIn("--ignore-scripts", execute.call_args.args[0])
        verify.assert_called_once_with(target)
        prompts = "\n".join(call.args[0][1]["content"] for call in model.complete_json.call_args_list)
        self.assertIn("Space Fractions", prompts)
        self.assertIn("PlantUML views:", prompts)
        self.assertIn(self.plan["summary"], prompts)
        for file in target.rglob("*"):
            if file.is_file():
                self.assertNotIn("sk-unit-test-secret", file.read_text(encoding="utf-8"))

    def test_failed_check_is_sent_to_model_and_repaired_code_is_verified(self):
        repaired = "// model repair selected after observing failed scoring"
        responses = self.responses() + [{"diagnosis": "score bug", "files": [
            {"path": "src/app.js", "content": repaired},
        ]}]
        with architecture_documents() as (documentation, views), ExitStack() as stack:
            model, execute, verify = self.mocked_tools(stack, responses=responses, results=[
                {"passed": False, "output": "correct answer score stayed zero"},
                {"passed": True, "output": "all checks passed"},
            ])
            target = run_generation(documentation, views, self.root, api_key="sk-unit-test",
                                    on_event=self.events.append)
        self.assertEqual((target / "src/app.js").read_text(encoding="utf-8"), repaired + "\n")
        self.assertEqual(verify.call_count, 2)
        self.assertEqual(execute.call_count, 2)
        repair_prompt = model.complete_json.call_args_list[-1].args[0][1]["content"]
        self.assertIn("correct answer score stayed zero", repair_prompt)
        self.assertIn(self.model_files["src/app.js"], repair_prompt)
        self.assertIn("repair", [event["stage"] for event in self.events])
        state = json.loads((target / ".agent-state.json").read_text(encoding="utf-8"))
        self.assertEqual(state["repairs"], 1)
        self.assertEqual(state["status"], "passed")

    def test_install_failure_does_not_claim_success_or_ask_model_to_fix_network(self):
        with architecture_documents() as (documentation, views), ExitStack() as stack:
            model, execute, verify = self.mocked_tools(stack)
            execute.return_value = {"passed": False, "returncode": 1, "output": "registry not reachable"}
            with self.assertRaisesRegex(GenerationFailure, "registry not reachable"):
                run_generation(documentation, views, self.root, api_key="sk-unit-test",
                               on_event=self.events.append)
        verify.assert_not_called()
        self.assertEqual(model.complete_json.call_count, 1 + len(GROUPS))
        self.assertFalse((self.root / "latest-project.json").exists())
        state = json.loads((self.root / "space-fractions-llm/.agent-state.json").read_text(encoding="utf-8"))
        self.assertEqual(state["status"], "failed")
        self.assertEqual(self.events[-1]["stage"], "failed")

    def test_cancelled_run_never_calls_model_and_records_cancelled(self):
        stop = threading.Event()
        stop.set()
        with architecture_documents() as (documentation, views), ExitStack() as stack:
            model, execute, verify = self.mocked_tools(stack)
            with self.assertRaises(GenerationCancelled):
                run_generation(documentation, views, self.root, api_key="sk-unit-test", stop_event=stop)
        model.complete_json.assert_not_called()
        execute.assert_not_called()
        verify.assert_not_called()
        self.assertFalse((self.root / "latest-project.json").exists())
        state = json.loads((self.root / "space-fractions-llm/.agent-state.json").read_text(encoding="utf-8"))
        self.assertEqual(state["status"], "cancelled")


if __name__ == "__main__":
    unittest.main()
