"""Codex P13 fail-closed holes against the current license-closure HEAD."""

from __future__ import annotations

import json
from pathlib import Path

from build_manifest import main as build_manifest_main
from license_closure_fixtures import MERGE_OID, inventory_pr, spdx_known_bundle
from license_closure_helpers import (
    _assert_schema,
    _cli_argv,
    _report,
    _write_cli_bundle,
)
from validate_license_closure import main as license_closure_main


def test_integer_top_level_repo_cannot_close_via_nested_identity():
    bundle = spdx_known_bundle()
    bundle["records"][0]["repo"] = 7
    bundle["records"][0]["repository"] = {"owner": "rmems", "name": "widget"}
    report = _report(bundle)
    _assert_schema(report)
    assert "declarations_disagree" in report["quarantined"][0]["reason_codes"]
    assert report["released_positives"] == []


def test_truncated_inventory_oids_cannot_close_on_merge_match():
    bundle = spdx_known_bundle()
    bundle["records"][0]["repository"] = {"commit_oid": MERGE_OID}
    bundle["pull_requests"] = [
        inventory_pr(
            "rmems/widget",
            1,
            base_oid="abc",
            head_oid="def",
            merge_commit_oid=MERGE_OID,
        )
    ]
    report = _report(bundle)
    _assert_schema(report)
    assert "snapshot_provenance_missing" in report["quarantined"][0]["reason_codes"]
    assert report["released_positives"] == []


def test_cli_refuses_out_hardlink_to_frozen_records(tmp_path: Path):
    bundle = spdx_known_bundle()
    paths = _write_cli_bundle(tmp_path, bundle)
    alias = tmp_path / "records-hardlink.jsonl"
    alias.hardlink_to(paths["records"])
    original = paths["records"].read_bytes()
    argv = _cli_argv(paths, "--out", str(alias))
    assert license_closure_main(argv) == 2
    assert paths["records"].read_bytes() == original
    assert alias.read_bytes() == original


def test_build_manifest_rejects_nonfinite_card_fields(tmp_path: Path):
    jsonl = tmp_path / "fixture.jsonl"
    jsonl.write_text(
        json.dumps(
            {
                "id": "rmems-widget-1",
                "pr_number": 1,
                "training_use": "repair",
                "task_type": "bugfix",
                "domain": "tools",
                "language": "Python",
                "quality_score": 0.9,
                "outcome": "merged",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    card = tmp_path / "card.json"
    card.write_text(
        json.dumps(
            {
                "schema_version": "pr_trajectory_v0",
                "source_repo": "rmems/widget",
                "unresolved_license_count": float("nan"),
            }
        ),
        encoding="utf-8",
    )
    manifest = tmp_path / "fixture.manifest.json"
    manifest.write_text(
        json.dumps({"created_at": "2026-01-01", "created_by": "test"}),
        encoding="utf-8",
    )
    assert (
        build_manifest_main(
            [
                "--jsonl",
                str(jsonl),
                "--card",
                str(card),
                "--out",
                str(manifest),
                "--check",
            ]
        )
        == 2
    )
