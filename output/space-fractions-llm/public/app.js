'use strict';

(function () {
  var STORAGE_KEY = 'space-fractions-game-id';
  var TOKEN_KEY = 'space-fractions-admin-token';

  var state = {
    gameId: null,
    snapshot: null,
    selected: null,
    pending: false,
    awaitingNext: false,
    lastResult: null,
    adminToken: '',
    screen: 'home'
  };

  function $(id) { return document.getElementById(id); }

  function show(el) { if (el) el.hidden = false; }
  function hide(el) { if (el) el.hidden = true; }

  function setText(el, text) {
    if (el) el.textContent = text == null ? '' : String(text);
  }

  function showError(el, message) {
    if (!el) return;
    setText(el, message);
    show(el);
  }

  function clearError(el) {
    if (!el) return;
    setText(el, '');
    hide(el);
  }

  function api(path, options) {
    var opts = options || {};
    var headers = Object.assign({ 'content-type': 'application/json' }, opts.headers || {});
    return fetch(path, {
      method: opts.method || 'GET',
      headers: headers,
      body: opts.body === undefined ? undefined : JSON.stringify(opts.body)
    }).then(function (res) {
      return res.json().catch(function () { return {}; }).then(function (body) {
        if (!res.ok) {
          var err = new Error((body && body.error) || ('请求失败（' + res.status + '）'));
          err.status = res.status;
          err.body = body;
          throw err;
        }
        return body;
      });
    });
  }

  var screens = {
    home: $('screen-home'),
    game: $('screen-game'),
    results: $('screen-results'),
    board: $('screen-board'),
    admin: $('screen-admin')
  };

  function showScreen(name) {
    state.screen = name;
    Object.keys(screens).forEach(function (key) {
      if (!screens[key]) return;
      if (key === name) show(screens[key]);
      else hide(screens[key]);
    });
    if (name !== 'game') hide($('pause-overlay'));
    if (name === 'home') refreshResumeButton();
  }

  function overlayOpen() {
    var pause = $('pause-overlay');
    var help = $('help-overlay');
    return (pause && !pause.hidden) || (help && !help.hidden);
  }

  function refreshResumeButton() {
    var btn = $('home-resume-game');
    if (!btn) return;
    var id = state.gameId;
    if (!id) {
      try { id = localStorage.getItem(STORAGE_KEY); } catch (e) { id = null; }
    }
    if (id) {
      state.gameId = id;
      show(btn);
    } else {
      hide(btn);
    }
  }

  function setScore(value) {
    var el = $('score');
    if (el) el.textContent = String(value);
  }

  function setProgress(answered, total) {
    var chip = $('progress-chip');
    var fill = $('progress-fill');
    var shown = Math.min(answered + 1, total);
    setText(chip, '第 ' + shown + ' / ' + total + ' 题');
    if (fill) fill.style.width = Math.round((answered / total) * 100) + '%';
  }

  function renderOptions(question) {
    var box = $('options');
    if (!box) return;
    box.textContent = '';
    state.selected = null;
    if (!question) return;
    question.options.forEach(function (option, index) {
      var btn = document.createElement('button');
      btn.type = 'button';
      btn.className = 'option';
      btn.setAttribute('data-testid', 'answer-option');
      btn.setAttribute('data-option', option);
      var key = document.createElement('span');
      key.className = 'key';
      key.textContent = String(index + 1);
      var label = document.createElement('span');
      label.textContent = option;
      btn.appendChild(key);
      btn.appendChild(label);
      btn.addEventListener('click', function () { selectOption(option, btn); });
      box.appendChild(btn);
    });
  }

  function selectOption(option, btn) {
    if (state.pending || state.awaitingNext) return;
    state.selected = option;
    var box = $('options');
    if (!box) return;
    Array.prototype.forEach.call(box.querySelectorAll('.option'), function (el) {
      el.classList.toggle('selected', el === btn);
    });
  }

  function renderQuestion(question) {
    setText($('question'), question ? question.prompt : '正在加载题目…');
    renderOptions(question);
  }

  function renderSnapshot(snap) {
    state.snapshot = snap;
    state.gameId = snap.gameId;
    try { localStorage.setItem(STORAGE_KEY, snap.gameId); } catch (e) { /* 忽略存储异常 */ }
    setText($('player-chip'), snap.playerName || '星际学员');
    setScore(snap.score);
    setProgress(snap.answered, snap.totalQuestions);
    renderQuestion(snap.question);
    hide($('feedback'));
    hide($('next-question'));
    show($('submit-answer'));
    show($('pause-game'));
    state.awaitingNext = false;
    state.pending = false;
    if (snap.status === 'paused') show($('pause-overlay'));
    else hide($('pause-overlay'));
    showScreen('game');
  }

  function renderFeedback(result) {
    var box = $('feedback');
    if (!box) return;
    box.textContent = '';
    box.classList.toggle('good', !!result.correct);
    box.classList.toggle('bad', !result.correct);
    var title = document.createElement('h3');
    title.textContent = result.correct ? '回答正确！+10 分' : '回答错误，本题不得分';
    var answerLine = document.createElement('p');
    answerLine.className = 'answer-line';
    answerLine.textContent = '正确答案：' + result.correctAnswer;
    var tip = document.createElement('p');
    tip.className = 'explanation-line';
    tip.textContent = result.explanation || (result.correct
      ? '继续保持，下一题也要看清分母哦。'
      : '别灰心，记住通分和约分的方法，下一题一定可以。');
    box.appendChild(title);
    box.appendChild(answerLine);
    box.appendChild(tip);
    show(box);
  }

  function renderResults(snap) {
    setText($('results-score'), snap.score);
    var line = '你完成了 ' + snap.totalQuestions + ' 道题，答对 ' + (snap.score / 10) + ' 道。';
    if (snap.score === snap.totalQuestions * 10) line += '满分！你就是分数舰长。';
    else if (snap.score >= snap.totalQuestions * 10 * 0.6) line += '表现不错，再练一局冲击满分吧。';
    else line += '多看看解析，下一局会更好。';
    setText($('results-line'), line);
    showScreen('results');
  }

  function startGame() {
    var input = $('player-name');
    var name = input ? input.value.trim() : '';
    if (name.length > 24) {
      showError($('home-error'), '名字最多 24 个字符');
      return;
    }
    clearError($('home-error'));
    var btn = $('start-game');
    if (btn) btn.disabled = true;
    api('/api/games', { method: 'POST', body: { playerName: name || '星际学员' } })
      .then(function (snap) {
        renderSnapshot(snap);
      })
      .catch(function (err) {
        showError($('home-error'), err.message);
      })
      .then(function () {
        if (btn) btn.disabled = false;
      });
  }

  function resumeGame() {
    var id = state.gameId;
    if (!id) {
      try { id = localStorage.getItem(STORAGE_KEY); } catch (e) { id = null; }
    }
    if (!id) {
      showError($('home-error'), '没有找到未完成的探索');
      refreshResumeButton();
      return;
    }
    // 重试开始时清除上一次的错误提示，避免旧错误残留。
    clearError($('home-error'));
    api('/api/games/' + encodeURIComponent(id))
      .then(function (snap) {
        if (snap.status === 'finished') {
          state.snapshot = snap;
          state.gameId = snap.gameId;
          renderResults(snap);
        } else {
          renderSnapshot(snap);
        }
      })
      .catch(function (err) {
        // 只有确认游戏不存在（404）时才清除本地记录；
        // 网络故障或 5xx 必须保留 gameId 与“继续上次探索”按钮，方便重试。
        if (err && err.status === 404) {
          try { localStorage.removeItem(STORAGE_KEY); } catch (e) { /* 忽略 */ }
          state.gameId = null;
          state.snapshot = null;
        }
        showError($('home-error'), err.message);
        refreshResumeButton();
      });
  }

  function submitAnswer() {
    if (state.pending || state.awaitingNext) return;
    if (!state.selected) {
      showError($('game-error'), '请先选择一个答案');
      return;
    }
    clearError($('game-error'));
    var snap = state.snapshot;
    if (!snap || !snap.question) return;
    state.pending = true;
    var btn = $('submit-answer');
    if (btn) btn.disabled = true;
    api('/api/games/' + encodeURIComponent(snap.gameId) + '/answers', {
      method: 'POST',
      body: { answer: state.selected, questionId: snap.question.id }
    })
      .then(function (result) {
        state.lastResult = result;
        state.awaitingNext = true;
        // 分数立即更新；题号标签保持指向当前正在讲解的题目，
        // 等点击“下一题”渲染新题目时再推进。
        setScore(result.score);
        renderFeedback(result);
        var box = $('options');
        if (box) {
          Array.prototype.forEach.call(box.querySelectorAll('.option'), function (el) {
            el.disabled = true;
            if (el.getAttribute('data-option') === result.correctAnswer) el.classList.add('correct');
            else if (el.classList.contains('selected')) el.classList.add('wrong');
          });
        }
        hide($('submit-answer'));
        hide($('pause-game'));
        show($('next-question'));
      })
      .catch(function (err) {
        showError($('game-error'), err.message);
      })
      .then(function () {
        state.pending = false;
        if (btn) btn.disabled = false;
      });
  }

  function nextQuestion() {
    var result = state.lastResult;
    if (!result) return;
    state.awaitingNext = false;
    hide($('next-question'));
    hide($('feedback'));
    show($('submit-answer'));
    show($('pause-game'));
    if (result.status === 'finished' || !result.question) {
      var snap = state.snapshot || {};
      renderResults({
        score: result.score,
        totalQuestions: result.totalQuestions,
        answered: result.answered,
        status: 'finished',
        playerName: snap.playerName
      });
      return;
    }
    state.snapshot = Object.assign({}, state.snapshot, {
      question: result.question,
      score: result.score,
      answered: result.answered,
      status: result.status
    });
    // 渲染下一题时同步推进题号与进度条，保证题号与当前题目一致。
    setProgress(result.answered, result.totalQuestions);
    renderQuestion(result.question);
  }

  function pauseGame() {
    var snap = state.snapshot;
    if (!snap) return;
    api('/api/games/' + encodeURIComponent(snap.gameId) + '/pause', { method: 'POST', body: {} })
      .then(function (next) {
        state.snapshot = Object.assign({}, state.snapshot, { status: next.status });
        show($('pause-overlay'));
      })
      .catch(function (err) {
        showError($('game-error'), err.message);
      });
  }

  function resumeFromPause() {
    var snap = state.snapshot;
    if (!snap) return;
    api('/api/games/' + encodeURIComponent(snap.gameId) + '/resume', { method: 'POST', body: {} })
      .then(function (next) {
        state.snapshot = Object.assign({}, state.snapshot, { status: next.status });
        hide($('pause-overlay'));
      })
      .catch(function (err) {
        showError($('game-error'), err.message);
      });
  }

  function loadLeaderboard() {
    var body = $('board-body');
    var empty = $('board-empty');
    if (body) body.textContent = '';
    api('/api/leaderboard')
      .then(function (data) {
        var entries = (data && data.entries) || [];
        if (!entries.length) {
          show(empty);
          return;
        }
        hide(empty);
        entries.forEach(function (entry, index) {
          var tr = document.createElement('tr');
          var cells = [
            String(index + 1),
            entry.playerName || '星际学员',
            String(entry.score),
            String(entry.totalQuestions),
            entry.finishedAt ? new Date(entry.finishedAt).toLocaleString('zh-CN') : '-'
          ];
          cells.forEach(function (text) {
            var td = document.createElement('td');
            td.textContent = text;
            tr.appendChild(td);
          });
          body.appendChild(tr);
        });
      })
      .catch(function (err) {
        showError($('home-error'), err.message);
      });
  }

  function openHelp() {
    var text = $('help-text');
    setText(text, '正在加载帮助…');
    show($('help-overlay'));
    api('/api/help')
      .then(function (data) { setText(text, data.text || ''); })
      .catch(function (err) { setText(text, '帮助加载失败：' + err.message); });
  }

  function currentToken() {
    var input = $('admin-token');
    var typed = input ? input.value.trim() : '';
    if (typed) {
      state.adminToken = typed;
      try { sessionStorage.setItem(TOKEN_KEY, typed); } catch (e) { /* 忽略 */ }
      return typed;
    }
    return state.adminToken;
  }

  function loadAdminQuestions() {
    var token = currentToken();
    if (!token) {
      showError($('admin-error'), '请输入管理员令牌');
      return;
    }
    clearError($('admin-error'));
    api('/api/admin/questions', { headers: { 'x-admin-token': token } })
      .then(function (data) {
        var area = $('admin-json');
        if (area) area.value = JSON.stringify(data.questions, null, 2);
        show($('admin-ok'));
        setText($('admin-ok'), '题库已读取，共 ' + data.questions.length + ' 题。');
      })
      .catch(function (err) {
        showError($('admin-error'), err.message);
      });
  }

  function saveAdminQuestions() {
    var token = currentToken();
    if (!token) {
      showError($('admin-error'), '请输入管理员令牌');
      return;
    }
    var area = $('admin-json');
    var parsed;
    try {
      parsed = JSON.parse(area ? area.value : '[]');
    } catch (e) {
      showError($('admin-error'), 'JSON 格式错误，请检查后再保存');
      return;
    }
    clearError($('admin-error'));
    api('/api/admin/questions', {
      method: 'PUT',
      headers: { 'x-admin-token': token },
      body: { questions: parsed }
    })
      .then(function (data) {
        show($('admin-ok'));
        setText($('admin-ok'), '题库已保存，共 ' + data.questions.length + ' 题。');
      })
      .catch(function (err) {
        showError($('admin-error'), err.message);
      });
  }

  function bind() {
    var startForm = $('start-form');
    if (startForm) {
      startForm.addEventListener('submit', function (event) {
        event.preventDefault();
        startGame();
      });
    }

    var homeResume = $('home-resume-game');
    if (homeResume) homeResume.addEventListener('click', function () { resumeGame(); });
    var pauseResume = $('pause-resume-game');
    if (pauseResume) pauseResume.addEventListener('click', function () { resumeFromPause(); });

    var submit = $('submit-answer');
    if (submit) submit.addEventListener('click', submitAnswer);
    var next = $('next-question');
    if (next) next.addEventListener('click', nextQuestion);
    var pause = $('pause-game');
    if (pause) pause.addEventListener('click', pauseGame);

    var replay = $('replay-game');
    if (replay) replay.addEventListener('click', function () {
      try { localStorage.removeItem(STORAGE_KEY); } catch (e) { /* 忽略 */ }
      state.snapshot = null;
      state.gameId = null;
      state.lastResult = null;
      state.awaitingNext = false;
      state.selected = null;
      showScreen('home');
    });

    var navHome = $('nav-home');
    if (navHome) navHome.addEventListener('click', function () { showScreen('home'); });
    var navBoard = $('nav-board');
    if (navBoard) navBoard.addEventListener('click', function () { showScreen('board'); loadLeaderboard(); });
    var navHelp = $('nav-help');
    if (navHelp) navHelp.addEventListener('click', openHelp);
    var navAdmin = $('nav-admin');
    if (navAdmin) navAdmin.addEventListener('click', function () { showScreen('admin'); });

    var boardBack = $('board-back');
    if (boardBack) boardBack.addEventListener('click', function () { showScreen('home'); });
    var resultsBoard = $('results-board');
    if (resultsBoard) resultsBoard.addEventListener('click', function () { showScreen('board'); loadLeaderboard(); });

    var helpClose = $('help-close');
    if (helpClose) helpClose.addEventListener('click', function () { hide($('help-overlay')); });

    var adminLoad = $('admin-load');
    if (adminLoad) adminLoad.addEventListener('click', loadAdminQuestions);
    var adminSave = $('admin-save');
    if (adminSave) adminSave.addEventListener('click', saveAdminQuestions);
    var adminBack = $('admin-back');
    if (adminBack) adminBack.addEventListener('click', function () { showScreen('home'); });

    document.addEventListener('keydown', function (event) {
      if (event.defaultPrevented) return;
      if (event.ctrlKey || event.metaKey || event.altKey) return;
      var target = event.target;
      if (target && /^(INPUT|TEXTAREA|SELECT)$/.test(target.tagName)) return;
      if (target && target.isContentEditable) return;
      if (state.screen !== 'game') return;
      if (overlayOpen()) return;
      if (event.key >= '1' && event.key <= '4') {
        var box = $('options');
        if (!box) return;
        var options = box.querySelectorAll('.option');
        var chosen = options[Number(event.key) - 1];
        if (chosen && !chosen.disabled) {
          event.preventDefault();
          chosen.click();
        }
      } else if (event.key === 'Enter') {
        var nextBtn = $('next-question');
        var submitBtn = $('submit-answer');
        if (nextBtn && !nextBtn.hidden) {
          event.preventDefault();
          nextQuestion();
        } else if (submitBtn && !submitBtn.hidden) {
          event.preventDefault();
          submitAnswer();
        }
      }
    });
  }

  function init() {
    bind();
    try {
      var saved = localStorage.getItem(STORAGE_KEY);
      if (saved) state.gameId = saved;
      var token = sessionStorage.getItem(TOKEN_KEY);
      if (token) {
        state.adminToken = token;
        var input = $('admin-token');
        if (input) input.value = token;
      }
    } catch (e) { /* 忽略存储异常 */ }
    showScreen('home');
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
