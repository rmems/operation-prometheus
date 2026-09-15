"""Codex P5 fail-closed holes against the current license-closure HEAD."""

from __future__ import annotations

from pathlib import Path

from license_closure_fixtures import bind_source_hash, spdx_known_bundle
from license_closure_helpers import (
    _assert_schema,
    _cli_argv,
    _report,
    _write_cli_bundle,
)
from lib.license_closure import source_provenance_digest, validate_positive_release
from validate_license_closure import main as license_closure_main


def test_private_inventory_visibility_cannot_close():
    bundle = spdx_known_bundle()
    row = dict(bundle["repositories"][0])
    row["visibility"] = "private"
    bundle["repositories"] = [bind_source_hash(row)]
    report = _report(bundle)
    _assert_schema(report)
    assert "snapshot_provenance_missing" in report["quarantined"][0]["reason_codes"]
    assert report["released_positives"] == []


def test_private_prior_inventory_cannot_authenticate_license_history():
    bundle = spdx_known_bundle()
    prior = dict(bundle["repositories"][0])
    prior["visibility"] = "private"
    bundle["prior_repositories"] = [bind_source_hash(prior)]
    report = _report(bundle)
    _assert_schema(report)
    assert "source_license_changed" in report["quarantined"][0]["reason_codes"]
    assert report["released_positives"] == []


def test_integer_released_repo_cannot_validate_release():
    report = _report(spdx_known_bundle())
    row = report["released_positives"][0]
    row["repo"] = 7
    row["source_provenance_digest"] = source_provenance_digest(
        "",
        row["repository_source_hash"],
        row["snapshot_sha256"],
        record_id=row["record_id"],
        pr_number=row["pr_number"],
    )
    report["evidence_digests"][0]["repository"] = 7
    errors = validate_positive_release(report)
    assert errors
    assert any("value types" in error for error in errors)


def test_unhashable_released_repo_cannot_validate_release():
    report = _report(spdx_known_bundle())
    report["released_positives"][0]["repo"] = []
    errors = validate_positive_release(report)
    assert errors
    assert any("value types" in error for error in errors)


def test_cli_hashes_the_bytes_used_to_build_the_report(
    tmp_path: Path, monkeypatch
) -> None:
    bundle = spdx_known_bundle()
    paths = _write_cli_bundle(tmp_path, bundle)
    original = Path.read_bytes
    seen: dict[str, int] = {}

    def read_once_then_poison(self: Path) -> bytes:
        key = str(self.resolve())
        count = seen.get(key, 0)
        seen[key] = count + 1
        data = original(self)
        if count == 0:
            return data
        return b"x" * len(data) if data else b"poison"

    monkeypatch.setattr(Path, "read_bytes", read_once_then_poison)
    assert license_closure_main(_cli_argv(paths, "--out", str(paths["out"]))) == 0
