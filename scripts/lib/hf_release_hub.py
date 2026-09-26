"""Hugging Face tag lookup and pinned-revision checksums for release verify."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from .ci_contracts import sha256_file

try:
    from huggingface_hub import HfApi, hf_hub_download
except ImportError:
    HfApi = None
    hf_hub_download = None


class ReleaseVerifyError(ValueError):
    """A release-verify precondition failed."""


def pinned_revision_checksums(
    downloaded: dict[str, str],
    expected: list[dict[str, Any]],
) -> list[str]:
    errors: list[str] = []
    for item in expected:
        message = _checksum_message(downloaded.get(item["path"]), item)
        if message is not None:
            errors.append(message)
    return errors


def _checksum_message(actual: str | None, item: dict[str, Any]) -> str | None:
    if actual is None:
        return f"pinned revision is missing {item['path']}"
    if actual != item["sha256"]:
        return f"pinned revision checksum mismatch for {item['path']}"
    return None


def _tag_name(tag: Any) -> str | None:
    name = getattr(tag, "name", None)
    if name:
        return str(name)
    ref = getattr(tag, "ref", None)
    if ref:
        return str(ref)
    return None


def _tag_oid(tag: Any) -> str | None:
    oid = getattr(tag, "target_commit", None)
    if oid:
        return str(oid)
    ref = getattr(tag, "ref", None)
    if ref:
        return str(ref)
    return None


def _tag_name_and_oid(tag: Any) -> tuple[str, str] | None:
    name = _tag_name(tag)
    oid = _tag_oid(tag)
    if name is None:
        return None
    if oid is None:
        return None
    return name, oid


def load_remote_tags(dataset_repo: str, token: str | None) -> dict[str, str]:
    if not token:
        return {}
    if HfApi is None:
        raise ReleaseVerifyError("huggingface_hub is required when HF_TOKEN is set")
    refs = HfApi(token=token).list_repo_refs(dataset_repo, repo_type="dataset")
    tags: dict[str, str] = {}
    for tag in getattr(refs, "tags", []) or []:
        parsed = _tag_name_and_oid(tag)
        if parsed is None:
            continue
        tags[parsed[0]] = parsed[1]
    return tags


def download_pinned_checksums(
    dataset_repo: str,
    revision: str,
    filenames: list[str],
    token: str | None,
) -> dict[str, str]:
    if not token:
        return {}
    if hf_hub_download is None:
        raise ReleaseVerifyError("huggingface_hub is required when HF_TOKEN is set")
    checksums: dict[str, str] = {}
    for name in filenames:
        local = hf_hub_download(
            repo_id=dataset_repo,
            filename=name,
            repo_type="dataset",
            revision=revision,
            token=token,
        )
        checksums[name] = sha256_file(Path(local))
    return checksums


def maybe_download_pinned(
    tag: str,
    dataset_repo: str,
    artifacts: list[dict[str, Any]],
    tags: dict[str, str],
) -> dict[str, str] | None:
    if not os.environ.get("HF_TOKEN"):
        return None
    if tag not in tags:
        return None
    names = [item["path"] for item in artifacts]
    return download_pinned_checksums(
        dataset_repo, tag, names, os.environ.get("HF_TOKEN")
    )


def pinned_checksum_errors(
    tag: str,
    dataset_repo: str,
    artifacts: list[dict[str, Any]],
    remotes: dict[str, Any],
) -> list[str]:
    resolved = remotes.get("downloaded")
    if resolved is None:
        resolved = maybe_download_pinned(tag, dataset_repo, artifacts, remotes["tags"])
    if not resolved:
        return []
    return pinned_revision_checksums(resolved, artifacts)
