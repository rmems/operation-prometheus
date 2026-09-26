#!/usr/bin/env python3
"""PR-gate trajectory contract: schemas, fixtures, and strict policy."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_SCRIPTS = Path(__file__).resolve().parent
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

from lib.ci_contracts import ROOT  # noqa: E402
from validate_jsonl import load_schema, validate_file  # noqa: E402

try:
    import jsonschema
except ImportError:
    jsonschema = None


FIXTURE_DIR = ROOT / "tests" / "fixtures" / "v1"
V0_EXAMPLE = ROOT / "datasets" / "examples" / "trajectory-v0-example.json"
KNOWN_GOOD_FIXTURES = (
    "software_valid.jsonl",
    "research_valid.jsonl",
    "head_oid_only.jsonl",
    "after_blob_only.jsonl",
    "remote_magnet_uri.jsonl",
    "successful_last_neutral.jsonl",
    "failed_last_neutral.jsonl",
    "research_no_disposition.jsonl",
)


def _validators():
    if jsonschema is None:
        raise RuntimeError("jsonschema is required")
    v0 = jsonschema.Draft7Validator(
        load_schema(ROOT / "schemas" / "pr_trajectory.schema.json"),
        format_checker=jsonschema.Draft7Validator.FORMAT_CHECKER,
    )
    v1 = jsonschema.Draft7Validator(
        load_schema(ROOT / "schemas" / "trajectory_v1.schema.json"),
        format_checker=jsonschema.Draft7Validator.FORMAT_CHECKER,
    )
    return v0, v1


def round_trip_errors(path: Path) -> list[str]:
    """Re-serialize each record without rewriting raw evidence fields."""
    errors: list[str] = []
    original = path.read_text(encoding="utf-8")
    for line_number, line in enumerate(original.splitlines(), start=1):
        if not line.strip():
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            # validate_file already records the parse error for this line.
            continue
        rebuilt = json.dumps(record, ensure_ascii=False)
        if json.loads(rebuilt) != record:
            errors.append(
                f"{path.name}:{line_number} round-trip mutated record content"
            )
    return errors


def production_files() -> list[Path]:
    return sorted((ROOT / "datasets" / "jsonl").glob("*.jsonl"))


def _v0_example_errors(v0) -> list[str]:
    if not V0_EXAMPLE.is_file():
        return [f"{V0_EXAMPLE.name} is missing"]
    errors: list[str] = []
    record = json.loads(V0_EXAMPLE.read_text(encoding="utf-8"))
    if json.loads(json.dumps(record, ensure_ascii=False)) != record:
        errors.append(f"{V0_EXAMPLE.name} v0 example round-trip mutated content")
    for error in sorted(v0.iter_errors(record), key=lambda item: list(item.path)):
        path = ".".join(str(part) for part in error.absolute_path) or "(root)"
        errors.append(f"{V0_EXAMPLE.name} [{path}] - {error.message}")
    return errors


def _file_contract_errors(filepath: Path, v0, v1) -> list[str]:
    file_errors = validate_file(filepath, v0, v1, strict_policy=True)
    errors = [*file_errors, *round_trip_errors(filepath)]
    relative = (
        filepath.name
        if not filepath.is_relative_to(ROOT)
        else filepath.relative_to(ROOT)
    )
    if not file_errors:
        print(f"  ✓ {relative}")
    else:
        print(f"  ✗ {relative} ({len(file_errors)} error(s))")
    return errors


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "files", nargs="*", type=Path, help="Extra JSONL files that must pass"
    )
    args = parser.parse_args(argv)
    v0, v1 = _validators()
    errors = _v0_example_errors(v0)

    targets = production_files()
    targets.extend(FIXTURE_DIR / name for name in KNOWN_GOOD_FIXTURES)
    targets.extend(args.files)
    for filepath in targets:
        errors.extend(_file_contract_errors(filepath, v0, v1))

    if errors:
        print("\ntrajectory-contract FAILED:")
        for error in errors:
            print(error)
        return 1
    print("\ntrajectory-contract passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
