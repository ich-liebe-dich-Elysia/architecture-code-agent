"""Contract and credential-handling tests; these never contact the paid API."""

from __future__ import annotations

import io
import json
import os
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import Mock, patch
from urllib.error import HTTPError

from agent.deepseek_client import DeepSeekClient, DeepSeekError, _NoRedirect, load_api_key


KEY = "sk-test-secret-never-print"


def completion(content='{"files": []}', reason="stop"):
    return {
        "model": "deepseek-flash",
        "choices": [{"finish_reason": reason, "message": {"content": content}}],
        "usage": {"total_tokens": 42},
    }


class DeepSeekKeyTests(unittest.TestCase):
    def test_precedence_and_bom(self):
        with TemporaryDirectory() as folder:
            key_file = Path(folder) / "key.txt"
            key_file.write_text("\ufeff  sk-file-key\n", encoding="utf-8")
            with patch.dict(os.environ, {"DEEPSEEK_API_KEY": "sk-env-key"}):
                self.assertEqual(load_api_key(KEY, key_file), KEY)
                self.assertEqual(load_api_key(key_file=key_file), "sk-env-key")
            with patch.dict(os.environ, {}, clear=True):
                self.assertEqual(load_api_key(key_file=key_file), "sk-file-key")

    def test_missing_or_malformed_key_never_echoed(self):
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(DeepSeekError):
                load_api_key()
        for invalid in ("", KEY + "\nAuthorization: stolen", "api_key=" + KEY):
            with self.subTest(invalid=invalid):
                with self.assertRaises(DeepSeekError) as caught:
                    load_api_key(invalid)
                self.assertNotIn(KEY, str(caught.exception))


class DeepSeekClientTests(unittest.TestCase):
    def setUp(self):
        self.client = DeepSeekClient(KEY)
        self.client._opener = Mock()
        self.messages = [{"role": "user", "content": "Return JSON: 中文"}]

    def respond(self, value):
        self.client._opener.open.return_value = io.BytesIO(json.dumps(value).encode("utf-8"))

    def test_json_request_and_usage(self):
        self.respond(completion())
        self.assertEqual(self.client.complete_json(self.messages, 16000), {"files": []})
        request = self.client._opener.open.call_args.args[0]
        payload = json.loads(request.data)
        self.assertEqual(request.full_url, "https://api.deepseek.com/chat/completions")
        self.assertEqual(request.get_header("Authorization"), "Bearer " + KEY)
        self.assertEqual(payload["response_format"], {"type": "json_object"})
        self.assertEqual(payload["thinking"], {"type": "disabled"})
        self.assertEqual(payload["max_tokens"], 16000)
        self.assertFalse(payload["stream"])
        self.assertEqual(payload["messages"], self.messages)
        self.assertEqual(self.client.last_usage, {"total_tokens": 42})
        self.assertEqual(self.client.last_model, "deepseek-flash")

    def test_fenced_json_fallback(self):
        self.respond(completion('```json\n{"files": []}\n```'))
        self.assertEqual(self.client.complete_json(self.messages), {"files": []})

    def test_truncated_response_rejected_even_when_json_is_valid(self):
        self.respond(completion(reason="length"))
        with self.assertRaisesRegex(DeepSeekError, "truncated"):
            self.client.complete_json(self.messages)

    def test_invalid_or_missing_completion(self):
        for response in ({}, completion(""), completion("[]"), completion(KEY)):
            with self.subTest(response=response):
                self.respond(response)
                with self.assertRaises(DeepSeekError) as caught:
                    self.client.complete_json(self.messages)
                self.assertNotIn(KEY, str(caught.exception))

    def test_http_401_is_not_retried_and_does_not_leak_body(self):
        self.client._opener.open.side_effect = HTTPError(
            "https://api.deepseek.com", 401, KEY, {}, io.BytesIO(KEY.encode())
        )
        with self.assertRaisesRegex(DeepSeekError, "HTTP 401") as caught:
            self.client.complete_json(self.messages)
        self.assertNotIn(KEY, str(caught.exception))
        self.assertEqual(self.client._opener.open.call_count, 1)

    @patch("agent.deepseek_client.time.sleep")
    def test_transient_error_retries_then_succeeds(self, sleep):
        self.client._opener.open.side_effect = [
            HTTPError("https://api.deepseek.com", 429, "limit", {}, io.BytesIO()),
            io.BytesIO(json.dumps(completion()).encode()),
        ]
        self.assertEqual(self.client.complete_json(self.messages), {"files": []})
        self.assertEqual(self.client._opener.open.call_count, 2)
        sleep.assert_called_once_with(1)

    @patch("agent.deepseek_client.time.sleep")
    def test_retry_limit_is_three_attempts(self, sleep):
        self.client._opener.open.side_effect = [
            HTTPError("https://api.deepseek.com", 503, KEY, {}, io.BytesIO())
            for _ in range(3)
        ]
        with self.assertRaisesRegex(DeepSeekError, "HTTP 503"):
            self.client.complete_json(self.messages)
        self.assertEqual(self.client._opener.open.call_count, 3)
        self.assertEqual(sleep.call_count, 2)

    def test_api_key_cannot_be_sent_to_other_hosts(self):
        for url in (
            "http://api.deepseek.com", "https://example.com", "https://api.deepseek.com.example.com",
            "https://name:password@api.deepseek.com", "https://api.deepseek.com/?x=1",
            "https://api.deepseek.com:8080", "https://api.deepseek.com/another-path",
        ):
            with self.subTest(url=url):
                with self.assertRaises(DeepSeekError):
                    DeepSeekClient(KEY, base_url=url)
        self.assertIsNone(_NoRedirect().redirect_request(None, None, 302, "", {}, "https://example.com"))

    def test_v1_endpoint_and_model_list(self):
        client = DeepSeekClient(KEY, base_url="https://api.deepseek.com/v1/")
        client._opener = Mock()
        client._opener.open.return_value = io.BytesIO(b'{"data":[{"id":"deepseek-flash"}]}')
        result = client.check_connection()
        self.assertTrue(result["available"])
        request = client._opener.open.call_args.args[0]
        self.assertEqual(request.full_url, "https://api.deepseek.com/v1/models")
        self.assertEqual(request.method, "GET")


if __name__ == "__main__":
    unittest.main()
