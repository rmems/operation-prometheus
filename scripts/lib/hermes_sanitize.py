"""Secret-query sanitization and hidden-reasoning stripping for Hermes traces."""

from __future__ import annotations

import re
import urllib.parse
from dataclasses import dataclass, field
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
        _ = parts.port
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
    state = _HiddenStripState(value)
    for match in _HIDDEN_TAG_TOKEN_RE.finditer(value):
        state.consume(match)
    return state.finish()


@dataclass
class _HiddenStripState:
    value: str
    output: list[str] = field(default_factory=list)
    stack: list[str] = field(default_factory=list)
    cursor: int = 0
    hidden_start: int = 0

    def consume(self, match: re.Match[str]) -> None:
        closing, tag = match.groups()
        normalized_tag = tag.casefold()
        if not self.stack:
            self._consume_at_top_level(match, closing, normalized_tag)
        elif not closing:
            self.stack.append(normalized_tag)
        elif normalized_tag == self.stack[-1]:
            self.stack.pop()
            if not self.stack:
                self.cursor = match.end()

    def _consume_at_top_level(
        self, match: re.Match[str], closing: str, normalized_tag: str
    ) -> None:
        if closing:
            return
        self.output.append(self.value[self.cursor : match.start()])
        self.hidden_start = match.start()
        self.stack.append(normalized_tag)

    def finish(self) -> str:
        suffix_start = self.hidden_start if self.stack else self.cursor
        self.output.append(self.value[suffix_start:])
        return "".join(self.output)
