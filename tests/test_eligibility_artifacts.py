from __future__ import annotations

import pytest

from build_eligibility_ledger import _validate_artifacts, _validate_inputs
from eligibility_fixtures import _policy, _repo_root, _snapshot
from lib.eligibility_artifacts import build_eligibility_artifacts
from lib.eligibility_quality import QUALITY_DIMENSIONS
from lib.eligibility_render import render_artifacts
from lib.source_inventory import sha256_json


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


def test_repeated_build_is_byte_identical(tmp_path):
    snapshot = _snapshot()
    policy = _policy()
    repo_root = _repo_root(tmp_path)
    first = render_artifacts(build_eligibility_artifacts(snapshot, policy, repo_root))
    second = render_artifacts(build_eligibility_artifacts(snapshot, policy, repo_root))
    assert first == second


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


def test_snapshot_owners_must_match_policy_owners(tmp_path):
    snapshot = _snapshot()
    snapshot["owners"] = [{"kind": "user", "login": "rmems"}]
    snapshot.pop("snapshot_sha256")
    snapshot["snapshot_sha256"] = sha256_json(snapshot)
    with pytest.raises(ValueError, match="owners do not match"):
        build_eligibility_artifacts(snapshot, _policy(), _repo_root(tmp_path))


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
