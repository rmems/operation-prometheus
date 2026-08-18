#!/usr/bin/env python3
"""Generate a dataset manifest from its curated JSONL and card.

Usage:
    python scripts/build_manifest.py --jsonl datasets/jsonl/<name>.jsonl
    python scripts/build_manifest.py --jsonl ... --check   # fail if stale (CI)

Manifests were hand-authored until GH #39, which is how limen-axon-encoder-v0's
sha256/bytes drifted from its committed JSONL without anything noticing, and how
older manifests ended up missing per-record fields newer ones carry. Everything
in a manifest is derivable from the JSONL plus the card, so derive it.

``created_at`` / ``created_by`` are provenance, not derived data: they are
preserved from the existing manifest unless overridden on the CLI.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent


def record_row(rec: dict[str, Any]) -> dict[str, Any]:
    """Summarize one trajectory record the way the manifest's records[] does."""
    signals = rec.get("review_signals") or []
    return {
        "id": rec["id"],
        "pr_number": rec["pr_number"],
        "training_use": rec["training_use"],
        "task_type": rec["task_type"],
        "domain": rec["domain"],
        "language": rec["language"],
        "quality_score": rec["quality_score"],
        "outcome": rec["outcome"],
        "has_issue_context": bool(rec.get("issue_context")),
        "review_signal_count": len(signals),
        "unique_review_signal_count": len(
            {(s.get("comment") or s.get("suggestion") or "") for s in signals}
        ),
        "patch_chars": len(rec.get("patch") or ""),
        "validation_count": len(rec.get("validation") or []),
        "source_url_count": len(rec.get("source_urls") or []),
    }


def build_manifest(
    jsonl_path: Path,
    card: dict[str, Any],
    *,
    created_at: str,
    created_by: str,
    name: str,
) -> dict[str, Any]:
    data = jsonl_path.read_bytes()
    records = [json.loads(line) for line in data.decode("utf-8").splitlines() if line.strip()]
    return {
        "name": name,
        "schema_version": str(card.get("schema_version") or "pr_trajectory_v0"),
        "created_at": created_at,
        "created_by": created_by,
        "source_repo": str(card.get("source_repo") or ""),
        "jsonl_path": jsonl_path.relative_to(ROOT).as_posix()
        if jsonl_path.is_relative_to(ROOT)
        else str(jsonl_path),
        "record_count": len(records),
        "sha256": hashlib.sha256(data).hexdigest(),
        "bytes": len(data),
        "records": [record_row(r) for r in records],
    }


def render(manifest: dict[str, Any]) -> str:
    return json.dumps(manifest, indent=2, ensure_ascii=False) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--jsonl", type=Path, required=True, help="curated JSONL file")
    parser.add_argument("--card", type=Path, help="dataset card (default: cards/<name>.json)")
    parser.add_argument("--out", type=Path, help="manifest path (default: manifests/<name>.manifest.json)")
    parser.add_argument("--created-at", help="override the preserved created_at (YYYY-MM-DD)")
    parser.add_argument("--created-by", help="override the preserved created_by")
    parser.add_argument(
        "--check",
        action="store_true",
        help="exit non-zero if the committed manifest is stale instead of rewriting it",
    )
    args = parser.parse_args(argv)

    name = args.jsonl.stem
    card_path = args.card or ROOT / "datasets" / "cards" / f"{name}.json"
    out_path = args.out or ROOT / "datasets" / "manifests" / f"{name}.manifest.json"

    card = json.loads(card_path.read_text(encoding="utf-8"))
    existing: dict[str, Any] = {}
    if out_path.exists():
        existing = json.loads(out_path.read_text(encoding="utf-8"))

    created_at = args.created_at or existing.get("created_at")
    created_by = args.created_by or existing.get("created_by")
    if not created_at or not created_by:
        print(
            f"ERROR: no existing manifest at {out_path} to preserve provenance from; "
            "pass --created-at and --created-by.",
            file=sys.stderr,
        )
        return 2

    manifest = build_manifest(
        args.jsonl.resolve(),
        card,
        created_at=str(created_at),
        created_by=str(created_by),
        name=name,
    )
    rendered = render(manifest)
    current = out_path.read_text(encoding="utf-8") if out_path.exists() else None

    if args.check:
        if rendered != current:
            print(
                f"ERROR: {out_path.name} is out of date with {args.jsonl.name}. "
                f"Run: python scripts/build_manifest.py --jsonl {args.jsonl}",
                file=sys.stderr,
            )
            return 1
        print(f"{out_path.name} is up to date ({manifest['record_count']} records).")
        return 0

    if rendered == current:
        print(f"{out_path.name} already up to date ({manifest['record_count']} records).")
        return 0
    out_path.write_text(rendered, encoding="utf-8")
    print(f"Wrote {out_path.name} ({manifest['record_count']} records).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
