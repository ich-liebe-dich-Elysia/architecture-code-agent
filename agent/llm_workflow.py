"""DeepSeek plan -> write -> execute -> observe -> repair coding workflow."""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import threading
from datetime import datetime
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Callable

from agent.deepseek_client import DeepSeekClient, load_api_key
from agent.generation_prompts import (
    ALLOWED_FILES, GROUPS, SYSTEM_PROMPT, files_prompt, plan_prompt, repair_prompt,
)
from agent.workflow import analyze_architecture


class GenerationFailure(RuntimeError):
    """Generation did not reach a verified, runnable state."""


class GenerationCancelled(GenerationFailure):
    """User requested cancellation between bounded operations."""


def safe_file(root: Path, relative: str) -> Path:
    """Accept only the known relative source files, also on Windows."""
    if (not isinstance(relative, str) or relative not in ALLOWED_FILES
            or PureWindowsPath(relative).is_absolute() or '\\' in relative
            or '..' in PurePosixPath(relative).parts):
        raise GenerationFailure(f"Model returned an unsupported file path: {relative!r}")
    target = (root / relative).resolve()
    if not target.is_relative_to(root.resolve()):
        raise GenerationFailure("Output path escaped the generated project.")
    return target


def write_model_files(root: Path, response: dict, required: list[str] | None = None) -> list[str]:
    """Validate the entire response before writing any model-produced file."""
    files = response.get('files')
    if not isinstance(files, list) or not files:
        raise GenerationFailure("DeepSeek response has no generated files.")
    prepared = []
    seen = set()
    for item in files:
        if not isinstance(item, dict):
            raise GenerationFailure("Generated files must be path/content objects.")
        path, content = item.get('path'), item.get('content')
        target = safe_file(root, path)
        if path in seen or not isinstance(content, str) or not content.strip():
            raise GenerationFailure(f"Invalid or duplicated file: {path}")
        if len(content.encode('utf-8')) > 180_000:
            raise GenerationFailure(f"Generated file too large: {path}")
        seen.add(path)
        prepared.append((path, target, content))
    if required is not None and seen != set(required):
        raise GenerationFailure(f"Expected files {required}; received {sorted(seen)}")
    for _, target, content in prepared:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content.rstrip() + '\n', encoding='utf-8')
    return [item[0] for item in prepared]


def _sources(root: Path) -> str:
    return '\n'.join(f'--- {path} ---\n' + (root / path).read_text(encoding='utf-8')
                     for path in sorted(ALLOWED_FILES) if (root / path).is_file())


def clean_environment() -> dict[str, str]:
    """Do not inherit provider credentials into generated-code processes."""
    return {key: value for key, value in os.environ.items()
            if not any(word in key.upper() for word in ('API_KEY', 'SECRET', 'TOKEN'))}


def execute(command: list[str], cwd: Path, timeout: int = 180) -> dict:
    """Run only a caller-chosen command, with bounded time and output."""
    flags = subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
    try:
        result = subprocess.run(command, cwd=cwd, capture_output=True, text=True,
                                encoding='utf-8', errors='replace', timeout=timeout,
                                env=clean_environment(), creationflags=flags)
        return {'passed': result.returncode == 0, 'returncode': result.returncode,
                'output': (result.stdout + '\n' + result.stderr)[-18000:]}
    except subprocess.TimeoutExpired:
        return {'passed': False, 'returncode': -1, 'output': f'Command timeout after {timeout}s.'}
    except OSError as exc:
        return {'passed': False, 'returncode': -1, 'output': f'Cannot start tool: {exc}'}


def package_error(root: Path) -> str | None:
    """Keep the model's dependency and npm-script surface small and predictable."""
    try:
        package = json.loads((root / 'package.json').read_text(encoding='utf-8'))
        if package.get('scripts') != {'start': 'node src/app.js', 'test': 'node --test'}:
            return 'package.json scripts must be exactly start=node src/app.js and test=node --test.'
        if package.get('dependencies') != {'express': '4.22.3'} or any(
                package.get(field) for field in ('devDependencies', 'optionalDependencies', 'peerDependencies')):
            return 'Only dependency express:4.22.3 is allowed; no devDependencies.'
        if package.get('type', 'commonjs') != 'commonjs':
            return 'Generated project must use CommonJS.'
        return None
    except (OSError, ValueError, AttributeError) as exc:
        return f'Invalid package.json: {exc}'


def verify_project(root: Path) -> dict:
    """Execute syntax, generated tests, and our independent functional acceptance."""
    from agent.acceptance import run_acceptance
    issue = package_error(root)
    if issue:
        return {'passed': False, 'output': issue}
    node = shutil.which('node')
    if not node:
        return {'passed': False, 'output': 'Node.js is not installed.'}
    checks = []
    for path in sorted(ALLOWED_FILES):
        if not (root / path).is_file():
            checks.append({'passed': False, 'output': f'Missing file: {path}'})
        elif path.endswith('.js'):
            result = execute([node, '--check', str(root / path)], root, 30)
            if not result['passed']:
                checks.append(result)
    if checks:
        return {'passed': False, 'output': '\n'.join(c['output'] for c in checks)}
    tests = execute([node, '--test', 'tests/game.test.js'], root, 120)
    # A zero exit code without any tests is not adequate validation.
    count = re.search(r'# tests (\d+)', tests['output'])
    if not count or int(count.group(1)) < 6:
        tests['passed'] = False
        tests['output'] += '\nAt least six real Node test cases are required.'
    acceptance = run_acceptance(root)
    return {'passed': bool(tests['passed'] and acceptance['passed']),
            'output': 'Generated tests:\n' + tests['output'] + '\nIndependent acceptance:\n'
                      + json.dumps(acceptance, ensure_ascii=False),
            'tests': tests, 'acceptance': acceptance}


def _write_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def _launch_script(root: Path) -> None:
    # A launcher is infrastructure. All application source remains the model's output.
    (root / 'launch_game.cjs').write_text(r'''"use strict";

const http = require("node:http");
const { spawn } = require("node:child_process");

function openBrowser(url) {
  if (process.env.NO_BROWSER === "1") return;
  let command;
  let args;
  if (process.platform === "win32") {
    command = "rundll32.exe";
    args = ["url.dll,FileProtocolHandler", url];
  } else if (process.platform === "darwin") {
    command = "open";
    args = [url];
  } else {
    command = "xdg-open";
    args = [url];
  }
  const browser = spawn(command, args, {
    detached: true, stdio: "ignore", windowsHide: true, shell: false,
  });
  browser.on("error", () => console.error("Open this address in your browser: " + url));
  browser.unref();
}

function launch() {
  const portText = (process.env.PORT || "3000").trim();
  const requestedPort = Number(portText);
  if (!/^\d+$/.test(portText) || !Number.isInteger(requestedPort) || requestedPort < 0 || requestedPort > 65535) {
    throw new Error("PORT must be a whole number from 0 to 65535.");
  }
  const { createApp } = require("./src/app.js");
  if (typeof createApp !== "function") throw new Error("src/app.js must export createApp().");
  const app = createApp();
  let activeServer;
  function listen(port, retried) {
    const server = http.createServer(app);
    activeServer = server;
    server.once("error", (error) => {
      if (error.code === "EADDRINUSE" && !retried && port !== 0) {
        console.log("Port " + port + " is occupied; choosing an available local port.");
        listen(0, true);
        return;
      }
      console.error("Cannot start game server: " + error.message);
      process.exitCode = 1;
    });
    server.listen(port, "127.0.0.1", () => {
      const url = "http://127.0.0.1:" + server.address().port;
      console.log("Game ready: " + url);
      console.log("Keep this window open while playing. Press Ctrl+C to stop.");
      openBrowser(url);
    });
  }
  listen(requestedPort, false);
  process.once("SIGINT", () => {
    if (activeServer) activeServer.close(() => process.exit(0));
  });
}

try {
  launch();
} catch (error) {
  console.error("Cannot start game: " + error.message);
  console.error("Check Node.js, run npm install in this directory, and try again.");
  process.exitCode = 1;
}
''', encoding='utf-8')
    (root / 'Start-Game.cmd').write_text(
        '@echo off\r\nsetlocal\r\ncd /d "%~dp0"\r\n'
        'where node >nul 2>nul\r\n'
        'if errorlevel 1 (\r\n'
        '  echo Node.js is missing. Install Node.js 22 or newer, then reopen this file.\r\n'
        '  pause\r\n  exit /b 1\r\n)\r\n'
        'if not exist "node_modules\\express" (\r\n'
        '  where npm.cmd >nul 2>nul\r\n'
        '  if errorlevel 1 (\r\n'
        '    echo npm is missing. Reinstall Node.js with npm, then reopen this file.\r\n'
        '    pause\r\n    exit /b 1\r\n  )\r\n'
        '  echo Installing game dependencies...\r\n'
        '  call npm.cmd install --ignore-scripts --no-audit --no-fund\r\n'
        '  if errorlevel 1 (\r\n'
        '    echo Dependency installation failed. Check your network and try again.\r\n'
        '    pause\r\n    exit /b 1\r\n  )\r\n)\r\n'
        'set "NODE_ENV=production"\r\n'
        'set "DEEPSEEK_API_KEY="\r\nset "OPENAI_API_KEY="\r\n'
        'node launch_game.cjs\r\n'
        'if errorlevel 1 (echo The game could not start. See the error above. & pause & exit /b 1)\r\n',
        encoding='ascii', newline='')
    (root / '.gitignore').write_text('node_modules/\ndata/\n.env\n*.log\n', encoding='utf-8')
    (root / '.dockerignore').write_text('node_modules\ndata\n.git\n.env\n', encoding='utf-8')


def repair_project(
    project_directory: Path, feedback: str, key_file: Path | None = None,
    api_key: str | None = None, model: str = 'deepseek-flash', max_repairs: int = 2,
    on_event: Callable[[dict], None] | None = None,
) -> Path:
    """Use observed runtime/UI feedback to improve an existing generated project."""
    root = Path(project_directory).resolve()
    if not (root / '.agent-state.json').is_file():
        raise GenerationFailure('请选择由 LLM Agent 生成的项目。')
    client = DeepSeekClient(load_api_key(api_key, key_file), model=model)
    context = 'Architecture specification:\n' + (root / 'architecture_spec.json').read_text(encoding='utf-8')
    state_path = root / '.agent-state.json'
    state = json.loads(state_path.read_text(encoding='utf-8'))
    state['status'] = 'repairing'
    _write_json(state_path, state)
    try:
        for attempt in range(max_repairs + 1):
            if on_event:
                on_event({'stage': 'repair', 'message': f'DeepSeek 正在修复实际运行问题（{attempt + 1}）。'})
            response = client.complete_json([
                {'role': 'system', 'content': SYSTEM_PROMPT},
                {'role': 'user', 'content': repair_prompt(context, _sources(root), feedback)},
            ], max_tokens=20000)
            write_model_files(root, response)
            state['repairs'] = state.get('repairs', 0) + 1
            result = verify_project(root)
            if result['passed']:
                _launch_script(root)
                state['status'] = 'passed'
                _write_json(state_path, state)
                return root
            feedback = result['output'][-20000:]
        raise GenerationFailure('修复后的代码尚未通过验收：\n' + feedback[-5000:])
    except Exception:
        state['status'] = 'failed'
        _write_json(state_path, state)
        raise


def run_generation(
    documentation: Path, views: Path, output_root: Path,
    api_key: str | None = None, key_file: Path | None = None,
    base_url: str = 'https://api.deepseek.com', model: str = 'deepseek-flash',
    max_repairs: int = 2, on_event: Callable[[dict], None] | None = None,
    stop_event: threading.Event | None = None,
) -> Path:
    """Generate a fresh complete game using real DeepSeek calls, then verify it.

    Existing projects are never overwritten. Each rerun gets a distinct directory.
    Keys live only in the HTTP client; persistent state contains no prompt credentials.
    """
    if not 0 <= max_repairs <= 5:
        raise ValueError('max_repairs must be between 0 and 5.')
    key = load_api_key(api_key, key_file)
    client = DeepSeekClient(key, base_url=base_url, model=model)
    if not shutil.which('node') or not shutil.which('npm'):
        raise GenerationFailure('请先安装 Node.js 22 或更高版本（包含 npm）。')
    docs = []
    for path in (Path(documentation), Path(views)):
        if not path.is_file() or path.stat().st_size > 200_000:
            raise GenerationFailure(f'输入文件不存在或超过 200 KB：{path.name}')
        docs.append(path.read_text(encoding='utf-8-sig'))
    output_root = Path(output_root).resolve()
    output_root.mkdir(parents=True, exist_ok=True)
    target = output_root / 'space-fractions-llm'
    if target.exists():
        target = output_root / ('space-fractions-llm-' + datetime.now().strftime('%Y%m%d-%H%M%S-%f'))
    target.mkdir()
    state_file = target / '.agent-state.json'
    state = {'status': 'running', 'model': model, 'completed_groups': [], 'repairs': 0}

    def emit(stage: str, message: str) -> None:
        if on_event:
            on_event({'stage': stage, 'message': message})

    def check_cancel() -> None:
        if stop_event and stop_event.is_set():
            raise GenerationCancelled('生成已取消；已完成的文件保留在输出目录。')

    def call(prompt: str, max_tokens: int = 16000) -> dict:
        check_cancel()
        response = client.complete_json([
            {'role': 'system', 'content': SYSTEM_PROMPT},
            {'role': 'user', 'content': prompt},
        ], max_tokens=max_tokens)
        check_cancel()
        return response

    try:
        emit('analyze', '读取两份架构文档并整理规格。')
        spec = analyze_architecture(Path(documentation), Path(views)).to_dict()
        _write_json(target / 'architecture_spec.json', spec)
        context = 'Architecture specification:\n' + json.dumps(spec, ensure_ascii=False)
        context += '\nArchitectural documentation:\n' + docs[0] + '\nPlantUML views:\n' + docs[1]
        emit('plan', f'调用 {model} 分析功能并制定实现计划。')
        plan = call(plan_prompt(context), 4000)
        _write_json(target / '.agent-plan.json', plan)
        for group, paths in GROUPS:
            emit(group, f'DeepSeek 正在生成 {group}：' + ', '.join(paths))
            response = call(files_prompt(context, json.dumps(plan, ensure_ascii=False),
                                         group, paths, _sources(target)))
            write_model_files(target, response, paths)
            state['completed_groups'].append(group)
            _write_json(state_file, state)
        npm = shutil.which('npm.cmd') if os.name == 'nt' else shutil.which('npm')
        for attempt in range(max_repairs + 1):
            check_cancel()
            issue = package_error(target)
            if not issue:
                emit('install', '安装生成项目的 Express 依赖。')
                install = execute([npm, 'install', '--ignore-scripts', '--no-audit', '--no-fund'],
                                  target, 240)
                if not install['passed']:
                    # A registry/network outage is not a source-code bug to repair with the LLM.
                    raise GenerationFailure('依赖安装失败，请检查 npm 网络连接。\n' + install['output'][-2000:])
                emit('test', '运行生成的测试和独立游戏功能验收。')
                result = verify_project(target)
            else:
                result = {'passed': False, 'output': issue}
            if result['passed']:
                _launch_script(target)
                state.update(status='passed', repairs=attempt)
                _write_json(state_file, state)
                _write_json(output_root / 'latest-project.json', {'path': target.name})
                emit('complete', f'生成成功，游戏已通过功能测试：{target}')
                return target
            if attempt >= max_repairs:
                raise GenerationFailure('达到修复次数上限，项目尚未通过测试。\n' + result['output'][-8000:])
            emit('repair', f'测试发现问题，反馈给 DeepSeek 自动修复（{attempt + 1}/{max_repairs}）。')
            response = call(repair_prompt(context, _sources(target), result['output'][-20000:]))
            write_model_files(target, response)
            state['repairs'] = attempt + 1
            _write_json(state_file, state)
    except Exception as exc:
        state['status'] = 'cancelled' if isinstance(exc, GenerationCancelled) else 'failed'
        _write_json(state_file, state)
        # Never interpolate the API key into user-facing messages.
        emit(state['status'], str(exc).replace(key, '[REDACTED]'))
        raise
    raise GenerationFailure('Generation ended without a verified project.')
