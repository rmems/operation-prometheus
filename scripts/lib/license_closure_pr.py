"""Pull-request provenance and markdown disclosure for source-license closure."""

from __future__ import annotations

import re
from typing import Any

from .license_closure_ids import GIT_OID_RE, MARKDOWN_LICENSE_SECTION_RE, _text


def _valid_oid(value: Any) -> str | None:
    text = _text(value)
    if GIT_OID_RE.fullmatch(text):
        return text
    return None


_RECORD_TO_PR_ROLE = (
    ("base_oid", "base_oid"),
    ("head_oid", "head_oid"),
    ("commit_oid", "merge_commit_oid"),
    ("merge_commit_oid", "merge_commit_oid"),
)


def _record_role_oids(record: dict[str, Any], key: str) -> set[str]:
    containers: list[Any] = [record.get("repository")]
    events = record.get("events") if isinstance(record.get("events"), list) else []
    containers.extend(
        event.get("code_state") for event in events if isinstance(event, dict)
    )
    oids: set[str] = set()
    for container in containers:
        if not isinstance(container, dict):
            continue
        oid = _valid_oid(container.get(key))
        if oid is not None:
            oids.add(oid)
    return oids


def _code_state_matches_inventory_pr(
    record: dict[str, Any],
    inventory_pr: dict[str, Any],
) -> bool:
    pr_oids = {
        "base_oid": _valid_oid(inventory_pr.get("base_oid")),
        "head_oid": _valid_oid(inventory_pr.get("head_oid")),
        "merge_commit_oid": _valid_oid(inventory_pr.get("merge_commit_oid")),
    }
    if not any(pr_oids.values()):
        return False
    saw_record_oid = False
    for record_key, pr_key in _RECORD_TO_PR_ROLE:
        record_oids = _record_role_oids(record, record_key)
        if not record_oids:
            continue
        saw_record_oid = True
        expected = pr_oids[pr_key]
        if expected is None and pr_key == "merge_commit_oid":
            expected = pr_oids["head_oid"]
        if expected is None or any(oid != expected for oid in record_oids):
            return False
    return saw_record_oid


def _pr_inventory_reasons(
    record: dict[str, Any],
    repo: str,
    pr_number: int | None,
    pull_requests: dict[tuple[str, int], dict[str, Any]] | None,
) -> list[str]:
    if pull_requests is None:
        return []
    if not repo or pr_number is None:
        return ["snapshot_provenance_missing"]
    inventory_pr = pull_requests.get((repo.casefold(), pr_number))
    if inventory_pr is None or not _code_state_matches_inventory_pr(
        record, inventory_pr
    ):
        return ["snapshot_provenance_missing"]
    return []


def _index_pull_requests(
    pull_requests: list[dict[str, Any]] | None,
) -> dict[tuple[str, int], dict[str, Any]]:
    index: dict[tuple[str, int], dict[str, Any]] = {}
    for row in pull_requests or []:
        repo = _text(row.get("repository_name_with_owner")).casefold()
        number = row.get("number")
        if repo and isinstance(number, int):
            index[(repo, number)] = row
    return index


def _declared_repos(container: dict[str, Any]) -> set[str]:
    names = [_text(container.get("source_repo"))]
    extra = container.get("source_repos")
    if isinstance(extra, list):
        names.extend(_text(item) for item in extra)
    return {name.casefold() for name in names if name}


def _markdown_license_section(markdown: str) -> str | None:
    match = MARKDOWN_LICENSE_SECTION_RE.search(markdown)
    if match is None:
        return None
    rest = markdown[match.end() :]
    next_heading = re.search(r"^##\s+", rest, re.MULTILINE)
    if next_heading is None:
        return rest
    return rest[: next_heading.start()]


def _markdown_discloses(markdown: str | None, identifier: str | None) -> bool:
    if markdown is None:
        return True
    section = _markdown_license_section(markdown)
    if section is None or not identifier:
        return False
    pattern = r"(?<![A-Za-z0-9.+-])" + re.escape(identifier) + r"(?![A-Za-z0-9.+-])"
    return re.search(pattern, section, flags=re.IGNORECASE) is not None
