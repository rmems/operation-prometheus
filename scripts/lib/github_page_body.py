"""Decode and sanitize captured GitHub page bodies."""

from __future__ import annotations

import json
from typing import Any

from .secrets import scan_and_sanitize_obj, sanitize_text


def decode_page_body(raw: bytes, content_type: str) -> tuple[Any, str | None, bool]:
    text = raw.decode("utf-8", errors="replace")
    if not text:
        return None, None, False
    if not _looks_json(text, content_type):
        return _sanitized_text(text, malformed=False)
    return _parsed_json_body(text)


def _looks_json(text: str, content_type: str) -> bool:
    stripped = text.lstrip()
    return "json" in content_type.lower() or stripped[:1] in "{["


def _sanitized_text(text: str, *, malformed: bool) -> tuple[Any, str | None, bool]:
    cleaned, _warnings = sanitize_text(text)
    return None, cleaned, malformed


def _parsed_json_body(text: str) -> tuple[Any, str | None, bool]:
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        return _sanitized_text(text, malformed=True)
    sanitized, _warnings = scan_and_sanitize_obj(parsed)
    return sanitized, None, False
