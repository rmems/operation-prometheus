"""Build sanitized GitHub page envelopes from captured HTTP exchanges."""

from __future__ import annotations

import hashlib
import urllib.parse
from dataclasses import dataclass
from typing import Any

from .github_client import _parse_next_link
from .github_page_body import decode_page_body
from .github_page_kinds import classify_page_kind
from .github_page_sanitize import RESPONSE_HEADER_ALLOWLIST, sanitize_headers, sanitize_url
from .github_page_truncate import infer_truncated
from .source_inventory_common import canonical_json_bytes


@dataclass(frozen=True)
class PageCapture:
    method: str
    url: str
    status: int
    raw_body: bytes
    response_headers: Any
    accept: str = "application/vnd.github+json"


def build_page_envelope(capture: PageCapture) -> dict[str, Any]:
    """Build one sanitized page envelope from a captured HTTP exchange."""
    clean_url = sanitize_url(capture.url)
    headers = sanitize_headers(capture.response_headers, allowlist=RESPONSE_HEADER_ALLOWLIST)
    content_type = headers.get("content-type") or "application/json"
    body, body_text, malformed = decode_page_body(capture.raw_body, content_type)
    kind = classify_page_kind(clean_url, capture.accept)
    truncated = infer_truncated(kind, body, headers)
    replay_bytes = canonical_json_bytes(body) if body is not None else (body_text or "").encode("utf-8")
    body_sha256 = hashlib.sha256(replay_bytes).hexdigest()
    etag = headers.get("etag")
    query = dict(urllib.parse.parse_qsl(urllib.parse.urlsplit(clean_url).query, keep_blank_values=True))
    return {
        "kind": kind,
        "method": capture.method.upper(),
        "url": clean_url,
        "request": {"accept": capture.accept, "query": dict(sorted(query.items()))},
        "status": int(capture.status),
        "etag": etag,
        "identity": {"status": int(capture.status), "etag": etag, "body_sha256": body_sha256},
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


def _rate_limit_metadata(headers: dict[str, str]) -> dict[str, Any]:
    return {
        "limit": _maybe_int(headers.get("x-ratelimit-limit")),
        "remaining": _maybe_int(headers.get("x-ratelimit-remaining")),
        "reset": _maybe_int(headers.get("x-ratelimit-reset")),
        "used": _maybe_int(headers.get("x-ratelimit-used")),
        "resource": headers.get("x-ratelimit-resource"),
        "retry_after": headers.get("retry-after"),
    }


def _maybe_int(raw: str | None) -> int | None:
    if raw is None or raw == "":
        return None
    try:
        return int(raw)
    except ValueError:
        return None


def _pagination_state(url: str, headers: dict[str, str]) -> dict[str, Any]:
    parts = urllib.parse.urlsplit(url)
    query = dict(urllib.parse.parse_qsl(parts.query, keep_blank_values=True))
    link = headers.get("link") or ""
    return {
        "link": link or None,
        "next": _parse_next_link(link),
        "page": _maybe_int(query.get("page")),
        "per_page": _maybe_int(query.get("per_page")),
        "cursor": query.get("cursor") or query.get("after"),
    }
