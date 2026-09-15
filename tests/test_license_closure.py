"""Fail-closed license-closure validation before positive corpus release."""

from __future__ import annotations

import json
from pathlib import Path

import jsonschema
import pytest

from license_closure_fixtures import (
    apache_source_bundle,
    changed_license_bundle,
    conflicting_card_manifest_bundle,
    conflicting_card_manifest_digest_bundle,
    custom_license_bundle,
    forge_substitution_bundle,
    missing_license_bundle,
    mixed_repository_bundle,
    report_kwargs,
    spdx_known_bundle,
    stale_digest_bundle,
    unknown_license_bundle,
)
from lib.eligibility_render import render_json
from lib.license_closure import (
    SCHEMA_VERSION,
    assert_released_positives_are_closed,
    build_license_closure_report,
    classify_license_family,
    released_positive_ids,
    validate_positive_release,
)
from validate_jsonl import load_schema, validate_file
from validate_license_closure import main as license_closure_main

ROOT = Path(__file__).resolve().parents[1]
SCHEMA = ROOT / "schemas" / "license_closure.schema.json"
V0_SCHEMA = ROOT / "schemas" / "pr_trajectory.schema.json"
V1_SCHEMA = ROOT / "schemas" / "trajectory_v1.schema.json"


def _validator():
    return jsonschema.Draft7Validator(
        json.loads(SCHEMA.read_text(encoding="utf-8")),
        format_checker=jsonschema.Draft7Validator.FORMAT_CHECKER,
    )


def _report(bundle: dict) -> dict:
    return build_license_closure_report(**report_kwargs(bundle))


def _assert_schema(report: dict) -> None:
    errors = sorted(_validator().iter_errors(report), key=lambda error: list(error.path))
    assert not errors, [error.message for error in errors]


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
    assert classify_license_family("LicenseRef-TemporalFocus") == "custom"
    assert classify_license_family("NOASSERTION") == "unknown"
    assert classify_license_family("Not-A-Real-License-1.0") == "unknown"
    assert classify_license_family(None) == "missing"


def test_existing_v0_extracts_cannot_publish_as_positives():
    records = [
        json.loads(line)
        for line in (ROOT / "datasets/jsonl/corinth-canal-v0.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
        if line.strip()
    ]
    card = json.loads((ROOT / "datasets/cards/corinth-canal-v0.json").read_text())
    manifest = json.loads(
        (ROOT / "datasets/manifests/corinth-canal-v0.manifest.json").read_text()
    )
    repositories = [
        json.loads(line)
        for line in (ROOT / "datasets/inventory/v0.7/repositories.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
        if line.strip()
    ]
    inventory_manifest = json.loads(
        (ROOT / "datasets/inventory/v0.7/manifest.json").read_text()
    )
    report = build_license_closure_report(
        records,
        card,
        manifest,
        repositories,
        snapshot_sha256=inventory_manifest["snapshot_sha256"],
        markdown_card=(ROOT / "datasets/cards/corinth-canal-trajectories-v0.md").read_text(),
    )
    _assert_schema(report)
    assert_released_positives_are_closed(report)
    assert report["counts"]["released_positive_count"] == 0
    assert report["counts"]["unresolved_count"] == len(records)
    assert report["released_positives"] == []
    assert all(row["evidence"] for row in report["quarantined"])
    assert all(row["reason_codes"] for row in report["quarantined"])


def test_strict_policy_still_accepts_existing_jsonl():
    v0 = jsonschema.Draft7Validator(
        load_schema(V0_SCHEMA),
        format_checker=jsonschema.Draft7Validator.FORMAT_CHECKER,
    )
    v1 = jsonschema.Draft7Validator(
        load_schema(V1_SCHEMA),
        format_checker=jsonschema.Draft7Validator.FORMAT_CHECKER,
    )
    errors = validate_file(
        ROOT / "datasets/jsonl/limen-axon-encoder-v0.jsonl",
        v0,
        v1,
        strict_policy=True,
    )
    assert errors == []


def test_cli_writes_manifest_and_fails_closed(tmp_path: Path):
    bundle = spdx_known_bundle()
    records_path = tmp_path / "records.jsonl"
    records_path.write_text(
        json.dumps(bundle["records"][0]) + "\n",
        encoding="utf-8",
    )
    card_path = tmp_path / "card.json"
    card_path.write_text(json.dumps(bundle["card"]), encoding="utf-8")
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(json.dumps(bundle["manifest"]), encoding="utf-8")
    inventory_path = tmp_path / "inventory.jsonl"
    inventory_path.write_text(json.dumps(bundle["repositories"][0]) + "\n", encoding="utf-8")
    out_path = tmp_path / "closure.json"
    assert (
        license_closure_main(
            [
                "--records",
                str(records_path),
                "--card",
                str(card_path),
                "--manifest",
                str(manifest_path),
                "--inventory",
                str(inventory_path),
                "--snapshot-sha256",
                bundle["snapshot_sha256"],
                "--out",
                str(out_path),
            ]
        )
        == 0
    )
    saved = json.loads(out_path.read_text(encoding="utf-8"))
    assert saved["schema_version"] == SCHEMA_VERSION
    assert saved["closed"] is True

    missing = missing_license_bundle()
    records_path.write_text(json.dumps(missing["records"][0]) + "\n", encoding="utf-8")
    card_path.write_text(json.dumps(missing["card"]), encoding="utf-8")
    manifest_path.write_text(json.dumps(missing["manifest"]), encoding="utf-8")
    inventory_path.write_text(json.dumps(missing["repositories"][0]) + "\n", encoding="utf-8")
    assert (
        license_closure_main(
            [
                "--records",
                str(records_path),
                "--card",
                str(card_path),
                "--manifest",
                str(manifest_path),
                "--inventory",
                str(inventory_path),
                "--snapshot-sha256",
                missing["snapshot_sha256"],
            ]
        )
        == 1
    )


def test_module_does_not_import_network_clients():
    import lib.license_closure as module

    assert "github_client" not in dir(module)
    assert "urllib" not in module.__dict__
    assert "requests" not in module.__dict__


def test_missing_markdown_section_blocks_when_card_is_supplied():
    bundle = spdx_known_bundle()
    bundle["markdown"] = "# Dataset card\n\nNo license section here.\n"
    report = _report(bundle)
    assert "card_disclosure_missing" in report["quarantined"][0]["reason_codes"]
    assert report["released_positives"] == []


def test_snapshot_sha256_must_be_frozen_hex():
    bundle = spdx_known_bundle()
    with pytest.raises(ValueError, match="snapshot_sha256"):
        build_license_closure_report(
            **{**report_kwargs(bundle), "snapshot_sha256": "not-a-digest"}
        )
