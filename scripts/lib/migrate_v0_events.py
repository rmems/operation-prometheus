"""Unknown-event refusal helpers for v0-to-v1 migration."""

from __future__ import annotations

from typing import Any

from .migrate_v0_constants import KNOWN_EVENT_TYPES, KNOWN_VALIDATION_TYPES


def unknown_event_reason(record: dict[str, Any]) -> str | None:
    events = record.get("events")
    if events is not None and _unknown_event_list(events):
        return "unknown_event"
    validation = record.get("validation")
    if validation is None:
        return None
    if _unknown_validation_list(validation):
        return "unknown_event"
    return None


def _unknown_event_list(events: object) -> bool:
    if not isinstance(events, list):
        return True
    return any(_unknown_event_item(item) for item in events)


def _unknown_event_item(item: object) -> bool:
    if not isinstance(item, dict):
        return True
    event_type = item.get("event_type")
    return not isinstance(event_type, str) or event_type not in KNOWN_EVENT_TYPES


def _unknown_validation_list(validation: object) -> bool:
    if not isinstance(validation, list):
        return True
    return any(_unknown_validation_item(item) for item in validation)


def _unknown_validation_item(item: object) -> bool:
    if not isinstance(item, dict):
        return True
    vtype = item.get("type")
    if vtype is None:
        return False
    return not isinstance(vtype, str) or vtype not in KNOWN_VALIDATION_TYPES
