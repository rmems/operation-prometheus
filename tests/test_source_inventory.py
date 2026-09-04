from __future__ import annotations

import urllib.error
import urllib.request
from typing import Any

import pytest

from lib.github_client import GitHubClient, GitHubError, _SafeRedirectHandler
from lib.source_inventory import (
    CLOSING_ISSUES_QUERY,
    PULL_REQUESTS_QUERY,
    _Page,
    _page_evidence,
    _pull_request_source_hash,
    _pull_request_record,
    _repository_source_hash,
    collect_source_inventory,
    parse_owner_spec,
)


class FakeInventoryClient(GitHubClient):
    def __init__(
        self,
        *,
        stalled: bool = False,
        repeated_repository_page: bool = False,
        include_non_public: bool = False,
    ):
        super().__init__(token="fixture", base_url="https://api.github.test")
        self.stalled = stalled
        self.repeated_repository_page = repeated_repository_page
        self.include_non_public = include_non_public

    def get_json_with_headers(self, path_or_url: str):
        if "/users/rmems/repos" in path_or_url:
            owner = "rmems"
            repo_id = "R_user"
        elif "/orgs/Limen-Neural/repos" in path_or_url:
            owner = "Limen-Neural"
            repo_id = "R_org"
        else:
            raise AssertionError(path_or_url)
        repositories = [
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
        ]
        if self.include_non_public:
            repositories.extend(
                [
                    {
                        **repositories[0],
                        "node_id": f"{repo_id}_internal",
                        "id": 101,
                        "full_name": f"{owner}/internal-repo",
                        "name": "internal-repo",
                        "html_url": f"https://github.com/{owner}/internal-repo",
                        "visibility": "internal",
                    },
                    {
                        **repositories[0],
                        "node_id": f"{repo_id}_private",
                        "id": 102,
                        "full_name": f"{owner}/private-repo",
                        "name": "private-repo",
                        "html_url": f"https://github.com/{owner}/private-repo",
                        "visibility": "private",
                        "private": True,
                    },
                ]
            )
        headers = {"date": "Sun, 30 Aug 2026 12:00:00 GMT"}
        if self.repeated_repository_page:
            headers["link"] = f'<{path_or_url}>; rel="next"'
        return repositories, headers

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


@pytest.mark.parametrize(
    "document",
    [PULL_REQUESTS_QUERY, CLOSING_ISSUES_QUERY],
    ids=["pull_requests", "closing_issues"],
)
def test_production_queries_satisfy_the_read_only_guard(document, monkeypatch):
    client = GitHubClient(token="fixture", max_retries=0)
    calls: list[str] = []

    def fail_after_guard(req, timeout=None):
        calls.append(req.full_url)
        raise urllib.error.URLError("stub")

    monkeypatch.setattr(client._opener, "open", fail_after_guard)
    with pytest.raises(GitHubError, match="network error"):
        client.query_graphql(document, {"owner": "rmems", "name": "repo"})
    assert calls == ["https://api.github.com/graphql"]


@pytest.mark.parametrize(
    "target",
    ["http://api.github.com/graphql", "https://example.invalid/graphql"],
)
def test_redirect_handler_rejects_credential_leaking_targets(target):
    handler = _SafeRedirectHandler()
    request = urllib.request.Request(
        "https://api.github.com/graphql",
        data=b"{}",
        headers={"Authorization": "Bearer fixture"},
        method="POST",
    )
    with pytest.raises(GitHubError, match="Refusing GitHub API redirect"):
        handler.redirect_request(request, None, 302, "Found", {}, target)


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


def test_pull_request_record_preserves_full_body_and_discloses_any_text_limit():
    raw = {
        "number": 7,
        "title": "t" * 1100,
        "bodyText": "b" * 20000,
        "labels": {"totalCount": 0, "nodes": []},
        "closingIssuesReferences": {"totalCount": 0, "nodes": []},
    }
    record = _pull_request_record(
        raw,
        {"id": "R1", "database_id": 1, "name_with_owner": "rmems/repo"},
    )
    assert len(record["body"]) == 20000
    assert len(record["title"]) == 1024
    assert "source_text_truncated_at_1024_characters" in record["collection_warnings"]


def test_pull_request_record_redacts_secret_spanning_title_limit():
    secret = "sk-proj-" + ("x" * 24)
    raw = {
        "number": 7,
        "title": ("t" * 1007) + " " + secret + " " + ("z" * 32),
        "labels": {"totalCount": 0, "nodes": []},
        "closingIssuesReferences": {"totalCount": 0, "nodes": []},
    }

    record = _pull_request_record(
        raw,
        {"id": "R1", "database_id": 1, "name_with_owner": "rmems/repo"},
    )

    assert secret not in record["title"]
    assert "[REDACTED]" in record["title"]
    assert len(record["title"]) == 1024
    assert "redacted_1_secret_matches" in record["collection_warnings"]
    assert "source_text_truncated_at_1024_characters" in record["collection_warnings"]


def test_page_hash_excludes_volatile_rate_limit_telemetry():
    kwargs = {
        "scope": "pull_requests",
        "item_count": 0,
        "page_index": 0,
        "has_next_page": False,
        "headers": {},
    }
    first = _page_evidence(
        _Page(response={"repository": {"id": "R1"}, "rateLimit": {"remaining": 10}}, **kwargs),
    )
    second = _page_evidence(
        _Page(response={"repository": {"id": "R1"}, "rateLimit": {"remaining": 9}}, **kwargs),
    )
    assert first["response_sha256"] == second["response_sha256"]


class ClosingIssuePaginationClient(FakeInventoryClient):
    def __init__(self):
        super().__init__()
        self.pull_raw = {
            "id": "PR1",
            "databaseId": 7,
            "number": 7,
            "url": "https://github.com/rmems/repo/pull/7",
            "state": "MERGED",
            "title": "feat: paginate issue lineage",
            "bodyText": "Closes two issues.",
            "labels": {"totalCount": 0, "nodes": []},
            "closingIssuesReferences": {
                "totalCount": 2,
                "pageInfo": {"hasNextPage": True, "endCursor": "issue-cursor-1"},
                "nodes": [self._issue(1)],
            },
        }

    @staticmethod
    def _issue(number: int) -> dict[str, Any]:
        return {
            "id": f"I{number}",
            "databaseId": number,
            "number": number,
            "url": f"https://github.com/rmems/repo/issues/{number}",
            "repository": {
                "id": "R_user",
                "databaseId": 1,
                "nameWithOwner": "rmems/repo",
            },
        }

    def query_graphql(self, query: str, variables: dict[str, Any] | None = None):
        if query == CLOSING_ISSUES_QUERY:
            return (
                {
                    "node": {
                        "closingIssuesReferences": {
                            "totalCount": 2,
                            "pageInfo": {"hasNextPage": False, "endCursor": "issue-cursor-2"},
                            "nodes": [self._issue(2)],
                        }
                    },
                    "rateLimit": {
                        "cost": 1,
                        "remaining": 999,
                        "resetAt": "2026-08-30T13:00:00Z",
                    },
                },
                {"date": "Sun, 30 Aug 2026 12:00:00 GMT"},
            )
        assert query == PULL_REQUESTS_QUERY
        return (
            {
                "repository": {
                    "id": "R_user",
                    "databaseId": 1,
                    "nameWithOwner": "rmems/repo",
                    "pullRequests": {
                        "totalCount": 1,
                        "pageInfo": {"hasNextPage": False, "endCursor": "pr-cursor-1"},
                        "nodes": [self.pull_raw],
                    },
                },
                "rateLimit": {
                    "cost": 1,
                    "remaining": 1000,
                    "resetAt": "2026-08-30T13:00:00Z",
                },
            },
            {"date": "Sun, 30 Aug 2026 12:00:00 GMT"},
        )


class DuplicateClosingIssuePaginationClient(ClosingIssuePaginationClient):
    def query_graphql(self, query: str, variables: dict[str, Any] | None = None):
        if query != CLOSING_ISSUES_QUERY:
            return super().query_graphql(query, variables)
        return (
            {
                "node": {
                    "closingIssuesReferences": {
                        "totalCount": 2,
                        "pageInfo": {"hasNextPage": False, "endCursor": "issue-cursor-2"},
                        "nodes": [self._issue(1)],
                    }
                },
                "rateLimit": {
                    "cost": 1,
                    "remaining": 999,
                    "resetAt": "2026-08-30T13:00:00Z",
                },
            },
            {"date": "Sun, 30 Aug 2026 12:00:00 GMT"},
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
        "non_public_repositories_ignored": 0,
    }
    assert len(snapshot["repositories"]) == 2
    assert {row["archived"] for row in snapshot["repositories"]} == {False, True}
    assert all(row["pull_request_total_count"] == 0 for row in snapshot["repositories"])
    assert all(
        row["source_hash"] == _repository_source_hash(row) for row in snapshot["repositories"]
    )
    assert len(snapshot["snapshot_sha256"]) == 64


def test_repository_source_hash_changes_with_exhaustive_pull_request_count():
    row = collect_source_inventory(
        FakeInventoryClient(),
        ["user:rmems"],
        collected_at="2026-08-30T12:00:00Z",
    )["repositories"][0]
    changed = {**row, "pull_request_total_count": row["pull_request_total_count"] + 1}
    assert _repository_source_hash(changed) != row["source_hash"]


def test_collect_source_inventory_rejects_stalled_cursor():
    with pytest.raises(GitHubError, match="cursor stalled"):
        collect_source_inventory(
            FakeInventoryClient(stalled=True),
            ["user:rmems"],
            collected_at="2026-08-30T12:00:00Z",
        )


def test_collect_source_inventory_rejects_invalid_fixed_timestamp_before_collection():
    with pytest.raises(ValueError, match="Invalid collected_at"):
        collect_source_inventory(
            FakeInventoryClient(),
            ["user:rmems"],
            collected_at="not-a-timestamp",
        )


def test_collect_source_inventory_normalizes_fixed_timestamp():
    snapshot = collect_source_inventory(
        FakeInventoryClient(),
        ["user:rmems"],
        collected_at="2026-08-30 12:00:00+00:00",
    )

    assert snapshot["collected_at"] == "2026-08-30T12:00:00+00:00"


def test_collect_source_inventory_excludes_every_non_public_visibility():
    snapshot = collect_source_inventory(
        FakeInventoryClient(include_non_public=True),
        ["user:rmems"],
        collected_at="2026-08-30T12:00:00Z",
    )
    assert [row["name_with_owner"] for row in snapshot["repositories"]] == ["rmems/repo"]
    assert snapshot["collection"]["non_public_repositories_ignored"] == 2


def test_collect_source_inventory_rejects_repeated_rest_pagination_url():
    with pytest.raises(GitHubError, match="pagination URL repeated"):
        collect_source_inventory(
            FakeInventoryClient(repeated_repository_page=True),
            ["user:rmems"],
            collected_at="2026-08-30T12:00:00Z",
        )


def test_closing_issue_pagination_recomputes_pull_request_source_hash():
    client = ClosingIssuePaginationClient()
    snapshot = collect_source_inventory(
        client,
        ["user:rmems"],
        collected_at="2026-08-30T12:00:00Z",
    )
    record = snapshot["pull_requests"][0]
    assert len(record["linked_issues"]) == 2
    assert record["source_hash"] == _pull_request_source_hash(client.pull_raw, record)


def test_closing_issue_pagination_rejects_duplicate_immutable_issue_ids():
    with pytest.raises(GitHubError, match="duplicate linked-issue ID"):
        collect_source_inventory(
            DuplicateClosingIssuePaginationClient(),
            ["user:rmems"],
            collected_at="2026-08-30T12:00:00Z",
        )
