"""Safety policy checks for normalized Hermes values."""

from __future__ import annotations

import json
import xml.etree.ElementTree as ET
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


def _contains_secret(value: Any) -> bool:
    if isinstance(value, str):
        return (
            bool(find_secrets(value))
            or contains_header_secret(value)
            or _json_credential_string(value)
        )
    if isinstance(value, list):
        return any(_contains_secret(item) for item in value)
    if isinstance(value, dict):
        return any(
            _contains_secret(key) or _contains_secret(item)
            for key, item in value.items()
        )
    return False


def _contains_credential_key(value: Any) -> bool:
    if isinstance(value, list):
        return any(_contains_credential_key(item) for item in value)
    if isinstance(value, dict):
        for key, item in value.items():
            if _credential_key(key) and item not in (
                None,
                "",
                False,
            ):
                return True
            if _contains_credential_key(item):
                return True
    return False


def _contains_home_path(value: Any) -> bool:
    if isinstance(value, str):
        return HOME_PATH_RE.search(value) is not None
    if isinstance(value, list):
        return any(_contains_home_path(item) for item in value)
    if isinstance(value, dict):
        return any(
            _contains_home_path(key) or _contains_home_path(item)
            for key, item in value.items()
        )
    return False


def _contains_hidden_reasoning(value: Any) -> bool:
    if isinstance(value, str):
        return hidden_markup_remains(value)
    if isinstance(value, list):
        return any(_contains_hidden_reasoning(item) for item in value)
    if isinstance(value, dict):
        return any(
            is_hidden_key(key) or _contains_hidden_reasoning(item)
            for key, item in value.items()
        )
    return False


def _tool_payload_reasons(record: dict[str, Any]) -> list[str]:
    messages = record.get("messages")
    if not isinstance(messages, list):
        return []
    for message in messages:
        if not isinstance(message, dict) or message.get("role") != "tool":
            continue
        content = message.get("content")
        if not isinstance(content, str):
            continue
        text = content.lstrip()
        if text.startswith("{") or text.startswith("["):
            try:
                json.loads(text)
            except json.JSONDecodeError:
                return ["invalid_tool_payload"]
        elif text.startswith("<") and not _xml_well_formed(text):
            return ["invalid_tool_payload"]
    return []


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



