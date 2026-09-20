"""Codex P8 fail-closed holes against the current license-closure HEAD."""

from __future__ import annotations

from pathlib import Path

import pytest

from license_closure_fixtures import spdx_known_bundle
from license_closure_helpers import (
    _assert_schema,
    _cli_argv,
    _report,
    _write_cli_bundle,
)
from lib.license_closure import (
    evidence_digest,
    license_evidence_payload,
    source_provenance_digest,
    validate_positive_release,
)
from validate_license_closure import main as license_closure_main


def test_non_object_trajectory_row_cannot_build_report():
    bundle = spdx_known_bundle()
    bundle["records"].append("not-a-row")
    with pytest.raises(ValueError, match="trajectory records must be objects"):
        _report(bundle)


def test_nested_markdown_link_label_destination_is_not_disclosure():
    bundle = spdx_known_bundle()
    bundle["markdown"] = (
        "## License / provenance\n\n[details [nested]](https://example.test/MIT)\n"
    )
    report = _report(bundle)
    _assert_schema(report)
    assert "card_disclosure_missing" in report["quarantined"][0]["reason_codes"]
    assert report["released_positives"] == []


def test_swapped_license_evidence_without_provenance_cannot_validate():
    report = _report(spdx_known_bundle())
    released = report["released_positives"][0]
    inventory = dict(released["inventory_license"])
    inventory["spdx_id"] = "Apache-2.0"
    released["inventory_license"] = inventory
    released["spdx_id"] = "Apache-2.0"
    digest = evidence_digest(
        license_evidence_payload(
            {
                "custom_license": released.get("custom_license"),
                "license": inventory,
            }
        )
    )
    released["evidence_digest"] = digest
    report["evidence_digests"][0]["digest"] = digest
    report["evidence_digests"][0]["spdx_id"] = "Apache-2.0"
    errors = validate_positive_release(report)
    assert errors
    assert any("license family" in error for error in errors)


@pytest.mark.parametrize("pr_number", [0, -1])
def test_non_positive_released_pr_number_cannot_validate(pr_number):
    report = _report(spdx_known_bundle())
    row = report["released_positives"][0]
    row["pr_number"] = pr_number
    row["source_provenance_digest"] = source_provenance_digest(
        row["repo"],
        row["repository_source_hash"],
        row["snapshot_sha256"],
        {
            "record_id": row["record_id"],
            "pr_number": pr_number,
            "evidence_digest": row["evidence_digest"],
        },
    )
    errors = validate_positive_release(report)
    assert errors
    assert any("value types" in error for error in errors)


def test_cli_refuses_out_overwrite_of_frozen_records(tmp_path: Path):
    bundle = spdx_known_bundle()
    paths = _write_cli_bundle(tmp_path, bundle)
    original = paths["records"].read_bytes()
    argv = _cli_argv(paths, "--out", str(paths["records"]))
    assert license_closure_main(argv) == 2
    assert paths["records"].read_bytes() == original


def test_cli_refuses_out_symlink_to_frozen_records(tmp_path: Path):
    bundle = spdx_known_bundle()
    paths = _write_cli_bundle(tmp_path, bundle)
    alias = tmp_path / "records-alias.jsonl"
    alias.symlink_to(paths["records"])
    original = paths["records"].read_bytes()
    argv = _cli_argv(paths, "--out", str(alias))
    assert license_closure_main(argv) == 2
    assert paths["records"].read_bytes() == original
    assert alias.read_bytes() == original


def test_cli_check_refuses_out_overwrite_of_frozen_records(tmp_path: Path):
    bundle = spdx_known_bundle()
    paths = _write_cli_bundle(tmp_path, bundle)
    original = paths["records"].read_bytes()
    argv = _cli_argv(paths, "--out", str(paths["records"]), "--check")
    assert license_closure_main(argv) == 2
    assert paths["records"].read_bytes() == original
