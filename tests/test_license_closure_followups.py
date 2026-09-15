"""Additional fail-closed holes for license-closure validation."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from license_closure_fixtures import (
    SOURCE_HASH,
    WRONG_HEAD_OID,
    bind_source_hash,
    inventory_pr,
    report_kwargs,
    repository,
    spdx_known_bundle,
    with_code_state,
)
from license_closure_helpers import _assert_schema, _report, _write_cli_bundle
from lib.license_closure import (
    build_license_closure_report,
    classify_license_family,
    validate_positive_release,
)
from validate_license_closure import main as license_closure_main


def test_empty_spdx_operands_are_unknown():
    assert classify_license_family("MIT OR ()") == "unknown"
    assert classify_license_family("() AND MIT") == "unknown"


def test_record_count_must_match_released_and_quarantined_rows():
    report = _report(spdx_known_bundle())
    report["released_positives"] = []
    report["counts"]["released_positive_count"] = 0
    report["counts"]["record_count"] = 1
    report["closed"] = True
    errors = validate_positive_release(report)
    assert errors
    assert any("record count" in error.lower() for error in errors)


def test_duplicate_pr_inventory_keys_are_rejected():
    bundle = spdx_known_bundle()
    bundle["records"][0] = with_code_state(bundle["records"][0])
    bundle["pull_requests"] = [
        inventory_pr("rmems/widget", 1),
        inventory_pr("rmems/widget", 1, head_oid=WRONG_HEAD_OID),
    ]
    with pytest.raises(ValueError, match="Duplicate inventory pull request"):
        _report(bundle)


def test_intermediate_event_commit_does_not_need_to_match_merge():
    bundle = spdx_known_bundle()
    row = with_code_state(bundle["records"][0])
    row["events"] = [{"code_state": {"commit_oid": "6" * 40}}]
    bundle["records"][0] = row
    bundle["pull_requests"] = [inventory_pr("rmems/widget", 1)]
    report = _report(bundle)
    _assert_schema(report)
    assert report["closed"] is True


def test_forward_rename_still_sees_prior_license_change():
    bundle = spdx_known_bundle()
    current = dict(bundle["repositories"][0])
    current["name_with_owner"] = "rmems/widget-renamed"
    current["aliases"] = [{"name_with_owner": "rmems/widget"}]
    bundle["repositories"] = [bind_source_hash(current)]
    bundle["records"][0]["repo"] = "rmems/widget-renamed"
    bundle["card"]["source_repo"] = "rmems/widget-renamed"
    bundle["manifest"]["source_repo"] = "rmems/widget-renamed"
    bundle["prior_repositories"] = [
        repository(
            "rmems/widget",
            spdx_id="Apache-2.0",
            license_name="Apache License 2.0",
            url="https://api.github.com/licenses/apache-2.0",
        )
    ]
    report = _report(bundle)
    _assert_schema(report)
    assert "source_license_changed" in report["quarantined"][0]["reason_codes"]
    assert report["released_positives"] == []


def test_conflicting_record_repo_identities_cannot_close():
    bundle = spdx_known_bundle()
    bundle["records"][0]["repository"] = {"owner": "other", "name": "place"}
    report = _report(bundle)
    _assert_schema(report)
    assert "declarations_disagree" in report["quarantined"][0]["reason_codes"]
    assert report["released_positives"] == []


def test_inventory_alias_claimed_by_two_rows_is_rejected():
    bundle = spdx_known_bundle()
    other = repository(
        "rmems/other",
        spdx_id="MIT",
        license_name="MIT License",
        url="https://api.github.com/licenses/mit",
    )
    other["aliases"] = [{"name_with_owner": "rmems/widget"}]
    bundle["repositories"].append(other)
    with pytest.raises(ValueError, match="Duplicate inventory alias"):
        _report(bundle)


def test_inventory_row_may_repeat_its_own_name_as_alias():
    bundle = spdx_known_bundle()
    row = dict(bundle["repositories"][0])
    row["aliases"] = [{"name_with_owner": "rmems/widget"}]
    bundle["repositories"] = [bind_source_hash(row)]
    report = _report(bundle)
    _assert_schema(report)
    assert report["closed"] is True


def test_uppercase_snapshot_digest_is_emitted_lowercase():
    bundle = spdx_known_bundle()
    report = build_license_closure_report(
        **{
            **report_kwargs(bundle),
            "snapshot_sha256": bundle["snapshot_sha256"].upper(),
        }
    )
    _assert_schema(report)
    assert report["snapshot_sha256"] == bundle["snapshot_sha256"]
    assert report["closed"] is True


def test_fractional_unresolved_count_cannot_close():
    bundle = spdx_known_bundle()
    bundle["manifest"]["unresolved_license_count"] = 0.5
    report = _report(bundle)
    _assert_schema(report)
    assert report["closed"] is False
    assert any("unresolved_license_count" in error for error in report["bundle_errors"])


def test_emptied_evidence_summary_cannot_validate_release():
    report = _report(spdx_known_bundle())
    report["evidence_digests"] = []
    errors = validate_positive_release(report)
    assert errors
    assert any("evidence_digests" in error for error in errors)


def test_cli_requires_inventory_manifest_file_binding(tmp_path: Path):
    bundle = spdx_known_bundle()
    paths = _write_cli_bundle(tmp_path, bundle)
    inventory_manifest = tmp_path / "inventory-manifest.json"
    inventory_manifest.write_text(
        json.dumps({"snapshot_sha256": bundle["snapshot_sha256"]}),
        encoding="utf-8",
    )
    assert (
        license_closure_main(
            [
                "--records",
                str(paths["records"]),
                "--card",
                str(paths["card"]),
                "--manifest",
                str(paths["manifest"]),
                "--inventory",
                str(paths["inventory"]),
                "--inventory-manifest",
                str(inventory_manifest),
                "--out",
                str(paths["out"]),
            ]
        )
        == 1
    )
    saved = json.loads(paths["out"].read_text(encoding="utf-8"))
    assert saved["closed"] is False
    assert any("file binding" in error for error in saved["bundle_errors"])


def test_cli_accepts_bound_inventory_manifest(tmp_path: Path):
    bundle = spdx_known_bundle()
    paths = _write_cli_bundle(tmp_path, bundle)
    digest = hashlib.sha256(paths["inventory"].read_bytes()).hexdigest()
    inventory_manifest = tmp_path / "inventory-manifest.json"
    inventory_manifest.write_text(
        json.dumps(
            {
                "files": {"repositories.jsonl": {"sha256": digest}},
                "snapshot_sha256": bundle["snapshot_sha256"],
            }
        ),
        encoding="utf-8",
    )
    assert (
        license_closure_main(
            [
                "--records",
                str(paths["records"]),
                "--card",
                str(paths["card"]),
                "--manifest",
                str(paths["manifest"]),
                "--inventory",
                str(paths["inventory"]),
                "--inventory-manifest",
                str(inventory_manifest),
            ]
        )
        == 0
    )


def test_duplicate_released_ids_cannot_validate_release():
    report = _report(spdx_known_bundle())
    report["released_positives"].append(dict(report["released_positives"][0]))
    report["counts"]["released_positive_count"] = 2
    report["counts"]["record_count"] = 2
    errors = validate_positive_release(report)
    assert errors
    assert any("unique" in error.lower() for error in errors)


def test_unknown_identifier_labeled_spdx_cannot_validate_release():
    report = _report(spdx_known_bundle())
    report["released_positives"][0]["spdx_id"] = "NOASSERTION"
    report["released_positives"][0]["license_family"] = "spdx"
    report["evidence_digests"][0]["spdx_id"] = "NOASSERTION"
    report["evidence_digests"][0]["family"] = "spdx"
    errors = validate_positive_release(report)
    assert errors
    assert any("license family" in error for error in errors)


def test_with_license_operand_is_unknown():
    assert classify_license_family("MIT WITH Apache-2.0") == "unknown"
    assert classify_license_family("MIT AND Apache-2.0") == "spdx"


def test_empty_manifest_records_cannot_close():
    bundle = spdx_known_bundle()
    bundle["manifest"]["records"] = []
    report = _report(bundle)
    _assert_schema(report)
    assert report["closed"] is False
    assert any("record ids" in error for error in report["bundle_errors"])


def test_stale_inventory_source_hash_cannot_close():
    bundle = spdx_known_bundle()
    row = dict(bundle["repositories"][0])
    row["source_hash"] = SOURCE_HASH
    bundle["repositories"] = [row]
    report = _report(bundle)
    _assert_schema(report)
    assert "snapshot_provenance_missing" in report["quarantined"][0]["reason_codes"]
    assert report["released_positives"] == []
