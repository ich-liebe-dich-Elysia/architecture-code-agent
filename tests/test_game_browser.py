"""Optional real-browser regression tests for the generated game.

Run using .venv/Scripts/python -m unittest tests.test_game_browser -v.
The browser and game use temporary profiles/data; normal player records are untouched.
"""
from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from agent.game_launcher import GameLauncher

ROOT = Path(__file__).resolve().parents[1]
GAME = Path(os.environ.get('AGENT_GAME_DIR', ROOT / 'output' / 'space-fractions-llm'))
HAS_BROWSER = importlib.util.find_spec('playwright') is not None


@unittest.skipUnless(HAS_BROWSER and (GAME / 'public' / 'index.html').is_file(),
                     'Install optional playwright and generate game to run browser tests.')
class GameBrowserTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from playwright.sync_api import sync_playwright
        cls.temp = tempfile.TemporaryDirectory(prefix='fractions-browser-')
        cls.launcher = GameLauncher()
        with patch.dict(os.environ, {'DATA_FILE': str(Path(cls.temp.name) / 'store.json'),
                                     'ADMIN_TOKEN': 'browser-test-admin'}):
            cls.url = cls.launcher.start(GAME, open_browser=False)
        cls.playwright = sync_playwright().start()
        cls.browser = cls.playwright.chromium.launch(channel='msedge', headless=True)

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls.playwright.stop()
        cls.launcher.stop()
        cls.temp.cleanup()

    def setUp(self):
        self.context = self.browser.new_context(viewport={'width': 1360, 'height': 900})
        self.page = self.context.new_page()
        self.errors = []
        self.page.on('pageerror', lambda error: self.errors.append(str(error)))
        self.page.goto(self.url)

    def tearDown(self):
        self.context.close()
        self.assertEqual(self.errors, [], 'Browser JavaScript errors')

    def test_unique_ids_and_mobile_layout(self):
        ids = self.page.locator('[id]').evaluate_all('(els) => els.map(e => e.id)')
        self.assertEqual(len(ids), len(set(ids)), 'HTML ids must be unique')
        self.page.set_viewport_size({'width': 390, 'height': 844})
        self.assertLessEqual(self.page.evaluate('document.documentElement.scrollWidth'), 391)
        self.assertTrue(self.page.get_by_test_id('start-game').is_visible())

    def test_complete_round_pause_refresh_feedback_and_replay(self):
        response = self.context.request.get(self.url + '/api/admin/questions',
                                           headers={'x-admin-token': 'browser-test-admin'})
        bank = {q['prompt']: q for q in response.json()['questions']}
        self.page.get_by_test_id('player-name').fill('浏览器学员')
        self.page.get_by_test_id('start-game').click()
        self.page.get_by_test_id('question').wait_for(state='visible')
        self.page.get_by_test_id('pause-game').click()
        resume = self.page.locator('[data-testid="resume-game"]:visible')
        resume.wait_for()
        resume.click()
        self.page.locator('#pause-overlay').wait_for(state='hidden')
        self.page.reload()
        self.page.locator('[data-testid="resume-game"]:visible').click()
        self.page.get_by_test_id('question').wait_for(state='visible')
        for index in range(5):
            prompt = self.page.get_by_test_id('question').inner_text()
            question = bank[prompt]
            self.page.get_by_test_id('answer-option').nth(question['options'].index(question['answer'])).click()
            self.page.get_by_test_id('submit-answer').click()
            self.page.get_by_test_id('next-question').wait_for(state='visible')
            self.assertIn(question['explanation'], self.page.locator('#feedback').inner_text())
            self.assertEqual(self.page.get_by_test_id('score').inner_text(), str((index + 1) * 10))
            self.page.get_by_test_id('next-question').click()
        self.page.get_by_test_id('results').wait_for(state='visible')
        self.assertIn('50', self.page.get_by_test_id('results').inner_text())
        self.page.get_by_test_id('replay-game').click()
        self.page.get_by_test_id('start-game').wait_for(state='visible')

    def test_help_and_teacher_editor(self):
        self.page.locator('#nav-help').click()
        self.page.locator('#help-overlay').wait_for(state='visible')
        self.page.wait_for_function("document.getElementById('help-text').textContent.includes('分数')")
        self.page.locator('#help-close').click()
        self.page.locator('#nav-admin').click()
        self.page.locator('#admin-token').fill('browser-test-admin')
        self.page.locator('#admin-load').click()
        self.page.wait_for_function("document.getElementById('admin-json').value.length > 100")
        bank = json.loads(self.page.locator('#admin-json').input_value())
        self.assertGreaterEqual(len(bank), 10)
        self.page.locator('#admin-save').click()
        self.page.locator('#admin-ok').wait_for(state='visible')

    def test_returning_home_can_resume_existing_round(self):
        self.page.get_by_test_id('start-game').click()
        question = self.page.get_by_test_id('question')
        question.wait_for(state='visible')
        original_prompt = question.inner_text()
        original_id = self.page.evaluate("localStorage.getItem('space-fractions-game-id')")

        self.page.locator('#nav-home').click()
        self.page.locator('#screen-home').wait_for(state='visible')
        resume = self.page.locator('#home-resume-game')
        self.assertTrue(resume.is_visible(), 'Returning home must show the existing-game resume action')
        self.assertTrue(resume.is_enabled(), 'Resume must be usable without reloading the page')
        resume.click()
        question.wait_for(state='visible')
        self.assertEqual(question.inner_text(), original_prompt)
        self.assertEqual(self.page.evaluate("localStorage.getItem('space-fractions-game-id')"), original_id)
        self.assertEqual(self.page.get_by_test_id('score').inner_text(), '0')

    def test_game_shortcuts_do_not_submit_from_home_or_help(self):
        self.page.get_by_test_id('start-game').click()
        self.page.get_by_test_id('question').wait_for(state='visible')
        game_id = self.page.evaluate("localStorage.getItem('space-fractions-game-id')")
        submissions = []
        self.page.on('request', lambda request: submissions.append(request.url)
                     if request.method == 'POST' and request.url.endswith('/answers') else None)

        def assert_shortcuts_are_inactive():
            # Clear the navigation button's focus: the keys exercise document-level
            # shortcuts, not a button's normal Enter activation behavior.
            self.page.evaluate('document.activeElement.blur()')
            self.page.keyboard.press('1')
            self.page.keyboard.press('Enter')
            # Give any synchronous keyboard handler and its fetch a full event-loop
            # turn; a successful health fetch also keeps browser events pumping.
            self.page.evaluate("async () => { await new Promise(requestAnimationFrame); await fetch('/api/health'); }")
            self.assertEqual(submissions, [], 'Hidden or covered gameplay must not submit an answer')
            snapshot = self.context.request.get(self.url + '/api/games/' + game_id).json()
            self.assertEqual(snapshot['answered'], 0)
            self.assertEqual(snapshot['score'], 0)
            self.assertTrue(self.page.locator('#feedback').is_hidden())

        self.page.locator('#nav-home').click()
        self.page.locator('#screen-home').wait_for(state='visible')
        assert_shortcuts_are_inactive()

        self.page.locator('#home-resume-game').click()
        self.page.get_by_test_id('question').wait_for(state='visible')
        self.page.locator('#nav-help').click()
        self.page.locator('#help-overlay').wait_for(state='visible')
        assert_shortcuts_are_inactive()
        self.page.locator('#help-close').click()

        # The same shortcuts should work again once gameplay is actually visible.
        self.page.evaluate('document.activeElement.blur()')
        self.page.keyboard.press('1')
        self.page.keyboard.press('Enter')
        self.page.get_by_test_id('next-question').wait_for(state='visible')
        self.assertEqual(len(submissions), 1)
        snapshot = self.context.request.get(self.url + '/api/games/' + game_id).json()
        self.assertEqual(snapshot['answered'], 1)

    def test_teacher_actions_use_changed_token_field_not_cached_token(self):
        self.page.locator('#nav-admin').click()
        token = self.page.locator('#admin-token')
        token.fill('browser-test-admin')
        with self.page.expect_response(lambda response:
                response.url.endswith('/api/admin/questions') and response.request.method == 'GET') as pending:
            self.page.locator('#admin-load').click()
        self.assertEqual(pending.value.status, 200)
        self.page.wait_for_function("document.getElementById('admin-json').value.length > 100")

        for button, method in (('#admin-load', 'GET'), ('#admin-save', 'PUT')):
            with self.subTest(method=method):
                token.fill('changed-invalid-token-' + method.lower())
                with self.page.expect_response(lambda response:
                        response.url.endswith('/api/admin/questions') and response.request.method == method) as pending:
                    self.page.locator(button).click()
                response = pending.value
                self.assertIn(response.status, (401, 403), 'Changed invalid token must not reuse authorized cached token')
                self.assertEqual(response.request.header_value('x-admin-token'), token.input_value())
                self.page.locator('#admin-error').wait_for(state='visible')

        token.fill('browser-test-admin')
        with self.page.expect_response(lambda response:
                response.url.endswith('/api/admin/questions') and response.request.method == 'GET') as pending:
            self.page.locator('#admin-load').click()
        self.assertEqual(pending.value.status, 200, 'Correcting the input should restore access immediately')

    def test_temporary_resume_failure_preserves_saved_game_and_allows_retry(self):
        self.page.get_by_test_id('start-game').click()
        self.page.get_by_test_id('question').wait_for(state='visible')
        game_id = self.page.evaluate("localStorage.getItem('space-fractions-game-id')")
        original_prompt = self.page.get_by_test_id('question').inner_text()
        self.page.locator('#nav-home').click()
        route_url = self.url + '/api/games/' + game_id
        self.page.route(route_url, lambda route: route.fulfill(
            status=503, content_type='application/json', body=json.dumps({'error': '服务暂时不可用，请重试'})))

        self.page.locator('#home-resume-game').click()
        self.page.locator('#home-error').wait_for(state='visible')
        self.assertEqual(self.page.evaluate("localStorage.getItem('space-fractions-game-id')"), game_id,
                         'Temporary server failure must not discard a recoverable session')
        self.assertTrue(self.page.locator('#home-resume-game').is_visible())
        self.assertTrue(self.page.locator('#home-resume-game').is_enabled())

        self.page.unroute(route_url)
        self.page.locator('#home-resume-game').click()
        self.page.get_by_test_id('question').wait_for(state='visible')
        self.assertEqual(self.page.get_by_test_id('question').inner_text(), original_prompt)
        self.assertEqual(self.page.evaluate("localStorage.getItem('space-fractions-game-id')"), game_id)

    def test_missing_saved_game_clears_stale_resume_state(self):
        self.page.get_by_test_id('start-game').click()
        self.page.get_by_test_id('question').wait_for(state='visible')
        game_id = self.page.evaluate("localStorage.getItem('space-fractions-game-id')")
        self.page.locator('#nav-home').click()
        self.page.route(self.url + '/api/games/' + game_id, lambda route: route.fulfill(
            status=404, content_type='application/json', body=json.dumps({'error': '游戏记录不存在'})))

        self.page.locator('#home-resume-game').click()
        self.page.locator('#home-error').wait_for(state='visible')
        self.assertIsNone(self.page.evaluate("localStorage.getItem('space-fractions-game-id')"),
                          'A confirmed missing game should clear the stale saved identifier')
        self.assertTrue(self.page.locator('#home-resume-game').is_hidden())
        self.assertTrue(self.page.get_by_test_id('start-game').is_visible())
