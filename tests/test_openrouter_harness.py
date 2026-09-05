"""Dry-run / live-gate tests for the OpenRouter bugfix synth harness."""

from __future__ import annotations

import json
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import pytest

import generate_bugfix_synth as harness
from lib.bugfix_synth import EXP_ID, LOCKED_MODEL, VARIANT_KNOBS, fixture_chat_response
from providers.openrouter.client import (
    CHAT_COMPLETIONS_URL,
    OpenRouterClient,
    OpenRouterError,
    assert_locked_model,
    build_chat_request,
    redact_planned_request,
)

def _boom(*_args, **_kwargs):
    raise AssertionError("network was invoked")


def _seed_from_messages(messages: list[dict[str, str]]) -> tuple[dict, str]:
    user = messages[1]["content"]
    start = user.find("{")
    end = user.rfind("}")
    payload = json.loads(user[start : end + 1])
    seed = {
        "id": payload["seed_id"],
        "repo": payload["repo"],
        "pr_number": 1,
        "language": payload["language"],
        "domain": payload["domain"],
        "issue_context": payload["issue_context"],
        "before_context": payload["before_context"],
        "validation": [{"type": kind, "result": "pass"} for kind in payload["validation_kinds"]]
        or [{"type": "ci", "result": "pass"}],
        "patch": "not-used-by-fixture",
    }
    return seed, payload["variant"]


def test_model_lock_rejects_other_ids():
    assert assert_locked_model(LOCKED_MODEL) == LOCKED_MODEL
    with pytest.raises(OpenRouterError, match="not allowed"):
        assert_locked_model("openai/gpt-4o")


def test_planned_request_redacts_authorization():
    planned = build_chat_request(
        [{"role": "user", "content": "hi"}],
        api_key="sk-or-v1-not-a-real-key-123456",
    )
    assert planned.url == CHAT_COMPLETIONS_URL
    dumped = redact_planned_request(planned)
    assert dumped["headers"]["Authorization"] == "Bearer [REDACTED]"
    assert "sk-or-v1-not-a-real-key-123456" not in json.dumps(dumped)


def test_client_complete_requires_key():
    client = OpenRouterClient(api_key=None)
    with pytest.raises(OpenRouterError, match="OPENROUTER_API_KEY"):
        client.complete([{"role": "user", "content": "hi"}])


def test_dry_run_cli_no_network_no_key(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.setattr(urllib.request, "urlopen", _boom)
    monkeypatch.setattr(urllib.request.OpenerDirector, "open", _boom)

    rc = harness.main(
        [
            "--exp",
            EXP_ID,
            "--dry-run",
            "--out-dir",
            str(tmp_path),
            "--jsonl-dir",
            str(ROOT / "datasets" / "jsonl"),
            "--seed-manifest",
            str(ROOT / "experiments" / EXP_ID / "seed-manifest.json"),
        ]
    )
    assert rc == 0
    ledger_path = tmp_path / "yield-ledger.jsonl"
    rows = [json.loads(line) for line in ledger_path.read_text().splitlines() if line]
    assert len(rows) == 8 * len(VARIANT_KNOBS)
    assert all(row["dry_run"] is True for row in rows)
    assert all(row["teacher_model"] == LOCKED_MODEL for row in rows)
    assert all(row["exp_id"] == EXP_ID for row in rows)
    assert {row["decision"] for row in rows} == {"keep"}
    planned = list((tmp_path / "planned_requests").glob("*.json"))
    assert len(planned) == 24
    sample = json.loads(planned[0].read_text())
    assert sample["url"] == CHAT_COMPLETIONS_URL
    assert "Authorization" not in sample["headers"]
    summary = json.loads((tmp_path / "run-summary.json").read_text())
    assert summary["network"] is False
    assert summary["attempts"] == 24


def test_default_is_dry_run(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.setattr(urllib.request.OpenerDirector, "open", _boom)
    rc = harness.main(["--exp", EXP_ID, "--out-dir", str(tmp_path), "--variants-per-seed", "1"])
    assert rc == 0
    rows = [json.loads(line) for line in (tmp_path / "yield-ledger.jsonl").read_text().splitlines()]
    assert len(rows) == 8
    assert all(row["dry_run"] is True for row in rows)


def test_wrong_exp_and_model_exit_2(tmp_path: Path):
    assert harness.main(["--exp", "EXP-OTHER", "--out-dir", str(tmp_path)]) == 2
    assert (
        harness.main(
            ["--exp", EXP_ID, "--model", "openai/gpt-4o", "--out-dir", str(tmp_path)]
        )
        == 2
    )


def test_live_without_key_is_gated(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.setattr(urllib.request.OpenerDirector, "open", _boom)
    rc = harness.main(["--exp", EXP_ID, "--live", "--out-dir", str(tmp_path)])
    assert rc == 2
    assert not (tmp_path / "yield-ledger.jsonl").exists()


def test_live_and_dry_run_conflict(tmp_path: Path):
    rc = harness.main(
        ["--exp", EXP_ID, "--live", "--dry-run", "--out-dir", str(tmp_path)]
    )
    assert rc == 2


def test_live_path_uses_injected_complete(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-v1-test-not-real-1234567890abcd")
    calls: list[str] = []

    def fake_complete(self, messages, *, model=LOCKED_MODEL, temperature=0.7):
        calls.append(model)
        seed, variant = _seed_from_messages(messages)
        return fixture_chat_response(seed, variant)

    monkeypatch.setattr(OpenRouterClient, "complete", fake_complete)
    monkeypatch.setattr(urllib.request.OpenerDirector, "open", _boom)
    rc = harness.main(
        [
            "--exp",
            EXP_ID,
            "--live",
            "--out-dir",
            str(tmp_path),
            "--variants-per-seed",
            "1",
        ]
    )
    assert rc == 0
    assert len(calls) == 8
    assert all(model == LOCKED_MODEL for model in calls)
    rows = [json.loads(line) for line in (tmp_path / "yield-ledger.jsonl").read_text().splitlines()]
    assert len(rows) == 8
    assert all(row["dry_run"] is False for row in rows)
