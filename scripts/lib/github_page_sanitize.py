"""URL and header sanitizers for GitHub page cassettes."""

from __future__ import annotations

import urllib.parse
from typing import Any

from .github_page_kinds import PAGE_KINDS, classify_page_kind
from .secrets import sanitize_text

__all__ = [
    "FORBIDDEN_HEADER_NAMES",
    "PAGE_KINDS",
    "RESPONSE_HEADER_ALLOWLIST",
    "SECRET_QUERY_KEYS",
    "classify_page_kind",
    "header_map",
    "request_accept",
    "request_identity",
    "sanitize_headers",
    "sanitize_link_header",
    "sanitize_url",
]

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

def sanitize_url(url: str) -> str:
    """Drop credentials, secret query keys, fragments, and sort query params."""
    parts = urllib.parse.urlsplit(url)
    scheme = parts.scheme or "https"
    host = parts.hostname or ""
    netloc = f"{host}:{parts.port}" if parts.port else host
    query_pairs = [
        (key, value)
        for key, value in urllib.parse.parse_qsl(parts.query, keep_blank_values=True)
        if key.lower() not in SECRET_QUERY_KEYS
    ]
    query_pairs.sort(key=lambda item: (item[0], item[1]))
    path, _warnings = sanitize_text(parts.path or "")
    return urllib.parse.urlunsplit((scheme, netloc, path, urllib.parse.urlencode(query_pairs), ""))


def header_map(headers: Any) -> dict[str, str]:
    if headers is None:
        return {}
    if hasattr(headers, "items"):
        return {str(key).lower(): str(value) for key, value in headers.items()}
    return {str(key).lower(): str(value) for key, value in dict(headers).items()}


def sanitize_headers(headers: Any, *, allowlist: frozenset[str]) -> dict[str, str]:
    """Keep a stable allowlist and never persist credentials or cookies."""
    cleaned: dict[str, str] = {}
    for key, value in header_map(headers).items():
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
        rewritten = _rewrite_link_section(raw.strip())
        if rewritten:
            parts.append(rewritten)
    return ", ".join(parts)


def _rewrite_link_section(section: str) -> str:
    if not section:
        return ""
    start = section.find("<")
    end = section.find(">")
    missing_brackets = start == -1 or end == -1
    if missing_brackets or end <= start:
        return section
    url = sanitize_url(section[start + 1 : end])
    tail = section[end + 1 :].strip()
    suffix = f" {tail}" if tail else ""
    return f"<{url}>{suffix}"


def request_accept(req: Any) -> str:
    raw = req.headers.get("Accept") or req.get_header("Accept") or ""
    return str(raw)


def request_identity(req: Any) -> dict[str, Any]:
    url = sanitize_url(req.full_url)
    parts = urllib.parse.urlsplit(url)
    query = dict(urllib.parse.parse_qsl(parts.query, keep_blank_values=True))
    return {
        "method": (req.get_method() or "GET").upper(),
        "url": url,
        "accept": request_accept(req),
        "query": dict(sorted(query.items())),
    }
