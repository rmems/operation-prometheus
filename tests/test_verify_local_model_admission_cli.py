"""CLI tests for scripts/verify_local_model_admission.py (offline fixtures only)."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
CLI = ROOT / "scripts" / "verify_local_model_admission.py"
FIXTURES = ROOT / "tests" / "fixtures" / "local_model_admission"


def _run(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(CLI), *args],
        capture_output=True,
        text=True,
        cwd=ROOT,
    )


def _args(out: Path, admissions: str = "admissions.jsonl") -> list[str]:
    return [
        "--admissions", str(FIXTURES / admissions),
        "--rights", str(FIXTURES / "rights.json"),
        "--probe", str(FIXTURES / "ollama_probe.json"),
        "--out", str(out),
    ]


def test_closed_fixture_run(tmp_path):
    out = tmp_path / "report.json"
    result = _run(*_args(out))
    assert result.returncode == 0, result.stderr
    report = json.loads(out.read_text())
    assert report["schema_version"] == "local_model_admission_v1"
    assert report["closed"] is True
    assert report["counts"]["accepted"] == 1
    assert report["input_digests"]["admissions"]
    assert report["input_digests"]["rights"]
    assert report["input_digests"]["probe"]


def test_quarantined_candidate_exits_1(tmp_path):
    out = tmp_path / "report.json"
    result = _run(*_args(out, admissions="admissions_quarantined.jsonl"))
    assert result.returncode == 1
    report = json.loads(out.read_text())
    assert report["closed"] is False
    assert report["quarantined"][0]["reason_codes"]


def test_rejected_candidate_exits_1(tmp_path):
    out = tmp_path / "report.json"
    result = _run(*_args(out, admissions="admissions_rejected.jsonl"))
    assert result.returncode == 1
    report = json.loads(out.read_text())
    assert report["rejected"][0]["reason_codes"]


def test_check_mode_detects_stale_report(tmp_path):
    out = tmp_path / "report.json"
    assert _run(*_args(out)).returncode == 0
    assert _run(*_args(out), "--check").returncode == 0
    out.write_text("{}")
    assert _run(*_args(out), "--check").returncode == 1


def test_out_colliding_with_input_rejected(tmp_path):
    result = _run(*_args(FIXTURES / "rights.json"))
    assert result.returncode == 2
    assert "collides" in result.stderr


def test_duplicate_json_keys_fail_closed(tmp_path):
    bad = tmp_path / "rights.json"
    bad.write_text('{"models": {}, "models": {}}')
    result = _run(
        "--admissions", str(FIXTURES / "admissions.jsonl"),
        "--rights", str(bad),
        "--probe", str(FIXTURES / "ollama_probe.json"),
        "--out", str(tmp_path / "report.json"),
    )
    assert result.returncode == 2


def test_non_finite_json_rejected(tmp_path):
    bad = tmp_path / "rights.json"
    bad.write_text('{"models": {"x": {"license": "MIT", "terms_sha256": NaN}}}')
    result = _run(
        "--admissions", str(FIXTURES / "admissions.jsonl"),
        "--rights", str(bad),
        "--probe", str(FIXTURES / "ollama_probe.json"),
        "--out", str(tmp_path / "report.json"),
    )
    assert result.returncode == 2


def test_inputs_manifest_mismatch_fails_closed(tmp_path):
    manifest = tmp_path / "inputs-manifest.json"
    manifest.write_text(json.dumps({"files": {"admissions": {"sha256": "0" * 64}}}))
    out = tmp_path / "report.json"
    result = _run(*_args(out), "--inputs-manifest", str(manifest))
    assert result.returncode == 1
    report = json.loads(out.read_text())
    assert report["closed"] is False
    assert report["bundle_errors"]


def test_inputs_manifest_match_binds(tmp_path):
    import hashlib

    manifest = tmp_path / "inputs-manifest.json"
    files = {}
    for name, path in (
        ("admissions", FIXTURES / "admissions.jsonl"),
        ("rights", FIXTURES / "rights.json"),
        ("probe", FIXTURES / "ollama_probe.json"),
    ):
        files[name] = {"sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
    manifest.write_text(json.dumps({"files": files}))
    out = tmp_path / "report.json"
    result = _run(*_args(out), "--inputs-manifest", str(manifest))
    assert result.returncode == 0, result.stderr


def test_report_has_no_nan(tmp_path):
    out = tmp_path / "report.json"
    assert _run(*_args(out)).returncode == 0
    assert "NaN" not in out.read_text()


def test_live_requires_loopback(tmp_path):
    result = _run(
        "--admissions", str(FIXTURES / "admissions.jsonl"),
        "--rights", str(FIXTURES / "rights.json"),
        "--live",
        "--endpoint", "https://example.com",
        "--out", str(tmp_path / "report.json"),
    )
    assert result.returncode == 2
    assert "loopback" in result.stderr
