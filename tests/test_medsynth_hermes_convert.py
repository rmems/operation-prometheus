"""First-party medsynth Hermes session conversion tests."""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import jsonschema
import pytest

ROOT = Path(__file__).resolve().parent.parent
_SCRIPTS = ROOT / "scripts"
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

from convert_medsynth_hermes_sessions import main  # noqa: E402
from lib.hermes_normalize import _is_remote  # noqa: E402
from lib.medsynth_hermes_convert import convert_files  # noqa: E402
from validate_jsonl import load_schema, validate_file  # noqa: E402

PIN_ENTRY = """### Pin: `deepseek-v4.1-flash`

- **pin_id:** `deepseek-v4.1-flash`
- **api_key_env:** `MERGE_GATEWAY_API_KEY`
- **route_terms_document:** `Merge Gateway Terms`
- **route_terms_version:** `last updated 2026-04-02`
- **route_terms_date:** `2026-04-02`
- **route_terms_url:** `https://www.merge.dev/legal/gateway-terms`
- **route_terms_clause:** `§1: Customer Data includes Inputs and outputs received through the Service.`
"""
PIN_SHA256 = hashlib.sha256(PIN_ENTRY.strip().encode("utf-8")).hexdigest()
SESSION_NAME = "abc123.session.json"


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _session() -> dict:
    return {
        "run_id": "run-1",
        "session_id": "sess-1",
        "task_id": "task-1",
        "raw_trace_id": "trace-1",
        "completed": True,
        "partial": False,
        "started_at": "2026-11-27T10:00:00Z",
        "ended_at": "2026-11-27T10:01:00Z",
        "messages": [
            {
                "role": "system",
                "content": "You draft fictional medical education JSON.",
                "timestamp": "2026-11-27T10:00:00Z",
            },
            {
                "role": "user",
                "content": "Draft one anchored MCQ.",
                "timestamp": "2026-11-27T10:00:01Z",
            },
            {
                "role": "assistant",
                "content": "<think>hidden producer state</think>I will draft anchored content.",
                "timestamp": "2026-11-27T10:00:02Z",
            },
            {
                "role": "assistant",
                "content": "{\"question\":\"invented\"}",
                "timestamp": "2026-11-27T10:00:03Z",
            },
        ],
    }


def _session_text(session: dict | None = None) -> str:
    return json.dumps(session or _session(), indent=2, sort_keys=True) + "\n"


def _envelope(session_sha256: str, **overrides) -> dict:
    envelope = {
        "record_id": "draft-test-000",
        "teacher_variant": "DeepSeek-V4.1-Flash-1017",
        "model_id": "deepseek/deepseek-v4.1-flash-1017",
        "served_model": "deepseek-flash",
        "route": "Hermes via Merge Gateway",
        "serving_vendor": "deepseek",
        "session_file": SESSION_NAME,
        "session_sha256": session_sha256,
        "pin_id": "deepseek-v4.1-flash",
        "pin_entry": PIN_ENTRY,
        "pin_entry_sha256": PIN_SHA256,
        "content_sha256": "a" * 64,
    }
    envelope.update(overrides)
    return envelope


def _teacher_pin(**overrides) -> dict:
    pin = {
        "pin_id": "deepseek-v4.1-flash",
        "variant": "DeepSeek-V4.1-Flash-1017",
        "model_id": "deepseek/deepseek-v4.1-flash-1017",
        "route": "Hermes via Merge Gateway",
        "pin_entry_sha256": PIN_SHA256,
        "terms_document": "DeepSeek Open Platform Terms of Service",
        "terms_version": "release 2026-04-22; effective 2026-04-29",
        "terms_date": "2026-04-29",
        "terms_url": "https://cdn.deepseek.com/policies/en-US/deepseek-open-platform-terms-of-service.html",
        "terms_clause": "§4.2(3): outputs may be used for training other models",
        "snapshot_date": "2026-11-27",
    }
    pin.update(overrides)
    return pin


def _manifest(envelopes: list[dict], **pin_overrides) -> dict:
    return {
        "manifest_version": 1,
        "batch_id": "batch-test-000",
        "rights_envelopes": envelopes,
        "teacher_pin": _teacher_pin(**pin_overrides),
    }


def _write_case(
    tmp_path: Path,
    *,
    manifest: dict,
    session_text: str | None = None,
    session_name: str = SESSION_NAME,
) -> dict[str, Path]:
    tmp_path.mkdir(parents=True, exist_ok=True)
    batch_manifest = tmp_path / "manifest.json"
    batch_manifest.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    session_root = tmp_path / "sessions"
    session_root.mkdir()
    if session_text is not None:
        (session_root / session_name).write_bytes(session_text.encode("utf-8"))
    return {
        "batch_manifest": batch_manifest,
        "session_root": session_root,
        "output": tmp_path / "artifacts.jsonl",
        "report": tmp_path / "report.json",
    }


def _run(paths: dict[str, Path]) -> dict:
    assert main([
        "--batch-manifest",
        str(paths["batch_manifest"]),
        "--session-root",
        str(paths["session_root"]),
        "--output",
        str(paths["output"]),
        "--report",
        str(paths["report"]),
    ]) == 0
    return json.loads(paths["report"].read_text(encoding="utf-8"))


def _default_case(tmp_path: Path) -> dict[str, Path]:
    session_text = _session_text()
    envelope = _envelope(_sha256_text(session_text))
    return _write_case(
        tmp_path,
        manifest=_manifest([envelope]),
        session_text=session_text,
    )


def _jsonl(path: Path) -> list[dict]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def test_accepts_bound_session_and_preserves_provenance(tmp_path: Path):
    paths = _default_case(tmp_path)
    report = _run(paths)

    assert report["accepted_count"] == 1
    assert report["refused_count"] == 0
    row = report["records"][0]
    assert row["batch_id"] == "batch-test-000"
    assert row["record_id"] == "draft-test-000"
    assert row["session_id"] == "sess-1"
    assert row["rights_envelope_sha256"]

    artifacts = _jsonl(paths["output"])
    assert len(artifacts) == 1
    artifact = artifacts[0]
    assert artifact["schema_version"] == "first_party_hermes_trajectory_v1"
    assert artifact["source"]["batch_id"] == "batch-test-000"
    assert artifact["source"]["rights_envelope_sha256"] == row["rights_envelope_sha256"]
    assert artifact["session"]["session_id"] == "sess-1"
    assert artifact["teacher"]["route"] == "Hermes via Merge Gateway"
    assert artifact["teacher"]["serving_vendor"] == "deepseek"
    assert artifact["rights"]["terms_document"] == "DeepSeek Open Platform Terms of Service"
    assert artifact["rights"]["route_terms_document"] == "Merge Gateway Terms"
    events = artifact["trace"]["events"]
    assert [event["kind"] for event in events] == [
        "prompt",
        "prompt",
        "decision",
        "output",
    ]
    assert "hidden producer state" not in json.dumps(artifact, ensure_ascii=False)

    schema = load_schema(ROOT / "schemas" / "first_party_hermes_trajectory.schema.json")
    jsonschema.Draft7Validator(
        schema, format_checker=jsonschema.Draft7Validator.FORMAT_CHECKER
    ).validate(artifact)


def test_canonical_output_and_report_are_deterministic(tmp_path: Path):
    first = _default_case(tmp_path / "first")
    second = _default_case(tmp_path / "second")
    for paths in (first, second):
        convert_files(
            batch_manifest_path=paths["batch_manifest"],
            session_root=paths["session_root"],
            output_path=paths["output"],
            report_path=paths["report"],
        )
    assert first["output"].read_bytes() == second["output"].read_bytes()
    assert first["report"].read_bytes() == second["report"].read_bytes()


def test_strict_jsonl_validator_accepts_first_party_artifact(tmp_path: Path):
    paths = _default_case(tmp_path)
    _run(paths)
    v0 = jsonschema.Draft7Validator(
        load_schema(ROOT / "schemas" / "pr_trajectory.schema.json"),
        format_checker=jsonschema.Draft7Validator.FORMAT_CHECKER,
    )
    v1 = jsonschema.Draft7Validator(
        load_schema(ROOT / "schemas" / "trajectory_v1.schema.json"),
        format_checker=jsonschema.Draft7Validator.FORMAT_CHECKER,
    )
    assert validate_file(paths["output"], v0, v1, strict_policy=True) == []


def test_orphan_session_without_rights_envelope_is_refused(tmp_path: Path):
    paths = _write_case(
        tmp_path,
        manifest=_manifest([]),
        session_text=_session_text(),
    )
    report = _run(paths)
    assert paths["output"].read_text(encoding="utf-8") == ""
    assert report["accepted_count"] == 0
    assert report["refused_count"] == 1
    row = report["records"][0]
    assert row["status"] == "refused"
    assert "missing_rights_envelope" in row["reason_codes"]
    assert row["session_id"] == "sess-1"


def test_incomplete_rights_envelope_is_refused_without_orphan_duplicate(tmp_path: Path):
    session_text = _session_text()
    envelope = _envelope(_sha256_text(session_text))
    envelope.pop("session_sha256")
    paths = _write_case(
        tmp_path,
        manifest=_manifest([envelope]),
        session_text=session_text,
    )
    report = _run(paths)
    assert report["accepted_count"] == 0
    assert report["refused_count"] == 1
    reasons = report["records"][0]["reason_codes"]
    assert "incomplete_rights_envelope" in reasons
    assert "missing_rights_envelope" not in reasons


def test_session_hash_mismatch_is_refused(tmp_path: Path):
    paths = _write_case(
        tmp_path,
        manifest=_manifest([_envelope("0" * 64)]),
        session_text=_session_text(),
    )
    report = _run(paths)
    assert report["refused_count"] == 1
    assert "session_hash_mismatch" in report["records"][0]["reason_codes"]
    assert paths["output"].read_text(encoding="utf-8") == ""


def test_invalid_raw_session_record_is_refused(tmp_path: Path):
    session = _session()
    session.pop("run_id")
    session_text = _session_text(session)
    paths = _write_case(
        tmp_path,
        manifest=_manifest([_envelope(_sha256_text(session_text))]),
        session_text=session_text,
    )
    report = _run(paths)
    assert report["refused_count"] == 1
    assert "invalid_hermes_record" in report["records"][0]["reason_codes"]


def _assert_envelope_refusal(
    tmp_path: Path,
    envelope: dict,
    session_text: str | None,
    expected_reason: str,
    *,
    manifest_pin_sha256: str = PIN_SHA256,
) -> None:
    paths = _write_case(
        tmp_path,
        manifest=_manifest([envelope], pin_entry_sha256=manifest_pin_sha256),
        session_text=session_text,
    )
    report = _run(paths)
    assert report["refused_count"] == 1
    assert expected_reason in report["records"][0]["reason_codes"]


def test_envelope_must_match_manifest_teacher_pin(tmp_path: Path):
    session_text = _session_text()
    envelope = _envelope(
        _sha256_text(session_text), model_id="deepseek/renamed-model"
    )
    _assert_envelope_refusal(
        tmp_path, envelope, session_text, "rights_envelope_mismatch"
    )

def test_secret_bearing_session_is_refused(tmp_path: Path):
    session = _session()
    session["messages"][1]["content"] = "token=ghp_abcdefghijklmnopqrstuvwxyz123456"
    session_text = _session_text(session)
    paths = _write_case(
        tmp_path,
        manifest=_manifest([_envelope(_sha256_text(session_text))]),
        session_text=session_text,
    )
    report = _run(paths)
    assert report["refused_count"] == 1
    assert "secret_leakage" in report["records"][0]["reason_codes"]
    assert "ghp_abcdefghijklmnopqrstuvwxyz123456" not in paths["report"].read_text(
        encoding="utf-8"
    )


def test_unsafe_session_file_name_is_refused(tmp_path: Path):
    session_text = _session_text()
    envelope = _envelope(
        _sha256_text(session_text), session_file="../outside.session.json"
    )
    _assert_envelope_refusal(tmp_path, envelope, None, "unsafe_session_file")

def test_windows_drive_paths_are_local_file_boundary_paths():
    assert not _is_remote(r"C:\Users\example\manifest.json")
    assert not _is_remote("C:/Users/example/manifest.json")
    assert _is_remote("https://example.invalid/manifest.json")


def test_empty_teacher_batch_is_recorded_as_refusal(tmp_path: Path):
    paths = _write_case(tmp_path, manifest=_manifest([]), session_text=None)
    report = _run(paths)
    assert report["accepted_count"] == 0
    assert report["refused_count"] == 1
    assert "empty_input" in report["records"][0]["reason_codes"]


def test_pin_entry_hash_mismatch_is_refused(tmp_path: Path):
    session_text = _session_text()
    envelope = _envelope(_sha256_text(session_text), pin_entry_sha256="0" * 64)
    _assert_envelope_refusal(
        tmp_path,
        envelope,
        session_text,
        "pin_entry_hash_mismatch",
        manifest_pin_sha256="0" * 64,
    )


def test_output_cannot_overwrite_bound_session(tmp_path: Path):
    paths = _default_case(tmp_path)
    with pytest.raises(RuntimeError, match="overwrite source"):
        convert_files(
            batch_manifest_path=paths["batch_manifest"],
            session_root=paths["session_root"],
            output_path=paths["session_root"] / SESSION_NAME,
            report_path=paths["report"],
        )


def test_strict_validator_rechecks_pin_and_trace_consistency(tmp_path: Path):
    paths = _default_case(tmp_path)
    _run(paths)
    artifact = json.loads(paths["output"].read_text(encoding="utf-8"))
    artifact["rights"]["pin_entry_sha256"] = "0" * 64
    artifact["trace"]["event_count"] = 99
    paths["output"].write_text(
        json.dumps(artifact, sort_keys=True) + "\n", encoding="utf-8"
    )
    v0 = jsonschema.Draft7Validator(load_schema(ROOT / "schemas" / "pr_trajectory.schema.json"))
    v1 = jsonschema.Draft7Validator(load_schema(ROOT / "schemas" / "trajectory_v1.schema.json"))
    errors = validate_file(paths["output"], v0, v1, strict_policy=True)
    assert any("pin entry hash mismatch" in error for error in errors)
    assert any("event_count" in error for error in errors)
