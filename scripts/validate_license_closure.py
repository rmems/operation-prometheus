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
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

import jsonschema

_SCRIPTS = Path(__file__).resolve().parent
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

from lib.eligibility_render import render_json  # noqa: E402
from lib.license_closure import (  # noqa: E402
    SCHEMA_VERSION,
    build_license_closure_report,
    validate_positive_release,
)
from lib.license_closure_ids import _sha256_or_none  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
SCHEMA_PATH = ROOT / "schemas" / "license_closure.schema.json"


def _reject_nonfinite(constant: str) -> None:
    raise json.JSONDecodeError(f"non-finite constant {constant!r}", constant, 0)


def _object_pairs(pairs: list[tuple[Any, Any]]) -> dict[str, Any]:
    seen: set[str] = set()
    result: dict[str, Any] = {}
    for key, value in pairs:
        name = key if isinstance(key, str) else str(key)
        if name in seen:
            raise json.JSONDecodeError(f"duplicate object key {name!r}", name, 0)
        seen.add(name)
        result[name] = value
    return result


def _loads(text: str) -> Any:
    return json.loads(
        text,
        object_pairs_hook=_object_pairs,
        parse_constant=_reject_nonfinite,
    )


def _load_json(path: Path) -> Any:
    return _loads(path.read_text(encoding="utf-8"))


def _decode_utf8(raw: bytes, path: Path) -> str:
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError(f"{path} is not valid UTF-8") from exc


def _parse_json(raw: bytes, path: Path) -> Any:
    try:
        return _loads(_decode_utf8(raw, path))
    except json.JSONDecodeError as exc:
        raise ValueError(f"{path}: {exc}") from exc


def _require_object(value: Any, path: Path) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{path} must be a JSON object")
    return value


def _parse_jsonl(raw: bytes, path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line in _decode_utf8(raw, path).splitlines():
        if not line.strip():
            continue
        try:
            record = _loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(f"{path}: {exc}") from exc
        if not isinstance(record, dict):
            raise ValueError(f"{path} contains a non-object JSONL row")
        rows.append(record)
    return rows


def _snapshot_sha256(
    explicit: str | None,
    inventory_manifest: dict[str, Any] | None,
    inventory_manifest_path: Path | None,
) -> str:
    explicit_digest = _sha256_or_none(explicit) or ""
    declared = ""
    if inventory_manifest is not None:
        declared = _sha256_or_none(inventory_manifest.get("snapshot_sha256")) or ""
        if not declared:
            source = (
                inventory_manifest_path
                if inventory_manifest_path is not None
                else "inventory-manifest"
            )
            raise ValueError(f"{source} is missing snapshot_sha256")
    if explicit_digest and declared and explicit_digest != declared:
        raise ValueError(
            "--snapshot-sha256 disagrees with inventory-manifest snapshot_sha256"
        )
    digest = declared or explicit_digest
    if not digest:
        source = (
            inventory_manifest_path
            if inventory_manifest_path is not None
            else "snapshot_sha256"
        )
        raise ValueError(f"{source} is missing snapshot_sha256")
    return digest


def _schema_validator():
    schema = _load_json(SCHEMA_PATH)
    return jsonschema.Draft7Validator(
        schema,
        format_checker=jsonschema.Draft7Validator.FORMAT_CHECKER,
    )


def _sha256_bytes(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


_FROZEN_INPUT_ATTRS = (
    "records",
    "card",
    "manifest",
    "inventory",
    "inventory_manifest",
    "prior_inventory",
    "prior_inventory_manifest",
    "markdown_card",
)


def _resolve_path(path: Path) -> Path:
    try:
        return path.resolve()
    except OSError:
        return path


def _paths_are_same_file(left: Path, right: Path) -> bool:
    try:
        return left.exists() and right.exists() and left.samefile(right)
    except OSError:
        return False


def _out_collides_with_frozen_inputs(args: argparse.Namespace) -> Path | None:
    if args.out is None:
        return None
    out = _resolve_path(args.out)
    for attr in _FROZEN_INPUT_ATTRS:
        path = getattr(args, attr)
        if path is None:
            continue
        resolved = _resolve_path(path)
        if resolved == out or _paths_are_same_file(out, resolved):
            return path
    return None


def _hex_digest(value: Any) -> str | None:
    text = str(value or "").strip().lower()
    if len(text) == 64 and all(char in "0123456789abcdef" for char in text):
        return text
    return None


def _require_matching_digest(
    declared: Any, digest: str, path: Path, label: str
) -> str | None:
    expected = _hex_digest(declared)
    if expected is None:
        return f"{label} sha256 is missing or malformed"
    if expected != digest:
        return f"{label} sha256 does not match {path}"
    return None


def _inventory_file_binding_errors(
    *,
    inventory_path: Path,
    inventory_digest: str,
    inventory_manifest: Any | None,
    inventory_manifest_path: Path | None,
) -> list[str]:
    if inventory_manifest_path is None or inventory_manifest is None:
        return [f"{inventory_path} requires an inventory-manifest file binding"]
    files = (
        inventory_manifest.get("files")
        if isinstance(inventory_manifest, dict)
        else None
    )
    listed = (
        files.get(inventory_path.name) or files.get("repositories.jsonl")
        if isinstance(files, dict)
        else None
    )
    if not isinstance(listed, dict):
        return [
            f"{inventory_manifest_path} is missing a repositories.jsonl file binding"
        ]
    mismatch = _require_matching_digest(
        listed.get("sha256"),
        inventory_digest,
        inventory_path,
        f"{inventory_manifest_path} repositories",
    )
    return [mismatch] if mismatch else []


def _publication_binding_errors(
    *,
    records_path: Path,
    records_digest: str,
    record_count: int,
    dataset_manifest: Any,
    dataset_manifest_path: Path,
    inventory_path: Path,
    inventory_digest: str,
    inventory_manifest: Any | None,
    inventory_manifest_path: Path | None,
    prior_inventory_path: Path | None = None,
    prior_inventory_digest: str | None = None,
    prior_inventory_manifest: Any | None = None,
    prior_inventory_manifest_path: Path | None = None,
) -> list[str]:
    errors: list[str] = []
    mismatch = _require_matching_digest(
        dataset_manifest.get("sha256") if isinstance(dataset_manifest, dict) else None,
        records_digest,
        records_path,
        str(dataset_manifest_path),
    )
    if mismatch:
        errors.append(mismatch)
    if isinstance(dataset_manifest, dict) and "record_count" in dataset_manifest:
        declared = dataset_manifest["record_count"]
        if (
            isinstance(declared, bool)
            or not isinstance(declared, int)
            or declared != record_count
        ):
            errors.append(
                f"{dataset_manifest_path} record_count does not match {records_path}"
            )
    errors.extend(
        _inventory_file_binding_errors(
            inventory_path=inventory_path,
            inventory_digest=inventory_digest,
            inventory_manifest=inventory_manifest,
            inventory_manifest_path=inventory_manifest_path,
        )
    )
    if prior_inventory_path is not None:
        errors.extend(
            _inventory_file_binding_errors(
                inventory_path=prior_inventory_path,
                inventory_digest=prior_inventory_digest or "",
                inventory_manifest=prior_inventory_manifest,
                inventory_manifest_path=prior_inventory_manifest_path,
            )
        )
    return errors


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--records", type=Path, required=True, help="Proposed positive JSONL"
    )
    parser.add_argument(
        "--card", type=Path, required=True, help="Machine dataset card JSON"
    )
    parser.add_argument(
        "--manifest", type=Path, required=True, help="Dataset manifest JSON"
    )
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
        "--prior-inventory-manifest",
        type=Path,
        help="Frozen manifest that binds --prior-inventory file bytes",
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


def _read_optional(path: Path | None) -> bytes | None:
    return path.read_bytes() if path is not None else None


def _frozen_inputs(args: argparse.Namespace) -> dict[str, Any]:
    raws = {
        "records": args.records.read_bytes(),
        "card": args.card.read_bytes(),
        "manifest": args.manifest.read_bytes(),
        "inventory": args.inventory.read_bytes(),
        "inventory_manifest": _read_optional(args.inventory_manifest),
        "prior_inventory": _read_optional(args.prior_inventory),
        "prior_inventory_manifest": _read_optional(args.prior_inventory_manifest),
        "markdown_card": _read_optional(args.markdown_card),
    }
    parsed = {
        "records": _parse_jsonl(raws["records"], args.records),
        "card": _require_object(_parse_json(raws["card"], args.card), args.card),
        "manifest": _require_object(
            _parse_json(raws["manifest"], args.manifest), args.manifest
        ),
        "inventory": _parse_jsonl(raws["inventory"], args.inventory),
        "inventory_manifest": (
            _parse_json(raws["inventory_manifest"], args.inventory_manifest)
            if raws["inventory_manifest"] is not None
            else None
        ),
        "prior_inventory_manifest": (
            _parse_json(
                raws["prior_inventory_manifest"], args.prior_inventory_manifest
            )
            if raws["prior_inventory_manifest"] is not None
            else None
        ),
        "prior_inventory": (
            _parse_jsonl(raws["prior_inventory"], args.prior_inventory)
            if raws["prior_inventory"] is not None
            else None
        ),
        "markdown_card": (
            _decode_utf8(raws["markdown_card"], args.markdown_card)
            if raws["markdown_card"] is not None
            else None
        ),
    }
    parsed["snapshot_sha256"] = _snapshot_sha256(
        args.snapshot_sha256,
        parsed["inventory_manifest"]
        if isinstance(parsed["inventory_manifest"], dict)
        else None,
        args.inventory_manifest,
    )
    parsed["raws"] = raws
    return parsed


def _check_args(args: argparse.Namespace) -> int:
    colliding = _out_collides_with_frozen_inputs(args)
    if colliding is not None:
        print(
            f"ERROR: --out would overwrite frozen validation input {colliding}",
            file=sys.stderr,
        )
        return 2
    if not args.snapshot_sha256 and not args.inventory_manifest:
        print(
            "ERROR: pass --snapshot-sha256 or --inventory-manifest",
            file=sys.stderr,
        )
        return 2
    return 0


def _apply_binding_errors(
    report: dict[str, Any], args: argparse.Namespace, inputs: dict[str, Any]
) -> None:
    raws = inputs["raws"]
    binding_errors = _publication_binding_errors(
        records_path=args.records,
        records_digest=_sha256_bytes(raws["records"]),
        record_count=report["counts"]["record_count"],
        dataset_manifest=inputs["manifest"],
        dataset_manifest_path=args.manifest,
        inventory_path=args.inventory,
        inventory_digest=_sha256_bytes(raws["inventory"]),
        inventory_manifest=inputs["inventory_manifest"],
        inventory_manifest_path=args.inventory_manifest,
        prior_inventory_path=args.prior_inventory,
        prior_inventory_digest=(
            _sha256_bytes(raws["prior_inventory"])
            if raws["prior_inventory"] is not None
            else None
        ),
        prior_inventory_manifest=inputs["prior_inventory_manifest"],
        prior_inventory_manifest_path=args.prior_inventory_manifest,
    )
    if binding_errors:
        report["bundle_errors"] = (
            list(report.get("bundle_errors") or []) + binding_errors
        )
        report["closed"] = False


def _check_schema(report: dict[str, Any]) -> int:
    validator = _schema_validator()
    schema_errors = sorted(
        validator.iter_errors(report), key=lambda error: list(error.path)
    )
    if not schema_errors:
        return 0
    print(
        "ERROR: license-closure manifest failed schema validation:", file=sys.stderr
    )
    for error in schema_errors:
        path = ".".join(str(part) for part in error.absolute_path) or "(root)"
        print(f"  [{path}] {error.message}", file=sys.stderr)
    return 1


def _emit_report(report: dict[str, Any], args: argparse.Namespace) -> int:
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
    return 0


def _report_errors(report: dict[str, Any]) -> int:
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


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    early = _check_args(args)
    if early:
        return early
    try:
        inputs = _frozen_inputs(args)
        report = build_license_closure_report(
            inputs["records"],
            inputs["card"],
            inputs["manifest"],
            inputs["inventory"],
            snapshot_sha256=inputs["snapshot_sha256"],
            prior_repositories=inputs["prior_inventory"],
            markdown_card=inputs["markdown_card"],
        )
    except (OSError, UnicodeDecodeError, ValueError, json.JSONDecodeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    _apply_binding_errors(report, args, inputs)
    if _check_schema(report):
        return 1
    if _emit_report(report, args):
        return 1
    return _report_errors(report)


if __name__ == "__main__":
    raise SystemExit(main())
