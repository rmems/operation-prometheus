#!/usr/bin/env python3
"""Validate JSONL trajectory files against schemas.

Usage:
    python scripts/validate_jsonl.py datasets/jsonl/*.jsonl
    python scripts/validate_jsonl.py --strict-policy datasets/jsonl/*.jsonl

Each file is read line-by-line. Each non-empty line must be valid JSON
conforming to the PR Trajectory schema. Exits 0 if all records pass,
non-zero if any validation error is found.
"""

from __future__ import annotations

import argparse
import hashlib
import math
from datetime import datetime, timezone
from urllib.parse import urlparse
import json
import re
import sys
from pathlib import Path

try:
    import jsonschema
except ImportError:
    jsonschema = None
    print(
        "ERROR: jsonschema is required. Install with: pip install jsonschema",
        file=sys.stderr,
    )
    sys.exit(2)

_SCRIPTS = Path(__file__).resolve().parent
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

from lib.ci_contracts import (  # noqa: E402
    blank_license_policy_errors,
    iter_uri_fields,
    private_reference_errors,
    record_identity,
    unique_event_errors,
)
from lib.secrets import find_secrets  # noqa: E402

SCHEMA_V0_PATH = (
    Path(__file__).resolve().parent.parent / "schemas" / "pr_trajectory.schema.json"
)
SCHEMA_V1_PATH = (
    Path(__file__).resolve().parent.parent / "schemas" / "trajectory_v1.schema.json"
)
HOME_PATH_RE = re.compile(
    r"("
    r"/home/[A-Za-z0-9._-]+"
    r"|/Users/[A-Za-z0-9._-]+"
    r"|/root(?:/[^\s\"']+)?"
    r"|(?:[A-Za-z]:\\Users\\|[A-Za-z]:/Users/)[A-Za-z0-9._-]+"
    r")",
    re.IGNORECASE,
)
_GIT_OID_RE = re.compile(r"^[0-9a-fA-F]{3,64}$")
_SNAPSHOT_KEYS = (
    "before_blob",
    "after_blob",
    "base_oid",
    "commit_oid",
    "tree_oid",
    "head_oid",
)
_AUTHORITY_SCHEMES = frozenset({"http", "https", "ftp", "ftps"})


def load_schema(path: Path) -> dict:
    if not path.exists():
        print(f"ERROR: Schema not found at {path}", file=sys.stderr)
        sys.exit(2)
    with open(path) as f:
        return json.load(f)


def _iter_strings(obj: object):
    """Yield raw string keys and values from a nested JSON structure."""
    if isinstance(obj, str):
        yield obj
    elif isinstance(obj, dict):
        for key, value in obj.items():
            if isinstance(key, str):
                yield key
            yield from _iter_strings(value)
    elif isinstance(obj, list):
        for value in obj:
            yield from _iter_strings(value)


def _is_absolute_uri(value: object) -> bool:
    if not isinstance(value, str) or not value:
        return False
    try:
        parsed = urlparse(value)
    except ValueError:
        return False
    if not parsed.scheme:
        return False
    if parsed.scheme.lower() in _AUTHORITY_SCHEMES:
        return bool(parsed.netloc)
    return True


def _is_git_oid(value: object) -> bool:
    return isinstance(value, str) and bool(_GIT_OID_RE.fullmatch(value))


def _code_state_has_git_oid(code_state: object) -> bool:
    if not isinstance(code_state, dict):
        return False
    return any(_is_git_oid(code_state.get(key)) for key in _SNAPSHOT_KEYS)


def _event_has_evidence_url(event: dict) -> bool:
    refs = event.get("evidence_references")
    if not isinstance(refs, list):
        return False
    return any(_is_absolute_uri(ref) for ref in refs)


def _event_has_auditable_anchor(event: dict) -> bool:
    return _event_has_evidence_url(event) or _code_state_has_git_oid(
        event.get("code_state")
    )


def _event_anchor_errors(events: list, filename: str, lineno: int) -> list[str]:
    errors: list[str] = []
    for event in events:
        if isinstance(event, dict) and not _event_has_auditable_anchor(event):
            errors.append(
                _policy(
                    filename,
                    lineno,
                    "event missing auditable evidence anchor "
                    "(evidence_references URL or code_state git object id)",
                )
            )
    return errors


def _contains_nonfinite(obj: object) -> bool:
    if isinstance(obj, float) and not math.isfinite(obj):
        return True
    if isinstance(obj, dict):
        return any(_contains_nonfinite(v) for v in obj.values())
    if isinstance(obj, list):
        return any(_contains_nonfinite(v) for v in obj)
    return False


def _policy(filename: str, lineno: int, message: str) -> str:
    return f"  {filename}:{lineno} [policy] - {message}"


def _parse_utc_timestamp(ts: str) -> datetime:
    iso_ts = ts[:-1] + "+00:00" if ts.endswith(("Z", "z")) else ts
    parsed = datetime.fromisoformat(iso_ts)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _event_timestamp_errors(events: list, filename: str, lineno: int) -> list[str]:
    errors: list[str] = []
    last_dt: datetime | None = None
    for event in events:
        if not isinstance(event, dict):
            continue
        ts = event.get("timestamp")
        if not isinstance(ts, str) or not ts:
            continue
        try:
            current = _parse_utc_timestamp(ts)
        except OverflowError:
            errors.append(
                _policy(filename, lineno, "timestamp UTC normalization overflow")
            )
            continue
        except (ValueError, TypeError):
            errors.append(
                _policy(filename, lineno, "timestamp is not a parseable UTC instant")
            )
            continue
        if last_dt is not None and current < last_dt:
            errors.append(
                _policy(
                    filename,
                    lineno,
                    f"future-event leakage / events not ordered (timestamp {ts} before previous)",
                )
            )
        last_dt = current
    return errors


def _actor_type_errors(events: list, filename: str, lineno: int) -> list[str]:
    allowed = ("human", "bot", "application", "agent")
    errors: list[str] = []
    for event in events:
        actor = event.get("actor") if isinstance(event, dict) else None
        if isinstance(actor, dict) and actor.get("type") not in allowed:
            errors.append(_policy(filename, lineno, "invented/unsupported actor type"))
    return errors


def _software_snapshot_errors(events: list, filename: str, lineno: int) -> list[str]:
    errors: list[str] = []
    has_snapshot = False
    for event in events:
        if not isinstance(event, dict):
            continue
        code_state = event.get("code_state")
        if not isinstance(code_state, dict):
            continue
        for key in _SNAPSHOT_KEYS:
            value = code_state.get(key)
            if not value:
                continue
            if isinstance(value, str) and _GIT_OID_RE.fullmatch(value):
                has_snapshot = True
            else:
                errors.append(
                    _policy(
                        filename, lineno, f"code snapshot {key} is not a git object id"
                    )
                )
    if not has_snapshot:
        errors.append(
            _policy(
                filename,
                lineno,
                "missing required code snapshots for software trajectory",
            )
        )
    return errors


def _last_disposition(events: list):
    for event in reversed(events):
        if isinstance(event, dict) and "disposition" in event:
            return event.get("disposition")
    return None


def _terminal_success(last_disp, outcome: str):
    if last_disp in ("successful", "passed"):
        return True
    if last_disp not in (None, "neutral", "null"):
        return False
    success_outcomes = ("pass", "passed", "success", "successful", "verified", "ok")
    return (outcome in success_outcomes) if outcome else None


def _terminal_disposition_errors(
    record: dict, events: list, filename: str, lineno: int
) -> list[str]:
    disp = record.get("terminal_disposition")
    traj_type = record.get("trajectory_type")
    payload = (
        record.get("software_payload")
        if traj_type == "software"
        else record.get("research_payload")
    )
    last_disp = _last_disposition(events)
    outcome = ""
    if isinstance(payload, dict):
        outcome = str(payload.get("validation_outcome", "")).strip().lower()
    terminal_success = _terminal_success(last_disp, outcome)
    terminal_enum = {
        "successful",
        "failed",
        "reverted",
        "falsified",
        "null",
        "invalid",
        "interrupted",
        "inconclusive",
    }
    disagree = "terminal_disposition does not agree with terminal outcome evidence"
    if disp == "successful" and terminal_success is False:
        return [
            _policy(
                filename,
                lineno,
                "nonterminal record incorrectly represented as positive terminal example",
            )
        ]
    if disp not in (None, "successful") and terminal_success is True:
        return [_policy(filename, lineno, disagree)]
    if (
        isinstance(last_disp, str)
        and last_disp not in ("neutral", "null")
        and disp in terminal_enum
    ):
        normalized_last = "successful" if last_disp == "passed" else last_disp
        if normalized_last in terminal_enum and normalized_last != disp:
            return [_policy(filename, lineno, disagree)]
    return []


def _one_artifact_errors(art: dict, filename: str, lineno: int) -> list[str]:
    errors: list[str] = []
    availability = art.get("availability")
    content = art.get("content")
    label = "inline artifact" if availability == "inline" else "artifact"
    if availability == "inline" and not isinstance(content, str):
        return [_policy(filename, lineno, "inline artifact missing content")]
    if availability == "remote" and not _is_absolute_uri(art.get("uri")):
        errors.append(
            _policy(filename, lineno, "remote artifact uri is not an absolute URI")
        )
    if not isinstance(content, str):
        return errors
    try:
        raw = content.encode("utf-8")
    except UnicodeEncodeError:
        return [_policy(filename, lineno, f"{label} content is not UTF-8 encodable")]
    digest = hashlib.sha256(raw).hexdigest()
    declared = str(art.get("sha256") or "").strip().lower()
    if declared != digest:
        errors.append(
            _policy(filename, lineno, f"{label} sha256 does not match content")
        )
    if art.get("byte_size") != len(raw):
        errors.append(
            _policy(filename, lineno, f"{label} byte_size does not match content")
        )
    return errors


def _artifact_policy_errors(record: dict, filename: str, lineno: int) -> list[str]:
    artifacts = record.get("artifacts")
    if not isinstance(artifacts, list):
        return []
    errors: list[str] = []
    for art in artifacts:
        if isinstance(art, dict):
            errors.extend(_one_artifact_errors(art, filename, lineno))
    return errors


def _v1_policy_errors(record: dict, filename: str, lineno: int) -> list[str]:
    events = record.get("events")
    if not isinstance(events, list):
        events = []
    errors = [
        *_event_timestamp_errors(events, filename, lineno),
        *_actor_type_errors(events, filename, lineno),
        *_event_anchor_errors(events, filename, lineno),
    ]
    if record.get("trajectory_type") == "software" and isinstance(
        record.get("events"), list
    ):
        errors.extend(_software_snapshot_errors(events, filename, lineno))
    errors.extend(_terminal_disposition_errors(record, events, filename, lineno))
    errors.extend(_artifact_policy_errors(record, filename, lineno))
    return errors


def _canonical_url_errors(record: dict, filename: str, lineno: int) -> list[str]:
    repo = record.get("repo")
    pr = record.get("pr_number")
    urls = record.get("source_urls") or []
    if not (repo and pr):
        return []
    canonical = f"https://github.com/{repo}/pull/{pr}"
    if canonical in urls:
        return []
    return [
        f"  {filename}:{lineno} [source_urls] - missing canonical PR URL {canonical}"
    ]


def _home_secret_errors(record: dict, filename: str, lineno: int) -> list[str]:
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
    errors: list[str] = []
    if home_hit:
        errors.append(
            _policy(
                filename,
                lineno,
                "absolute user-home path present (/home, /Users, /root, or Windows Users)",
            )
        )
    if secret_families:
        errors.append(
            _policy(
                filename,
                lineno,
                f"secret-like token pattern present ({', '.join(secret_families)})",
            )
        )
    return errors


def policy_errors(record: dict, lineno: int, filename: str) -> list[str]:
    """Extra policy checks beyond JSON Schema."""
    if not isinstance(record, dict):
        return []
    errors: list[str] = []
    if record.get("schema_version") in ("1", "1.0", "v1"):
        errors.extend(_v1_policy_errors(record, filename, lineno))
    errors.extend(_canonical_url_errors(record, filename, lineno))
    errors.extend(_home_secret_errors(record, filename, lineno))
    return errors


def contract_policy_errors(record: dict, lineno: int, filename: str) -> list[str]:
    errors: list[str] = []
    private_hits: list[str] = []
    seen_private: set[str] = set()
    for text in iter_uri_fields(record):
        for hit in private_reference_errors(text):
            if hit not in seen_private:
                seen_private.add(hit)
                private_hits.append(hit)
    if private_hits:
        errors.append(
            f"  {filename}:{lineno} [policy] - private reference present "
            f"({', '.join(private_hits)})"
        )
    for message in unique_event_errors(record):
        errors.append(f"  {filename}:{lineno} [policy] - {message}")
    for message in blank_license_policy_errors(record):
        errors.append(f"  {filename}:{lineno} [policy] - {message}")
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
    seen_ids: dict[str, int] = {}
    try:
        with open(filepath) as f:
            for lineno, line in enumerate(f, start=1):
                line = line.strip()
                if not line:
                    continue
                count += 1
                try:

                    def _reject_nonfinite(constant: str):
                        raise json.JSONDecodeError(
                            f"non-finite constant {constant!r}", line, 0
                        )

                    record = json.loads(line, parse_constant=_reject_nonfinite)
                except json.JSONDecodeError as exc:
                    errors.append(f"  {filepath.name}:{lineno} - Invalid JSON: {exc}")
                    continue
                if _contains_nonfinite(record):
                    errors.append(
                        f"  {filepath.name}:{lineno} - Invalid JSON: non-finite number"
                    )
                    continue

                if isinstance(record, dict):
                    version = record.get("schema_version")
                    validator = (
                        v1_validator if version in ("1", "1.0", "v1") else v0_validator
                    )
                else:
                    validator = v0_validator

                for error in sorted(
                    validator.iter_errors(record), key=lambda e: list(e.path)
                ):
                    path = ".".join(str(p) for p in error.absolute_path) or "(root)"
                    errors.append(
                        f"  {filepath.name}:{lineno} [{path}] - {error.message}"
                    )
                if strict_policy and isinstance(record, dict):
                    errors.extend(policy_errors(record, lineno, filepath.name))
                    errors.extend(contract_policy_errors(record, lineno, filepath.name))
                    identity = record_identity(record)
                    if identity:
                        previous = seen_ids.get(identity)
                        if previous is not None:
                            errors.append(
                                f"  {filepath.name}:{lineno} [policy] - duplicate trajectory id "
                                f"{identity} (first seen on line {previous})"
                            )
                        else:
                            seen_ids[identity] = lineno
                    elif (
                        record.get("schema_version") in ("1", "1.0", "v1")
                        or record.get("id") is not None
                    ):
                        errors.append(
                            f"  {filepath.name}:{lineno} [policy] - trajectory/event record is missing a stable id"
                        )
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
    v0_validator = jsonschema.Draft7Validator(
        schema_v0, format_checker=jsonschema.Draft7Validator.FORMAT_CHECKER
    )

    schema_v1 = load_schema(SCHEMA_V1_PATH)
    v1_validator = jsonschema.Draft7Validator(
        schema_v1, format_checker=jsonschema.Draft7Validator.FORMAT_CHECKER
    )

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
