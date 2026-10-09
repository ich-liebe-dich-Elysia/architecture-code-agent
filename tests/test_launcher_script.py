"""Run the real generated launcher against a small local HTTP fixture."""

from __future__ import annotations

import http.client
import os
from pathlib import Path
import queue
import re
import shutil
import socket
import subprocess
import tempfile
import threading
import time
import unittest

from agent.llm_workflow import _launch_script


@unittest.skipUnless(shutil.which("node"), "Node.js is required for launcher runtime tests")
class GeneratedLauncherTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        (self.root / "src").mkdir()
        (self.root / "src" / "app.js").write_text(
            "exports.createApp = () => (request, response) => { response.end('fixture-ready'); };\n",
            encoding="utf-8",
        )
        _launch_script(self.root)

    def launch(self, port: int) -> tuple[subprocess.Popen[str], str]:
        environment = {key: value for key, value in os.environ.items()
                       if not any(word in key.upper() for word in ("API_KEY", "SECRET", "TOKEN"))}
        environment.update(PORT=str(port), NO_BROWSER="1")
        process = subprocess.Popen(
            [shutil.which("node"), "launch_game.cjs"], cwd=self.root, env=environment,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
            encoding="utf-8", errors="replace",
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
        )
        lines: queue.Queue[str] = queue.Queue()
        def capture() -> None:
            assert process.stdout is not None
            for line in process.stdout:
                lines.put(line)
        reader = threading.Thread(target=capture, daemon=True)
        reader.start()
        def cleanup() -> None:
            if process.poll() is None:
                process.terminate()
                process.wait(timeout=5)
            reader.join(timeout=2)
            if process.stdout:
                process.stdout.close()
        self.addCleanup(cleanup)
        deadline = time.monotonic() + 8
        output = []
        while time.monotonic() < deadline:
            try:
                line = lines.get(timeout=0.2)
            except queue.Empty:
                if process.poll() is not None:
                    break
                continue
            output.append(line)
            match = re.search(r"Game ready: (http://127\.0\.0\.1:\d+)", line)
            if match:
                return process, match.group(1)
        self.fail("Launcher never became ready: " + "".join(output))

    def assert_ready(self, url: str) -> None:
        port = int(url.rsplit(":", 1)[1])
        connection = http.client.HTTPConnection("127.0.0.1", port, timeout=2)
        try:
            connection.request("GET", "/")
            response = connection.getresponse()
            self.assertEqual(response.status, 200)
            self.assertEqual(response.read(), b"fixture-ready")
        finally:
            connection.close()

    def test_announced_address_is_immediately_ready(self) -> None:
        process, url = self.launch(0)
        self.assertIsNone(process.poll())
        self.assert_ready(url)

    def test_occupied_port_retries_on_an_available_port(self) -> None:
        occupied = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.addCleanup(occupied.close)
        occupied.bind(("127.0.0.1", 0))
        occupied.listen(1)
        port = occupied.getsockname()[1]
        _, url = self.launch(port)
        self.assertNotEqual(int(url.rsplit(":", 1)[1]), port)
        self.assert_ready(url)

    def test_invalid_port_exits_with_readable_error(self) -> None:
        environment = os.environ.copy()
        environment.update(PORT="not-a-port", NO_BROWSER="1")
        result = subprocess.run(
            [shutil.which("node"), "launch_game.cjs"], cwd=self.root, env=environment,
            capture_output=True, text=True, encoding="utf-8", timeout=5,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
        )
        self.assertEqual(result.returncode, 1)
        self.assertIn("PORT must be", result.stderr)
        self.assertNotIn("Game ready:", result.stdout)


if __name__ == "__main__":
    unittest.main()
