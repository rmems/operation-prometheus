"""Shared builders for eligibility-ledger tests.

Not a test module: imported by the ``test_eligibility_*.py`` files so each
stays focused on one ``lib.eligibility_*`` module.
"""

from __future__ import annotations

import json
from pathlib import Path

from lib.source_inventory import sha256_json


def _repository(
    repo_id: str,
    name: str,
    *,
    archived: bool = False,
    pr_count: int,
) -> dict:
    row = {
        "id": repo_id,
        "database_id": int(repo_id.removeprefix("R")),
        "name_with_owner": name,
        "owner_login": name.split("/", 1)[0],
        "owner_kind": "user" if name.startswith("rmems/") else "org",
        "name": name.split("/", 1)[1],
        "url": f"https://github.com/{name}",
        "visibility": "public",
        "archived": archived,
        "disabled": False,
        "fork": False,
        "default_branch": "main",
        "created_at": "2026-01-01T00:00:00Z",
        "updated_at": "2026-08-30T00:00:00Z",
        "pushed_at": "2026-08-30T00:00:00Z",
        "license": {"spdx_id": "MIT", "name": "MIT", "url": None},
        "pull_request_total_count": pr_count,
    }
    row["source_hash"] = sha256_json(row)
    return row


def _issue(number: int) -> dict:
    row = {
        "id": f"I{number}",
        "database_id": 1000 + number,
        "number": number,
        "url": f"https://github.com/rmems/repo-a/issues/{number}",
        "repository_id": "R1",
        "repository_database_id": 1,
        "repository_name_with_owner": "rmems/repo-a",
    }
    row["source_hash"] = sha256_json(row)
    return row


def _pull_request(
    number: int,
    *,
    state: str,
    title: str,
    options: dict | None = None,
) -> dict:
    options = options or {}
    author = options.get("author", "rmems")
    linked = options.get("linked", False)
    draft = options.get("draft", False)
    terminal = "2026-08-20T00:00:00Z" if state in {"merged", "closed"} else None
    linked_issues = [_issue(100 + number)] if linked else []
    row = {
        "id": f"PR{number}",
        "database_id": 2000 + number,
        "repository_id": "R1",
        "repository_database_id": 1,
        "repository_name_with_owner": "rmems/repo-a",
        "number": number,
        "url": f"https://github.com/rmems/repo-a/pull/{number}",
        "state": state,
        "draft": draft,
        "title": title,
        "body": "Implements a deterministic engineering change with tests.",
        "body_sha256": "b" * 64,
        "created_at": "2026-08-10T00:00:00Z",
        "updated_at": "2026-08-20T00:00:00Z",
        "closed_at": terminal if state == "closed" else None,
        "merged_at": terminal if state == "merged" else None,
        "base_oid": f"{number:040x}",
        "head_oid": f"{number + 100:040x}",
        "merge_commit_oid": f"{number + 200:040x}" if state == "merged" else None,
        "additions": 10,
        "deletions": 2,
        "changed_files": 2,
        "author": {"login": author, "type": "Bot" if author.endswith("[bot]") else "User"},
        "labels": [],
        "linked_issues": linked_issues,
        "linked_issues_total_count": len(linked_issues),
        "collection_warnings": [],
    }
    row["source_hash"] = sha256_json(row)
    return row


def _snapshot_pages() -> list[dict]:
    return [
        {
            "scope": "repositories",
            "owner": "rmems",
            "repository_id": None,
            "page_index": 0,
            "cursor": None,
            "next_cursor": None,
            "item_count": 2,
            "total_count": None,
            "has_next_page": False,
            "server_date": "Sun, 30 Aug 2026 12:00:00 GMT",
            "response_sha256": "a" * 64,
        },
        {
            "scope": "pull_requests",
            "owner": None,
            "repository_id": "R1",
            "page_index": 0,
            "cursor": None,
            "next_cursor": "cursor-1",
            "item_count": 5,
            "total_count": 5,
            "has_next_page": False,
            "server_date": "Sun, 30 Aug 2026 12:00:00 GMT",
            "response_sha256": "c" * 64,
        },
    ]


def _snapshot() -> dict:
    pulls = [
        _pull_request(
            1,
            state="merged",
            title="feat: add deterministic export pipeline alpha beta gamma",
            options={"linked": True},
        ),
        _pull_request(
            2,
            state="closed",
            title="feat: add deterministic export pipeline alpha beta delta",
        ),
        _pull_request(3, state="open", title="fix: mutable work", options={"draft": True}),
        _pull_request(
            4,
            state="merged",
            title="build(deps): bump jsonschema",
            options={"author": "dependabot[bot]"},
        ),
        _pull_request(5, state="merged", title="docs: refresh overview"),
    ]
    repositories = [
        _repository("R1", "rmems/repo-a", pr_count=5),
        _repository("R2", "Limen-Neural/repo-b", archived=True, pr_count=0),
    ]
    snapshot = {
        "schema_version": "source_inventory_v1",
        "provider": "github",
        "collector_version": "0.6.0",
        "collected_at": "2026-08-30T12:00:00Z",
        "owners": [
            {"kind": "user", "login": "rmems"},
            {"kind": "org", "login": "Limen-Neural"},
        ],
        "collection": {
            "complete": True,
            "repository_count": 2,
            "pull_request_count": 5,
            "page_count": 2,
            "non_public_repositories_ignored": 0,
        },
        "pages": _snapshot_pages(),
        "repositories": repositories,
        "pull_requests": pulls,
    }
    snapshot["snapshot_sha256"] = sha256_json(snapshot)
    return snapshot


def _policy() -> dict:
    return {
        "schema_version": "eligibility_policy_v1",
        "policy_version": "fixture-1",
        "owners": [
            {"kind": "user", "login": "rmems"},
            {"kind": "org", "login": "Limen-Neural"},
        ],
        "baseline": {
            "queried_at": "2026-08-24T01:39:05Z",
            "expected_counts": {
                "active_public_repository_count": 1,
                "merged_non_dependency_pr_count": 2,
                "formally_issue_linked_merged_pr_count": 1,
                "closed_unmerged_pr_count": 1,
                "existing_prometheus_row_count": 2,
                "existing_unique_pr_count": 1,
                "exact_current_duplicate_candidate_count": 1,
            },
            "drift_explanations": [],
        },
        "dependency_authors": ["dependabot[bot]"],
        "repository_aliases": [],
        "near_duplicate_threshold": 0.7,
        "overrides": [],
    }


def _repo_root(tmp_path: Path, *, repo: str = "rmems/repo-a") -> Path:
    jsonl = tmp_path / "datasets" / "jsonl"
    jsonl.mkdir(parents=True)
    record = {
        "id": "rmems-repo-a-1",
        "repo": repo,
        "pr_number": 1,
        "source_urls": ["https://github.com/rmems/repo-a/pull/1"],
    }
    encoded = json.dumps(record, separators=(",", ":")) + "\n"
    (jsonl / "a.jsonl").write_text(encoded, encoding="utf-8")
    (jsonl / "b.jsonl").write_text(encoded, encoding="utf-8")
    return tmp_path
