"""OID, repo, and unavailable-field helpers for v0-to-v1 migration."""

from __future__ import annotations

from typing import Any

from .migrate_v0_constants import GIT_OID_RE, OID_FIELD_MAP, REPO_RE, TIMESTAMP_KEYS
from .migrate_v0_timestamps import extract_timestamp


def nonempty_str(value: object) -> str | None:
    if isinstance(value, str) and value.strip():
        return value
    return None


def extract_code_state(record: dict[str, Any]) -> tuple[dict[str, str], str | None]:
    """Return (code_state, error_code). error_code is set on malformed OIDs."""
    sources: list[dict[str, Any]] = [record]
    nested = record.get("repository")
    if isinstance(nested, dict):
        sources.append(nested)
    code_state: dict[str, str] = {}
    for source in sources:
        error = _merge_oids(source, code_state)
        if error is not None:
            return {}, error
    return code_state, None


def _merge_oids(source: dict[str, Any], code_state: dict[str, str]) -> str | None:
    for src_key, dest_key in OID_FIELD_MAP:
        if src_key not in source:
            continue
        error = _assign_oid(source[src_key], dest_key, code_state)
        if error is not None:
            return error
    return None


def _assign_oid(value: object, dest_key: str, code_state: dict[str, str]) -> str | None:
    if not isinstance(value, str) or not GIT_OID_RE.fullmatch(value):
        return "malformed_commit_oid"
    if dest_key in code_state and code_state[dest_key] != value:
        return "conflicting_commit_oid"
    code_state[dest_key] = value
    return None


def split_repo(repo: object) -> tuple[str, str] | None:
    if not isinstance(repo, str) or not REPO_RE.fullmatch(repo):
        return None
    owner, name = repo.split("/", 1)
    return owner, name


def collect_unavailable(record: dict[str, Any]) -> list[str]:
    missing: list[str] = []
    _maybe_missing_review(record, missing)
    if not any(key in record for key in TIMESTAMP_KEYS):
        missing.append("timestamp")
    if not extract_code_state(record)[0]:
        missing.append("commit_oid")
    if "license" not in record or not nonempty_str(record.get("license")):
        missing.append("license")
    return missing


def _maybe_missing_review(record: dict[str, Any], missing: list[str]) -> None:
    review = record.get("review_signals")
    if not isinstance(review, list) or not review:
        missing.append("review_signals")


# Re-export so existing callers can keep importing timestamps from fields.
__all__ = [
    "collect_unavailable",
    "extract_code_state",
    "extract_timestamp",
    "nonempty_str",
    "split_repo",
]
