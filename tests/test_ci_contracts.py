"""CI contract jobs: trajectory, corpus integrity, consumer, release, inventory audit."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from lib.ci_contracts import (
    is_real_check_run_detail,
    iter_uri_fields,
    private_reference_errors,
    silent_truncation_errors,
    validation_evidence_errors,
)
from lib.github_client import GitHubClient, GitHubError

import corpus_integrity
from consumer_contract import consume, future_event_errors
from corpus_integrity import _resolve_records
from hf_release_verify import (
    ReleaseVerifyError,
    refuse_overwrite_immutable_tag,
    refuse_pull_request_context,
    resumable_upload_plan,
    verify,
)
from source_inventory_audit import (
    build_report as build_audit_report,
    diff_repositories,
    diff_terminal_candidates,
)
from validate_jsonl import load_schema, validate_file

try:
    import jsonschema
except ImportError:
    jsonschema = None

ROOT = Path(__file__).resolve().parents[1]
V1_FIXTURE = ROOT / "tests" / "fixtures" / "v1" / "software_valid.jsonl"


def _v1_record() -> dict:
    return json.loads(V1_FIXTURE.read_text())


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


def test_blank_license_is_rejected(tmp_path):
    v0, v1 = _validators()
    record = _v1_record()
    record["license"] = "   "
    path = tmp_path / "blank-license.jsonl"
    path.write_text(json.dumps(record) + "\n")
    errors = validate_file(path, v0, v1, strict_policy=True)
    assert any("license is missing" in error for error in errors)


def test_check_run_conclusions_are_distinguished_from_checklists():
    assert is_real_check_run_detail("Build & Test=success")
    assert is_real_check_run_detail("combined_status=success")
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


def test_silent_truncation_without_marker_is_rejected():
    record = {"patch": "a" * (96 * 1024)}
    assert any(
        "silent patch truncation" in error for error in silent_truncation_errors(record)
    )
    declared = {"patch": "# Truncated unified diff for training\n" + ("a" * 100)}
    assert silent_truncation_errors(declared) == []


def test_corpus_integrity_passes_frozen_inventory(tmp_path):
    report = corpus_integrity.build_report(
        ROOT / "datasets" / "inventory" / "v0.7", tmp_path
    )
    assert report["ok"], report["errors"]
    assert (tmp_path / "duplicates.jsonl").is_file()
    groups = [
        json.loads(line)
        for line in (tmp_path / "duplicates.jsonl").read_text().splitlines()
        if line.strip()
    ]
    assert groups
    assert all("kind" in row and "exact" in row for row in groups)
    assert report["duplicates"]["exact_count"] >= 1
    assert report["counts"]["unresolved_jsonl_records"] >= 0


def test_mutable_jsonl_cannot_enter_positive_release(tmp_path):
    candidates = [
        {
            "candidate_id": "github:repository:R_open:pull:PR_open",
            "repository_name_with_owner": "rmems/open-repo",
            "pull_request_number": 1,
            "state": "watchlist_open",
            "source_state": "open",
            "primary_reason": "mutable_open_pull_request",
            "reason_codes": ["mutable_open_pull_request"],
        }
    ]
    jsonl = tmp_path / "datasets" / "jsonl"
    jsonl.mkdir(parents=True)
    rec = {
        "id": "rmems-open-repo-1",
        "repo": "rmems/open-repo",
        "pr_number": 1,
    }
    (jsonl / "open.jsonl").write_text(json.dumps(rec) + "\n")
    monkey_root = tmp_path
    original = corpus_integrity.ROOT
    corpus_integrity.ROOT = monkey_root
    try:
        errors, _, _, unresolved = _resolve_records(candidates)
    finally:
        corpus_integrity.ROOT = original
    assert any("mutable candidate" in error for error in errors)
    assert unresolved == []


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


def test_hf_release_verify_refuses_immutable_tag_overwrite():
    with pytest.raises(ReleaseVerifyError, match="overwrite immutable tag"):
        refuse_overwrite_immutable_tag("v0.7.0", "aaa", {"v0.7.0": "bbb"})
    refuse_overwrite_immutable_tag("v0.7.0", "aaa", {})
    plan = resumable_upload_plan([{"path": "a.jsonl", "sha256": "ab", "bytes": 1}])
    assert plan[0]["resume_key"] == "sha256:ab"


def test_hf_release_verify_refuses_pull_request_event(monkeypatch, tmp_path):
    monkeypatch.setenv("GITHUB_EVENT_NAME", "pull_request")
    monkeypatch.setenv("HF_TOKEN", "should-not-be-here")
    with pytest.raises(ReleaseVerifyError, match="pull_request"):
        refuse_pull_request_context()
    monkeypatch.setenv("GITHUB_EVENT_NAME", "release")
    jsonl = tmp_path / "jsonl"
    jsonl.mkdir()
    (jsonl / "a.jsonl").write_bytes(b"{}\n")
    result = verify(
        tag="v0.7.0",
        dataset_repo="rmems/operation-prometheus-trajectories",
        dirs=(jsonl, tmp_path / "missing-parquet"),
        remotes={"tags": {}, "downloaded": {}},
    )
    assert result["ok"]
    assert result["release_manifest"]["jsonl"][0]["path"] == "a.jsonl"


def test_pr_workflows_never_receive_hf_token():
    ci = (ROOT / ".github" / "workflows" / "ci.yml").read_text()
    assert "HF_TOKEN" not in ci
    quality = ROOT / ".github" / "workflows"
    for path in quality.glob("*.yml"):
        text = path.read_text()
        if "HF_TOKEN" not in text:
            continue
        assert path.name == "hf_release_verify.yml"
        header = text.split("jobs:", 1)[0]
        assert "pull_request" not in header


def test_source_inventory_audit_reports_repo_and_terminal_drift():
    frozen_repos = [
        {"repository_id": "R_old", "name_with_owner": "rmems/old-name"},
        {"repository_id": "R_gone", "name_with_owner": "rmems/removed"},
    ]
    live_repos = [
        {"id": "R_old", "name_with_owner": "rmems/renamed"},
        {"id": "R_new", "name_with_owner": "rmems/new-repo"},
    ]
    repo_diff = diff_repositories(frozen_repos, live_repos)
    assert repo_diff["renamed"][0]["to"] == "rmems/renamed"
    assert repo_diff["new"][0]["name_with_owner"] == "rmems/new-repo"
    assert repo_diff["deleted"][0]["name_with_owner"] == "rmems/removed"

    frozen_candidates = [
        {
            "candidate_id": "github:repository:R_old:pull:PR_1",
            "source_state": "merged",
        }
    ]
    live_prs = [
        {
            "id": "PR_1",
            "repository_id": "R_old",
            "state": "closed",
            "merged_at": None,
            "number": 1,
        },
        {
            "id": "PR_2",
            "repository_id": "R_old",
            "state": "merged",
            "merged_at": "2026-09-01T00:00:00Z",
            "number": 2,
            "repository_name_with_owner": "rmems/renamed",
        },
    ]
    changed = diff_terminal_candidates(frozen_candidates, live_prs)
    kinds = {row["kind"] for row in changed}
    assert "source_state_changed" in kinds
    assert "new_terminal_candidate" in kinds


def test_source_inventory_audit_is_read_only_and_refuses_mutations():
    report = build_audit_report(
        [{"repository_id": "R1", "name_with_owner": "rmems/repo"}],
        [],
        {
            "repositories": [{"id": "R1", "name_with_owner": "rmems/repo"}],
            "pull_requests": [],
        },
    )
    assert report["read_only"] is True
    assert report["creates_source_issues"] is False
    assert report["mutates_source_repositories"] is False
    with pytest.raises(GitHubError, match="non-query"):
        GitHubClient._validate_graphql_document(
            "mutation CreateIssue { createIssue { id } }"
        )


def test_shared_files_guard_and_existing_gates_remain_named():
    ci = (ROOT / ".github" / "workflows" / "ci.yml").read_text()
    for job in (
        "lint",
        "test",
        "validate",
        "status-up-to-date",
        "shared-files-guard",
        "trajectory-contract",
        "corpus-integrity",
        "consumer-contract",
    ):
        assert f"{job}:" in ci
