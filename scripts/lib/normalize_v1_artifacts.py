"""v1 git-object and patch artifact assembly."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .cas import ContentAddressedStore, sha256_bytes
from .normalize import extract_patch


def _sha256_is_digest(sha256: Any) -> bool:
    if not isinstance(sha256, str):
        return False
    return len(sha256) == 64


def _reproduction_role(obj: dict[str, Any]) -> str:
    return str(obj.get("role") or obj.get("kind") or "git_object")


def _present_art_record(obj: dict[str, Any], index: int) -> dict[str, Any]:
    uri = obj.get("uri")
    art = {
        "id": f"obj-{index}",
        "sha256": obj.get("sha256"),
        "media_type": obj.get("media_type") or "application/octet-stream",
        "byte_size": int(obj.get("byte_size") or 0),
        "availability": "inline",
        "reproduction_role": _reproduction_role(obj),
    }
    if uri:
        art["availability"] = "remote"
        art["uri"] = uri
    return art


def _present_git_artifact(obj: dict[str, Any], index: int) -> dict[str, Any] | None:
    availability = obj.get("availability") or "missing"
    if availability != "present":
        return None
    if not _sha256_is_digest(obj.get("sha256")):
        return None
    return _present_art_record(obj, index)


def _placeholder_git_artifact(obj: dict[str, Any], index: int) -> dict[str, Any]:
    placeholder = {
        "reason": obj.get("reason") or "missing",
        "git_oid": obj.get("git_oid"),
        "kind": obj.get("kind"),
        "availability": obj.get("availability") or "missing",
    }
    encoded = repr(placeholder).encode("utf-8")
    return {
        "id": f"obj-{index}",
        "sha256": sha256_bytes(encoded),
        "media_type": "application/json",
        "byte_size": len(encoded),
        "availability": "missing",
        "reproduction_role": _reproduction_role(obj),
    }


def _artifact_from_object(obj: dict[str, Any], index: int) -> dict[str, Any]:
    present = _present_git_artifact(obj, index)
    if present:
        return present
    return _placeholder_git_artifact(obj, index)


def _cas_uri(sha256: str) -> str:
    return f"cas://sha256/{sha256}"


def _cas_patch_artifact(artifact_meta: dict[str, Any], patch: str) -> tuple[str, dict[str, Any]]:
    sha256 = artifact_meta["sha256"]
    art = {
        "id": "unified-diff",
        "sha256": sha256,
        "media_type": "text/x-diff",
        "byte_size": int(artifact_meta.get("byte_size") or len(patch.encode("utf-8"))),
        "availability": "remote",
        "reproduction_role": "implementation_patch",
        "uri": artifact_meta.get("uri") or _cas_uri(sha256),
    }
    if patch:
        return patch, art
    return _cas_uri(sha256), art


def _inline_patch_artifact(patch: str) -> tuple[str, dict[str, Any] | None]:
    if not patch:
        return "patch not collected", None
    data = patch.encode("utf-8")
    return patch, {
        "id": "inline-patch",
        "sha256": sha256_bytes(data),
        "media_type": "text/x-diff",
        "byte_size": len(data),
        "availability": "inline",
        "reproduction_role": "implementation_patch",
        "content": patch,
    }


def _has_cas_meta(artifact_meta: Any) -> bool:
    if not isinstance(artifact_meta, dict):
        return False
    return bool(artifact_meta.get("sha256"))


def _patch_artifact(
    raw: dict[str, Any],
    max_patch_bytes: int,
    raw_path: Path | None = None,
) -> tuple[str, dict[str, Any] | None]:
    patch = extract_patch(raw, raw_path=raw_path, max_bytes=max_patch_bytes)
    diff = raw.get("diff") or {}
    artifact_meta = diff.get("artifact") if isinstance(diff, dict) else None
    if _has_cas_meta(artifact_meta):
        return _cas_patch_artifact(artifact_meta, patch)
    return _inline_patch_artifact(patch)


def _pack_store_artifact(pack: dict[str, Any], store: ContentAddressedStore | None) -> dict[str, Any] | None:
    if store is None:
        return None
    digest = pack.get("store_sha256") or pack.get("pack_sha256")
    if not digest:
        return None
    if not store.exists(digest):
        return None
    return {
        "id": "object-pack",
        "sha256": digest,
        "media_type": "application/json",
        "byte_size": len(store.get_bytes(digest)),
        "availability": "remote",
        "reproduction_role": "object_pack",
        "uri": store.uri(digest),
    }


def _snapshot_objects(raw: dict[str, Any]) -> tuple[dict[str, Any], list[Any]]:
    pack = raw.get("snapshots") or {}
    if not isinstance(pack, dict):
        return {}, []
    return pack, list(pack.get("objects") or [])


def _assemble_artifacts(
    raw: dict[str, Any],
    patch_art: dict[str, Any] | None,
    store: ContentAddressedStore | None,
) -> list[dict[str, Any]]:
    artifacts: list[dict[str, Any]] = []
    if patch_art:
        artifacts.append(patch_art)
    pack, objects = _snapshot_objects(raw)
    for index, obj in enumerate(objects):
        artifacts.append(_artifact_from_object(obj, index))
    pack_art = _pack_store_artifact(pack, store)
    if pack_art:
        artifacts.append(pack_art)
    return artifacts
