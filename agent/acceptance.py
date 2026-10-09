"""Independent HTTP acceptance checks for an LLM-generated fraction game.

These checks belong to the Agent, not to the generated project's own test suite.
They start the app on a temporary port with a temporary data file, exercise a
complete game, and close it. No model-written tests are trusted as acceptance.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
from typing import Any


_MARKER = "__AGENT_ACCEPTANCE__"
_REQUIRED_CHECKS = {
    "health",
    "browser interface and assets",
    "admin authentication",
    "question bank",
    "start game",
    "unknown game",
    "invalid answer does not advance",
    "pause and resume",
    "correct answer and score",
    "incorrect answer feedback",
    "complete round",
    "leaderboard",
    "persistent game and leaderboard",
    "help",
}

# Keep the probe independent of generated files. `node -` executes it from stdin.
# Only the generated application is imported; its test files are never loaded.
_PROBE = r"""
'use strict';
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const checks = [];
let server;
let base;
let game;
let bank;
let request;
let createApp;

async function check(name, action) {
  try {
    const detail = await action();
    checks.push({name, passed: true, detail: detail || 'OK'});
  } catch (error) {
    checks.push({name, passed: false, detail: String(error.message || error).slice(0, 1600)});
  }
}

function publicQuestion(question) {
  assert.ok(question && typeof question.id === 'string', 'question requires a string id');
  assert.ok(typeof question.prompt === 'string' && question.prompt.trim(), 'question prompt missing');
  assert.ok(Array.isArray(question.options) && question.options.length >= 2, 'need at least two choices');
  assert.ok(question.options.every(value => typeof value === 'string' && value.trim()), 'choices must be strings');
  for (const field of ['answer', 'correctAnswer', 'correctIndex', 'solution', 'explanation']) {
    assert.ok(!(field in question), `public question leaks ${field}`);
  }
}

function answerFor(question) {
  const record = bank.find(item => item.id === question.id);
  assert.ok(record, `game question ${question.id} absent from bank`);
  return record.answer;
}

function instructionalFeedback(body, answeredQuestion) {
  assert.ok(typeof body.feedback === 'string' && body.feedback.trim(), 'answer needs feedback');
  const record = bank.find(item => item.id === answeredQuestion.id);
  const explanation = record && record.explanation;
  const separateExplanation = typeof body.explanation === 'string' ? body.explanation.trim() : '';
  assert.ok(body.feedback.trim().length >= 8 || separateExplanation.length >= 8,
    'feedback must teach the calculation, not only say correct or incorrect');
  if (typeof explanation === 'string' && explanation.trim()) {
    assert.ok(body.feedback.includes(explanation) || body.explanation === explanation,
      `answer to ${answeredQuestion.id} must return its teaching explanation in feedback or explanation`);
  }
}

function snapshot(body) {
  assert.ok(body && typeof body.gameId === 'string', 'gameId missing');
  assert.ok(Number.isFinite(body.score) && body.score >= 0, 'score must be nonnegative');
  assert.ok(Number.isInteger(body.answered) && body.answered >= 0, 'answered must be an integer');
  assert.ok(Number.isInteger(body.totalQuestions) && body.totalQuestions >= 2 && body.totalQuestions <= 50,
    'totalQuestions must be between 2 and 50');
  assert.ok(['playing', 'paused', 'finished'].includes(body.status), 'invalid game status');
  if (body.status === 'finished') assert.equal(body.question, null, 'finished game must have null question');
  else publicQuestion(body.question);
}

async function main() {
  await check('application startup', async () => {
    const imported = require(path.resolve(process.argv[2]));
    assert.equal(typeof imported.createApp, 'function', 'src/app.js must export createApp');
    createApp = imported.createApp;
    const app = await createApp({dataFile: process.argv[3]});
    assert.ok(app && typeof app.listen === 'function', 'createApp must return an Express app');
    server = await new Promise((resolve, reject) => {
      const instance = app.listen(0, '127.0.0.1', () => resolve(instance));
      instance.once('error', reject);
    });
    base = `http://127.0.0.1:${server.address().port}`;
    request = async (route, options = {}) => {
      const response = await fetch(base + route, {
        ...options,
        headers: {'content-type': 'application/json', ...options.headers},
        signal: AbortSignal.timeout(8000),
      });
      const text = await response.text();
      let body;
      try { body = JSON.parse(text); } catch { body = text; }
      return {status: response.status, headers: response.headers, body, text};
    };
  });
  if (!request) return;

  await check('health', async () => {
    const result = await request('/api/health');
    assert.equal(result.status, 200);
    assert.equal(result.body.status, 'ok');
  });

  await check('browser interface and assets', async () => {
    const result = await request('/');
    assert.equal(result.status, 200, 'root page must load');
    assert.match(result.headers.get('content-type') || '', /text\/html/i);
    assert.match(result.text, /<html[\s>]/i, 'root must serve a full HTML document');
    assert.match(result.text, /<button[\s>]|<input[^>]+type=["'](?:button|submit)/i,
      'interface needs an interactive control');
    const scripts = [...result.text.matchAll(/<script\b[^>]*\bsrc=["']([^"']+)["'][^>]*>/gi)];
    const inlineScript = /<script\b(?![^>]*\bsrc=)[^>]*>[\s\S]*?\S[\s\S]*?<\/script>/i.test(result.text);
    assert.ok(scripts.length || inlineScript, 'interface needs JavaScript for interaction');
    const assets = [...scripts.map(item => item[1]),
      ...[...result.text.matchAll(/<link\b[^>]*href=["']([^"']+\.css(?:\?[^"']*)?)["'][^>]*>/gi)].map(item => item[1])];
    let javascript = inlineScript ? result.text : '';
    for (const asset of assets) {
      const url = new URL(asset, base + '/');
      assert.equal(url.origin, base, 'game assets must be served locally for offline demonstration');
      const resource = await request(url.pathname + url.search);
      assert.equal(resource.status, 200, `asset ${asset} missing`);
      assert.ok(resource.text.trim(), `asset ${asset} is empty`);
      assert.doesNotMatch(resource.headers.get('content-type') || '', /text\/html/i,
        `asset ${asset} returned HTML instead of its contents`);
      if (scripts.some(script => script[1] === asset)) javascript += '\n' + resource.text;
    }
    assert.match(javascript, /fetch\s*\(|XMLHttpRequest|axios/i, 'UI must communicate with the server');
    return `HTML and ${assets.length} local assets available`;
  });

  await check('admin authentication', async () => {
    const denied = await request('/api/admin/questions');
    assert.ok([401, 403].includes(denied.status), 'admin bank exposed without credentials');
    const wrong = await request('/api/admin/questions', {headers: {'x-admin-token': 'incorrect-test-token'}});
    assert.ok([401, 403].includes(wrong.status), 'incorrect admin token accepted');
    const deniedUpdate = await request('/api/admin/questions', {method: 'PUT', body: JSON.stringify({questions: []})});
    assert.ok([401, 403].includes(deniedUpdate.status), 'question updates need authentication');
  });

  await check('question bank', async () => {
    const result = await request('/api/admin/questions', {headers: {'x-admin-token': process.env.ADMIN_TOKEN}});
    assert.equal(result.status, 200, 'configured ADMIN_TOKEN must grant access');
    assert.ok(Array.isArray(result.body.questions) && result.body.questions.length >= 2, 'bank needs multiple questions');
    bank = result.body.questions;
    const ids = new Set();
    for (const item of bank) {
      assert.equal(typeof item.id, 'string');
      assert.ok(!ids.has(item.id), 'question ids must be unique');
      ids.add(item.id);
      assert.ok(typeof item.prompt === 'string' && item.prompt.trim());
      assert.ok(Array.isArray(item.options) && item.options.length >= 2);
      assert.ok(item.options.includes(item.answer), 'correct answer must occur in choices');
      assert.ok(typeof item.explanation === 'string' && item.explanation.trim(),
        'every question needs a teaching explanation');
    }
    const rejected = await request('/api/admin/questions', {
      method: 'PUT', headers: {'x-admin-token': process.env.ADMIN_TOKEN},
      body: JSON.stringify({questions: [{id: 'invalid', prompt: '', options: [], answer: '0'}]}),
    });
    assert.ok([400, 422].includes(rejected.status), 'malformed question bank must be rejected');
    const unchanged = await request('/api/admin/questions', {headers: {'x-admin-token': process.env.ADMIN_TOKEN}});
    assert.deepEqual(unchanged.body.questions, bank, 'invalid update changed the bank');
    const valid = await request('/api/admin/questions', {
      method: 'PUT', headers: {'x-admin-token': process.env.ADMIN_TOKEN},
      body: JSON.stringify({questions: bank}),
    });
    assert.ok([200, 204].includes(valid.status), 'valid question bank update rejected');
    return `${bank.length} validated questions; authenticated updates work`;
  });

  await check('start game', async () => {
    const result = await request('/api/games', {method: 'POST', body: JSON.stringify({playerName: 'Acceptance player'})});
    assert.equal(result.status, 201, 'new game must return HTTP 201');
    snapshot(result.body);
    assert.equal(result.body.score, 0);
    assert.equal(result.body.answered, 0);
    assert.equal(result.body.status, 'playing');
    game = result.body;
    const restored = await request(`/api/games/${encodeURIComponent(game.gameId)}`);
    assert.equal(restored.status, 200);
    snapshot(restored.body);
    assert.equal(restored.body.question.id, game.question.id, 'GET changed current question');
  });

  await check('unknown game', async () => {
    const result = await request('/api/games/nonexistent-acceptance-game');
    assert.equal(result.status, 404);
  });

  await check('invalid answer does not advance', async () => {
    assert.ok(game, 'game did not start');
    const result = await request(`/api/games/${encodeURIComponent(game.gameId)}/answers`, {
      method: 'POST', body: JSON.stringify({answer: '__not_an_option__'}),
    });
    assert.ok([400, 422].includes(result.status), 'unknown choice must be rejected');
    const restored = await request(`/api/games/${encodeURIComponent(game.gameId)}`);
    assert.equal(restored.body.answered, 0);
    assert.equal(restored.body.score, 0);
    assert.equal(restored.body.question.id, game.question.id);
  });

  await check('pause and resume', async () => {
    assert.ok(game, 'game did not start');
    const route = `/api/games/${encodeURIComponent(game.gameId)}`;
    const paused = await request(route + '/pause', {method: 'POST', body: '{}'});
    assert.equal(paused.status, 200);
    assert.equal(paused.body.status, 'paused');
    const blocked = await request(route + '/answers', {
      method: 'POST', body: JSON.stringify({answer: game.question.options[0]}),
    });
    assert.equal(blocked.status, 409, 'paused games must not accept answers');
    const resumed = await request(route + '/resume', {method: 'POST', body: '{}'});
    assert.equal(resumed.status, 200);
    assert.equal(resumed.body.status, 'playing');
    const restored = await request(route);
    assert.equal(restored.status, 200);
    snapshot(restored.body);
    assert.equal(restored.body.answered, 0, 'pause/resume must preserve progress');
    assert.equal(restored.body.question.id, game.question.id);
    game = restored.body;
  });

  await check('correct answer and score', async () => {
    assert.ok(game && bank, 'game or question bank unavailable');
    const answeredQuestion = game.question;
    const oldScore = game.score;
    const oldAnswered = game.answered;
    const result = await request(`/api/games/${encodeURIComponent(game.gameId)}/answers`, {
      method: 'POST', body: JSON.stringify({answer: answerFor(game.question)}),
    });
    assert.equal(result.status, 200);
    assert.equal(result.body.correct, true, 'known correct choice marked incorrect');
    assert.ok(result.body.score > oldScore, 'correct answer must increase score');
    assert.equal(result.body.answered, oldAnswered + 1);
    game = {...game, ...result.body};
    snapshot(game);
    instructionalFeedback(result.body, answeredQuestion);
  });

  await check('incorrect answer feedback', async () => {
    assert.ok(game && game.question && bank, 'second question unavailable');
    const answeredQuestion = game.question;
    const oldScore = game.score;
    const oldAnswered = game.answered;
    const answer = game.question.options.find(option => option !== answerFor(game.question));
    assert.ok(answer, 'question lacks incorrect choices');
    const result = await request(`/api/games/${encodeURIComponent(game.gameId)}/answers`, {
      method: 'POST', body: JSON.stringify({answer}),
    });
    assert.equal(result.status, 200);
    assert.equal(result.body.correct, false);
    assert.ok(result.body.score <= oldScore, 'incorrect answer must not award points');
    assert.equal(result.body.answered, oldAnswered + 1);
    game = {...game, ...result.body};
    snapshot(game);
    instructionalFeedback(result.body, answeredQuestion);
  });

  await check('complete round', async () => {
    assert.ok(game && bank, 'game or question bank unavailable');
    let attempts = 0;
    const feedbackChecks = [];
    while (game.status !== 'finished' && attempts++ < 50) {
      const answeredQuestion = game.question;
      const oldAnswered = game.answered;
      const result = await request(`/api/games/${encodeURIComponent(game.gameId)}/answers`, {
        method: 'POST', body: JSON.stringify({answer: answerFor(game.question)}),
      });
      assert.equal(result.status, 200);
      assert.equal(result.body.correct, true);
      assert.equal(result.body.answered, oldAnswered + 1);
      game = {...game, ...result.body};
      snapshot(game);
      feedbackChecks.push([result.body, answeredQuestion]);
    }
    assert.equal(game.status, 'finished', 'round never finished');
    assert.equal(game.answered, game.totalQuestions);
    assert.equal(game.question, null);
    const extra = await request(`/api/games/${encodeURIComponent(game.gameId)}/answers`, {
      method: 'POST', body: JSON.stringify({answer: '1/2'}),
    });
    assert.ok([400, 409, 422].includes(extra.status), 'finished round accepted another answer');
    const restored = await request(`/api/games/${encodeURIComponent(game.gameId)}`);
    assert.equal(restored.body.status, 'finished');
    assert.equal(restored.body.score, game.score);
    for (const [response, question] of feedbackChecks) instructionalFeedback(response, question);
    return `${game.answered} questions completed; score ${game.score}`;
  });

  await check('leaderboard', async () => {
    assert.ok(game && game.status === 'finished', 'completed game unavailable');
    const result = await request('/api/leaderboard');
    assert.equal(result.status, 200);
    assert.ok(Array.isArray(result.body.entries), 'leaderboard needs entries array');
    const entry = result.body.entries.find(item => item.gameId === game.gameId);
    assert.ok(entry, 'finished game missing from leaderboard');
    assert.equal(entry.score, game.score);
  });

  await check('help', async () => {
    const result = await request('/api/help');
    assert.equal(result.status, 200);
    assert.ok(typeof result.body.text === 'string' && result.body.text.trim(), 'help text missing');
  });

  await check('persistent game and leaderboard', async () => {
    assert.ok(game && game.status === 'finished', 'completed game unavailable');
    assert.ok(fs.existsSync(process.argv[3]) && fs.statSync(process.argv[3]).size > 0,
      'app must write game state to the configured dataFile');
    await new Promise((resolve, reject) => {
      server.close(error => error ? reject(error) : resolve());
      if (server.closeAllConnections) server.closeAllConnections();
    });
    const reopenedApp = await createApp({dataFile: process.argv[3]});
    server = await new Promise((resolve, reject) => {
      const instance = reopenedApp.listen(0, '127.0.0.1', () => resolve(instance));
      instance.once('error', reject);
    });
    base = `http://127.0.0.1:${server.address().port}`;
    const restored = await request(`/api/games/${encodeURIComponent(game.gameId)}`);
    assert.equal(restored.status, 200, 'saved game missing after app restart');
    snapshot(restored.body);
    assert.equal(restored.body.gameId, game.gameId);
    assert.equal(restored.body.status, 'finished');
    assert.equal(restored.body.score, game.score, 'saved score lost after app restart');
    assert.equal(restored.body.answered, game.answered);
    const board = await request('/api/leaderboard');
    assert.equal(board.status, 200);
    assert.ok(Array.isArray(board.body.entries));
    const entries = board.body.entries.filter(entry => entry.gameId === game.gameId);
    assert.equal(entries.length, 1, 'saved game must occur exactly once on restored leaderboard');
    assert.equal(entries[0].score, game.score);
    const questions = await request('/api/admin/questions', {headers: {'x-admin-token': process.env.ADMIN_TOKEN}});
    assert.equal(questions.status, 200);
    assert.deepEqual(questions.body.questions, bank, 'question bank changed after app restart');
    return 'Completed game, score, question bank and leaderboard survive reopening the same data file';
  });
}

main().catch(error => {
  checks.push({name: 'probe execution', passed: false, detail: String(error.stack || error).slice(0, 1600)});
}).finally(() => {
  if (server) {
    server.close();
    if (server.closeAllConnections) server.closeAllConnections();
  }
  const passed = checks.length >= 15 && checks.every(check => check.passed);
  console.log('__AGENT_ACCEPTANCE__' + JSON.stringify({passed, checks}));
  process.exitCode = passed ? 0 : 1;
});
"""


def _failure(name: str, detail: str, output: str = "") -> dict[str, Any]:
    return {"passed": False, "checks": [{"name": name, "passed": False, "detail": detail}], "output": output[-16000:]}


def _text(value: str | bytes | None) -> str:
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return value or ""


def run_acceptance(project_directory: Path, timeout: int = 120) -> dict[str, Any]:
    """Run independent Node/HTTP checks; missing tools or empty results fail closed."""
    project_directory = Path(project_directory).resolve()
    application = project_directory / "src" / "app.js"
    if not application.is_file():
        return _failure("application entry", "Generated project is missing src/app.js")
    node = shutil.which("node")
    if not node:
        return _failure("Node.js runtime", "Node.js 18 or newer is required; node was not found in PATH")
    environment = dict(os.environ)
    environment.update({"ADMIN_TOKEN": "agent-acceptance-admin-only", "NODE_ENV": "test", "PORT": "0"})
    # The generated program does not need credentials used to generate it.
    for credential in ("DEEPSEEK_API_KEY", "OPENAI_API_KEY"):
        environment.pop(credential, None)
    try:
        with tempfile.TemporaryDirectory(prefix="fraction-game-acceptance-") as temporary:
            completed = subprocess.run(
                [node, "-", str(application), str(Path(temporary) / "game-data.json")],
                input=_PROBE,
                cwd=project_directory,
                env=environment,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=timeout,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                check=False,
            )
    except subprocess.TimeoutExpired as error:
        return _failure("acceptance timeout", f"Game checks did not finish within {timeout} seconds",
                        _text(error.stdout) + "\n" + _text(error.stderr))
    except OSError as error:
        return _failure("acceptance execution", str(error))

    output = (completed.stdout + "\n" + completed.stderr).strip()
    protocol_lines = [line[len(_MARKER):] for line in completed.stdout.splitlines() if line.startswith(_MARKER)]
    if not protocol_lines:
        return _failure("acceptance result", "Probe did not produce a structured acceptance result", output)
    try:
        result = json.loads(protocol_lines[-1])
        checks = result["checks"]
        valid = isinstance(checks, list) and checks and all(
            isinstance(check, dict)
            and isinstance(check.get("name"), str)
            and isinstance(check.get("passed"), bool)
            and isinstance(check.get("detail"), str)
            for check in checks
        )
        if not valid:
            raise ValueError("empty or malformed check list")
        names = {check["name"] for check in checks}
        missing = sorted(_REQUIRED_CHECKS - names)
        if missing:
            checks.append({"name": "acceptance completeness", "passed": False,
                           "detail": "Checks did not run: " + ", ".join(missing)})
        passed = result.get("passed") is True and all(check["passed"] for check in checks)
        if completed.returncode != 0 and passed:
            checks.append({"name": "process exit", "passed": False,
                           "detail": f"Node process exited with code {completed.returncode}"})
            passed = False
        return {"passed": passed, "checks": checks, "output": output[-16000:]}
    except (json.JSONDecodeError, KeyError, TypeError, ValueError) as error:
        return _failure("acceptance result", f"Malformed acceptance result: {error}", output)
