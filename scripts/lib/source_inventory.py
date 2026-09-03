"""Exhaustive, read-only GitHub source inventory collection.

The live collector deliberately stops at a frozen metadata snapshot.  Ledger
classification happens offline in :mod:`lib.eligibility`, so collection time
and pagination evidence do not make repeated ledger builds nondeterministic.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any

from . import __version__
from .github_client import GitHubClient, GitHubError, _parse_next_link
from .secrets import sanitize_text

SNAPSHOT_SCHEMA_VERSION = "source_inventory_v1"

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


def canonical_json_bytes(value: Any) -> bytes:
    """Return the canonical UTF-8 representation used for source hashes."""
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def sha256_json(value: Any) -> str:
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def _now_utc() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _validate_collected_at(value: str) -> str:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"Invalid collected_at timestamp {value!r}") from exc
    if parsed.tzinfo is None:
        raise ValueError("collected_at timestamp must include a UTC offset")
    return parsed.isoformat()


def parse_owner_spec(value: str) -> dict[str, str]:
    """Parse ``user:login`` or ``org:login`` into a normalized owner record."""
    kind, separator, login = value.strip().partition(":")
    if not separator or kind not in {"user", "org"} or not login.strip():
        raise ValueError(f"Invalid owner {value!r}; expected user:LOGIN or org:LOGIN")
    return {"kind": kind, "login": login.strip()}


def _repository_path(owner: dict[str, str]) -> str:
    login = owner["login"]
    if owner["kind"] == "org":
        return f"/orgs/{login}/repos?type=all&sort=full_name&direction=asc"
    return f"/users/{login}/repos?type=owner&sort=full_name&direction=asc"


def _safe_repository(raw: dict[str, Any], owner: dict[str, str]) -> dict[str, Any]:
    license_obj = raw.get("license") or {}
    selected = {
        "id": raw.get("node_id"),
        "database_id": raw.get("id"),
        "name_with_owner": raw.get("full_name"),
        "owner_login": ((raw.get("owner") or {}).get("login") or owner["login"]),
        "owner_kind": owner["kind"],
        "name": raw.get("name"),
        "url": raw.get("html_url"),
        "visibility": raw.get("visibility") or "public",
        "archived": bool(raw.get("archived")),
        "disabled": bool(raw.get("disabled")),
        "fork": bool(raw.get("fork")),
        "default_branch": raw.get("default_branch"),
        "created_at": raw.get("created_at"),
        "updated_at": raw.get("updated_at"),
        "pushed_at": raw.get("pushed_at"),
        "license": {
            "spdx_id": license_obj.get("spdx_id"),
            "name": license_obj.get("name"),
            "url": license_obj.get("url"),
        },
    }
    selected["source_hash"] = sha256_json(selected)
    return selected


def _repository_source_hash(record: dict[str, Any]) -> str:
    return sha256_json({key: value for key, value in record.items() if key != "source_hash"})


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


def _pull_request_record(raw: dict[str, Any], repository: dict[str, Any]) -> dict[str, Any]:
    title, title_warnings = _sanitize_source_text(raw.get("title"), limit=1024)
    body, body_warnings = _sanitize_source_text(raw.get("bodyText"))
    closing = raw.get("closingIssuesReferences") or {}
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
        "merge_commit_oid": ((raw.get("mergeCommit") or {}).get("oid")),
        "additions": raw.get("additions"),
        "deletions": raw.get("deletions"),
        "changed_files": raw.get("changedFiles"),
        "author": {
            "login": ((raw.get("author") or {}).get("login")),
            "type": ((raw.get("author") or {}).get("__typename")),
        },
        "labels": sorted(set(labels), key=str.casefold),
        "linked_issues": [
            _issue_record(node)
            for node in (closing.get("nodes") or [])
            if isinstance(node, dict)
        ],
        "linked_issues_total_count": int(closing.get("totalCount") or 0),
        "collection_warnings": sorted(set(title_warnings + body_warnings)),
    }
    linked_issue_ids = [str(item.get("id") or "") for item in selected["linked_issues"]]
    if any(not issue_id for issue_id in linked_issue_ids) or len(set(linked_issue_ids)) != len(
        linked_issue_ids
    ):
        raise GitHubError(
            f"Missing or duplicate linked-issue ID for "
            f"{repository['name_with_owner']}#{raw.get('number')}"
        )
    selected["source_hash"] = _pull_request_source_hash(raw, selected)
    return selected


def _page_evidence(
    *,
    scope: str,
    response: Any,
    item_count: int,
    page_index: int,
    has_next_page: bool,
    headers: dict[str, str],
    owner: str | None = None,
    repository_id: str | None = None,
    cursor: str | None = None,
    next_cursor: str | None = None,
    total_count: int | None = None,
) -> dict[str, Any]:
    hashable_response = response
    if isinstance(response, dict) and "rateLimit" in response:
        hashable_response = dict(response)
        hashable_response.pop("rateLimit", None)
    return {
        "scope": scope,
        "owner": owner,
        "repository_id": repository_id,
        "page_index": page_index,
        "cursor": cursor,
        "next_cursor": next_cursor,
        "item_count": item_count,
        "total_count": total_count,
        "has_next_page": has_next_page,
        "server_date": headers.get("date"),
        "response_sha256": sha256_json(hashable_response),
    }


def _collect_repositories(
    client: GitHubClient,
    owners: list[dict[str, str]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], int]:
    repositories: list[dict[str, Any]] = []
    pages: list[dict[str, Any]] = []
    non_public_ignored = 0
    seen_ids: set[str] = set()
    for owner in owners:
        path = _repository_path(owner)
        next_url: str | None = client._resolve_url(path + "&per_page=100")
        page_index = 0
        visited_urls: set[str] = set()
        while next_url:
            if next_url in visited_urls:
                raise GitHubError(f"Repository pagination URL repeated for {owner['login']}")
            visited_urls.add(next_url)
            data, headers = client.get_json_with_headers(next_url)
            if not isinstance(data, list):
                raise GitHubError(f"Expected repository list for {owner['login']}")
            next_link = _parse_next_link(headers.get("link", ""))
            pages.append(
                _page_evidence(
                    scope="repositories",
                    response=data,
                    item_count=len(data),
                    page_index=page_index,
                    has_next_page=bool(next_link),
                    headers=headers,
                    owner=owner["login"],
                )
            )
            for raw in data:
                if not isinstance(raw, dict):
                    raise GitHubError(f"Non-object repository for {owner['login']}")
                if raw.get("private") is True or raw.get("visibility") != "public":
                    non_public_ignored += 1
                    continue
                repo = _safe_repository(raw, owner)
                repo_id = str(repo.get("id") or "")
                if not repo_id or repo_id in seen_ids:
                    raise GitHubError(f"Missing or duplicate repository node ID for {repo.get('name_with_owner')}")
                seen_ids.add(repo_id)
                repositories.append(repo)
            next_url = next_link
            page_index += 1
    repositories.sort(key=lambda row: (str(row["id"]), str(row["name_with_owner"])))
    return repositories, pages, non_public_ignored


def _collect_additional_closing_issues(
    client: GitHubClient,
    pr_id: str,
    first_connection: dict[str, Any],
    pages: list[dict[str, Any]],
    repository_id: str,
) -> list[dict[str, Any]]:
    collected = [
        _issue_record(node)
        for node in (first_connection.get("nodes") or [])
        if isinstance(node, dict)
    ]
    page_info = first_connection.get("pageInfo") or {}
    cursor = page_info.get("endCursor")
    page_index = 1
    while page_info.get("hasNextPage"):
        if not cursor:
            raise GitHubError(f"Closing-issue pagination for {pr_id} has no cursor")
        data, headers = client.query_graphql(
            CLOSING_ISSUES_QUERY,
            {"id": pr_id, "cursor": cursor},
        )
        node = data.get("node")
        if not isinstance(node, dict):
            raise GitHubError(f"Pull request node {pr_id} disappeared during collection")
        connection = node.get("closingIssuesReferences") or {}
        nodes = connection.get("nodes") or []
        new_page_info = connection.get("pageInfo") or {}
        next_cursor = new_page_info.get("endCursor")
        pages.append(
            _page_evidence(
                scope="closing_issues",
                response=data,
                item_count=len(nodes),
                page_index=page_index,
                has_next_page=bool(new_page_info.get("hasNextPage")),
                headers=headers,
                repository_id=repository_id,
                cursor=cursor,
                next_cursor=next_cursor,
                total_count=int(connection.get("totalCount") or 0),
            )
        )
        collected.extend(_issue_record(item) for item in nodes if isinstance(item, dict))
        if next_cursor == cursor and new_page_info.get("hasNextPage"):
            raise GitHubError(f"Closing-issue pagination cursor repeated for {pr_id}")
        cursor = next_cursor
        page_info = new_page_info
        page_index += 1
    expected = int(first_connection.get("totalCount") or 0)
    if len(collected) != expected:
        raise GitHubError(
            f"Closing-issue count mismatch for {pr_id}: expected {expected}, got {len(collected)}"
        )
    return collected


def _collect_pull_requests(
    client: GitHubClient,
    repository: dict[str, Any],
    pages: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    owner, name = str(repository["name_with_owner"]).split("/", 1)
    cursor: str | None = None
    page_index = 0
    expected_total: int | None = None
    pull_requests: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    while True:
        data, headers = client.query_graphql(
            PULL_REQUESTS_QUERY,
            {"owner": owner, "name": name, "cursor": cursor},
        )
        repo_data = data.get("repository")
        if not isinstance(repo_data, dict):
            raise GitHubError(f"Repository {repository['name_with_owner']} disappeared during collection")
        if str(repo_data.get("id") or "") != str(repository["id"]):
            raise GitHubError(f"Repository identity changed for {repository['name_with_owner']}")
        connection = repo_data.get("pullRequests") or {}
        total_count = int(connection.get("totalCount") or 0)
        if expected_total is None:
            expected_total = total_count
        elif expected_total != total_count:
            raise GitHubError(
                f"Pull-request total changed during collection for {repository['name_with_owner']}"
            )
        nodes = connection.get("nodes") or []
        page_info = connection.get("pageInfo") or {}
        has_next = bool(page_info.get("hasNextPage"))
        next_cursor = page_info.get("endCursor")
        pages.append(
            _page_evidence(
                scope="pull_requests",
                response=data,
                item_count=len(nodes),
                page_index=page_index,
                has_next_page=has_next,
                headers=headers,
                repository_id=str(repository["id"]),
                cursor=cursor,
                next_cursor=next_cursor,
                total_count=total_count,
            )
        )
        for raw in nodes:
            if not isinstance(raw, dict):
                raise GitHubError(f"Non-object pull request in {repository['name_with_owner']}")
            pr_id = str(raw.get("id") or "")
            if not pr_id or pr_id in seen_ids:
                raise GitHubError(
                    f"Missing or duplicate pull-request node ID in {repository['name_with_owner']}"
                )
            seen_ids.add(pr_id)
            closing = raw.get("closingIssuesReferences") or {}
            record = _pull_request_record(raw, repository)
            if (closing.get("pageInfo") or {}).get("hasNextPage"):
                record["linked_issues"] = _collect_additional_closing_issues(
                    client,
                    pr_id,
                    closing,
                    pages,
                    str(repository["id"]),
                )
                record["source_hash"] = _pull_request_source_hash(raw, record)
            if len(record["linked_issues"]) != record["linked_issues_total_count"]:
                raise GitHubError(
                    f"Linked-issue count mismatch for {repository['name_with_owner']}#{record['number']}"
                )
            linked_issue_ids = [str(item.get("id") or "") for item in record["linked_issues"]]
            if any(not issue_id for issue_id in linked_issue_ids) or len(
                set(linked_issue_ids)
            ) != len(linked_issue_ids):
                raise GitHubError(
                    f"Missing or duplicate linked-issue ID for "
                    f"{repository['name_with_owner']}#{record['number']}"
                )
            pull_requests.append(record)
        if not has_next:
            break
        if not next_cursor or next_cursor == cursor:
            raise GitHubError(f"Pull-request pagination cursor stalled for {repository['name_with_owner']}")
        cursor = next_cursor
        page_index += 1
    if len(pull_requests) != int(expected_total or 0):
        raise GitHubError(
            f"Pull-request count mismatch for {repository['name_with_owner']}: "
            f"expected {expected_total or 0}, got {len(pull_requests)}"
        )
    pull_requests.sort(key=lambda row: (str(row["id"]), int(row["number"])))
    return pull_requests


def collect_source_inventory(
    client: GitHubClient,
    owner_specs: list[str],
    *,
    collected_at: str | None = None,
) -> dict[str, Any]:
    """Collect a complete public GitHub repository/PR inventory.

    The function either returns a snapshot with ``complete: true`` or raises;
    callers must never publish an incomplete candidate ledger.
    """
    owners = [parse_owner_spec(value) for value in owner_specs]
    if not owners:
        raise ValueError("At least one owner is required")
    owner_keys = {(row["kind"], row["login"].casefold()) for row in owners}
    if len(owner_keys) != len(owners):
        raise ValueError("Duplicate owner specification")
    frozen_collected_at = _validate_collected_at(collected_at) if collected_at else _now_utc()

    repositories, pages, non_public_ignored = _collect_repositories(client, owners)
    pull_requests: list[dict[str, Any]] = []
    for repository in repositories:
        repo_prs = _collect_pull_requests(client, repository, pages)
        repository["pull_request_total_count"] = len(repo_prs)
        repository["source_hash"] = _repository_source_hash(repository)
        pull_requests.extend(repo_prs)

    snapshot = {
        "schema_version": SNAPSHOT_SCHEMA_VERSION,
        "provider": "github",
        "collector_version": __version__,
        "collected_at": frozen_collected_at,
        "owners": owners,
        "collection": {
            "complete": True,
            "repository_count": len(repositories),
            "pull_request_count": len(pull_requests),
            "page_count": len(pages),
            "non_public_repositories_ignored": non_public_ignored,
        },
        "pages": pages,
        "repositories": repositories,
        "pull_requests": sorted(
            pull_requests,
            key=lambda row: (str(row["repository_id"]), str(row["id"])),
        ),
    }
    snapshot["snapshot_sha256"] = sha256_json(snapshot)
    return snapshot
