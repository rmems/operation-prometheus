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


def _reject_nonfinite(constant: str) -> None:
    raise json.JSONDecodeError(f"non-finite constant {constant!r}", constant, 0)


def _load_json(path: Path) -> Any:
    return json.loads(
        path.read_text(encoding="utf-8"),
        parse_constant=_reject_nonfinite,
    )


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
    records = [
        json.loads(line) for line in data.decode("utf-8").splitlines() if line.strip()
    ]
    source_repo: dict[str, str] = {}
    if "source_repo" in card:
        singular = card["source_repo"]
        if isinstance(singular, str) and singular.strip():
            source_repo["source_repo"] = singular
    return {
        "name": name,
        "schema_version": str(card.get("schema_version") or "pr_trajectory_v0"),
        "created_at": created_at,
        "created_by": created_by,
        **source_repo,
        "jsonl_path": jsonl_path.relative_to(ROOT).as_posix()
        if jsonl_path.is_relative_to(ROOT)
        else str(jsonl_path),
        "record_count": len(records),
        "sha256": hashlib.sha256(data).hexdigest(),
        "bytes": len(data),
        "records": [record_row(r) for r in records],
        **{
            key: card[key]
            for key in (
                "source_repos",
                "source_license",
                "source_licenses",
                "license_evidence_digest",
                "license_evidence_digests",
                "license_families",
                "unresolved_license_count",
            )
            if key in card
        },
    }


def render(manifest: dict[str, Any]) -> str:
    return json.dumps(manifest, indent=2, ensure_ascii=False, allow_nan=False) + "\n"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--jsonl", type=Path, required=True, help="curated JSONL file")
    parser.add_argument(
        "--card", type=Path, help="dataset card (default: cards/<name>.json)"
    )
    parser.add_argument(
        "--out",
        type=Path,
        help="manifest path (default: manifests/<name>.manifest.json)",
    )
    parser.add_argument(
        "--created-at", help="override the preserved created_at (YYYY-MM-DD)"
    )
    parser.add_argument("--created-by", help="override the preserved created_by")
    parser.add_argument(
        "--check",
        action="store_true",
        help="exit non-zero if the committed manifest is stale instead of rewriting it",
    )
    return parser


def _load_inputs(args: argparse.Namespace) -> tuple[dict[str, Any], dict[str, Any]] | int:
    name = args.jsonl.stem
    card_path = args.card or ROOT / "datasets" / "cards" / f"{name}.json"
    out_path = args.out or ROOT / "datasets" / "manifests" / f"{name}.manifest.json"
    try:
        card = _load_json(card_path)
        existing = _load_json(out_path) if out_path.exists() else {}
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    return card, {"existing": existing, "out_path": out_path}


def _provenance(args: argparse.Namespace, existing: dict[str, Any], out_path: Path):
    created_at = args.created_at or existing.get("created_at")
    created_by = args.created_by or existing.get("created_by")
    if not all((created_at, created_by)):
        print(
            f"ERROR: no existing manifest at {out_path} to preserve provenance from; "
            "pass --created-at and --created-by.",
            file=sys.stderr,
        )
        return None
    return str(created_at), str(created_by)


def _emit_check(rendered: str, current: str | None, args: argparse.Namespace) -> int:
    name = args.jsonl.stem
    out_path = args.out or ROOT / "datasets" / "manifests" / f"{name}.manifest.json"
    if rendered != current:
        print(
            f"ERROR: {out_path.name} is out of date with {args.jsonl.name}. "
            f"Run: python scripts/build_manifest.py --jsonl {args.jsonl}",
            file=sys.stderr,
        )
        return 1
    return 0


def _emit_write(rendered: str, current: str | None, out_path: Path, count: int) -> int:
    if rendered == current:
        print(f"{out_path.name} already up to date ({count} records).")
        return 0
    out_path.write_text(rendered, encoding="utf-8")
    print(f"Wrote {out_path.name} ({count} records).")
    return 0


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    loaded = _load_inputs(args)
    if isinstance(loaded, int):
        return loaded
    card, ctx = loaded
    provenance = _provenance(args, ctx["existing"], ctx["out_path"])
    if provenance is None:
        return 2
    manifest = build_manifest(
        args.jsonl.resolve(),
        card,
        created_at=provenance[0],
        created_by=provenance[1],
        name=args.jsonl.stem,
    )
    rendered = render(manifest)
    out_path = ctx["out_path"]
    current = out_path.read_text(encoding="utf-8") if out_path.exists() else None
    if args.check:
        if _emit_check(rendered, current, args):
            return 1
        print(f"{out_path.name} is up to date ({manifest['record_count']} records).")
        return 0
    return _emit_write(rendered, current, out_path, manifest["record_count"])


if __name__ == "__main__":
    raise SystemExit(main())
