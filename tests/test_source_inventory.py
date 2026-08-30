from __future__ import annotations

from typing import Any

import pytest

from lib.github_client import GitHubClient, GitHubError
from lib.source_inventory import (
    PULL_REQUESTS_QUERY,
    _pull_request_record,
    collect_source_inventory,
    parse_owner_spec,
)


class FakeInventoryClient(GitHubClient):
    def __init__(self, *, stalled: bool = False):
        super().__init__(token="fixture", base_url="https://api.github.test")
        self.stalled = stalled

    def get_json_with_headers(self, path_or_url: str):
        if "/users/rmems/repos" in path_or_url:
            owner = "rmems"
            repo_id = "R_user"
        elif "/orgs/Limen-Neural/repos" in path_or_url:
            owner = "Limen-Neural"
            repo_id = "R_org"
        else:
            raise AssertionError(path_or_url)
        return (
            [
                {
                    "node_id": repo_id,
                    "id": 1 if owner == "rmems" else 2,
                    "full_name": f"{owner}/repo",
                    "owner": {"login": owner},
                    "name": "repo",
                    "html_url": f"https://github.com/{owner}/repo",
                    "visibility": "public",
                    "private": False,
                    "archived": owner == "Limen-Neural",
                    "disabled": False,
                    "fork": False,
                    "default_branch": "main",
                    "created_at": "2026-01-01T00:00:00Z",
                    "updated_at": "2026-01-02T00:00:00Z",
                    "pushed_at": "2026-01-02T00:00:00Z",
                    "license": {"spdx_id": "MIT", "name": "MIT", "url": None},
                }
            ],
            {"date": "Sun, 30 Aug 2026 12:00:00 GMT"},
        )

    def query_graphql(
        self,
        query: str,
        variables: dict[str, Any] | None = None,
    ):
        assert query == PULL_REQUESTS_QUERY
        assert variables is not None
        repo_id = "R_user" if variables["owner"] == "rmems" else "R_org"
        cursor = variables.get("cursor")
        has_next = self.stalled and cursor is None
        end_cursor = None if self.stalled else "cursor-1"
        return (
            {
                "repository": {
                    "id": repo_id,
                    "databaseId": 1,
                    "nameWithOwner": f"{variables['owner']}/repo",
                    "pullRequests": {
                        "totalCount": 0,
                        "pageInfo": {
                            "hasNextPage": has_next,
                            "endCursor": end_cursor,
                        },
                        "nodes": [],
                    },
                },
                "rateLimit": {"cost": 1, "remaining": 1000, "resetAt": "2026-08-30T13:00:00Z"},
            },
            {"date": "Sun, 30 Aug 2026 12:00:00 GMT"},
        )


def test_parse_owner_spec():
    assert parse_owner_spec("user:rmems") == {"kind": "user", "login": "rmems"}
    assert parse_owner_spec("org:Limen-Neural") == {"kind": "org", "login": "Limen-Neural"}
    with pytest.raises(ValueError, match="expected"):
        parse_owner_spec("rmems")


def test_graphql_client_rejects_mutations_before_network():
    client = GitHubClient(token="fixture")
    with pytest.raises(GitHubError, match="non-query"):
        client.query_graphql("mutation Bad { deleteProjectV2(input: {}) { clientMutationId } }")
    with pytest.raises(GitHubError, match="non-query"):
        client.query_graphql("{ viewer { login } }")
    with pytest.raises(GitHubError, match="non-query"):
        client.query_graphql("query { viewer { login } }")


def test_pull_request_record_rejects_truncated_labels():
    with pytest.raises(GitHubError, match="Label pagination is incomplete"):
        _pull_request_record(
            {
                "number": 7,
                "labels": {"totalCount": 101, "nodes": [{"name": "one"}]},
                "closingIssuesReferences": {"totalCount": 0, "nodes": []},
            },
            {"id": "R1", "database_id": 1, "name_with_owner": "rmems/repo"},
        )


def test_collect_source_inventory_keeps_zero_pr_and_archived_repositories():
    snapshot = collect_source_inventory(
        FakeInventoryClient(),
        ["user:rmems", "org:Limen-Neural"],
        collected_at="2026-08-30T12:00:00Z",
    )
    assert snapshot["collection"] == {
        "complete": True,
        "repository_count": 2,
        "pull_request_count": 0,
        "page_count": 4,
        "private_repositories_ignored": 0,
    }
    assert len(snapshot["repositories"]) == 2
    assert {row["archived"] for row in snapshot["repositories"]} == {False, True}
    assert all(row["pull_request_total_count"] == 0 for row in snapshot["repositories"])
    assert len(snapshot["snapshot_sha256"]) == 64


def test_collect_source_inventory_rejects_stalled_cursor():
    with pytest.raises(GitHubError, match="cursor stalled"):
        collect_source_inventory(
            FakeInventoryClient(stalled=True),
            ["user:rmems"],
            collected_at="2026-08-30T12:00:00Z",
        )
