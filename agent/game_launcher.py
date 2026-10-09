"""Start the generated game locally and own its server process."""

from __future__ import annotations

import atexit
from collections import deque
import http.client
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import threading
import time
import webbrowser
import zlib


def project_root() -> Path:
    """Use the directory beside the executable when running a packaged Agent."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


def find_node() -> str | None:
    """Prefer an optional bundled Node runtime, then the installed runtime."""
    root = project_root()
    candidates = [root / "runtime" / "node.exe", root / "node" / "node.exe"]
    if getattr(sys, "_MEIPASS", None):
        candidates.append(Path(sys._MEIPASS) / "runtime" / "node.exe")
    for candidate in candidates:
        if candidate.is_file():
            return str(candidate)
    return shutil.which("node")


def choose_game_port(project_dir: Path) -> int:
    """Prefer a repeatable browser origin so localStorage survives restarts.

    The standalone game uses port 3000. If it is occupied, try a stable port
    derived from this project's absolute path, then ask the OS for a free port.
    A fallback changes the browser origin, so saved browser progress from a
    different port is not available there. Never reuse another server's port.
    """
    project_path = os.path.normcase(str(Path(project_dir).resolve()))
    project_port = 35000 + zlib.crc32(project_path.encode("utf-8")) % 20001
    for candidate in (3000, project_port, 0):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
            try:
                probe.bind(("127.0.0.1", candidate))
            except OSError:
                if candidate == 0:
                    raise
                continue
            return int(probe.getsockname()[1])
    raise RuntimeError("无法分配本地游戏端口。")


class GameLauncher:
    """Keep one Node process alive and clean it up when the Agent closes."""

    def __init__(self) -> None:
        self.process: subprocess.Popen[str] | None = None
        self.project: Path | None = None
        self.url: str | None = None
        self.lines: deque[str] = deque(maxlen=100)
        self._lock = threading.Lock()
        atexit.register(self.stop)

    @property
    def running(self) -> bool:
        return self.process is not None and self.process.poll() is None

    def _capture_output(self, process: subprocess.Popen[str]) -> None:
        if process.stdout is None:
            return
        try:
            for line in process.stdout:
                self.lines.append(line.rstrip()[:1000])
        finally:
            process.stdout.close()

    def start(self, project_dir: Path, open_browser: bool = True) -> str:
        """Launch a Node/Express game, returning its working local URL."""
        project = Path(project_dir).resolve()
        with self._lock:
            if self.running:
                if project != self.project:
                    raise RuntimeError("已有一个游戏正在运行，请先点击“停止游戏”再启动其他项目。")
                assert self.url is not None
                if open_browser:
                    webbrowser.open(self.url)
                return self.url

            if not (project / "src" / "app.js").is_file():
                raise FileNotFoundError(f"找不到游戏入口：{project / 'src' / 'app.js'}")
            package_file = project / "package.json"
            if not package_file.is_file():
                raise FileNotFoundError(f"找不到 package.json：{project}")
            node = find_node()
            if not node:
                raise RuntimeError("未找到 Node.js。请安装 Node.js LTS，再重新打开 Agent。")

            package = json.loads(package_file.read_text(encoding="utf-8-sig"))
            dependencies = package.get("dependencies", {})
            missing = [name for name in dependencies if not (project / "node_modules" / name).is_dir()]
            if missing:
                raise RuntimeError(
                    "游戏依赖尚未安装：" + ", ".join(missing)
                    + f"。请在游戏目录打开终端运行 npm install：\n{project}"
                )

            port = choose_game_port(project)
            child_env = os.environ.copy()
            child_env.update(PORT=str(port), HOST="127.0.0.1", NODE_ENV="production")
            for secret_name in ("DEEPSEEK_API_KEY", "OPENAI_API_KEY"):
                child_env.pop(secret_name, None)
            flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
            self.lines.clear()
            self.process = subprocess.Popen(
                [node, str(project / "src" / "app.js")],
                cwd=project,
                env=child_env,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                stdin=subprocess.DEVNULL,
                text=True,
                encoding="utf-8",
                errors="replace",
                creationflags=flags,
            )
            self.project = project
            self.url = f"http://127.0.0.1:{port}"
            threading.Thread(target=self._capture_output, args=(self.process,), daemon=True).start()
            deadline = time.monotonic() + 20
            while time.monotonic() < deadline:
                if self.process.poll() is not None:
                    details = "\n".join(list(self.lines)[-8:])
                    raise RuntimeError(f"游戏服务启动失败（退出码 {self.process.returncode}）。\n{details}")
                connection = http.client.HTTPConnection("127.0.0.1", port, timeout=0.4)
                try:
                    connection.request("GET", "/")
                    response = connection.getresponse()
                    response.read(4096)
                    if response.status == 200:
                        if open_browser:
                            webbrowser.open(self.url)
                        return self.url
                except (OSError, http.client.HTTPException):
                    pass
                finally:
                    connection.close()
                time.sleep(0.15)
            self._stop_process()
            raise RuntimeError("游戏服务未在 20 秒内就绪，请检查 src/app.js 是否使用环境变量 PORT 并提供首页。")

    def _stop_process(self) -> None:
        process = self.process
        if process is not None and process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=4)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=4)
        self.process = None
        self.url = None

    def stop(self) -> None:
        """Stop only the child server process created by this launcher."""
        with self._lock:
            self._stop_process()


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="启动生成的 Space Fractions 游戏")
    parser.add_argument("project", type=Path, nargs="?", default=project_root() / "output" / "space-fractions-llm")
    args = parser.parse_args()
    launcher = GameLauncher()
    try:
        print(launcher.start(args.project))
        print("游戏已启动。按 Ctrl+C 停止服务。")
        while launcher.running:
            time.sleep(0.5)
    except KeyboardInterrupt:
        pass
    finally:
        launcher.stop()


if __name__ == "__main__":
    main()
