"""Exhaustive, read-only GitHub source inventory collection.

The live collector deliberately stops at a frozen metadata snapshot.  Ledger
classification happens offline in :mod:`lib.eligibility`, so collection time
and pagination evidence do not make repeated ledger builds nondeterministic.

Facade module: hashing/page-evidence primitives live in
:mod:`lib.source_inventory_common` and pull-request collection in
:mod:`lib.source_inventory_pull_requests`. Every name previously importable
from here still is.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, NamedTuple

from . import __version__
from .github_client import GitHubClient, GitHubError, _parse_next_link
from .source_inventory_common import (
    _Page as _Page,
    _page_evidence as _page_evidence,
    canonical_json_bytes,
    sha256_json,
)
from .source_inventory_pull_requests import (
    CLOSING_ISSUES_QUERY as CLOSING_ISSUES_QUERY,
    PULL_REQUESTS_QUERY as PULL_REQUESTS_QUERY,
    _collect_pull_requests,
    _pull_request_record as _pull_request_record,
    _pull_request_source_hash as _pull_request_source_hash,
)

SNAPSHOT_SCHEMA_VERSION = "source_inventory_v1"

__all__ = [
    "CLOSING_ISSUES_QUERY",
    "PULL_REQUESTS_QUERY",
    "SNAPSHOT_SCHEMA_VERSION",
    "_Page",
    "_page_evidence",
    "_pull_request_record",
    "_pull_request_source_hash",
    "canonical_json_bytes",
    "collect_source_inventory",
    "parse_owner_spec",
    "sha256_json",
]


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
    if not separator:
        raise ValueError(f"Invalid owner {value!r}; expected user:LOGIN or org:LOGIN")
    if kind not in {"user", "org"}:
        raise ValueError(f"Invalid owner {value!r}; expected user:LOGIN or org:LOGIN")
    if not login.strip():
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


def _is_non_public(raw: dict[str, Any]) -> bool:
    return raw.get("private") is True or raw.get("visibility") != "public"


def _accept_repository(
    raw: Any,
    owner: dict[str, str],
    seen_ids: set[str],
) -> dict[str, Any] | None:
    """Validate one raw repository; return None when it is not public."""
    if not isinstance(raw, dict):
        raise GitHubError(f"Non-object repository for {owner['login']}")
    if _is_non_public(raw):
        return None
    repo = _safe_repository(raw, owner)
    repo_id = str(repo.get("id") or "")
    if not repo_id or repo_id in seen_ids:
        raise GitHubError(f"Missing or duplicate repository node ID for {repo.get('name_with_owner')}")
    seen_ids.add(repo_id)
    return repo


class _RepositoryCrawl(NamedTuple):
    """Shared state for paginating an owner's repository list."""

    client: GitHubClient
    owner: dict[str, str]
    pages: list[dict[str, Any]]
    seen_ids: set[str]


def _collect_repository_page(
    crawl: _RepositoryCrawl,
    url: str,
    page_index: int,
) -> tuple[list[dict[str, Any]], int, str | None]:
    """Collect one REST page of repositories; return (repos, ignored, next_url)."""
    data, headers = crawl.client.get_json_with_headers(url)
    if not isinstance(data, list):
        raise GitHubError(f"Expected repository list for {crawl.owner['login']}")
    next_link = _parse_next_link(headers.get("link", ""))
    crawl.pages.append(
        _page_evidence(
            _Page(
                scope="repositories",
                response=data,
                item_count=len(data),
                page_index=page_index,
                has_next_page=bool(next_link),
                headers=headers,
                owner=crawl.owner["login"],
            )
        )
    )
    repositories: list[dict[str, Any]] = []
    non_public_ignored = 0
    for raw in data:
        repo = _accept_repository(raw, crawl.owner, crawl.seen_ids)
        if repo is None:
            non_public_ignored += 1
        else:
            repositories.append(repo)
    return repositories, non_public_ignored, next_link


def _collect_repositories(
    client: GitHubClient,
    owners: list[dict[str, str]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], int]:
    repositories: list[dict[str, Any]] = []
    pages: list[dict[str, Any]] = []
    non_public_ignored = 0
    seen_ids: set[str] = set()
    for owner in owners:
        crawl = _RepositoryCrawl(client, owner, pages, seen_ids)
        path = _repository_path(owner)
        next_url: str | None = client.resolve_url(path + "&per_page=100")
        page_index = 0
        visited_urls: set[str] = set()
        while next_url:
            if next_url in visited_urls:
                raise GitHubError(f"Repository pagination URL repeated for {owner['login']}")
            visited_urls.add(next_url)
            page_repos, page_ignored, next_url = _collect_repository_page(
                crawl, next_url, page_index
            )
            repositories.extend(page_repos)
            non_public_ignored += page_ignored
            page_index += 1
    repositories.sort(key=lambda row: (str(row["id"]), str(row["name_with_owner"])))
    return repositories, pages, non_public_ignored


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
