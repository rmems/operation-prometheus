"""Shared constants and primitives for the eligibility-ledger modules."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

LEDGER_SCHEMA_VERSION = "eligibility_ledger_v1"
REPOSITORY_SCHEMA_VERSION = "source_repository_v1"
MANIFEST_SCHEMA_VERSION = "eligibility_manifest_v1"

LEDGER_STATES = {
    "included_positive",
    "included_negative",
    "quarantined",
    "excluded",
    "watchlist_open",
}


def _text(value: Any) -> str:
    """Coerce an optional value to a plain string, defaulting to empty."""
    return str(value or "")


def _or_empty_dict(value: Any) -> dict[str, Any]:
    return value if value else {}


def _or_empty_list(value: Any) -> list[Any]:
    return value if value else []


def _parse_time(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        normalized = value[:-1] + "+00:00" if value.endswith(("Z", "z")) else value
        parsed = datetime.fromisoformat(normalized)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    except (ValueError, TypeError, OverflowError):
        return None


def candidate_id(pr: dict[str, Any]) -> str:
    repo_id = str(pr.get("repository_id") or "").strip()
    pr_id = str(pr.get("id") or "").strip()
    if not repo_id or not pr_id:
        raise ValueError("Candidate is missing immutable repository or pull-request ID")
    return f"github:repository:{repo_id}:pull:{pr_id}"


def _source_ref(pr: dict[str, Any]) -> str:
    return f"sha256:{pr.get('source_hash') or ''}"
