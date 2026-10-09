'use strict';

const express = require('express');
const fs = require('fs');
const path = require('path');
const crypto = require('crypto');
const { initialQuestions } = require('./questions');

const TOTAL_QUESTIONS = 5;
const POINTS_PER_CORRECT = 10;
const MAX_PLAYER_NAME = 24;
const MAX_LEADERBOARD = 20;
const DEFAULT_ADMIN_TOKEN = 'space-fractions-admin';

function adminToken() {
  return process.env.ADMIN_TOKEN || DEFAULT_ADMIN_TOKEN;
}

function defaultDataFile() {
  return process.env.DATA_FILE || path.join(__dirname, '..', 'data', 'store.json');
}

function clone(value) {
  return JSON.parse(JSON.stringify(value));
}

function isPlainObject(value) {
  return value !== null && typeof value === 'object' && !Array.isArray(value);
}

function boundedString(value, min, max) {
  return typeof value === 'string' && value.trim().length >= min && value.trim().length <= max;
}

function validateQuestionBank(bank) {
  if (!Array.isArray(bank)) return '题库必须是数组';
  if (bank.length < 5 || bank.length > 100) return '题库数量必须在 5 到 100 之间';
  const ids = new Set();
  for (const q of bank) {
    if (!isPlainObject(q)) return '题目必须是对象';
    if (!boundedString(q.id, 1, 64)) return '题目 id 非法';
    if (ids.has(q.id)) return '题目 id 重复：' + q.id;
    ids.add(q.id);
    if (!boundedString(q.prompt, 1, 500)) return '题目题干非法';
    if (!boundedString(q.explanation, 1, 1000)) return '题目解析非法';
    if (!Array.isArray(q.options) || q.options.length !== 4) return '每题必须有 4 个选项';
    const opts = new Set();
    for (const opt of q.options) {
      if (!boundedString(opt, 1, 120)) return '选项必须是 1-120 字符的字符串';
      if (opts.has(opt)) return '选项必须互不相同';
      opts.add(opt);
    }
    if (typeof q.answer !== 'string' || !opts.has(q.answer)) return '答案必须是选项之一';
  }
  return null;
}

function publicQuestion(q) {
  return { id: q.id, prompt: q.prompt, options: q.options.slice() };
}

function createStore(dataFile) {
  const file = dataFile || defaultDataFile();
  let state = null;

  function load() {
    if (fs.existsSync(file)) {
      const raw = fs.readFileSync(file, 'utf8');
      let parsed;
      try {
        parsed = JSON.parse(raw);
      } catch (err) {
        throw new Error('数据文件已损坏，无法解析 JSON：' + file);
      }
      if (!isPlainObject(parsed) || !Array.isArray(parsed.questions) || !Array.isArray(parsed.games) || !Array.isArray(parsed.leaderboard)) {
        throw new Error('数据文件结构无效：' + file);
      }
      const problem = validateQuestionBank(parsed.questions);
      if (problem) throw new Error('数据文件中的题库无效：' + problem);
      state = parsed;
    } else {
      state = { questions: clone(initialQuestions), games: [], leaderboard: [] };
      persist();
    }
  }

  function persist() {
    const dir = path.dirname(file);
    fs.mkdirSync(dir, { recursive: true });
    const tmp = file + '.tmp-' + process.pid + '-' + Date.now() + '-' + crypto.randomBytes(4).toString('hex');
    fs.writeFileSync(tmp, JSON.stringify(state, null, 2), 'utf8');
    fs.renameSync(tmp, file);
  }

  load();

  return {
    file,
    get questions() { return state.questions; },
    get games() { return state.games; },
    get leaderboard() { return state.leaderboard; },
    setQuestions(bank) {
      const previous = state.questions;
      state.questions = clone(bank);
      try {
        persist();
      } catch (err) {
        state.questions = previous;
        throw err;
      }
    },
    addGame(game) {
      state.games.push(game);
      try {
        persist();
      } catch (err) {
        state.games.pop();
        throw err;
      }
    },
    // 原子提交：游戏状态与排行榜条目在同一次文件写入中完成，
    // 写入失败时回滚内存中的游戏与排行榜，避免出现“已计分但未上榜”的半完成状态。
    commitGame(game, leaderboardEntry) {
      const idx = state.games.findIndex((g) => g.gameId === game.gameId);
      const previousGame = idx >= 0 ? state.games[idx] : null;
      if (idx >= 0) state.games[idx] = game;
      else state.games.push(game);
      if (leaderboardEntry) state.leaderboard.push(leaderboardEntry);
      try {
        persist();
      } catch (err) {
        if (idx >= 0) state.games[idx] = previousGame;
        else state.games.pop();
        if (leaderboardEntry) state.leaderboard.pop();
        throw err;
      }
    }
  };
}

function pickQuestions(bank, count) {
  const pool = bank.slice();
  const picked = [];
  while (picked.length < count && pool.length > 0) {
    const idx = crypto.randomInt(0, pool.length);
    picked.push(pool.splice(idx, 1)[0]);
  }
  return picked;
}

function snapshot(game) {
  const current = game.questions[game.answered] || null;
  return {
    gameId: game.gameId,
    question: current ? publicQuestion(current) : null,
    score: game.score,
    totalQuestions: game.questions.length,
    answered: game.answered,
    status: game.status,
    playerName: game.playerName
  };
}

function createApp(options = {}) {
  const store = createStore(options.dataFile);
  const app = express();
  app.disable('x-powered-by');
  app.use(express.json({ limit: '128kb' }));

  app.use((err, req, res, next) => {
    if (err && err.type === 'entity.parse.failed') {
      return res.status(400).json({ error: '请求体不是合法的 JSON' });
    }
    if (err && err.type === 'entity.too.large') {
      return res.status(400).json({ error: '请求体过大' });
    }
    return next(err);
  });

  function requireAdmin(req, res, next) {
    const token = req.get('x-admin-token');
    if (!token) return res.status(401).json({ error: '缺少管理员令牌' });
    if (token !== adminToken()) return res.status(403).json({ error: '管理员令牌无效' });
    return next();
  }

  function findGame(id) {
    return store.games.find((g) => g.gameId === id) || null;
  }

  function startGame(playerName) {
    const questions = pickQuestions(store.questions, TOTAL_QUESTIONS);
    const game = {
      gameId: crypto.randomUUID(),
      playerName,
      questions: clone(questions),
      score: 0,
      answered: 0,
      status: 'playing',
      createdAt: new Date().toISOString()
    };
    store.addGame(game);
    return game;
  }

  app.get('/api/health', (req, res) => res.json({ status: 'ok' }));
  app.get('/health', (req, res) => res.json({ status: 'ok' }));

  app.post('/api/games', (req, res) => {
    const body = isPlainObject(req.body) ? req.body : {};
    let playerName = body.playerName;
    if (playerName === undefined || playerName === null) playerName = '星际学员';
    if (typeof playerName !== 'string') {
      return res.status(400).json({ error: 'playerName 必须是字符串' });
    }
    playerName = playerName.trim();
    if (playerName.length < 1 || playerName.length > MAX_PLAYER_NAME) {
      return res.status(400).json({ error: 'playerName 长度必须在 1 到 ' + MAX_PLAYER_NAME + ' 之间' });
    }
    try {
      const game = startGame(playerName);
      return res.status(201).json(snapshot(game));
    } catch (err) {
      return res.status(500).json({ error: '无法保存游戏数据' });
    }
  });

  app.get('/play', (req, res) => {
    const raw = typeof req.query.playerName === 'string' ? req.query.playerName : '星际学员';
    const playerName = raw.trim();
    if (playerName.length < 1 || playerName.length > MAX_PLAYER_NAME) {
      return res.status(400).json({ error: 'playerName 长度必须在 1 到 ' + MAX_PLAYER_NAME + ' 之间' });
    }
    try {
      const game = startGame(playerName);
      return res.status(201).json(snapshot(game));
    } catch (err) {
      return res.status(500).json({ error: '无法保存游戏数据' });
    }
  });

  app.get('/api/games/:id', (req, res) => {
    const game = findGame(req.params.id);
    if (!game) return res.status(404).json({ error: '未找到该游戏' });
    return res.json(snapshot(game));
  });

  app.get('/scores/:id', (req, res) => {
    const game = findGame(req.params.id);
    if (!game) return res.status(404).json({ error: '未找到该游戏' });
    return res.json(snapshot(game));
  });

  app.post('/api/games/:id/answers', (req, res) => {
    const game = findGame(req.params.id);
    if (!game) return res.status(404).json({ error: '未找到该游戏' });
    if (game.status === 'paused') return res.status(409).json({ error: '游戏已暂停，请先恢复' });
    if (game.status === 'finished') return res.status(409).json({ error: '游戏已结束' });

    const body = isPlainObject(req.body) ? req.body : {};
    const answer = body.answer;
    if (typeof answer !== 'string' || answer.trim().length === 0) {
      return res.status(400).json({ error: 'answer 必须是非空字符串' });
    }
    const current = game.questions[game.answered];
    if (!current) return res.status(409).json({ error: '没有待作答的题目' });
    if (body.questionId !== undefined && body.questionId !== null && body.questionId !== current.id) {
      return res.status(409).json({ error: '题目已过期，请使用当前题目作答' });
    }
    if (!current.options.includes(answer)) {
      return res.status(400).json({ error: 'answer 必须是当前题目的选项之一' });
    }

    const correct = answer === current.answer;
    const previousScore = game.score;
    const previousAnswered = game.answered;
    const previousStatus = game.status;

    if (correct) game.score += POINTS_PER_CORRECT;
    game.answered += 1;

    let finished = false;
    if (game.answered >= game.questions.length) {
      game.status = 'finished';
      finished = true;
    }

    const entry = finished
      ? {
          gameId: game.gameId,
          playerName: game.playerName,
          score: game.score,
          totalQuestions: game.questions.length,
          finishedAt: new Date().toISOString()
        }
      : null;

    try {
      store.commitGame(game, entry);
    } catch (err) {
      game.score = previousScore;
      game.answered = previousAnswered;
      game.status = previousStatus;
      return res.status(500).json({ error: '无法保存游戏数据' });
    }

    const next = finished ? null : publicQuestion(game.questions[game.answered]);
    return res.json({
      gameId: game.gameId,
      correct,
      score: game.score,
      answered: game.answered,
      totalQuestions: game.questions.length,
      status: game.status,
      question: next,
      feedback: correct ? '回答正确！' : '回答错误。',
      correctAnswer: current.answer,
      explanation: current.explanation
    });
  });

  app.post('/api/games/:id/pause', (req, res) => {
    const game = findGame(req.params.id);
    if (!game) return res.status(404).json({ error: '未找到该游戏' });
    if (game.status !== 'playing') return res.status(409).json({ error: '当前状态无法暂停' });
    const previous = game.status;
    game.status = 'paused';
    try {
      store.commitGame(game, null);
    } catch (err) {
      game.status = previous;
      return res.status(500).json({ error: '无法保存游戏数据' });
    }
    return res.json(snapshot(game));
  });

  app.post('/api/games/:id/resume', (req, res) => {
    const game = findGame(req.params.id);
    if (!game) return res.status(404).json({ error: '未找到该游戏' });
    if (game.status !== 'paused') return res.status(409).json({ error: '当前状态无法恢复' });
    const previous = game.status;
    game.status = 'playing';
    try {
      store.commitGame(game, null);
    } catch (err) {
      game.status = previous;
      return res.status(500).json({ error: '无法保存游戏数据' });
    }
    return res.json(snapshot(game));
  });

  app.get('/api/help', (req, res) => {
    res.json({
      text: [
        '《星际分数探索》玩法说明：',
        '1. 输入你的名字后点击“开始探索”，系统会随机抽取 5 道分数题。',
        '2. 每题有 4 个选项，点击选项后按“提交答案”。答对得 10 分，答错不得分。',
        '3. 提交后会显示正确答案与解析，点击“下一题”继续；5 题完成后显示最终成绩。',
        '4. 中途可以暂停，刷新页面后会自动恢复未完成的游戏。',
        '',
        '分数小技巧：',
        '· 比较分数先通分，分母相同看分子。',
        '· 等值分数：分子分母同时乘或除以同一个非零数。',
        '· 加减法先通分，分母不变，分子相加减。',
        '· 乘法：分子乘分子、分母乘分母，最后约分。',
        '· 除法：除以一个分数等于乘它的倒数。'
      ].join('\n')
    });
  });

  app.get('/api/leaderboard', (req, res) => {
    const entries = store.leaderboard
      .slice()
      .sort((a, b) => b.score - a.score || String(a.finishedAt).localeCompare(String(b.finishedAt)))
      .slice(0, MAX_LEADERBOARD);
    return res.json({ entries });
  });

  app.get('/api/admin/questions', requireAdmin, (req, res) => {
    return res.json({ questions: clone(store.questions) });
  });

  app.put('/api/admin/questions', requireAdmin, (req, res) => {
    const body = isPlainObject(req.body) ? req.body : {};
    const problem = validateQuestionBank(body.questions);
    if (problem) return res.status(400).json({ error: problem });
    try {
      store.setQuestions(body.questions);
    } catch (err) {
      return res.status(500).json({ error: '无法保存题库' });
    }
    return res.json({ questions: clone(store.questions) });
  });

  const publicDir = path.join(__dirname, '..', 'public');
  app.use(express.static(publicDir));
  app.get('/', (req, res) => res.sendFile(path.join(publicDir, 'index.html')));

  app.use((req, res) => res.status(404).json({ error: '未找到该资源' }));

  app.use((err, req, res, next) => {
    if (res.headersSent) return next(err);
    return res.status(500).json({ error: '服务器内部错误' });
  });

  return app;
}

if (require.main === module) {
  const port = Number(process.env.PORT) || 3000;
  const host = process.env.HOST || '127.0.0.1';
  const app = createApp();
  app.listen(port, host, () => {
    console.log('星际分数探索已启动：http://' + host + ':' + port);
  });
}

module.exports = { createApp };
