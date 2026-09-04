"""Pull-request and closing-issue collection for the source inventory.

Split from :mod:`lib.source_inventory` to keep each module's overall
complexity low; that module re-exports the public surface from here.
"""

from __future__ import annotations

import hashlib
from typing import Any, NamedTuple

from .github_client import GitHubClient, GitHubError
from .secrets import sanitize_text
from .source_inventory_common import _Page, _page_evidence, sha256_json

PULL_REQUESTS_QUERY = """
query InventoryPullRequests($owner: String!, $name: String!, $cursor: String) {
  repository(owner: $owner, name: $name) {
    id
    databaseId
    nameWithOwner
    pullRequests(first: 100, after: $cursor, orderBy: {field: CREATED_AT, direction: ASC}) {
      totalCount
      pageInfo { hasNextPage endCursor }
      nodes {
        id
        databaseId
        number
        url
        state
        isDraft
        title
        bodyText
        createdAt
        updatedAt
        closedAt
        mergedAt
        baseRefOid
        headRefOid
        mergeCommit { oid }
        additions
        deletions
        changedFiles
        author { __typename login }
        labels(first: 100) { totalCount nodes { name } }
        closingIssuesReferences(first: 100) {
          totalCount
          pageInfo { hasNextPage endCursor }
          nodes {
            id
            databaseId
            number
            url
            repository { id databaseId nameWithOwner }
          }
        }
      }
    }
  }
  rateLimit { cost remaining resetAt }
}
"""

CLOSING_ISSUES_QUERY = """
query InventoryClosingIssues($id: ID!, $cursor: String) {
  node(id: $id) {
    ... on PullRequest {
      closingIssuesReferences(first: 100, after: $cursor) {
        totalCount
        pageInfo { hasNextPage endCursor }
        nodes {
          id
          databaseId
          number
          url
          repository { id databaseId nameWithOwner }
        }
      }
    }
  }
  rateLimit { cost remaining resetAt }
}
"""


def _issue_record(raw: dict[str, Any]) -> dict[str, Any]:
    repo = raw.get("repository") or {}
    selected = {
        "id": raw.get("id"),
        "database_id": raw.get("databaseId"),
        "number": raw.get("number"),
        "url": raw.get("url"),
        "repository_id": repo.get("id"),
        "repository_database_id": repo.get("databaseId"),
        "repository_name_with_owner": repo.get("nameWithOwner"),
    }
    selected["source_hash"] = sha256_json(selected)
    return selected


def _sanitize_source_text(value: Any, *, limit: int | None = None) -> tuple[str, list[str]]:
    text = str(value or "")
    sanitized, warnings = sanitize_text(text)
    truncated = limit is not None and len(sanitized) > limit
    if truncated:
        sanitized = sanitized[:limit]
    if truncated:
        warnings.append(f"source_text_truncated_at_{limit}_characters")
    return sanitized, sorted(set(warnings))


def _pull_request_source_hash(raw: dict[str, Any], record: dict[str, Any]) -> str:
    """Hash the complete, sanitized record while binding original source text."""
    payload = {key: value for key, value in record.items() if key != "source_hash"}
    payload["title"] = str(raw.get("title") or "")
    payload["body"] = str(raw.get("bodyText") or "")
    return sha256_json(payload)


def _extract_labels(raw: dict[str, Any], repository: dict[str, Any]) -> list[str]:
    """Return the deduped, sorted label names, rejecting truncated pagination."""
    label_connection = raw.get("labels") or {}
    label_nodes = label_connection.get("nodes") or []
    label_total = int(label_connection.get("totalCount") or 0)
    if len(label_nodes) != label_total:
        raise GitHubError(
            f"Label pagination is incomplete for {repository['name_with_owner']}#{raw.get('number')}: "
            f"expected {label_total}, got {len(label_nodes)}"
        )
    labels = [
        str(node.get("name"))
        for node in label_nodes
        if isinstance(node, dict) and node.get("name")
    ]
    return sorted(set(labels), key=str.casefold)


def _validate_linked_issue_ids(record: dict[str, Any]) -> None:
    """Reject missing or duplicate linked-issue IDs in a pull-request record."""
    ids = [str(item.get("id") or "") for item in record["linked_issues"]]
    has_missing = any(not issue_id for issue_id in ids)
    has_duplicates = len(set(ids)) != len(ids)
    if has_missing or has_duplicates:
        raise GitHubError(
            f"Missing or duplicate linked-issue ID for "
            f"{record['repository_name_with_owner']}#{record['number']}"
        )


def _check_linked_issues_complete(record: dict[str, Any]) -> None:
    if len(record["linked_issues"]) != record["linked_issues_total_count"]:
        raise GitHubError(
            f"Linked-issue count mismatch for "
            f"{record['repository_name_with_owner']}#{record['number']}"
        )
    _validate_linked_issue_ids(record)


def _author_record(raw: dict[str, Any]) -> dict[str, Any]:
    author = raw.get("author") or {}
    return {"login": author.get("login"), "type": author.get("__typename")}


def _linked_issue_records(closing: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        _issue_record(node)
        for node in (closing.get("nodes") or [])
        if isinstance(node, dict)
    ]


def _pull_request_record(raw: dict[str, Any], repository: dict[str, Any]) -> dict[str, Any]:
    title, title_warnings = _sanitize_source_text(raw.get("title"), limit=1024)
    body, body_warnings = _sanitize_source_text(raw.get("bodyText"))
    closing = raw.get("closingIssuesReferences") or {}
    merge_commit = raw.get("mergeCommit") or {}
    selected = {
        "id": raw.get("id"),
        "database_id": raw.get("databaseId"),
        "repository_id": repository["id"],
        "repository_database_id": repository["database_id"],
        "repository_name_with_owner": repository["name_with_owner"],
        "number": raw.get("number"),
        "url": raw.get("url"),
        "state": str(raw.get("state") or "").lower(),
        "draft": bool(raw.get("isDraft")),
        "title": title,
        "body": body,
        "body_sha256": hashlib.sha256(str(raw.get("bodyText") or "").encode("utf-8")).hexdigest(),
        "created_at": raw.get("createdAt"),
        "updated_at": raw.get("updatedAt"),
        "closed_at": raw.get("closedAt"),
        "merged_at": raw.get("mergedAt"),
        "base_oid": raw.get("baseRefOid"),
        "head_oid": raw.get("headRefOid"),
        "merge_commit_oid": merge_commit.get("oid"),
        "additions": raw.get("additions"),
        "deletions": raw.get("deletions"),
        "changed_files": raw.get("changedFiles"),
        "author": _author_record(raw),
        "labels": _extract_labels(raw, repository),
        "linked_issues": _linked_issue_records(closing),
        "linked_issues_total_count": int(closing.get("totalCount") or 0),
        "collection_warnings": sorted(set(title_warnings + body_warnings)),
    }
    _validate_linked_issue_ids(selected)
    selected["source_hash"] = _pull_request_source_hash(raw, selected)
    return selected


def _fetch_closing_issues_page(
    client: GitHubClient,
    pr_id: str,
    cursor: str | None,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, str]]:
    """Fetch one closing-issues page; return (connection, raw data, headers)."""
    if not cursor:
        raise GitHubError(f"Closing-issue pagination for {pr_id} has no cursor")
    data, headers = client.query_graphql(
        CLOSING_ISSUES_QUERY,
        {"id": pr_id, "cursor": cursor},
    )
    node = data.get("node")
    if not isinstance(node, dict):
        raise GitHubError(f"Pull request node {pr_id} disappeared during collection")
    return node.get("closingIssuesReferences") or {}, data, headers


class _ClosingIssuePagination(NamedTuple):
    """Shared state for paginating one PR's closing-issues connection."""

    client: GitHubClient
    pr_id: str
    repository_id: str
    pages: list[dict[str, Any]]
    collected: list[dict[str, Any]]


def _process_closing_issues_page(
    ctx: _ClosingIssuePagination,
    cursor: str | None,
    page_index: int,
) -> tuple[dict[str, Any], str | None]:
    """Fetch and record one closing-issues page; return (page_info, next_cursor)."""
    connection, data, headers = _fetch_closing_issues_page(ctx.client, ctx.pr_id, cursor)
    nodes = connection.get("nodes") or []
    page_info = connection.get("pageInfo") or {}
    next_cursor = page_info.get("endCursor")
    ctx.pages.append(
        _page_evidence(
            _Page(
                scope="closing_issues",
                response=data,
                item_count=len(nodes),
                page_index=page_index,
                has_next_page=bool(page_info.get("hasNextPage")),
                headers=headers,
                repository_id=ctx.repository_id,
                cursor=cursor,
                next_cursor=next_cursor,
                total_count=int(connection.get("totalCount") or 0),
            )
        )
    )
    ctx.collected.extend(_issue_record(item) for item in nodes if isinstance(item, dict))
    if next_cursor == cursor and page_info.get("hasNextPage"):
        raise GitHubError(f"Closing-issue pagination cursor repeated for {ctx.pr_id}")
    return page_info, next_cursor


def _collect_additional_closing_issues(
    ctx: _ClosingIssuePagination,
    first_connection: dict[str, Any],
) -> list[dict[str, Any]]:
    ctx.collected.extend(
        _issue_record(node)
        for node in (first_connection.get("nodes") or [])
        if isinstance(node, dict)
    )
    page_info = first_connection.get("pageInfo") or {}
    cursor = page_info.get("endCursor")
    page_index = 1
    while page_info.get("hasNextPage"):
        page_info, cursor = _process_closing_issues_page(ctx, cursor, page_index)
        page_index += 1
    expected = int(first_connection.get("totalCount") or 0)
    if len(ctx.collected) != expected:
        raise GitHubError(
            f"Closing-issue count mismatch for {ctx.pr_id}: "
            f"expected {expected}, got {len(ctx.collected)}"
        )
    return ctx.collected


def _pull_request_connection(data: dict[str, Any], repository: dict[str, Any]) -> dict[str, Any]:
    """Return the pullRequests connection, guarding repository identity drift."""
    repo_data = data.get("repository")
    if not isinstance(repo_data, dict):
        raise GitHubError(f"Repository {repository['name_with_owner']} disappeared during collection")
    if str(repo_data.get("id") or "") != str(repository["id"]):
        raise GitHubError(f"Repository identity changed for {repository['name_with_owner']}")
    return repo_data.get("pullRequests") or {}


class _PullRequestCrawl(NamedTuple):
    """Shared state for paginating one repository's pull requests."""

    client: GitHubClient
    repository: dict[str, Any]
    pages: list[dict[str, Any]]
    seen_ids: set[str]


def _fetch_pull_request_page(
    crawl: _PullRequestCrawl,
    cursor: str | None,
    expected_total: int | None,
) -> tuple[list[Any], dict[str, Any], int, dict[str, Any], dict[str, str]]:
    """Fetch one pull-request page; return (nodes, page_info, total, data, headers)."""
    owner, name = str(crawl.repository["name_with_owner"]).split("/", 1)
    data, headers = crawl.client.query_graphql(
        PULL_REQUESTS_QUERY,
        {"owner": owner, "name": name, "cursor": cursor},
    )
    connection = _pull_request_connection(data, crawl.repository)
    total_count = int(connection.get("totalCount") or 0)
    if expected_total is not None and expected_total != total_count:
        raise GitHubError(
            f"Pull-request total changed during collection for {crawl.repository['name_with_owner']}"
        )
    return (
        connection.get("nodes") or [],
        connection.get("pageInfo") or {},
        total_count,
        data,
        headers,
    )


def _claim_pr_id(crawl: _PullRequestCrawl, raw: Any) -> str:
    """Validate a raw PR node and claim its node ID in the seen set."""
    if not isinstance(raw, dict):
        raise GitHubError(f"Non-object pull request in {crawl.repository['name_with_owner']}")
    pr_id = str(raw.get("id") or "")
    if not pr_id or pr_id in crawl.seen_ids:
        raise GitHubError(
            f"Missing or duplicate pull-request node ID in {crawl.repository['name_with_owner']}"
        )
    crawl.seen_ids.add(pr_id)
    return pr_id


def _has_more_closing_issues(closing: dict[str, Any]) -> bool:
    return bool((closing.get("pageInfo") or {}).get("hasNextPage"))


def _build_pull_request(crawl: _PullRequestCrawl, raw: Any) -> dict[str, Any]:
    """Validate one raw PR node and build its inventory record."""
    pr_id = _claim_pr_id(crawl, raw)
    closing = raw.get("closingIssuesReferences") or {}
    record = _pull_request_record(raw, crawl.repository)
    if _has_more_closing_issues(closing):
        ctx = _ClosingIssuePagination(
            crawl.client, pr_id, str(crawl.repository["id"]), crawl.pages, []
        )
        record["linked_issues"] = _collect_additional_closing_issues(ctx, closing)
        record["source_hash"] = _pull_request_source_hash(raw, record)
    _check_linked_issues_complete(record)
    return record


def _record_pr_page(
    crawl: _PullRequestCrawl,
    page: tuple[list[Any], dict[str, Any], int, dict[str, Any], dict[str, str]],
    cursor: str | None,
    page_index: int,
) -> tuple[bool, str | None]:
    """Append page evidence; return (has_next, next_cursor)."""
    nodes, page_info, total_count, data, headers = page
    has_next = bool(page_info.get("hasNextPage"))
    next_cursor = page_info.get("endCursor")
    crawl.pages.append(
        _page_evidence(
            _Page(
                scope="pull_requests",
                response=data,
                item_count=len(nodes),
                page_index=page_index,
                has_next_page=has_next,
                headers=headers,
                repository_id=str(crawl.repository["id"]),
                cursor=cursor,
                next_cursor=next_cursor,
                total_count=total_count,
            )
        )
    )
    return has_next, next_cursor


def _advance_pr_cursor(
    repository: dict[str, Any],
    cursor: str | None,
    next_cursor: str | None,
    has_next: bool,
) -> str | None:
    """Return the cursor for the next page, or None when pagination is done."""
    if not has_next:
        return None
    if not next_cursor or next_cursor == cursor:
        raise GitHubError(f"Pull-request pagination cursor stalled for {repository['name_with_owner']}")
    return next_cursor


def _check_pull_request_count(
    repository: dict[str, Any],
    pull_requests: list[dict[str, Any]],
    expected_total: int | None,
) -> None:
    if len(pull_requests) != int(expected_total or 0):
        raise GitHubError(
            f"Pull-request count mismatch for {repository['name_with_owner']}: "
            f"expected {expected_total or 0}, got {len(pull_requests)}"
        )


def _collect_pull_requests(
    client: GitHubClient,
    repository: dict[str, Any],
    pages: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    crawl = _PullRequestCrawl(client, repository, pages, set())
    cursor: str | None = None
    page_index = 0
    expected_total: int | None = None
    pull_requests: list[dict[str, Any]] = []
    while True:
        page = _fetch_pull_request_page(crawl, cursor, expected_total)
        if expected_total is None:
            expected_total = page[2]
        has_next, next_cursor = _record_pr_page(crawl, page, cursor, page_index)
        for raw in page[0]:
            pull_requests.append(_build_pull_request(crawl, raw))
        cursor = _advance_pr_cursor(repository, cursor, next_cursor, has_next)
        if cursor is None:
            break
        page_index += 1
    _check_pull_request_count(repository, pull_requests, expected_total)
    pull_requests.sort(key=lambda row: (str(row["id"]), int(row["number"])))
    return pull_requests
