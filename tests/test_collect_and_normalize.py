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

from lib.normalize import normalize_record  # noqa: E402
from lib.raw_record import collect_pr, write_raw_record  # noqa: E402

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
