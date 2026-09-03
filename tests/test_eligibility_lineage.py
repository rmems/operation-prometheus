from __future__ import annotations

import pytest

from lib.eligibility_lineage import _lineage


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
