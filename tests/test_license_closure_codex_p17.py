"""Codex P17 fail-closed holes against the current license-closure HEAD."""

from __future__ import annotations

import pytest

from license_closure_fixtures import bind_source_hash, spdx_known_bundle
from license_closure_helpers import _assert_schema, _report
from lib.license_closure import validate_positive_release


def test_null_declared_digest_cannot_close():
    bundle = spdx_known_bundle()
    bundle["card"]["license_evidence_digest"] = None
    bundle["manifest"]["license_evidence_digest"] = None
    report = _report(bundle)
    _assert_schema(report)
    assert "declarations_disagree" in report["quarantined"][0]["reason_codes"]
    assert report["released_positives"] == []


def test_omitted_declared_digest_still_closes():
    bundle = spdx_known_bundle()
    del bundle["card"]["license_evidence_digest"]
    del bundle["manifest"]["license_evidence_digest"]
    report = _report(bundle)
    _assert_schema(report)
    assert report["closed"] is True
    assert report["released_positives"]


def test_integer_repository_id_cannot_index():
    bundle = spdx_known_bundle()
    row = dict(bundle["repositories"][0])
    row["repository_id"] = 7
    bundle["repositories"] = [bind_source_hash(row)]
    with pytest.raises(ValueError, match="repository_id"):
        _report(bundle)


def test_code_span_in_link_label_is_not_disclosure():
    bundle = spdx_known_bundle()
    bundle["markdown"] = (
        "## License / provenance\n\n[details `]`](https://example.test/MIT)\n"
    )
    report = _report(bundle)
    _assert_schema(report)
    assert "card_disclosure_missing" in report["quarantined"][0]["reason_codes"]
    assert report["released_positives"] == []


def test_link_label_text_cannot_invent_license_heading():
    bundle = spdx_known_bundle()
    bundle["markdown"] = "[## License / provenance](https://example.test)\n\nMIT\n"
    report = _report(bundle)
    _assert_schema(report)
    assert "card_disclosure_missing" in report["quarantined"][0]["reason_codes"]
    assert report["released_positives"] == []


def test_empty_report_invalid_snapshot_cannot_validate_release():
    report = _report(spdx_known_bundle())
    report["released_positives"] = []
    report["quarantined"] = []
    report["evidence_digests"] = []
    report["license_families"] = []
    report["counts"] = {
        "quarantined_count": 0,
        "record_count": 0,
        "released_positive_count": 0,
        "unresolved_count": 0,
    }
    report["closed"] = True
    report["snapshot_sha256"] = "not-a-digest"
    errors = validate_positive_release(report)
    assert errors
    assert any("snapshot_sha256" in error for error in errors)


def test_scalar_inventory_license_cannot_close():
    bundle = spdx_known_bundle()
    row = dict(bundle["repositories"][0])
    row["license"] = "MIT"
    bundle["repositories"] = [bind_source_hash(row)]
    report = _report(bundle)
    _assert_schema(report)
    assert report["released_positives"] == []
    assert report["quarantined"]


def test_object_card_manifest_license_cannot_close():
    bundle = spdx_known_bundle()
    bundle["card"]["source_license"] = {"spdx_id": "MIT"}
    bundle["manifest"]["source_license"] = {"spdx_id": "MIT"}
    report = _report(bundle)
    _assert_schema(report)
    assert report["released_positives"] == []
    assert report["quarantined"]
