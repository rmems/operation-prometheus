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
    assert traj["id"] == "rmems-corinth-canal-89"
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


def test_parse_multi_issue_close_list_and_closing_gerund():
    body = (
        "**Closes:** #75, #76, #85\n"
        "Combined PR closing #80, #83, #84.\n"
    )
    found = parse_linked_issue_numbers(body, "rmems", "corinth-canal")
    for n in (75, 76, 85, 80, 83, 84):
        assert ("rmems", "corinth-canal", n) in found


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


def test_review_apps_alone_do_not_count_as_validation():
    from lib.normalize import extract_validation

    raw = {
        "pull": {"body": ""},
        "checks": {
            "check_runs": [
                {
                    "name": "Kilo Code Review",
                    "status": "completed",
                    "conclusion": "success",
                },
            ],
            "combined_status": {"state": "pending", "statuses": []},
        },
    }
    events = extract_validation(raw)
    assert any(
        e["detail"] == "No structured validation evidence collected" for e in events
    )
    assert any(e["detail"].startswith("review_apps:") for e in events)


def test_sec_title_is_security_task_type():
    from lib.normalize import task_type_for

    raw = {"pull": {"title": "sec(rng): replace insecure xorshift with rand"}}
    assert task_type_for("Limen-Neural/axon-encoder", 50, raw) == "security"


def test_domain_by_pr_on_card():
    from lib.normalize import domain_for

    card = {
        "domains": ["snn"],
        "domain_by_pr": {"50": "security", "41": "api", "37": "snn", "99": None},
    }
    assert domain_for("Limen-Neural/axon-encoder", 50, card, {}) == "security"
    assert domain_for("Limen-Neural/axon-encoder", 41, card, {}) == "api"
    assert domain_for("Limen-Neural/axon-encoder", 37, card, {}) == "snn"
    # Malformed values ignored; fall back to first card domain.
    assert domain_for("Limen-Neural/axon-encoder", 99, card, {}) == "snn"


def test_bare_fixed_in_replies_not_review_signals():
    from lib.normalize import extract_review_signals

    raw = {
        "reviews": [],
        "review_comments": [],
        "issue_comments": [
            {
                "user_login": "rmems",
                "user_type": "User",
                "body": "Fixed in 0b05325.",
            },
            {
                "user_login": "rmems",
                "user_type": "User",
                "body": "**Addressed in `7fcaac847c6908db737a9a7f960acd23492e5cc0`**",
            },
            {
                "user_login": "reviewer-x",
                "user_type": "User",
                "body": "Please reject non-finite input_range before division in GainCurve::evaluate.",
            },
        ],
    }
    signals = extract_review_signals(raw)
    assert len(signals) == 1
    assert "GainCurve" in signals[0]["comment"]


def test_remotes_txt_stripped_from_patch():
    from lib.normalize import extract_patch

    raw = {
        "diff": {
            "inline": (
                "diff --git a/src/ok.rs b/src/ok.rs\n"
                "--- a/src/ok.rs\n+++ b/src/ok.rs\n@@ -1 +1 @@\n-a\n+b\n"
                "diff --git a/remotes.txt b/remotes.txt\n"
                "--- a/remotes.txt\n+++ b/remotes.txt\n"
                "@@ -0,0 +1,2 @@\n+origin  git@github.com:Spikenaut/spikenaut-encoder.git\n"
                "diff --git a/.env.example b/.env.example\n"
                "--- a/.env.example\n+++ b/.env.example\n@@ -1 +1 @@\n-FOO=\n+FOO=1\n"
            )
        },
        "files": [],
    }
    patch = extract_patch(raw)
    assert "src/ok.rs" in patch
    assert "diff --git a/remotes.txt" not in patch
    assert "Spikenaut" not in patch
    assert "remotes/origin/" not in patch
    # Basename match must not drop .env.example as if it were .env
    assert ".env.example" in patch
    assert "FOO=1" in patch


def test_before_context_omits_noise_paths():
    from lib.normalize import extract_before_context

    raw = {
        "pull": {"title": "feat: x", "body": "## Summary\nHello\n"},
        "files": [
            {"filename": "src/lib.rs"},
            {"filename": "remotes.txt"},
            {"filename": ".env"},
        ],
    }
    ctx = extract_before_context(raw)
    assert "Changed files (1)" in ctx
    assert "src/lib.rs" in ctx
    assert "remotes.txt" not in ctx
    assert ".env" not in ctx


def test_c_quoted_diff_header_noise_basename():
    from lib.normalize import extract_patch

    # Git quotes non-ASCII path components with C-style escapes.
    raw = {
        "diff": {
            "inline": (
                'diff --git "a/caf\\303\\251/remotes.txt" "b/caf\\303\\251/remotes.txt"\n'
                "--- a/caf\xc3\xa9/remotes.txt\n"
                "+++ b/caf\xc3\xa9/remotes.txt\n"
                "@@ -0,0 +1 @@\n+secret-remote\n"
                "diff --git a/src/ok.rs b/src/ok.rs\n"
                "--- a/src/ok.rs\n+++ b/src/ok.rs\n@@ -1 +1 @@\n-a\n+b\n"
            )
        },
        "files": [],
    }
    patch = extract_patch(raw)
    assert "src/ok.rs" in patch
    assert "secret-remote" not in patch
    assert "remotes.txt" not in patch


def test_empty_patch_fallback_omits_noise_filenames():
    from lib.normalize import extract_patch

    # Inline noise-only + files list with noise + one real path without a patch chunk.
    raw = {
        "diff": {
            "inline": (
                "diff --git a/remotes.txt b/remotes.txt\n"
                "--- a/remotes.txt\n+++ b/remotes.txt\n@@ -0,0 +1 @@\n+origin secret\n"
            )
        },
        "files": [
            {"filename": "remotes.txt"},
            {"filename": ".env"},
            {"filename": "src/lib.rs"},
        ],
    }
    patch = extract_patch(raw)
    assert "remotes.txt" not in patch
    assert ".env" not in patch
    assert "origin secret" not in patch
    assert "changed files: src/lib.rs" in patch


def test_noise_filter_keeps_paths_with_space_after_env_prefix():
    from lib.normalize import extract_patch

    # Unquoted path with a space must not be split so "a/.env" alone looks like noise.
    raw = {
        "diff": {
            "inline": (
                "diff --git a/.env template b/.env template\n"
                "--- a/.env template\n+++ b/.env template\n"
                "@@ -1 +1 @@\n-old\n+new\n"
                "diff --git a/src/ok.rs b/src/ok.rs\n"
                "--- a/src/ok.rs\n+++ b/src/ok.rs\n@@ -1 +1 @@\n-a\n+b\n"
            )
        },
        "files": [],
    }
    patch = extract_patch(raw)
    assert ".env template" in patch
    assert "+new" in patch
    assert "src/ok.rs" in patch


def test_noise_prefilter_case_insensitive_uppercase_env():
    from lib.normalize import extract_patch

    raw = {
        "diff": {
            "inline": (
                "diff --git a/.ENV b/.ENV\n"
                "--- a/.ENV\n+++ b/.ENV\n"
                "@@ -0,0 +1 @@\n+SECRET=1\n"
                "diff --git a/src/ok.rs b/src/ok.rs\n"
                "--- a/src/ok.rs\n+++ b/src/ok.rs\n@@ -1 +1 @@\n-a\n+b\n"
            )
        },
        "files": [],
    }
    patch = extract_patch(raw)
    assert "SECRET=1" not in patch
    assert "diff --git a/.ENV" not in patch
    assert "src/ok.rs" in patch


def test_codeql_and_snyk_stay_in_ci_validation():
    from lib.normalize import extract_validation

    raw = {
        "pull": {"body": ""},
        "checks": {
            "check_runs": [
                {"name": "CodeQL", "status": "completed", "conclusion": "failure"},
                {"name": "Snyk", "status": "completed", "conclusion": "success"},
            ],
            "combined_status": {"state": "failure", "statuses": []},
        },
    }
    events = extract_validation(raw)
    ci = [e for e in events if e["type"] == "ci" and "CodeQL" in e["detail"]]
    assert ci and ci[0]["result"] == "fail"
    assert not any(
        e["type"] == "other" and "CodeQL" in e.get("detail", "") for e in events
    )


def test_all_skipped_ci_is_not_pass():
    from lib.normalize import extract_validation

    raw = {
        "pull": {"body": ""},
        "checks": {
            "check_runs": [
                {"name": "test", "status": "completed", "conclusion": "skipped"},
                {"name": "lint", "status": "completed", "conclusion": "neutral"},
            ],
            "combined_status": {"state": "success", "statuses": []},
        },
    }
    events = extract_validation(raw)
    ci = [e for e in events if e["type"] == "ci" and "test=" in e["detail"]]
    assert ci and ci[0]["result"] == "fail"


def test_success_plus_skipped_ci_is_pass():
    from lib.normalize import extract_validation

    raw = {
        "pull": {"body": ""},
        "checks": {
            "check_runs": [
                {"name": "test", "status": "completed", "conclusion": "success"},
                {"name": "optional", "status": "completed", "conclusion": "skipped"},
            ],
            "combined_status": {"state": "success", "statuses": []},
        },
    }
    events = extract_validation(raw)
    ci = [e for e in events if e["type"] == "ci" and "test=" in e["detail"]]
    assert ci and ci[0]["result"] == "pass"


def test_failing_prose_is_fail():
    from lib.normalize import extract_validation

    raw = {
        "pull": {"body": "## Validation\n\nCI is failing on main.\n"},
        "checks": {},
    }
    events = extract_validation(raw)
    assert events[0]["type"] == "test"
    assert events[0]["result"] == "fail"


def test_omitted_truncated_file_marked_in_fallback_patch():
    from lib.normalize import extract_patch

    raw = {
        "diff": {"inline": None, "sidecar_path": None},
        "files": [
            {
                "filename": "src/ok.rs",
                "status": "modified",
                "patch": "@@ -1 +1 @@\n-a\n+b\n",
            },
            {
                "filename": "weights.bin",
                "status": "added",
                "patch": None,
                "patch_truncated": True,
            },
        ],
    }
    patch = extract_patch(raw)
    assert "src/ok.rs" in patch
    assert "# omitted: weights.bin" in patch


def test_private_repo_rejected():
    from lib.github_client import GitHubError

    class PrivateClient(FakeClient):
        def get_json(self, path_or_url: str) -> Any:
            path = path_or_url.replace(self.base_url, "")
            if "/pulls/89" in path and "comments" not in path and "reviews" not in path:
                pull = json.loads((FIXTURES / "pull_89.json").read_text())
                pull = {
                    **pull,
                    "base": {
                        **(pull.get("base") or {}),
                        "repo": {
                            "private": True,
                            "full_name": "rmems/secret-repo",
                        },
                    },
                }
                return pull
            return super().get_json(path_or_url)

    if not (FIXTURES / "pull_89.json").exists():
        pytest.skip("fixtures missing")
    with pytest.raises(GitHubError, match="private"):
        collect_pr(PrivateClient(), "rmems/corinth-canal", 89)


def test_enrich_linked_issues_from_body_multi_list():
    from lib.normalize import normalize_record

    raw = {
        "source": {"repo": "rmems/corinth-canal", "pr_number": 91},
        "pull": {
            "title": "feature",
            "body": "**Closes:** #75, #76, #85\n\n## Summary\nMulti-issue PR.\n",
            "state": "closed",
            "merged": True,
            "draft": False,
        },
        "linked_issues": [],
        "reviews": [],
        "review_comments": [],
        "issue_comments": [],
        "files": [{"filename": "a.rs", "status": "modified", "patch": "+x\n"}],
        "checks": {},
        "commits": [],
    }
    traj = normalize_record(raw, {})
    urls = traj["source_urls"]
    assert "https://github.com/rmems/corinth-canal/pull/91" in urls
    for n in (75, 76, 85):
        assert f"https://github.com/rmems/corinth-canal/issues/{n}" in urls


def test_traj_id_includes_owner():
    from lib.normalize import normalize_record

    raw = {
        "source": {"repo": "alice/widget", "pr_number": 12},
        "pull": {
            "title": "x",
            "body": "",
            "state": "closed",
            "merged": True,
            "draft": False,
        },
        "linked_issues": [],
        "reviews": [],
        "review_comments": [],
        "issue_comments": [],
        "files": [],
        "checks": {},
        "commits": [],
    }
    traj = normalize_record(raw, {"language": "Python", "domains": ["tools"]})
    assert traj["id"] == "alice-widget-12"


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
