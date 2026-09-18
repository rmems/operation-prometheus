"""Shared accumulator for per-record license-closure evaluation."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class EvalAcc:
    record: dict[str, Any]
    card: dict[str, Any]
    manifest: dict[str, Any]
    inventory_index: dict[str, dict[str, Any]]
    prior_index: dict[str, dict[str, Any]] | None
    pull_requests: dict[tuple[str, int], dict[str, Any]] | None
    snapshot_sha256: str
    markdown: str | None
    reasons: list[str] = field(default_factory=list)
    repo: str = ""
    rid: str = ""
    pr_number: int | None = None
    names: list[str] = field(default_factory=list)
    repository: dict[str, Any] | None = None
    declared_record: str | None = None
    declared_card: str | None = None
    declared_manifest: str | None = None
    inventory_license: dict[str, Any] | None = None
    inventory_id: str | None = None
    has_custom: bool = False
    custom_license_obj: dict[str, Any] | None = None
    family: str = "missing"
    source_hash: str | None = None
    digest: str | None = None
    card_digest: str | None = None
    manifest_digest: str | None = None
    declared_digest: str | None = None
    prior_digest: str | None = None
    prior_id: str | None = None
