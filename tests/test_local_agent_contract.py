"""Offline Hermes trajectory, admission, and observable-action contract."""

from __future__ import annotations

import json

from lib.ci_policy import false_success_errors
from lib.local_agent_contract import _exported_row_errors, run_contract
from lib.local_agent_privacy import (
    trainable_text_errors,
)

from export_observable_actions import export_jsonl, export_jsonls, export_record


def test_local_agent_contract_accepts_synthetic_fixtures():
    assert run_contract() == []


def test_failed_verifier_cannot_become_successful():
    record = {
        "terminal_disposition": "successful",
        "execution": {"producer_completed": True},
        "execution_provenance": {"verifier": {"outcome": "fail"}},
    }
    assert false_success_errors(record) == [
        "failed verifier became a successful trajectory"
    ]


def test_observable_export_drops_hidden_reasoning_fields():
    exported = export_record(
        {
            "trajectory_id": "traj-1",
            "events": [
                {
                    "actor": {"type": "agent"},
                    "content": "Apply the fix.",
                    "event_type": "message",
                    "reasoning": "hidden chain of thought",
                    "timestamp": "2026-09-21T12:00:00Z",
                }
            ],
        }
    )
    assert exported is not None
    assert exported["messages"] == [{"role": "assistant", "content": "Apply the fix."}]
    assert "reasoning" not in exported["messages"][0]
    assert exported["_prometheus"]["source_trajectory_id"] == "traj-1"


def test_observable_export_maps_bot_messages_to_assistant():
    exported = export_record(
        {"events": [{"actor": {"type": "bot"}, "content": "Automated result"}]}
    )
    assert exported == {"messages": [{"role": "assistant", "content": "Automated result"}]}


def test_observable_export_rejects_private_trainable_text():
    try:
        export_record(
            {"events": [{"actor": {"type": "agent"}, "content": "file:///etc/passwd"}]}
        )
    except ValueError as exc:
        assert "private file URI" in str(exc)
    else:
        raise AssertionError("private URI was exported")


def test_observable_export_requires_existing_admitted_input(tmp_path):
    missing = tmp_path / "missing.jsonl"
    try:
        export_jsonl(missing, set())
    except FileNotFoundError:
        pass
    else:
        raise AssertionError("missing input was exported as an empty dataset")

    path = tmp_path / "raw.jsonl"
    path.write_text(
        '{"trajectory_id":"unadmitted","events":[{"actor":{"type":"agent"},"content":"x"}]}\n'
    )
    try:
        export_jsonl(path, {"accepted"})
    except ValueError as exc:
        assert "admitted trajectory ids" in str(exc)
    else:
        raise AssertionError("unadmitted trajectory was exported")


def test_observable_export_validates_admission_across_shards(tmp_path):
    first = tmp_path / "first.jsonl"
    second = tmp_path / "second.jsonl"
    first.write_text(
        '{"trajectory_id":"first","events":[{"actor":{"type":"agent"},"content":"one"}]}\n'
    )
    second.write_text(
        '{"trajectory_id":"second","events":[{"actor":{"type":"agent"},"content":"two"}]}\n'
    )
    exported = export_jsonls([first, second], {"first", "second"})
    assert [json.loads(line)["messages"][0]["content"] for line in exported.splitlines()] == [
        "one",
        "two",
    ]


def test_observable_export_rejects_duplicate_trajectory_ids(tmp_path):
    path = tmp_path / "duplicate.jsonl"
    row = (
        '{"trajectory_id":"same","events":'
        '[{"actor":{"type":"agent"},"content":"duplicate"}]}\n'
    )
    path.write_text(row + row)
    try:
        export_jsonl(path, {"same"})
    except ValueError as exc:
        assert "duplicate trajectory_id same" in str(exc)
    else:
        raise AssertionError("duplicate trajectory rows were exported")


def test_observable_export_rejects_missing_or_invalid_trajectory_ids(tmp_path):
    path = tmp_path / "invalid-ids.jsonl"
    for trajectory_id in (None, "", "   ", 7):
        record = {
            "events": [{"actor": {"type": "agent"}, "content": "output"}]
        }
        if trajectory_id is not None:
            record["trajectory_id"] = trajectory_id
        path.write_text(json.dumps(record) + "\n")
        try:
            export_jsonl(path, set())
        except ValueError as exc:
            assert "trajectory_id" in str(exc)
        else:
            raise AssertionError(f"invalid trajectory_id {trajectory_id!r} was exported")


def test_observable_export_rejects_unbalanced_hidden_reasoning():
    try:
        export_record(
            {"events": [{"actor": {"type": "agent"}, "content": "<think>secret"}]}
        )
    except ValueError as exc:
        assert "hidden reasoning" in str(exc)
    else:
        raise AssertionError("unbalanced hidden reasoning was exported")


def test_observable_export_rejects_admitted_record_without_messages(tmp_path):
    path = tmp_path / "empty.jsonl"
    path.write_text('{"trajectory_id":"empty","events":[]}\n')
    try:
        export_jsonl(path, {"empty"})
    except ValueError as exc:
        assert "empty" in str(exc)
    else:
        raise AssertionError("admitted record without messages was silently omitted")


def test_trainable_text_rejects_secrets_and_private_uris():
    assert any(
        "secret" in error
        for error in trainable_text_errors("token = ghp_AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA")
    )
    assert any(
        "private" in error
        for error in trainable_text_errors("see file:///etc/passwd")
    )


def test_trainable_text_rejects_authorization_headers():
    assert any(
        "secret" in error
        for error in trainable_text_errors(
            "Authorization: Bearer topsecretvalue12345"
        )
    )


def test_observable_metadata_rejects_private_source_identity():
    row = {
        "messages": [{"role": "assistant", "content": "Safe output"}],
        "_prometheus": {"source_trajectory_id": "file:///private/run"},
    }
    assert any("private file URI" in error for error in _exported_row_errors(row))
