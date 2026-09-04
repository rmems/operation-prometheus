from __future__ import annotations

import pytest

from build_eligibility_ledger import _validate_inputs
from eligibility_fixtures import _policy, _repo_root, _snapshot
from lib.eligibility_artifacts import build_eligibility_artifacts
from lib.source_inventory import sha256_json


def test_duplicate_baseline_explanation_metrics_fail_closed(tmp_path):
    policy = _policy()
    policy["baseline"]["drift_explanations"] = [
        {
            "metric": "active_public_repository_count",
            "reason_code": "first",
            "countervailing_delta": 0,
            "evidence_refs": ["evidence:first"],
        },
        {
            "metric": "active_public_repository_count",
            "reason_code": "second",
            "countervailing_delta": 1,
            "evidence_refs": ["evidence:second"],
        },
    ]
    _validate_inputs(_snapshot(), policy)
    with pytest.raises(ValueError, match="Duplicate baseline drift explanation metric"):
        build_eligibility_artifacts(_snapshot(), policy, _repo_root(tmp_path))


def test_baseline_automatic_drift_requires_exact_non_dependency_event_reconciliation(tmp_path):
    snapshot = _snapshot()
    snapshot["pull_requests"][0]["merged_at"] = "2026-08-25T00:00:00Z"
    snapshot["pull_requests"][3]["merged_at"] = "2026-08-26T00:00:00Z"
    snapshot["pull_requests"][4]["merged_at"] = "2026-08-27T00:00:00Z"
    snapshot.pop("snapshot_sha256")
    snapshot["snapshot_sha256"] = sha256_json(snapshot)
    policy = _policy()
    policy["baseline"]["expected_counts"]["merged_non_dependency_pr_count"] = 1
    artifacts = build_eligibility_artifacts(snapshot, policy, _repo_root(tmp_path))
    comparison = next(
        row
        for row in artifacts["baseline_report"]["comparisons"]
        if row["metric"] == "merged_non_dependency_pr_count"
    )
    assert comparison["delta"] == 1
    assert comparison["post_cutoff_event_count"] == 2
    assert comparison["countervailing_delta"] == -1
    assert comparison["explained"] is False
