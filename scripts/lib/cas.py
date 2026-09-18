"""Content-addressed artifact store for patches, git objects, and bundles.

Objects are addressed by SHA-256 of their exact byte content.  A cached file
is trusted only after the on-disk bytes re-hash to that digest — the path
name alone is never sufficient.  Writes are atomic (temp file + replace).
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

from .secrets import scan_and_sanitize_obj
from .source_inventory_common import canonical_json_bytes, sha256_json

SCHEMA_VERSION = "cas_object_v1"


@dataclass(frozen=True)
class ArtifactSpec:
    """Identity metadata stored alongside a CAS object (keeps put_* at ≤4 args)."""

    media_type: str
    kind: str
    git_oid: str | None = None
    extra: dict[str, Any] | None = None
    sanitize: bool = True


def sha256_bytes(data: bytes) -> str:
    """Return the hex SHA-256 of ``data``."""
    return hashlib.sha256(data).hexdigest()


def _object_path(root: Path, digest: str) -> Path:
    return root / "objects" / digest[:2] / digest


def _meta_path(root: Path, digest: str) -> Path:
    return root / "meta" / digest[:2] / f"{digest}.json"


def _atomic_write_bytes(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_bytes(data)
    tmp.replace(path)


def _atomic_write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    tmp.replace(path)


def _ensure_object(root: Path, digest: str, data: bytes) -> Path:
    obj_path = _object_path(root, digest)
    if obj_path.exists():
        existing = obj_path.read_bytes()
        if sha256_bytes(existing) != digest:
            # Path matched but content did not — rewrite after corruption.
            _atomic_write_bytes(obj_path, data)
        return obj_path
    _atomic_write_bytes(obj_path, data)
    return obj_path


def _object_meta(root: Path, digest: str, byte_size: int, spec: ArtifactSpec) -> dict[str, Any]:
    meta = {
        "schema_version": SCHEMA_VERSION,
        "sha256": digest,
        "byte_size": byte_size,
        "media_type": spec.media_type,
        "kind": spec.kind,
        "git_oid": spec.git_oid,
        "path": str(_object_path(root, digest).relative_to(root)),
    }
    if spec.extra:
        meta.update(spec.extra)
    return meta


def _with_secret_warnings(payload: Any, spec: ArtifactSpec) -> tuple[Any, ArtifactSpec]:
    extra = dict(spec.extra or {})
    if not spec.sanitize:
        return payload, replace(spec, extra=extra or None)
    payload, warnings = scan_and_sanitize_obj(payload)
    if warnings:
        extra["sanitized"] = True
        extra["secret_warnings"] = warnings
    return payload, replace(spec, extra=extra or None)


class ContentAddressedStore:
    """Deduplicating SHA-256 object store with hash-verified reads."""

    def __init__(self, root: Path) -> None:
        self.root = Path(root)

    def put_bytes(self, data: bytes, spec: ArtifactSpec) -> dict[str, Any]:
        """Store ``data`` and return its metadata record."""
        digest = sha256_bytes(data)
        _ensure_object(self.root, digest, data)
        meta = _object_meta(self.root, digest, len(data), spec)
        _atomic_write_text(
            _meta_path(self.root, digest),
            json.dumps(meta, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
        )
        return meta

    def put_text(self, text: str, spec: ArtifactSpec) -> dict[str, Any]:
        """Store UTF-8 text, optionally running secret scanning first."""
        payload, spec = _with_secret_warnings(text, spec)
        if not isinstance(payload, str):
            payload = str(payload)
        return self.put_bytes(payload.encode("utf-8"), spec)

    def put_json(self, value: Any, spec: ArtifactSpec | None = None) -> dict[str, Any]:
        """Store a canonical JSON document (sorted keys, compact separators)."""
        spec = spec or ArtifactSpec(media_type="application/json", kind="json")
        payload, spec = _with_secret_warnings(value, spec)
        extra = dict(spec.extra or {})
        extra["canonical_sha256"] = sha256_json(payload)
        stored = ArtifactSpec(
            media_type=spec.media_type,
            kind=spec.kind,
            git_oid=spec.git_oid,
            extra=extra,
            sanitize=spec.sanitize,
        )
        return self.put_bytes(canonical_json_bytes(payload), stored)

    def get_bytes(self, digest: str) -> bytes:
        """Read and verify an object by SHA-256. Raises ``FileNotFoundError`` / ``ValueError``."""
        digest = digest.lower()
        path = _object_path(self.root, digest)
        if not path.is_file():
            raise FileNotFoundError(f"CAS object not found: {digest}")
        data = path.read_bytes()
        actual = sha256_bytes(data)
        if actual != digest:
            raise ValueError(
                f"CAS object {digest} failed content-hash verification (got {actual})"
            )
        return data

    def get_text(self, digest: str) -> str:
        return self.get_bytes(digest).decode("utf-8")

    def exists(self, digest: str) -> bool:
        path = _object_path(self.root, digest.lower())
        if not path.is_file():
            return False
        try:
            self.get_bytes(digest)
        except (OSError, ValueError):
            return False
        return True

    def meta(self, digest: str) -> dict[str, Any] | None:
        path = _meta_path(self.root, digest.lower())
        if not path.is_file():
            return None
        return json.loads(path.read_text(encoding="utf-8"))

    def uri(self, digest: str) -> str:
        """Stable content-addressed URI used in v1 artifact records."""
        return f"cas://sha256/{digest.lower()}"
