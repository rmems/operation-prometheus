"""Persisted report fail-closed cases for validate_positive_release."""

from __future__ import annotations


from license_closure_fixtures import (
    custom_license_bundle,
    spdx_known_bundle,
)
from license_closure_helpers import _assert_schema, _report
from lib.license_closure import (
    validate_positive_release,
)

def test_custom_family_without_frozen_evidence_cannot_validate_release():
    report = _report(spdx_known_bundle())
    report["released_positives"][0]["spdx_id"] = "LicenseRef-Fake"
    report["released_positives"][0]["license_family"] = "custom"
    report["license_families"] = ["custom"]
    report["evidence_digests"][0]["spdx_id"] = "LicenseRef-Fake"
    report["evidence_digests"][0]["family"] = "custom"
    errors = validate_positive_release(report)
    assert errors
    assert any("license family" in error for error in errors)


def test_swapped_custom_text_digest_cannot_validate_release():
    report = _report(custom_license_bundle())
    released = report["released_positives"][0]
    released["custom_license"] = {
        **released["custom_license"],
        "text_sha256": "e" * 64,
    }
    _assert_schema(report)
    errors = validate_positive_release(report)
    assert errors
    assert any("license family" in error for error in errors)


def test_swapped_spdx_id_cannot_validate_release():
    report = _report(spdx_known_bundle())
    released = report["released_positives"][0]
    released["spdx_id"] = "Apache-2.0"
    report["evidence_digests"][0]["spdx_id"] = "Apache-2.0"
    _assert_schema(report)
    errors = validate_positive_release(report)
    assert errors
    assert any("license family" in error for error in errors)


def test_swapped_spdx_digest_cannot_validate_release():
    report = _report(spdx_known_bundle())
    released = report["released_positives"][0]
    released["evidence_digest"] = "e" * 64
    report["evidence_digests"][0]["digest"] = "e" * 64
    _assert_schema(report)
    errors = validate_positive_release(report)
    assert errors
    assert any("license family" in error for error in errors)


def test_malformed_quarantined_row_cannot_validate_release():
    report = _report(spdx_known_bundle())
    report["released_positives"] = []
    report["quarantined"] = ["malformed"]
    report["closed"] = True
    report["bundle_errors"] = []
    report["evidence_digests"] = []
    report["license_families"] = []
    report["counts"] = {
        "quarantined_count": 0,
        "record_count": 0,
        "released_positive_count": 0,
        "unresolved_count": 0,
    }
    errors = validate_positive_release(report)
    assert errors
    assert any("objects" in error for error in errors)


def test_released_row_missing_record_id_cannot_validate_release():
    report = _report(spdx_known_bundle())
    report["released_positives"] = [{}]
    errors = validate_positive_release(report)
    assert errors
    assert any("required fields" in error for error in errors)


def test_quarantined_row_missing_reason_cannot_validate_release():
    report = _report(spdx_known_bundle())
    report["released_positives"] = []
    report["quarantined"] = [{"record_id": "rmems-widget-1"}]
    report["closed"] = False
    errors = validate_positive_release(report)
    assert errors
    assert any("required fields" in error for error in errors)


def test_swapped_released_repo_cannot_validate_release():
    report = _report(spdx_known_bundle())
    report["released_positives"][0]["repo"] = "evil/other"
    report["evidence_digests"][0]["repository"] = "evil/other"
    errors = validate_positive_release(report)
    assert errors
    assert any("license family" in error for error in errors)


def test_swapped_report_snapshot_cannot_validate_release():
    report = _report(spdx_known_bundle())
    report["snapshot_sha256"] = "f" * 64
    errors = validate_positive_release(report)
    assert errors
    assert any("license family" in error for error in errors)


def test_boolean_report_counts_cannot_validate_release():
    report = _report(spdx_known_bundle())
    report["counts"] = {
        "quarantined_count": False,
        "record_count": True,
        "released_positive_count": True,
        "unresolved_count": False,
    }
    errors = validate_positive_release(report)
    assert errors
    assert any("count" in error for error in errors)


def test_released_row_missing_license_family_cannot_validate_release():
    report = _report(spdx_known_bundle())
    report["released_positives"][0].pop("license_family", None)
    errors = validate_positive_release(report)
    assert errors
    assert any("required fields" in error for error in errors)


def test_released_row_missing_evidence_digest_cannot_validate_release():
    report = _report(spdx_known_bundle())
    report["released_positives"][0].pop("evidence_digest", None)
    errors = validate_positive_release(report)
    assert errors
    assert any("required fields" in error for error in errors)


