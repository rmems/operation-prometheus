"""v0 contract checks that allow documented timestamp/OID extensions."""

from __future__ import annotations

from typing import Any

from .migrate_v0_constants import OID_FIELD_MAP, REQUIRED_V0_KEYS, SOURCE_URL_RE, TIMESTAMP_KEYS
from .migrate_v0_fields import nonempty_str, split_repo
from .migrate_v0_text import v0_validator

_DOCUMENTED_EXTENSION_KEYS = frozenset(
    TIMESTAMP_KEYS
    + tuple(src for src, _dest in OID_FIELD_MAP)
    + ("events", "repository")
)


def v0_contract_reason(record: dict[str, Any]) -> str | None:
    """Refuse records that are not a v0 trajectory plus documented extensions."""
    return (
        _required_v0_reason(record)
        or _source_url_reason(record)
        or _schema_reason(record)
    )


def _required_v0_reason(record: dict[str, Any]) -> str | None:
    if any(key not in record for key in REQUIRED_V0_KEYS):
        return "v0_contract"
    if _missing_issue_or_review(record):
        return "v0_contract"
    if _malformed_required_strings(record):
        return "v0_contract"
    if _malformed_pr_number(record.get("pr_number")):
        return "v0_contract"
    return None


def _source_url_reason(record: dict[str, Any]) -> str | None:
    urls = _source_urls(record.get("source_urls"))
    if urls is None:
        return "malformed_source_url"
    if not _canonical_pr_url_present(record, urls):
        return "v0_contract"
    return None


def _schema_reason(record: dict[str, Any]) -> str | None:
    if _nested_v0_schema_invalid(record):
        return "v0_contract"
    return None


def _nested_v0_schema_invalid(record: dict[str, Any]) -> bool:
    core = {
        key: value
        for key, value in record.items()
        if key not in _DOCUMENTED_EXTENSION_KEYS
    }
    return any(v0_validator().iter_errors(core))


def _missing_issue_or_review(record: dict[str, Any]) -> bool:
    has_issue = nonempty_str(record.get("issue_context")) is not None
    review = record.get("review_signals")
    has_review = isinstance(review, list) and bool(review)
    return not has_issue and not has_review


def _malformed_required_strings(record: dict[str, Any]) -> bool:
    for key in ("id", "language", "domain", "task_type", "before_context", "patch", "training_use"):
        if nonempty_str(record.get(key)) is None:
            return True
    return False


def _malformed_pr_number(value: object) -> bool:
    return not isinstance(value, int) or isinstance(value, bool) or value < 1


def _source_urls(value: object) -> list[str] | None:
    if not isinstance(value, list) or not value:
        return None
    urls: list[str] = []
    for item in value:
        if not isinstance(item, str) or not SOURCE_URL_RE.fullmatch(item):
            return None
        urls.append(item)
    return urls


def _canonical_pr_url_present(record: dict[str, Any], urls: list[str]) -> bool:
    parts = split_repo(record.get("repo"))
    if parts is None:
        return False
    owner, name = parts
    expected = f"https://github.com/{owner}/{name}/pull/{record['pr_number']}"
    return any(url.split("#", 1)[0] == expected for url in urls)
