"""Record identity fields for source-license closure."""

from __future__ import annotations

from typing import Any

from .license_closure_ids import _text


def _nested_record_repo(record: dict[str, Any]) -> str:
    repository = record.get("repository")
    if isinstance(repository, dict):
        owner = _text(repository.get("owner"))
        name = _text(repository.get("name"))
        if owner and name:
            return f"{owner}/{name}"
    return ""


def _nested_identity_invalid(record: dict[str, Any]) -> bool:
    if "repository" not in record:
        return False
    repository = record["repository"]
    if not isinstance(repository, dict):
        return True
    present = [key for key in ("owner", "name") if key in repository]
    if not present:
        return False
    if len(present) != 2:
        return True
    return any(
        not isinstance(repository[key], str) or not repository[key].strip()
        for key in ("owner", "name")
    )


def record_repo(record: dict[str, Any]) -> str:
    return _text(record.get("repo")) or _nested_record_repo(record)


def _top_repo_invalid(record: dict[str, Any]) -> bool:
    if "repo" not in record:
        return False
    value = record["repo"]
    return not isinstance(value, str) or not value.strip()


def record_repo_identities_conflict(record: dict[str, Any]) -> bool:
    if _top_repo_invalid(record) or _nested_identity_invalid(record):
        return True
    top = _text(record.get("repo"))
    nested = _nested_record_repo(record)
    if not top or not nested:
        return False
    return top.casefold() != nested.casefold()


def _supplied_record_id(record: dict[str, Any]) -> str:
    for key in ("id", "trajectory_id"):
        value = _text(record.get(key))
        if value:
            return value
    return ""


def record_ids_conflict(record: dict[str, Any]) -> bool:
    for key in ("id", "trajectory_id"):
        if key not in record:
            continue
        value = record[key]
        if not isinstance(value, str) or not value.strip():
            return True
    record_key = _text(record.get("id"))
    trajectory_key = _text(record.get("trajectory_id"))
    if not all((record_key, trajectory_key)):
        return False
    return record_key != trajectory_key


def _valid_pr_number(value: Any) -> bool:
    return type(value) is int and value >= 1


def _derived_record_id(record: dict[str, Any]) -> str:
    repo = record_repo(record)
    pr_number = record.get("pr_number")
    if repo and _valid_pr_number(pr_number):
        return f"{repo.replace('/', '-')}#{pr_number}"
    return repo or "unknown-record"


def record_id(record: dict[str, Any]) -> str:
    return _supplied_record_id(record) or _derived_record_id(record)


def record_pr_number(record: dict[str, Any]) -> int | None:
    value = record.get("pr_number")
    if type(value) is int and value >= 1:
        return value
    return None


def record_pr_number_invalid(record: dict[str, Any]) -> bool:
    if "pr_number" not in record:
        return False
    value = record["pr_number"]
    if value is None:
        return False
    return not (type(value) is int and value >= 1)


def record_license(record: dict[str, Any]) -> str | None:
    value = record.get("license")
    if not isinstance(value, str):
        return None
    text = value.strip()
    return text or None
