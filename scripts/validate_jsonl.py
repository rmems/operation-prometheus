#!/usr/bin/env python3
"""Validate JSONL trajectory files against pr_trajectory.schema.json.

Usage:
    python scripts/validate_jsonl.py datasets/jsonl/*.jsonl
    python scripts/validate_jsonl.py --strict-policy datasets/jsonl/*.jsonl

Each file is read line-by-line. Each non-empty line must be valid JSON
conforming to the PR Trajectory schema. Exits 0 if all records pass,
non-zero if any validation error is found.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

try:
    import jsonschema
except ImportError:
    print("ERROR: jsonschema is required. Install with: pip install jsonschema", file=sys.stderr)
    sys.exit(2)

SCHEMA_PATH = Path(__file__).resolve().parent.parent / "schemas" / "pr_trajectory.schema.json"
HOME_PATH_RE = re.compile(r"/home/[A-Za-z0-9._-]+")
SECRET_HINT_RE = re.compile(r"\b(ghp_|gho_|github_pat_|sk-|AKIA)[A-Za-z0-9_]*")


def load_schema() -> dict:
    if not SCHEMA_PATH.exists():
        print(f"ERROR: Schema not found at {SCHEMA_PATH}", file=sys.stderr)
        sys.exit(2)
    with open(SCHEMA_PATH) as f:
        return json.load(f)


def policy_errors(record: dict, lineno: int, filename: str) -> list[str]:
    """Extra policy checks beyond JSON Schema."""
    errors: list[str] = []
    repo = record.get("repo")
    pr = record.get("pr_number")
    urls = record.get("source_urls") or []
    if repo and pr:
        canonical = f"https://github.com/{repo}/pull/{pr}"
        if canonical not in urls:
            errors.append(
                f"  {filename}:{lineno} [source_urls] - missing canonical PR URL {canonical}"
            )
    blob = json.dumps(record, ensure_ascii=False)
    if HOME_PATH_RE.search(blob):
        errors.append(
            f"  {filename}:{lineno} [policy] - absolute /home/ path present (data-policy hygiene)"
        )
    if SECRET_HINT_RE.search(blob):
        errors.append(
            f"  {filename}:{lineno} [policy] - secret-like token pattern present"
        )
    return errors


def validate_file(
    filepath: Path,
    validator: jsonschema.Draft7Validator,
    *,
    strict_policy: bool = False,
) -> list[str]:
    """Validate a single JSONL file. Returns list of error strings."""
    errors: list[str] = []
    count = 0
    try:
        with open(filepath) as f:
            for lineno, line in enumerate(f, start=1):
                line = line.strip()
                if not line:
                    continue
                count += 1
                try:
                    record = json.loads(line)
                except json.JSONDecodeError as exc:
                    errors.append(f"  {filepath.name}:{lineno} - Invalid JSON: {exc}")
                    continue
                for error in sorted(validator.iter_errors(record), key=lambda e: list(e.path)):
                    path = ".".join(str(p) for p in error.absolute_path) or "(root)"
                    errors.append(f"  {filepath.name}:{lineno} [{path}] - {error.message}")
                if strict_policy and isinstance(record, dict):
                    errors.extend(policy_errors(record, lineno, filepath.name))
    except FileNotFoundError:
        errors.append(f"  ERROR: File not found: {filepath}")
        return errors
    if count == 0:
        errors.append(f"  {filepath.name} - no non-empty JSONL records")
    return errors


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("files", nargs="+", help="JSONL files to validate")
    parser.add_argument(
        "--strict-policy",
        action="store_true",
        help="Also enforce data-policy hygiene (canonical URL, no /home/ paths, no secret hints)",
    )
    args = parser.parse_args(argv)

    schema = load_schema()
    validator = jsonschema.Draft7Validator(schema)
    all_errors: list[str] = []

    for arg in args.files:
        filepath = Path(arg)
        file_errors = validate_file(
            filepath, validator, strict_policy=args.strict_policy
        )
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
