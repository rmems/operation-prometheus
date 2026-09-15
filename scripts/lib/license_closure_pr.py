"""Pull-request provenance and markdown disclosure for source-license closure."""

from __future__ import annotations

import re
from typing import Any

from .license_closure_ids import (
    GIT_OID_RE,
    MARKDOWN_LICENSE_SECTION_RE,
    _sha256_or_none,
    _text,
)
from .source_inventory_common import sha256_json

HTML_COMMENT_RE = re.compile(r"<!--.*?-->", re.DOTALL)


def pr_inventory_row_source_hash(row: dict[str, Any]) -> str:
    """Hash the supplied PR inventory row, excluding ``source_hash``.

    Eligibility producer hashes bind unsanitized GraphQL title/body, which
    published PR rows do not keep. Authenticate the published object used
    for code-state matching instead so a stale digest cannot cover edited
    base/head/merge OIDs.
    """
    payload = {key: value for key, value in row.items() if key != "source_hash"}
    return sha256_json(payload)


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
    container = record.get("repository")
    if not isinstance(container, dict):
        return set()
    oid = _valid_oid(container.get(key))
    return {oid} if oid is not None else set()


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
        if expected is None or any(oid != expected for oid in record_oids):
            return False
    return saw_record_oid


def _pr_inventory_reasons(
    record: dict[str, Any],
    repos: list[str],
    pr_number: int | None,
    pull_requests: dict[tuple[str, int], dict[str, Any]] | None,
) -> list[str]:
    if pull_requests is None:
        return []
    names = [name for name in repos if name]
    if not names or pr_number is None:
        return ["snapshot_provenance_missing"]
    seen: set[str] = set()
    matched: list[dict[str, Any]] = []
    seen_evidence: set[str] = set()
    for name in names:
        folded = name.casefold()
        if folded in seen:
            continue
        seen.add(folded)
        inventory_pr = pull_requests.get((folded, pr_number))
        if inventory_pr is None:
            continue
        evidence = sha256_json(
            {
                "base_oid": inventory_pr.get("base_oid"),
                "head_oid": inventory_pr.get("head_oid"),
                "merge_commit_oid": inventory_pr.get("merge_commit_oid"),
                "number": inventory_pr.get("number"),
            }
        )
        if evidence in seen_evidence:
            continue
        seen_evidence.add(evidence)
        matched.append(inventory_pr)
    if len(matched) > 1:
        raise ValueError(f"Duplicate inventory pull request {names[0]}#{pr_number}")
    if matched and _code_state_matches_inventory_pr(record, matched[0]):
        return []
    return ["snapshot_provenance_missing"]


def _index_pull_requests(
    pull_requests: list[dict[str, Any]] | None,
) -> dict[tuple[str, int], dict[str, Any]]:
    index: dict[tuple[str, int], dict[str, Any]] = {}
    for row in pull_requests or []:
        repo = _text(row.get("repository_name_with_owner")).casefold()
        number = row.get("number")
        if repo and type(number) is int and number >= 1:
            declared = _sha256_or_none(row.get("source_hash"))
            if declared is None or declared != pr_inventory_row_source_hash(row):
                raise ValueError(
                    "pull-request inventory source_hash does not match the published row"
                )
            key = (repo, number)
            if key in index:
                raise ValueError(f"Duplicate inventory pull request {repo}#{number}")
            index[key] = row
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
    next_heading = re.search(r"^#{1,2}\s+", rest, re.MULTILINE)
    if next_heading is None:
        return rest
    return rest[: next_heading.start()]


def _markdown_discloses(markdown: str | None, identifier: str | None) -> bool:
    if markdown is None:
        return True
    section = _markdown_license_section(markdown)
    if section is None or not identifier:
        return False
    visible = HTML_COMMENT_RE.sub("", section)
    pattern = r"(?<![A-Za-z0-9.+-])" + re.escape(identifier) + r"(?![A-Za-z0-9.+-])"
    return re.search(pattern, visible, flags=re.IGNORECASE) is not None
