"""CLI, extract, and disclosure tests for license-closure validation."""

from __future__ import annotations

import json
from pathlib import Path

import jsonschema
import pytest

from license_closure_fixtures import (
    STALE_DIGEST,
    missing_license_bundle,
    mixed_repository_bundle,
    report_kwargs,
    spdx_known_bundle,
)
from license_closure_helpers import (
    ROOT,
    V0_SCHEMA,
    V1_SCHEMA,
    _assert_schema,
    _report,
    _write_cli_bundle,
)
from lib.license_closure import (
    SCHEMA_VERSION,
    assert_released_positives_are_closed,
    build_license_closure_report,
    released_positive_ids,
)
from validate_jsonl import load_schema, validate_file
from validate_license_closure import main as license_closure_main

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
        markdown_card=(
            ROOT / "datasets/cards/corinth-canal-trajectories-v0.md"
        ).read_text(),
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
        == 0
    )
    saved = json.loads(paths["out"].read_text(encoding="utf-8"))
    assert saved["schema_version"] == SCHEMA_VERSION
    assert saved["closed"] is True

    missing = missing_license_bundle()
    paths = _write_cli_bundle(tmp_path, missing)
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


def test_identifier_outside_license_section_does_not_disclose():
    bundle = spdx_known_bundle()
    bundle["markdown"] = (
        "## License / provenance\n\nUnresolved.\n\n## Dependencies\n\nMIT licensed helper.\n"
    )
    report = _report(bundle)
    assert "card_disclosure_missing" in report["quarantined"][0]["reason_codes"]
    assert report["released_positives"] == []


def test_markdown_prefix_identifier_does_not_disclose():
    bundle = spdx_known_bundle()
    bundle["markdown"] = "## License / provenance\n\n- Source license: MIT-0\n"
    report = _report(bundle)
    assert "card_disclosure_missing" in report["quarantined"][0]["reason_codes"]
    assert report["released_positives"] == []


def test_singular_and_mapped_license_disagreement_blocks_release():
    bundle = spdx_known_bundle()
    bundle["card"]["source_license"] = "Apache-2.0"
    bundle["card"]["source_licenses"] = {"rmems/widget": "MIT"}
    report = _report(bundle)
    _assert_schema(report)
    assert "declarations_disagree" in report["quarantined"][0]["reason_codes"]
    assert report["released_positives"] == []


def test_singular_and_mapped_digest_disagreement_blocks_release():
    bundle = spdx_known_bundle()
    digest = bundle["card"]["license_evidence_digest"]
    bundle["card"]["license_evidence_digest"] = STALE_DIGEST
    bundle["card"]["license_evidence_digests"] = {"rmems/widget": digest}
    report = _report(bundle)
    _assert_schema(report)
    assert "declarations_disagree" in report["quarantined"][0]["reason_codes"]
    assert report["released_positives"] == []


def test_card_license_map_is_case_insensitive():
    bundle = mixed_repository_bundle()
    bundle["records"][1]["repo"] = "limen-neural/axon-encoder"
    report = _report(bundle)
    assert report["closed"] is True
    ids = released_positive_ids(report)
    assert "Limen-Neural-axon-encoder-37" in ids


def test_manifest_must_name_the_record_repository():
    bundle = spdx_known_bundle()
    bundle["manifest"]["source_repo"] = "rmems/other"
    report = _report(bundle)
    assert "declarations_disagree" in report["quarantined"][0]["reason_codes"]
    assert report["released_positives"] == []


def test_duplicate_record_ids_are_quarantined():
    bundle = spdx_known_bundle()
    bundle["records"].append(dict(bundle["records"][0]))
    report = _report(bundle)
    _assert_schema(report)
    assert_released_positives_are_closed(report)
    assert report["released_positives"] == []
    assert report["counts"]["quarantined_count"] == 2
    assert all(
        "source_license_unresolved" in row["reason_codes"]
        for row in report["quarantined"]
    )


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
