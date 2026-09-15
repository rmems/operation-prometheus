"""Content-addressed git object collection and quarantine.

Required commit objects and before/after blobs are fetched read-only from
the GitHub Git Data API and stored by SHA-256.  A missing or inaccessible
object is recorded in the pack with ``availability: missing`` and the PR is
quarantined — the pack is never silently marked complete.
"""

from __future__ import annotations

import base64
from dataclasses import dataclass
from typing import Any
from urllib.parse import quote

from .cas import ArtifactSpec, ContentAddressedStore
from .github_client import GitHubClient, GitHubError
from .source_inventory_common import sha256_json

PACK_SCHEMA_VERSION = "object_pack_v1"


@dataclass(frozen=True)
class GitFetch:
    """Read-only GitHub + CAS handle used by snapshot fetch helpers."""

    client: GitHubClient
    store: ContentAddressedStore
    full: str


@dataclass(frozen=True)
class SnapshotScope:
    """PR surfaces that determine which git objects must be collected."""

    pull: dict[str, Any]
    commits: list[dict[str, Any]]
    files: list[dict[str, Any]]
    review_comments: list[dict[str, Any]] | None = None


@dataclass
class PackBuilder:
    fetch: GitFetch
    objects: list[dict[str, Any]]
    quarantine: list[dict[str, Any]]
    seen_oids: set[str]


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


def _present_record(git_oid: str, kind: str, meta: dict[str, Any], store: ContentAddressedStore) -> dict[str, Any]:
    return {
        "git_oid": git_oid,
        "kind": kind,
        "sha256": meta["sha256"],
        "byte_size": meta["byte_size"],
        "availability": "present",
        "media_type": meta.get("media_type"),
        "uri": store.uri(meta["sha256"]),
        "sanitized": bool(meta.get("sanitized")),
    }


def _store_git_json(fetch: GitFetch, payload: dict[str, Any], spec: ArtifactSpec) -> dict[str, Any]:
    meta = fetch.store.put_json(payload, spec)
    return _present_record(spec.git_oid or "", spec.kind, meta, fetch.store)


def _missing(git_oid: str, kind: str, reason: str, status: int | None = None) -> dict[str, Any]:
    return {
        "git_oid": git_oid,
        "kind": kind,
        "sha256": None,
        "byte_size": 0,
        "availability": "missing",
        "reason": reason,
        "http_status": status,
    }


def _truncated(git_oid: str, kind: str, reason: str, sha256: str | None = None) -> dict[str, Any]:
    return {
        "git_oid": git_oid,
        "kind": kind,
        "sha256": sha256,
        "byte_size": 0,
        "availability": "truncated",
        "reason": reason,
    }


def _unavailable(record: dict[str, Any], ignore_reasons: frozenset[str] | None = None) -> bool:
    if record.get("availability") == "present":
        return False
    ignored = ignore_reasons or frozenset()
    if record.get("reason") in ignored:
        return False
    return record.get("availability") in {"missing", "truncated"}


def _quarantine_from(record: dict[str, Any], extra: dict[str, Any] | None = None) -> dict[str, Any]:
    entry = {
        "reason": record.get("reason") or "git_object_inaccessible",
        "git_oid": record.get("git_oid"),
        "kind": record.get("kind"),
    }
    if record.get("http_status") is not None:
        entry["http_status"] = record.get("http_status")
    if extra:
        entry.update(extra)
    return entry


def fetch_git_commit(fetch: GitFetch, oid: str) -> dict[str, Any]:
    try:
        payload = fetch.client.get_json(f"/repos/{fetch.full}/git/commits/{oid}")
    except GitHubError as exc:
        reason = "git_commit_inaccessible" if _is_not_found(exc) else "git_commit_fetch_failed"
        return _missing(oid, "commit", reason, status=exc.status)
    if not isinstance(payload, dict):
        return _missing(oid, "commit", "git_commit_unexpected_payload")
    spec = ArtifactSpec(
        media_type="application/vnd.github.git-commit+json",
        kind="commit",
        git_oid=oid,
    )
    return _store_git_json(fetch, payload, spec)


def _store_base64_blob(fetch: GitFetch, oid: str, content: str) -> dict[str, Any]:
    try:
        data = base64.b64decode(content)
    except (ValueError, TypeError):
        return _truncated(oid, "blob", "git_blob_base64_invalid")
    spec = ArtifactSpec(media_type="application/octet-stream", kind="blob", git_oid=oid)
    try:
        text = data.decode("utf-8")
        meta = fetch.store.put_text(text, spec)
    except UnicodeDecodeError:
        meta = fetch.store.put_bytes(data, spec)
    return _present_record(oid, "blob", meta, fetch.store)


def _decode_blob(fetch: GitFetch, oid: str, payload: dict[str, Any]) -> dict[str, Any]:
    encoding = payload.get("encoding")
    content = payload.get("content")
    if encoding == "base64" and isinstance(content, str):
        return _store_base64_blob(fetch, oid, content)
    if payload.get("size") and not content:
        return _truncated(oid, "blob", "git_blob_content_omitted")
    spec = ArtifactSpec(
        media_type="application/vnd.github.git-blob+json",
        kind="blob",
        git_oid=oid,
    )
    return _store_git_json(fetch, payload, spec)


def fetch_git_blob(fetch: GitFetch, oid: str) -> dict[str, Any]:
    try:
        payload = fetch.client.get_json(f"/repos/{fetch.full}/git/blobs/{oid}")
    except GitHubError as exc:
        reason = "git_blob_inaccessible" if _is_not_found(exc) else "git_blob_fetch_failed"
        return _missing(oid, "blob", reason, status=exc.status)
    if not isinstance(payload, dict):
        return _missing(oid, "blob", "git_blob_unexpected_payload")
    return _decode_blob(fetch, oid, payload)


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


def _before_blob_id(base_oid: str, path: str) -> str:
    return f"{base_oid}:{path}"


def fetch_before_blob(fetch: GitFetch, path: str, base_oid: str) -> dict[str, Any]:
    """Fetch the pre-change blob at ``path`` on ``base_oid``.  New files are missing."""
    encoded = quote(path, safe="/")
    blob_id = _before_blob_id(base_oid, path)
    try:
        payload = fetch.client.get_json(f"/repos/{fetch.full}/contents/{encoded}?ref={base_oid}")
    except GitHubError as exc:
        reason = "before_blob_absent" if _is_not_found(exc) else "before_blob_fetch_failed"
        return _missing(blob_id, "blob", reason, status=exc.status)
    if not isinstance(payload, dict):
        return _missing(blob_id, "blob", "before_blob_unexpected_payload")
    blob_oid = _valid_oid(payload.get("sha"))
    if not blob_oid:
        return _missing(blob_id, "blob", "before_blob_missing_oid")
    return fetch_git_blob(fetch, blob_oid)


def _collect_required_commits(pack: PackBuilder, oids: list[str]) -> None:
    for oid in oids:
        if oid in pack.seen_oids:
            continue
        pack.seen_oids.add(oid)
        record = fetch_git_commit(pack.fetch, oid)
        pack.objects.append(record)
        if _unavailable(record):
            pack.quarantine.append(_quarantine_from(record, extra={"kind": "commit", "git_oid": oid}))


def _collect_after_blobs(pack: PackBuilder, files: list[dict[str, Any]]) -> None:
    for oid, filename in _file_blob_oids(files):
        if oid in pack.seen_oids:
            continue
        pack.seen_oids.add(oid)
        record = fetch_git_blob(pack.fetch, oid)
        record["filename"] = filename
        record["role"] = "after_blob"
        pack.objects.append(record)
        extra = {"kind": "blob", "filename": filename, "git_oid": oid}
        if _unavailable(record):
            pack.quarantine.append(_quarantine_from(record, extra))


def _collect_before_blobs(pack: PackBuilder, files: list[dict[str, Any]], base_oid: str) -> None:
    ignore = frozenset({"before_blob_absent"})
    for item in files:
        status = str(item.get("status") or "")
        filename = str(item.get("filename") or item.get("previous_filename") or "")
        if not filename or status == "added":
            # Before blob is legitimately absent for additions.
            continue
        before_path = str(item.get("previous_filename") or filename)
        record = fetch_before_blob(pack.fetch, before_path, base_oid)
        record["filename"] = before_path
        record["role"] = "before_blob"
        pack.objects.append(record)
        if _unavailable(record, ignore_reasons=ignore):
            pack.quarantine.append(
                _quarantine_from(record, extra={"kind": "blob", "filename": before_path})
            )


def _pack_complete(oids: list[str], objects: list[dict[str, Any]]) -> bool:
    required = set(oids)
    commit_objects = [o for o in objects if o.get("kind") == "commit" and o.get("git_oid") in required]
    return bool(oids) and all(o.get("availability") == "present" for o in commit_objects)


def collect_snapshots(fetch: GitFetch, scope: SnapshotScope) -> dict[str, Any]:
    """Build a content-addressed object pack for one PR.

    ``complete`` is true only when every required commit object is present.
    Missing blobs are represented explicitly; they quarantine the pack when
    they are required after-blobs of included files (not newly added files'
    absent before-blobs).
    """
    oids = required_oids(scope.pull, scope.commits, scope.review_comments)
    pack = PackBuilder(fetch=fetch, objects=[], quarantine=[], seen_oids=set())
    _collect_required_commits(pack, oids)
    _collect_after_blobs(pack, scope.files)
    base_oid = _valid_oid(scope.pull.get("base_sha") or (scope.pull.get("base") or {}).get("sha"))
    if base_oid:
        _collect_before_blobs(pack, scope.files, base_oid)

    complete = _pack_complete(oids, pack.objects)
    if not oids:
        pack.quarantine.append({"reason": "required_oids_empty", "kind": "commit"})

    result = {
        "schema_version": PACK_SCHEMA_VERSION,
        "repository": fetch.full,
        "required_oids": oids,
        "objects": pack.objects,
        "complete": complete,
        "quarantine": pack.quarantine,
        "missing_oids": [
            o["git_oid"] for o in pack.objects if o.get("availability") == "missing" and o.get("git_oid")
        ],
    }
    result["pack_sha256"] = sha256_json({k: v for k, v in result.items() if k != "pack_sha256"})
    return result
