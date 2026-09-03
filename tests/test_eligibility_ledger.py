from __future__ import annotations

import json
from pathlib import Path

import pytest

from build_eligibility_ledger import _validate_artifacts, _validate_inputs
from lib.eligibility import (
    QUALITY_DIMENSIONS,
    _duplicate_records,
    _lineage,
    _load_existing_rows,
    build_eligibility_artifacts,
    infer_task_family,
    render_artifacts,
)
from lib.source_inventory import sha256_json

ROOT = Path(__file__).resolve().parents[1]


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
    author: str = "rmems",
    linked: bool = False,
    draft: bool = False,
) -> dict:
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


def _snapshot() -> dict:
    pulls = [
        _pull_request(
            1,
            state="merged",
            title="feat: add deterministic export pipeline alpha beta gamma",
            linked=True,
        ),
        _pull_request(
            2,
            state="closed",
            title="feat: add deterministic export pipeline alpha beta delta",
        ),
        _pull_request(3, state="open", title="fix: mutable work", draft=True),
        _pull_request(
            4,
            state="merged",
            title="build(deps): bump jsonschema",
            author="dependabot[bot]",
        ),
        _pull_request(5, state="merged", title="docs: refresh overview"),
    ]
    repositories = [
        _repository("R1", "rmems/repo-a", pr_count=5),
        _repository("R2", "Limen-Neural/repo-b", archived=True, pr_count=0),
    ]
    pages = [
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
        "pages": pages,
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


def test_build_assigns_one_fail_closed_state_and_all_quality_dimensions(tmp_path):
    artifacts = build_eligibility_artifacts(_snapshot(), _policy(), _repo_root(tmp_path))
    by_number = {row["pull_request_number"]: row for row in artifacts["candidates"]}
    assert by_number[1]["state"] == "quarantined"
    assert by_number[2]["state"] == "quarantined"
    assert by_number[3]["state"] == "watchlist_open"
    assert by_number[4]["state"] == "excluded"
    assert by_number[5]["state"] == "excluded"
    assert by_number[1]["quality"]["task_hypothesis_clarity"]["assessment"] == "partial"
    assert "formal_issue_reference_without_issue_content" in by_number[1]["quality"][
        "task_hypothesis_clarity"
    ]["reason_codes"]
    for candidate in artifacts["candidates"]:
        assert candidate["primary_reason"] in candidate["reason_codes"]
        assert set(candidate["quality"]) == set(QUALITY_DIMENSIONS)
        assert "quality_score" not in candidate
    assert artifacts["baseline_report"]["complete"] is True


def test_duplicate_and_near_duplicate_reports_are_machine_readable(tmp_path):
    artifacts = build_eligibility_artifacts(_snapshot(), _policy(), _repo_root(tmp_path))
    kinds = {row["kind"] for row in artifacts["duplicates"]}
    assert "current_corpus_duplicate" in kinds
    assert "near_title_match" in kinds
    exact = next(row for row in artifacts["duplicates"] if row["kind"] == "current_corpus_duplicate")
    assert exact["exact"] is True


def test_duplicate_detection_groups_connected_titles_and_exact_titles():
    candidates = [
        {
            "candidate_id": "a",
            "repository_name_with_owner": "rmems/repo",
            "title": "alpha beta gamma delta",
            "base_oid": "base-shared",
            "head_oid": "shared-head",
        },
        {
            "candidate_id": "b",
            "repository_name_with_owner": "rmems/repo",
            "title": "alpha beta gamma epsilon",
            "base_oid": "base-shared",
            "head_oid": "shared-head",
        },
        {
            "candidate_id": "c",
            "repository_name_with_owner": "rmems/repo",
            "title": "alpha beta epsilon zeta",
            "base_oid": "base-c",
            "head_oid": "unique-head",
        },
        {
            "candidate_id": "d",
            "repository_name_with_owner": "rmems/other",
            "title": "identical title tokens here",
            "base_oid": "base-d",
            "head_oid": "head-d",
        },
        {
            "candidate_id": "e",
            "repository_name_with_owner": "rmems/other",
            "title": "identical title tokens here",
            "base_oid": "base-e",
            "head_oid": "head-e",
        },
    ]
    groups = _duplicate_records(candidates, [], {}, near_threshold=0.6)
    shared_head = next(group for group in groups if group["kind"] == "shared_head_oid")
    connected = next(
        group
        for group in groups
        if group["kind"] == "near_title_match" and set(group["candidate_ids"]) == {"a", "b", "c"}
    )
    exact_title = next(group for group in groups if group["kind"] == "exact_title_match")
    assert shared_head["candidate_ids"] == ["a", "b"]
    assert connected["similarity"] == 0.6
    assert exact_title["candidate_ids"] == ["d", "e"]
    assert exact_title["exact"] is True


def test_duplicate_detection_matches_identical_short_titles():
    candidates = [
        {
            "candidate_id": candidate_id,
            "repository_name_with_owner": "rmems/repo",
            "title": title,
            "base_oid": f"base-{candidate_id}",
            "head_oid": f"head-{candidate_id}",
        }
        for candidate_id, title in (("a", "Fix typo"), ("b", "Fix typo"))
    ]

    groups = _duplicate_records(candidates, [], {}, near_threshold=0.6)

    exact_title = next(group for group in groups if group["kind"] == "exact_title_match")
    assert exact_title["candidate_ids"] == ["a", "b"]
    assert exact_title["exact"] is True


def test_duplicate_exactness_preserves_base_state_and_literal_title_differences():
    candidates = [
        {
            "candidate_id": "a",
            "repository_name_with_owner": "rmems/repo",
            "title": "build(deps): bump Ruff from 0.15.13 to 0.16.0",
            "base_oid": "base-a",
            "head_oid": "shared-head",
        },
        {
            "candidate_id": "b",
            "repository_name_with_owner": "rmems/repo",
            "title": "build(deps): bump Ruff from 0.16.2 to 0.16.4",
            "base_oid": "base-b",
            "head_oid": "shared-head",
        },
    ]
    groups = _duplicate_records(candidates, [], {}, near_threshold=0.9)
    shared_head = next(group for group in groups if group["kind"] == "shared_head_oid")
    title_group = next(group for group in groups if group["kind"] == "near_title_match")
    assert shared_head["exact"] is False
    assert shared_head["similarity"] is None
    assert shared_head["evidence"][0]["base_oids"] == ["base-a", "base-b"]
    assert title_group["exact"] is False
    assert title_group["similarity"] == 1.0


def test_repeated_build_is_byte_identical(tmp_path):
    snapshot = _snapshot()
    policy = _policy()
    repo_root = _repo_root(tmp_path)
    first = render_artifacts(build_eligibility_artifacts(snapshot, policy, repo_root))
    second = render_artifacts(build_eligibility_artifacts(snapshot, policy, repo_root))
    assert first == second


def test_lineage_resolves_same_repo_and_qualified_cross_repo_references():
    lineage = _lineage(
        {
            "title": "Reverts https://github.com/Limen-Neural/repo-b/pull/9",
            "body": "Supersedes PR #4.",
            "repository_name_with_owner": "rmems/repo-a",
            "source_hash": "a" * 64,
        },
        {
            ("limen-neural/repo-b", 9): "cross-repo-candidate",
            ("rmems/repo-a", 4): "same-repo-candidate",
        },
    )
    assert [edge["target_candidate_id"] for edge in lineage["reverts"]] == [
        "cross-repo-candidate"
    ]
    assert [edge["target_candidate_id"] for edge in lineage["supersedes"]] == [
        "same-repo-candidate"
    ]


@pytest.mark.parametrize(
    "body",
    [
        "Reverts the behavior described in issue #4.",
        "This reverts the change; fixes #4.",
        "Supersedes issue #4 after validation.",
    ],
)
def test_lineage_does_not_treat_issue_scoped_bare_references_as_pull_requests(body):
    lineage = _lineage(
        {
            "title": "fix: preserve lineage",
            "body": body,
            "repository_name_with_owner": "rmems/repo-a",
            "source_hash": "a" * 64,
        },
        {("rmems/repo-a", 4): "same-repo-candidate"},
    )
    assert lineage["reverts"] == []
    assert lineage["supersedes"] == []


def test_explicit_dependency_author_list_is_retained_but_markers_require_bot_type():
    policy = {"dependency_authors": ["explicit-human"]}
    human_marker = {
        "title": "feat: add user-facing behavior",
        "author": {"login": "human-dependabot-maintainer", "type": "User"},
    }
    explicit = {
        "title": "feat: add user-facing behavior",
        "author": {"login": "explicit-human", "type": "User"},
    }
    bot_marker = {
        "title": "feat: add user-facing behavior",
        "author": {"login": "renovate-helper", "type": "Bot"},
    }
    assert infer_task_family(human_marker, policy)[0] == "feature"
    assert infer_task_family(explicit, policy)[0] == "dependency"
    assert infer_task_family(bot_marker, policy)[0] == "dependency"


def test_snapshot_hash_and_per_repository_counts_fail_closed(tmp_path):
    snapshot = _snapshot()
    snapshot["pull_requests"][0]["title"] = "tampered after freeze"
    with pytest.raises(ValueError, match="sha256 does not match"):
        build_eligibility_artifacts(snapshot, _policy(), _repo_root(tmp_path / "hash"))

    snapshot = _snapshot()
    snapshot["repositories"][0]["pull_request_total_count"] = 4
    snapshot.pop("snapshot_sha256")
    snapshot["snapshot_sha256"] = sha256_json(snapshot)
    with pytest.raises(ValueError, match="Repository pull-request count"):
        build_eligibility_artifacts(snapshot, _policy(), _repo_root(tmp_path / "count"))


def test_policy_schema_requires_the_complete_audit_baseline():
    policy = _policy()
    _validate_inputs(_snapshot(), policy)

    del policy["baseline"]["expected_counts"]["closed_unmerged_pr_count"]
    with pytest.raises(ValueError, match="closed_unmerged_pr_count"):
        _validate_inputs(_snapshot(), policy)


def test_duplicate_baseline_explanation_metrics_fail_closed(tmp_path):
    policy = _policy()
    policy["baseline"]["drift_explanations"] = [
        {
            "metric": "active_public_repository_count",
            "reason_code": "first",
            "countervailing_delta": 0,
            "evidence_refs": ["evidence:first"],
        },
        {
            "metric": "active_public_repository_count",
            "reason_code": "second",
            "countervailing_delta": 1,
            "evidence_refs": ["evidence:second"],
        },
    ]
    _validate_inputs(_snapshot(), policy)
    with pytest.raises(ValueError, match="Duplicate baseline drift explanation metric"):
        build_eligibility_artifacts(_snapshot(), policy, _repo_root(tmp_path))


def test_every_generated_artifact_is_schema_validated(tmp_path):
    artifacts = build_eligibility_artifacts(_snapshot(), _policy(), _repo_root(tmp_path))
    rendered = render_artifacts(artifacts)
    _validate_artifacts(artifacts, rendered)

    artifacts["repositories"][0].pop("repository_id")
    with pytest.raises(ValueError, match=r"repository\[0\].*repository_id"):
        _validate_artifacts(artifacts, render_artifacts(artifacts))


def test_repository_alias_preserves_existing_rows_across_transfer(tmp_path):
    policy = _policy()
    policy["repository_aliases"] = [
        {
            "alias": "legacy/repo-a",
            "repository_id": "R1",
            "canonical_name_with_owner": "rmems/repo-a",
            "evidence_refs": ["https://github.com/legacy/repo-a"],
        }
    ]
    artifacts = build_eligibility_artifacts(
        _snapshot(),
        policy,
        _repo_root(tmp_path, repo="legacy/repo-a"),
    )
    candidate = next(row for row in artifacts["candidates"] if row["pull_request_number"] == 1)
    assert candidate["existing_dataset_refs"][0]["repo"] == "legacy/repo-a"
    assert (
        candidate["existing_dataset_refs"][0]["resolved_repository_name_with_owner"]
        == "rmems/repo-a"
    )
    assert artifacts["baseline_report"]["orphan_existing_dataset_candidates"] == []


def test_repository_alias_resolves_lineage_references(tmp_path):
    snapshot = _snapshot()
    snapshot["pull_requests"][0]["body"] = (
        "Reverts https://github.com/legacy/repo-a/pull/2 after validation."
    )
    snapshot["pull_requests"][0]["source_hash"] = sha256_json(snapshot["pull_requests"][0])
    snapshot.pop("snapshot_sha256")
    snapshot["snapshot_sha256"] = sha256_json(snapshot)
    policy = _policy()
    policy["repository_aliases"] = [
        {
            "alias": "legacy/repo-a",
            "repository_id": "R1",
            "canonical_name_with_owner": "rmems/repo-a",
            "evidence_refs": ["https://github.com/legacy/repo-a"],
        }
    ]
    artifacts = build_eligibility_artifacts(snapshot, policy, _repo_root(tmp_path))
    candidate = next(row for row in artifacts["candidates"] if row["pull_request_number"] == 1)
    assert candidate["lineage"]["reverts"][0]["target_candidate_id"].endswith(":pull:PR2")


def test_terminal_draft_is_not_misclassified_as_open_watchlist(tmp_path):
    snapshot = _snapshot()
    snapshot["pull_requests"][0]["draft"] = True
    snapshot.pop("snapshot_sha256")
    snapshot["snapshot_sha256"] = sha256_json(snapshot)
    artifacts = build_eligibility_artifacts(snapshot, _policy(), _repo_root(tmp_path))
    candidate = next(row for row in artifacts["candidates"] if row["pull_request_number"] == 1)
    assert candidate["source_state"] == "merged"
    assert candidate["state"] == "quarantined"


def test_snapshot_owners_must_match_policy_owners(tmp_path):
    snapshot = _snapshot()
    snapshot["owners"] = [{"kind": "user", "login": "rmems"}]
    snapshot.pop("snapshot_sha256")
    snapshot["snapshot_sha256"] = sha256_json(snapshot)
    with pytest.raises(ValueError, match="owners do not match"):
        build_eligibility_artifacts(snapshot, _policy(), _repo_root(tmp_path))


def test_open_candidate_cannot_be_overridden_as_included_negative(tmp_path):
    policy = _policy()
    policy["overrides"] = [
        {
            "candidate_id": "github:repository:R1:pull:PR3",
            "state": "included_negative",
            "reason_codes": ["explicit_negative"],
            "evidence_refs": ["https://github.com/rmems/repo-a/pull/3"],
        }
    ]
    with pytest.raises(ValueError, match="open candidate as negative"):
        build_eligibility_artifacts(_snapshot(), policy, _repo_root(tmp_path))


def test_baseline_automatic_drift_requires_exact_non_dependency_event_reconciliation(tmp_path):
    snapshot = _snapshot()
    snapshot["pull_requests"][0]["merged_at"] = "2026-08-25T00:00:00Z"
    snapshot["pull_requests"][3]["merged_at"] = "2026-08-26T00:00:00Z"
    snapshot["pull_requests"][4]["merged_at"] = "2026-08-27T00:00:00Z"
    snapshot.pop("snapshot_sha256")
    snapshot["snapshot_sha256"] = sha256_json(snapshot)
    policy = _policy()
    policy["baseline"]["expected_counts"]["merged_non_dependency_pr_count"] = 1
    artifacts = build_eligibility_artifacts(snapshot, policy, _repo_root(tmp_path))
    comparison = next(
        row
        for row in artifacts["baseline_report"]["comparisons"]
        if row["metric"] == "merged_non_dependency_pr_count"
    )
    assert comparison["delta"] == 1
    assert comparison["post_cutoff_event_count"] == 2
    assert comparison["countervailing_delta"] == -1
    assert comparison["explained"] is False


def test_incomplete_snapshot_and_stale_override_fail_closed(tmp_path):
    snapshot = _snapshot()
    snapshot["collection"]["complete"] = False
    with pytest.raises(ValueError, match="incomplete"):
        build_eligibility_artifacts(snapshot, _policy(), _repo_root(tmp_path))

    snapshot = _snapshot()
    policy = _policy()
    policy["overrides"] = [
        {
            "candidate_id": "github:repository:missing:pull:missing",
            "state": "excluded",
            "reason_codes": ["explicit_policy_exclusion"],
            "evidence_refs": ["https://example.invalid/evidence"],
        }
    ]
    with pytest.raises(ValueError, match="stale overrides"):
        build_eligibility_artifacts(snapshot, policy, _repo_root(tmp_path / "second"))


def test_duplicate_override_candidate_ids_fail_closed(tmp_path):
    override = {
        "candidate_id": "github:repository:R1:pull:PR1",
        "state": "excluded",
        "reason_codes": ["explicit_policy_exclusion"],
        "evidence_refs": ["https://example.invalid/evidence"],
    }
    policy = _policy()
    policy["overrides"] = [override, {**override, "state": "quarantined"}]
    with pytest.raises(ValueError, match="duplicate override candidate_id"):
        build_eligibility_artifacts(_snapshot(), policy, _repo_root(tmp_path))


def test_current_repo_regression_detects_grok_ozempic_42_duplicate():
    rows = _load_existing_rows(ROOT)
    matches = [
        row
        for row in rows
        if row["repo"] == "rmems/grok-ozempic" and row["pr_number"] == 42
    ]
    assert len(matches) == 2
    assert len({row["canonical_sha256"] for row in matches}) == 1
