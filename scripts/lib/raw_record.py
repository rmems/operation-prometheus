"""Assemble and write raw PR collection records."""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from . import __version__
from .cas import ContentAddressedStore
from .collect_events import (
    collect_check_suites,
    collect_commit_statuses,
    collect_timeline,
    detect_revert_state,
    slim_check_run,
)
from .github_client import GitHubClient, GitHubError, _parse_next_link, parse_repo
from .secrets import scan_and_sanitize_obj
from .snapshots import collect_snapshots

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
# Runtime allowlist is the union of this constant and collect_pr(..., cross_repo_allowlist=...).
CROSS_REPO_ALLOWLIST: tuple[str, ...] = (
    # Add approved cross-repo references here, e.g.:
    # "rmems/operation-prometheus",
)


def _norm_repo(repo: str) -> str:
    """Case-fold owner/repo for allowlist and same-repo comparisons."""
    return str(repo).strip().lower()


def _user_login(obj: dict | None) -> str | None:
    if not obj:
        return None
    return obj.get("login")


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


def collect_pr(
    client: GitHubClient,
    repo: str,
    pr_number: int,
    *,
    include_checks: bool = True,
    include_diff: bool = True,
    include_timeline: bool = True,
    include_snapshots: bool = False,
    artifact_store: ContentAddressedStore | None = None,
    cross_repo_allowlist: tuple[str, ...] | list[str] | None = None,
) -> dict[str, Any]:
    """Fetch a full raw trajectory-oriented PR record (read-only).

    ``cross_repo_allowlist`` extends (does not replace) ``CROSS_REPO_ALLOWLIST``
    with additional ``owner/repo`` entries that may be fetched for linked issues.

    Extra timeline / check-suite / status events are collected by default so
    chronology can link reviews and checks to a code state.  Git object
    snapshots are opt-in via ``include_snapshots`` and require an artifact store.
    """
    owner, name = parse_repo(repo)
    full = f"{owner}/{name}"
    warnings: list[str] = []
    endpoints: list[str] = []
    allowlist = {_norm_repo(x) for x in CROSS_REPO_ALLOWLIST if str(x).strip()}
    if cross_repo_allowlist:
        for entry in cross_repo_allowlist:
            entry = str(entry).strip()
            if entry:
                allowlist.add(_norm_repo(entry))

    pull = client.get_json(f"/repos/{full}/pulls/{pr_number}")
    endpoints.append("pulls")
    if not isinstance(pull, dict):
        raise GitHubError(f"Unexpected pull payload for {full}#{pr_number}")

    # Public-history only: reject private base/head repos immediately (token may
    # still be able to read private repos — do not turn them into training data).
    for side in ("base", "head"):
        repo_meta = (pull.get(side) or {}).get("repo") or {}
        if isinstance(repo_meta, dict) and repo_meta.get("private") is True:
            side_full = repo_meta.get("full_name") or full
            raise GitHubError(
                f"Refusing to collect private repository {side_full} "
                f"(PR {full}#{pr_number} {side}). "
                "Operation Prometheus only extracts public GitHub history."
            )

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
    if include_diff:
        try:
            diff_text = client.get_text(f"/repos/{full}/pulls/{pr_number}")
            endpoints.append("diff")
        except GitHubError as exc:
            warnings.append(f"diff_fetch_failed: {exc}")

    checks: dict[str, Any] = {
        "check_runs": [],
        "check_suites": [],
        "combined_status": None,
        "commit_statuses": [],
    }
    head_sha = (pull.get("head") or {}).get("sha")
    if include_checks and head_sha:
        try:
            runs: list[dict[str, Any]] = []
            total_count: int | None = None
            next_url: str | None = f"/repos/{full}/commits/{head_sha}/check-runs?per_page=100"
            while next_url:
                cr, headers = client.get_json_with_headers(next_url)
                if total_count is None:
                    total_count = (cr or {}).get("total_count")
                runs.extend((cr or {}).get("check_runs") or [])
                next_url = _parse_next_link(headers.get("link", ""))
            endpoints.append("check_runs")
            if total_count is not None and total_count > len(runs):
                warnings.append(
                    f"check_runs_truncated: total_count={total_count} collected={len(runs)}"
                )
            checks["check_runs"] = [slim_check_run(r) for r in runs if isinstance(r, dict)]
        except GitHubError as exc:
            warnings.append(f"check_runs_failed: {exc}")
        try:
            status = client.get_json(f"/repos/{full}/commits/{head_sha}/status")
            endpoints.append("combined_status")
            checks["combined_status"] = {
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
            }
        except GitHubError as exc:
            warnings.append(f"combined_status_failed: {exc}")
        suites, suite_warnings = collect_check_suites(client, full, head_sha)
        checks["check_suites"] = suites
        warnings.extend(suite_warnings)
        if suites or not suite_warnings:
            endpoints.append("check_suites")
        statuses, status_warnings = collect_commit_statuses(client, full, head_sha)
        checks["commit_statuses"] = statuses
        warnings.extend(status_warnings)
        if statuses or not status_warnings:
            endpoints.append("commit_statuses")

    timeline: list[dict[str, Any]] = []
    if include_timeline:
        timeline, timeline_warnings = collect_timeline(client, full, pr_number)
        warnings.extend(timeline_warnings)
        if timeline or not timeline_warnings:
            endpoints.append("timeline")

    # Closing keywords from PR body AND commit messages (GitHub also closes from commits).
    link_text_parts = [pull.get("body") or ""]
    for c in commits:
        msg = ((c.get("commit") or {}).get("message") if isinstance(c, dict) else None)
        if not msg and isinstance(c, dict):
            msg = c.get("message")
        if msg:
            link_text_parts.append(str(msg))
    link_blob = "\n".join(link_text_parts)

    linked: list[dict[str, Any]] = []
    for i_owner, i_repo, num in parse_linked_issue_numbers(link_blob, owner, name):
        # Check if cross-repo fetch is allowed (case-insensitive owner/repo).
        target_repo = f"{i_owner}/{i_repo}"
        source_repo = f"{owner}/{name}"
        if _norm_repo(target_repo) != _norm_repo(source_repo):
            # Cross-repo reference - require allowlist entry (CLI or module default).
            if _norm_repo(target_repo) not in allowlist:
                warnings.append(
                    f"linked_issue_{num}_skipped: cross-repo {target_repo} not in allowlist "
                    f"(pass --allow-cross-repo {target_repo})"
                )
                continue
        try:
            issue = client.get_json(f"/repos/{i_owner}/{i_repo}/issues/{num}")
            endpoints.append(f"issue_{num}")
            issue_comments_linked: list[dict[str, Any]] = []
            if isinstance(issue, dict) and not issue.get("pull_request"):
                try:
                    issue_comments_linked = [
                        _slim_comment(c)
                        for c in client.get_all(f"/repos/{i_owner}/{i_repo}/issues/{num}/comments")
                    ]
                    endpoints.append(f"issue_{num}_comments")
                except GitHubError as exc:
                    warnings.append(f"linked_issue_{num}_comments_failed: {exc}")
                linked.append(
                    {
                        "number": issue.get("number"),
                        "repo": f"{i_owner}/{i_repo}",
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
                        "comments": issue_comments_linked,
                        "closed_by_pr": True,
                    }
                )
        except GitHubError as exc:
            warnings.append(f"linked_issue_{num}_failed: {exc}")

    slim_commits = [_slim_commit(c) for c in commits]
    slim_reviews = [_slim_review(r) for r in reviews]
    slim_review_comments = [_slim_review_comment(c) for c in review_comments]
    slim_files = [_slim_file(f) for f in files]
    labels = [lb.get("name") for lb in (pull.get("labels") or []) if lb.get("name")]
    pull_slim = {
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
    merge_state = detect_revert_state(pull_slim, slim_commits, timeline)

    snapshots: dict[str, Any] | None = None
    if include_snapshots:
        if artifact_store is None:
            warnings.append("snapshots_skipped: artifact store required")
        else:
            snapshots = collect_snapshots(
                client,
                artifact_store,
                full,
                pull=pull_slim,
                commits=slim_commits,
                files=slim_files,
                review_comments=slim_review_comments,
            )
            endpoints.append("git_objects")
            if snapshots.get("quarantine"):
                warnings.append(
                    "snapshots_quarantined: "
                    + ",".join(
                        str(q.get("reason") or "unknown") for q in snapshots["quarantine"][:8]
                    )
                )

    if artifact_store is not None and isinstance(diff_text, str) and diff_text:
        diff_meta = artifact_store.put_text(
            diff_text,
            media_type="text/x-diff",
            kind="unified_diff",
            extra={"repo": full, "pr_number": pr_number},
        )
        diff_artifact = {
            "sha256": diff_meta["sha256"],
            "byte_size": diff_meta["byte_size"],
            "uri": artifact_store.uri(diff_meta["sha256"]),
        }
    else:
        diff_artifact = None

    evidence_complete = True
    if include_snapshots:
        evidence_complete = bool(snapshots and snapshots.get("complete"))
    if any("truncated" in w for w in warnings):
        evidence_complete = False

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


def write_raw_record(
    record: dict[str, Any],
    out_dir: Path,
    *,
    max_inline_diff_bytes: int = DEFAULT_MAX_INLINE_DIFF,
    artifact_store: ContentAddressedStore | None = None,
) -> Path:
    """Write pr-N.json (and optional .diff sidecar / object pack). Returns path to JSON."""
    out_dir.mkdir(parents=True, exist_ok=True)
    pr_number = record["source"]["pr_number"]
    json_path = out_dir / f"pr-{pr_number}.json"

    record = dict(record)
    diff_info = dict(record.get("diff") or {})
    inline = diff_info.get("inline")
    if isinstance(inline, str) and len(inline.encode("utf-8")) > max_inline_diff_bytes:
        sidecar = out_dir / f"pr-{pr_number}.diff"
        sidecar.write_text(inline, encoding="utf-8")
        diff_info = {
            **diff_info,
            "inline": None,
            "sidecar_path": sidecar.name,
            "bytes": len(inline.encode("utf-8")),
            "truncated": False,
        }
        record["diff"] = diff_info

    pack = record.get("snapshots")
    if isinstance(pack, dict) and pack:
        pack_path = out_dir / f"pr-{pr_number}.pack.json"
        pack_path.write_text(
            json.dumps(pack, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        record["snapshots"] = {
            **pack,
            "pack_path": pack_path.name,
        }
        if artifact_store is not None:
            meta = artifact_store.put_json(pack, kind="object_pack", media_type="application/json")
            record["snapshots"]["store_sha256"] = meta["sha256"]
            record["snapshots"]["store_uri"] = artifact_store.uri(meta["sha256"])

    tmp_path = json_path.with_suffix(json_path.suffix + ".tmp")
    tmp_path.write_text(
        json.dumps(record, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    tmp_path.replace(json_path)
    return json_path
