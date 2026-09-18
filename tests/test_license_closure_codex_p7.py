"""Codex P7 fail-closed holes against the current license-closure HEAD."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from license_closure_fixtures import (
    STALE_DIGEST,
    bind_source_hash,
    custom_license_bundle,
    digest_for,
    spdx_known_bundle,
)
from license_closure_helpers import (
    _assert_schema,
    _cli_argv,
    _report,
    _write_cli_bundle,
)
from lib.license_closure import validate_positive_release
from validate_license_closure import main as license_closure_main


@pytest.mark.parametrize("bundle_errors", [None, {}])
def test_missing_or_object_bundle_errors_cannot_validate_release(bundle_errors):
    report = _report(spdx_known_bundle())
    if bundle_errors is None:
        del report["bundle_errors"]
    else:
        report["bundle_errors"] = bundle_errors
    report["closed"] = True
    errors = validate_positive_release(report)
    assert errors
    assert any("bundle_errors" in error for error in errors)


@pytest.mark.parametrize("pr_number", [True, 0, "7"])
def test_present_invalid_record_pr_number_cannot_close(pr_number):
    bundle = spdx_known_bundle()
    bundle["records"][0]["pr_number"] = pr_number
    report = _report(bundle)
    _assert_schema(report)
    assert "declarations_disagree" in report["quarantined"][0]["reason_codes"]
    assert report["released_positives"] == []
    assert report["quarantined"][0]["pr_number"] is None


def test_cli_rejects_nonfinite_inventory_jsonl(tmp_path: Path):
    bundle = spdx_known_bundle()
    paths = _write_cli_bundle(tmp_path, bundle)
    row = json.loads(paths["inventory"].read_text(encoding="utf-8"))
    row["custom_license"] = {"identifier": "LicenseRef-X", "text_sha256": float("nan")}
    paths["inventory"].write_text(json.dumps(row) + "\n", encoding="utf-8")
    assert license_closure_main(_cli_argv(paths)) == 2


def test_conflicting_custom_evidence_digests_cannot_close():
    bundle = custom_license_bundle()
    row = dict(bundle["repositories"][0])
    custom = dict(row["custom_license"])
    custom["evidence_sha256"] = STALE_DIGEST
    row["custom_license"] = custom
    row = bind_source_hash(row)
    digest = digest_for(row)
    bundle["repositories"] = [row]
    bundle["card"]["license_evidence_digest"] = digest
    bundle["manifest"]["license_evidence_digest"] = digest
    report = _report(bundle)
    _assert_schema(report)
    assert report["released_positives"] == []
    assert report["quarantined"]
