"""Content-addressed git object collection and quarantine.

Required commit objects and before/after blobs are fetched read-only from
the GitHub Git Data API and stored by SHA-256.  A missing or inaccessible
object is recorded in the pack with ``availability: missing`` and the PR is
quarantined — the pack is never silently marked complete.
"""

from __future__ import annotations

import base64
from typing import Any

from .cas import ContentAddressedStore
from .github_client import GitHubClient, GitHubError
from .source_inventory_common import sha256_json

PACK_SCHEMA_VERSION = "object_pack_v1"


def _is_not_found(exc: GitHubError) -> bool:
    return exc.status in (404, 410, 451)


def _valid_oid(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    oid = value.strip().lower()
    if 3 <= len(oid) <= 64 and all(c in "0123456789abcdef" for c in oid):
        return oid
    return None


def required_oids(
    pull: dict[str, Any],
    commits: list[dict[str, Any]],
    review_comments: list[dict[str, Any]] | None = None,
) -> list[str]:
    """Stable unique list of git OIDs this trajectory must be able to reproduce."""
    found: list[str] = []
    seen: set[str] = set()

    def add(value: Any) -> None:
        oid = _valid_oid(value)
        if oid and oid not in seen:
            seen.add(oid)
            found.append(oid)

    add(pull.get("base_sha") or (pull.get("base") or {}).get("sha"))
    add(pull.get("head_sha") or (pull.get("head") or {}).get("sha"))
    add(pull.get("merge_commit_sha") or pull.get("merge_commit_oid"))
    for commit in commits:
        add(commit.get("sha"))
        add(commit.get("tree_oid"))
        nested = commit.get("commit") if isinstance(commit.get("commit"), dict) else {}
        tree = nested.get("tree") if isinstance(nested, dict) else None
        if isinstance(tree, dict):
            add(tree.get("sha"))
    for comment in review_comments or []:
        add(comment.get("commit_id"))
        add(comment.get("original_commit_id"))
    return found


def _store_git_json(
    store: ContentAddressedStore,
    payload: dict[str, Any],
    *,
    git_oid: str,
    kind: str,
    media_type: str,
) -> dict[str, Any]:
    meta = store.put_json(
        payload,
        media_type=media_type,
        kind=kind,
        git_oid=git_oid,
    )
    return {
        "git_oid": git_oid,
        "kind": kind,
        "sha256": meta["sha256"],
        "byte_size": meta["byte_size"],
        "availability": "present",
        "media_type": media_type,
        "uri": store.uri(meta["sha256"]),
        "sanitized": bool(meta.get("sanitized")),
    }


def _missing(git_oid: str, kind: str, reason: str, *, status: int | None = None) -> dict[str, Any]:
    return {
        "git_oid": git_oid,
        "kind": kind,
        "sha256": None,
        "byte_size": 0,
        "availability": "missing",
        "reason": reason,
        "http_status": status,
    }


def _truncated(git_oid: str, kind: str, reason: str, *, sha256: str | None = None) -> dict[str, Any]:
    return {
        "git_oid": git_oid,
        "kind": kind,
        "sha256": sha256,
        "byte_size": 0,
        "availability": "truncated",
        "reason": reason,
    }


def fetch_git_commit(
    client: GitHubClient,
    store: ContentAddressedStore,
    full: str,
    oid: str,
) -> dict[str, Any]:
    try:
        payload = client.get_json(f"/repos/{full}/git/commits/{oid}")
    except GitHubError as exc:
        reason = "git_commit_inaccessible" if _is_not_found(exc) else "git_commit_fetch_failed"
        return _missing(oid, "commit", reason, status=exc.status)
    if not isinstance(payload, dict):
        return _missing(oid, "commit", "git_commit_unexpected_payload")
    return _store_git_json(
        store,
        payload,
        git_oid=oid,
        kind="commit",
        media_type="application/vnd.github.git-commit+json",
    )


def fetch_git_blob(
    client: GitHubClient,
    store: ContentAddressedStore,
    full: str,
    oid: str,
) -> dict[str, Any]:
    try:
        payload = client.get_json(f"/repos/{full}/git/blobs/{oid}")
    except GitHubError as exc:
        reason = "git_blob_inaccessible" if _is_not_found(exc) else "git_blob_fetch_failed"
        return _missing(oid, "blob", reason, status=exc.status)
    if not isinstance(payload, dict):
        return _missing(oid, "blob", "git_blob_unexpected_payload")
    encoding = payload.get("encoding")
    content = payload.get("content")
    if encoding == "base64" and isinstance(content, str):
        try:
            data = base64.b64decode(content)
        except (ValueError, TypeError):
            return _truncated(oid, "blob", "git_blob_base64_invalid")
        try:
            text = data.decode("utf-8")
            meta = store.put_text(
                text,
                media_type="application/octet-stream",
                kind="blob",
                git_oid=oid,
            )
        except UnicodeDecodeError:
            meta = store.put_bytes(
                data,
                media_type="application/octet-stream",
                kind="blob",
                git_oid=oid,
            )
        return {
            "git_oid": oid,
            "kind": "blob",
            "sha256": meta["sha256"],
            "byte_size": meta["byte_size"],
            "availability": "present",
            "media_type": meta.get("media_type"),
            "uri": store.uri(meta["sha256"]),
            "sanitized": bool(meta.get("sanitized")),
        }
    # GitHub omits content for large blobs.
    if payload.get("size") and not content:
        return _truncated(oid, "blob", "git_blob_content_omitted")
    return _store_git_json(
        store,
        payload,
        git_oid=oid,
        kind="blob",
        media_type="application/vnd.github.git-blob+json",
    )


def _file_blob_oids(files: list[dict[str, Any]]) -> list[tuple[str, str]]:
    """Return (oid, filename) pairs for after-blobs advertised by the files API."""
    pairs: list[tuple[str, str]] = []
    seen: set[str] = set()
    for item in files:
        oid = _valid_oid(item.get("sha"))
        name = str(item.get("filename") or "")
        if oid and oid not in seen:
            seen.add(oid)
            pairs.append((oid, name))
    return pairs


def fetch_before_blob(
    client: GitHubClient,
    store: ContentAddressedStore,
    full: str,
    path: str,
    base_oid: str,
) -> dict[str, Any]:
    """Fetch the pre-change blob at ``path`` on ``base_oid``.  New files are missing."""
    from urllib.parse import quote

    encoded = quote(path, safe="/")
    try:
        payload = client.get_json(f"/repos/{full}/contents/{encoded}?ref={base_oid}")
    except GitHubError as exc:
        if _is_not_found(exc):
            return _missing(
                f"{base_oid}:{path}",
                "blob",
                "before_blob_absent",
                status=exc.status,
            )
        return _missing(
            f"{base_oid}:{path}",
            "blob",
            "before_blob_fetch_failed",
            status=exc.status,
        )
    if not isinstance(payload, dict):
        return _missing(f"{base_oid}:{path}", "blob", "before_blob_unexpected_payload")
    blob_oid = _valid_oid(payload.get("sha"))
    if not blob_oid:
        return _missing(f"{base_oid}:{path}", "blob", "before_blob_missing_oid")
    return fetch_git_blob(client, store, full, blob_oid)


def collect_snapshots(
    client: GitHubClient,
    store: ContentAddressedStore,
    full: str,
    *,
    pull: dict[str, Any],
    commits: list[dict[str, Any]],
    files: list[dict[str, Any]],
    review_comments: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Build a content-addressed object pack for one PR.

    ``complete`` is true only when every required commit object is present.
    Missing blobs are represented explicitly; they quarantine the pack when
    they are required after-blobs of included files (not newly added files'
    absent before-blobs).
    """
    oids = required_oids(pull, commits, review_comments)
    objects: list[dict[str, Any]] = []
    quarantine: list[dict[str, Any]] = []
    seen_oids: set[str] = set()

    for oid in oids:
        if oid in seen_oids:
            continue
        seen_oids.add(oid)
        record = fetch_git_commit(client, store, full, oid)
        objects.append(record)
        if record.get("availability") != "present":
            quarantine.append(
                {
                    "reason": record.get("reason") or "git_object_inaccessible",
                    "git_oid": oid,
                    "kind": "commit",
                    "http_status": record.get("http_status"),
                }
            )

    after_blobs = _file_blob_oids(files)
    for oid, filename in after_blobs:
        if oid in seen_oids:
            continue
        seen_oids.add(oid)
        record = fetch_git_blob(client, store, full, oid)
        record["filename"] = filename
        record["role"] = "after_blob"
        objects.append(record)
        if record.get("availability") == "missing":
            quarantine.append(
                {
                    "reason": record.get("reason") or "git_blob_inaccessible",
                    "git_oid": oid,
                    "kind": "blob",
                    "filename": filename,
                    "http_status": record.get("http_status"),
                }
            )
        elif record.get("availability") == "truncated":
            quarantine.append(
                {
                    "reason": record.get("reason") or "git_blob_truncated",
                    "git_oid": oid,
                    "kind": "blob",
                    "filename": filename,
                }
            )

    base_oid = _valid_oid(pull.get("base_sha") or (pull.get("base") or {}).get("sha"))
    if base_oid:
        for item in files:
            status = str(item.get("status") or "")
            filename = str(item.get("filename") or item.get("previous_filename") or "")
            if not filename or status == "added":
                # Before blob is legitimately absent for additions.
                continue
            before_path = str(item.get("previous_filename") or filename)
            record = fetch_before_blob(client, store, full, before_path, base_oid)
            record["filename"] = before_path
            record["role"] = "before_blob"
            objects.append(record)
            if record.get("availability") == "missing" and record.get("reason") != "before_blob_absent":
                quarantine.append(
                    {
                        "reason": record.get("reason") or "before_blob_inaccessible",
                        "git_oid": record.get("git_oid"),
                        "kind": "blob",
                        "filename": before_path,
                        "http_status": record.get("http_status"),
                    }
                )

    commit_objects = [o for o in objects if o.get("kind") == "commit" and o.get("git_oid") in set(oids)]
    complete = bool(oids) and all(o.get("availability") == "present" for o in commit_objects)
    if not oids:
        complete = False
        quarantine.append({"reason": "required_oids_empty", "kind": "commit"})

    pack = {
        "schema_version": PACK_SCHEMA_VERSION,
        "repository": full,
        "required_oids": oids,
        "objects": objects,
        "complete": complete,
        "quarantine": quarantine,
        "missing_oids": [
            o["git_oid"] for o in objects if o.get("availability") == "missing" and o.get("git_oid")
        ],
    }
    pack["pack_sha256"] = sha256_json({k: v for k, v in pack.items() if k != "pack_sha256"})
    return pack
