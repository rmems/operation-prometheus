"""Shared helpers for trajectory, corpus, consumer, and release CI contracts."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from .eligibility_common import LEDGER_STATES

ROOT = Path(__file__).resolve().parent.parent.parent
INVENTORY_DIR = ROOT / "datasets" / "inventory" / "v0.7"
JSONL_DIR = ROOT / "datasets" / "jsonl"
MANIFEST_DIR = ROOT / "datasets" / "manifests"
PARQUET_DIR = ROOT / "datasets" / "parquet"
RELEASE_MANIFEST = ROOT / "datasets" / "release" / "manifest.json"

SHA256_RE = re.compile(r"^[a-f0-9]{64}$")
CHECKLIST_RE = re.compile(r"^\s*[-*]\s+\[[ xX]\]", re.MULTILINE)
CHECK_RUN_CONCLUSION_RE = re.compile(
    r"(?:=(?:success|failure|cancelled|neutral|skipped|pending|timed_out|action_required)\b)"
    r"|(?:combined_status=)",
    re.IGNORECASE,
)
DECLARED_TRUNCATION_MARKERS = (
    "# … truncated …",
    "# Truncated unified diff",
    "patch unavailable / truncated",
    "# omitted:",
)
PRIVATE_HOST_RE = re.compile(
    r"(?i)^(localhost|127\.0\.0\.1|10\.\d+\.\d+\.\d+|192\.168\.\d+\.\d+"
    r"|172\.(?:1[6-9]|2[0-9]|3[0-1])\.\d+\.\d+|.*\.(?:internal|lan))$"
)
POSITIVE_RELEASE_STATES = frozenset({"included_positive"})
MUTABLE_STATES = frozenset({"watchlist_open"})
MUTABLE_SOURCE_STATES = frozenset({"open"})


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_jsonl(path: Path) -> list[tuple[int, dict[str, Any]]]:
    rows: list[tuple[int, dict[str, Any]]] = []
    with path.open(encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            record = json.loads(line)
            if isinstance(record, dict):
                rows.append((line_number, record))
    return rows


def record_identity(record: dict[str, Any]) -> str | None:
    if record.get("schema_version") in ("1", "1.0", "v1"):
        value = record.get("trajectory_id")
    else:
        value = record.get("id")
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def iter_uri_fields(record: dict[str, Any]) -> list[str]:
    """Yield sourced URI strings, excluding patch bodies and review prose."""
    values: list[str] = []
    for key in ("source_urls", "evidence_references"):
        field = record.get(key)
        if isinstance(field, list):
            values.extend(item for item in field if isinstance(item, str))
        elif isinstance(field, str):
            values.append(field)
    for key in ("url", "uri", "html_url"):
        field = record.get(key)
        if isinstance(field, str):
            values.append(field)
    for artifact in record.get("artifacts") or []:
        if isinstance(artifact, dict) and isinstance(artifact.get("uri"), str):
            values.append(artifact["uri"])
    for event in record.get("events") or []:
        if not isinstance(event, dict):
            continue
        refs = event.get("evidence_references")
        if isinstance(refs, list):
            values.extend(item for item in refs if isinstance(item, str))
    return values


def private_reference_errors(text: str) -> list[str]:
    """Return policy hits for URI-like private or non-public references."""
    errors: list[str] = []
    for match in re.finditer(
        r"\b(?:[a-z][a-z0-9+.-]*:|/+)[^\s\"'<>]+", text, re.IGNORECASE
    ):
        token = match.group(0)
        try:
            parsed = urlparse(token)
        except ValueError:
            continue
        scheme = (parsed.scheme or "").casefold()
        if scheme == "file":
            errors.append("private file URI")
            continue
        if scheme in {"ssh", "git"}:
            errors.append("private or ssh git URI")
            continue
        host = (parsed.hostname or "").casefold()
        if host and PRIVATE_HOST_RE.fullmatch(host):
            errors.append(f"private host {host}")
    if re.search(r"(?i)\bgit@[^\s:]+:", text):
        errors.append("ssh git@ remote")
    return errors


def unique_event_errors(record: dict[str, Any]) -> list[str]:
    events = record.get("events")
    if not isinstance(events, list):
        return []
    seen: set[str] = set()
    errors: list[str] = []
    for event in events:
        if not isinstance(event, dict):
            continue
        event_id = event.get("event_id")
        if not isinstance(event_id, str) or not event_id.strip():
            errors.append("event is missing a sourced event_id")
            continue
        if event_id in seen:
            errors.append(f"duplicate event_id {event_id}")
        seen.add(event_id)
        actor = event.get("actor")
        if isinstance(actor, dict):
            actor_id = actor.get("id")
            if not isinstance(actor_id, str) or not actor_id.strip():
                errors.append("actor attribution is missing a sourced id")
    artifacts = record.get("artifacts")
    if isinstance(artifacts, list):
        artifact_ids: set[str] = set()
        for artifact in artifacts:
            if not isinstance(artifact, dict):
                continue
            artifact_id = artifact.get("id")
            if isinstance(artifact_id, str) and artifact_id:
                if artifact_id in artifact_ids:
                    errors.append(f"duplicate artifact id {artifact_id}")
                artifact_ids.add(artifact_id)
            digest = artifact.get("sha256")
            if digest is not None and not (
                isinstance(digest, str) and SHA256_RE.fullmatch(digest)
            ):
                errors.append("artifact sha256 is not a 64-char hex digest")
    return errors


def blank_license_policy_errors(record: dict[str, Any]) -> list[str]:
    if record.get("schema_version") not in ("1", "1.0", "v1"):
        return []
    errors: list[str] = []
    for field in ("license", "collection_policy"):
        value = record.get(field)
        if not isinstance(value, str) or not value.strip():
            errors.append(f"{field} is missing a sourced value")
    return errors


def is_real_check_run_detail(detail: str) -> bool:
    """True when a validation detail is a Checks API conclusion, not a PR checklist."""
    if CHECKLIST_RE.search(detail):
        return False
    return bool(CHECK_RUN_CONCLUSION_RE.search(detail))


def validation_evidence_errors(record: dict[str, Any]) -> list[str]:
    events = record.get("validation")
    if not isinstance(events, list) or not events:
        if record.get("schema_version") in ("1", "1.0", "v1"):
            return []
        return ["missing required validation evidence"]
    errors: list[str] = []
    ci_events = [
        event
        for event in events
        if isinstance(event, dict) and event.get("type") == "ci"
    ]
    for event in ci_events:
        detail = str(event.get("detail") or "")
        if CHECKLIST_RE.search(detail) and not is_real_check_run_detail(detail):
            errors.append(
                "CI evidence is a PR-body checklist rather than a check-run conclusion"
            )
        elif (
            detail.strip()
            and not is_real_check_run_detail(detail)
            and not detail.startswith("review_apps")
        ):
            # Prose-only CI details are allowed only when no checklist is pretending to be a gate.
            if (
                "passing locally" in detail.casefold()
                or "test plan" in detail.casefold()
            ):
                errors.append("CI evidence is prose rather than a check-run conclusion")
    return errors


def silent_truncation_errors(record: dict[str, Any]) -> list[str]:
    patch = record.get("patch")
    if not isinstance(patch, str) or not patch:
        return []
    declared = any(marker in patch for marker in DECLARED_TRUNCATION_MARKERS)
    encoded = patch.encode("utf-8")
    if len(encoded) >= 96 * 1024 and not declared:
        return [
            "silent patch truncation: patch meets the 96KiB budget without a truncation marker"
        ]
    if "# omitted:" in patch:
        for line in patch.splitlines():
            if (
                line.startswith("# omitted:")
                and "truncated" not in line.casefold()
                and "unavailable" not in line.casefold()
            ):
                return [
                    "silent patch truncation: omitted file lacks a truncation reason"
                ]
    return []


def load_inventory_candidates(inventory_dir: Path) -> list[dict[str, Any]]:
    return [row for _, row in load_jsonl(inventory_dir / "candidates.jsonl")]


def load_inventory_repositories(inventory_dir: Path) -> list[dict[str, Any]]:
    return [row for _, row in load_jsonl(inventory_dir / "repositories.jsonl")]


def candidate_index(
    candidates: list[dict[str, Any]],
) -> dict[tuple[str, int], dict[str, Any]]:
    index: dict[tuple[str, int], dict[str, Any]] = {}
    for candidate in candidates:
        repo = str(candidate.get("repository_name_with_owner") or "").casefold()
        number = candidate.get("pull_request_number")
        if repo and isinstance(number, int):
            index[(repo, number)] = candidate
        for alias in candidate.get("repository_aliases") or []:
            if isinstance(alias, str) and alias:
                index[(alias.casefold(), number)] = candidate
    return index


def candidate_reason_errors(candidate: dict[str, Any]) -> list[str]:
    state = candidate.get("state")
    if state not in LEDGER_STATES:
        return [
            f"candidate {candidate.get('candidate_id')} has unknown state {state!r}"
        ]
    reasons = candidate.get("reason_codes")
    primary = candidate.get("primary_reason")
    errors: list[str] = []
    if not isinstance(primary, str) or not primary.strip():
        errors.append(
            f"candidate {candidate.get('candidate_id')} is missing primary_reason"
        )
    if not isinstance(reasons, list) or not reasons:
        errors.append(
            f"candidate {candidate.get('candidate_id')} is missing reason_codes"
        )
    return errors


def inventory_file_hash_errors(inventory_dir: Path) -> list[str]:
    manifest_path = inventory_dir / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    files = manifest.get("files") or {}
    errors: list[str] = []
    for name, meta in files.items():
        path = inventory_dir / name
        if not path.is_file():
            errors.append(f"inventory file missing: {name}")
            continue
        digest = sha256_file(path)
        declared = str((meta or {}).get("sha256") or "")
        size = path.stat().st_size
        if digest != declared:
            errors.append(
                f"{name} sha256 mismatch: declared {declared} actual {digest}"
            )
        declared_bytes = (meta or {}).get("bytes")
        if declared_bytes is not None and declared_bytes != size:
            errors.append(
                f"{name} byte size mismatch: declared {declared_bytes} actual {size}"
            )
    return errors


def parquet_hash_errors(release_manifest: Path, parquet_dir: Path) -> list[str]:
    if not release_manifest.is_file():
        return []
    manifest = json.loads(release_manifest.read_text(encoding="utf-8"))
    errors: list[str] = []
    files = manifest.get("files") or manifest.get("parquet") or {}
    if isinstance(files, dict):
        for name, meta in files.items():
            path = parquet_dir / name if not Path(name).is_absolute() else Path(name)
            if not path.is_file() and (parquet_dir / Path(name).name).is_file():
                path = parquet_dir / Path(name).name
            if not path.is_file():
                errors.append(f"release artifact missing: {name}")
                continue
            declared = str((meta or {}).get("sha256") or "")
            if declared and sha256_file(path) != declared:
                errors.append(f"{path.name} sha256 does not match release manifest")
    return errors
