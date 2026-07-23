"""Assemble and write raw PR collection records."""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from . import __version__
from .github_client import GitHubClient, GitHubError, _parse_next_link, parse_repo
from .secrets import scan_and_sanitize_obj

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
        "line": c.get("line") or c.get("original_line"),
        "body": c.get("body") or "",
        "diff_hunk": c.get("diff_hunk"),
        "created_at": c.get("created_at"),
        "in_reply_to_id": c.get("in_reply_to_id"),
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
    }


def _slim_commit(c: dict) -> dict:
    commit = c.get("commit") or {}
    author = commit.get("author") or {}
    return {
        "sha": c.get("sha"),
        "message": commit.get("message") or "",
        "author_login": _user_login(c.get("author")),
        "date": author.get("date"),
    }


def _slim_file(f: dict) -> dict:
    patch = f.get("patch")
    return {
        "filename": f.get("filename"),
        "status": f.get("status"),
        "additions": f.get("additions"),
        "deletions": f.get("deletions"),
        "changes": f.get("changes"),
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
    cross_repo_allowlist: tuple[str, ...] | list[str] | None = None,
) -> dict[str, Any]:
    """Fetch a full raw trajectory-oriented PR record (read-only).

    ``cross_repo_allowlist`` extends (does not replace) ``CROSS_REPO_ALLOWLIST``
    with additional ``owner/repo`` entries that may be fetched for linked issues.
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

    checks: dict[str, Any] = {"check_runs": [], "combined_status": None}
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
            checks["check_runs"] = [
                {
                    "name": r.get("name"),
                    "status": r.get("status"),
                    "conclusion": r.get("conclusion"),
                    "html_url": r.get("html_url"),
                }
                for r in runs
            ]
        except GitHubError as exc:
            warnings.append(f"check_runs_failed: {exc}")
        try:
            status = client.get_json(f"/repos/{full}/commits/{head_sha}/status")
            endpoints.append("combined_status")
            checks["combined_status"] = {
                "state": status.get("state"),
                "statuses": [
                    {
                        "context": s.get("context"),
                        "state": s.get("state"),
                        "description": s.get("description"),
                    }
                    for s in (status.get("statuses") or [])
                ],
            }
        except GitHubError as exc:
            warnings.append(f"combined_status_failed: {exc}")

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
            if isinstance(issue, dict) and not issue.get("pull_request"):
                linked.append(
                    {
                        "number": issue.get("number"),
                        "repo": f"{i_owner}/{i_repo}",
                        "title": issue.get("title"),
                        "body": issue.get("body") or "",
                        "state": issue.get("state"),
                        "html_url": issue.get("html_url"),
                        "closed_by_pr": True,
                    }
                )
        except GitHubError as exc:
            warnings.append(f"linked_issue_{num}_failed: {exc}")

    labels = [lb.get("name") for lb in (pull.get("labels") or []) if lb.get("name")]
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
        "pull": {
            "title": pull.get("title"),
            "body": pull.get("body") or "",
            "state": pull.get("state"),
            "merged": bool(pull.get("merged")),
            "merged_at": pull.get("merged_at"),
            "user_login": _user_login(pull.get("user")),
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
        },
        "issue_comments": [_slim_comment(c) for c in issue_comments],
        "review_comments": [_slim_review_comment(c) for c in review_comments],
        "reviews": [_slim_review(r) for r in reviews],
        "commits": [_slim_commit(c) for c in commits],
        "files": [_slim_file(f) for f in files],
        "diff": {
            "inline": diff_text,
            "sidecar_path": None,
            "bytes": len(diff_text.encode("utf-8")) if diff_text else 0,
            "truncated": False,
        },
        "checks": checks,
        "linked_issues": linked,
        "collection_meta": {
            "authenticated": bool(client.token),
            "endpoints_called": endpoints,
            "warnings": warnings,
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
) -> Path:
    """Write pr-N.json (and optional .diff sidecar). Returns path to JSON."""
    out_dir.mkdir(parents=True, exist_ok=True)
    pr_number = record["source"]["pr_number"]
    json_path = out_dir / f"pr-{pr_number}.json"

    diff_info = record.get("diff") or {}
    inline = diff_info.get("inline")
    if isinstance(inline, str) and len(inline.encode("utf-8")) > max_inline_diff_bytes:
        sidecar = out_dir / f"pr-{pr_number}.diff"
        sidecar.write_text(inline, encoding="utf-8")
        record = dict(record)
        record["diff"] = {
            **diff_info,
            "inline": None,
            "sidecar_path": sidecar.name,
            "bytes": len(inline.encode("utf-8")),
            "truncated": False,
        }

    json_path.write_text(
        json.dumps(record, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return json_path
