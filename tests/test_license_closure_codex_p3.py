"""Codex P3 fail-closed holes against the current license-closure HEAD."""

from __future__ import annotations

import pytest

from license_closure_fixtures import (
    custom_license_bundle,
    inventory_pr,
    mixed_repository_bundle,
    spdx_known_bundle,
    with_code_state,
)
from license_closure_helpers import _assert_schema, _report
from lib.license_closure import validate_positive_release


def test_undeclared_record_license_map_conflict_cannot_close():
    bundle = mixed_repository_bundle()
    bundle["records"] = [bundle["records"][0]]
    bundle["manifest"]["source_licenses"] = dict(bundle["manifest"]["source_licenses"])
    bundle["manifest"]["source_licenses"]["Limen-Neural/axon-encoder"] = "MIT"
    report = _report(bundle)
    _assert_schema(report)
    assert "declarations_disagree" in report["quarantined"][0]["reason_codes"]
    assert report["released_positives"] == []


def test_balanced_parenthesis_link_destination_is_not_disclosure():
    bundle = spdx_known_bundle()
    bundle["markdown"] = (
        "## License / provenance\n\n[details](https://example.test/foo(bar)/MIT)\n"
    )
    report = _report(bundle)
    _assert_schema(report)
    assert "card_disclosure_missing" in report["quarantined"][0]["reason_codes"]
    assert report["released_positives"] == []


def test_swapped_released_record_identity_cannot_validate_release():
    report = _report(spdx_known_bundle())
    report["released_positives"][0]["record_id"] = "evil-other-99"
    report["released_positives"][0]["pr_number"] = 99
    errors = validate_positive_release(report)
    assert errors
    assert any("license family" in error for error in errors)


def test_malformed_pr_inventory_row_is_rejected():
    bundle = spdx_known_bundle()
    bundle["records"][0] = with_code_state(bundle["records"][0])
    bundle["pull_requests"] = [inventory_pr("rmems/widget", 1), {}]
    with pytest.raises(ValueError, match="pull-request inventory"):
        _report(bundle)


def test_conflicting_custom_license_identity_fields_cannot_close():
    bundle = custom_license_bundle()
    custom = dict(bundle["repositories"][0]["custom_license"])
    custom["spdx_id"] = "LicenseRef-Other"
    bundle["repositories"][0]["custom_license"] = custom
    report = _report(bundle)
    _assert_schema(report)
    assert report["released_positives"] == []
    assert report["quarantined"]


def test_string_closed_flag_cannot_validate_release():
    report = _report(spdx_known_bundle())
    report["closed"] = "false"
    errors = validate_positive_release(report)
    assert errors
    assert any("closed" in error for error in errors)
