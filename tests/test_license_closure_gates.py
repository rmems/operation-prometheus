"""Fail-closed publication gates for license-closure validation."""

from __future__ import annotations

import json
from pathlib import Path

from license_closure_fixtures import (
    WRONG_HEAD_OID,
    digest_for,
    inventory_pr,
    missing_license_bundle,
    repository,
    spdx_known_bundle,
    with_code_state,
)
from license_closure_helpers import _assert_schema, _report, _write_cli_bundle
from lib.license_closure import validate_positive_release
from validate_license_closure import main as license_closure_main


def test_cli_rejects_conflicting_snapshot_digests(tmp_path: Path):
    bundle = spdx_known_bundle()
    paths = _write_cli_bundle(tmp_path, bundle)
    inventory_manifest = tmp_path / "inventory-manifest.json"
    inventory_manifest.write_text(
        json.dumps({"snapshot_sha256": "f" * 64, "files": {}}),
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
                "--snapshot-sha256",
                bundle["snapshot_sha256"],
            ]
        )
        == 2
    )


def test_cli_writes_failed_bindings_as_unclosed(tmp_path: Path):
    bundle = spdx_known_bundle()
    bundle["manifest"]["sha256"] = "e" * 64
    paths = _write_cli_bundle(tmp_path, bundle)
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
                "--snapshot-sha256",
                bundle["snapshot_sha256"],
                "--out",
                str(paths["out"]),
            ]
        )
        == 1
    )
    saved = json.loads(paths["out"].read_text(encoding="utf-8"))
    assert saved["closed"] is False
    assert saved["bundle_errors"]
    assert any("sha256 does not match" in error for error in saved["bundle_errors"])


def test_cli_rejects_missing_dataset_manifest_digest(tmp_path: Path):
    bundle = spdx_known_bundle()
    paths = _write_cli_bundle(tmp_path, bundle)
    manifest = json.loads(paths["manifest"].read_text(encoding="utf-8"))
    manifest.pop("sha256", None)
    paths["manifest"].write_text(json.dumps(manifest), encoding="utf-8")
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
                "--snapshot-sha256",
                bundle["snapshot_sha256"],
                "--out",
                str(paths["out"]),
            ]
        )
        == 1
    )
    saved = json.loads(paths["out"].read_text(encoding="utf-8"))
    assert saved["closed"] is False
    assert any("missing or malformed" in error for error in saved["bundle_errors"])


def test_prior_inventory_rename_does_not_look_like_license_change():
    bundle = spdx_known_bundle()
    current = dict(bundle["repositories"][0])
    current["name_with_owner"] = "rmems/widget-renamed"
    current["aliases"] = [{"name_with_owner": "rmems/widget"}]
    bundle["repositories"] = [current]
    bundle["prior_repositories"] = [
        repository(
            "rmems/widget",
            spdx_id="MIT",
            license_name="MIT License",
            url="https://api.github.com/licenses/mit",
        )
    ]
    report = _report(bundle)
    _assert_schema(report)
    assert report["closed"] is True
    assert report["released_positives"][0]["record_id"] == "rmems-widget-1"


def test_casefold_duplicate_license_map_blocks_release():
    bundle = spdx_known_bundle()
    del bundle["card"]["source_license"]
    bundle["card"]["source_licenses"] = {
        "RMEMS/widget": "Apache-2.0",
        "rmems/widget": "MIT",
    }
    report = _report(bundle)
    _assert_schema(report)
    assert "declarations_disagree" in report["quarantined"][0]["reason_codes"]
    assert report["released_positives"] == []


def test_supplied_pr_inventory_must_include_the_record():
    bundle = spdx_known_bundle()
    bundle["records"][0] = with_code_state(bundle["records"][0])
    bundle["pull_requests"] = [inventory_pr("rmems/other", 99)]
    report = _report(bundle)
    _assert_schema(report)
    assert "snapshot_provenance_missing" in report["quarantined"][0]["reason_codes"]
    assert report["released_positives"] == []


def test_empty_pr_inventory_quarantines_every_record():
    bundle = spdx_known_bundle()
    bundle["records"][0] = with_code_state(bundle["records"][0])
    bundle["pull_requests"] = []
    report = _report(bundle)
    assert "snapshot_provenance_missing" in report["quarantined"][0]["reason_codes"]
    assert report["released_positives"] == []


def test_matching_pr_oids_by_role_still_close():
    bundle = spdx_known_bundle()
    bundle["records"][0] = with_code_state(bundle["records"][0])
    bundle["pull_requests"] = [inventory_pr("rmems/widget", 1)]
    report = _report(bundle)
    _assert_schema(report)
    assert report["closed"] is True
    assert report["released_positives"][0]["record_id"] == "rmems-widget-1"


def test_wrong_head_oid_is_not_masked_by_matching_base():
    bundle = spdx_known_bundle()
    bundle["records"][0] = with_code_state(
        bundle["records"][0], head_oid=WRONG_HEAD_OID
    )
    bundle["pull_requests"] = [inventory_pr("rmems/widget", 1)]
    report = _report(bundle)
    assert "snapshot_provenance_missing" in report["quarantined"][0]["reason_codes"]
    assert report["released_positives"] == []


def test_distinct_tree_oid_does_not_block_matching_pr():
    bundle = spdx_known_bundle()
    bundle["records"][0] = with_code_state(bundle["records"][0])
    bundle["records"][0]["repository"]["tree_oid"] = "5" * 40
    bundle["pull_requests"] = [inventory_pr("rmems/widget", 1)]
    report = _report(bundle)
    _assert_schema(report)
    assert report["closed"] is True
    assert report["released_positives"][0]["record_id"] == "rmems-widget-1"


def test_malformed_declared_digest_cannot_close():
    bundle = spdx_known_bundle()
    bundle["card"]["license_evidence_digest"] = "not-a-digest"
    bundle["manifest"]["license_evidence_digest"] = "not-a-digest"
    report = _report(bundle)
    _assert_schema(report)
    assert "declarations_disagree" in report["quarantined"][0]["reason_codes"]
    assert report["released_positives"] == []


def test_malformed_mapped_digest_cannot_close():
    bundle = spdx_known_bundle()
    del bundle["card"]["license_evidence_digest"]
    del bundle["manifest"]["license_evidence_digest"]
    bundle["card"]["license_evidence_digests"] = {"rmems/widget": "not-a-digest"}
    bundle["manifest"]["license_evidence_digests"] = {"rmems/widget": "not-a-digest"}
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
    assert report["released_positives"][0]["record_id"] == "rmems-widget-1"


def test_validate_positive_release_uses_quarantined_rows_not_declared_counts():
    report = _report(missing_license_bundle())
    report["counts"]["unresolved_count"] = 0
    report["counts"]["quarantined_count"] = 0
    report["closed"] = True
    errors = validate_positive_release(report)
    assert errors
    assert any("unresolved" in error.lower() for error in errors)


def test_unbalanced_spdx_parentheses_cannot_close():
    bundle = spdx_known_bundle()
    malformed = "(MIT"
    repo = dict(bundle["repositories"][0])
    license_obj = dict(repo["license"])
    license_obj["spdx_id"] = malformed
    repo["license"] = license_obj
    digest = digest_for(repo)
    bundle["repositories"] = [repo]
    bundle["records"][0]["license"] = malformed
    bundle["card"]["source_license"] = malformed
    bundle["card"]["license_evidence_digest"] = digest
    bundle["manifest"]["source_license"] = malformed
    bundle["manifest"]["license_evidence_digest"] = digest
    bundle["markdown"] = "## License / provenance\n\n(MIT\n"
    report = _report(bundle)
    _assert_schema(report)
    assert "source_license_unknown" in report["quarantined"][0]["reason_codes"]
    assert report["released_positives"] == []
