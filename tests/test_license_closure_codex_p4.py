"""Codex P4 fail-closed holes against the current license-closure HEAD."""

from __future__ import annotations

from license_closure_fixtures import SNAPSHOT_SHA256, spdx_known_bundle
from license_closure_helpers import _assert_schema, _report


def test_inline_display_none_is_not_disclosure():
    bundle = spdx_known_bundle()
    bundle["markdown"] = (
        '## License / provenance\n\n<span style="display:none">MIT</span>\n'
    )
    report = _report(bundle)
    _assert_schema(report)
    assert "card_disclosure_missing" in report["quarantined"][0]["reason_codes"]
    assert report["released_positives"] == []


def test_inline_visibility_hidden_is_not_disclosure():
    bundle = spdx_known_bundle()
    bundle["markdown"] = (
        '## License / provenance\n\n<span style="visibility:hidden">MIT</span>\n'
    )
    report = _report(bundle)
    _assert_schema(report)
    assert "card_disclosure_missing" in report["quarantined"][0]["reason_codes"]
    assert report["released_positives"] == []


def test_html_block_fragments_are_not_disclosure():
    bundle = spdx_known_bundle()
    bundle["markdown"] = "## License / provenance\n\n<p>MI</p><p>T</p>\n"
    report = _report(bundle)
    _assert_schema(report)
    assert "card_disclosure_missing" in report["quarantined"][0]["reason_codes"]
    assert report["released_positives"] == []


def test_visible_html_paragraph_still_discloses():
    bundle = spdx_known_bundle()
    bundle["markdown"] = "## License / provenance\n\n<p>MIT</p>\n"
    report = _report(bundle)
    _assert_schema(report)
    assert report["closed"] is True
    assert report["quarantined"] == []


def test_missing_record_id_cannot_close_under_synthetic_identity():
    bundle = spdx_known_bundle()
    record = dict(bundle["records"][0])
    synthetic = f"{record['repo'].replace('/', '-')}#{record['pr_number']}"
    del record["id"]
    bundle["records"] = [record]
    bundle["manifest"]["records"] = [{"id": synthetic}]
    report = _report(bundle)
    _assert_schema(report)
    assert "declarations_disagree" in report["quarantined"][0]["reason_codes"]
    assert report["released_positives"] == []


def test_non_string_record_id_cannot_close():
    bundle = spdx_known_bundle()
    record = dict(bundle["records"][0])
    record["id"] = 1
    bundle["records"] = [record]
    report = _report(bundle)
    _assert_schema(report)
    assert "declarations_disagree" in report["quarantined"][0]["reason_codes"]
    assert report["released_positives"] == []


def test_multiline_reference_destination_is_not_disclosure():
    bundle = spdx_known_bundle()
    bundle["markdown"] = "## License / provenance\n\n[source]:\n /url/MIT\n"
    report = _report(bundle)
    _assert_schema(report)
    assert "card_disclosure_missing" in report["quarantined"][0]["reason_codes"]
    assert report["released_positives"] == []


def test_duplicate_record_ids_keep_snapshot_provenance():
    bundle = spdx_known_bundle()
    source_hash = bundle["repositories"][0]["source_hash"]
    bundle["records"].append(dict(bundle["records"][0]))
    report = _report(bundle)
    _assert_schema(report)
    assert report["released_positives"] == []
    assert all(
        row["evidence"]["snapshot_sha256"] == SNAPSHOT_SHA256
        and row["evidence"]["repository_source_hash"] == source_hash
        for row in report["quarantined"]
    )
