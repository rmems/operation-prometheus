"""Event, artifact, license, and CI-evidence policy helpers."""

from __future__ import annotations

import re
from typing import Any

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


def _actor_id_error(event: dict[str, Any]) -> str | None:
    actor = event.get("actor")
    if not isinstance(actor, dict):
        return None
    actor_id = actor.get("id")
    if isinstance(actor_id, str) and actor_id.strip():
        return None
    return "actor attribution is missing a sourced id"


def _one_event_errors(event: dict[str, Any], seen: set[str]) -> list[str]:
    event_id = event.get("event_id")
    if not isinstance(event_id, str):
        return ["event is missing a sourced event_id"]
    if not event_id.strip():
        return ["event is missing a sourced event_id"]
    errors: list[str] = []
    if event_id in seen:
        errors.append(f"duplicate event_id {event_id}")
    seen.add(event_id)
    actor_error = _actor_id_error(event)
    if actor_error:
        errors.append(actor_error)
    return errors


def unique_artifact_errors(record: dict[str, Any]) -> list[str]:
    artifacts = record.get("artifacts")
    if not isinstance(artifacts, list):
        return []
    artifact_ids: set[str] = set()
    errors: list[str] = []
    for artifact in artifacts:
        errors.extend(_one_artifact_errors(artifact, artifact_ids))
    return errors


def _duplicate_artifact_id(artifact_id: str, artifact_ids: set[str]) -> str | None:
    if artifact_id in artifact_ids:
        return f"duplicate artifact id {artifact_id}"
    artifact_ids.add(artifact_id)
    return None


def _artifact_digest_error(digest: Any) -> str | None:
    if digest is None:
        return None
    if isinstance(digest, str) and SHA256_RE.fullmatch(digest):
        return None
    return "artifact sha256 is not a 64-char hex digest"


def _record_artifact_id(artifact: dict[str, Any], artifact_ids: set[str]) -> str | None:
    artifact_id = artifact.get("id")
    if not isinstance(artifact_id, str) or not artifact_id:
        return None
    return _duplicate_artifact_id(artifact_id, artifact_ids)


def _one_artifact_errors(artifact: Any, artifact_ids: set[str]) -> list[str]:
    if not isinstance(artifact, dict):
        return []
    errors: list[str] = []
    dup = _record_artifact_id(artifact, artifact_ids)
    if dup:
        errors.append(dup)
    digest_error = _artifact_digest_error(artifact.get("sha256"))
    if digest_error:
        errors.append(digest_error)
    return errors


def unique_event_errors(record: dict[str, Any]) -> list[str]:
    events = record.get("events")
    if not isinstance(events, list):
        return unique_artifact_errors(record)
    seen: set[str] = set()
    errors: list[str] = []
    for event in events:
        if not isinstance(event, dict):
            continue
        errors.extend(_one_event_errors(event, seen))
    errors.extend(unique_artifact_errors(record))
    return errors


def _license_field_error(record: dict[str, Any], field: str) -> str | None:
    value = record.get(field)
    if not isinstance(value, str):
        return f"{field} is missing a sourced value"
    if value.strip():
        return None
    return f"{field} is missing a sourced value"


def blank_license_policy_errors(record: dict[str, Any]) -> list[str]:
    if record.get("schema_version") not in ("1", "1.0", "v1"):
        return []
    errors: list[str] = []
    for field in ("license", "collection_policy"):
        message = _license_field_error(record, field)
        if message:
            errors.append(message)
    return errors


def is_real_check_run_detail(detail: str) -> bool:
    """True when a validation detail is a Checks API conclusion, not a PR checklist."""
    if CHECKLIST_RE.search(detail):
        return False
    return bool(CHECK_RUN_CONCLUSION_RE.search(detail))


def _ci_detail_error(detail: str) -> str | None:
    if CHECKLIST_RE.search(detail):
        if is_real_check_run_detail(detail):
            return None
        return "CI evidence is a PR-body checklist rather than a check-run conclusion"
    if not detail.strip():
        return None
    if is_real_check_run_detail(detail):
        return None
    if detail.startswith("review_apps"):
        return None
    folded = detail.casefold()
    if "passing locally" in folded:
        return "CI evidence is prose rather than a check-run conclusion"
    if "test plan" in folded:
        return "CI evidence is prose rather than a check-run conclusion"
    return None


def _missing_validation_errors(record: dict[str, Any]) -> list[str]:
    if record.get("schema_version") in ("1", "1.0", "v1"):
        return []
    return ["missing required validation evidence"]


def _ci_event_error(event: Any) -> str | None:
    if not isinstance(event, dict):
        return None
    if event.get("type") != "ci":
        return None
    return _ci_detail_error(str(event.get("detail") or ""))


def validation_evidence_errors(record: dict[str, Any]) -> list[str]:
    events = record.get("validation")
    if not isinstance(events, list):
        return _missing_validation_errors(record)
    if not events:
        return _missing_validation_errors(record)
    errors: list[str] = []
    for event in events:
        message = _ci_event_error(event)
        if message:
            errors.append(message)
    return errors


def _omitted_line_lacks_reason(line: str) -> bool:
    if not line.startswith("# omitted:"):
        return False
    folded = line.casefold()
    if "truncated" in folded:
        return False
    return "unavailable" not in folded


def _omitted_without_reason(patch: str) -> bool:
    for line in patch.splitlines():
        if _omitted_line_lacks_reason(line):
            return True
    return False


def _silent_budget_error(patch: str, declared: bool) -> str | None:
    if declared:
        return None
    if len(patch.encode("utf-8")) < 96 * 1024:
        return None
    return "silent patch truncation: patch meets the 96KiB budget without a truncation marker"


def _omitted_reason_error(patch: str) -> str | None:
    if "# omitted:" not in patch:
        return None
    if not _omitted_without_reason(patch):
        return None
    return "silent patch truncation: omitted file lacks a truncation reason"


def silent_truncation_errors(record: dict[str, Any]) -> list[str]:
    patch = record.get("patch")
    if not isinstance(patch, str) or not patch:
        return []
    declared = any(marker in patch for marker in DECLARED_TRUNCATION_MARKERS)
    budget = _silent_budget_error(patch, declared)
    if budget:
        return [budget]
    omitted = _omitted_reason_error(patch)
    if omitted:
        return [omitted]
    return []
