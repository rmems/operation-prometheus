"""Timezone-aware timestamp extraction for v0-to-v1 migration."""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any

from .migrate_v0_constants import TERMINAL_TIMESTAMP_KEYS, TIMESTAMP_KEYS

_OVERLONG_FRACTION = re.compile(r"\.\d{7,}")


def parse_utc_timestamp(value: str) -> str | None:
    """Normalize a timezone-aware instant. Naive values are refused."""
    if _OVERLONG_FRACTION.search(value):
        return None
    try:
        iso_ts = value[:-1] + "+00:00" if value.endswith(("Z", "z")) else value
        parsed = datetime.fromisoformat(iso_ts)
        if parsed.tzinfo is None:
            return None
        utc = parsed.astimezone(timezone.utc)
    except (ValueError, TypeError, OverflowError):
        return None
    return _format_utc(utc)


def _format_utc(utc: datetime) -> str:
    if utc.microsecond:
        return utc.strftime("%Y-%m-%dT%H:%M:%S.%fZ")
    return utc.strftime("%Y-%m-%dT%H:%M:%SZ")


def extract_timestamp(record: dict[str, Any]) -> tuple[str | None, str | None]:
    """Return (timestamp, error_code). error_code is set on malformed values."""
    keys = TERMINAL_TIMESTAMP_KEYS.get(record.get("outcome"), TIMESTAMP_KEYS)
    for key in keys:
        parsed = _timestamp_from_key(record, key)
        if parsed is None:
            continue
        return parsed
    if record.get("outcome") in TERMINAL_TIMESTAMP_KEYS and any(
        key in record for key in TIMESTAMP_KEYS
    ):
        return None, "missing_terminal_timestamp"
    return None, "unavailable_timestamp"


def _timestamp_from_key(
    record: dict[str, Any], key: str
) -> tuple[str | None, str | None] | None:
    if key not in record:
        return None
    value = record[key]
    if not isinstance(value, str) or not value.strip():
        return None, "malformed_timestamp"
    parsed = parse_utc_timestamp(value.strip())
    if parsed is None:
        return None, "malformed_timestamp"
    return parsed, None
