#!/usr/bin/env python3
"""Build the deterministic v0.7 eligibility ledger from a frozen snapshot."""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

_SCRIPTS = Path(__file__).resolve().parent
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

from lib.eligibility import build_eligibility_artifacts, render_artifacts  # noqa: E402
from lib.source_inventory import sha256_json  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger("build_eligibility_ledger")

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_POLICY = ROOT / "datasets" / "inventory" / "v0.7" / "policy.json"
DEFAULT_OUT = ROOT / "datasets" / "inventory" / "v0.7"
SOURCE_SCHEMA = ROOT / "schemas" / "source_inventory.schema.json"
POLICY_SCHEMA = ROOT / "schemas" / "eligibility_policy.schema.json"
LEDGER_SCHEMA = ROOT / "schemas" / "eligibility_ledger.schema.json"
REPOSITORY_SCHEMA = ROOT / "schemas" / "source_repository.schema.json"
DUPLICATE_SCHEMA = ROOT / "schemas" / "duplicate_group.schema.json"
BASELINE_REPORT_SCHEMA = ROOT / "schemas" / "eligibility_baseline_report.schema.json"
MANIFEST_SCHEMA = ROOT / "schemas" / "eligibility_manifest.schema.json"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--snapshot", type=Path, required=True, help="Frozen source snapshot JSON")
    parser.add_argument("--policy", type=Path, default=DEFAULT_POLICY, help="Eligibility policy JSON")
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT, help="Ledger output directory")
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=ROOT,
        help="Repository root containing existing datasets/jsonl files",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Fail if committed outputs differ instead of rewriting them",
    )
    parser.add_argument(
        "--check-determinism",
        action="store_true",
        help="Build twice in memory and require byte-identical artifacts",
    )
    parser.add_argument(
        "--strict-baseline",
        action="store_true",
        help="Fail when baseline drift lacks evidence or existing rows are orphaned",
    )
    return parser


def _load_json(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return value


def _validator(schema_path: Path):
    try:
        import jsonschema
    except ImportError as exc:
        raise RuntimeError("jsonschema is required") from exc
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


def _validate_inputs(snapshot: dict, policy: dict) -> None:
    errors: list[tuple[str, object]] = []
    for prefix, value, schema_path in (
        ("snapshot", snapshot, SOURCE_SCHEMA),
        ("policy", policy, POLICY_SCHEMA),
    ):
        validator = _validator(schema_path)
        document_errors = sorted(
            validator.iter_errors(value),
            key=lambda item: [str(part) for part in item.absolute_path],
        )
        errors.extend((prefix, error) for error in document_errors)
    _raise_validation_errors(errors)


def _validate_artifacts(artifacts: dict, rendered: dict[str, bytes]) -> None:
    errors: list[tuple[str, object]] = []
    for name, rows, schema_path in (
        ("repository", artifacts["repositories"], REPOSITORY_SCHEMA),
        ("candidate", artifacts["candidates"], LEDGER_SCHEMA),
        ("duplicate", artifacts["duplicates"], DUPLICATE_SCHEMA),
    ):
        validator = _validator(schema_path)
        for index, row in enumerate(rows):
            for error in validator.iter_errors(row):
                errors.append((f"{name}[{index}]", error))
    for name, value, schema_path in (
        ("baseline_report", artifacts["baseline_report"], BASELINE_REPORT_SCHEMA),
        ("manifest", json.loads(rendered["manifest.json"]), MANIFEST_SCHEMA),
    ):
        validator = _validator(schema_path)
        for error in validator.iter_errors(value):
            errors.append((name, error))
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


def _verify_snapshot_hash(snapshot: dict) -> None:
    declared_snapshot_hash = snapshot.pop("snapshot_sha256", None)
    actual_snapshot_hash = sha256_json(snapshot)
    snapshot["snapshot_sha256"] = declared_snapshot_hash
    if not declared_snapshot_hash or declared_snapshot_hash != actual_snapshot_hash:
        raise ValueError(
            "Snapshot sha256 does not match its canonical content "
            f"(declared={declared_snapshot_hash}, actual={actual_snapshot_hash})"
        )


def _check_determinism(args: argparse.Namespace, snapshot: dict, policy: dict, rendered: dict[str, bytes]) -> None:
    if not args.check_determinism:
        return
    second = render_artifacts(
        build_eligibility_artifacts(snapshot, policy, args.repo_root.resolve())
    )
    if rendered != second:
        raise ValueError("Second build from unchanged inputs was not byte-identical")


def _enforce_strict_baseline(args: argparse.Namespace, artifacts: dict) -> None:
    if not args.strict_baseline:
        return
    report = artifacts["baseline_report"]
    if not report.get("complete"):
        raise ValueError("Baseline report contains unexplained drift")
    if report.get("orphan_existing_dataset_candidates"):
        raise ValueError("Existing dataset rows are absent from the frozen source inventory")


def _build_and_validate(args: argparse.Namespace) -> tuple[dict, dict[str, bytes]]:
    snapshot = _load_json(args.snapshot.resolve())
    _verify_snapshot_hash(snapshot)
    policy = _load_json(args.policy.resolve())
    _validate_inputs(snapshot, policy)
    artifacts = build_eligibility_artifacts(snapshot, policy, args.repo_root.resolve())
    rendered = render_artifacts(artifacts)
    _validate_artifacts(artifacts, rendered)
    _check_determinism(args, snapshot, policy, rendered)
    _enforce_strict_baseline(args, artifacts)
    return artifacts, rendered


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        artifacts, rendered = _build_and_validate(args)
    except (OSError, json.JSONDecodeError, RuntimeError, ValueError) as exc:
        logger.error("%s", exc)
        return 1

    out_dir = args.out_dir.resolve()
    if args.check:
        stale = _check_outputs(out_dir, rendered)
        if stale:
            logger.error("Eligibility outputs are stale or missing: %s", ", ".join(stale))
            return 1
        logger.info("Eligibility outputs are current and deterministic")
        return 0
    _write_outputs(out_dir, rendered)
    logger.info(
        "Wrote %s repositories, %s candidates, and %s duplicate groups -> %s",
        len(artifacts["repositories"]),
        len(artifacts["candidates"]),
        len(artifacts["duplicates"]),
        out_dir,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
