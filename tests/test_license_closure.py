"""Fail-closed license-closure validation before positive corpus release."""

from __future__ import annotations

from license_closure_fixtures import (
    apache_source_bundle,
    changed_license_bundle,
    conflicting_card_manifest_bundle,
    conflicting_card_manifest_digest_bundle,
    custom_license_bundle,
    forge_substitution_bundle,
    license_ref_without_digest_bundle,
    mismatched_custom_identifier_bundle,
    missing_license_bundle,
    mixed_repository_bundle,
    spdx_known_bundle,
    stale_digest_bundle,
    unknown_license_bundle,
)
from license_closure_helpers import _assert_schema, _report
from lib.eligibility_render import render_json
from lib.license_closure import (
    assert_released_positives_are_closed,
    classify_license_family,
    released_positive_ids,
    validate_positive_release,
)


def test_spdx_known_license_closes_and_is_released():
    report = _report(spdx_known_bundle())
    _assert_schema(report)
    assert_released_positives_are_closed(report)
    assert report["closed"] is True
    assert report["license_families"] == ["spdx"]
    assert report["counts"]["unresolved_count"] == 0
    assert report["counts"]["released_positive_count"] == 1
    assert report["released_positives"][0]["spdx_id"] == "MIT"
    assert report["evidence_digests"][0]["digest"]
    assert not validate_positive_release(report)


def test_custom_license_closes_with_frozen_evidence():
    report = _report(custom_license_bundle())
    _assert_schema(report)
    assert report["closed"] is True
    assert report["license_families"] == ["custom"]
    assert report["released_positives"][0]["spdx_id"] == "LicenseRef-TemporalFocus"


def test_license_ref_without_text_digest_is_quarantined():
    report = _report(license_ref_without_digest_bundle())
    _assert_schema(report)
    assert report["released_positives"] == []
    assert "source_license_unknown" in report["quarantined"][0]["reason_codes"]


def test_custom_evidence_must_match_inventory_identifier():
    report = _report(mismatched_custom_identifier_bundle())
    _assert_schema(report)
    assert report["released_positives"] == []
    assert "source_license_unknown" in report["quarantined"][0]["reason_codes"]


def test_missing_license_is_quarantined_with_reason_and_evidence():
    report = _report(missing_license_bundle())
    _assert_schema(report)
    assert report["closed"] is False
    assert report["counts"]["released_positive_count"] == 0
    row = report["quarantined"][0]
    assert row["state"] == "quarantined"
    assert "source_license_missing" in row["reason_codes"]
    assert row["evidence"]["inventory_license"]["spdx_id"] is None
    assert row["record_id"] not in released_positive_ids(report)
    assert validate_positive_release(report)


def test_changed_license_blocks_positive_release():
    report = _report(changed_license_bundle())
    _assert_schema(report)
    reasons = report["quarantined"][0]["reason_codes"]
    assert "source_license_changed" in reasons
    assert report["released_positives"] == []
    assert report["quarantined"][0]["evidence"]["prior_evidence_digest"]
    assert report["quarantined"][0]["evidence"]["evidence_digest"]


def test_stale_declared_digest_is_a_changed_license():
    report = _report(stale_digest_bundle())
    assert "source_license_changed" in report["quarantined"][0]["reason_codes"]
    assert report["counts"]["unresolved_count"] == 1


def test_conflicting_card_and_manifest_digests_block_release():
    report = _report(conflicting_card_manifest_digest_bundle())
    _assert_schema(report)
    reasons = report["quarantined"][0]["reason_codes"]
    assert "declarations_disagree" in reasons
    assert "source_license_changed" in reasons
    assert report["released_positives"] == []
    assert report["quarantined"][0]["record_id"] not in released_positive_ids(report)


def test_conflicting_card_and_manifest_block_release():
    report = _report(conflicting_card_manifest_bundle())
    _assert_schema(report)
    reasons = report["quarantined"][0]["reason_codes"]
    assert "source_license_conflict" in reasons
    assert "declarations_disagree" in reasons
    assert report["quarantined"][0]["evidence"]["card_license"] == "MIT"
    assert report["quarantined"][0]["evidence"]["manifest_license"] == "Apache-2.0"


def test_mixed_repository_bundle_reports_each_digest():
    report = _report(mixed_repository_bundle())
    _assert_schema(report)
    assert report["closed"] is True
    assert report["license_families"] == ["spdx"]
    repos = {row["repository"] for row in report["evidence_digests"]}
    assert repos == {"rmems/widget", "Limen-Neural/axon-encoder"}
    assert report["counts"]["released_positive_count"] == 2
    ids = released_positive_ids(report)
    assert "rmems-widget-1" in ids
    assert "Limen-Neural-axon-encoder-37" in ids


def test_unknown_and_forge_substitution_cannot_be_released():
    unknown = _report(unknown_license_bundle())
    assert "source_license_unknown" in unknown["quarantined"][0]["reason_codes"]
    assert unknown["released_positives"] == []

    forged = _report(forge_substitution_bundle())
    reasons = forged["quarantined"][0]["reason_codes"]
    assert "forge_license_substitution" in reasons
    assert "source_license_missing" in reasons
    assert forged["released_positives"] == []


def test_genuine_apache_source_is_not_treated_as_relicense():
    report = _report(apache_source_bundle())
    assert report["closed"] is True
    assert report["released_positives"][0]["spdx_id"] == "Apache-2.0"
    assert not any(
        "forge_license_substitution" in (row.get("reason_codes") or [])
        for row in report["quarantined"]
    )


def test_unresolved_record_cannot_appear_in_released_positives():
    for bundle in (
        missing_license_bundle(),
        changed_license_bundle(),
        conflicting_card_manifest_bundle(),
        conflicting_card_manifest_digest_bundle(),
        license_ref_without_digest_bundle(),
        mismatched_custom_identifier_bundle(),
        unknown_license_bundle(),
        forge_substitution_bundle(),
    ):
        report = _report(bundle)
        assert_released_positives_are_closed(report)
        quarantined_ids = {row["record_id"] for row in report["quarantined"]}
        leaked = quarantined_ids.intersection(released_positive_ids(report))
        assert not leaked
        assert report["counts"]["released_positive_count"] == 0


def test_mixed_bundle_does_not_release_an_unresolved_sibling():
    bundle = mixed_repository_bundle()
    bundle["records"].append(
        {
            "id": "rmems-unlicensed-3",
            "repo": "rmems/unlicensed",
            "pr_number": 3,
            "license": "MIT",
        }
    )
    report = _report(bundle)
    assert report["closed"] is False
    assert "rmems-unlicensed-3" not in released_positive_ids(report)
    assert "rmems-unlicensed-3" in {row["record_id"] for row in report["quarantined"]}
    assert report["counts"]["released_positive_count"] == 2
    assert report["counts"]["unresolved_count"] == 1


def test_repeated_build_is_byte_identical():
    bundle = mixed_repository_bundle()
    first = render_json(_report(bundle))
    second = render_json(_report(bundle))
    assert first == second


def test_classify_license_family_is_fail_closed():
    assert classify_license_family("MIT") == "spdx"
    assert classify_license_family("MIT OR Apache-2.0") == "spdx"
    assert classify_license_family("(MIT OR Apache-2.0) AND BSD-3-Clause") == "spdx"
    assert classify_license_family("MIT AND (Apache-2.0 OR BSD-3-Clause)") == "spdx"
    assert classify_license_family("(MIT)") == "spdx"
    assert classify_license_family("LicenseRef-TemporalFocus") == "unknown"
    assert (
        classify_license_family("LicenseRef-TemporalFocus", has_custom_evidence=True)
        == "custom"
    )
    assert classify_license_family("NOASSERTION") == "unknown"
    assert classify_license_family("Not-A-Real-License-1.0") == "unknown"
    assert classify_license_family(None) == "missing"
    assert classify_license_family("(MIT") == "unknown"
    assert classify_license_family("MIT)") == "unknown"
    assert classify_license_family("MIT) OR (Apache-2.0") == "unknown"
    assert classify_license_family("NOASSERTION", has_custom_evidence=True) == "unknown"
    assert classify_license_family("OTHER", has_custom_evidence=True) == "unknown"
    assert (
        classify_license_family("Not-A-Real-License-1.0", has_custom_evidence=True)
        == "unknown"
    )
