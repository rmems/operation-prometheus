"""Codex P14 fail-closed holes against the current license-closure HEAD."""

from __future__ import annotations

from license_closure_fixtures import spdx_known_bundle
from license_closure_helpers import _assert_schema, _report
from lib.license_closure import classify_license_family, validate_positive_release


def test_newline_after_hashes_is_not_license_heading():
    bundle = spdx_known_bundle()
    bundle["markdown"] = "##\nLicense / provenance\n\nMIT\n"
    report = _report(bundle)
    _assert_schema(report)
    assert "card_disclosure_missing" in report["quarantined"][0]["reason_codes"]
    assert report["released_positives"] == []


def test_malformed_inventory_scalars_cannot_authenticate():
    bundle = spdx_known_bundle()
    row = dict(bundle["repositories"][0])
    row["archived"] = {}
    row["pull_request_total_count"] = {}
    bundle["repositories"] = [row]
    report = _report(bundle)
    _assert_schema(report)
    assert "snapshot_provenance_missing" in report["quarantined"][0]["reason_codes"]
    assert report["released_positives"] == []


def test_integer_id_cannot_close_via_trajectory_id():
    bundle = spdx_known_bundle()
    record = dict(bundle["records"][0])
    record["trajectory_id"] = record["id"]
    record["id"] = 7
    bundle["records"] = [record]
    report = _report(bundle)
    _assert_schema(report)
    assert "declarations_disagree" in report["quarantined"][0]["reason_codes"]
    assert report["released_positives"] == []


def test_deeply_nested_spdx_groups_are_unknown_not_recursion_error():
    identifier = "MIT"
    for _ in range(1000):
        identifier = f"MIT OR ({identifier})"
    assert classify_license_family(identifier) == "unknown"
    assert classify_license_family("(MIT OR Apache-2.0) AND BSD-3-Clause") == "spdx"


def test_array_quarantined_record_id_cannot_validate_release():
    report = _report(spdx_known_bundle())
    report["released_positives"] = []
    report["quarantined"] = [
        {
            "record_id": ["rmems-widget-1"],
            "primary_reason": "source_license_missing",
            "reason_codes": ["source_license_missing"],
        }
    ]
    report["closed"] = True
    report["counts"] = {
        "quarantined_count": 1,
        "record_count": 1,
        "released_positive_count": 0,
        "unresolved_count": 1,
    }
    errors = validate_positive_release(report)
    assert errors
    assert any("record_id" in error for error in errors)
