"""Canonical byte rendering for eligibility-ledger artifacts."""

from __future__ import annotations

import hashlib
import json
from typing import Any

from .source_inventory import canonical_json_bytes


def render_jsonl(rows: list[dict[str, Any]]) -> bytes:
    return b"".join(canonical_json_bytes(row) + b"\n" for row in rows)


def render_json(value: dict[str, Any]) -> bytes:
    return json.dumps(
        value,
        indent=2,
        ensure_ascii=False,
        sort_keys=True,
    ).encode("utf-8") + b"\n"


def render_artifacts(artifacts: dict[str, Any]) -> dict[str, bytes]:
    rendered = {
        "repositories.jsonl": render_jsonl(artifacts["repositories"]),
        "candidates.jsonl": render_jsonl(artifacts["candidates"]),
        "duplicates.jsonl": render_jsonl(artifacts["duplicates"]),
        "baseline-report.json": render_json(artifacts["baseline_report"]),
    }
    manifest = dict(artifacts["manifest"])
    manifest["files"] = {
        name: {"bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}
        for name, data in sorted(rendered.items())
    }
    rendered["manifest.json"] = render_json(manifest)
    return rendered
