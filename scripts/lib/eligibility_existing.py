"""Loading of existing dataset rows for duplicate and orphan detection."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .source_inventory import sha256_json


def _load_existing_rows(repo_root: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for path in sorted((repo_root / "datasets" / "jsonl").glob("*.jsonl")):
        for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            if not line.strip():
                continue
            record = json.loads(line)
            if not isinstance(record, dict):
                continue
            repo = str(record.get("repo") or "")
            pr_number = record.get("pr_number")
            if not repo or not isinstance(pr_number, int):
                continue
            rows.append(
                {
                    "repo": repo,
                    "pr_number": pr_number,
                    "record_id": record.get("id"),
                    "file": path.relative_to(repo_root).as_posix(),
                    "line": line_number,
                    "canonical_sha256": sha256_json(record),
                }
            )
    return rows
