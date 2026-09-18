"""Assemble and write raw PR collection records."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from . import __version__
from .cas import ArtifactSpec, ContentAddressedStore
from .collect_events import (
    collect_check_suites,
    collect_commit_statuses,
    collect_timeline,
    detect_revert_state,
    slim_check_run,
)
from .github_client import GitHubClient, GitHubError, _parse_next_link, parse_repo
from .secrets import scan_and_sanitize_obj
from .snapshots import GitFetch, SnapshotScope, collect_snapshots

# GitHub closing keywords (present + past tense + gerund + singular).
# Optional colon form is documented by GitHub: "Closes: #10".
# Also accept markdown emphasis: **Closes:** #10
_CLOSE_KW = r"(?:close[sd]?|closing|fix(?:e[sd])?|fixing|resolve[sd]?|resolving)"
_CLOSE_SEP = r"(?:\*+)?(?::\*+|:)?\**\s+"
# Single "#N" after a close keyword.
CLOSES_RE = re.compile(rf"(?i)\b{_CLOSE_KW}{_CLOSE_SEP}#(\d+)\b")
# Multi-issue lists: "Closes: #75, #76, and #85" or "closing #80, #83, #84"
CLOSES_LIST_RE = re.compile(
    rf"(?i)\b{_CLOSE_KW}{_CLOSE_SEP}"
    r"#(\d+)(?:\s*[,/]\s*(?:and\s+)?#(\d+))*"
    r"(?:\s+and\s+#(\d+))?"
)
CLOSES_FULL_RE = re.compile(
    rf"(?i)\b{_CLOSE_KW}{_CLOSE_SEP}"
    r"https://github\.com/([\w.-]+)/([\w.-]+)/issues/(\d+)\b"
)
CLOSES_CROSS_RE = re.compile(
    rf"(?i)\b{_CLOSE_KW}{_CLOSE_SEP}([\w.-]+)/([\w.-]+)#(\d+)\b"
)

DEFAULT_MAX_INLINE_DIFF = 256 * 1024

# Default cross-repository issue fetching allowlist (owner/repo format).
# Runtime allowlist is the union of this constant and collect_pr(..., options.cross_repo_allowlist).
CROSS_REPO_ALLOWLIST: tuple[str, ...] = (
    # Add approved cross-repo references here, e.g.:
    # "rmems/operation-prometheus",
)


@dataclass
class CollectOptions:
    """Flags for a single PR collection (keeps ``collect_pr`` at ≤4 args)."""

    include_checks: bool = True
    include_diff: bool = True
    include_timeline: bool = True
    include_snapshots: bool = False
    artifact_store: ContentAddressedStore | None = None
    cross_repo_allowlist: tuple[str, ...] | list[str] | None = None


@dataclass
class _IssueFetch:
    client: GitHubClient
    owner: str
    name: str
    allowlist: set[str]


def _norm_repo(repo: str) -> str:
    """Case-fold owner/repo for allowlist and same-repo comparisons."""
    return str(repo).strip().lower()


def _user_login(obj: dict | None) -> str | None:
    if not obj:
        return None
    return obj.get("login")


def _cross_repo_allowlist(options: CollectOptions) -> set[str]:
    allowlist = {_norm_repo(x) for x in CROSS_REPO_ALLOWLIST if str(x).strip()}
    for entry in options.cross_repo_allowlist or ():
        text = str(entry).strip()
        if text:
            allowlist.add(_norm_repo(text))
    return allowlist


def _slim_comment(c: dict) -> dict:
    user = c.get("user") or {}
    return {
        "id": c.get("id"),
        "user_login": user.get("login"),
        "user_type": user.get("type"),
        "created_at": c.get("created_at"),
        "updated_at": c.get("updated_at"),
        "html_url": c.get("html_url"),
        "body": c.get("body") or "",
        "author_association": c.get("author_association"),
    }


def _slim_review_comment(c: dict) -> dict:
    user = c.get("user") or {}
    return {
        "id": c.get("id"),
        "user_login": user.get("login"),
        "user_type": user.get("type"),
        "path": c.get("path"),
        "line": c.get("line") if c.get("line") is not None else c.get("original_line"),
        "original_line": c.get("original_line"),
        "start_line": c.get("start_line"),
        "original_start_line": c.get("original_start_line"),
        "side": c.get("side"),
        "start_side": c.get("start_side"),
        "position": c.get("position"),
        "original_position": c.get("original_position"),
        "body": c.get("body") or "",
        "diff_hunk": c.get("diff_hunk"),
        "created_at": c.get("created_at"),
        "updated_at": c.get("updated_at"),
        "in_reply_to_id": c.get("in_reply_to_id"),
        "pull_request_review_id": c.get("pull_request_review_id"),
        "commit_id": c.get("commit_id"),
        "original_commit_id": c.get("original_commit_id"),
        "subject_type": c.get("subject_type"),
        "html_url": c.get("html_url"),
        "author_association": c.get("author_association"),
    }


def _slim_review(r: dict) -> dict:
    user = r.get("user") or {}
    return {
        "id": r.get("id"),
        "user_login": user.get("login"),
        "user_type": user.get("type"),
        "state": r.get("state"),
        "body": r.get("body") or "",
        "submitted_at": r.get("submitted_at"),
        "commit_id": r.get("commit_id"),
        "html_url": r.get("html_url"),
        "author_association": r.get("author_association"),
    }


def _slim_commit(c: dict) -> dict:
    commit = c.get("commit") or {}
    author = commit.get("author") or {}
    tree = commit.get("tree") if isinstance(commit.get("tree"), dict) else {}
    parents = commit.get("parents") if isinstance(commit.get("parents"), list) else []
    return {
        "sha": c.get("sha"),
        "message": commit.get("message") or "",
        "author_login": _user_login(c.get("author")),
        "author_type": (c.get("author") or {}).get("type") if isinstance(c.get("author"), dict) else None,
        "date": author.get("date"),
        "tree_oid": tree.get("sha"),
        "parent_oids": [p.get("sha") for p in parents if isinstance(p, dict) and p.get("sha")],
    }


def _slim_file(f: dict) -> dict:
    patch = f.get("patch")
    return {
        "filename": f.get("filename"),
        "previous_filename": f.get("previous_filename"),
        "status": f.get("status"),
        "additions": f.get("additions"),
        "deletions": f.get("deletions"),
        "changes": f.get("changes"),
        "sha": f.get("sha"),
        "blob_url": f.get("blob_url"),
        "patch": patch,
        "patch_truncated": patch is None and f.get("status") != "removed",
    }


def parse_linked_issue_numbers(body: str | None, default_owner: str, default_repo: str) -> list[tuple[str, str, int]]:
    """Return list of (owner, repo, number) referenced as closed by the PR body."""
    if not body:
        return []
    found: list[tuple[str, str, int]] = []
    seen: set[tuple[str, str, int]] = set()

    def _add(owner: str, repo: str, num: int) -> None:
        key = (owner, repo, num)
        if key not in seen:
            seen.add(key)
            found.append(key)

    # Prefer multi-issue lists so "#75, #76, #85" after Closes is fully captured.
    for m in CLOSES_LIST_RE.finditer(body):
        for g in m.groups():
            if g:
                _add(default_owner, default_repo, int(g))
        # Also pull any extra #N tokens in the matched span (handles long lists).
        for n in re.findall(r"#(\d+)\b", m.group(0)):
            _add(default_owner, default_repo, int(n))
    for m in CLOSES_RE.finditer(body):
        _add(default_owner, default_repo, int(m.group(1)))
    for m in CLOSES_FULL_RE.finditer(body):
        _add(m.group(1), m.group(2), int(m.group(3)))
    for m in CLOSES_CROSS_RE.finditer(body):
        _add(m.group(1), m.group(2), int(m.group(3)))
    return found


def _reject_private_repos(pull: dict[str, Any], full: str, pr_number: int) -> None:
    for side in ("base", "head"):
        repo_meta = (pull.get(side) or {}).get("repo") or {}
        if isinstance(repo_meta, dict) and repo_meta.get("private") is True:
            side_full = repo_meta.get("full_name") or full
            raise GitHubError(
                f"Refusing to collect private repository {side_full} "
                f"(PR {full}#{pr_number} {side}). "
                "Operation Prometheus only extracts public GitHub history."
            )


def _fetch_diff(client: GitHubClient, full: str, pr_number: int) -> tuple[str | None, list[str], list[str]]:
    try:
        return client.get_text(f"/repos/{full}/pulls/{pr_number}"), [], ["diff"]
    except GitHubError as exc:
        return None, [f"diff_fetch_failed: {exc}"], []


def _empty_checks() -> dict[str, Any]:
    return {
        "check_runs": [],
        "check_suites": [],
        "combined_status": None,
        "commit_statuses": [],
    }


def _collect_check_runs(
    client: GitHubClient,
    full: str,
    head_sha: str,
) -> tuple[list[dict[str, Any]], list[str]]:
    runs: list[dict[str, Any]] = []
    warnings: list[str] = []
    total_count: int | None = None
    next_url: str | None = f"/repos/{full}/commits/{head_sha}/check-runs?per_page=100"
    while next_url:
        cr, headers = client.get_json_with_headers(next_url)
        if total_count is None:
            total_count = (cr or {}).get("total_count")
        runs.extend((cr or {}).get("check_runs") or [])
        next_url = _parse_next_link(headers.get("link", ""))
    if total_count is not None and total_count > len(runs):
        warnings.append(
            f"check_runs_truncated: total_count={total_count} collected={len(runs)}"
        )
    return [slim_check_run(r) for r in runs if isinstance(r, dict)], warnings


def _collect_combined_status(
    client: GitHubClient,
    full: str,
    head_sha: str,
) -> tuple[dict[str, Any] | None, list[str]]:
    try:
        status = client.get_json(f"/repos/{full}/commits/{head_sha}/status")
    except GitHubError as exc:
        return None, [f"combined_status_failed: {exc}"]
    return {
        "state": status.get("state"),
        "sha": status.get("sha") or head_sha,
        "statuses": [
            {
                "context": s.get("context"),
                "state": s.get("state"),
                "description": s.get("description"),
                "created_at": s.get("created_at"),
            }
            for s in (status.get("statuses") or [])
        ],
    }, []


def _maybe_endpoint(name: str, items: Any, warnings: list[str]) -> list[str]:
    if items or not warnings:
        return [name]
    return []


def _collect_checks(
    client: GitHubClient,
    full: str,
    head_sha: str,
) -> tuple[dict[str, Any], list[str], list[str]]:
    checks = _empty_checks()
    warnings: list[str] = []
    endpoints: list[str] = []
    try:
        runs, run_warnings = _collect_check_runs(client, full, head_sha)
        checks["check_runs"] = runs
        warnings.extend(run_warnings)
        endpoints.append("check_runs")
    except GitHubError as exc:
        warnings.append(f"check_runs_failed: {exc}")
    combined, status_warnings = _collect_combined_status(client, full, head_sha)
    if combined is not None:
        checks["combined_status"] = combined
        endpoints.append("combined_status")
    warnings.extend(status_warnings)
    suites, suite_warnings = collect_check_suites(client, full, head_sha)
    checks["check_suites"] = suites
    warnings.extend(suite_warnings)
    endpoints.extend(_maybe_endpoint("check_suites", suites, suite_warnings))
    statuses, commit_status_warnings = collect_commit_statuses(client, full, head_sha)
    checks["commit_statuses"] = statuses
    warnings.extend(commit_status_warnings)
    endpoints.extend(_maybe_endpoint("commit_statuses", statuses, commit_status_warnings))
    return checks, warnings, endpoints


def _commit_message(commit: Any) -> str | None:
    if not isinstance(commit, dict):
        return None
    msg = (commit.get("commit") or {}).get("message") if isinstance(commit.get("commit"), dict) else None
    return str(msg or commit.get("message") or "") or None


def _link_blob(pull: dict[str, Any], commits: list[Any]) -> str:
    parts = [pull.get("body") or ""]
    for commit in commits:
        msg = _commit_message(commit)
        if msg:
            parts.append(msg)
    return "\n".join(parts)


def _skip_cross_repo(
    target_repo: str,
    source_repo: str,
    allowlist: set[str],
    num: int,
) -> str | None:
    if _norm_repo(target_repo) == _norm_repo(source_repo):
        return None
    if _norm_repo(target_repo) in allowlist:
        return None
    return (
        f"linked_issue_{num}_skipped: cross-repo {target_repo} not in allowlist "
        f"(pass --allow-cross-repo {target_repo})"
    )


def _slim_linked_issue(
    issue: dict[str, Any],
    repo: str,
    comments: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "number": issue.get("number"),
        "repo": repo,
        "title": issue.get("title"),
        "body": issue.get("body") or "",
        "state": issue.get("state"),
        "html_url": issue.get("html_url"),
        "created_at": issue.get("created_at"),
        "closed_at": issue.get("closed_at"),
        "user_login": _user_login(issue.get("user")),
        "user_type": (issue.get("user") or {}).get("type")
        if isinstance(issue.get("user"), dict)
        else None,
        "comments": comments,
        "closed_by_pr": True,
    }


def _linked_issue_comments(
    client: GitHubClient,
    owner: str,
    repo: str,
    num: int,
) -> tuple[list[dict[str, Any]], list[str], list[str]]:
    try:
        comments = [
            _slim_comment(c)
            for c in client.get_all(f"/repos/{owner}/{repo}/issues/{num}/comments")
        ]
        return comments, [], [f"issue_{num}_comments"]
    except GitHubError as exc:
        return [], [f"linked_issue_{num}_comments_failed: {exc}"], []


def _fetch_one_linked_issue(ctx: _IssueFetch, num: int, i_owner: str, i_repo: str) -> tuple[dict[str, Any] | None, list[str], list[str]]:
    warnings: list[str] = []
    endpoints: list[str] = []
    try:
        issue = ctx.client.get_json(f"/repos/{i_owner}/{i_repo}/issues/{num}")
        endpoints.append(f"issue_{num}")
    except GitHubError as exc:
        return None, [f"linked_issue_{num}_failed: {exc}"], []
    if not isinstance(issue, dict) or issue.get("pull_request"):
        return None, warnings, endpoints
    comments, comment_warnings, comment_eps = _linked_issue_comments(
        ctx.client, i_owner, i_repo, num
    )
    warnings.extend(comment_warnings)
    endpoints.extend(comment_eps)
    return _slim_linked_issue(issue, f"{i_owner}/{i_repo}", comments), warnings, endpoints


def _collect_linked_issues(ctx: _IssueFetch, link_blob: str) -> tuple[list[dict[str, Any]], list[str], list[str]]:
    linked: list[dict[str, Any]] = []
    warnings: list[str] = []
    endpoints: list[str] = []
    source_repo = f"{ctx.owner}/{ctx.name}"
    for i_owner, i_repo, num in parse_linked_issue_numbers(link_blob, ctx.owner, ctx.name):
        skip = _skip_cross_repo(f"{i_owner}/{i_repo}", source_repo, ctx.allowlist, num)
        if skip:
            warnings.append(skip)
            continue
        record, issue_warnings, issue_eps = _fetch_one_linked_issue(ctx, num, i_owner, i_repo)
        warnings.extend(issue_warnings)
        endpoints.extend(issue_eps)
        if record:
            linked.append(record)
    return linked, warnings, endpoints


def _slim_pull(pull: dict[str, Any], head_sha: Any) -> dict[str, Any]:
    labels = [lb.get("name") for lb in (pull.get("labels") or []) if lb.get("name")]
    return {
        "title": pull.get("title"),
        "body": pull.get("body") or "",
        "state": pull.get("state"),
        "merged": bool(pull.get("merged")),
        "merged_at": pull.get("merged_at"),
        "created_at": pull.get("created_at"),
        "closed_at": pull.get("closed_at"),
        "updated_at": pull.get("updated_at"),
        "user_login": _user_login(pull.get("user")),
        "user_type": (pull.get("user") or {}).get("type") if isinstance(pull.get("user"), dict) else None,
        "labels": labels,
        "base_sha": (pull.get("base") or {}).get("sha"),
        "head_sha": head_sha,
        "merge_commit_sha": pull.get("merge_commit_sha"),
        "additions": pull.get("additions"),
        "deletions": pull.get("deletions"),
        "changed_files": pull.get("changed_files"),
        "draft": bool(pull.get("draft")),
        "commits": pull.get("commits"),
        "comments": pull.get("comments"),
        "review_comments": pull.get("review_comments"),
    }


def _maybe_snapshots(
    fetch: GitFetch | None,
    scope: SnapshotScope,
    include: bool,
) -> tuple[dict[str, Any] | None, list[str], list[str]]:
    if not include:
        return None, [], []
    if fetch is None:
        return None, ["snapshots_skipped: artifact store required"], []
    snapshots = collect_snapshots(fetch, scope)
    warnings: list[str] = []
    if snapshots.get("quarantine"):
        reasons = ",".join(str(q.get("reason") or "unknown") for q in snapshots["quarantine"][:8])
        warnings.append("snapshots_quarantined: " + reasons)
    return snapshots, warnings, ["git_objects"]


def _usable_diff_text(diff_text: str | None) -> str | None:
    if not isinstance(diff_text, str):
        return None
    if not diff_text:
        return None
    return diff_text


def _maybe_diff_artifact(
    store: ContentAddressedStore | None,
    diff_text: str | None,
    full: str,
    pr_number: int,
) -> dict[str, Any] | None:
    if store is None:
        return None
    text = _usable_diff_text(diff_text)
    if text is None:
        return None
    spec = ArtifactSpec(
        media_type="text/x-diff",
        kind="unified_diff",
        extra={"repo": full, "pr_number": pr_number},
    )
    diff_meta = store.put_text(text, spec)
    return {
        "sha256": diff_meta["sha256"],
        "byte_size": diff_meta["byte_size"],
        "uri": store.uri(diff_meta["sha256"]),
    }


def _evidence_complete(
    include_snapshots: bool,
    snapshots: dict[str, Any] | None,
    warnings: list[str],
) -> bool:
    complete = True
    if include_snapshots:
        complete = bool(snapshots and snapshots.get("complete"))
    if any("truncated" in w for w in warnings):
        return False
    return complete


def collect_pr(
    client: GitHubClient,
    repo: str,
    pr_number: int,
    options: CollectOptions | None = None,
) -> dict[str, Any]:
    """Fetch a full raw trajectory-oriented PR record (read-only).

    ``options.cross_repo_allowlist`` extends (does not replace) ``CROSS_REPO_ALLOWLIST``
    with additional ``owner/repo`` entries that may be fetched for linked issues.

    Extra timeline / check-suite / status events are collected by default so
    chronology can link reviews and checks to a code state.  Git object
    snapshots are opt-in via ``include_snapshots`` and require an artifact store.
    """
    opts = options or CollectOptions()
    owner, name = parse_repo(repo)
    full = f"{owner}/{name}"
    warnings: list[str] = []
    endpoints: list[str] = []
    allowlist = _cross_repo_allowlist(opts)

    pull = client.get_json(f"/repos/{full}/pulls/{pr_number}")
    endpoints.append("pulls")
    if not isinstance(pull, dict):
        raise GitHubError(f"Unexpected pull payload for {full}#{pr_number}")
    _reject_private_repos(pull, full, pr_number)

    issue_comments = client.get_all(f"/repos/{full}/issues/{pr_number}/comments")
    endpoints.append("issue_comments")
    review_comments = client.get_all(f"/repos/{full}/pulls/{pr_number}/comments")
    endpoints.append("review_comments")
    reviews = client.get_all(f"/repos/{full}/pulls/{pr_number}/reviews")
    endpoints.append("reviews")
    commits = client.get_all(f"/repos/{full}/pulls/{pr_number}/commits")
    endpoints.append("commits")
    files = client.get_all(f"/repos/{full}/pulls/{pr_number}/files")
    endpoints.append("files")

    diff_text: str | None = None
    if opts.include_diff:
        diff_text, diff_warnings, diff_eps = _fetch_diff(client, full, pr_number)
        warnings.extend(diff_warnings)
        endpoints.extend(diff_eps)

    checks = _empty_checks()
    head_sha = (pull.get("head") or {}).get("sha")
    if opts.include_checks and head_sha:
        checks, check_warnings, check_eps = _collect_checks(client, full, head_sha)
        warnings.extend(check_warnings)
        endpoints.extend(check_eps)

    timeline: list[dict[str, Any]] = []
    if opts.include_timeline:
        timeline, timeline_warnings = collect_timeline(client, full, pr_number)
        warnings.extend(timeline_warnings)
        endpoints.extend(_maybe_endpoint("timeline", timeline, timeline_warnings))

    issue_ctx = _IssueFetch(client=client, owner=owner, name=name, allowlist=allowlist)
    linked, linked_warnings, linked_eps = _collect_linked_issues(ctx=issue_ctx, link_blob=_link_blob(pull, commits))
    warnings.extend(linked_warnings)
    endpoints.extend(linked_eps)

    slim_commits = [_slim_commit(c) for c in commits]
    slim_reviews = [_slim_review(r) for r in reviews]
    slim_review_comments = [_slim_review_comment(c) for c in review_comments]
    slim_files = [_slim_file(f) for f in files]
    pull_slim = _slim_pull(pull, head_sha)
    merge_state = detect_revert_state(pull_slim, slim_commits, timeline)

    fetch = None
    if opts.artifact_store is not None:
        fetch = GitFetch(client, opts.artifact_store, full)
    snapshots, snap_warnings, snap_eps = _maybe_snapshots(
        fetch,
        SnapshotScope(
            pull=pull_slim,
            commits=slim_commits,
            files=slim_files,
            review_comments=slim_review_comments,
        ),
        opts.include_snapshots,
    )
    warnings.extend(snap_warnings)
    endpoints.extend(snap_eps)

    diff_artifact = _maybe_diff_artifact(opts.artifact_store, diff_text, full, pr_number)
    evidence_complete = _evidence_complete(opts.include_snapshots, snapshots, warnings)

    record: dict[str, Any] = {
        "schema_version": "raw_pr_record_v0",
        "collected_at": datetime.now(timezone.utc).isoformat(),
        "collector_version": __version__,
        "source": {
            "repo": full,
            "pr_number": pr_number,
            "html_url": pull.get("html_url"),
            "api_urls": {
                "pull": f"{client.base_url}/repos/{full}/pulls/{pr_number}",
            },
        },
        "pull": pull_slim,
        "issue_comments": [_slim_comment(c) for c in issue_comments],
        "review_comments": slim_review_comments,
        "reviews": slim_reviews,
        "commits": slim_commits,
        "files": slim_files,
        "diff": {
            "inline": diff_text,
            "sidecar_path": None,
            "bytes": len(diff_text.encode("utf-8")) if diff_text else 0,
            "truncated": False,
            "artifact": diff_artifact,
        },
        "checks": checks,
        "timeline": timeline,
        "merge_state": merge_state,
        "snapshots": snapshots,
        "linked_issues": linked,
        "collection_meta": {
            "authenticated": bool(client.token),
            "endpoints_called": endpoints,
            "warnings": warnings,
            "evidence_complete": evidence_complete,
        },
    }
    record, sec_warnings = scan_and_sanitize_obj(record)
    record["collection_meta"]["warnings"].extend(sec_warnings)
    return record


def _spill_inline_diff(record: dict[str, Any], out_dir: Path, max_inline_diff_bytes: int) -> dict[str, Any]:
    pr_number = record["source"]["pr_number"]
    diff_info = dict(record.get("diff") or {})
    inline = diff_info.get("inline")
    if not isinstance(inline, str) or len(inline.encode("utf-8")) <= max_inline_diff_bytes:
        return record
    sidecar = out_dir / f"pr-{pr_number}.diff"
    sidecar.write_text(inline, encoding="utf-8")
    record["diff"] = {
        **diff_info,
        "inline": None,
        "sidecar_path": sidecar.name,
        "bytes": len(inline.encode("utf-8")),
        "truncated": False,
    }
    return record


def _write_object_pack(
    record: dict[str, Any],
    out_dir: Path,
    artifact_store: ContentAddressedStore | None,
) -> dict[str, Any]:
    pack = record.get("snapshots")
    if not isinstance(pack, dict) or not pack:
        return record
    pr_number = record["source"]["pr_number"]
    pack_path = out_dir / f"pr-{pr_number}.pack.json"
    pack_path.write_text(
        json.dumps(pack, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    record["snapshots"] = {**pack, "pack_path": pack_path.name}
    if artifact_store is not None:
        spec = ArtifactSpec(kind="object_pack", media_type="application/json")
        meta = artifact_store.put_json(pack, spec)
        record["snapshots"]["store_sha256"] = meta["sha256"]
        record["snapshots"]["store_uri"] = artifact_store.uri(meta["sha256"])
    return record


def write_raw_record(
    record: dict[str, Any],
    out_dir: Path,
    max_inline_diff_bytes: int = DEFAULT_MAX_INLINE_DIFF,
    artifact_store: ContentAddressedStore | None = None,
) -> Path:
    """Write pr-N.json (and optional .diff sidecar / object pack). Returns path to JSON."""
    out_dir.mkdir(parents=True, exist_ok=True)
    pr_number = record["source"]["pr_number"]
    json_path = out_dir / f"pr-{pr_number}.json"
    record = _spill_inline_diff(dict(record), out_dir, max_inline_diff_bytes)
    record = _write_object_pack(record, out_dir, artifact_store)
    tmp_path = json_path.with_suffix(json_path.suffix + ".tmp")
    tmp_path.write_text(
        json.dumps(record, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    tmp_path.replace(json_path)
    return json_path
