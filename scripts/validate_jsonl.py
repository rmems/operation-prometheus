#!/usr/bin/env python3
"""Validate JSONL trajectory files against pr_trajectory.schema.json.

Usage:
    python scripts/validate_jsonl.py datasets/jsonl/*.jsonl

Each file is read line-by-line. Each non-empty line must be valid JSON
conforming to the PR Trajectory schema. Exits 0 if all records pass,
non-zero if any validation error is found.
"""

import json
import sys
from pathlib import Path

try:
    import jsonschema
except ImportError:
    print("ERROR: jsonschema is required. Install with: pip install jsonschema", file=sys.stderr)
    sys.exit(2)

SCHEMA_PATH = Path(__file__).resolve().parent.parent / "schemas" / "pr_trajectory.schema.json"


def load_schema() -> dict:
    if not SCHEMA_PATH.exists():
        print(f"ERROR: Schema not found at {SCHEMA_PATH}", file=sys.stderr)
        sys.exit(2)
    with open(SCHEMA_PATH) as f:
        return json.load(f)


def validate_file(filepath: Path, validator: jsonschema.Draft7Validator) -> list[str]:
    """Validate a single JSONL file. Returns list of error strings."""
    errors: list[str] = []
    try:
        with open(filepath) as f:
            for lineno, line in enumerate(f, start=1):
                line = line.strip()
                if not line:
                    continue
                try:
                    record = json.loads(line)
                except json.JSONDecodeError as exc:
                    errors.append(f"  {filepath.name}:{lineno} - Invalid JSON: {exc}")
                    continue
                for error in sorted(validator.iter_errors(record), key=lambda e: list(e.path)):
                    path = ".".join(str(p) for p in error.absolute_path) or "(root)"
                    errors.append(f"  {filepath.name}:{lineno} [{path}] - {error.message}")
    except FileNotFoundError:
        errors.append(f"  ERROR: File not found: {filepath}")
    return errors


def main() -> int:
    if len(sys.argv) < 2:
        print("Usage: validate_jsonl.py <file1.jsonl> [file2.jsonl ...]", file=sys.stderr)
        return 2

    schema = load_schema()
    validator = jsonschema.Draft7Validator(schema)
    all_errors: list[str] = []

    for arg in sys.argv[1:]:
        filepath = Path(arg)
        file_errors = validate_file(filepath, validator)
        all_errors.extend(file_errors)
        if not file_errors:
            print(f"  ✓ {filepath.name}")
        else:
            print(f"  ✗ {filepath.name} ({len(file_errors)} error(s))")

    if all_errors:
        print("\nValidation FAILED:")
        for err in all_errors:
            print(err)
        return 1

    print("\nAll files passed validation.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
