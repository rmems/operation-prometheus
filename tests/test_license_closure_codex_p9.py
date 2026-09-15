"""Codex P9 fail-closed holes against the current license-closure HEAD."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from license_closure_fixtures import (
    mixed_repository_bundle,
    repository,
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


def test_non_object_counts_cannot_validate_release():
    report = _report(spdx_known_bundle())
    report["counts"] = [1]
    report["closed"] = True
    errors = validate_positive_release(report)
    assert errors
    assert any("counts" in error for error in errors)


def test_conflicting_id_and_trajectory_id_cannot_close():
    bundle = spdx_known_bundle()
    bundle["records"][0]["trajectory_id"] = "other-stable-id"
    report = _report(bundle)
    _assert_schema(report)
    assert "declarations_disagree" in report["quarantined"][0]["reason_codes"]
    assert report["released_positives"] == []


def test_matching_id_and_trajectory_id_still_closes():
    bundle = spdx_known_bundle()
    bundle["records"][0]["trajectory_id"] = bundle["records"][0]["id"]
    report = _report(bundle)
    _assert_schema(report)
    assert report["closed"] is True
    assert report["released_positives"]


def test_unused_declared_repo_without_licenses_cannot_close():
    bundle = mixed_repository_bundle()
    bundle["records"] = [bundle["records"][0]]
    unused = "Limen-Neural/axon-encoder"
    bundle["card"]["source_licenses"] = dict(bundle["card"]["source_licenses"])
    bundle["manifest"]["source_licenses"] = dict(bundle["manifest"]["source_licenses"])
    del bundle["card"]["source_licenses"][unused]
    del bundle["manifest"]["source_licenses"][unused]
    report = _report(bundle)
    _assert_schema(report)
    assert "declarations_disagree" in report["quarantined"][0]["reason_codes"]
    assert report["released_positives"] == []


def test_cli_prior_inventory_requires_manifest_binding(tmp_path: Path):
    bundle = spdx_known_bundle()
    paths = _write_cli_bundle(tmp_path, bundle)
    prior = tmp_path / "prior.jsonl"
    prior.write_bytes(paths["inventory"].read_bytes())
    argv = _cli_argv(paths, "--prior-inventory", str(prior), "--out", str(paths["out"]))
    assert license_closure_main(argv) == 1
    saved = json.loads(paths["out"].read_text(encoding="utf-8"))
    assert saved["closed"] is False
    assert any("file binding" in error for error in saved["bundle_errors"])


def test_cli_bound_matching_prior_inventory_still_closes(tmp_path: Path):
    bundle = spdx_known_bundle()
    paths = _write_cli_bundle(tmp_path, bundle)
    prior = tmp_path / "prior.jsonl"
    prior.write_bytes(paths["inventory"].read_bytes())
    prior_manifest = tmp_path / "prior-manifest.json"
    prior_manifest.write_text(
        json.dumps(
            {
                "files": {
                    prior.name: {
                        "sha256": hashlib.sha256(prior.read_bytes()).hexdigest()
                    }
                },
                "snapshot_sha256": bundle["snapshot_sha256"],
            }
        ),
        encoding="utf-8",
    )
    argv = _cli_argv(
        paths,
        "--prior-inventory",
        str(prior),
        "--prior-inventory-manifest",
        str(prior_manifest),
        "--out",
        str(paths["out"]),
    )
    assert license_closure_main(argv) == 0


def test_cli_unbound_rewritten_prior_inventory_cannot_close(tmp_path: Path):
    bundle = spdx_known_bundle()
    paths = _write_cli_bundle(tmp_path, bundle)
    prior_row = repository(
        "rmems/widget",
        spdx_id="Apache-2.0",
        license_name="Apache License 2.0",
        url="https://api.github.com/licenses/apache-2.0",
    )
    prior = tmp_path / "prior.jsonl"
    prior.write_text(json.dumps(prior_row) + "\n", encoding="utf-8")
    argv = _cli_argv(paths, "--prior-inventory", str(prior), "--out", str(paths["out"]))
    assert license_closure_main(argv) == 1
    saved = json.loads(paths["out"].read_text(encoding="utf-8"))
    assert saved["closed"] is False
    assert any("file binding" in error for error in saved["bundle_errors"])
