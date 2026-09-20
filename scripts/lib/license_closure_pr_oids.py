"""PR inventory OIDs, indexing, and source-repo coverage."""

from __future__ import annotations

from typing import Any

from .license_closure_ids import GIT_OID_RE, _sha256_or_none, _text
from .source_inventory_common import sha256_json

_PR_OID_KEYS = ("base_oid", "head_oid", "merge_commit_oid")
_RECORD_TO_PR_ROLE = (
    ("base_oid", "base_oid"),
    ("head_oid", "head_oid"),
    ("commit_oid", "merge_commit_oid"),
    ("merge_commit_oid", "merge_commit_oid"),
)


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
        return text.lower()
    return None


def _record_role_oids(record: dict[str, Any], key: str) -> set[str]:
    container = record.get("repository")
    if not isinstance(container, dict):
        return set()
    oid = _valid_oid(container.get(key))
    return {oid} if oid is not None else set()


def _present_oid_invalid(container: Any, key: str) -> bool:
    if not isinstance(container, dict) or key not in container:
        return False
    return _valid_oid(container[key]) is None


def _present_role_oid_invalid(record: dict[str, Any], key: str) -> bool:
    return _present_oid_invalid(record.get("repository"), key)


def _code_state_matches_inventory_pr(
    record: dict[str, Any],
    inventory_pr: dict[str, Any],
) -> bool:
    if any(_present_oid_invalid(inventory_pr, key) for key in _PR_OID_KEYS):
        return False
    pr_oids = {key: _valid_oid(inventory_pr.get(key)) for key in _PR_OID_KEYS}
    if not any(pr_oids.values()):
        return False
    saw_record_oid = False
    saw_merge = False
    for record_key, pr_key in _RECORD_TO_PR_ROLE:
        if _present_role_oid_invalid(record, record_key):
            return False
        record_oids = _record_role_oids(record, record_key)
        if not record_oids:
            continue
        saw_record_oid = True
        if pr_key == "merge_commit_oid":
            saw_merge = True
        expected = pr_oids[pr_key]
        if expected is None or any(oid != expected for oid in record_oids):
            return False
    return saw_record_oid and saw_merge


def _pr_inventory_reasons(
    record: dict[str, Any],
    repos: list[str],
    provenance: tuple[int | None, dict[tuple[str, int], dict[str, Any]] | None, dict[str, Any] | None],
) -> list[str]:
    pr_number, pull_requests, repository = provenance
    if pull_requests is None:
        return []
    names = [name for name in repos if name]
    if not names or pr_number is None:
        return ["snapshot_provenance_missing"]
    inventory_id = _text((repository or {}).get("repository_id"))
    matched = _matching_inventory_prs(names, pr_number, pull_requests, inventory_id)
    return _matched_pr_reasons(record, names, pr_number, matched)


def _matched_pr_reasons(
    record: dict[str, Any],
    names: list[str],
    pr_number: int,
    matched: list[dict[str, Any]] | None,
) -> list[str]:
    if not matched:
        return ["snapshot_provenance_missing"]
    if len(matched) > 1:
        raise ValueError(f"Duplicate inventory pull request {names[0]}#{pr_number}")
    if _code_state_matches_inventory_pr(record, matched[0]):
        return []
    return ["snapshot_provenance_missing"]


def _pr_evidence_fingerprint(inventory_pr: dict[str, Any]) -> str:
    return sha256_json(
        {
            "base_oid": inventory_pr.get("base_oid"),
            "head_oid": inventory_pr.get("head_oid"),
            "merge_commit_oid": inventory_pr.get("merge_commit_oid"),
            "number": inventory_pr.get("number"),
        }
    )


def _matching_inventory_prs(
    names: list[str],
    pr_number: int,
    pull_requests: dict[tuple[str, int], dict[str, Any]],
    inventory_id: str,
) -> list[dict[str, Any]] | None:
    """Return matched PR rows, or None when a repository-id mismatch fails closed."""
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
        pr_id = _text(inventory_pr.get("repository_id"))
        if _repository_ids_conflict(inventory_id, pr_id):
            return None
        evidence = _pr_evidence_fingerprint(inventory_pr)
        if evidence in seen_evidence:
            continue
        seen_evidence.add(evidence)
        matched.append(inventory_pr)
    return matched


def _repository_ids_conflict(inventory_id: str, pr_id: str) -> bool:
    return all((inventory_id, pr_id)) and inventory_id != pr_id


def _pr_row_key(row: dict[str, Any]) -> tuple[str, int]:
    if not isinstance(row, dict):
        raise ValueError("pull-request inventory rows must be objects")
    repo = _text(row.get("repository_name_with_owner")).casefold()
    number = row.get("number")
    if not repo:
        raise ValueError(
            "pull-request inventory row is missing a repository name or PR number"
        )
    if type(number) is not int or number < 1:
        raise ValueError(
            "pull-request inventory row is missing a repository name or PR number"
        )
    return repo, number


def _index_pull_request_row(
    index: dict[tuple[str, int], dict[str, Any]], row: dict[str, Any]
) -> None:
    key = _pr_row_key(row)
    declared = _sha256_or_none(row.get("source_hash"))
    if declared is None or declared != pr_inventory_row_source_hash(row):
        raise ValueError(
            "pull-request inventory source_hash does not match the published row"
        )
    if key in index:
        raise ValueError(f"Duplicate inventory pull request {key[0]}#{key[1]}")
    index[key] = row


def _index_pull_requests(
    pull_requests: list[dict[str, Any]] | None,
) -> dict[tuple[str, int], dict[str, Any]]:
    index: dict[tuple[str, int], dict[str, Any]] = {}
    for row in pull_requests or []:
        _index_pull_request_row(index, row)
    return index


def _declared_repos(container: dict[str, Any]) -> set[str]:
    names = [_text(container.get("source_repo"))]
    extra = container.get("source_repos")
    if isinstance(extra, list):
        names.extend(_text(item) for item in extra if isinstance(item, str))
    return {name.casefold() for name in names if name}


def _singular_source_repo_invalid(container: dict[str, Any]) -> bool:
    if "source_repo" not in container:
        return False
    singular = container.get("source_repo")
    return not isinstance(singular, str) or not singular.strip()


def _plural_source_repos_invalid(container: dict[str, Any]) -> bool:
    if "source_repos" not in container:
        return False
    extra = container.get("source_repos")
    if not isinstance(extra, list):
        return True
    return any(not isinstance(item, str) or not item.strip() for item in extra)


def _source_coverage_invalid(container: dict[str, Any]) -> bool:
    if _singular_source_repo_invalid(container):
        return True
    if _plural_source_repos_invalid(container):
        return True
    return not _declared_repos(container)
