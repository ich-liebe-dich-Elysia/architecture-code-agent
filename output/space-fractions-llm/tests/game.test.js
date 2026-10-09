'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const { createApp } = require('../src/app');

function tempDataFile() {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'space-fractions-'));
  return path.join(dir, 'store.json');
}

async function startServer(dataFile) {
  const app = createApp({ dataFile });
  const server = await new Promise((resolve) => {
    const s = app.listen(0, '127.0.0.1', () => resolve(s));
  });
  const { port } = server.address();
  return { server, base: 'http://127.0.0.1:' + port };
}

async function stopServer(server) {
  await new Promise((resolve) => server.close(resolve));
}

async function jsonFetch(base, url, options) {
  const res = await fetch(base + url, options);
  let body = null;
  try {
    body = await res.json();
  } catch (err) {
    body = null;
  }
  return { status: res.status, body };
}

function postJson(base, url, payload, headers) {
  return jsonFetch(base, url, {
    method: 'POST',
    headers: Object.assign({ 'content-type': 'application/json' }, headers || {}),
    body: JSON.stringify(payload || {})
  });
}

async function startGame(base, playerName) {
  const res = await postJson(base, '/api/games', { playerName: playerName || '测试学员' });
  assert.equal(res.status, 201);
  return res.body;
}

// 通过题库接口拿到正确答案，用于构造正确/错误作答。
async function correctAnswerFor(base, questionId) {
  const res = await jsonFetch(base, '/api/admin/questions', {
    headers: { 'x-admin-token': 'space-fractions-admin' }
  });
  assert.equal(res.status, 200);
  const q = res.body.questions.find((item) => item.id === questionId);
  assert.ok(q, '题库中应存在题目 ' + questionId);
  return q.answer;
}

// 公开快照不含 answer，必须借助题库接口找出一个真正的错误选项。
async function wrongAnswerFor(base, question) {
  const correct = await correctAnswerFor(base, question.id);
  const wrong = question.options.find((opt) => opt !== correct);
  assert.ok(wrong, '应能找到一个与正确答案不同的选项');
  return wrong;
}

test('健康检查返回 ok', async () => {
  const dataFile = tempDataFile();
  const { server, base } = await startServer(dataFile);
  try {
    const res = await jsonFetch(base, '/api/health');
    assert.equal(res.status, 200);
    assert.deepEqual(res.body, { status: 'ok' });
    const alias = await jsonFetch(base, '/health');
    assert.equal(alias.status, 200);
    assert.equal(alias.body.status, 'ok');
  } finally {
    await stopServer(server);
  }
});

test('开始游戏返回公开快照且不泄露答案', async () => {
  const dataFile = tempDataFile();
  const { server, base } = await startServer(dataFile);
  try {
    const game = await startGame(base, '小明');
    assert.equal(typeof game.gameId, 'string');
    assert.equal(game.score, 0);
    assert.equal(game.totalQuestions, 5);
    assert.equal(game.answered, 0);
    assert.equal(game.status, 'playing');
    assert.equal(game.playerName, '小明');
    assert.ok(game.question);
    assert.equal(game.question.answer, undefined);
    assert.equal(game.question.explanation, undefined);
    assert.equal(game.question.options.length, 4);

    const bad = await postJson(base, '/api/games', { playerName: 123 });
    assert.equal(bad.status, 400);
    assert.ok(bad.body.error);

    const tooLong = await postJson(base, '/api/games', { playerName: 'x'.repeat(50) });
    assert.equal(tooLong.status, 400);

    const unknown = await jsonFetch(base, '/api/games/does-not-exist');
    assert.equal(unknown.status, 404);
  } finally {
    await stopServer(server);
  }
});

test('答对得分并推进到下一题', async () => {
  const dataFile = tempDataFile();
  const { server, base } = await startServer(dataFile);
  try {
    const game = await startGame(base);
    const answer = await correctAnswerFor(base, game.question.id);
    const res = await postJson(base, '/api/games/' + game.gameId + '/answers', {
      answer,
      questionId: game.question.id
    });
    assert.equal(res.status, 200);
    assert.equal(res.body.correct, true);
    assert.equal(res.body.score, 10);
    assert.equal(res.body.answered, 1);
    assert.equal(res.body.status, 'playing');
    assert.ok(res.body.question);
    assert.notEqual(res.body.question.id, game.question.id);
    assert.equal(typeof res.body.correctAnswer, 'string');
    assert.equal(typeof res.body.feedback, 'string');
  } finally {
    await stopServer(server);
  }
});

test('错误答案与非法答案处理', async () => {
  const dataFile = tempDataFile();
  const { server, base } = await startServer(dataFile);
  try {
    const game = await startGame(base);
    const wrong = await wrongAnswerFor(base, game.question);
    const res = await postJson(base, '/api/games/' + game.gameId + '/answers', {
      answer: wrong,
      questionId: game.question.id
    });
    assert.equal(res.status, 200);
    assert.equal(res.body.correct, false);
    assert.equal(res.body.score, 0);
    assert.equal(res.body.answered, 1);

    const missing = await postJson(base, '/api/games/' + game.gameId + '/answers', {});
    assert.equal(missing.status, 400);

    const invalid = await postJson(base, '/api/games/' + game.gameId + '/answers', {
      answer: '不存在的选项'
    });
    assert.equal(invalid.status, 400);

    const stale = await postJson(base, '/api/games/' + game.gameId + '/answers', {
      answer: game.question.options[0],
      questionId: game.question.id
    });
    assert.equal(stale.status, 409);

    const after = await jsonFetch(base, '/api/games/' + game.gameId);
    assert.equal(after.body.answered, 1);
    assert.equal(after.body.score, 0);
  } finally {
    await stopServer(server);
  }
});

test('暂停与恢复的状态转换', async () => {
  const dataFile = tempDataFile();
  const { server, base } = await startServer(dataFile);
  try {
    const game = await startGame(base);
    const paused = await postJson(base, '/api/games/' + game.gameId + '/pause', {});
    assert.equal(paused.status, 200);
    assert.equal(paused.body.status, 'paused');

    const doublePause = await postJson(base, '/api/games/' + game.gameId + '/pause', {});
    assert.equal(doublePause.status, 409);

    const answerWhilePaused = await postJson(base, '/api/games/' + game.gameId + '/answers', {
      answer: game.question.options[0]
    });
    assert.equal(answerWhilePaused.status, 409);

    const resumed = await postJson(base, '/api/games/' + game.gameId + '/resume', {});
    assert.equal(resumed.status, 200);
    assert.equal(resumed.body.status, 'playing');

    const doubleResume = await postJson(base, '/api/games/' + game.gameId + '/resume', {});
    assert.equal(doubleResume.status, 409);
  } finally {
    await stopServer(server);
  }
});

test('完成全部题目后进入排行榜', async () => {
  const dataFile = tempDataFile();
  const { server, base } = await startServer(dataFile);
  try {
    const game = await startGame(base, '冠军');
    let current = game.question;
    let last = null;
    for (let i = 0; i < 5; i += 1) {
      const answer = await correctAnswerFor(base, current.id);
      const res = await postJson(base, '/api/games/' + game.gameId + '/answers', {
        answer,
        questionId: current.id
      });
      assert.equal(res.status, 200);
      assert.equal(res.body.correct, true);
      last = res.body;
      current = res.body.question;
    }
    assert.equal(last.status, 'finished');
    assert.equal(last.question, null);
    assert.equal(last.score, 50);
    assert.equal(last.answered, 5);

    const finishedAnswer = await postJson(base, '/api/games/' + game.gameId + '/answers', {
      answer: '任意'
    });
    assert.equal(finishedAnswer.status, 409);

    const board = await jsonFetch(base, '/api/leaderboard');
    assert.equal(board.status, 200);
    assert.ok(Array.isArray(board.body.entries));
    const entry = board.body.entries.find((e) => e.gameId === game.gameId);
    assert.ok(entry);
    assert.equal(entry.score, 50);
    assert.equal(entry.playerName, '冠军');
    assert.equal(entry.totalQuestions, 5);
  } finally {
    await stopServer(server);
  }
});

test('数据持久化与损坏检测', async () => {
  const dataFile = tempDataFile();
  const first = await startServer(dataFile);
  let gameId;
  try {
    const game = await startGame(first.base, '持久者');
    gameId = game.gameId;
  } finally {
    await stopServer(first.server);
  }

  const second = await startServer(dataFile);
  try {
    const res = await jsonFetch(second.base, '/api/games/' + gameId);
    assert.equal(res.status, 200);
    assert.equal(res.body.playerName, '持久者');
    assert.equal(res.body.status, 'playing');
  } finally {
    await stopServer(second.server);
  }

  fs.writeFileSync(dataFile, '{ 这不是合法 JSON', 'utf8');
  assert.throws(() => createApp({ dataFile }), /损坏|无效/);
});

test('管理员题库接口鉴权与校验', async () => {
  const dataFile = tempDataFile();
  const { server, base } = await startServer(dataFile);
  try {
    const noToken = await jsonFetch(base, '/api/admin/questions');
    assert.equal(noToken.status, 401);

    const badToken = await jsonFetch(base, '/api/admin/questions', {
      headers: { 'x-admin-token': 'wrong' }
    });
    assert.equal(badToken.status, 403);

    const ok = await jsonFetch(base, '/api/admin/questions', {
      headers: { 'x-admin-token': 'space-fractions-admin' }
    });
    assert.equal(ok.status, 200);
    assert.ok(ok.body.questions.length >= 10);

    const invalidBank = await jsonFetch(base, '/api/admin/questions', {
      method: 'PUT',
      headers: { 'content-type': 'application/json', 'x-admin-token': 'space-fractions-admin' },
      body: JSON.stringify({ questions: [{ id: 'x' }] })
    });
    assert.equal(invalidBank.status, 400);

    const stillThere = await jsonFetch(base, '/api/admin/questions', {
      headers: { 'x-admin-token': 'space-fractions-admin' }
    });
    assert.ok(stillThere.body.questions.length >= 10);

    const newBank = ok.body.questions.slice(0, 5).map((q, i) => ({
      id: 'custom-' + i,
      prompt: '自定义题目 ' + i,
      options: ['A', 'B', 'C', 'D'],
      answer: 'A',
      explanation: '自定义解析 ' + i
    }));
    const updated = await jsonFetch(base, '/api/admin/questions', {
      method: 'PUT',
      headers: { 'content-type': 'application/json', 'x-admin-token': 'space-fractions-admin' },
      body: JSON.stringify({ questions: newBank })
    });
    assert.equal(updated.status, 200);
    assert.equal(updated.body.questions.length, 5);
    assert.equal(updated.body.questions[0].id, 'custom-0');
  } finally {
    await stopServer(server);
  }
});
