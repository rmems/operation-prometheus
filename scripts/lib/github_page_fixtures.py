"""Sanitized GitHub REST page cassettes for offline collector replay.

Recorded envelopes keep pagination, ETag, and rate-limit metadata while
dropping credentials, cookies, and unstable transport headers. Replay is
strictly ordered and GET-only — the live collector remains read-only.
"""

from __future__ import annotations

import hashlib
import json
import re
import urllib.error
import urllib.parse
import urllib.request
from email.message import Message
from io import BytesIO
from pathlib import Path
from typing import Any

from .github_client import DEFAULT_BASE, GitHubClient, GitHubError, _parse_next_link
from .secrets import find_secrets, scan_and_sanitize_obj, sanitize_text
from .source_inventory_common import canonical_json_bytes

CASSETTE_SCHEMA_VERSION = "github_page_cassette_v1"

PAGE_KINDS = (
    "pull",
    "issue",
    "comment",
    "review",
    "commit",
    "checks",
    "status",
    "file",
    "diff",
    "other",
)

SECRET_QUERY_KEYS = frozenset(
    {
        "access_token",
        "token",
        "client_secret",
        "client_id",
        "authorization",
    }
)

RESPONSE_HEADER_ALLOWLIST = frozenset(
    {
        "etag",
        "last-modified",
        "link",
        "content-type",
        "x-github-media-type",
        "x-ratelimit-limit",
        "x-ratelimit-remaining",
        "x-ratelimit-reset",
        "x-ratelimit-used",
        "x-ratelimit-resource",
        "retry-after",
        "x-poll-interval",
    }
)

FORBIDDEN_HEADER_NAMES = frozenset(
    {
        "authorization",
        "proxy-authorization",
        "cookie",
        "set-cookie",
        "x-github-otp",
        "www-authenticate",
        "x-oauth-scopes",
        "x-accepted-oauth-scopes",
    }
)

_KIND_RULES: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"/commits/[^/]+/check-runs(?:\?|$)"), "checks"),
    (re.compile(r"/commits/[^/]+/status(?:\?|$)"), "status"),
    (re.compile(r"/pulls/\d+/files(?:\?|$)"), "file"),
    (re.compile(r"/pulls/\d+/comments(?:\?|$)"), "comment"),
    (re.compile(r"/issues/\d+/comments(?:\?|$)"), "comment"),
    (re.compile(r"/pulls/\d+/reviews(?:\?|$)"), "review"),
    (re.compile(r"/pulls/\d+/commits(?:\?|$)"), "commit"),
    (re.compile(r"/repos/[^/]+/[^/]+/commits/[^/?]+(?:\?|$)"), "commit"),
    (re.compile(r"/pulls/\d+(?:\?|$)"), "pull"),
    (re.compile(r"/issues/\d+(?:\?|$)"), "issue"),
)


def classify_page_kind(url: str, accept: str = "") -> str:
    """Map a GitHub REST URL (and optional Accept) to a page kind."""
    accept_l = accept.lower()
    if "diff" in accept_l or "patch" in accept_l:
        return "diff"
    path = urllib.parse.urlsplit(url).path
    for pattern, kind in _KIND_RULES:
        if pattern.search(path):
            return kind
    return "other"


def sanitize_url(url: str) -> str:
    """Drop credentials, secret query keys, fragments, and sort query params."""
    parts = urllib.parse.urlsplit(url)
    scheme = parts.scheme or "https"
    host = parts.hostname or ""
    netloc = host
    if parts.port:
        netloc = f"{host}:{parts.port}"
    query_pairs = [
        (key, value)
        for key, value in urllib.parse.parse_qsl(parts.query, keep_blank_values=True)
        if key.lower() not in SECRET_QUERY_KEYS
    ]
    query_pairs.sort(key=lambda item: (item[0], item[1]))
    path, path_warnings = sanitize_text(parts.path or "")
    if path_warnings:
        path = parts.path or ""
        path, _ = sanitize_text(path)
    return urllib.parse.urlunsplit((scheme, netloc, path, urllib.parse.urlencode(query_pairs), ""))


def _header_map(headers: Any) -> dict[str, str]:
    if headers is None:
        return {}
    if hasattr(headers, "items"):
        return {str(key).lower(): str(value) for key, value in headers.items()}
    return {str(key).lower(): str(value) for key, value in dict(headers).items()}


def sanitize_headers(headers: Any, *, allowlist: frozenset[str]) -> dict[str, str]:
    """Keep a stable allowlist and never persist credentials or cookies."""
    cleaned: dict[str, str] = {}
    for key, value in _header_map(headers).items():
        name = key.lower()
        if name in FORBIDDEN_HEADER_NAMES or name not in allowlist:
            continue
        text, _warnings = sanitize_text(value)
        if name == "link":
            text = sanitize_link_header(text)
        cleaned[name] = text
    return dict(sorted(cleaned.items()))


def sanitize_link_header(link_header: str) -> str:
    """Rewrite Link URLs so tokens and unsorted query keys cannot leak."""
    parts: list[str] = []
    for raw in link_header.split(","):
        section = raw.strip()
        if not section:
            continue
        start = section.find("<")
        end = section.find(">")
        if start == -1 or end == -1 or end <= start:
            parts.append(section)
            continue
        url = sanitize_url(section[start + 1 : end])
        tail = section[end + 1 :].strip()
        parts.append(f"<{url}>{(' ' + tail) if tail else ''}")
    return ", ".join(parts)


def request_accept(req: urllib.request.Request) -> str:
    raw = req.headers.get("Accept") or req.get_header("Accept") or ""
    return str(raw)


def request_identity(req: urllib.request.Request) -> dict[str, Any]:
    url = sanitize_url(req.full_url)
    parts = urllib.parse.urlsplit(url)
    query = dict(urllib.parse.parse_qsl(parts.query, keep_blank_values=True))
    return {
        "method": (req.get_method() or "GET").upper(),
        "url": url,
        "accept": request_accept(req),
        "query": dict(sorted(query.items())),
    }


def _rate_limit_metadata(headers: dict[str, str]) -> dict[str, Any]:
    def _maybe_int(name: str) -> int | None:
        raw = headers.get(name)
        if raw is None or raw == "":
            return None
        try:
            return int(raw)
        except ValueError:
            return None

    return {
        "limit": _maybe_int("x-ratelimit-limit"),
        "remaining": _maybe_int("x-ratelimit-remaining"),
        "reset": _maybe_int("x-ratelimit-reset"),
        "used": _maybe_int("x-ratelimit-used"),
        "resource": headers.get("x-ratelimit-resource"),
        "retry_after": headers.get("retry-after"),
    }


def _pagination_state(url: str, headers: dict[str, str]) -> dict[str, Any]:
    parts = urllib.parse.urlsplit(url)
    query = dict(urllib.parse.parse_qsl(parts.query, keep_blank_values=True))
    page_raw = query.get("page")
    per_page_raw = query.get("per_page")
    cursor = query.get("cursor") or query.get("after")
    page: int | None
    per_page: int | None
    try:
        page = int(page_raw) if page_raw is not None else None
    except ValueError:
        page = None
    try:
        per_page = int(per_page_raw) if per_page_raw is not None else None
    except ValueError:
        per_page = None
    link = headers.get("link") or ""
    return {
        "link": link or None,
        "next": _parse_next_link(link),
        "page": page,
        "per_page": per_page,
        "cursor": cursor,
    }


def _sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _infer_truncated(kind: str, body: Any) -> bool:
    if not isinstance(body, dict):
        return False
    if kind == "checks":
        total = body.get("total_count")
        runs = body.get("check_runs")
        if isinstance(total, int) and isinstance(runs, list):
            return total > len(runs)
    if body.get("incomplete_results") is True:
        return True
    return False


def _decode_body(raw: bytes, content_type: str) -> tuple[Any, str | None, bool]:
    text = raw.decode("utf-8", errors="replace")
    if not text:
        return None, None, False
    stripped = text.lstrip()
    looks_json = "json" in content_type.lower() or stripped[:1] in "{["
    if looks_json:
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError:
            cleaned, _warnings = sanitize_text(text)
            return None, cleaned, True
        sanitized, _warnings = scan_and_sanitize_obj(parsed)
        return sanitized, None, False
    cleaned, _warnings = sanitize_text(text)
    return None, cleaned, False


def build_page_envelope(
    *,
    method: str,
    url: str,
    status: int,
    raw_body: bytes,
    response_headers: Any,
    accept: str = "application/vnd.github+json",
) -> dict[str, Any]:
    """Build one sanitized page envelope from a captured HTTP exchange."""
    clean_url = sanitize_url(url)
    headers = sanitize_headers(response_headers, allowlist=RESPONSE_HEADER_ALLOWLIST)
    content_type = headers.get("content-type") or "application/json"
    body, body_text, malformed = _decode_body(raw_body, content_type)
    kind = classify_page_kind(clean_url, accept)
    truncated = _infer_truncated(kind, body)
    if body is not None:
        replay_bytes = canonical_json_bytes(body)
    else:
        replay_bytes = (body_text or "").encode("utf-8")
    body_sha256 = _sha256_bytes(replay_bytes)
    etag = headers.get("etag")
    query = dict(urllib.parse.parse_qsl(urllib.parse.urlsplit(clean_url).query, keep_blank_values=True))
    return {
        "kind": kind,
        "method": method.upper(),
        "url": clean_url,
        "request": {
            "accept": accept,
            "query": dict(sorted(query.items())),
        },
        "status": int(status),
        "etag": etag,
        "identity": {
            "status": int(status),
            "etag": etag,
            "body_sha256": body_sha256,
        },
        "pagination": _pagination_state(clean_url, headers),
        "rate_limit": _rate_limit_metadata(headers),
        "headers": headers,
        "body": body,
        "body_text": body_text,
        "malformed_json": malformed,
        "truncated": truncated,
        "duplicate": False,
        "duplicate_of": None,
    }


def envelope_replay_bytes(page: dict[str, Any]) -> bytes:
    if page.get("body") is not None:
        return canonical_json_bytes(page["body"])
    return str(page.get("body_text") or "").encode("utf-8")


def _duplicate_key(page: dict[str, Any]) -> tuple[Any, ...]:
    return (page.get("kind"), page.get("method"), page.get("url"), page.get("identity", {}).get("body_sha256"))


def mark_duplicates(pages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Flag later pages that replay the same kind/url/body as an earlier one."""
    seen: dict[tuple[Any, ...], int] = {}
    out: list[dict[str, Any]] = []
    for seq, page in enumerate(pages):
        item = dict(page)
        item["seq"] = seq
        key = _duplicate_key(item)
        first = seen.get(key)
        if first is None:
            seen[key] = seq
            item["duplicate"] = False
            item["duplicate_of"] = None
        else:
            item["duplicate"] = True
            item["duplicate_of"] = first
        out.append(item)
    return out


def cassette_dict(pages: list[dict[str, Any]]) -> dict[str, Any]:
    ordered = mark_duplicates(list(pages))
    return {
        "schema_version": CASSETTE_SCHEMA_VERSION,
        "page_count": len(ordered),
        "pages": ordered,
    }


def dumps_cassette(pages: list[dict[str, Any]]) -> str:
    payload = cassette_dict(pages)
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n"


def load_cassette(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise GitHubError("GitHub page cassette must be an object")
    pages = payload.get("pages")
    if not isinstance(pages, list):
        raise GitHubError("GitHub page cassette is missing pages")
    payload["pages"] = mark_duplicates(pages)
    payload["page_count"] = len(payload["pages"])
    payload["schema_version"] = payload.get("schema_version") or CASSETTE_SCHEMA_VERSION
    return payload


def write_cassette(path: Path, pages: list[dict[str, Any]]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(dumps_cassette(pages), encoding="utf-8")
    return path


_LEAK_MARKERS: tuple[tuple[str, str], ...] = (
    ("authorization", "authorization_header"),
    ("bearer ", "bearer_token"),
    ("set-cookie", "cookie"),
    ('"cookie"', "cookie"),
)


def scan_cassette_secrets(payload: dict[str, Any] | str) -> list[str]:
    """Return secret-pattern hits and credential-header leaks in a cassette dump."""
    if isinstance(payload, str):
        text = payload
    else:
        pages = payload.get("pages") if isinstance(payload, dict) else []
        text = dumps_cassette(list(pages or []))
    hits = list(find_secrets(text))
    lowered = text.lower()
    for needle, name in _LEAK_MARKERS:
        if needle in lowered and name not in hits:
            hits.append(name)
    return hits


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
        req = fullurl if isinstance(fullurl, urllib.request.Request) else urllib.request.Request(fullurl)
        method = (req.get_method() or "GET").upper()
        if method not in {"GET", "HEAD"}:
            raise GitHubError(f"Refusing to record non-GET GitHub request ({method})")
        try:
            resp = self._inner.open(req, data=data, timeout=timeout)
        except urllib.error.HTTPError as exc:
            raw = b""
            try:
                raw = exc.read()
            except OSError:
                raw = b""
            envelope = build_page_envelope(
                method=method,
                url=req.full_url,
                status=exc.code,
                raw_body=raw,
                response_headers=exc.headers,
                accept=request_accept(req),
            )
            self.pages.append(envelope)
            _raise_http_error(envelope)
        with resp:
            raw = resp.read()
            status = getattr(resp, "status", None) or getattr(resp, "code", None) or 200
            envelope = build_page_envelope(
                method=method,
                url=getattr(resp, "url", None) or req.full_url,
                status=int(status),
                raw_body=raw,
                response_headers=resp.headers,
                accept=request_accept(req),
            )
        self.pages.append(envelope)
        return _ReplayResponse(
            envelope_replay_bytes(envelope),
            envelope.get("headers") or {},
            envelope["url"],
            int(envelope["status"]),
        )


class ReplayOpener:
    """Serve cassette pages in recorded order. No network."""

    def __init__(self, pages: list[dict[str, Any]]):
        self.pages = mark_duplicates(list(pages))
        self._index = 0

    def open(self, fullurl, data=None, timeout=None):  # noqa: ANN001
        del data, timeout
        req = fullurl if isinstance(fullurl, urllib.request.Request) else urllib.request.Request(fullurl)
        method = (req.get_method() or "GET").upper()
        if method not in {"GET", "HEAD"}:
            raise GitHubError(f"Refusing non-GET GitHub replay ({method})")
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
        status = int(page.get("status") or 0)
        if status >= 400:
            _raise_http_error(page)
        return _ReplayResponse(
            envelope_replay_bytes(page),
            page.get("headers") or {},
            page["url"],
            status,
        )


def attach_page_recorder(client: GitHubClient) -> RecordingOpener:
    """Install a recording wrapper on an existing read-only client."""
    recorder = RecordingOpener(client._opener)
    client._opener = recorder
    return recorder


def replay_github_client(
    pages: list[dict[str, Any]] | dict[str, Any] | Path,
    *,
    base_url: str = DEFAULT_BASE,
    max_retries: int = 5,
    min_remaining: int = 2,
    sleep_fn=lambda _seconds: None,
) -> GitHubClient:
    """Build a GitHubClient that replays a cassette and never opens a socket."""
    if isinstance(pages, Path):
        payload = load_cassette(pages)
        recorded = payload["pages"]
    elif isinstance(pages, dict):
        recorded = list(pages.get("pages") or [])
    else:
        recorded = list(pages)
    client = GitHubClient(
        token=None,
        base_url=base_url,
        max_retries=max_retries,
        min_remaining=min_remaining,
        sleep_fn=sleep_fn,
        opener=ReplayOpener(recorded),
    )
    return client
