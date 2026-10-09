"""Small, standard-library DeepSeek client used by the coding agent.

Credentials are loaded locally and are never included in saved generation logs
or exception messages. Model responses are treated as untrusted JSON data.
"""

from __future__ import annotations

import json
import os
import re
import time
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener


DEFAULT_MODEL = "deepseek-flash"
DEFAULT_BASE_URL = "https://api.deepseek.com"
_MAX_RESPONSE_BYTES = 8 * 1024 * 1024


class DeepSeekError(RuntimeError):
    """A safe-to-display API/configuration error, without raw response bodies."""


def load_api_key(
    api_key: str | None = None, key_file: Path | None = None
) -> str:
    """Load an explicit key, DEEPSEEK_API_KEY, or a UTF-8 plain-text key file.

    An explicitly supplied but invalid key is an error; silently falling back
    to a different credential would make the user's configuration misleading.
    """
    value = api_key if api_key is not None else os.environ.get("DEEPSEEK_API_KEY")
    if value is None and key_file is not None:
        try:
            value = Path(key_file).read_text(encoding="utf-8-sig")
        except (OSError, UnicodeError):
            raise DeepSeekError("Cannot read the DeepSeek key file as UTF-8.") from None
    if value is None:
        raise DeepSeekError(
            "DeepSeek API key is missing. Set DEEPSEEK_API_KEY or select a key file."
        )
    if not isinstance(value, str):
        raise DeepSeekError("DeepSeek API key must be a plain-text string.")
    value = value.strip().lstrip("\ufeff").strip()
    if not re.fullmatch(r"sk-[A-Za-z0-9_-]+", value):
        raise DeepSeekError(
            "Invalid DeepSeek API key format. Supply only the sk-... key."
        )
    return value


class _NoRedirect(HTTPRedirectHandler):
    """Do not forward the authorization header to a redirected endpoint."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class DeepSeekClient:
    """Call DeepSeek's chat-completions API and return the JSON content object."""

    def __init__(
        self,
        api_key: str,
        base_url: str = DEFAULT_BASE_URL,
        model: str = DEFAULT_MODEL,
        timeout: float = 240,
    ) -> None:
        self._api_key = load_api_key(api_key)
        try:
            parsed = urlsplit(base_url)
            safe_url = (
                parsed.scheme == "https"
                and parsed.hostname == "api.deepseek.com"
                and parsed.port in (None, 443)
                and parsed.username is None
                and parsed.password is None
                and not parsed.query
                and not parsed.fragment
                and parsed.path.rstrip("/") in ("", "/v1")
            )
        except (TypeError, ValueError):
            safe_url = False
        if not safe_url:
            raise DeepSeekError(
                "DeepSeek base URL must be https://api.deepseek.com or its /v1 endpoint."
            )
        if not isinstance(model, str) or not model.strip():
            raise DeepSeekError("A DeepSeek model name is required.")
        if timeout <= 0:
            raise DeepSeekError("API timeout must be positive.")
        self.base_url = base_url.rstrip("/")
        self.model = model.strip()
        self.timeout = timeout
        self.last_usage: dict = {}
        self.last_model: str = self.model
        self._opener = build_opener(_NoRedirect())

    def _request_json(self, endpoint: str, payload: dict | None = None) -> dict:
        try:
            body = (
                json.dumps(payload, ensure_ascii=False).encode("utf-8")
                if payload is not None
                else None
            )
        except (TypeError, ValueError):
            raise DeepSeekError("API request contains data that is not JSON serializable.") from None
        request = Request(
            self.base_url + endpoint,
            data=body,
            headers={
                "Authorization": "Bearer " + self._api_key,
                "Content-Type": "application/json",
                "Accept": "application/json",
                "User-Agent": "ArchitectureCodeAgent/2.0",
            },
            method="POST" if payload is not None else "GET",
        )
        for attempt in range(3):
            try:
                with self._opener.open(request, timeout=self.timeout) as response:
                    raw = response.read(_MAX_RESPONSE_BYTES + 1)
                if len(raw) > _MAX_RESPONSE_BYTES:
                    raise DeepSeekError("DeepSeek response exceeds the supported size limit.")
                try:
                    result = json.loads(raw.decode("utf-8"))
                except (ValueError, UnicodeError):
                    raise DeepSeekError("DeepSeek returned an invalid JSON API response.") from None
                if not isinstance(result, dict):
                    raise DeepSeekError("DeepSeek API response must be a JSON object.")
                if "error" in result:
                    raise DeepSeekError("DeepSeek returned an API error. Check your account and model settings.")
                return result
            except HTTPError as exc:
                status = exc.code
                exc.close()
                if (status == 429 or 500 <= status < 600) and attempt < 2:
                    time.sleep(attempt + 1)
                    continue
                explanations = {
                    400: "The model or request settings were rejected.",
                    401: "The API key was rejected. Check your DeepSeek key.",
                    402: "The DeepSeek account has insufficient balance.",
                    403: "This key does not have access to the requested model.",
                    404: "The DeepSeek endpoint or model was not found.",
                    429: "DeepSeek is rate limiting requests; try again later.",
                }
                explanation = explanations.get(status, "The DeepSeek service could not complete the request.")
                raise DeepSeekError(f"DeepSeek HTTP {status}: {explanation}") from None
            except (URLError, TimeoutError, OSError):
                if attempt < 2:
                    time.sleep(attempt + 1)
                    continue
                raise DeepSeekError(
                    "Could not reach DeepSeek after 3 attempts. Check the network or increase the timeout."
                ) from None
        raise DeepSeekError("DeepSeek request did not complete.")

    def check_connection(self) -> dict:
        """Return available model IDs without making a paid completion request."""
        result = self._request_json("/models")
        data = result.get("data")
        if not isinstance(data, list):
            raise DeepSeekError("DeepSeek returned an invalid model list.")
        models = [item["id"] for item in data if isinstance(item, dict) and isinstance(item.get("id"), str)]
        return {"models": models, "selected_model": self.model, "available": self.model in models}

    def complete_json(self, messages: list[dict], max_tokens: int = 8192) -> dict:
        """Generate one complete JSON object, failing clearly on token truncation.

        Callers should mention JSON and the required schema in their prompt,
        then validate that schema before using or writing generated content.
        """
        if not isinstance(messages, list) or not messages or not all(
            isinstance(item, dict)
            and item.get("role") in ("system", "user", "assistant")
            and isinstance(item.get("content"), str)
            for item in messages
        ):
            raise DeepSeekError("Messages must contain role/content text objects.")
        if isinstance(max_tokens, bool) or not isinstance(max_tokens, int) or max_tokens <= 0:
            raise DeepSeekError("max_tokens must be a positive integer.")
        self.last_usage = {}
        result = self._request_json(
            "/chat/completions",
            {
                "model": self.model,
                "messages": messages,
                "max_tokens": max_tokens,
                "temperature": 0.2,
                "stream": False,
                "response_format": {"type": "json_object"},
                "thinking": {"type": "disabled"},
            },
        )
        if isinstance(result.get("usage"), dict):
            self.last_usage = result["usage"]
        if isinstance(result.get("model"), str):
            self.last_model = result["model"]
        choices = result.get("choices")
        if not isinstance(choices, list) or not choices or not isinstance(choices[0], dict):
            raise DeepSeekError("DeepSeek returned no completion choice.")
        choice = choices[0]
        if choice.get("finish_reason") == "length":
            raise DeepSeekError(
                "DeepSeek output was truncated by the token limit. Request fewer files or increase max_tokens."
            )
        message = choice.get("message")
        content = message.get("content") if isinstance(message, dict) else None
        if not isinstance(content, str) or not content.strip():
            raise DeepSeekError("DeepSeek returned no JSON content.")
        content = content.strip()
        fence = re.fullmatch(r"```(?:json)?\s*\n?(.*?)\n?```", content, flags=re.DOTALL | re.IGNORECASE)
        if fence:
            content = fence.group(1).strip()
        try:
            document = json.loads(content)
        except ValueError:
            raise DeepSeekError("DeepSeek completion is not valid JSON; regenerate this step.") from None
        if not isinstance(document, dict):
            raise DeepSeekError("DeepSeek completion must be a JSON object, not an array or scalar.")
        return document
