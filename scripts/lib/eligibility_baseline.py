"""Baseline drift reconciliation for the eligibility ledger."""

from __future__ import annotations

from datetime import datetime
from typing import Any, NamedTuple

from .eligibility_common import _parse_time

_REPOSITORY_METRICS = {"public_repository_count", "active_public_repository_count"}
_MERGED_PR_METRICS = {
    "merged_non_dependency_pr_count",
    "formally_issue_linked_merged_pr_count",
}


def _is_active_repository(row: dict[str, Any]) -> bool:
    return not row.get("archived") and not row.get("disabled")


def _merged_non_dependency(candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        row
        for row in candidates
        if row["source_state"] == "merged" and row["task_family"] != "dependency"
    ]


def _closed_unmerged_non_dependency(candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        row
        for row in candidates
        if row["source_state"] == "closed" and row["task_family"] != "dependency"
    ]


def _unique_existing_keys(existing_rows: list[dict[str, Any]]) -> set[tuple[str, Any]]:
    return {
        (
            str(row.get("resolved_repository_name_with_owner") or row["repo"]).casefold(),
            row["pr_number"],
        )
        for row in existing_rows
    }


def _exact_current_duplicates(duplicates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        row
        for row in duplicates
        if row["kind"] == "current_corpus_duplicate" and row.get("exact")
    ]


def _baseline_counts(
    repositories: list[dict[str, Any]],
    candidates: list[dict[str, Any]],
    existing_rows: list[dict[str, Any]],
    duplicates: list[dict[str, Any]],
) -> dict[str, int]:
    merged_non_dependency = _merged_non_dependency(candidates)
    linked_merged = [row for row in merged_non_dependency if row.get("linked_issues")]
    return {
        "public_repository_count": len(repositories),
        "active_public_repository_count": len([
            row for row in repositories if _is_active_repository(row)
        ]),
        "merged_non_dependency_pr_count": len(merged_non_dependency),
        "formally_issue_linked_merged_pr_count": len(linked_merged),
        "closed_unmerged_pr_count": len(_closed_unmerged_non_dependency(candidates)),
        "existing_prometheus_row_count": len(existing_rows),
        "existing_unique_pr_count": len(_unique_existing_keys(existing_rows)),
        "exact_current_duplicate_candidate_count": len(_exact_current_duplicates(duplicates)),
    }


def _is_post_cutoff(row: dict[str, Any], time_field: str, cutoff: datetime) -> bool:
    moment = _parse_time(row.get(time_field))
    return moment is not None and moment > cutoff


def _post_cutoff_repository_events(
    metric: str,
    cutoff: datetime,
    repositories: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    return [
        {"repository_id": row["repository_id"], "created_at": row.get("created_at")}
        for row in repositories
        if metric != "active_public_repository_count" or _is_active_repository(row)
        if _is_post_cutoff(row, "created_at", cutoff)
    ]


class _PrEventSpec(NamedTuple):
    state: str
    time_field: str
    linked_only: bool


def _post_cutoff_pr_events(
    cutoff: datetime,
    candidates: list[dict[str, Any]],
    spec: _PrEventSpec,
) -> list[dict[str, Any]]:
    return [
        {"candidate_id": row["candidate_id"], spec.time_field: row.get(spec.time_field)}
        for row in candidates
        if row["source_state"] == spec.state
        and row["task_family"] != "dependency"
        and (not spec.linked_only or row.get("linked_issues"))
        and _is_post_cutoff(row, spec.time_field, cutoff)
    ]


def _post_cutoff_evidence(
    metric: str,
    cutoff: datetime,
    repositories: list[dict[str, Any]],
    candidates: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    if metric in _REPOSITORY_METRICS:
        return _post_cutoff_repository_events(metric, cutoff, repositories)
    if metric in _MERGED_PR_METRICS:
        spec = _PrEventSpec(
            "merged", "merged_at", metric == "formally_issue_linked_merged_pr_count"
        )
        return _post_cutoff_pr_events(cutoff, candidates, spec)
    if metric == "closed_unmerged_pr_count":
        return _post_cutoff_pr_events(cutoff, candidates, _PrEventSpec("closed", "closed_at", False))
    return []


def _drift_metric(item: Any) -> str | None:
    if not isinstance(item, dict) or not item.get("metric"):
        return None
    return str(item["metric"])


def _manual_drift_map(baseline: dict[str, Any]) -> dict[str, dict[str, Any]]:
    manual: dict[str, dict[str, Any]] = {}
    for item in baseline.get("drift_explanations") or []:
        metric = _drift_metric(item)
        if metric is None:
            continue
        if metric in manual:
            raise ValueError(f"Duplicate baseline drift explanation metric {metric}")
        manual[metric] = item
    return manual


def _initial_reconciliation(delta: int, automatic_event_count: int) -> tuple[bool, str]:
    if delta == 0:
        return True, "unchanged_from_baseline"
    return 0 < delta == automatic_event_count, "post_baseline_source_events"


class _BaselineContext(NamedTuple):
    actual: dict[str, int]
    cutoff: datetime
    repositories: list[dict[str, Any]]
    candidates: list[dict[str, Any]]
    manual: dict[str, dict[str, Any]]


def _apply_manual_explanation(
    entry: dict[str, Any],
    delta: int,
    automatic_event_count: int,
    evidence: list[dict[str, Any]],
) -> tuple[bool, str]:
    refs = entry.get("evidence_refs") or []
    declared_countervailing_delta = entry.get("countervailing_delta")
    if declared_countervailing_delta != delta - automatic_event_count:
        raise ValueError(
            f"Baseline drift explanation for {entry['metric']} declares countervailing_delta "
            f"{declared_countervailing_delta!r}, expected {delta - automatic_event_count}"
        )
    if not refs:
        return False, "unexplained_drift"
    evidence.extend({"evidence_ref": str(ref)} for ref in refs)
    return True, str(entry.get("reason_code") or "manual_evidence_backed_explanation")


def _metric_comparison(
    metric: str,
    expected_value: Any,
    context: _BaselineContext,
) -> dict[str, Any]:
    if metric not in context.actual:
        raise ValueError(f"Unknown baseline metric {metric}")
    expected_int = int(expected_value)
    actual_value = int(context.actual[metric])
    delta = actual_value - expected_int
    evidence = _post_cutoff_evidence(
        metric, context.cutoff, context.repositories, context.candidates
    )
    automatic_event_count = len(evidence)
    explained, explanation = _initial_reconciliation(delta, automatic_event_count)
    if not explained and metric in context.manual:
        explained, explanation = _apply_manual_explanation(
            context.manual[metric], delta, automatic_event_count, evidence
        )
    return {
        "metric": metric,
        "expected": expected_int,
        "actual": actual_value,
        "delta": delta,
        "post_cutoff_event_count": automatic_event_count,
        "countervailing_delta": delta - automatic_event_count,
        "explained": explained,
        "explanation": explanation if explained else "unexplained_drift",
        "evidence": evidence,
    }


def build_baseline_report(
    policy: dict[str, Any],
    actual: dict[str, int],
    repositories: list[dict[str, Any]],
    candidates: list[dict[str, Any]],
) -> dict[str, Any]:
    baseline = policy.get("baseline") or {}
    expected = baseline.get("expected_counts") or {}
    cutoff = _parse_time(baseline.get("queried_at"))
    if cutoff is None:
        raise ValueError("Policy baseline.queried_at must be a valid timestamp")
    manual = _manual_drift_map(baseline)
    context = _BaselineContext(actual, cutoff, repositories, candidates, manual)
    comparisons = [
        _metric_comparison(metric, expected_value, context)
        for metric, expected_value in expected.items()
    ]
    return {
        "schema_version": "eligibility_baseline_report_v1",
        "baseline_queried_at": baseline.get("queried_at"),
        "snapshot_collected_at": policy.get("snapshot_collected_at"),
        "comparisons": comparisons,
        "complete": all(row["explained"] for row in comparisons),
    }
