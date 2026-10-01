"""Offline Hermes trajectory, admission, and observable-action contract."""

from __future__ import annotations

from lib.local_agent_contract import run_contract
from lib.local_agent_privacy import (
    false_success_errors,
    trainable_text_errors,
)

from export_observable_actions import export_record


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


def test_trainable_text_rejects_secrets_and_private_uris():
    assert any(
        "secret" in error
        for error in trainable_text_errors("token = ghp_AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA")
    )
    assert any(
        "private" in error
        for error in trainable_text_errors("see file:///etc/passwd")
    )
