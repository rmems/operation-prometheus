"""Persisted report fail-closed cases for validate_positive_release."""

from __future__ import annotations

import pytest

from license_closure_fixtures import (
    custom_license_bundle,
    spdx_known_bundle,
)
from license_closure_helpers import _assert_schema, _report
from lib.license_closure import (
    validate_positive_release,
)


def _swap_custom_identifier(report: dict) -> None:
    report["released_positives"][0]["spdx_id"] = "LicenseRef-Fake"
    report["released_positives"][0]["license_family"] = "custom"
    report["license_families"] = ["custom"]
    report["evidence_digests"][0]["spdx_id"] = "LicenseRef-Fake"
    report["evidence_digests"][0]["family"] = "custom"


def _swap_custom_text_digest(report: dict) -> None:
    released = report["released_positives"][0]
    released["custom_license"] = {
        **released["custom_license"],
        "text_sha256": "e" * 64,
    }
    _assert_schema(report)


def _swap_released_spdx_id(report: dict) -> None:
    report["released_positives"][0]["spdx_id"] = "Apache-2.0"
    report["evidence_digests"][0]["spdx_id"] = "Apache-2.0"
    _assert_schema(report)


def _swap_released_spdx_digest(report: dict) -> None:
    report["released_positives"][0]["evidence_digest"] = "e" * 64
    report["evidence_digests"][0]["digest"] = "e" * 64
    _assert_schema(report)


def _swap_released_repo(report: dict) -> None:
    report["released_positives"][0]["repo"] = "evil/other"
    report["evidence_digests"][0]["repository"] = "evil/other"


def _swap_report_snapshot(report: dict) -> None:
    report["snapshot_sha256"] = "f" * 64


def _swap_counts_to_booleans(report: dict) -> None:
    report["counts"] = {
        "quarantined_count": False,
        "record_count": True,
        "released_positive_count": True,
        "unresolved_count": False,
    }


def _drop_released_license_family(report: dict) -> None:
    report["released_positives"][0].pop("license_family", None)


def _drop_released_evidence_digest(report: dict) -> None:
    report["released_positives"][0].pop("evidence_digest", None)


def _blank_released_row(report: dict) -> None:
    report["released_positives"] = [{}]


def _reasonless_quarantined_row(report: dict) -> None:
    report["released_positives"] = []
    report["quarantined"] = [{"record_id": "rmems-widget-1"}]
    report["closed"] = False


@pytest.mark.parametrize(
    "bundle_fn,mutate",
    [
        pytest.param(
            spdx_known_bundle, _swap_custom_identifier, id="custom-no-evidence"
        ),
        pytest.param(
            custom_license_bundle, _swap_custom_text_digest,
            id="custom-text-digest",
        ),
        pytest.param(spdx_known_bundle, _swap_released_spdx_id, id="spdx-id"),
        pytest.param(
            spdx_known_bundle, _swap_released_spdx_digest, id="spdx-digest"
        ),
        pytest.param(spdx_known_bundle, _swap_released_repo, id="repo"),
        pytest.param(spdx_known_bundle, _swap_report_snapshot, id="snapshot"),
    ],
)
def test_tampered_release_report_cannot_validate(bundle_fn, mutate):
    report = _report(bundle_fn())
    mutate(report)
    errors = validate_positive_release(report)
    assert errors
    assert any("license family" in error for error in errors)


@pytest.mark.parametrize(
    "mutate",
    [
        pytest.param(_blank_released_row, id="missing-record-id"),
        pytest.param(_reasonless_quarantined_row, id="missing-reason"),
        pytest.param(_drop_released_license_family, id="missing-family"),
        pytest.param(_drop_released_evidence_digest, id="missing-digest"),
    ],
)
def test_rows_missing_required_fields_cannot_validate(mutate):
    report = _report(spdx_known_bundle())
    mutate(report)
    errors = validate_positive_release(report)
    assert errors
    assert any("required fields" in error for error in errors)


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


def test_boolean_report_counts_cannot_validate_release():
    report = _report(spdx_known_bundle())
    _swap_counts_to_booleans(report)
    errors = validate_positive_release(report)
    assert errors
    assert any("count" in error for error in errors)
