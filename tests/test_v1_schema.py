import json
import sys
from pathlib import Path

import jsonschema

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from scripts.validate_jsonl import validate_file, load_schema  # noqa: E402

V0_SCHEMA_PATH = _REPO_ROOT / "schemas" / "pr_trajectory.schema.json"
V1_SCHEMA_PATH = _REPO_ROOT / "schemas" / "trajectory_v1.schema.json"
FIXTURES_DIR = _REPO_ROOT / "tests" / "fixtures" / "v1"


def get_validators():
    v0_schema = load_schema(V0_SCHEMA_PATH)
    v0_validator = jsonschema.Draft7Validator(
        v0_schema, format_checker=jsonschema.Draft7Validator.FORMAT_CHECKER
    )
    v1_schema = load_schema(V1_SCHEMA_PATH)
    v1_validator = jsonschema.Draft7Validator(
        v1_schema, format_checker=jsonschema.Draft7Validator.FORMAT_CHECKER
    )
    return v0_validator, v1_validator


def test_v1_valid_software():
    v0, v1 = get_validators()
    errors = validate_file(FIXTURES_DIR / "software_valid.jsonl", v0, v1, strict_policy=True)
    assert not errors, f"Expected valid software, got {errors}"


def test_v1_valid_research():
    v0, v1 = get_validators()
    errors = validate_file(FIXTURES_DIR / "research_valid.jsonl", v0, v1, strict_policy=True)
    assert not errors, f"Expected valid research, got {errors}"


def test_v1_missing_snapshot():
    v0, v1 = get_validators()
    errors = validate_file(FIXTURES_DIR / "missing_snapshot.jsonl", v0, v1, strict_policy=True)
    assert any("missing required code snapshots" in e for e in errors), f"Expected missing snapshot error, got {errors}"


def test_v1_malformed_hash():
    v0, v1 = get_validators()
    errors = validate_file(FIXTURES_DIR / "malformed_hash.jsonl", v0, v1, strict_policy=True)
    assert any("badhash" in e or "pattern" in e for e in errors), f"Expected malformed hash error, got {errors}"


def test_v1_future_leakage():
    v0, v1 = get_validators()
    errors = validate_file(FIXTURES_DIR / "future_leakage.jsonl", v0, v1, strict_policy=True)
    assert any("future-event leakage" in e for e in errors), f"Expected future leakage error, got {errors}"


def test_v1_future_leakage_mixed_offset():
    v0, v1 = get_validators()
    errors = validate_file(FIXTURES_DIR / "future_leakage_offset.jsonl", v0, v1, strict_policy=True)
    assert any("future-event leakage" in e for e in errors), f"Expected future leakage error, got {errors}"


def test_v1_timestamp_utc_overflow_is_reported_and_validation_continues(tmp_path):
    v0, v1 = get_validators()
    overflow_record = json.loads((FIXTURES_DIR / "software_valid.jsonl").read_text())
    overflow_record["events"][0]["timestamp"] = "0001-01-01T00:00:00+14:00"
    next_record = json.loads((FIXTURES_DIR / "software_valid.jsonl").read_text())
    next_record["events"][0]["actor"]["type"] = "wizard"
    filepath = tmp_path / "timestamps.jsonl"
    filepath.write_text(f"{json.dumps(overflow_record)}\n{json.dumps(next_record)}\n")

    errors = validate_file(filepath, v0, v1, strict_policy=True)

    assert any(
        f"{filepath.name}:1 [policy] - timestamp UTC normalization overflow" in error for error in errors
    )
    assert any(
        f"{filepath.name}:2 [policy] - invented/unsupported actor type" in error for error in errors
    )


def test_v1_nonterminal_positive():
    v0, v1 = get_validators()
    errors = validate_file(FIXTURES_DIR / "nonterminal_positive.jsonl", v0, v1, strict_policy=True)
    assert any("nonterminal record incorrectly represented" in e for e in errors), f"Expected nonterminal error, got {errors}"


def test_v1_missing_typed_payload():
    v0, v1 = get_validators()
    errors = validate_file(FIXTURES_DIR / "missing_payload.jsonl", v0, v1, strict_policy=True)
    assert any("software_payload" in e or "allOf" in e for e in errors), f"Expected missing payload error, got {errors}"


def test_v1_invented_actor():
    v0, v1 = get_validators()
    errors = validate_file(FIXTURES_DIR / "invented_actor.jsonl", v0, v1, strict_policy=True)
    assert any("wizard" in e or "actor type" in e for e in errors), f"Expected actor error, got {errors}"


def test_v1_failed_with_only_successful_events():
    v0, v1 = get_validators()
    errors = validate_file(FIXTURES_DIR / "failed_all_successful_events.jsonl", v0, v1, strict_policy=True)
    assert any("terminal_disposition does not agree" in e for e in errors), f"Expected disposition disagreement, got {errors}"


def test_v1_successful_with_last_event_failed():
    v0, v1 = get_validators()
    errors = validate_file(FIXTURES_DIR / "successful_last_event_failed.jsonl", v0, v1, strict_policy=True)
    assert any("nonterminal record incorrectly represented" in e for e in errors), f"Expected nonterminal error, got {errors}"


def test_v1_empty_software_payload():
    v0, v1 = get_validators()
    errors = validate_file(FIXTURES_DIR / "empty_software_payload.jsonl", v0, v1, strict_policy=True)
    assert any("software_payload" in e or "anyOf" in e or "minProperties" in e for e in errors), f"Expected empty payload error, got {errors}"


def test_v1_lowercase_z_order():
    v0, v1 = get_validators()
    errors = validate_file(FIXTURES_DIR / "lowercase_z_order.jsonl", v0, v1, strict_policy=True)
    assert any("future-event leakage" in e for e in errors), f"Expected order error for lowercase z, got {errors}"


def test_v1_inline_artifact_hash_mismatch():
    v0, v1 = get_validators()
    errors = validate_file(FIXTURES_DIR / "inline_hash_mismatch.jsonl", v0, v1, strict_policy=True)
    assert any("inline artifact sha256 does not match content" in e for e in errors), f"Expected hash mismatch, got {errors}"
    assert not any("inline artifact byte_size does not match content" in e for e in errors), f"Fixture should isolate sha256, got {errors}"


def test_v1_empty_research_payload():
    v0, v1 = get_validators()
    errors = validate_file(FIXTURES_DIR / "empty_research_payload.jsonl", v0, v1, strict_policy=True)
    assert any("research_payload" in e or "anyOf" in e or "minProperties" in e for e in errors), f"Expected empty research payload error, got {errors}"


def test_v1_blank_software_payload_rejected():
    v0, v1 = get_validators()
    errors = validate_file(FIXTURES_DIR / "blank_software_payload.jsonl", v0, v1, strict_policy=True)
    assert any("minLength" in e or "issue_statement" in e for e in errors), f"Expected blank payload error, got {errors}"


def test_v1_empty_events_rejected():
    v0, v1 = get_validators()
    errors = validate_file(FIXTURES_DIR / "empty_events.jsonl", v0, v1, strict_policy=True)
    assert any("minItems" in e or "is too short" in e or "events" in e for e in errors), f"Expected empty events error, got {errors}"


def test_v1_reverted_with_successful_last_event():
    v0, v1 = get_validators()
    errors = validate_file(FIXTURES_DIR / "reverted_last_successful.jsonl", v0, v1, strict_policy=True)
    assert any("terminal_disposition does not agree" in e for e in errors), f"Expected disposition disagreement, got {errors}"


def test_v1_remote_artifact_requires_uri():
    v0, v1 = get_validators()
    errors = validate_file(FIXTURES_DIR / "remote_missing_uri.jsonl", v0, v1, strict_policy=True)
    assert any("uri" in e for e in errors), f"Expected missing uri error, got {errors}"


def test_v1_secret_like_object_key_is_flagged(tmp_path):
    v0, v1 = get_validators()
    record = json.loads((FIXTURES_DIR / "software_valid.jsonl").read_text())
    record["evidence_quality"] = {"github_pat_abcdefghijklmnopqrstuvwxyz0123": 1}
    filepath = tmp_path / "secret_key.jsonl"
    filepath.write_text(json.dumps(record) + "\n")
    errors = validate_file(filepath, v0, v1, strict_policy=True)
    assert any("secret-like token" in e for e in errors), f"Expected secret key error, got {errors}"


def test_v1_nonfinite_json_constant_rejected(tmp_path):
    v0, v1 = get_validators()
    record = json.loads((FIXTURES_DIR / "software_valid.jsonl").read_text())
    record["evidence_quality"] = {"signal_to_noise": 0.5}
    line = json.dumps(record).replace("0.5", "NaN")
    filepath = tmp_path / "nan.jsonl"
    filepath.write_text(line + "\n")
    errors = validate_file(filepath, v0, v1, strict_policy=True)
    assert any("Invalid JSON" in e or "non-finite" in e for e in errors), f"Expected NaN rejection, got {errors}"


def test_v1_inline_lone_surrogate_does_not_crash(tmp_path):
    v0, v1 = get_validators()
    next_record = json.loads((FIXTURES_DIR / "software_valid.jsonl").read_text())
    next_record["events"][0]["actor"]["type"] = "wizard"
    filepath = tmp_path / "surrogate.jsonl"
    first = (
        '{"schema_version": "1.0", "trajectory_id": "soft-1", "trajectory_type": "software",'
        ' "provider_id": "test-provider", "source_id": "test-source", "collector_version": "0.6.0",'
        ' "repository": {"owner": "foo", "name": "bar"}, "license": "MIT", "collection_policy": "public",'
        ' "terminal_disposition": "successful",'
        ' "events": [{"event_id": "e1", "timestamp": "2023-01-01T12:00:00Z",'
        ' "actor": {"type": "human", "id": "u1"}, "event_type": "commit",'
        ' "code_state": {"base_oid": "abc", "head_oid": "def"}, "disposition": "successful"}],'
        ' "artifacts": [{"id": "a1", "sha256": "' + ("0" * 64) + '", "media_type": "text/plain",'
        ' "byte_size": 1, "availability": "inline", "reproduction_role": "patch",'
        ' "content": "\\ud800"}],'
        ' "software_payload": {"validation_outcome": "pass"}}'
    )
    filepath.write_text(first + "\n" + json.dumps(next_record) + "\n")
    errors = validate_file(filepath, v0, v1, strict_policy=True)
    assert any(
        "not UTF-8 encodable" in e or "sha256 does not match" in e for e in errors
    ), f"Expected surrogate handling, got {errors}"
    assert any(
        "invented/unsupported actor type" in e for e in errors
    ), f"Expected validation to continue, got {errors}"


def test_v1_head_oid_only_snapshot_is_enough():
    v0, v1 = get_validators()
    errors = validate_file(FIXTURES_DIR / "head_oid_only.jsonl", v0, v1, strict_policy=True)
    assert not any("missing required code snapshots" in e for e in errors), f"head_oid-only should count, got {errors}"


def test_v1_after_blob_only_snapshot_is_enough():
    v0, v1 = get_validators()
    errors = validate_file(FIXTURES_DIR / "after_blob_only.jsonl", v0, v1, strict_policy=True)
    assert not any("missing required code snapshots" in e for e in errors), f"after_blob-only should count, got {errors}"


def test_v1_missing_artifact_content_hash_is_checked():
    v0, v1 = get_validators()
    errors = validate_file(FIXTURES_DIR / "missing_content_hash.jsonl", v0, v1, strict_policy=True)
    assert any("sha256 does not match content" in e for e in errors), f"Expected hash mismatch, got {errors}"


def test_v1_relative_remote_uri_rejected():
    v0, v1 = get_validators()
    errors = validate_file(FIXTURES_DIR / "relative_remote_uri.jsonl", v0, v1, strict_policy=True)
    assert any("uri" in e.lower() for e in errors), f"Expected relative uri error, got {errors}"


def test_v1_yesterday_timestamp_rejected():
    v0, v1 = get_validators()
    errors = validate_file(FIXTURES_DIR / "yesterday_timestamp.jsonl", v0, v1, strict_policy=True)
    assert any("timestamp" in e.lower() or "date-time" in e.lower() or "format" in e.lower() for e in errors), f"Expected timestamp format error, got {errors}"


def test_v1_overflow_float_rejected():
    v0, v1 = get_validators()
    errors = validate_file(FIXTURES_DIR / "overflow_float.jsonl", v0, v1, strict_policy=True)
    assert any("non-finite" in e or "Invalid JSON" in e for e in errors), f"Expected 1e999 rejection, got {errors}"


def test_v1_research_successful_without_event_disposition():
    v0, v1 = get_validators()
    errors = validate_file(FIXTURES_DIR / "research_no_disposition.jsonl", v0, v1, strict_policy=True)
    assert not any("nonterminal record" in e or "does not agree" in e for e in errors), f"Research without disposition should not false-positive, got {errors}"


def test_v1_successful_last_event_neutral_is_not_false_positive():
    v0, v1 = get_validators()
    errors = validate_file(FIXTURES_DIR / "successful_last_neutral.jsonl", v0, v1, strict_policy=True)
    assert not any("nonterminal record" in e for e in errors), f"Neutral last event should not false-positive successful, got {errors}"


def test_v1_failed_last_event_neutral_is_symmetric():
    v0, v1 = get_validators()
    errors = validate_file(FIXTURES_DIR / "failed_last_neutral.jsonl", v0, v1, strict_policy=True)
    assert not any("does not agree" in e or "nonterminal record" in e for e in errors), f"Neutral last event should not disagree with failed, got {errors}"
