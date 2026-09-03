"""Per-dimension quality assessment for eligibility-ledger candidates."""

from __future__ import annotations

from typing import Any

from .eligibility_common import _parse_time, _source_ref, _text

QUALITY_DIMENSIONS = (
    "task_hypothesis_clarity",
    "before_state_completeness",
    "patch_action_fidelity",
    "chronology_confidence",
    "validation_strength",
    "outcome_confidence",
    "artifact_reproducibility",
    "license_clarity",
    "policy_privacy_result",
)
QUALITY_ASSESSMENTS = {
    "verified",
    "partial",
    "missing",
    "failed",
    "unknown",
    "not_applicable",
}


def _quality(
    assessment: str,
    reason_codes: list[str],
    evidence_refs: list[str] | None = None,
) -> dict[str, Any]:
    if assessment not in QUALITY_ASSESSMENTS:
        raise ValueError(f"Unknown quality assessment {assessment}")
    return {
        "assessment": assessment,
        "reason_codes": sorted(set(reason_codes)),
        "evidence_refs": sorted(set(evidence_refs or [])),
    }


def _linked_clarity(
    linked_refs: list[str],
    title: str,
    body: str,
    source: str,
) -> dict[str, Any]:
    if title or body:
        return _quality(
            "partial",
            ["formal_issue_reference_without_issue_content", "pr_description_present"],
            [source, *linked_refs],
        )
    return _quality(
        "partial",
        ["formal_issue_reference_without_issue_content"],
        linked_refs,
    )


def _clarity_assessment(
    linked: list[dict[str, Any]],
    title: str,
    body: str,
    source: str,
) -> dict[str, Any]:
    linked_refs = [str(item.get("url") or item.get("id")) for item in linked]
    if linked:
        return _linked_clarity(linked_refs, title, body, source)
    if title and body:
        return _quality("partial", ["pr_description_without_formal_issue_link"], [source])
    if title:
        return _quality("partial", ["pr_title_only"], [source])
    return _quality("missing", ["task_signal_missing"])


def _before_state_completeness(base_oid: str, head_oid: str) -> dict[str, Any]:
    if base_oid and head_oid:
        return _quality(
            "partial",
            ["source_oids_without_content_addressed_snapshot"],
            [f"git:{base_oid}", f"git:{head_oid}"],
        )
    return _quality("missing", ["base_or_head_oid_missing"])


def _patch_action_fidelity(base_oid: str, head_oid: str) -> dict[str, Any]:
    if base_oid and head_oid:
        return _quality(
            "partial",
            ["source_oids_without_full_patch_artifact"],
            [f"git:{base_oid}", f"git:{head_oid}"],
        )
    return _quality("missing", ["patch_and_code_state_missing"])


def _chronology_confidence(
    pr: dict[str, Any],
    state: str,
    terminal_time: Any,
    source: str,
) -> dict[str, Any]:
    timestamps = [pr.get("created_at"), pr.get("updated_at")]
    if state in {"merged", "closed"}:
        timestamps.append(terminal_time)
    if all(_parse_time(value) is not None for value in timestamps):
        return _quality("partial", ["pr_level_chronology_only"], [source])
    return _quality("missing", ["source_timestamp_missing_or_invalid"])


_TERMINAL_OUTCOME_REASONS = {
    "merged": ("merged_at", "github_merged_terminal_state"),
    "closed": ("closed_at", "github_closed_unmerged_terminal_state"),
}


def _outcome_confidence(pr: dict[str, Any], state: str, source: str) -> dict[str, Any]:
    url_ref = str(pr.get("url") or source)
    terminal = _TERMINAL_OUTCOME_REASONS.get(state)
    if terminal and _parse_time(pr.get(terminal[0])):
        return _quality("verified", [terminal[1]], [url_ref])
    if state == "open":
        return _quality("partial", ["mutable_open_state"], [url_ref])
    return _quality("unknown", ["terminal_state_unresolved"])


def _artifact_reproducibility(base_oid: str, head_oid: str) -> dict[str, Any]:
    if base_oid and head_oid:
        return _quality(
            "partial",
            ["git_oids_present_artifact_bundle_missing"],
            [f"git:{base_oid}", f"git:{head_oid}"],
        )
    return _quality("missing", ["reproducible_artifact_reference_missing"])


def _license_clarity(repository: dict[str, Any]) -> dict[str, Any]:
    spdx = str(((repository.get("license") or {}).get("spdx_id")) or "").strip()
    if spdx and spdx.upper() not in {"NOASSERTION", "OTHER"}:
        return _quality(
            "partial",
            ["current_repository_license_only"],
            [f"spdx:{spdx}", _source_ref(repository)],
        )
    return _quality("missing", ["source_license_unresolved"])


def _policy_privacy_result(pr: dict[str, Any], source: str) -> dict[str, Any]:
    warnings = pr.get("collection_warnings") or []
    if warnings:
        return _quality(
            "partial",
            ["source_metadata_sanitized", *[str(item) for item in warnings]],
            [source],
        )
    return _quality("partial", ["public_metadata_only_policy_scan"], [source])


def _assert_dimensions(result: dict[str, Any]) -> None:
    if set(result) != set(QUALITY_DIMENSIONS):
        raise AssertionError("Quality assessment dimensions drifted")


def assess_quality(pr: dict[str, Any], repository: dict[str, Any]) -> dict[str, Any]:
    source = _source_ref(pr)
    title = _text(pr.get("title")).strip()
    body = _text(pr.get("body")).strip()
    base_oid = _text(pr.get("base_oid"))
    head_oid = _text(pr.get("head_oid"))
    state = _text(pr.get("state")).lower()
    terminal_time = pr.get("merged_at") or pr.get("closed_at")

    result = {
        "task_hypothesis_clarity": _clarity_assessment(
            pr.get("linked_issues") or [], title, body, source
        ),
        "before_state_completeness": _before_state_completeness(base_oid, head_oid),
        "patch_action_fidelity": _patch_action_fidelity(base_oid, head_oid),
        "chronology_confidence": _chronology_confidence(pr, state, terminal_time, source),
        "validation_strength": _quality(
            "missing", ["check_and_validation_events_not_collected"]
        ),
        "outcome_confidence": _outcome_confidence(pr, state, source),
        "artifact_reproducibility": _artifact_reproducibility(base_oid, head_oid),
        "license_clarity": _license_clarity(repository),
        "policy_privacy_result": _policy_privacy_result(pr, source),
    }
    _assert_dimensions(result)
    return result
