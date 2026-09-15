"""Shared types for trajectory v1 normalization."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .cas import ContentAddressedStore

V1_SCHEMA_VERSION = "1.0"
COLLECTION_POLICY = "public-github-read-only"


@dataclass
class V1NormalizeOptions:
    artifact_store: ContentAddressedStore | None = None
    max_patch_bytes: int = 96 * 1024
    source_license: str | None = None
    raw_path: Path | None = None


@dataclass
class EventDraft:
    event_id: str
    timestamp: str | None
    actor: dict[str, str]
    event_type: str
    code_state: dict[str, str] | None = None
    evidence: list[str] | None = None
    disposition: str | None = None
    content: str | None = None


@dataclass
class EventContext:
    raw: dict[str, Any]
    source_id: str
    pull: dict[str, Any]
    base_oid: Any
    head_oid: Any
    author: dict[str, str]
    events: list[dict[str, Any]]
