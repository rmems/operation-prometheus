"""Codex P15 fail-closed holes against the current license-closure HEAD."""

from __future__ import annotations

import json
from pathlib import Path

from license_closure_fixtures import SNAPSHOT_SHA256, spdx_known_bundle
from license_closure_helpers import (
    _assert_schema,
    _cli_argv,
    _report,
    _write_cli_bundle,
)
from validate_license_closure import main as license_closure_main


def test_code_span_cannot_close_hidden_html_scope():
    bundle = spdx_known_bundle()
    bundle["markdown"] = "## License / provenance\n\n<span hidden>`</span>`MIT</span>\n"
    report = _report(bundle)
    _assert_schema(report)
    assert "card_disclosure_missing" in report["quarantined"][0]["reason_codes"]
    assert report["released_positives"] == []


def test_nested_image_destination_is_not_disclosure():
    bundle = spdx_known_bundle()
    bundle["markdown"] = (
        "## License / provenance\n\n"
        "[![details](https://example.test/MIT)](https://outer.test)\n"
    )
    report = _report(bundle)
    _assert_schema(report)
    assert "card_disclosure_missing" in report["quarantined"][0]["reason_codes"]
    assert report["released_positives"] == []


def test_malformed_nested_repository_identity_cannot_close():
    bundle = spdx_known_bundle()
    record = dict(bundle["records"][0])
    record["repository"] = {"owner": 7, "name": "widget"}
    bundle["records"] = [record]
    report = _report(bundle)
    _assert_schema(report)
    assert "declarations_disagree" in report["quarantined"][0]["reason_codes"]
    assert report["released_positives"] == []


def test_cli_requires_inventory_manifest_snapshot_digest(tmp_path: Path):
    bundle = spdx_known_bundle()
    paths = _write_cli_bundle(tmp_path, bundle)
    payload = json.loads(paths["inventory_manifest"].read_text(encoding="utf-8"))
    del payload["snapshot_sha256"]
    paths["inventory_manifest"].write_text(json.dumps(payload), encoding="utf-8")
    argv = _cli_argv(
        paths,
        "--snapshot-sha256",
        SNAPSHOT_SHA256,
        "--out",
        str(paths["out"]),
    )
    assert license_closure_main(argv) == 2
    assert not paths["out"].exists()
