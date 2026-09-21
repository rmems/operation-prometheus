"""Shared imports and helpers for Hermes normalizer tests."""

from __future__ import annotations

import json
import time
from pathlib import Path

import jsonschema
import pytest

from hermes_fixtures import (
    ADMISSION_FIXTURE,
    BASE_OID,
    HEAD_OID,
    ROOT,
    SYNTHETIC_GITHUB_TOKEN,
    VERIFIER_ARTIFACT,
    cli_args,
    default_admission,
    default_verifier,
    hermes_record,
    seal_admission,
    sha256_bytes,
    write_fixture_scenario,
    write_json,
    write_scenario,
)
from lib.hermes_normalize import LocalFileBoundary, canonical_dumps, normalize_files
from lib.hermes_sanitize import strip_hidden_reasoning
from normalize_hermes_trajectories import build_parser, main
from validate_jsonl import load_schema, validate_file

V1_1_SCHEMA = ROOT / "schemas" / "trajectory_v1_1.schema.json"
V0_SCHEMA = ROOT / "schemas" / "pr_trajectory.schema.json"
V1_SCHEMA = ROOT / "schemas" / "trajectory_v1.schema.json"

__all__ = [
    "ADMISSION_FIXTURE",
    "BASE_OID",
    "HEAD_OID",
    "LocalFileBoundary",
    "Path",
    "ROOT",
    "SYNTHETIC_GITHUB_TOKEN",
    "V0_SCHEMA",
    "V1_1_SCHEMA",
    "V1_SCHEMA",
    "VERIFIER_ARTIFACT",
    "_load_jsonl",
    "_report",
    "_run",
    "_scenario_from_fixture",
    "build_parser",
    "canonical_dumps",
    "default_admission",
    "default_verifier",
    "hermes_record",
    "json",
    "jsonschema",
    "load_schema",
    "normalize_files",
    "pytest",
    "seal_admission",
    "sha256_bytes",
    "strip_hidden_reasoning",
    "time",
    "validate_file",
    "write_json",
    "write_scenario",
]


def _load_jsonl(path: Path) -> list[dict]:
    lines = [line for line in path.read_text(encoding="utf-8").splitlines() if line]
    return [json.loads(line) for line in lines]


def _run(paths: dict[str, Path], extra: list[str] | None = None) -> int:
    argv = cli_args(paths)
    if extra:
        argv.extend(extra)
    return main(argv)


def _scenario_from_fixture(tmp_path: Path, name: str) -> dict[str, Path]:
    return write_fixture_scenario(tmp_path, name)


def _report(paths: dict[str, Path]) -> dict:
    return json.loads(paths["report"].read_text(encoding="utf-8"))
