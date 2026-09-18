"""Codex P6 fail-closed holes against the current license-closure HEAD."""

from __future__ import annotations

import pytest

from license_closure_fixtures import (
    STALE_DIGEST,
    mixed_repository_bundle,
    spdx_known_bundle,
)
from license_closure_helpers import _assert_schema, _report


def test_unused_declared_repo_must_match_inventory_license():
    bundle = mixed_repository_bundle()
    bundle["records"] = [bundle["records"][0]]
    bundle["card"]["source_licenses"] = dict(bundle["card"]["source_licenses"])
    bundle["manifest"]["source_licenses"] = dict(bundle["manifest"]["source_licenses"])
    bundle["card"]["license_evidence_digests"] = dict(
        bundle["card"]["license_evidence_digests"]
    )
    bundle["manifest"]["license_evidence_digests"] = dict(
        bundle["manifest"]["license_evidence_digests"]
    )
    unused = "Limen-Neural/axon-encoder"
    bundle["card"]["source_licenses"][unused] = "GPL-3.0-only"
    bundle["manifest"]["source_licenses"][unused] = "GPL-3.0-only"
    bundle["card"]["license_evidence_digests"][unused] = STALE_DIGEST
    bundle["manifest"]["license_evidence_digests"][unused] = STALE_DIGEST
    report = _report(bundle)
    _assert_schema(report)
    assert "declarations_disagree" in report["quarantined"][0]["reason_codes"]
    assert report["released_positives"] == []


def test_setext_h1_after_license_section_is_not_disclosure():
    bundle = spdx_known_bundle()
    bundle["markdown"] = (
        "## License / provenance\n\nNo license\nAppendix\n========\nMIT\n"
    )
    report = _report(bundle)
    _assert_schema(report)
    assert "card_disclosure_missing" in report["quarantined"][0]["reason_codes"]
    assert report["released_positives"] == []


def test_setext_h2_after_license_section_is_not_disclosure():
    bundle = spdx_known_bundle()
    bundle["markdown"] = (
        "## License / provenance\n\nNo license\nAppendix\n--------\nMIT\n"
    )
    report = _report(bundle)
    _assert_schema(report)
    assert "card_disclosure_missing" in report["quarantined"][0]["reason_codes"]
    assert report["released_positives"] == []


def test_visible_mit_before_setext_heading_still_discloses():
    bundle = spdx_known_bundle()
    bundle["markdown"] = "## License / provenance\n\nMIT\nAppendix\n========\nLater\n"
    report = _report(bundle)
    _assert_schema(report)
    assert report["closed"] is True
    assert report["released_positives"]


def test_malformed_repository_inventory_row_is_rejected():
    bundle = spdx_known_bundle()
    bundle["repositories"].append({})
    with pytest.raises(ValueError, match="repository inventory"):
        _report(bundle)
