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

_SCRIPTS = Path(__file__).resolve().parent
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

from lib.secrets import find_secrets  # noqa: E402

SCHEMA_V0_PATH = Path(__file__).resolve().parent.parent / "schemas" / "pr_trajectory.schema.json"
SCHEMA_V1_PATH = Path(__file__).resolve().parent.parent / "schemas" / "trajectory_v1.schema.json"
HOME_PATH_RE = re.compile(
    r"(?:"
    r"/home/[A-Za-z0-9._-]+"
    r"|/Users/[A-Za-z0-9._-]+"
    r"|/root(?:/[^\s\"']+)?"
    r"|(?:[A-Za-z]:\\Users\\|[A-Za-z]:/Users/)[A-Za-z0-9._-]+"
    r")",
    re.IGNORECASE,
)


def load_schema(path: Path) -> dict:
    if not path.exists():
        print(f"ERROR: Schema not found at {path}", file=sys.stderr)
        sys.exit(2)
    with open(path) as f:
        return json.load(f)


def _iter_strings(obj: object):
    """Yield raw string values from a nested JSON structure (pre-serialization)."""
    if isinstance(obj, str):
        yield obj
    elif isinstance(obj, dict):
        for value in obj.values():
            yield from _iter_strings(value)
    elif isinstance(obj, list):
        for value in obj:
            yield from _iter_strings(value)


def policy_errors(record: dict, lineno: int, filename: str) -> list[str]:
    """Extra policy checks beyond JSON Schema."""
    errors: list[str] = []
    
    schema_version = record.get("schema_version")
    if schema_version in ("1", "1.0", "v1"):
        events = record.get("events", [])
        last_ts = ""
        for e in events:
            ts = e.get("timestamp", "")
            if ts:
                if last_ts and ts < last_ts:
                    errors.append(f"  {filename}:{lineno} [policy] - future-event leakage / events not ordered (timestamp {ts} before {last_ts})")
                last_ts = ts
                
        traj_type = record.get("trajectory_type")
        if traj_type == "software":
            has_snapshot = False
            for e in events:
                if e.get("code_state", {}).get("before_blob") or e.get("code_state", {}).get("base_oid"):
                    has_snapshot = True
                    break
            if not has_snapshot:
                errors.append(f"  {filename}:{lineno} [policy] - missing required code snapshots for software trajectory")

        disp = record.get("terminal_disposition")
        if disp == "successful":
            payload = record.get("software_payload") or record.get("research_payload") or {}
            has_success_event = any(e.get("disposition") == "successful" for e in events)
            if not has_success_event and "successful" not in str(payload):
                 errors.append(f"  {filename}:{lineno} [policy] - nonterminal record incorrectly represented as positive terminal example")
                 
        for e in events:
            actor = e.get("actor", {})
            if actor.get("type") not in ("human", "bot", "application", "agent"):
                 errors.append(f"  {filename}:{lineno} [policy] - invented/unsupported actor type")

    repo = record.get("repo")
    pr = record.get("pr_number")
    urls = record.get("source_urls") or []
    if repo and pr:
        canonical = f"https://github.com/{repo}/pull/{pr}"
        if canonical not in urls:
            errors.append(
                f"  {filename}:{lineno} [source_urls] - missing canonical PR URL {canonical}"
            )
    # Scan raw strings so Windows paths (C:\\Users\\...) are not missed via json.dumps escapes.
    home_hit = False
    secret_families: list[str] = []
    seen_families: set[str] = set()
    for text in _iter_strings(record):
        if not home_hit and HOME_PATH_RE.search(text):
            home_hit = True
        for family in find_secrets(text):
            if family not in seen_families:
                seen_families.add(family)
                secret_families.append(family)
    if home_hit:
        errors.append(
            f"  {filename}:{lineno} [policy] - absolute user-home path present "
            f"(/home, /Users, /root, or Windows Users)"
        )
    if secret_families:
        families = ", ".join(secret_families)
        errors.append(
            f"  {filename}:{lineno} [policy] - secret-like token pattern present "
            f"({families})"
        )
    return errors


def validate_file(
    filepath: Path,
    v0_validator: jsonschema.Draft7Validator,
    v1_validator: jsonschema.Draft7Validator,
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
                
                version = record.get("schema_version")
                validator = v1_validator if version in ("1", "1.0", "v1") else v0_validator

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

    schema_v0 = load_schema(SCHEMA_V0_PATH)
    v0_validator = jsonschema.Draft7Validator(schema_v0)
    
    schema_v1 = load_schema(SCHEMA_V1_PATH)
    v1_validator = jsonschema.Draft7Validator(schema_v1)
    
    all_errors: list[str] = []

    for arg in args.files:
        filepath = Path(arg)
        file_errors = validate_file(
            filepath, v0_validator, v1_validator, strict_policy=args.strict_policy
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
