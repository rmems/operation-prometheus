"""CI contract jobs: trajectory policy and Agoge consumer sidecars."""

from __future__ import annotations

import json
from pathlib import Path

from lib.ci_contracts import (
    blank_license_policy_errors,
    is_real_check_run_detail,
    iter_uri_fields,
    private_reference_errors,
    silent_truncation_errors,
    unique_event_errors,
    validation_evidence_errors,
)
from lib.hermes_normalize import normalize_files

from consumer_contract import consume, future_event_errors
from validate_jsonl import load_schema, validate_file

try:
    import jsonschema
except ImportError:
    jsonschema = None

ROOT = Path(__file__).resolve().parents[1]
V1_FIXTURE = ROOT / "tests" / "fixtures" / "v1" / "software_valid.jsonl"


def _v1_record() -> dict:
    return json.loads(V1_FIXTURE.read_text().splitlines()[0])


def _validators():
    v0 = jsonschema.Draft7Validator(
        load_schema(ROOT / "schemas" / "pr_trajectory.schema.json"),
        format_checker=jsonschema.Draft7Validator.FORMAT_CHECKER,
    )
    v1 = jsonschema.Draft7Validator(
        load_schema(ROOT / "schemas" / "trajectory_v1.schema.json"),
        format_checker=jsonschema.Draft7Validator.FORMAT_CHECKER,
    )
    return v0, v1


def test_duplicate_trajectory_id_is_rejected(tmp_path):
    v0, v1 = _validators()
    record = _v1_record()
    path = tmp_path / "dup.jsonl"
    path.write_text(json.dumps(record) + "\n" + json.dumps(record) + "\n")
    errors = validate_file(path, v0, v1, strict_policy=True)
    assert any("duplicate trajectory id" in error for error in errors)


def test_duplicate_event_id_is_rejected(tmp_path):
    v0, v1 = _validators()
    record = _v1_record()
    extra = dict(record["events"][0])
    extra["event_id"] = "e1"
    extra["timestamp"] = "2023-01-01T13:00:00Z"
    record["events"].append(extra)
    path = tmp_path / "dup-event.jsonl"
    path.write_text(json.dumps(record) + "\n")
    errors = validate_file(path, v0, v1, strict_policy=True)
    assert any("duplicate event_id" in error for error in errors)


def test_private_file_uri_on_source_url_is_rejected(tmp_path):
    v0, v1 = _validators()
    record = _v1_record()
    record["source_urls"] = ["file:///etc/passwd"]
    path = tmp_path / "private.jsonl"
    path.write_text(json.dumps(record) + "\n")
    errors = validate_file(path, v0, v1, strict_policy=True)
    assert any("private reference" in error for error in errors)


def test_patch_mentions_of_localhost_are_not_private_references():
    record = {
        "patch": "diff --git a/test.py b/test.py\n+url = 'http://127.0.0.1:8000'\n",
        "source_urls": ["https://github.com/rmems/ci-demo/pull/17"],
    }
    assert iter_uri_fields(record) == ["https://github.com/rmems/ci-demo/pull/17"]
    assert private_reference_errors("http://[::1]/health") == ["private host ::1"]
    assert private_reference_errors("https://alice:s3cr3t@example.com/path") == [
        "credentials in URI"
    ]
    assert private_reference_errors("//10.0.0.1/private") == ["private host 10.0.0.1"]
    nested = {"repository": {"url": "file:///etc/passwd"}}
    assert iter_uri_fields(nested) == ["file:///etc/passwd"]
    provenance = {
        "execution_provenance": {"repository": {"url": "ssh://private.lan/repo"}}
    }
    assert iter_uri_fields(provenance) == ["ssh://private.lan/repo"]


def test_uri_collection_ignores_schema_invalid_sequences():
    assert iter_uri_fields({"artifacts": "invalid", "events": 42}) == []


def test_private_hosts_with_trailing_root_dot_are_rejected():
    for uri, host in (
        ("http://localhost./secret", "localhost"),
        ("http://127.0.0.1./x", "127.0.0.1"),
        ("http://private.internal./x", "private.internal"),
    ):
        assert private_reference_errors(uri) == [f"private host {host}"]


def test_blank_license_is_rejected(tmp_path):
    v0, v1 = _validators()
    record = _v1_record()
    record["license"] = "   "
    path = tmp_path / "blank-license.jsonl"
    path.write_text(json.dumps(record) + "\n")
    errors = validate_file(path, v0, v1, strict_policy=True)
    assert any("license is missing" in error for error in errors)


def test_blank_license_is_rejected_for_v1_1():
    record = {"schema_version": "1.1", "license": "", "collection_policy": " "}
    assert blank_license_policy_errors(record) == [
        "license is missing a sourced value",
        "collection_policy is missing a sourced value",
    ]


def test_check_run_conclusions_are_distinguished_from_checklists():
    assert is_real_check_run_detail("Build & Test=success")
    assert is_real_check_run_detail("combined_status=success")
    assert not is_real_check_run_detail("combined_status=banana")
    assert not is_real_check_run_detail("- [ ] unit tests")
    prose = {
        "validation": [
            {
                "type": "ci",
                "result": "pass",
                "detail": "- [x] CI is green in the PR body",
            },
        ]
    }
    assert any("checklist" in error for error in validation_evidence_errors(prose))
    real = {
        "validation": [
            {"type": "ci", "result": "pass", "detail": "CPU tests=success"},
        ]
    }
    assert validation_evidence_errors(real) == []
    prose_pass = {
        "validation": [{"type": "ci", "result": "pass", "detail": "CI passed"}]
    }
    assert any(
        "prose" in error for error in validation_evidence_errors(prose_pass)
    )


def test_silent_truncation_without_marker_is_rejected():
    record = {"patch": "a" * (96 * 1024)}
    assert any(
        "silent patch truncation" in error for error in silent_truncation_errors(record)
    )
    declared = {"patch": "# Truncated unified diff for training\n" + ("a" * 100)}
    assert silent_truncation_errors(declared) == []
    hidden = {"software_payload": {"implementation_patch": "b" * (96 * 1024)}}
    assert any(
        "silent patch truncation" in error for error in silent_truncation_errors(hidden)
    )
    blank_id = {"artifacts": [{"id": ""}]}
    assert unique_event_errors(blank_id) == ["artifact id is missing"]


def test_consumer_contract_parses_messages_and_instruction_with_sidecar(tmp_path):
    def normalize(row, tokenizer=None, index=0):
        if "messages" in row:
            return {"text": "\n".join(m["content"] for m in row["messages"])}
        return {"text": f"{row['instruction']}\n{row.get('output', '')}"}

    path = ROOT / "tests" / "fixtures" / "consumer" / "messages_and_instruction.jsonl"
    sidecar = consume(path, normalize)
    assert sidecar["ok"]
    formats = {row["format"] for row in sidecar["rows"]}
    assert formats == {"messages", "instruction"}
    assert sidecar["parser"] == "agoge_forger.datasets.normalize_row"
    assert sidecar["source_sha256"]
    assert sidecar["source_path"] == (
        "tests/fixtures/consumer/messages_and_instruction.jsonl"
    )


def test_consumer_contract_reports_malformed_rows_and_keeps_trajectory_id(tmp_path):
    def normalize(row, tokenizer=None, index=0):
        return {"text": "ok"}

    path = tmp_path / "bad.jsonl"
    path.write_text(
        "\n".join(
            [
                "{",
                "[]",
                json.dumps(
                    {
                        "text": "keep",
                        "_prometheus": {"source_trajectory_id": "traj-9"},
                    }
                ),
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    sidecar = consume(path, normalize)
    assert sidecar["ok"] is False
    assert any("Invalid JSON" in error for error in sidecar["errors"])
    assert any("not a JSON object" in error for error in sidecar["errors"])
    assert sidecar["rows"][0]["source_trajectory_id"] == "traj-9"


def test_consumer_contract_rejects_blank_normalized_text(tmp_path):
    def normalize(row, tokenizer=None, index=0):
        return {"text": "   "}

    path = tmp_path / "blank.jsonl"
    path.write_text('{"instruction":"nonempty"}\n', encoding="utf-8")
    sidecar = consume(path, normalize)
    assert sidecar["ok"] is False
    assert sidecar["rows"] == []
    assert any("parser did not return a text row" in error for error in sidecar["errors"])


def test_consumer_contract_rejects_malformed_timestamp_metadata():
    record = {"_prometheus": {"event_timestamps": [1, "2026-01-01T00:00:00Z"]}}
    assert any("malformed event timestamp" in error for error in future_event_errors(record))


def test_consumer_contract_rejects_missing_payload_timestamp():
    record = {"events": [{"timestamp": "2026-01-01T00:00:00Z"}, {}]}
    assert future_event_errors(record) == ["malformed event timestamp None"]


def test_consumer_contract_does_not_double_count_event_timelines():
    record = {
        "events": [{"timestamp": "2026-01-02T00:00:00Z"}],
        "_prometheus": {
            "event_timestamps": ["2026-01-01T00:00:00Z", "2026-01-02T00:00:00Z"]
        },
    }
    assert future_event_errors(record) == []


def test_consumer_contract_detects_future_event_leakage():
    path = (
        ROOT / "tests" / "fixtures" / "consumer" / "negative" / "future_leakage.jsonl"
    )
    record = json.loads(path.read_text().splitlines()[0])
    assert any("future-event leakage" in error for error in future_event_errors(record))

    def normalize(row, tokenizer=None, index=0):
        return {"text": "x"}

    sidecar = consume(path, normalize)
    assert sidecar["ok"] is False



def test_schema_v1_software_without_validation_evidence_is_rejected():
    record = {
        "schema_version": "1.0",
        "trajectory_type": "software",
        "events": [
            {
                "event_id": "e1",
                "content": "The empty-list helper returns None.",
                "code_state": {"head_oid": "abc123"},
            }
        ],
    }
    assert validation_evidence_errors(record) == [
        "missing required validation evidence"
    ]


def test_strict_validator_enforces_validation_evidence(tmp_path):
    v0, v1 = _validators()
    record = _v1_record()
    record.pop("validation", None)
    for event in record["events"]:
        event.pop("disposition", None)
    record.pop("validation_outcome", None)
    record.get("software_payload", {}).pop("validation_outcome", None)
    path = tmp_path / "missing-evidence.jsonl"
    path.write_text(json.dumps(record) + "\n")
    errors = validate_file(path, v0, v1, strict_policy=True)
    assert any("missing required validation evidence" in error for error in errors)


def test_strict_validator_rejects_successful_record_with_failed_verifier(tmp_path):
    scenario = ROOT / "tests" / "fixtures" / "local_agent" / "accepted"
    canonical = tmp_path / "canonical.jsonl"
    normalize_files(
        input_path=scenario / "input.jsonl",
        run_manifest_path=scenario / "run_manifest.json",
        model_admission_path=scenario / "model_admission.json",
        output_path=canonical,
        report_path=tmp_path / "report.json",
    )
    record = json.loads(canonical.read_text())
    record["execution_provenance"]["verifier"]["outcome"] = "fail"
    canonical.write_text(json.dumps(record) + "\n")
    v0, v1 = _validators()
    v1_1 = jsonschema.Draft7Validator(
        load_schema(ROOT / "schemas" / "trajectory_v1_1.schema.json"),
        format_checker=jsonschema.Draft7Validator.FORMAT_CHECKER,
    )
    errors = validate_file(
        canonical, v0, v1, strict_policy=True, v1_1_validator=v1_1
    )
    assert any("failed verifier became a successful trajectory" in error for error in errors)


def test_schema_v1_event_disposition_counts_as_validation_evidence():
    record = {
        "schema_version": "1.1",
        "trajectory_type": "software",
        "events": [{"disposition": "successful"}],
    }
    assert validation_evidence_errors(record) == []


def test_schema_v1_research_without_validation_array_is_allowed():
    record = {"schema_version": "1.0", "trajectory_type": "research"}
    assert validation_evidence_errors(record) == []


def test_pr_workflows_stay_offline():
    workflows = ROOT / ".github" / "workflows"
    for path in workflows.glob("*.yml"):
        text = path.read_text()
        assert "HF_TOKEN" not in text
        assert "ollama" not in text.casefold()
    ci = (workflows / "ci.yml").read_text()
    assert "CUDA_VISIBLE_DEVICES" in ci
    assert "HF_HUB_OFFLINE" in ci


def test_shared_files_guard_and_existing_gates_remain_named():
    ci = (ROOT / ".github" / "workflows" / "ci.yml").read_text()
    for job in (
        "lint",
        "test",
        "validate",
        "status-up-to-date",
        "shared-files-guard",
        "trajectory-contract",
        "local-agent-contract",
        "consumer-contract",
    ):
        assert f"{job}:" in ci
