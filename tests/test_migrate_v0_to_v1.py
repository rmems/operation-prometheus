"""Lossless pr_trajectory_v0 → trajectory-v1 migration (Linear RM-1346)."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import jsonschema

from lib.migrate_v0_to_v1 import (
    MIGRATION_TOOL_VERSION,
    canonical_dumps,
    migrate_files,
    migrate_jsonl,
    migrate_record,
    source_digest,
)
from migrate_v0_to_v1 import main
from validate_jsonl import load_schema, validate_file

ROOT = Path(__file__).resolve().parents[1]
EXAMPLE_V0 = ROOT / "datasets" / "examples" / "trajectory-v0-example.json"
FIXTURES = ROOT / "tests" / "fixtures" / "migrate"
V1_SOFTWARE = ROOT / "tests" / "fixtures" / "v1" / "software_valid.jsonl"
V0_SCHEMA = ROOT / "schemas" / "pr_trajectory.schema.json"
V1_SCHEMA = ROOT / "schemas" / "trajectory_v1.schema.json"


def _validators():
    v0 = jsonschema.Draft7Validator(
        load_schema(V0_SCHEMA),
        format_checker=jsonschema.Draft7Validator.FORMAT_CHECKER,
    )
    v1 = jsonschema.Draft7Validator(
        load_schema(V1_SCHEMA),
        format_checker=jsonschema.Draft7Validator.FORMAT_CHECKER,
    )
    return v0, v1


def _fixture(name: str) -> Path:
    return FIXTURES / name


def _example_jsonl_bytes() -> bytes:
    record = json.loads(EXAMPLE_V0.read_text(encoding="utf-8"))
    return (json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n").encode(
        "utf-8"
    )


def test_existing_v0_fixture_is_quarantined_without_invented_evidence(tmp_path):
    source = tmp_path / "existing_v0.jsonl"
    original = _example_jsonl_bytes()
    source.write_bytes(original)
    out = tmp_path / "out.jsonl"
    report_path = tmp_path / "report.json"

    report = migrate_files([source], out_path=out, report_path=report_path)

    assert source.read_bytes() == original
    assert out.read_text(encoding="utf-8") == ""
    assert report["admitted_count"] == 0
    assert report["refused_count"] == 1
    row = report["records"][0]
    assert row["status"] == "refused"
    assert "unavailable_timestamp" in row["reason_codes"]
    assert "commit_oid" in row["unavailable_fields"]
    assert "timestamp" in row["unavailable_fields"]
    assert report["migration_tool_version"] == MIGRATION_TOOL_VERSION
    assert row["source_sha256"] == hashlib.sha256(original.rstrip(b"\r\n")).hexdigest()


def test_admissible_v0_preserves_raw_values_and_records_provenance():
    line = _fixture("v0_admissible.jsonl").read_bytes()
    decision = migrate_record(line)
    assert decision["status"] == "admitted"
    record = decision["output_record"]
    source = json.loads(line.decode("utf-8"))

    assert record["schema_version"] == "1.0"
    assert record["trajectory_id"] == source["id"]
    assert record["collector_version"] == MIGRATION_TOOL_VERSION
    assert record["migration"]["tool_version"] == MIGRATION_TOOL_VERSION
    assert record["migration"]["source_sha256"] == decision["source_sha256"]
    assert record["migration"]["source_byte_size"] == decision["source_byte_size"]
    digest, byte_size, text = source_digest(line)
    assert decision["source_sha256"] == digest
    assert decision["source_byte_size"] == byte_size
    source_art = record["artifacts"][0]
    assert source_art["sha256"] == digest
    assert source_art["byte_size"] == byte_size
    assert source_art["content"] == text
    assert record["v0_fields"]["patch"] == source["patch"]
    assert record["v0_fields"]["review_signals"] == source["review_signals"]
    assert record["software_payload"]["issue_statement"] == source["issue_context"]
    assert record["software_payload"]["pre_change_state"] == source["before_context"]
    assert record["software_payload"]["implementation_patch"] == source["patch"]
    assert record["events"][0]["code_state"]["head_oid"] == "abc"
    assert source["source_urls"][0] in record["events"][0]["evidence_references"]
    assert record["evidence_quality"]["signal_to_noise"] == 0.85
    assert "review_signals" not in record["migration"]["unavailable_fields"]


def test_missing_review_signal_is_unavailable_not_fabricated():
    decision = migrate_record(_fixture("missing_review_signal.jsonl").read_bytes())
    assert decision["status"] == "admitted"
    record = decision["output_record"]
    assert "review_signals" in decision["unavailable_fields"]
    assert "review_signals" in record["migration"]["unavailable_fields"]
    assert "review_signals" not in record["v0_fields"]
    assert all(
        event.get("event_type") != "review" for event in record["events"]
    ), "migrator must not invent review events"


def test_missing_commit_oid_is_refused():
    decision = migrate_record(_fixture("missing_commit_oid.jsonl").read_bytes())
    assert decision["status"] == "refused"
    assert decision["reason_codes"] == ["unavailable_commit_oid"]
    assert "commit_oid" in decision["unavailable_fields"]
    assert decision["output_record"] is None


def test_malformed_timestamp_is_refused():
    decision = migrate_record(_fixture("malformed_timestamp.jsonl").read_bytes())
    assert decision["status"] == "refused"
    assert decision["reason_codes"] == ["malformed_timestamp"]
    assert decision["output_record"] is None


def test_unknown_event_is_refused():
    decision = migrate_record(_fixture("unknown_event.jsonl").read_bytes())
    assert decision["status"] == "refused"
    assert decision["reason_codes"] == ["unknown_event"]
    assert decision["output_record"] is None


def test_already_v1_is_refused_documented_noop():
    decision = migrate_record(V1_SOFTWARE.read_bytes())
    assert decision["status"] == "refused"
    assert decision["reason_codes"] == ["already_v1"]
    assert "documented no-op" in decision["detail"]
    assert decision["output_record"] is None


def test_mixed_file_splits_admitted_and_refused(tmp_path):
    mixed = tmp_path / "mixed.jsonl"
    chunks = [
        _fixture("v0_admissible.jsonl").read_bytes().rstrip(b"\n"),
        _fixture("missing_commit_oid.jsonl").read_bytes().rstrip(b"\n"),
        _fixture("malformed_timestamp.jsonl").read_bytes().rstrip(b"\n"),
        _fixture("unknown_event.jsonl").read_bytes().rstrip(b"\n"),
        V1_SOFTWARE.read_bytes().rstrip(b"\n"),
        _fixture("missing_review_signal.jsonl").read_bytes().rstrip(b"\n"),
    ]
    mixed.write_bytes(b"\n".join(chunks) + b"\n")
    out = tmp_path / "out.jsonl"
    report_path = tmp_path / "report.json"
    report = migrate_files([mixed], out_path=out, report_path=report_path)

    statuses = [row["status"] for row in report["records"]]
    reasons = [row["reason_codes"] for row in report["records"]]
    assert statuses == [
        "admitted",
        "refused",
        "refused",
        "refused",
        "refused",
        "admitted",
    ]
    assert reasons[1] == ["unavailable_commit_oid"]
    assert reasons[2] == ["malformed_timestamp"]
    assert reasons[3] == ["unknown_event"]
    assert reasons[4] == ["already_v1"]
    assert report["admitted_count"] == 2
    assert report["refused_count"] == 4
    admitted_lines = [line for line in out.read_text(encoding="utf-8").splitlines() if line]
    assert len(admitted_lines) == 2


def test_admitted_output_passes_v1_schema_and_strict_policy(tmp_path):
    out = tmp_path / "out.jsonl"
    report_path = tmp_path / "report.json"
    migrate_files(
        [_fixture("v0_admissible.jsonl"), _fixture("missing_review_signal.jsonl")],
        out_path=out,
        report_path=report_path,
    )
    v0, v1 = _validators()
    errors = validate_file(out, v0, v1, strict_policy=True)
    assert errors == [], errors
    for line in out.read_text(encoding="utf-8").splitlines():
        if not line:
            continue
        record = json.loads(line)
        assert record["migration"]["source_sha256"]
        assert record["collector_version"] == MIGRATION_TOOL_VERSION


def test_migration_is_byte_identical_on_rerun(tmp_path):
    source = tmp_path / "in.jsonl"
    source.write_bytes(_fixture("v0_admissible.jsonl").read_bytes())
    first_out = tmp_path / "a.jsonl"
    first_report = tmp_path / "a.report.json"
    second_out = tmp_path / "b.jsonl"
    second_report = tmp_path / "b.report.json"
    migrate_files([source], out_path=first_out, report_path=first_report)
    migrate_files([source], out_path=second_out, report_path=second_report)
    assert first_out.read_bytes() == second_out.read_bytes()
    assert first_report.read_bytes() == second_report.read_bytes()
    assert first_out.read_bytes() == canonical_dumps(
        json.loads(first_out.read_text(encoding="utf-8"))
    ).encode("utf-8") + b"\n"


def test_cli_never_overwrites_source(tmp_path):
    source = tmp_path / "in.jsonl"
    source.write_bytes(_fixture("v0_admissible.jsonl").read_bytes())
    original = source.read_bytes()
    report = tmp_path / "report.json"
    rc = main(["--out", str(source), "--report", str(report), str(source)])
    assert rc == 2
    assert source.read_bytes() == original
    assert not report.exists()


def test_cli_writes_out_and_report(tmp_path):
    source = tmp_path / "in.jsonl"
    source.write_bytes(_fixture("v0_admissible.jsonl").read_bytes())
    original = source.read_bytes()
    out = tmp_path / "out.jsonl"
    report = tmp_path / "report.json"
    rc = main(["--out", str(out), "--report", str(report), str(source)])
    assert rc == 0
    assert source.read_bytes() == original
    assert out.is_file()
    assert report.is_file()
    payload = json.loads(report.read_text(encoding="utf-8"))
    assert payload["admitted_count"] == 1
    assert payload["migration_tool_version"] == MIGRATION_TOOL_VERSION


def test_migrate_jsonl_helper_matches_file_path(tmp_path):
    text = _fixture("v0_admissible.jsonl").read_text(encoding="utf-8")
    admitted, report = migrate_jsonl(text, input_path="v0_admissible.jsonl")
    out = tmp_path / "out.jsonl"
    report_path = tmp_path / "report.json"
    migrate_files([_fixture("v0_admissible.jsonl")], out_path=out, report_path=report_path)
    assert admitted == out.read_text(encoding="utf-8")
    file_report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report["admitted_count"] == file_report["admitted_count"]
    assert report["records"][0]["source_sha256"] == file_report["records"][0]["source_sha256"]


def _admissible() -> dict:
    return json.loads(_fixture("v0_admissible.jsonl").read_text(encoding="utf-8"))


def _line(record: dict) -> bytes:
    return (json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n").encode("utf-8")


def test_digest_uses_original_source_bytes():
    line = _fixture("v0_admissible.jsonl").read_bytes().rstrip(b"\n") + b"\r\n"
    decision = migrate_record(line)
    assert decision["status"] == "admitted"
    raw = line.rstrip(b"\r\n")
    artifact = decision["output_record"]["artifacts"][0]
    assert artifact["byte_size"] == len(raw)
    assert artifact["sha256"] == hashlib.sha256(raw).hexdigest()
    assert artifact["sha256"] == decision["source_sha256"]


def test_nonfinite_json_constants_are_refused():
    record = _admissible()
    line = (
        json.dumps(record, separators=(",", ":")).replace("0.85", "NaN") + "\n"
    ).encode("utf-8")
    decision = migrate_record(line)
    assert decision["status"] == "refused"
    assert decision["reason_codes"] == ["invalid_json"]
    assert decision["output_record"] is None


def test_cli_rejects_identical_out_and_report(tmp_path):
    source = tmp_path / "in.jsonl"
    source.write_bytes(_fixture("v0_admissible.jsonl").read_bytes())
    dest = tmp_path / "same.jsonl"
    rc = main(["--out", str(dest), "--report", str(dest), str(source)])
    assert rc == 2
    assert not dest.exists()


def test_atomic_write_does_not_clobber_source_named_like_tmp(tmp_path):
    source = tmp_path / "out.jsonl.tmp"
    source.write_bytes(_fixture("v0_admissible.jsonl").read_bytes())
    original = source.read_bytes()
    out = tmp_path / "out.jsonl"
    report = tmp_path / "report.json"
    rc = main(["--out", str(out), "--report", str(report), str(source)])
    assert rc == 0
    assert source.read_bytes() == original
    assert out.is_file()


def test_naive_timestamp_is_refused_not_assigned_utc():
    record = _admissible()
    record["timestamp"] = "2023-01-01T12:00:00"
    decision = migrate_record(_line(record))
    assert decision["status"] == "refused"
    assert decision["reason_codes"] == ["malformed_timestamp"]


def test_fractional_seconds_are_preserved():
    record = _admissible()
    record["timestamp"] = "2023-01-01T12:00:00.999999Z"
    decision = migrate_record(_line(record))
    assert decision["status"] == "admitted"
    assert decision["output_record"]["events"][0]["timestamp"] == "2023-01-01T12:00:00.999999Z"


def test_timezone_overflow_is_refused():
    record = _admissible()
    record["timestamp"] = "0001-01-01T00:00:00+14:00"
    decision = migrate_record(_line(record))
    assert decision["status"] == "refused"
    assert decision["reason_codes"] == ["malformed_timestamp"]


def test_conflicting_oid_aliases_are_refused():
    record = _admissible()
    record["commit_oid"] = "abc"
    record["merge_commit_sha"] = "def"
    decision = migrate_record(_line(record))
    assert decision["status"] == "refused"
    assert decision["reason_codes"] == ["conflicting_commit_oid"]


def test_lone_surrogate_is_refused():
    record = _admissible()
    raw = json.dumps(record, separators=(",", ":")).replace(
        "CI was flaky", "CI was flaky \\ud800"
    )
    decision = migrate_record((raw + "\n").encode("utf-8"))
    assert decision["status"] == "refused"
    assert decision["reason_codes"] == ["unencodable_json"]


def test_superseded_is_not_relabeled_reverted():
    record = _admissible()
    record["outcome"] = "superseded"
    decision = migrate_record(_line(record))
    assert decision["status"] == "refused"
    assert decision["reason_codes"] == ["unmappable_outcome"]
    assert decision["output_record"] is None


def test_physical_line_numbers_include_blank_lines(tmp_path):
    chunks = [
        b"",
        _fixture("v0_admissible.jsonl").read_bytes().rstrip(b"\n"),
        b"",
        _fixture("missing_commit_oid.jsonl").read_bytes().rstrip(b"\n"),
    ]
    source = tmp_path / "blank.jsonl"
    source.write_bytes(b"\n".join(chunks) + b"\n")
    report = migrate_files(
        [source], out_path=tmp_path / "out.jsonl", report_path=tmp_path / "report.json"
    )
    assert [row["line"] for row in report["records"]] == [2, 4]
    assert report["records"][0]["status"] == "admitted"
    assert report["records"][1]["reason_codes"] == ["unavailable_commit_oid"]


def test_jsonl_does_not_split_on_unicode_line_separators():
    record = _admissible()
    record["issue_context"] = "hello\u0085world"
    admitted, report = migrate_jsonl(json.dumps(record, ensure_ascii=False) + "\n")
    assert report["admitted_count"] == 1
    assert report["refused_count"] == 0
    assert admitted


def test_non_string_validation_type_is_refused_not_raised():
    record = _admissible()
    record["validation"] = [{"type": ["ci"], "result": "pass"}]
    decision = migrate_record(_line(record))
    assert decision["status"] == "refused"
    assert decision["reason_codes"] == ["unknown_event"]


def test_incomplete_v0_object_is_refused():
    record = {
        "id": "only-core",
        "repo": "rmems/ci-demo",
        "outcome": "merged",
        "patch": "--- a/x\n+++ b/x",
        "timestamp": "2023-01-01T12:00:00Z",
        "head_oid": "abc",
    }
    decision = migrate_record(_line(record))
    assert decision["status"] == "refused"
    assert decision["reason_codes"] == ["v0_contract"]


def test_malformed_source_url_is_refused():
    record = _admissible()
    record["source_urls"] = ["not-a-github-pr"]
    decision = migrate_record(_line(record))
    assert decision["status"] == "refused"
    assert decision["reason_codes"] == ["malformed_source_url"]
