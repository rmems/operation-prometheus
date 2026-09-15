"""Codex P16 fail-closed holes against the current license-closure HEAD."""

from __future__ import annotations

import pytest

from license_closure_fixtures import (
    bind_source_hash,
    inventory_alias,
    spdx_known_bundle,
)
from license_closure_helpers import _assert_schema, _report


def test_duplicate_ids_keep_declaration_licenses():
    bundle = spdx_known_bundle()
    bundle["records"].append(dict(bundle["records"][0]))
    report = _report(bundle)
    _assert_schema(report)
    assert report["released_positives"] == []
    assert all(
        row["evidence"]["record_license"] == "MIT"
        and row["evidence"]["card_license"] == "MIT"
        and row["evidence"]["manifest_license"] == "MIT"
        for row in report["quarantined"]
    )


def test_escaped_angle_bracket_destination_is_not_disclosure():
    bundle = spdx_known_bundle()
    bundle["markdown"] = (
        "## License / provenance\n\n[details](<https://example.test/\\> foo MIT>)\n"
    )
    report = _report(bundle)
    _assert_schema(report)
    assert "card_disclosure_missing" in report["quarantined"][0]["reason_codes"]
    assert report["released_positives"] == []


def test_alias_object_without_evidence_refs_cannot_index():
    bundle = spdx_known_bundle()
    row = dict(bundle["repositories"][0])
    row["aliases"] = [{"name_with_owner": "rmems/other"}]
    bundle["repositories"][0] = bind_source_hash(row)
    bundle["records"][0]["repo"] = "rmems/other"
    bundle["card"]["source_repo"] = "rmems/other"
    bundle["manifest"]["source_repo"] = "rmems/other"
    with pytest.raises(ValueError, match="aliases"):
        _report(bundle)


def test_alias_object_with_evidence_refs_still_closes():
    bundle = spdx_known_bundle()
    row = dict(bundle["repositories"][0])
    row["aliases"] = [inventory_alias("rmems/other")]
    bundle["repositories"][0] = bind_source_hash(row)
    bundle["records"][0]["repo"] = "rmems/other"
    bundle["card"]["source_repo"] = "rmems/other"
    bundle["manifest"]["source_repo"] = "rmems/other"
    report = _report(bundle)
    _assert_schema(report)
    assert report["closed"] is True
    assert report["released_positives"]
