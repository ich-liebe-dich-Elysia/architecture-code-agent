"""Failure handling tests for the independent generated-game acceptance probe."""

from pathlib import Path
import json
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from agent.acceptance import _PROBE, _REQUIRED_CHECKS, run_acceptance


class AcceptanceTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.project = Path(self.temporary.name)
        (self.project / "src").mkdir()
        (self.project / "src" / "app.js").touch()

    def probe_result(self, checks, passed=True, returncode=0):
        stdout = "__AGENT_ACCEPTANCE__" + json.dumps({"passed": passed, "checks": checks})
        return subprocess.CompletedProcess(["node"], returncode, stdout=stdout, stderr="")

    def test_missing_application_fails(self):
        result = run_acceptance(self.project / "absent")
        self.assertFalse(result["passed"])
        self.assertIn("missing src/app.js", result["checks"][0]["detail"])

    @patch("agent.acceptance.shutil.which", return_value=None)
    def test_missing_node_fails(self, _which):
        result = run_acceptance(self.project)
        self.assertFalse(result["passed"])
        self.assertIn("Node.js", result["checks"][0]["detail"])

    @patch("agent.acceptance.shutil.which", return_value="node")
    @patch("agent.acceptance.subprocess.run")
    def test_empty_checks_cannot_pass(self, run, _which):
        run.return_value = self.probe_result([])
        result = run_acceptance(self.project)
        self.assertFalse(result["passed"])
        self.assertIn("empty", result["checks"][0]["detail"])

    @patch("agent.acceptance.shutil.which", return_value="node")
    @patch("agent.acceptance.subprocess.run")
    def test_partial_checks_cannot_pass(self, run, _which):
        run.return_value = self.probe_result([{"name": "health", "passed": True, "detail": "OK"}])
        result = run_acceptance(self.project)
        self.assertFalse(result["passed"])
        self.assertEqual(result["checks"][-1]["name"], "acceptance completeness")

    @patch("agent.acceptance.shutil.which", return_value="node")
    @patch("agent.acceptance.subprocess.run")
    def test_success_uses_independent_probe_and_scrubs_api_key(self, run, _which):
        checks = [{"name": name, "passed": True, "detail": "OK"} for name in _REQUIRED_CHECKS]
        run.return_value = self.probe_result(checks)
        with patch.dict("os.environ", {"DEEPSEEK_API_KEY": "do-not-forward-this"}):
            result = run_acceptance(self.project, timeout=17)
        self.assertTrue(result["passed"])
        call = run.call_args
        self.assertEqual(call.args[0][0:2], ["node", "-"])
        self.assertIn("invalid answer does not advance", call.kwargs["input"])
        self.assertNotIn("DEEPSEEK_API_KEY", call.kwargs["env"])
        self.assertEqual(call.kwargs["timeout"], 17)

    @patch("agent.acceptance.shutil.which", return_value="node")
    @patch("agent.acceptance.subprocess.run")
    def test_timeout_reports_captured_output(self, run, _which):
        run.side_effect = subprocess.TimeoutExpired("node", 1, output=b"startup failed", stderr=b"details")
        result = run_acceptance(self.project, timeout=1)
        self.assertFalse(result["passed"])
        self.assertIn("startup failed", result["output"])

    @patch("agent.acceptance.shutil.which", return_value="node")
    @patch("agent.acceptance.subprocess.run")
    def test_absent_protocol_does_not_pass_on_exit_zero(self, run, _which):
        run.return_value = subprocess.CompletedProcess(["node"], 0, stdout="0 tests run", stderr="")
        result = run_acceptance(self.project)
        self.assertFalse(result["passed"])
        self.assertIn("structured", result["checks"][0]["detail"])

    @unittest.skipUnless(shutil.which("node"), "Node.js is needed to test the fixed JavaScript assertions")
    def test_teaching_feedback_and_public_question_assertions(self):
        helpers = _PROBE.partition("async function main()")[0]
        assertions = r"""
bank = [{id: 'q1', answer: '3/4', explanation: 'Same denominator: add numerators, keep the denominator.'}];
const question = {id: 'q1', prompt: '1/4 + 2/4 = ?', options: ['3/4', '3/8']};
publicQuestion(question);
assert.throws(() => publicQuestion({...question, explanation: bank[0].explanation}), /leaks explanation/);
assert.throws(() => instructionalFeedback({feedback: 'Correct!'}, question), /teaching explanation/);
assert.throws(() => instructionalFeedback({feedback: 'OK'}, question), /teach the calculation/);
instructionalFeedback({feedback: 'Correct! ' + bank[0].explanation}, question);
instructionalFeedback({feedback: 'Incorrect', explanation: bank[0].explanation}, question);
assert.throws(() => instructionalFeedback({feedback: 'Incorrect', explanation: 'unrelated long explanation'}, question),
  /teaching explanation/);
"""
        result = subprocess.run(
            [shutil.which("node"), "-"], input=helpers + assertions,
            capture_output=True, text=True, encoding="utf-8", timeout=15,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
