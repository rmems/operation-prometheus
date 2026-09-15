"""Codex P11 fail-closed holes against the current license-closure HEAD."""

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
from validate_license_closure import main as license_closure_main


def test_atx_closing_hashes_on_license_heading_still_disclose():
    bundle = spdx_known_bundle()
    bundle["markdown"] = "## License / provenance ##\n\nMIT\n"
    report = _report(bundle)
    _assert_schema(report)
    assert report["closed"] is True
    assert report["released_positives"]


def test_object_record_license_cannot_close():
    bundle = spdx_known_bundle()
    bundle["records"][0]["license"] = {"spdx_id": "MIT"}
    report = _report(bundle)
    _assert_schema(report)
    assert report["released_positives"] == []
    assert report["quarantined"]


@pytest.mark.parametrize("artifact", ["card", "manifest"])
def test_cli_non_object_publication_artifact_cannot_close(
    tmp_path: Path, artifact: str
):
    bundle = spdx_known_bundle()
    paths = _write_cli_bundle(tmp_path, bundle)
    paths[artifact].write_text("[]\n", encoding="utf-8")
    assert license_closure_main(_cli_argv(paths, "--out", str(paths["out"]))) == 2


@pytest.mark.parametrize("alias", [{}, 7])
def test_malformed_inventory_alias_entry_cannot_index(alias):
    bundle = spdx_known_bundle()
    row = dict(bundle["repositories"][0])
    row["aliases"] = [alias]
    bundle["repositories"][0] = row
    with pytest.raises(ValueError, match="aliases"):
        _report(bundle)
