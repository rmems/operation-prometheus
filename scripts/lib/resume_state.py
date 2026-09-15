"""Durable collector resume state.

State is a single JSON document written atomically (temp + replace).  A PR
shard is marked ``complete`` only after its raw record and optional object
pack have been written and content-hashed.  Crashes or API rate-limit
failures leave the item in ``pending`` / ``in_progress`` so a later run
retries it instead of emitting a duplicate or truncated shard.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .source_inventory_common import sha256_json

SCHEMA_VERSION = "collector_resume_v1"
VALID_STATUSES = frozenset(
    {"pending", "in_progress", "complete", "failed", "quarantined"}
)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _atomic_write(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    tmp.replace(path)


class ResumeState:
    """Per-candidate collection progress persisted under ``path``."""

    def __init__(self, path: Path, *, inventory_sha256: str | None = None) -> None:
        self.path = Path(path)
        self.data: dict[str, Any] = {
            "schema_version": SCHEMA_VERSION,
            "inventory_sha256": inventory_sha256,
            "updated_at": _now(),
            "items": {},
        }
        if self.path.is_file():
            loaded = json.loads(self.path.read_text(encoding="utf-8"))
            if not isinstance(loaded, dict):
                raise ValueError(f"Resume state is not an object: {self.path}")
            loaded_schema = loaded.get("schema_version")
            if loaded_schema not in (None, SCHEMA_VERSION):
                raise ValueError(
                    f"Unsupported resume schema {loaded_schema!r} in {self.path}"
                )
            items = loaded.get("items") or {}
            if not isinstance(items, dict):
                raise ValueError(f"Resume state items must be an object: {self.path}")
            self.data["items"] = items
            if loaded.get("inventory_sha256") and not inventory_sha256:
                self.data["inventory_sha256"] = loaded.get("inventory_sha256")
            elif inventory_sha256:
                self.data["inventory_sha256"] = inventory_sha256

    def get(self, item_id: str) -> dict[str, Any] | None:
        item = self.data["items"].get(item_id)
        return dict(item) if isinstance(item, dict) else None

    def status(self, item_id: str) -> str:
        item = self.get(item_id)
        if not item:
            return "pending"
        status = str(item.get("status") or "pending")
        return status if status in VALID_STATUSES else "pending"

    def is_complete(self, item_id: str, *, record_sha256: str | None = None) -> bool:
        """True when a prior run finished this item and the shard hash still matches."""
        item = self.get(item_id)
        if not item or item.get("status") != "complete":
            return False
        if record_sha256 is None:
            return True
        stored = item.get("record_sha256")
        return stored == record_sha256

    def mark(
        self,
        item_id: str,
        status: str,
        *,
        extra: dict[str, Any] | None = None,
        persist: bool = True,
    ) -> dict[str, Any]:
        if status not in VALID_STATUSES:
            raise ValueError(f"Unknown resume status {status}")
        current = self.get(item_id) or {}
        current["status"] = status
        current["updated_at"] = _now()
        if extra:
            current.update(extra)
        self.data["items"][item_id] = current
        self.data["updated_at"] = _now()
        if persist:
            self.save()
        return dict(current)

    def save(self) -> None:
        _atomic_write(self.path, self.data)

    def counts(self) -> dict[str, int]:
        tallies = {name: 0 for name in sorted(VALID_STATUSES)}
        for item in self.data["items"].values():
            status = str((item or {}).get("status") or "pending")
            if status not in tallies:
                status = "pending"
            tallies[status] += 1
        return tallies

    def fingerprint(self) -> str:
        """Canonical hash of item statuses (excludes updated_at timestamps)."""
        items = {}
        for item_id, item in sorted(self.data["items"].items()):
            if not isinstance(item, dict):
                continue
            items[item_id] = {
                key: item[key]
                for key in (
                    "status",
                    "repo",
                    "pr_number",
                    "record_sha256",
                    "pack_sha256",
                    "reason",
                )
                if key in item
            }
        return sha256_json({"items": items, "inventory_sha256": self.data.get("inventory_sha256")})
