"""Codex P12 fail-closed holes against the current license-closure HEAD."""

from __future__ import annotations

import pytest

from license_closure_fixtures import CUSTOM_TEXT_SHA256, spdx_known_bundle
from license_closure_helpers import _report
from lib.license_closure import (
    evidence_digest,
    license_evidence_payload,
    source_provenance_digest,
    validate_positive_release,
)


@pytest.mark.parametrize("value", [1, True])
def test_scalar_evidence_digests_cannot_validate_release(value):
    report = _report(spdx_known_bundle())
    report["evidence_digests"] = value
    errors = validate_positive_release(report)
    assert errors
    assert any("evidence_digests" in error for error in errors)


def test_unmatched_custom_on_spdx_released_row_cannot_validate():
    report = _report(spdx_known_bundle())
    row = report["released_positives"][0]
    custom = {"identifier": "LicenseRef-Other", "text_sha256": CUSTOM_TEXT_SHA256}
    row["custom_license"] = custom
    digest = evidence_digest(
        license_evidence_payload(
            {"custom_license": custom, "license": row["inventory_license"]}
        )
    )
    row["evidence_digest"] = digest
    row["source_provenance_digest"] = source_provenance_digest(
        row["repo"],
        row["repository_source_hash"],
        row["snapshot_sha256"],
        {
            "record_id": row["record_id"],
            "pr_number": row["pr_number"],
            "evidence_digest": digest,
        },
    )
    report["evidence_digests"][0]["digest"] = digest
    errors = validate_positive_release(report)
    assert errors
    assert any("license family" in error for error in errors)
