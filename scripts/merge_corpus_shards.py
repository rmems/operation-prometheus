#!/usr/bin/env python3
"""Merge verified corpus shards into one canonical global manifest.

Usage:
    python scripts/merge_corpus_shards.py \\
      --inventory-dir datasets/inventory/v0.7 \\
      --shards-dir datasets/shards/v0.7 \\
      --out-dir datasets/corpus/v0.7
    python scripts/merge_corpus_shards.py ... --check
    python scripts/merge_corpus_shards.py ... --check-determinism
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path
from typing import Any

import jsonschema

_SCRIPTS = Path(__file__).resolve().parent
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

from lib.corpus_shards import (  # noqa: E402
    SHARD_COUNT,
    merge_corpus_shards,
)

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger("merge_corpus_shards")

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_INVENTORY = ROOT / "datasets" / "inventory" / "v0.7"
DEFAULT_SHARDS = ROOT / "datasets" / "shards" / "v0.7"
DEFAULT_OUT = ROOT / "datasets" / "corpus" / "v0.7"
RECORD_SCHEMA = ROOT / "schemas" / "corpus_shard_record.schema.json"
SHARD_MANIFEST_SCHEMA = ROOT / "schemas" / "corpus_shard_manifest.schema.json"
GLOBAL_MANIFEST_SCHEMA = ROOT / "schemas" / "corpus_global_manifest.schema.json"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--inventory-dir",
        type=Path,
        default=DEFAULT_INVENTORY,
        help="Frozen eligibility inventory directory",
    )
    parser.add_argument(
        "--shards-dir",
        type=Path,
        default=DEFAULT_SHARDS,
        help="Directory containing shard-0, shard-1, and shard-2 outputs",
    )
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=DEFAULT_OUT,
        help="Directory for the canonical global manifest and merged JSONL",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Fail if committed outputs differ instead of rewriting them",
    )
    parser.add_argument(
        "--check-determinism",
        action="store_true",
        help="Merge twice in memory and require byte-identical artifacts",
    )
    return parser


def _load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return value


def _validator(schema_path: Path):
    return jsonschema.Draft7Validator(
        _load_json(schema_path),
        format_checker=jsonschema.Draft7Validator.FORMAT_CHECKER,
    )


def _raise_validation_errors(errors: list[tuple[str, object]]) -> None:
    if not errors:
        return
    messages: list[str] = []
    for prefix, error in errors[:50]:
        path = ".".join(str(part) for part in error.absolute_path) or "(root)"
        messages.append(f"{prefix}.{path}: {error.message}")
    raise ValueError("Schema validation failed:\n" + "\n".join(messages))


def _document_validation_errors(
    name: str, value: dict[str, Any], schema_path: Path
) -> list[tuple[str, object]]:
    validator = _validator(schema_path)
    return [(name, error) for error in validator.iter_errors(value)]


def _jsonl_lines(data: bytes) -> list[bytes]:
    body = data[:-1] if data.endswith(b"\n") else data
    if not body:
        return []
    return body.split(b"\n")


def validate_merge_artifacts(
    shards_dir: Path,
    manifest: dict[str, Any],
    rendered: dict[str, bytes],
) -> None:
    """Strict-schema-validate shard records/manifests and the global manifest."""
    errors: list[tuple[str, object]] = []
    record_validator = _validator(RECORD_SCHEMA)
    for number in range(SHARD_COUNT):
        shard_path = shards_dir / f"shard-{number}"
        shard_manifest = _load_json(shard_path / "manifest.json")
        errors.extend(
            _document_validation_errors(
                f"shard-{number}.manifest", shard_manifest, SHARD_MANIFEST_SCHEMA
            )
        )
        shard_records = _jsonl_lines((shard_path / "records.jsonl").read_bytes())
        for index, line in enumerate(shard_records, start=1):
            record = json.loads(line.decode("utf-8"))
            errors.extend(
                (f"shard-{number}.records[{index}]", error)
                for error in record_validator.iter_errors(record)
            )
    for index, line in enumerate(_jsonl_lines(rendered["records.jsonl"]), start=1):
        record = json.loads(line.decode("utf-8"))
        errors.extend(
            (f"global.records[{index}]", error)
            for error in record_validator.iter_errors(record)
        )
    errors.extend(
        _document_validation_errors("global.manifest", manifest, GLOBAL_MANIFEST_SCHEMA)
    )
    errors.sort(key=lambda item: (item[0], [str(part) for part in item[1].absolute_path]))
    _raise_validation_errors(errors)


def _write_outputs(out_dir: Path, rendered: dict[str, bytes]) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    for name, data in rendered.items():
        path = out_dir / name
        tmp_path = path.with_suffix(path.suffix + ".tmp")
        tmp_path.write_bytes(data)
        tmp_path.replace(path)


def _check_outputs(out_dir: Path, rendered: dict[str, bytes]) -> list[str]:
    stale: list[str] = []
    for name, expected in rendered.items():
        path = out_dir / name
        if not path.exists() or path.read_bytes() != expected:
            stale.append(name)
    return stale


def _merge(args: argparse.Namespace) -> tuple[dict[str, Any], dict[str, bytes]]:
    inventory_dir = args.inventory_dir.resolve()
    shards_dir = args.shards_dir.resolve()
    manifest, rendered = merge_corpus_shards(inventory_dir, shards_dir)
    if args.check_determinism:
        second_manifest, second_rendered = merge_corpus_shards(inventory_dir, shards_dir)
        if rendered != second_rendered or second_manifest != manifest:
            raise ValueError("Second merge from unchanged inputs was not byte-identical")
    validate_merge_artifacts(shards_dir, manifest, rendered)
    return manifest, rendered


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        manifest, rendered = _merge(args)
    except (OSError, json.JSONDecodeError, RuntimeError, ValueError) as exc:
        logger.error("%s", exc)
        return 1

    out_dir = args.out_dir.resolve()
    if args.check:
        stale = _check_outputs(out_dir, rendered)
        if stale:
            logger.error("Global corpus outputs are stale or missing: %s", ", ".join(stale))
            return 1
        logger.info("Global corpus outputs are current and deterministic")
        return 0
    _write_outputs(out_dir, rendered)
    logger.info(
        "Wrote %s records (excluded=%s quarantined=%s) -> %s",
        manifest["counts"]["record_count"],
        manifest["exclusion_total"],
        manifest["quarantine_total"],
        out_dir,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
