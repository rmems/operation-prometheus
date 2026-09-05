"""Stdlib HTTPS client for OpenRouter chat completions.

Dry-run scaffolding never calls :meth:`OpenRouterClient.complete`. The live
path is opt-in, model-locked, and requires ``OPENROUTER_API_KEY``.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any

CHAT_COMPLETIONS_URL = "https://openrouter.ai/api/v1/chat/completions"
LOCKED_MODEL = "nvidia/nemotron-3-ultra-550b-a55b:free"
API_KEY_ENV = "OPENROUTER_API_KEY"
USER_AGENT = (
    "operation-prometheus-openrouter/0.1 "
    "(+https://github.com/rmems/operation-prometheus; EXP-PROM-BUGFIX-SWE-001)"
)
_ALLOWED_NETLOC = "openrouter.ai"


class OpenRouterError(RuntimeError):
    """Non-retryable OpenRouter client failure (including model lock)."""

    def __init__(self, message: str, *, status: int | None = None):
        super().__init__(message)
        self.status = status


def _https_openrouter_url(url: str) -> bool:
    parsed = urllib.parse.urlsplit(url)
    return parsed.scheme.casefold() == "https" and parsed.netloc.casefold() == _ALLOWED_NETLOC


class _SafeRedirectHandler(urllib.request.HTTPRedirectHandler):
    """Allow redirects only to https://openrouter.ai."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        source = urllib.parse.urlsplit(req.full_url)
        if not _https_openrouter_url(newurl):
            target = urllib.parse.urlsplit(newurl)
            raise OpenRouterError(
                f"Refusing OpenRouter redirect from {source.netloc} to "
                f"{target.scheme or '(missing)'}://{target.netloc or '(missing)'}"
            )
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def assert_locked_model(model: str) -> str:
    """Hard-reject any teacher other than the EXP-locked Ultra free id."""
    if model != LOCKED_MODEL:
        raise OpenRouterError(
            f"Model {model!r} is not allowed for EXP-PROM-BUGFIX-SWE-001; "
            f"locked teacher is {LOCKED_MODEL!r} (no fallback models)"
        )
    return model


@dataclass(frozen=True)
class PlannedRequest:
    """Request that would be POSTed to OpenRouter (may omit credentials)."""

    url: str
    headers: dict[str, str]
    body: dict[str, Any]


def build_chat_request(
    messages: list[dict[str, str]],
    *,
    model: str = LOCKED_MODEL,
    api_key: str | None = None,
    temperature: float = 0.7,
) -> PlannedRequest:
    """Build an OpenAI-compatible chat.completions payload.

    ``api_key`` is optional so dry-run can record the planned body without a
    credential. Live callers must pass a key; :meth:`OpenRouterClient.complete`
    still refuses a missing key.
    """
    assert_locked_model(model)
    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json",
        "User-Agent": USER_AGENT,
        "HTTP-Referer": "https://github.com/rmems/operation-prometheus",
        "X-Title": "operation-prometheus EXP-PROM-BUGFIX-SWE-001",
    }
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    body = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
        "response_format": {"type": "json_object"},
    }
    return PlannedRequest(url=CHAT_COMPLETIONS_URL, headers=headers, body=body)


def redact_planned_request(planned: PlannedRequest) -> dict[str, Any]:
    """Return a JSON-serializable request dump with credentials stripped."""
    headers = dict(planned.headers)
    if "Authorization" in headers:
        headers["Authorization"] = "Bearer [REDACTED]"
    return {
        "url": planned.url,
        "headers": headers,
        "body": planned.body,
    }


class OpenRouterClient:
    """Minimal POST-only OpenRouter chat client. Never constructed by dry-run."""

    def __init__(
        self,
        api_key: str | None = None,
        *,
        endpoint: str = CHAT_COMPLETIONS_URL,
        opener: urllib.request.OpenerDirector | None = None,
        timeout: float = 120.0,
    ) -> None:
        self.api_key = api_key if api_key else None
        self.endpoint = endpoint
        self.timeout = timeout
        self._opener = opener or urllib.request.build_opener(_SafeRedirectHandler())

    @classmethod
    def from_env(cls, env_name: str = API_KEY_ENV) -> OpenRouterClient:
        return cls(api_key=os.environ.get(env_name) or None)

    def complete(
        self,
        messages: list[dict[str, str]],
        *,
        model: str = LOCKED_MODEL,
        temperature: float = 0.7,
    ) -> dict[str, Any]:
        """POST chat completions. Callers must not use this from dry-run."""
        if not self.api_key:
            raise OpenRouterError(f"{API_KEY_ENV} is required for live OpenRouter calls")
        planned = build_chat_request(
            messages, model=model, api_key=self.api_key, temperature=temperature
        )
        self._assert_endpoint(planned.url)
        return _decode_object(self._post(planned))

    def _assert_endpoint(self, url: str) -> None:
        if url != self.endpoint or not _https_openrouter_url(url):
            raise OpenRouterError(f"Refusing unexpected OpenRouter URL: {url[:80]}")

    def _post(self, planned: PlannedRequest) -> bytes:
        request = urllib.request.Request(
            planned.url,
            data=json.dumps(planned.body).encode("utf-8"),
            headers=planned.headers,
            method="POST",
        )
        try:
            with self._opener.open(request, timeout=self.timeout) as resp:  # nosec B310
                return resp.read()
        except urllib.error.HTTPError as exc:
            err = exc.read().decode("utf-8", errors="replace")[:500]
            raise OpenRouterError(
                f"OpenRouter POST failed with {exc.code}: {err}",
                status=exc.code,
            ) from exc
        except urllib.error.URLError as exc:
            raise OpenRouterError(f"OpenRouter network error: {exc}") from exc


def _decode_object(raw: bytes) -> dict[str, Any]:
    try:
        decoded = json.loads(raw.decode("utf-8"))
    except json.JSONDecodeError as exc:
        raise OpenRouterError("OpenRouter returned non-JSON body") from exc
    if not isinstance(decoded, dict):
        raise OpenRouterError("OpenRouter JSON root must be an object")
    return decoded
