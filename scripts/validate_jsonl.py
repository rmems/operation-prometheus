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
from dataclasses import dataclass
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
from lib.hermes_sanitize import (  # noqa: E402
    hidden_markup_remains,
    is_hidden_key,
    strip_hidden_reasoning,
)
from lib.secrets import find_secrets  # noqa: E402

SCHEMA_V0_PATH = (
    Path(__file__).resolve().parent.parent / "schemas" / "pr_trajectory.schema.json"
)
SCHEMA_V1_PATH = (
    Path(__file__).resolve().parent.parent / "schemas" / "trajectory_v1.schema.json"
)
SCHEMA_V1_1_PATH = (
    Path(__file__).resolve().parent.parent / "schemas" / "trajectory_v1_1.schema.json"
)
_V1_VERSIONS = frozenset({"1", "1.0", "v1"})
_V1_1_VERSIONS = frozenset({"1.1", "v1.1"})
_SUCCESS_OUTCOMES = frozenset(
    {"pass", "passed", "success", "successful", "verified", "ok"}
)
_TERMINAL_DISPOSITIONS = frozenset(
    {
        "successful",
        "failed",
        "reverted",
        "falsified",
        "null",
        "invalid",
        "interrupted",
        "inconclusive",
    }
)


@dataclass(frozen=True)
class _LineValidationContext:
    filename: str
    validators: tuple[
        jsonschema.Draft7Validator,
        jsonschema.Draft7Validator,
        jsonschema.Draft7Validator | None,
    ]
    strict_policy: bool
    seen_ids: dict[str, int]


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


def _contains_nonfinite(obj: object) -> bool:
    if isinstance(obj, float) and not math.isfinite(obj):
        return True
    if isinstance(obj, dict):
        return any(_contains_nonfinite(v) for v in obj.values())
    if isinstance(obj, list):
        return any(_contains_nonfinite(v) for v in obj)
    return False


def _contains_hidden_reasoning(obj: object) -> bool:
    if isinstance(obj, str):
        return hidden_markup_remains(obj) or strip_hidden_reasoning(obj) != obj
    if isinstance(obj, dict):
        return any(
            is_hidden_key(key) or _contains_hidden_reasoning(value)
            for key, value in obj.items()
        )
    if isinstance(obj, list):
        return any(_contains_hidden_reasoning(value) for value in obj)
    return False


def policy_errors(record: dict, lineno: int, filename: str) -> list[str]:
    """Extra policy checks beyond JSON Schema."""
    if not isinstance(record, dict):
        return []
    location = f"  {filename}:{lineno}"
    schema_version = record.get("schema_version")
    errors = _versioned_policy_errors(record, schema_version, location)
    errors.extend(_canonical_source_errors(record, location))
    errors.extend(_sensitive_data_errors(record, location))
    return errors


def _versioned_policy_errors(
    record: dict, schema_version: object, location: str
) -> list[str]:
    errors: list[str] = []
    if schema_version in _V1_1_VERSIONS and _contains_hidden_reasoning(record):
        errors.append(f"{location} [policy] - hidden reasoning is not allowed in v1.1")
    if schema_version not in _V1_VERSIONS and schema_version not in _V1_1_VERSIONS:
        return errors
    events = record.get("events")
    errors.extend(_event_errors(events, location))
    errors.extend(_snapshot_errors(record, events, location))
    errors.extend(_terminal_errors(record, events, location))
    errors.extend(_artifact_errors(record.get("artifacts"), location))
    return errors


def _event_errors(events: object, location: str) -> list[str]:
    if not isinstance(events, list):
        return []
    errors: list[str] = []
    last_dt: datetime | None = None
    for event in (item for item in events if isinstance(item, dict)):
        timestamp_errors, current_dt = _timestamp_errors(
            event.get("timestamp"), last_dt, location
        )
        errors.extend(timestamp_errors)
        last_dt = current_dt or last_dt
        actor = event.get("actor")
        if isinstance(actor, dict) and actor.get("type") not in (
            "human",
            "bot",
            "application",
            "agent",
        ):
            errors.append(f"{location} [policy] - invented/unsupported actor type")
        if not _event_has_auditable_anchor(event):
            errors.append(
                f"{location} [policy] - event missing auditable evidence anchor "
                "(evidence_references URL or code_state git object id)"
            )
    return errors


def _timestamp_errors(
    timestamp: object, previous: datetime | None, location: str
) -> tuple[list[str], datetime | None]:
    if not isinstance(timestamp, str) or not timestamp:
        return [], None
    try:
        iso_timestamp = (
            timestamp[:-1] + "+00:00" if timestamp.endswith(("Z", "z")) else timestamp
        )
        current = datetime.fromisoformat(iso_timestamp)
        current = (
            current.replace(tzinfo=timezone.utc)
            if current.tzinfo is None
            else current.astimezone(timezone.utc)
        )
    except OverflowError:
        return [f"{location} [policy] - timestamp UTC normalization overflow"], None
    except (ValueError, TypeError):
        return [f"{location} [policy] - timestamp is not a parseable UTC instant"], None
    if previous is not None and current < previous:
        return [
            f"{location} [policy] - future-event leakage / events not ordered "
            f"(timestamp {timestamp} before previous)"
        ], current
    return [], current


def _snapshot_errors(record: dict, events: object, location: str) -> list[str]:
    if record.get("trajectory_type") != "software" or not isinstance(events, list):
        return []
    errors: list[str] = []
    has_snapshot = False
    for event in (item for item in events if isinstance(item, dict)):
        code_state = event.get("code_state")
        if not isinstance(code_state, dict):
            continue
        for key in _SNAPSHOT_KEYS:
            value = code_state.get(key)
            if not value:
                continue
            if _is_git_oid(value):
                has_snapshot = True
            else:
                errors.append(
                    f"{location} [policy] - code snapshot {key} is not a git object id"
                )
    if not has_snapshot:
        errors.append(
            f"{location} [policy] - missing required code snapshots for software trajectory"
        )
    return errors


def _terminal_errors(record: dict, events: object, location: str) -> list[str]:
    disposition = record.get("terminal_disposition")
    last_disposition = _last_disposition(events)
    terminal_success = _terminal_success(last_disposition, _validation_outcome(record))
    if disposition == "successful" and terminal_success is False:
        return [
            f"{location} [policy] - nonterminal record incorrectly represented as positive terminal example"
        ]
    if disposition not in (None, "successful") and terminal_success is True:
        return [
            f"{location} [policy] - terminal_disposition does not agree with terminal outcome evidence"
        ]
    normalized_last = "successful" if last_disposition == "passed" else last_disposition
    if _terminal_dispositions_conflict(disposition, normalized_last):
        return [
            f"{location} [policy] - terminal_disposition does not agree with terminal outcome evidence"
        ]
    return []


def _validation_outcome(record: dict) -> str:
    payload_name = (
        "software_payload"
        if record.get("trajectory_type") == "software"
        else "research_payload"
    )
    payload = record.get(payload_name)
    if not isinstance(payload, dict):
        return ""
    return str(payload.get("validation_outcome", "")).strip().lower()


def _terminal_success(last_disposition: object, outcome: str) -> bool | None:
    if last_disposition in ("successful", "passed"):
        return True
    if last_disposition not in (None, "neutral", "null"):
        return False
    return outcome in _SUCCESS_OUTCOMES if outcome else None


def _terminal_dispositions_conflict(
    disposition: object, normalized_last: object
) -> bool:
    if normalized_last in (None, "neutral", "null"):
        return False
    if disposition not in _TERMINAL_DISPOSITIONS:
        return False
    return normalized_last in _TERMINAL_DISPOSITIONS and normalized_last != disposition


def _last_disposition(events: object) -> object:
    if not isinstance(events, list):
        return None
    for event in reversed(events):
        if isinstance(event, dict) and "disposition" in event:
            return event.get("disposition")
    return None


def _artifact_errors(artifacts: object, location: str) -> list[str]:
    if not isinstance(artifacts, list):
        return []
    errors: list[str] = []
    for artifact in (item for item in artifacts if isinstance(item, dict)):
        errors.extend(_single_artifact_errors(artifact, location))
    return errors


def _single_artifact_errors(artifact: dict, location: str) -> list[str]:
    availability = artifact.get("availability")
    content = artifact.get("content")
    if availability == "inline" and not isinstance(content, str):
        return [f"{location} [policy] - inline artifact missing content"]
    errors: list[str] = []
    if availability == "remote" and not _is_absolute_uri(artifact.get("uri")):
        errors.append(
            f"{location} [policy] - remote artifact uri is not an absolute URI"
        )
    if not isinstance(content, str):
        return errors
    label = "inline artifact" if availability == "inline" else "artifact"
    try:
        raw = content.encode("utf-8")
    except UnicodeEncodeError:
        errors.append(f"{location} [policy] - {label} content is not UTF-8 encodable")
        return errors
    if (
        str(artifact.get("sha256") or "").strip().lower()
        != hashlib.sha256(raw).hexdigest()
    ):
        errors.append(f"{location} [policy] - {label} sha256 does not match content")
    if artifact.get("byte_size") != len(raw):
        errors.append(f"{location} [policy] - {label} byte_size does not match content")
    return errors


def _canonical_source_errors(record: dict, location: str) -> list[str]:
    repo = record.get("repo")
    pr = record.get("pr_number")
    urls = record.get("source_urls") or []
    if repo and pr:
        canonical = f"https://github.com/{repo}/pull/{pr}"
        if canonical not in urls:
            return [f"{location} [source_urls] - missing canonical PR URL {canonical}"]
    return []


def _sensitive_data_errors(record: dict, location: str) -> list[str]:
    # Scan raw strings so Windows paths (C:\\Users\\...) are not missed via json.dumps escapes.
    errors: list[str] = []
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
            f"{location} [policy] - absolute user-home path present "
            f"(/home, /Users, /root, or Windows Users)"
        )
    if secret_families:
        families = ", ".join(secret_families)
        errors.append(
            f"{location} [policy] - secret-like token pattern present ({families})"
        )
    return errors


def _select_validator(
    record: object,
    v0_validator: jsonschema.Draft7Validator,
    v1_validator: jsonschema.Draft7Validator,
    v1_1_validator: jsonschema.Draft7Validator | None,
) -> jsonschema.Draft7Validator:
    if not isinstance(record, dict):
        return v0_validator
    version = record.get("schema_version")
    if version in _V1_1_VERSIONS:
        if v1_1_validator is None:
            v1_1_validator = jsonschema.Draft7Validator(
                load_schema(SCHEMA_V1_1_PATH),
                format_checker=jsonschema.Draft7Validator.FORMAT_CHECKER,
            )
        return v1_1_validator
    if version in _V1_VERSIONS:
        return v1_validator
    return v0_validator


def validate_file(
    filepath: Path,
    *validators: jsonschema.Draft7Validator,
    strict_policy: bool = False,
    v1_1_validator: jsonschema.Draft7Validator | None = None,
) -> list[str]:
    """Validate a single JSONL file. Returns list of error strings."""
    if len(validators) != 2:
        raise TypeError("validate_file requires v0 and v1 validators")
    v0_validator, v1_validator = validators
    context = _LineValidationContext(
        filename=filepath.name,
        validators=(v0_validator, v1_validator, v1_1_validator),
        strict_policy=strict_policy,
        seen_ids={},
    )
    errors: list[str] = []
    count = 0
    try:
        with open(filepath) as f:
            for lineno, line in enumerate(f, start=1):
                line = line.strip()
                if not line:
                    continue
                count += 1
                errors.extend(_line_errors(line, lineno, context))
    except FileNotFoundError:
        errors.append(f"  ERROR: File not found: {filepath}")
        return errors
    if count == 0:
        errors.append(f"  {filepath.name} - no non-empty JSONL records")
    return errors


def _line_errors(
    line: str,
    lineno: int,
    context: _LineValidationContext,
) -> list[str]:
    try:

        def _reject_nonfinite(constant: str):
            raise json.JSONDecodeError(f"non-finite constant {constant!r}", line, 0)

        record = json.loads(line, parse_constant=_reject_nonfinite)
    except json.JSONDecodeError as exc:
        return [f"  {context.filename}:{lineno} - Invalid JSON: {exc}"]
    if _contains_nonfinite(record):
        return [f"  {context.filename}:{lineno} - Invalid JSON: non-finite number"]
    v0_validator, v1_validator, v1_1_validator = context.validators
    validator = _select_validator(record, v0_validator, v1_validator, v1_1_validator)
    errors = _jsonschema_errors(record, validator, lineno, context.filename)
    if context.strict_policy and isinstance(record, dict):
        errors.extend(policy_errors(record, lineno, context.filename))
        errors.extend(contract_policy_errors(record, lineno, context.filename))
        errors.extend(_identity_errors(record, lineno, context))
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


def _identity_errors(
    record: dict, lineno: int, context: _LineValidationContext
) -> list[str]:
    identity = record_identity(record)
    if identity:
        previous = context.seen_ids.get(identity)
        if previous is not None:
            return [
                f"  {context.filename}:{lineno} [policy] - duplicate trajectory id "
                f"{identity} (first seen on line {previous})"
            ]
        context.seen_ids[identity] = lineno
        return []
    version = record.get("schema_version")
    if (
        version in _V1_VERSIONS
        or version in _V1_1_VERSIONS
        or record.get("id") is not None
    ):
        return [
            f"  {context.filename}:{lineno} [policy] - "
            "trajectory/event record is missing a stable id"
        ]
    return []


def _jsonschema_errors(
    record: object,
    validator: jsonschema.Draft7Validator,
    lineno: int,
    filename: str,
) -> list[str]:
    errors: list[str] = []
    for error in sorted(
        validator.iter_errors(record), key=lambda item: list(item.path)
    ):
        path = ".".join(str(part) for part in error.absolute_path) or "(root)"
        errors.append(f"  {filename}:{lineno} [{path}] - {error.message}")
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
    v1_1_validator = None
    if SCHEMA_V1_1_PATH.exists():
        v1_1_validator = jsonschema.Draft7Validator(
            load_schema(SCHEMA_V1_1_PATH),
            format_checker=jsonschema.Draft7Validator.FORMAT_CHECKER,
        )

    all_errors: list[str] = []

    for arg in args.files:
        filepath = Path(arg)
        file_errors = validate_file(
            filepath,
            v0_validator,
            v1_validator,
            strict_policy=args.strict_policy,
            v1_1_validator=v1_1_validator,
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
