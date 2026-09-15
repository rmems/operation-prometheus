"""Shared helpers for fail-closed license-closure tests."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import jsonschema

from license_closure_fixtures import report_kwargs
from lib.license_closure import build_license_closure_report

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
    errors = sorted(
        _validator().iter_errors(report), key=lambda error: list(error.path)
    )
    assert not errors, [error.message for error in errors]


def _write_cli_bundle(tmp_path: Path, bundle: dict) -> dict[str, Path]:
    paths = {
        "records": tmp_path / "records.jsonl",
        "card": tmp_path / "card.json",
        "manifest": tmp_path / "manifest.json",
        "inventory": tmp_path / "inventory.jsonl",
        "inventory_manifest": tmp_path / "inventory-manifest.json",
        "out": tmp_path / "closure.json",
    }
    paths["records"].write_text(
        json.dumps(bundle["records"][0]) + "\n", encoding="utf-8"
    )
    paths["card"].write_text(json.dumps(bundle["card"]), encoding="utf-8")
    manifest = dict(bundle["manifest"])
    if not manifest.get("sha256"):
        manifest["sha256"] = hashlib.sha256(paths["records"].read_bytes()).hexdigest()
    paths["manifest"].write_text(json.dumps(manifest), encoding="utf-8")
    paths["inventory"].write_text(
        json.dumps(bundle["repositories"][0]) + "\n", encoding="utf-8"
    )
    paths["inventory_manifest"].write_text(
        json.dumps(
            {
                "files": {
                    paths["inventory"].name: {
                        "sha256": hashlib.sha256(
                            paths["inventory"].read_bytes()
                        ).hexdigest()
                    }
                },
                "snapshot_sha256": bundle["snapshot_sha256"],
            }
        ),
        encoding="utf-8",
    )
    return paths


def _cli_argv(paths: dict[str, Path], *extra: str) -> list[str]:
    return [
        "--records",
        str(paths["records"]),
        "--card",
        str(paths["card"]),
        "--manifest",
        str(paths["manifest"]),
        "--inventory",
        str(paths["inventory"]),
        "--inventory-manifest",
        str(paths["inventory_manifest"]),
        *extra,
    ]
