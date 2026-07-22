"""Collector assembly + normalizer tests using fixtures (mocked client)."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import jsonschema
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from lib.normalize import normalize_record, outcome_for  # noqa: E402
from lib.raw_record import (  # noqa: E402
    collect_pr,
    parse_linked_issue_numbers,
    write_raw_record,
)

FIXTURES = ROOT / "tests" / "fixtures" / "github"
SCHEMA = ROOT / "schemas" / "pr_trajectory.schema.json"
CARD = ROOT / "datasets" / "cards" / "corinth-canal-v0.json"


class FakeClient:
    """Map GitHub REST paths to fixture payloads."""

    token = "fixture-token"
    base_url = "https://api.github.com"

    def get_json(self, path_or_url: str) -> Any:
        path = path_or_url.replace(self.base_url, "")
        if path.startswith("/repos/rmems/corinth-canal/pulls/89") and "comments" not in path and "reviews" not in path and "commits" not in path and "files" not in path:
            return json.loads((FIXTURES / "pull_89.json").read_text())
        if "check-runs" in path:
            return json.loads((FIXTURES / "check_runs_89.json").read_text())
        if path.endswith("/status") or "/status" in path:
            return json.loads((FIXTURES / "status_89.json").read_text())
        if path.endswith("/issues/74"):
            return json.loads((FIXTURES / "issue_74.json").read_text())
        raise AssertionError(f"unexpected get_json path: {path_or_url}")

    def get_json_with_headers(self, path_or_url: str) -> tuple[Any, dict[str, str]]:
        return self.get_json(path_or_url), {}

    def get_text(self, path_or_url: str, *, accept: str = "") -> str:
        return (FIXTURES / "diff_89.diff").read_text()

    def get_all(self, path: str, *, per_page: int = 100) -> list:
        if path.endswith("/issues/89/comments"):
            return json.loads((FIXTURES / "issue_comments_89.json").read_text())
        if path.endswith("/pulls/89/comments"):
            return json.loads((FIXTURES / "review_comments_89.json").read_text())
        if path.endswith("/pulls/89/reviews"):
            return json.loads((FIXTURES / "reviews_89.json").read_text())
        if path.endswith("/pulls/89/commits"):
            return json.loads((FIXTURES / "commits_89.json").read_text())
        if path.endswith("/pulls/89/files"):
            return json.loads((FIXTURES / "files_89.json").read_text())
        raise AssertionError(f"unexpected get_all path: {path}")


def test_collect_pr_fixture(tmp_path: Path):
    if not (FIXTURES / "pull_89.json").exists():
        pytest.skip("fixtures missing")
    record = collect_pr(FakeClient(), "rmems/corinth-canal", 89)
    assert record["source"]["pr_number"] == 89
    assert record["pull"]["merged"] is True
    assert record["linked_issues"]
    assert record["linked_issues"][0]["number"] == 74
    path = write_raw_record(record, tmp_path)
    assert path.exists()
    reloaded = json.loads(path.read_text())
    assert reloaded["files"]


def test_normalize_validates_against_schema():
    if not (FIXTURES / "pull_89.json").exists():
        pytest.skip("fixtures missing")
    raw = collect_pr(FakeClient(), "rmems/corinth-canal", 89)
    card = json.loads(CARD.read_text()) if CARD.exists() else {}
    traj = normalize_record(raw, card)
    schema = json.loads(SCHEMA.read_text())
    jsonschema.Draft7Validator(schema).validate(traj)
    assert traj["id"] == "corinth-canal-89"
    assert traj["training_use"] == "validation"
    assert traj["outcome"] == "merged"
    assert any(s["author"] == "reviewer-x" for s in traj.get("review_signals", []))
    assert not any("codeant" in (s.get("author") or "").lower() for s in traj.get("review_signals", []))
    assert "https://github.com/rmems/corinth-canal/pull/89" in traj["source_urls"]


def test_feature_bucket_maps_to_other_training_use():
    if not (FIXTURES / "pull_89.json").exists():
        pytest.skip("fixtures missing")
    raw = collect_pr(FakeClient(), "rmems/corinth-canal", 89)
    # Use a PR number NOT in TRAINING_USE_OVERRIDE so card buckets are exercised.
    raw["source"]["pr_number"] = 999
    raw["source"]["repo"] = "rmems/other-sandbox"
    card = {
        "training_use_buckets": {"feature": [999]},
        "language": "Rust",
        "domains": ["ml-infra"],
    }
    traj = normalize_record(raw, card)
    assert traj["training_use"] == "other"
    assert traj["task_type"] in ("feature", "test", "other")


def test_parse_closes_colon_syntax():
    body = "Closes: #10\nFixes: https://github.com/acme/widgets/issues/3\nResolves: other/proj#7"
    found = parse_linked_issue_numbers(body, "rmems", "corinth-canal")
    assert ("rmems", "corinth-canal", 10) in found
    assert ("acme", "widgets", 3) in found
    assert ("other", "proj", 7) in found


def test_open_draft_outcome_is_open():
    assert outcome_for({"pull": {"state": "open", "draft": True, "merged": False}}) == "open"
    assert outcome_for({"pull": {"state": "open", "draft": False, "merged": False}}) == "open"
    assert outcome_for({"pull": {"state": "closed", "draft": True, "merged": False}}) == "closed"
    assert outcome_for({"pull": {"merged": True, "draft": True, "state": "closed"}}) == "merged"


def test_zero_tests_failed_is_pass():
    from lib.normalize import extract_validation

    raw = {
        "pull": {"body": "## Validation\n\n0 tests failed, all green.\n"},
        "checks": {},
    }
    events = extract_validation(raw)
    assert events[0]["type"] == "test"
    assert events[0]["result"] == "pass"


def test_allowlist_case_insensitive_same_repo():
    from lib.raw_record import _norm_repo

    assert _norm_repo("Rmems/Corinth-Canal") == _norm_repo("rmems/corinth-canal")


def test_empty_combined_status_pending_ignored_when_checks_pass():
    from lib.normalize import extract_validation

    raw = {
        "pull": {"body": "## Validation\n\nAll good.\n"},
        "checks": {
            "check_runs": [
                {"name": "test", "status": "completed", "conclusion": "success"},
            ],
            "combined_status": {"state": "pending", "statuses": []},
        },
    }
    events = extract_validation(raw)
    assert not any(
        e.get("detail", "").startswith("combined_status=") for e in events
    )
    assert any(e["type"] == "ci" and e["result"] == "pass" for e in events)


def test_nonzero_error_count_fails_validation():
    from lib.normalize import extract_validation

    raw = {
        "pull": {"body": "## Testing\n\nERROR SUMMARY: 1 error\n"},
        "checks": {},
    }
    events = extract_validation(raw)
    assert events[0]["type"] == "test"
    assert events[0]["result"] == "fail"


def test_zero_skipped_is_pass():
    from lib.normalize import extract_validation

    raw = {
        "pull": {"body": "## Validation\n\n100 passed, 0 skipped\n"},
        "checks": {},
    }
    events = extract_validation(raw)
    assert events[0]["result"] == "pass"


def test_testing_heading_is_validation_evidence():
    from lib.normalize import extract_validation

    raw = {
        "pull": {"body": "## Testing\n\nAll unit tests passed.\n"},
        "checks": {},
    }
    events = extract_validation(raw)
    assert events[0]["type"] == "test"
    assert "unit tests" in events[0]["detail"].lower()


def test_codex_review_wrapper_not_in_signals():
    from lib.normalize import extract_review_signals

    raw = {
        "reviews": [
            {
                "user_login": "chatgpt-codex-connector",
                "user_type": "Bot",
                "state": "COMMENTED",
                "body": (
                    "### 💡 Codex Review\n\nHere are some automated review suggestions.\n"
                    "Your team has set up Codex to review pull requests in this repo.\n"
                    "About Codex in GitHub\n"
                ),
            },
            {
                "user_login": "reviewer-x",
                "user_type": "User",
                "state": "CHANGES_REQUESTED",
                "body": "Please fix the rate limit double-read bug in github_client.",
            },
        ],
        "review_comments": [],
        "issue_comments": [],
    }
    signals = extract_review_signals(raw)
    assert len(signals) == 1
    assert signals[0]["author"] == "reviewer-x"
    assert not any("Codex Review" in (s.get("comment") or "") for s in signals)


def test_empty_suggestion_block_omits_field():
    from lib.normalize import extract_review_signals

    raw = {
        "reviews": [],
        "review_comments": [
            {
                "user_login": "reviewer-x",
                "user_type": "User",
                "body": "Delete this line:\n```suggestion\n\n```\n",
            }
        ],
        "issue_comments": [],
    }
    signals = extract_review_signals(raw)
    assert len(signals) == 1
    assert "suggestion" not in signals[0]


def test_resolved_failed_prose_is_pass():
    from lib.normalize import extract_validation

    raw = {
        "pull": {
            "body": "## Validation\n\nPreviously failed tests are now passing.\n"
        },
        "checks": {},
    }
    events = extract_validation(raw)
    assert events[0]["result"] == "pass"


def test_review_app_checks_separated_from_ci():
    from lib.normalize import extract_validation

    raw = {
        "pull": {"body": ""},
        "checks": {
            "check_runs": [
                {"name": "CPU Tests", "status": "completed", "conclusion": "success"},
                {
                    "name": "Kilo Code Review",
                    "status": "completed",
                    "conclusion": "failure",
                },
            ],
            "combined_status": {"state": "success", "statuses": [{"context": "ci"}]},
        },
    }
    events = extract_validation(raw)
    ci = [e for e in events if e["type"] == "ci" and not e["detail"].startswith("combined")]
    rev = [e for e in events if e["type"] == "other" and e["detail"].startswith("review_apps")]
    assert ci and ci[0]["result"] == "pass"
    assert rev and rev[0]["result"] == "fail"


def test_load_card_missing_path_raises(tmp_path: Path):
    from lib.normalize import load_card

    assert load_card(None) == {}
    missing = tmp_path / "nope.json"
    try:
        load_card(missing)
        raise AssertionError("expected FileNotFoundError")
    except FileNotFoundError:
        pass


def test_sidecar_path_must_stay_under_raw_dir(tmp_path: Path):
    from lib.normalize import _load_diff_text

    secret = tmp_path / "secret.txt"
    secret.write_text("PRIVATE", encoding="utf-8")
    raw_dir = tmp_path / "raw"
    raw_dir.mkdir()
    raw_path = raw_dir / "pr-1.json"
    raw_path.write_text("{}", encoding="utf-8")
    # Escape via ..
    raw = {"diff": {"sidecar_path": "../secret.txt", "inline": None}, "files": []}
    assert "PRIVATE" not in _load_diff_text(raw, raw_path)
    # Absolute path rejected
    raw2 = {"diff": {"sidecar_path": str(secret), "inline": None}, "files": []}
    assert "PRIVATE" not in _load_diff_text(raw2, raw_path)
    # Basename inside raw dir ok
    side = raw_dir / "pr-1.diff"
    side.write_text("DIFF_OK", encoding="utf-8")
    raw3 = {"diff": {"sidecar_path": "pr-1.diff", "inline": None}, "files": []}
    assert _load_diff_text(raw3, raw_path) == "DIFF_OK"
