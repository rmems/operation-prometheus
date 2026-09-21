"""Normalize verified Hermes traces into trajectory v1.1 (Linear RM-1348)."""

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
    sha256_bytes,
    seal_admission,
    write_json,
    write_scenario,
    write_fixture_scenario,
)
from lib.hermes_normalize import LocalFileBoundary, canonical_dumps, normalize_files
from lib.hermes_sanitize import strip_hidden_reasoning
from normalize_hermes_trajectories import build_parser, main
from validate_jsonl import load_schema, validate_file

V1_1_SCHEMA = ROOT / "schemas" / "trajectory_v1_1.schema.json"
V0_SCHEMA = ROOT / "schemas" / "pr_trajectory.schema.json"
V1_SCHEMA = ROOT / "schemas" / "trajectory_v1.schema.json"


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


def test_accepted_admission_with_reasons_is_rejected(tmp_path: Path):
    admission = default_admission(reasons=["rights_conflict"])
    paths = write_scenario(tmp_path, [hermes_record(run_id="run-reasons")], admission=admission)
    assert _run(paths) == 0
    assert paths["output"].read_text(encoding="utf-8") == ""
    report = _report(paths)
    assert report["accepted_count"] == 0
    assert "admission_reasons" in report["records"][0]["reason_codes"]

def test_runtime_and_probe_conflicts_are_rejected(tmp_path: Path):
    admission = default_admission()
    admission["runtime"]["version"] = "9.9.9"
    admission["runtime"]["endpoint"] = "http://127.0.0.1:1"
    admission["probe"]["endpoint"] = "http://127.0.0.1:2"
    paths = write_scenario(
        tmp_path, [hermes_record(run_id="run-runtime")], admission=admission
    )
    assert _run(paths) == 0
    report = _report(paths)
    assert report["accepted_count"] == 0
    joined = ",".join(report["records"][0]["reason_codes"])
    assert "runtime" in joined or "probe" in joined

def test_provider_config_without_fallback_flag_is_rejected(tmp_path: Path):
    admission = default_admission()
    admission["provider"]["config"].pop("cloud_fallback_allowed")
    paths = write_scenario(
        tmp_path, [hermes_record(run_id="run-fallback")], admission=admission
    )
    assert _run(paths) == 0
    report = _report(paths)
    assert report["accepted_count"] == 0
    assert "cloud_fallback" in report["records"][0]["reason_codes"]

def test_fake_evidence_digest_is_rejected(tmp_path: Path):
    admission = default_admission()
    admission["evidence_digest"] = "f" * 64
    paths = write_scenario(
        tmp_path,
        [hermes_record(run_id="run-digest")],
        admission=admission,
    )
    # write_scenario reseals; overwrite the sealed file with a fake digest.
    stored = json.loads(paths["admission"].read_text(encoding="utf-8"))
    stored["evidence_digest"] = "f" * 64
    write_json(paths["admission"], stored)
    manifest = json.loads(paths["manifest"].read_text(encoding="utf-8"))
    manifest["admission_report_sha256"] = sha256_bytes(paths["admission"].read_bytes())
    write_json(paths["manifest"], manifest)
    assert _run(paths) == 0
    report = _report(paths)
    assert report["accepted_count"] == 0
    assert "evidence_digest" in report["records"][0]["reason_codes"]

def test_shared_or_missing_workspace_kind_is_rejected(tmp_path: Path):
    record = hermes_record(run_id="run-shared-ws")
    record.pop("workspace")
    shared = write_scenario(
        tmp_path / "shared",
        [record],
        manifest_overrides={"workspace": {"kind": "shared"}},
    )
    missing = write_scenario(tmp_path / "missing", [record])
    missing_manifest = json.loads(missing["manifest"].read_text(encoding="utf-8"))
    missing_manifest["workspace"].pop("kind")
    write_json(missing["manifest"], missing_manifest)
    assert _run(shared) == 0
    assert _run(missing) == 0
    for paths in (shared, missing):
        assert paths["output"].read_text(encoding="utf-8") == ""
        report = _report(paths)
        assert report["accepted_count"] == 0
        assert report["rejected_count"] >= 1
        assert "workspace" in ",".join(report["records"][0]["reason_codes"])

def test_casefolded_hermes_verifier_identity_is_not_external(tmp_path: Path):
    paths = write_scenario(
        tmp_path,
        [hermes_record(run_id="run-self-case")],
        manifest_overrides={
            "verifier": {
                "artifact_sha256": [VERIFIER_ARTIFACT],
                "identity": "Hermes-Agent",
                "outcome": "pass",
                "version": "0.4.0",
            }
        },
    )
    assert _run(paths) == 0
    dumped = paths["output"].read_text(encoding="utf-8")
    assert dumped == ""
    assert "successful" not in dumped
    report = _report(paths)
    assert report["accepted_count"] == 0
    assert "verifier" in ",".join(report["records"][0]["reason_codes"])

def test_hidden_equivalent_tags_are_stripped_and_unclosed_are_rejected(tmp_path: Path):
    closed = hermes_record(
        run_id="run-hidden-tags",
        content=(
            "<analysis>private chain</analysis>"
            "<reasoning>private chain</reasoning>"
            "<scratchpad>private chain</scratchpad>"
            "Visible answer."
        ),
    )
    paths = write_scenario(tmp_path / "closed", [closed])
    assert _run(paths) == 0
    dumped = paths["output"].read_text(encoding="utf-8")
    assert "private chain" not in dumped
    assert "Visible answer." in dumped
    unclosed = hermes_record(
        run_id="run-unclosed",
        content="<analysis>private chain",
    )
    rejected = write_scenario(tmp_path / "open", [unclosed])
    assert _run(rejected) == 0
    open_dump = rejected["output"].read_text(encoding="utf-8")
    assert open_dump == ""
    assert "private chain" not in open_dump
    assert _report(rejected)["rejected_count"] >= 1

def test_unclosed_hidden_tags_are_scanned_in_bounded_time():
    value = "<think>" * 20_000
    started = time.monotonic()
    assert strip_hidden_reasoning(value) == value
    assert time.monotonic() - started < 1.0

def test_repository_url_query_credential_is_not_emitted(tmp_path: Path):
    secret_url = (
        "https://github.com/rmems/synthetic-loop?access_token=ordinarysecretvalue123"
    )
    omitted = hermes_record(run_id="run-url-omit")
    omitted.pop("repository")
    agreed = hermes_record(run_id="run-url-agree")
    agreed["repository"]["url"] = secret_url
    for name, record in (("omit", omitted), ("agree", agreed)):
        paths = write_scenario(
            tmp_path / name,
            [record],
            manifest_overrides={"repository": {"url": secret_url}},
        )
        assert _run(paths) == 0
        dumped = paths["output"].read_text(encoding="utf-8") + paths["report"].read_text(
            encoding="utf-8"
        )
        assert "ordinarysecretvalue123" not in dumped
        assert "access_token" not in dumped

def test_header_and_json_credential_content_is_rejected(tmp_path: Path):
    bearer = hermes_record(
        run_id="run-bearer",
        content="Authorization: Bearer ordinarysecretvalue123",
    )
    header = hermes_record(
        run_id="run-header",
        content='{"X-API-Key":"ordinarysecretvalue123"}',
    )
    for name, record in (("bearer", bearer), ("header", header)):
        paths = write_scenario(tmp_path / name, [record])
        assert _run(paths) == 0
        dumped = paths["output"].read_text(encoding="utf-8")
        assert dumped == ""
        assert "ordinarysecretvalue123" not in dumped
        assert _report(paths)["rejected_count"] >= 1

def test_trajectory_id_encoding_resists_delimiter_collision(tmp_path: Path):
    first = hermes_record(run_id="a/b")
    first["session_id"] = "c"
    first["task_id"] = "d"
    first["raw_trace_id"] = "e"
    second = hermes_record(run_id="a")
    second["session_id"] = "b"
    second["task_id"] = "c"
    second["raw_trace_id"] = "d/e"
    records = []
    for name, source in (("first", first), ("second", second)):
        paths = write_scenario(tmp_path / name, [source])
        assert _run(paths) == 0
        records.extend(_load_jsonl(paths["output"]))
    assert len(records) == 2
    assert records[0]["trajectory_id"] != records[1]["trajectory_id"]
    assert records[0]["trajectory_id"] != "hermes:a/b/c/d/e"
    assert records[0]["execution_provenance"]["run_id"] == "a/b"
    assert records[1]["execution_provenance"]["raw_trace_id"] == "d/e"

def test_malformed_tool_payload_is_rejected(tmp_path: Path):
    record = hermes_record(
        run_id="run-tool",
        extra_message={
            "role": "tool",
            "name": "fetch",
            "timestamp": "2026-09-21T12:00:30Z",
            "content": '{"unterminated":',
        },
    )
    paths = write_scenario(tmp_path, [record])
    assert _run(paths) == 0
    assert paths["output"].read_text(encoding="utf-8") == ""
    report = _report(paths)
    assert report["rejected_count"] >= 1
    assert "invalid_tool_payload" in report["records"][0]["reason_codes"]

def test_unknown_message_field_is_rejected(tmp_path: Path):
    record = hermes_record(run_id="run-extra-field")
    record["messages"][1]["private_notes"] = "producer private container"
    paths = write_scenario(tmp_path, [record])
    assert _run(paths) == 0
    dumped = paths["output"].read_text(encoding="utf-8")
    assert "producer private container" not in dumped
    assert _report(paths)["accepted_count"] == 0

def test_canonical_dumps_rejects_nonfinite_numbers():
    with pytest.raises(ValueError):
        canonical_dumps({"value": float("nan")})

