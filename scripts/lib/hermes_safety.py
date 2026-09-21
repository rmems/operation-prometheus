"""Safety policy checks for normalized Hermes values."""

from __future__ import annotations

import json
import xml.etree.ElementTree as ET
from collections.abc import Callable, Iterator
from typing import Any

from validate_jsonl import HOME_PATH_RE

from .hermes_sanitize import (
    SECRET_QUERY_KEYS,
    contains_header_secret,
    hidden_markup_remains,
    is_hidden_key,
)
from .secrets import find_secrets

_CREDENTIAL_KEY_NAMES = {name.replace("-", "_") for name in SECRET_QUERY_KEYS} | {
    "x_api_key",
    "bearer",
}


def _credential_key(key: Any) -> bool:
    return str(key).casefold().replace("-", "_") in _CREDENTIAL_KEY_NAMES


def _json_credential_string(value: str) -> bool:
    text = value.strip()
    if not (text.startswith("{") and text.endswith("}")):
        return False
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        return False
    return _contains_credential_key(parsed)


def _walk(value: Any) -> Iterator[tuple[Any | None, Any]]:
    if isinstance(value, dict):
        for key, item in value.items():
            yield key, item
            yield from _walk(item)
    elif isinstance(value, list):
        for item in value:
            yield None, item
            yield from _walk(item)


def _contains_string(value: Any, predicate: Callable[[str], bool]) -> bool:
    if isinstance(value, str) and predicate(value):
        return True
    return any(
        (isinstance(key, str) and predicate(key))
        or (isinstance(item, str) and predicate(item))
        for key, item in _walk(value)
    )


def _secret_string(value: str) -> bool:
    return (
        bool(find_secrets(value))
        or contains_header_secret(value)
        or _json_credential_string(value)
    )


def _contains_secret(value: Any) -> bool:
    return _contains_string(value, _secret_string)


def _contains_credential_key(value: Any) -> bool:
    return any(
        key is not None and _credential_key(key) and item not in (None, "", False)
        for key, item in _walk(value)
    )


def _contains_home_path(value: Any) -> bool:
    return _contains_string(value, lambda text: HOME_PATH_RE.search(text) is not None)


def _contains_hidden_reasoning(value: Any) -> bool:
    if isinstance(value, dict) and any(is_hidden_key(key) for key in value):
        return True
    if any(key is not None and is_hidden_key(key) for key, _ in _walk(value)):
        return True
    return _contains_string(value, hidden_markup_remains)


def _tool_payload_reasons(record: dict[str, Any]) -> list[str]:
    messages = record.get("messages")
    if not isinstance(messages, list):
        return []
    invalid = any(_invalid_tool_payload(message) for message in messages)
    return ["invalid_tool_payload"] if invalid else []


def _invalid_tool_payload(message: Any) -> bool:
    if not isinstance(message, dict) or message.get("role") != "tool":
        return False
    content = message.get("content")
    if not isinstance(content, str):
        return False
    text = content.lstrip()
    if text.startswith(("{", "[")):
        return not _json_well_formed(text)
    return text.startswith("<") and not _xml_well_formed(text)


def _json_well_formed(text: str) -> bool:
    try:
        json.loads(text)
    except json.JSONDecodeError:
        return False
    return True


def _xml_well_formed(text: str) -> bool:
    try:
        ET.fromstring(text)
    except ET.ParseError:
        return False
    return True


def _safety_reasons(value: Any, *, allow_hidden: bool = False) -> list[str]:
    reasons: list[str] = []
    if (
        _contains_secret(value)
        or _contains_credential_key(value)
        or _contains_home_path(value)
    ):
        reasons.append("secret_leakage")
    if not allow_hidden and _contains_hidden_reasoning(value):
        reasons.append("hidden_reasoning")
    return reasons
