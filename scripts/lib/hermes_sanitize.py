"""Secret-query sanitization and hidden-reasoning stripping for Hermes traces."""

from __future__ import annotations

import re
import urllib.parse
from typing import Any

SECRET_QUERY_KEYS = frozenset(
    {
        "access_token",
        "token",
        "client_secret",
        "client_id",
        "authorization",
        "api_key",
        "password",
        "secret",
    }
)

HIDDEN_KEYS = frozenset(
    {
        "reasoning",
        "hidden_reasoning",
        "thinking",
        "thought",
        "thoughts",
        "analysis",
        "scratchpad",
        "chain_of_thought",
        "chain-of-thought",
        "cot",
    }
)

_HIDDEN_TAG = (
    r"(?:think|thought|thinking|analysis|reasoning|scratchpad|chain-of-thought|cot)"
)
_HIDDEN_TAG_TOKEN_RE = re.compile(
    rf"<(/?)({_HIDDEN_TAG})\b[^>]*>",
    re.IGNORECASE,
)
_HIDDEN_OPEN_RE = re.compile(rf"<({_HIDDEN_TAG})\b", re.IGNORECASE)
_HIDDEN_CLOSE_RE = re.compile(rf"</({_HIDDEN_TAG})\b", re.IGNORECASE)
_URL_RE = re.compile(r"(?:https?|ftps?)://[^\s\"'<>]+", re.IGNORECASE)
_HEADER_SECRET_RE = re.compile(
    r"(?i)\b(?:authorization|x-api-key|api[-_]?key)\b\s*[:=]"
)


class UnsafeUrlError(ValueError):
    """Raised when a URL cannot be sanitized safely."""


def sanitize_url(url: str) -> str:
    """Drop credentials, secret query keys, and fragments; sort remaining query."""
    parts = _split_url(url)
    _reject_url_credentials(parts)
    return urllib.parse.urlunsplit(
        (
            parts.scheme or "https",
            _normalized_netloc(parts),
            parts.path or "",
            _sanitized_query(parts.query),
            "",
        )
    )


def _split_url(url: str) -> urllib.parse.SplitResult:
    try:
        parts = urllib.parse.urlsplit(url)
        parts.port
    except ValueError as exc:
        raise UnsafeUrlError("invalid_url") from exc
    return parts


def _reject_url_credentials(parts: urllib.parse.SplitResult) -> None:
    if parts.username or parts.password:
        raise UnsafeUrlError("credential_url")
    for segment in (parts.path or "").split("/"):
        if _decoded_segment(segment).casefold() in SECRET_QUERY_KEYS:
            raise UnsafeUrlError("credential_url")


def _decoded_segment(segment: str) -> str:
    decoded = segment
    for _ in range(3):
        next_value = urllib.parse.unquote(decoded)
        if next_value == decoded:
            return decoded
        decoded = next_value
    if urllib.parse.unquote(decoded) != decoded:
        raise UnsafeUrlError("credential_url")
    return decoded


def _normalized_netloc(parts: urllib.parse.SplitResult) -> str:
    host = parts.hostname or ""
    if ":" in host and not host.startswith("["):
        host = f"[{host}]"
    return f"{host}:{parts.port}" if parts.port else host


def _sanitized_query(query: str) -> str:
    query_pairs = [
        (key, value)
        for key, value in urllib.parse.parse_qsl(query, keep_blank_values=True)
        if key.lower() not in SECRET_QUERY_KEYS
    ]
    query_pairs.sort(key=lambda item: (item[0], item[1]))
    return urllib.parse.urlencode(query_pairs)


def sanitize_query_secrets(value: Any) -> Any:
    """Rewrite URLs embedded in strings so secret query keys cannot leak."""
    if isinstance(value, str):
        return _URL_RE.sub(lambda match: sanitize_url(match.group(0)), value)
    if isinstance(value, list):
        return [sanitize_query_secrets(item) for item in value]
    if isinstance(value, dict):
        return {key: sanitize_query_secrets(item) for key, item in value.items()}
    return value


def is_hidden_key(key: Any) -> bool:
    return str(key).casefold() in HIDDEN_KEYS


def hidden_markup_remains(value: str) -> bool:
    """True when a hidden tag is unclosed or only partially stripped."""
    stripped = _strip_hidden_tag_regions(value)
    return (
        _HIDDEN_OPEN_RE.search(stripped) is not None
        or _HIDDEN_CLOSE_RE.search(stripped) is not None
    )


def contains_header_secret(value: str) -> bool:
    return _HEADER_SECRET_RE.search(value) is not None


def strip_hidden_reasoning(value: Any) -> Any:
    """Remove hidden-reasoning fields and producer think-tags from trainable views."""
    if isinstance(value, str):
        return _strip_hidden_tag_regions(value)
    if isinstance(value, list):
        return [strip_hidden_reasoning(item) for item in value]
    if isinstance(value, dict):
        return {
            key: strip_hidden_reasoning(item)
            for key, item in value.items()
            if not is_hidden_key(key)
        }
    return value


def _strip_hidden_tag_regions(value: str) -> str:
    """Strip balanced hidden-tag regions with a single left-to-right scan."""
    output: list[str] = []
    stack: list[str] = []
    cursor = 0
    hidden_start = 0
    for match in _HIDDEN_TAG_TOKEN_RE.finditer(value):
        closing, tag = match.groups()
        normalized_tag = tag.casefold()
        if not stack:
            if closing:
                continue
            output.append(value[cursor : match.start()])
            hidden_start = match.start()
            stack.append(normalized_tag)
            continue
        if not closing:
            stack.append(normalized_tag)
            continue
        if normalized_tag != stack[-1]:
            continue
        stack.pop()
        if not stack:
            cursor = match.end()
    if stack:
        output.append(value[hidden_start:])
    else:
        output.append(value[cursor:])
    return "".join(output)
