"""Codex P10 fail-closed holes against the current license-closure HEAD."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from license_closure_fixtures import (
    CUSTOM_TEXT_SHA256,
    bind_source_hash,
    digest_for,
    inventory_alias,
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


def test_cli_duplicate_json_keys_cannot_close(tmp_path: Path):
    bundle = spdx_known_bundle()
    paths = _write_cli_bundle(tmp_path, bundle)
    original = paths["records"].read_text(encoding="utf-8").strip()
    duplicated = original.replace(
        '"license": "MIT"',
        '"license": "GPL-3.0-only", "license": "MIT"',
        1,
    )
    assert duplicated != original
    paths["records"].write_text(duplicated + "\n", encoding="utf-8")
    manifest = json.loads(paths["manifest"].read_text(encoding="utf-8"))
    manifest["sha256"] = hashlib.sha256(paths["records"].read_bytes()).hexdigest()
    paths["manifest"].write_text(json.dumps(manifest), encoding="utf-8")
    assert license_closure_main(_cli_argv(paths, "--out", str(paths["out"]))) == 2


def test_unmatched_custom_license_on_spdx_row_cannot_close():
    bundle = spdx_known_bundle()
    row = dict(bundle["repositories"][0])
    row["custom_license"] = {
        "identifier": "LicenseRef-Other",
        "text_sha256": CUSTOM_TEXT_SHA256,
    }
    bundle["repositories"][0] = bind_source_hash(row)
    digest = digest_for(bundle["repositories"][0])
    bundle["card"]["license_evidence_digest"] = digest
    bundle["manifest"]["license_evidence_digest"] = digest
    report = _report(bundle)
    _assert_schema(report)
    assert "source_license_conflict" in report["quarantined"][0]["reason_codes"]
    assert report["released_positives"] == []
    assert report["quarantined"][0]["evidence"]["custom_license"]["identifier"] == (
        "LicenseRef-Other"
    )


def test_object_license_families_cannot_validate_release():
    report = _report(spdx_known_bundle())
    report["license_families"] = {"spdx": 123}
    report["closed"] = True
    errors = validate_positive_release(report)
    assert errors
    assert any("license_families" in error for error in errors)


def test_object_inventory_aliases_cannot_index():
    bundle = spdx_known_bundle()
    row = dict(bundle["repositories"][0])
    row["aliases"] = {"rmems/other": {}}
    bundle["repositories"][0] = row
    bundle["records"][0]["repo"] = "rmems/other"
    bundle["card"]["source_repo"] = "rmems/other"
    bundle["manifest"]["source_repo"] = "rmems/other"
    with pytest.raises(ValueError, match="aliases"):
        _report(bundle)


def test_array_inventory_aliases_still_close():
    bundle = spdx_known_bundle()
    row = dict(bundle["repositories"][0])
    row["aliases"] = [inventory_alias("rmems/other")]
    bundle["repositories"][0] = bind_source_hash(row)
    bundle["records"][0]["repo"] = "rmems/other"
    bundle["card"]["source_repo"] = "rmems/other"
    bundle["manifest"]["source_repo"] = "rmems/other"
    report = _report(bundle)
    _assert_schema(report)
    assert report["closed"] is True
    assert report["released_positives"]


def test_escaped_reference_definition_label_is_not_disclosure():
    bundle = spdx_known_bundle()
    bundle["markdown"] = (
        "## License / provenance\n\n[license\\]]: https://example.test/MIT\n"
    )
    report = _report(bundle)
    _assert_schema(report)
    assert "card_disclosure_missing" in report["quarantined"][0]["reason_codes"]
    assert report["released_positives"] == []
