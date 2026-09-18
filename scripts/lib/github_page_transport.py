"""Recording and replay transports for GitHub page cassettes."""

from __future__ import annotations

import urllib.error
import urllib.request
from dataclasses import dataclass
from email.message import Message
from io import BytesIO
from pathlib import Path
from typing import Any

from .github_client import DEFAULT_BASE, GitHubClient, GitHubError
from .github_page_cassette import load_cassette, mark_duplicates
from .github_page_envelope import PageCapture, build_page_envelope, envelope_replay_bytes
from .github_page_sanitize import header_map, request_accept, request_identity, sanitize_url


class _HeaderMessage(Message):
    """Case-insensitive header map compatible with urllib.error.HTTPError."""


def _message_from_headers(headers: dict[str, str]) -> _HeaderMessage:
    msg = _HeaderMessage()
    for key, value in headers.items():
        msg[key] = value
    return msg


class _ReplayResponse:
    def __init__(self, body: bytes, headers: dict[str, str], url: str, status: int):
        self._body = body
        self.headers = _message_from_headers(headers)
        self.url = url
        self.status = status
        self.code = status

    def read(self, *args: Any, **kwargs: Any) -> bytes:
        del args, kwargs
        return self._body

    def __enter__(self) -> _ReplayResponse:
        return self

    def __exit__(self, *args: Any) -> bool:
        del args
        return False


def _as_get_request(fullurl: Any) -> urllib.request.Request:
    if isinstance(fullurl, urllib.request.Request):
        return fullurl
    return urllib.request.Request(fullurl)


def _require_get(req: urllib.request.Request, action: str) -> str:
    method = (req.get_method() or "GET").upper()
    if method not in {"GET", "HEAD"}:
        raise GitHubError(f"Refusing {action} non-GET GitHub request ({method})")
    return method


def _raise_http_error(page: dict[str, Any]) -> None:
    body = envelope_replay_bytes(page)
    raise urllib.error.HTTPError(
        page["url"],
        int(page["status"]),
        "GitHub page cassette replay",
        _message_from_headers(page.get("headers") or {}),
        BytesIO(body),
    )


class RecordingOpener:
    """Wrap an opener, appending one sanitized envelope per HTTP exchange."""

    def __init__(self, inner: Any, pages: list[dict[str, Any]] | None = None):
        self._inner = inner
        self.pages: list[dict[str, Any]] = list(pages or [])

    def open(self, fullurl, data=None, timeout=None):  # noqa: ANN001
        req = _as_get_request(fullurl)
        method = _require_get(req, "to record")
        try:
            resp = self._inner.open(req, data=data, timeout=timeout)
        except urllib.error.HTTPError as exc:
            return self._record_error(req, method, exc)
        return self._record_success(req, method, resp)

    def _record_error(self, req: urllib.request.Request, method: str, exc: urllib.error.HTTPError) -> None:
        raw = _read_error_body(exc)
        capture = PageCapture(
            method=method,
            url=req.full_url,
            status=exc.code,
            raw_body=raw,
            response_headers=exc.headers,
            accept=request_accept(req),
        )
        self.pages.append(build_page_envelope(capture))
        raise urllib.error.HTTPError(req.full_url, exc.code, exc.msg, exc.headers, BytesIO(raw))

    def _record_success(self, req: urllib.request.Request, method: str, resp: Any) -> _ReplayResponse:
        with resp:
            raw = resp.read()
            status = getattr(resp, "status", None) or getattr(resp, "code", None) or 200
            live_url = getattr(resp, "url", None) or req.full_url
            live_headers = header_map(resp.headers)
            raw_headers = resp.headers
        capture = PageCapture(
            method=method,
            url=req.full_url,
            status=int(status),
            raw_body=raw,
            response_headers=raw_headers,
            accept=request_accept(req),
        )
        self.pages.append(build_page_envelope(capture))
        return _ReplayResponse(raw, live_headers, live_url, int(status))


def _read_error_body(exc: urllib.error.HTTPError) -> bytes:
    try:
        return exc.read()
    except OSError:
        return b""


class ReplayOpener:
    """Serve cassette pages in recorded order. No network."""

    def __init__(self, pages: list[dict[str, Any]]):
        self.pages = mark_duplicates(list(pages))
        self._index = 0

    def open(self, fullurl, data=None, timeout=None):  # noqa: ANN001
        del data, timeout
        req = _as_get_request(fullurl)
        method = _require_get(req, "to replay")
        del method
        page = self._take_page(req)
        status = int(page.get("status") or 0)
        if status >= 400:
            _raise_http_error(page)
        return _ReplayResponse(
            envelope_replay_bytes(page),
            page.get("headers") or {},
            page["url"],
            status,
        )

    def _take_page(self, req: urllib.request.Request) -> dict[str, Any]:
        if self._index >= len(self.pages):
            raise GitHubError(f"GitHub page cassette exhausted before {sanitize_url(req.full_url)}")
        page = self.pages[self._index]
        identity = request_identity(req)
        expected_url = page.get("url")
        expected_accept = (page.get("request") or {}).get("accept") or ""
        if identity["url"] != expected_url or identity["accept"] != expected_accept:
            raise GitHubError(
                "GitHub page cassette replay order mismatch: "
                f"expected {page.get('method')} {expected_url} accept={expected_accept!r}, "
                f"got {identity['method']} {identity['url']} accept={identity['accept']!r}"
            )
        self._index += 1
        return page


def attach_page_recorder(client: GitHubClient) -> RecordingOpener:
    """Install a recording wrapper on an existing read-only client."""
    recorder = RecordingOpener(client._opener)
    client._opener = recorder
    return recorder


@dataclass(frozen=True)
class ReplayOptions:
    base_url: str = DEFAULT_BASE
    max_retries: int = 5
    min_remaining: int = 2
    sleep_fn: Any = None


def replay_github_client(
    pages: list[dict[str, Any]] | dict[str, Any] | Path,
    options: ReplayOptions | None = None,
) -> GitHubClient:
    """Build a GitHubClient that replays a cassette and never opens a socket."""
    opts = options or ReplayOptions()
    recorded = _recorded_pages(pages)
    return GitHubClient(
        token=None,
        base_url=opts.base_url,
        max_retries=opts.max_retries,
        min_remaining=opts.min_remaining,
        sleep_fn=opts.sleep_fn or (lambda _seconds: None),
        opener=ReplayOpener(recorded),
    )


def _recorded_pages(pages: list[dict[str, Any]] | dict[str, Any] | Path) -> list[dict[str, Any]]:
    if isinstance(pages, Path):
        return list(load_cassette(pages)["pages"])
    if isinstance(pages, dict):
        return list(pages.get("pages") or [])
    return list(pages)
