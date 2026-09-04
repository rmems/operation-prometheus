from __future__ import annotations

from eligibility_fixtures import _policy, _repo_root, _snapshot
from lib.eligibility_artifacts import build_eligibility_artifacts
from lib.eligibility_duplicates import _duplicate_records


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
