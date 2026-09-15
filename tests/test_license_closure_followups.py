"""Additional fail-closed holes for license-closure validation."""

from __future__ import annotations

import pytest

from license_closure_fixtures import (
    WRONG_HEAD_OID,
    inventory_pr,
    repository,
    spdx_known_bundle,
    with_code_state,
)
from license_closure_helpers import _assert_schema, _report
from lib.license_closure import classify_license_family, validate_positive_release


def test_empty_spdx_operands_are_unknown():
    assert classify_license_family("MIT OR ()") == "unknown"
    assert classify_license_family("() AND MIT") == "unknown"


def test_record_count_must_match_released_and_quarantined_rows():
    report = _report(spdx_known_bundle())
    report["released_positives"] = []
    report["counts"]["released_positive_count"] = 0
    report["counts"]["record_count"] = 1
    report["closed"] = True
    errors = validate_positive_release(report)
    assert errors
    assert any("record count" in error.lower() for error in errors)


def test_duplicate_pr_inventory_keys_are_rejected():
    bundle = spdx_known_bundle()
    bundle["records"][0] = with_code_state(bundle["records"][0])
    bundle["pull_requests"] = [
        inventory_pr("rmems/widget", 1),
        inventory_pr("rmems/widget", 1, head_oid=WRONG_HEAD_OID),
    ]
    with pytest.raises(ValueError, match="Duplicate inventory pull request"):
        _report(bundle)


def test_intermediate_event_commit_does_not_need_to_match_merge():
    bundle = spdx_known_bundle()
    row = with_code_state(bundle["records"][0])
    row["events"] = [{"code_state": {"commit_oid": "6" * 40}}]
    bundle["records"][0] = row
    bundle["pull_requests"] = [inventory_pr("rmems/widget", 1)]
    report = _report(bundle)
    _assert_schema(report)
    assert report["closed"] is True


def test_forward_rename_still_sees_prior_license_change():
    bundle = spdx_known_bundle()
    current = dict(bundle["repositories"][0])
    current["name_with_owner"] = "rmems/widget-renamed"
    current["aliases"] = [{"name_with_owner": "rmems/widget"}]
    bundle["repositories"] = [current]
    bundle["records"][0]["repo"] = "rmems/widget-renamed"
    bundle["card"]["source_repo"] = "rmems/widget-renamed"
    bundle["manifest"]["source_repo"] = "rmems/widget-renamed"
    bundle["prior_repositories"] = [
        repository(
            "rmems/widget",
            spdx_id="Apache-2.0",
            license_name="Apache License 2.0",
            url="https://api.github.com/licenses/apache-2.0",
        )
    ]
    report = _report(bundle)
    _assert_schema(report)
    assert "source_license_changed" in report["quarantined"][0]["reason_codes"]
    assert report["released_positives"] == []


def test_conflicting_record_repo_identities_cannot_close():
    bundle = spdx_known_bundle()
    bundle["records"][0]["repository"] = {"owner": "other", "name": "place"}
    report = _report(bundle)
    _assert_schema(report)
    assert "declarations_disagree" in report["quarantined"][0]["reason_codes"]
    assert report["released_positives"] == []
