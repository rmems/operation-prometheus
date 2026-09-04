"""Orchestration: build deterministic eligibility-ledger artifacts from a snapshot."""

from __future__ import annotations

from collections import defaultdict
from pathlib import Path
from typing import Any, NamedTuple

from .eligibility_baseline import _baseline_counts, build_baseline_report
from .eligibility_classification import (
    _automatic_state,
    _override_decision,
    _override_map,
    infer_task_family,
)
from .eligibility_common import (
    LEDGER_SCHEMA_VERSION,
    LEDGER_STATES,
    MANIFEST_SCHEMA_VERSION,
    _or_empty_dict,
    _or_empty_list,
    _source_ref,
    _text,
    candidate_id,
)
from .eligibility_duplicates import _duplicate_records
from .eligibility_existing import _load_existing_rows
from .eligibility_lineage import _lineage, _multi_pr_lineage
from .eligibility_quality import assess_quality
from .eligibility_repositories import _apply_repository_aliases, _repository_row
from .source_inventory import sha256_json


def _validate_snapshot_and_policy(snapshot: dict[str, Any], policy: dict[str, Any]) -> None:
    if snapshot.get("schema_version") != "source_inventory_v1":
        raise ValueError("Unsupported source inventory schema")
    if not (snapshot.get("collection") or {}).get("complete"):
        raise ValueError("Refusing to build a ledger from an incomplete snapshot")
    if policy.get("schema_version") != "eligibility_policy_v1":
        raise ValueError("Unsupported eligibility policy schema")


def _owner_keys(owners: list[Any]) -> set[tuple[str, str]]:
    return {
        (str(row.get("kind") or ""), str(row.get("login") or "").casefold())
        for row in owners
        if isinstance(row, dict)
    }


def _validate_owner_parity(snapshot: dict[str, Any], policy: dict[str, Any]) -> None:
    snapshot_owners = snapshot.get("owners") or []
    policy_owners = policy.get("owners") or []
    snapshot_owner_keys = _owner_keys(snapshot_owners)
    policy_owner_keys = _owner_keys(policy_owners)
    mismatched = any(
        (
            len(snapshot_owner_keys) != len(snapshot_owners),
            len(policy_owner_keys) != len(policy_owners),
            snapshot_owner_keys != policy_owner_keys,
        )
    )
    if mismatched:
        raise ValueError("Source snapshot owners do not match eligibility policy owners")


def _snapshot_hash_payload(snapshot: dict[str, Any]) -> dict[str, Any]:
    payload = dict(snapshot)
    payload.pop("snapshot_sha256", None)
    return payload


def _validate_snapshot_hash(snapshot: dict[str, Any]) -> None:
    declared_snapshot_hash = snapshot.get("snapshot_sha256")
    actual_snapshot_hash = sha256_json(_snapshot_hash_payload(snapshot))
    if not declared_snapshot_hash or declared_snapshot_hash != actual_snapshot_hash:
        raise ValueError(
            "Source snapshot sha256 does not match its canonical content "
            f"(declared={declared_snapshot_hash}, actual={actual_snapshot_hash})"
        )


def _build_repository_index(
    snapshot: dict[str, Any],
    policy: dict[str, Any],
) -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]], dict[str, str]]:
    repositories = [_repository_row(row) for row in (snapshot.get("repositories") or [])]
    repository_by_id = {str(row["repository_id"]): row for row in repositories}
    if len(repository_by_id) != len(repositories):
        raise ValueError("Repository inventory contains missing or duplicate immutable IDs")
    repository_aliases = _apply_repository_aliases(policy, repositories)
    return repositories, repository_by_id, repository_aliases


def _validate_page_conservation(snapshot: dict[str, Any]) -> None:
    collection = snapshot.get("collection") or {}
    pages = snapshot.get("pages") or []
    if len(pages) != int(collection.get("page_count", -1)):
        raise ValueError("Source snapshot pagination evidence count does not conserve")


def _validate_source_id_uniqueness(raw_prs: list[dict[str, Any]]) -> None:
    source_ids = [candidate_id(row) for row in raw_prs]
    if len(set(source_ids)) != len(source_ids):
        raise ValueError("Source snapshot contains duplicate pull-request IDs")


def _validate_conservation(
    snapshot: dict[str, Any],
    raw_prs: list[dict[str, Any]],
    repositories: list[dict[str, Any]],
) -> None:
    collection = snapshot.get("collection") or {}
    _validate_source_id_uniqueness(raw_prs)
    if len(raw_prs) != int(collection.get("pull_request_count", -1)):
        raise ValueError("Source snapshot pull-request count does not conserve")
    if len(repositories) != int(collection.get("repository_count", -1)):
        raise ValueError("Source snapshot repository count does not conserve")


def _pr_counts_by_repository(raw_prs: list[dict[str, Any]]) -> dict[str, int]:
    pull_request_counts: dict[str, int] = defaultdict(int)
    for raw in raw_prs:
        pull_request_counts[str(raw.get("repository_id") or "")] += 1
    return pull_request_counts


def _validate_repository_pr_counts(
    raw_prs: list[dict[str, Any]],
    repositories: list[dict[str, Any]],
) -> None:
    pull_request_counts = _pr_counts_by_repository(raw_prs)
    for repository in repositories:
        repository_id = str(repository["repository_id"])
        declared_count = int(repository["pull_request_total_count"])
        actual_count = pull_request_counts.get(repository_id, 0)
        if declared_count != actual_count:
            raise ValueError(
                "Repository pull-request count does not conserve for "
                f"{repository['name_with_owner']}: declared {declared_count}, actual {actual_count}"
            )


def _expand_alias_entries(
    by_repo_number: dict[tuple[str, int], str],
    repository_aliases: dict[str, str],
) -> None:
    for (repository_name, number), source_id in list(by_repo_number.items()):
        for alias, canonical in repository_aliases.items():
            if canonical == repository_name:
                by_repo_number[(alias, number)] = source_id


def _build_repo_number_index(
    raw_prs: list[dict[str, Any]],
    repository_aliases: dict[str, str],
) -> dict[tuple[str, int], str]:
    by_repo_number = {
        (str(row.get("repository_name_with_owner") or "").casefold(), int(row["number"])): candidate_id(row)
        for row in raw_prs
    }
    if len(by_repo_number) != len(raw_prs):
        raise ValueError("Source snapshot contains duplicate repository/PR aliases")
    _expand_alias_entries(by_repo_number, repository_aliases)
    return by_repo_number


def _resolve_existing_rows(
    repo_root: Path,
    repository_aliases: dict[str, str],
) -> tuple[list[dict[str, Any]], dict[tuple[str, int], list[dict[str, Any]]]]:
    existing_rows = _load_existing_rows(repo_root)
    existing_by_source: dict[tuple[str, int], list[dict[str, Any]]] = defaultdict(list)
    for row in existing_rows:
        repo_key = row["repo"].casefold()
        resolved_repo = repository_aliases.get(repo_key, repo_key)
        row["resolved_repository_name_with_owner"] = resolved_repo
        existing_by_source[(resolved_repo, row["pr_number"])].append(row)
    return existing_rows, existing_by_source


class _CandidateContext(NamedTuple):
    repository_by_id: dict[str, dict[str, Any]]
    policy: dict[str, Any]
    overrides: dict[str, dict[str, Any]]
    by_repo_number: dict[tuple[str, int], str]
    existing_by_source: dict[tuple[str, int], list[dict[str, Any]]]


def _classification(cid: str, raw: dict[str, Any], overrides: dict[str, dict[str, Any]]) -> dict[str, Any]:
    if cid in overrides:
        return {
            "method": "explicit_override",
            "evidence_refs": [str(item) for item in overrides[cid].get("evidence_refs") or []],
        }
    return {
        "method": "deterministic_rules",
        "evidence_refs": [_source_ref(raw)],
    }


def _build_candidate(raw: dict[str, Any], context: _CandidateContext) -> dict[str, Any]:
    cid = candidate_id(raw)
    repository = context.repository_by_id.get(str(raw.get("repository_id")))
    if repository is None:
        raise ValueError(f"Candidate {cid} references an unknown repository")
    task_family, task_basis = infer_task_family(raw, context.policy)
    state, reason_codes = _automatic_state(raw, task_family)
    if cid in context.overrides:
        state, reason_codes = _override_decision(
            cid, _text(raw.get("state")), context.overrides[cid]
        )
    repo_alias = _text(raw.get("repository_name_with_owner"))
    number = int(raw["number"])
    current_refs = context.existing_by_source.get((repo_alias.casefold(), number), [])
    return {
        "schema_version": LEDGER_SCHEMA_VERSION,
        "candidate_id": cid,
        "provider": "github",
        "repository_id": raw.get("repository_id"),
        "repository_database_id": raw.get("repository_database_id"),
        "repository_name_with_owner": repo_alias,
        "pull_request_id": raw.get("id"),
        "pull_request_database_id": raw.get("database_id"),
        "pull_request_number": number,
        "url": raw.get("url"),
        "source_state": raw.get("state"),
        "draft": bool(raw.get("draft")),
        "title": _text(raw.get("title")),
        "body_sha256": raw.get("body_sha256"),
        "created_at": raw.get("created_at"),
        "updated_at": raw.get("updated_at"),
        "closed_at": raw.get("closed_at"),
        "merged_at": raw.get("merged_at"),
        "base_oid": raw.get("base_oid"),
        "head_oid": raw.get("head_oid"),
        "merge_commit_oid": raw.get("merge_commit_oid"),
        "change_summary": {
            "additions": raw.get("additions"),
            "deletions": raw.get("deletions"),
            "changed_files": raw.get("changed_files"),
        },
        "author": _or_empty_dict(raw.get("author")),
        "labels": _or_empty_list(raw.get("labels")),
        "linked_issues": _or_empty_list(raw.get("linked_issues")),
        "state": state,
        "primary_reason": reason_codes[0],
        "reason_codes": sorted(set(reason_codes)),
        "task_family": task_family,
        "task_family_basis": task_basis,
        "lineage": _lineage(raw, context.by_repo_number),
        "quality": assess_quality(raw, repository),
        "existing_dataset_refs": current_refs,
        "duplicate_group_ids": [],
        "source_hash": raw.get("source_hash"),
        "policy_version": context.policy.get("policy_version"),
        "classification": _classification(cid, raw, context.overrides),
    }


def _duplicate_group_index(duplicates: list[dict[str, Any]]) -> dict[str, list[str]]:
    by_candidate: dict[str, list[str]] = defaultdict(list)
    for duplicate in duplicates:
        for cid in duplicate.get("candidate_ids") or []:
            by_candidate[cid].append(duplicate["group_id"])
    return by_candidate


def _attach_duplicate_groups(
    candidates: list[dict[str, Any]],
    duplicates: list[dict[str, Any]],
) -> None:
    by_candidate_duplicate_groups = _duplicate_group_index(duplicates)
    for candidate in candidates:
        candidate["duplicate_group_ids"] = sorted(by_candidate_duplicate_groups[candidate["candidate_id"]])


def _orphan_existing(
    existing_rows: list[dict[str, Any]],
    by_repo_number: dict[tuple[str, int], str],
) -> list[str]:
    return sorted(
        {
            f"{row['repo']}#{row['pr_number']}"
            for row in existing_rows
            if (
                str(row["resolved_repository_name_with_owner"]).casefold(),
                row["pr_number"],
            )
            not in by_repo_number
        }
    )


class _ManifestInputs(NamedTuple):
    snapshot: dict[str, Any]
    policy: dict[str, Any]
    actual_counts: dict[str, int]
    repositories: list[dict[str, Any]]
    candidates: list[dict[str, Any]]
    duplicates: list[dict[str, Any]]
    baseline_report: dict[str, Any]
    orphan_existing: list[str]


def _state_counts(candidates: list[dict[str, Any]]) -> dict[str, int]:
    return {
        state: sum(1 for row in candidates if row["state"] == state)
        for state in sorted(LEDGER_STATES)
    }


def _pagination_block(snapshot: dict[str, Any]) -> dict[str, Any]:
    pages = snapshot.get("pages") or []
    return {
        "page_count": len(pages),
        "page_hashes": [str(row.get("response_sha256")) for row in pages],
        "complete": bool((snapshot.get("collection") or {}).get("complete")),
    }


def _build_manifest(inputs: _ManifestInputs) -> dict[str, Any]:
    snapshot = inputs.snapshot
    return {
        "schema_version": MANIFEST_SCHEMA_VERSION,
        "provider": "github",
        "snapshot_sha256": snapshot.get("snapshot_sha256"),
        "snapshot_collected_at": snapshot.get("collected_at"),
        "collector_version": snapshot.get("collector_version"),
        "policy_version": inputs.policy.get("policy_version"),
        "counts": {
            **inputs.actual_counts,
            "repository_record_count": len(inputs.repositories),
            "candidate_record_count": len(inputs.candidates),
            "duplicate_group_count": len(inputs.duplicates),
            "state_counts": _state_counts(inputs.candidates),
        },
        "pagination": _pagination_block(snapshot),
        "baseline_report_complete": bool(inputs.baseline_report["complete"]),
        "orphan_existing_dataset_candidates": inputs.orphan_existing,
    }


def build_eligibility_artifacts(
    snapshot: dict[str, Any],
    policy: dict[str, Any],
    repo_root: Path,
) -> dict[str, Any]:
    """Return all deterministic ledger artifacts as Python values."""
    _validate_snapshot_and_policy(snapshot, policy)
    _validate_owner_parity(snapshot, policy)
    _validate_snapshot_hash(snapshot)
    _validate_page_conservation(snapshot)

    raw_prs = snapshot.get("pull_requests") or []
    repositories, repository_by_id, repository_aliases = _build_repository_index(
        snapshot, policy
    )
    _validate_conservation(snapshot, raw_prs, repositories)
    _validate_repository_pr_counts(raw_prs, repositories)
    by_repo_number = _build_repo_number_index(raw_prs, repository_aliases)

    overrides = _override_map(policy)
    source_ids = [candidate_id(row) for row in raw_prs]
    stale_overrides = sorted(set(overrides) - set(source_ids))
    if stale_overrides:
        raise ValueError(f"Eligibility policy has stale overrides: {stale_overrides}")

    existing_rows, existing_by_source = _resolve_existing_rows(repo_root, repository_aliases)

    candidate_context = _CandidateContext(
        repository_by_id, policy, overrides, by_repo_number, existing_by_source
    )
    candidates = [_build_candidate(raw, candidate_context) for raw in raw_prs]
    candidates.sort(key=lambda row: row["candidate_id"])
    _multi_pr_lineage(candidates)

    duplicates = _duplicate_records(
        candidates,
        existing_rows,
        by_repo_number,
        near_threshold=float(policy.get("near_duplicate_threshold") or 0.9),
    )
    _attach_duplicate_groups(candidates, duplicates)

    policy_for_report = dict(policy)
    policy_for_report["snapshot_collected_at"] = snapshot.get("collected_at")
    actual_counts = _baseline_counts(repositories, candidates, existing_rows, duplicates)
    baseline_report = build_baseline_report(
        policy_for_report,
        actual_counts,
        repositories,
        candidates,
    )
    orphan_existing = _orphan_existing(existing_rows, by_repo_number)
    baseline_report["orphan_existing_dataset_candidates"] = orphan_existing

    manifest = _build_manifest(
        _ManifestInputs(
            snapshot,
            policy,
            actual_counts,
            repositories,
            candidates,
            duplicates,
            baseline_report,
            orphan_existing,
        )
    )
    return {
        "repositories": repositories,
        "candidates": candidates,
        "duplicates": duplicates,
        "baseline_report": baseline_report,
        "manifest": manifest,
    }
