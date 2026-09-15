#!/usr/bin/env python3
"""Validate source-license closure before positive corpus publication.

Usage:
    python scripts/validate_license_closure.py \\
      --records datasets/jsonl/<name>.jsonl \\
      --card datasets/cards/<name>.json \\
      --manifest datasets/manifests/<name>.manifest.json \\
      --inventory datasets/inventory/v0.7/repositories.jsonl \\
      --inventory-manifest datasets/inventory/v0.7/manifest.json

The checker reads only frozen local evidence. It does not contact GitHub and
does not treat this repository's Apache-2.0 license as a source relicense.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

_SCRIPTS = Path(__file__).resolve().parent
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

from lib.eligibility_render import render_json  # noqa: E402
from lib.license_closure import (  # noqa: E402
    SCHEMA_VERSION,
    build_license_closure_report,
    validate_positive_release,
)

ROOT = Path(__file__).resolve().parent.parent
SCHEMA_PATH = ROOT / "schemas" / "license_closure.schema.json"


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        record = json.loads(line)
        if not isinstance(record, dict):
            raise ValueError(f"{path} contains a non-object JSONL row")
        rows.append(record)
    return rows


def _snapshot_sha256(args: argparse.Namespace) -> str:
    if args.snapshot_sha256:
        return str(args.snapshot_sha256).strip().lower()
    manifest = _load_json(args.inventory_manifest)
    digest = str(manifest.get("snapshot_sha256") or "").strip().lower()
    if not digest:
        raise ValueError(f"{args.inventory_manifest} is missing snapshot_sha256")
    return digest


def _schema_validator():
    try:
        import jsonschema
    except ImportError as exc:
        raise RuntimeError("jsonschema is required") from exc
    schema = _load_json(SCHEMA_PATH)
    return jsonschema.Draft7Validator(
        schema,
        format_checker=jsonschema.Draft7Validator.FORMAT_CHECKER,
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--records", type=Path, required=True, help="Proposed positive JSONL")
    parser.add_argument("--card", type=Path, required=True, help="Machine dataset card JSON")
    parser.add_argument("--manifest", type=Path, required=True, help="Dataset manifest JSON")
    parser.add_argument(
        "--inventory",
        type=Path,
        required=True,
        help="Frozen source-inventory repositories JSONL",
    )
    parser.add_argument(
        "--inventory-manifest",
        type=Path,
        help="Eligibility inventory manifest (supplies snapshot_sha256)",
    )
    parser.add_argument("--snapshot-sha256", help="Frozen source-snapshot digest")
    parser.add_argument(
        "--prior-inventory",
        type=Path,
        help="Previous frozen repositories JSONL used to detect license changes",
    )
    parser.add_argument(
        "--markdown-card",
        type=Path,
        help="Optional human dataset card; requires a License / provenance section",
    )
    parser.add_argument("--out", type=Path, help="Write the license-closure manifest")
    parser.add_argument(
        "--check",
        action="store_true",
        help="Require the written manifest (if any) to match the rebuilt report",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if not args.snapshot_sha256 and not args.inventory_manifest:
        print(
            "ERROR: pass --snapshot-sha256 or --inventory-manifest",
            file=sys.stderr,
        )
        return 2

    try:
        snapshot_sha256 = _snapshot_sha256(args)
        report = build_license_closure_report(
            _load_jsonl(args.records),
            _load_json(args.card),
            _load_json(args.manifest),
            _load_jsonl(args.inventory),
            snapshot_sha256=snapshot_sha256,
            prior_repositories=(
                _load_jsonl(args.prior_inventory) if args.prior_inventory else None
            ),
            markdown_card=(
                args.markdown_card.read_text(encoding="utf-8")
                if args.markdown_card
                else None
            ),
        )
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    validator = _schema_validator()
    schema_errors = sorted(validator.iter_errors(report), key=lambda error: list(error.path))
    if schema_errors:
        print("ERROR: license-closure manifest failed schema validation:", file=sys.stderr)
        for error in schema_errors:
            path = ".".join(str(part) for part in error.absolute_path) or "(root)"
            print(f"  [{path}] {error.message}", file=sys.stderr)
        return 1

    rendered = render_json(report)
    if args.check and args.out:
        current = args.out.read_bytes() if args.out.exists() else b""
        if current != rendered:
            print(
                f"ERROR: {args.out} is stale. Rebuild with the same arguments "
                "and omit --check.",
                file=sys.stderr,
            )
            return 1
    if args.out and not args.check:
        args.out.write_bytes(rendered)
        print(f"Wrote {args.out} ({SCHEMA_VERSION}).")
    elif not args.out:
        sys.stdout.buffer.write(rendered)

    errors = validate_positive_release(report)
    if errors:
        print("License-closure FAILED:", file=sys.stderr)
        for error in errors:
            print(error, file=sys.stderr)
        return 1
    print(
        "License closure passed "
        f"({report['counts']['released_positive_count']} released positives, "
        f"families={report['license_families']}).",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
