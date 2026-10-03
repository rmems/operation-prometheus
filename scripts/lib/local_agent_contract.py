"""Offline checks for Hermes trajectory v1.1, admission, and observable actions."""

from __future__ import annotations

import json
import os
import shutil
import tempfile
from collections import Counter
from pathlib import Path
from typing import Any

from export_observable_actions import admitted_trajectory_ids, export_jsonl
from consumer_contract import future_event_errors

from .ci_policy import false_success_errors
from .ci_io import ROOT, sha256_file
from .hermes_normalize import normalize_files
from .local_agent_privacy import (
    cloud_fallback_errors,
    hash_errors,
    hidden_reasoning_errors,
    trainable_text_errors,
)
from .source_inventory_common import sha256_json

try:
    import jsonschema
except ImportError:  # pragma: no cover - CI installs jsonschema before this job
    jsonschema = None

SCENARIO_ROOT = ROOT / "tests" / "fixtures" / "local_agent"
OBSERVABLE_FIXTURE = (
    ROOT / "tests" / "fixtures" / "consumer" / "observable_actions.jsonl"
)
V1_1_SCHEMA = ROOT / "schemas" / "trajectory_v1_1.schema.json"
_DECISIONS = ("accepted", "quarantined", "rejected")
_SCENARIO_FILES = ("input.jsonl", "run_manifest.json", "model_admission.json")


def run_contract() -> list[str]:
    errors = _runtime_errors()
    if jsonschema is None:
        return [*errors, "jsonschema is required"]
    validator = jsonschema.Draft7Validator(
        json.loads(V1_1_SCHEMA.read_text(encoding="utf-8")),
        format_checker=jsonschema.Draft7Validator.FORMAT_CHECKER,
    )
    for scenario in _scenarios():
        errors.extend(_scenario_errors(scenario, validator))
    errors.extend(_prefixed("digest-mismatch", _digest_mismatch_errors()))
    return errors


def _runtime_errors() -> list[str]:
    visible = os.environ.get("CUDA_VISIBLE_DEVICES")
    if visible not in (None, "", "-1"):
        return ["local-agent contract must run with no GPU"]
    return []


def _scenarios() -> list[Path]:
    return sorted(
        path
        for path in SCENARIO_ROOT.iterdir()
        if path.is_dir() and (path / "expect.json").is_file()
    )


def _scenario_errors(scenario: Path, validator: Any) -> list[str]:
    expect = json.loads((scenario / "expect.json").read_text(encoding="utf-8"))
    with tempfile.TemporaryDirectory() as first_dir, tempfile.TemporaryDirectory() as second_dir:
        first = _normalize_scenario(scenario, Path(first_dir))
        second = _normalize_scenario(scenario, Path(second_dir))
        errors = _pair_errors(scenario, expect, validator, (first, second))
    return _prefixed(scenario.name, errors)


def _pair_errors(
    scenario: Path,
    expect: dict[str, Any],
    validator: Any,
    runs: tuple[dict[str, Any], dict[str, Any]],
) -> list[str]:
    first, second = runs
    errors: list[str] = []
    if first["output"] != second["output"] or first["report_bytes"] != second["report_bytes"]:
        errors.append("normalizer output is not deterministic")
    report = first["report"]
    output_path = first["output_path"]
    errors.extend(_accounting_errors(report, expect))
    errors.extend(_admission_errors(scenario, report))
    errors.extend(_output_errors(output_path, report, expect, validator))
    exported = export_jsonl(output_path, admitted_trajectory_ids(report))
    errors.extend(_export_errors(scenario, report, exported))
    return errors


def _normalize_scenario(scenario: Path, directory: Path) -> dict[str, Any]:
    output_path = directory / "canonical.jsonl"
    report_path = directory / "report.json"
    report = normalize_files(
        input_path=scenario / "input.jsonl",
        run_manifest_path=scenario / "run_manifest.json",
        model_admission_path=scenario / "model_admission.json",
        output_path=output_path,
        report_path=report_path,
    )
    return {
        "report": report,
        "report_bytes": report_path.read_bytes(),
        "output": output_path.read_bytes(),
        "output_path": output_path,
    }


def _accounting_errors(report: dict[str, Any], expect: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    records = report.get("records")
    if not isinstance(records, list):
        return ["decision report is missing records"]
    counts = Counter(
        row.get("status") for row in records if isinstance(row, dict)
    )
    for name in _DECISIONS:
        key = f"{name}_count"
        if report.get(key) != expect.get(key):
            errors.append(f"{key} does not match the frozen expectation")
        if counts[name] != report.get(key):
            errors.append(f"{key} does not match decision rows")
    if sum(counts[name] for name in _DECISIONS) != len(records):
        errors.append("decision report contains an unknown status")
    return errors


def _admission_errors(scenario: Path, report: dict[str, Any]) -> list[str]:
    path = scenario / "model_admission.json"
    admission = json.loads(path.read_text(encoding="utf-8"))
    manifest = json.loads(
        (scenario / "run_manifest.json").read_text(encoding="utf-8")
    )
    errors: list[str] = []
    if admission.get("decision") != "accepted":
        errors.append("fixture admission is not accepted")
    if admission.get("cloud_fallback_allowed") is not False:
        errors.append("fixture admission allows cloud fallback")
    body = {
        key: value for key, value in admission.items() if key != "evidence_digest"
    }
    if admission.get("evidence_digest") != sha256_json(body):
        errors.append("admission evidence_digest does not match the report body")
    file_hash = sha256_file(path)
    if manifest.get("admission_report_sha256") != file_hash:
        errors.append("run manifest admission digest does not match admission bytes")
    if report.get("admission_report_sha256") != file_hash:
        errors.append("decision report admission digest does not match admission bytes")
    return errors


def _output_errors(
    path: Path,
    report: dict[str, Any],
    expect: dict[str, Any],
    validator: Any,
) -> list[str]:
    records = _jsonl_records(path)
    errors = _schema_errors(path, records, validator)
    errors.extend(_identity_errors(records))
    errors.extend(_record_policy_errors(records))
    if len(records) != report.get("accepted_count"):
        errors.append("canonical row count does not match accepted_count")
    successful = sum(
        1 for record in records if record.get("terminal_disposition") == "successful"
    )
    if successful != expect.get("successful_terminal_count"):
        errors.append("successful terminal count does not match the expectation")
    errors.extend(_leak_errors(report, path.read_text(encoding="utf-8"), ""))
    return errors


def _jsonl_records(path: Path) -> list[dict[str, Any]]:
    if path.stat().st_size == 0:
        return []
    records: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            parsed = json.loads(line)
            if isinstance(parsed, dict):
                records.append(parsed)
    return records


def _schema_errors(
    path: Path, records: list[dict[str, Any]], validator: Any
) -> list[str]:
    errors: list[str] = []
    for index, record in enumerate(records, start=1):
        for error in validator.iter_errors(record):
            errors.append(f"{path.name}:{index} {error.message}")
    return errors


def _identity_errors(records: list[dict[str, Any]]) -> list[str]:
    seen: set[str] = set()
    errors: list[str] = []
    for record in records:
        trajectory_id = record.get("trajectory_id")
        if not isinstance(trajectory_id, str) or not trajectory_id.strip():
            errors.append("accepted record is missing trajectory_id")
            continue
        if trajectory_id in seen:
            errors.append(f"duplicate trajectory id {trajectory_id}")
        seen.add(trajectory_id)
        errors.extend(hash_errors(record))
    return errors


def _record_policy_errors(records: list[dict[str, Any]]) -> list[str]:
    errors: list[str] = []
    for record in records:
        errors.extend(false_success_errors(record))
        errors.extend(hidden_reasoning_errors(record))
        errors.extend(cloud_fallback_errors(record))
        for text in _trainable_strings(record):
            errors.extend(trainable_text_errors(text))
    return errors


def _trainable_strings(record: dict[str, Any]) -> list[str]:
    texts: list[str] = []
    events = record.get("events")
    if isinstance(events, list):
        texts.extend(_event_strings(events))
    payload = record.get("software_payload")
    if isinstance(payload, dict):
        texts.extend(
            value for value in payload.values() if isinstance(value, str)
        )
    return texts


def _event_strings(events: list[Any]) -> list[str]:
    texts: list[str] = []
    for event in events:
        if not isinstance(event, dict):
            continue
        content = event.get("content")
        if isinstance(content, str):
            texts.append(content)
    return texts


def _export_errors(scenario: Path, report: dict[str, Any], exported: str) -> list[str]:
    errors = _leak_errors(report, "", exported)
    for line in exported.splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        errors.extend(_exported_row_errors(row))
    if scenario.name == "accepted" and exported != OBSERVABLE_FIXTURE.read_text(
        encoding="utf-8"
    ):
        errors.append("accepted observable export drifted from the consumer fixture")
    if report.get("accepted_count") == 0 and exported:
        errors.append("non-accepted scenario produced a trainable export")
    return errors


def _exported_row_errors(row: dict[str, Any]) -> list[str]:
    errors = list(future_event_errors(row))
    errors.extend(hidden_reasoning_errors(row))
    errors.extend(cloud_fallback_errors(row))
    errors.extend(_message_contract_errors(row))
    for text in _message_texts(row):
        errors.extend(trainable_text_errors(text))
    for text in _metadata_texts(row):
        errors.extend(trainable_text_errors(text))
    return errors


def _metadata_texts(row: dict[str, Any]) -> list[str]:
    meta = row.get("_prometheus")
    if not isinstance(meta, dict):
        return []
    return [value for value in meta.values() if isinstance(value, str)]


def _message_contract_errors(row: dict[str, Any]) -> list[str]:
    messages = row.get("messages")
    if not isinstance(messages, list) or not messages:
        return ["observable row is missing messages"]
    errors: list[str] = []
    for message in messages:
        errors.extend(_one_message_errors(message))
    return errors


def _one_message_errors(message: Any) -> list[str]:
    if not isinstance(message, dict):
        return ["observable message is not an object"]
    role = message.get("role")
    content = message.get("content")
    if role not in {"user", "assistant", "system", "tool"}:
        return [f"observable role {role!r} is not a consumer role"]
    if not isinstance(content, str):
        return ["observable message content is not a string"]
    return []


def _message_texts(row: dict[str, Any]) -> list[str]:
    messages = row.get("messages")
    if not isinstance(messages, list):
        return []
    return [
        message["content"]
        for message in messages
        if isinstance(message, dict) and isinstance(message.get("content"), str)
    ]


def _leak_errors(report: dict[str, Any], output_text: str, exported: str) -> list[str]:
    blocked = [
        row.get("trajectory_id")
        for row in report.get("records") or []
        if isinstance(row, dict)
        and row.get("status") != "accepted"
        and isinstance(row.get("trajectory_id"), str)
    ]
    return [
        f"{trajectory_id} leaked into a trainable export"
        for trajectory_id in blocked
        if trajectory_id in output_text or trajectory_id in exported
    ]


def _digest_mismatch_errors() -> list[str]:
    scenario = SCENARIO_ROOT / "accepted"
    with tempfile.TemporaryDirectory() as tmp:
        dest = Path(tmp)
        for name in _SCENARIO_FILES:
            shutil.copy(scenario / name, dest / name)
        _rewrite_mismatched_manifest(dest / "run_manifest.json")
        report = normalize_files(
            input_path=dest / "input.jsonl",
            run_manifest_path=dest / "run_manifest.json",
            model_admission_path=dest / "model_admission.json",
            output_path=dest / "canonical.jsonl",
            report_path=dest / "report.json",
        )
    if report.get("accepted_count") != 0:
        return ["digest mismatch was accepted"]
    reasons = [
        code
        for row in report.get("records") or []
        if isinstance(row, dict)
        for code in row.get("reason_codes") or []
    ]
    if "admission_digest_mismatch" not in reasons:
        return ["digest mismatch did not fail closed"]
    return []


def _rewrite_mismatched_manifest(path: Path) -> None:
    manifest = json.loads(path.read_text(encoding="utf-8"))
    manifest["admission_report_sha256"] = "0" * 64
    path.write_text(
        json.dumps(manifest, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
        + "\n",
        encoding="utf-8",
    )


def _prefixed(name: str, errors: list[str]) -> list[str]:
    return [f"{name}: {error}" for error in errors]
