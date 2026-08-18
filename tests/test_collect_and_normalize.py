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


def test_feature_bucket_maps_to_feature_training_use():
    """Schema v0.1 (GH #39): the feature bucket is a first-class training_use."""
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
    assert traj["training_use"] == "feature"
    # The record must validate against the schema carrying the new enum value.
    schema = json.loads(SCHEMA.read_text())
    jsonschema.Draft7Validator(schema).validate(traj)
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


def test_review_signal_dedupe_and_ack_deprioritized():
    """GH #18: identical Addressed-in acks must not fill all slots; problems rank first."""
    from lib.normalize import extract_review_signals

    ack = (
        "Addressed in 5ecbe0855124d24533a1cc365274ea2dcb9400c1: portable ~/.models "
        "paths in docs/help (no hard-coded username), dtype KeyError guard, NPY header "
        "uses space-pad then trailing newline"
    )
    raw = {
        "reviews": [],
        "review_comments": [
            {
                "user_login": "rmems",
                "user_type": "User",
                "body": ack,
            }
            for _ in range(8)
        ]
        + [
            {
                "user_login": "reviewer-x",
                "user_type": "User",
                "body": f"Finding {i}: please validate export path edge case {i} before merge.",
            }
            for i in range(1, 7)
        ],
        "issue_comments": [],
    }
    signals = extract_review_signals(raw, max_items=8)
    comments = [s["comment"] for s in signals]
    # Dedupe: at most one copy of the ack body (or its rationale key).
    ack_hits = sum(1 for c in comments if "5ecbe0855124d24533a1cc365274ea2dcb9400c1" in c or "portable ~/.models" in c)
    assert ack_hits <= 1
    problem_hits = sum(1 for c in comments if c.startswith("Finding "))
    assert problem_hits >= 5
    assert len(signals) <= 8
    # Problems appear before the reserved ack when both are present.
    if problem_hits and ack_hits:
        first_ack = next(
            i
            for i, c in enumerate(comments)
            if "portable ~/.models" in c or "5ecbe08" in c
        )
        first_problem = next(i for i, c in enumerate(comments) if c.startswith("Finding "))
        assert first_problem < first_ack


def test_max_items_one_prefers_problem_over_ack():
    """When max_items=1, do not reserve the only slot for an ack."""
    from lib.normalize import extract_review_signals

    raw = {
        "reviews": [],
        "review_comments": [
            {
                "user_login": "rmems",
                "user_type": "User",
                "body": (
                    "Addressed in abcdef0123456789: portable paths and dtype guard notes."
                ),
            },
            {
                "user_login": "reviewer-x",
                "user_type": "User",
                "body": "Finding 1: please validate export path edge case before merge.",
            },
        ],
        "issue_comments": [],
    }
    signals = extract_review_signals(raw, max_items=1)
    assert len(signals) == 1
    assert signals[0]["comment"].startswith("Finding 1")


def test_duplicate_merges_suggestion_from_inline():
    """Dedupe keeps problem text and merges a later non-empty suggestion."""
    from lib.normalize import extract_review_signals

    body = "Please fix the dtype KeyError guard in the export path."
    raw = {
        "reviews": [
            {
                "user_login": "reviewer-x",
                "user_type": "User",
                "state": "COMMENTED",
                "body": body,
            }
        ],
        "review_comments": [
            {
                "user_login": "reviewer-x",
                "user_type": "User",
                "body": body + "\n```suggestion\nfixed_line = True\n```\n",
            }
        ],
        "issue_comments": [],
    }
    signals = extract_review_signals(raw, max_items=8)
    assert len(signals) == 1
    assert "dtype KeyError" in signals[0]["comment"]
    assert signals[0].get("suggestion") == "fixed_line = True"


def test_distinct_non_suggestion_fences_not_collapsed():
    """Non-suggestion fences remain part of signal identity (Bugbot)."""
    from lib.normalize import extract_review_signals

    raw = {
        "reviews": [],
        "review_comments": [
            {
                "user_login": "reviewer-x",
                "user_type": "User",
                "body": "Bad pattern here:\n```rust\nlet x = 1;\n```\n",
            },
            {
                "user_login": "reviewer-x",
                "user_type": "User",
                "body": "Bad pattern here:\n```rust\nlet x = 2;\n```\n",
            },
        ],
        "issue_comments": [],
    }
    signals = extract_review_signals(raw, max_items=8)
    assert len(signals) == 2


def test_fixed_in_commit_bare_ack_dropped():
    from lib.normalize import extract_review_signals

    raw = {
        "reviews": [],
        "review_comments": [],
        "issue_comments": [
            {
                "user_login": "rmems",
                "user_type": "User",
                "body": "Fixed in commit 0b05325abcdef.",
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


def test_language_by_pr_overrides_card_language():
    """GH #19: language_by_pr beats card.language for that PR only."""
    from lib.normalize import language_for

    card = {
        "language": "Rust",
        "language_by_pr": {"42": "Python", 7: "Julia", "99": ""},
    }
    raw42 = {"source": {"pr_number": 42}, "files": [{"filename": "scripts/export.py"}]}
    raw7 = {"source": {"pr_number": 7}, "files": [{"filename": "src/lib.rs"}]}
    raw99 = {"source": {"pr_number": 99}, "files": [{"filename": "src/lib.rs"}]}
    assert language_for("rmems/grok-ozempic", 42, card, raw42) == "Python"
    # Integer key in language_by_pr
    assert language_for("rmems/grok-ozempic", 7, card, raw7) == "Julia"
    # Empty override ignored → card language.
    assert language_for("rmems/grok-ozempic", 99, card, raw99) == "Rust"
    # No card language → extension sniff.
    assert (
        language_for(
            "rmems/widget",
            1,
            {},
            {"source": {"pr_number": 1}, "files": [{"filename": "a.py"}]},
        )
        == "Python"
    )


def test_review_signal_dedupe_across_three_sources():
    """GH #18: SHA-normalized acks from reviews / review_comments / issue_comments collapse."""
    from lib.normalize import extract_review_signals

    def ack(sha: str) -> str:
        return (
            f"Addressed in {sha}: reject negative payload offsets before mmap slice "
            "and pin the export umask."
        )

    raw = {
        "reviews": [
            {
                "user_login": "rmems",
                "user_type": "User",
                "state": "COMMENTED",
                "body": ack("aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"),
            }
        ],
        "review_comments": [
            {
                "user_login": "rmems",
                "user_type": "User",
                "body": ack("bbbbbbb"),
            }
            for _ in range(6)
        ],
        "issue_comments": [
            {
                "user_login": "rmems",
                "user_type": "User",
                "body": ack("cccccccc"),
            }
        ],
    }
    signals = extract_review_signals(raw, max_items=8)
    assert len(signals) == 1
    assert signals[0]["author"] == "rmems"
    # First occurrence (reviews are processed first) keeps its original SHA.
    assert "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa" in signals[0]["comment"]

    extra_findings = [
        {
            "user_login": "reviewer-x",
            "user_type": "User",
            "body": f"Finding {i}: please validate export path edge case {i} before merge.",
        }
        for i in range(1, 12)
    ]
    capped = extract_review_signals(
        {**raw, "review_comments": raw["review_comments"] + extra_findings},
        max_items=8,
    )
    assert len(capped) == 8
    unique = {(s.get("comment") or "") for s in capped}
    assert len(unique) == 8


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


def test_expected_failure_prose_is_pass():
    from lib.normalize import extract_validation

    raw = {
        "pull": {
            "body": (
                "## Validation\n\n"
                "- `cargo test --features cli`\n"
                "- Manual invalid schema fixture confirms ingest failure behavior\n"
            )
        },
        "checks": {},
    }
    events = extract_validation(raw)
    assert events[0]["result"] == "pass"


def test_expected_failure_does_not_mask_a_real_failure():
    from lib.normalize import extract_validation

    raw = {
        "pull": {
            "body": (
                "## Validation\n\n"
                "- Invalid fixture fails as expected\n"
                "- `cargo test` — 2 tests failed on the router path\n"
            )
        },
        "checks": {},
    }
    events = extract_validation(raw)
    assert events[0]["result"] == "fail"


def test_self_referential_linked_issue_is_dropped():
    from lib.normalize import enrich_linked_issues

    raw = {
        "source": {"repo": "rmems/widget", "pr_number": 26},
        "pull": {"number": 26, "body": "Closes #26"},
        "linked_issues": [],
        "commits": [],
    }
    assert enrich_linked_issues(raw) == []


def test_reporting_verbs_do_not_mask_failures():
    """A reporting verb is not an expected-failure marker (Codex P1 on #17)."""
    from lib.normalize import extract_validation

    for body in (
        "## Validation\n\nCI checks failed on Linux\n",
        "## Validation\n\nVerified that cargo test failed\n",
        "## Validation\n\nConfirmed the nightly job is still failing\n",
        "## Validation\n\nEnsured coverage, but 1 test failed\n",
    ):
        events = extract_validation({"pull": {"body": body}, "checks": {}})
        assert events[0]["result"] == "fail", body


def test_optional_unchecked_checkbox_does_not_fail_validation():
    """Optional / not-required unchecked items must not fail the test event (#35 Codex)."""
    from lib.normalize import extract_validation

    body = (
        "## Test plan\n\n"
        "- [x] Tiny synthetic shard export + numpy load assert\n"
        "- [x] `xai-dissect dissect` parse on real tensor\n"
        "- [ ] Optional full 3 GiB export (for #39 experiment; not required for merge)\n"
    )
    events = extract_validation({"pull": {"body": body}, "checks": {}})
    assert events[0]["type"] == "test"
    assert events[0]["result"] == "pass", events[0]


def test_required_unchecked_checkbox_still_fails_validation():
    from lib.normalize import extract_validation

    body = (
        "## Test plan\n\n"
        "- [x] Unit tests\n"
        "- [ ] Fix path traversal in export CLI\n"
    )
    events = extract_validation({"pull": {"body": body}, "checks": {}})
    assert events[0]["result"] == "fail"


def test_negated_optional_checkbox_still_blocks():
    """'not optional' must not be treated as optional (#35 Codex P2)."""
    from lib.normalize import extract_validation

    body = (
        "## Test plan\n\n"
        "- [x] Unit tests\n"
        "- [ ] Windows test is not optional\n"
    )
    events = extract_validation({"pull": {"body": body}, "checks": {}})
    assert events[0]["result"] == "fail"


def test_bare_unchecked_checkbox_still_blocks():
    """Empty `- [ ]` lines remain required (#35 Codex P2)."""
    from lib.normalize import extract_validation

    body = "## Test plan\n\n- [x] Unit tests\n- [ ]\n"
    events = extract_validation({"pull": {"body": body}, "checks": {}})
    assert events[0]["result"] == "fail"


def test_optional_checkbox_deferred_wording_does_not_fail_section():
    """Optional lines with pending/todo/not executed must not fail via section scan."""
    from lib.normalize import extract_validation

    for item in (
        "Optional follow-up pending upstream benchmark",
        "Out of scope; not executed",
        "Optional path not run on CI",
    ):
        body = f"## Test plan\n\n- [x] Core tests\n- [ ] {item}\n"
        events = extract_validation({"pull": {"body": body}, "checks": {}})
        assert events[0]["result"] == "pass", item


def test_required_follow_up_checkbox_still_blocks():
    """Bare 'follow-up' / 'Required follow-up' must not be treated as optional."""
    from lib.normalize import extract_validation

    for item in (
        "Required follow-up: run Windows tests before merge",
        "Follow-up: run integration tests",
    ):
        body = f"## Test plan\n\n- [x] Unit tests\n- [ ] {item}\n"
        events = extract_validation({"pull": {"body": body}, "checks": {}})
        assert events[0]["result"] == "fail", item


def test_not_out_of_scope_checkbox_still_blocks():
    from lib.normalize import extract_validation

    body = (
        "## Test plan\n\n"
        "- [x] Unit tests\n"
        "- [ ] Windows path is not out of scope\n"
    )
    events = extract_validation({"pull": {"body": body}, "checks": {}})
    assert events[0]["result"] == "fail"


def test_optional_checkbox_continuation_lines_do_not_fail_section():
    """Indented continuation under an optional item must be stripped too."""
    from lib.normalize import extract_validation

    body = (
        "## Test plan\n\n"
        "- [x] Core tests\n"
        "- [ ] Optional upstream benchmark\n"
        "  Pending hardware; not run\n"
    )
    events = extract_validation({"pull": {"body": body}, "checks": {}})
    assert events[0]["result"] == "pass", events[0]


def test_optional_nested_sublist_does_not_fail_section():
    """Nested list under optional must strip with parent (#35 Codex P2)."""
    from lib.normalize import extract_validation

    body = (
        "## Test plan\n\n"
        "- [x] Core tests\n"
        "- [ ] Optional platform tests\n"
        "  - [ ] Windows pending\n"
    )
    events = extract_validation({"pull": {"body": body}, "checks": {}})
    assert events[0]["result"] == "pass", events[0]


def test_optional_line_with_actual_failure_still_fails():
    """Observed failures on optional lines must still fail (#35 Codex P2)."""
    from lib.normalize import extract_validation

    body = (
        "## Test plan\n\n"
        "- [x] Core tests\n"
        "- [ ] Optional Windows smoke test failed with 2 errors\n"
    )
    events = extract_validation({"pull": {"body": body}, "checks": {}})
    assert events[0]["result"] == "fail"


def test_optional_blank_then_nested_sublist_does_not_fail():
    from lib.normalize import extract_validation

    body = (
        "## Test plan\n\n"
        "- [x] Core tests\n"
        "- [ ] Optional platform tests\n"
        "\n"
        "  - [ ] Windows pending\n"
    )
    events = extract_validation({"pull": {"body": body}, "checks": {}})
    assert events[0]["result"] == "pass", events[0]


def test_mid_sentence_optional_mention_does_not_exempt_task():
    from lib.normalize import extract_validation

    for item in (
        "Run release tests with optional coverage reporting",
        "Run release tests (GPU not required)",
    ):
        body = f"## Test plan\n\n- [x] Core\n- [ ] {item}\n"
        events = extract_validation({"pull": {"body": body}, "checks": {}})
        assert events[0]["result"] == "fail", item


def test_optional_failure_recovery_name_not_run_is_pass():
    """Bare 'failure' in a deferred optional task name is not an observed fail."""
    from lib.normalize import extract_validation

    body = (
        "## Test plan\n\n"
        "- [x] Core tests\n"
        "- [ ] Optional failure-recovery benchmark; not run\n"
    )
    events = extract_validation({"pull": {"body": body}, "checks": {}})
    assert events[0]["result"] == "pass", events[0]


def test_zero_failures_line_does_not_mask_other_failed_line():
    from lib.normalize import extract_validation

    body = (
        "## Test plan\n\n"
        "- [x] Core suite: 0 failures\n"
        "- [ ] Optional Windows smoke test failed\n"
    )
    events = extract_validation({"pull": {"body": body}, "checks": {}})
    assert events[0]["result"] == "fail"


def test_zero_failures_same_line_as_one_error_is_fail():
    """Zero-fail summary must not suppress a co-located nonzero error count."""
    from lib.normalize import extract_validation

    body = "## Validation\n\nSuite: 0 failures, 1 error\n"
    events = extract_validation({"pull": {"body": body}, "checks": {}})
    assert events[0]["result"] == "fail"


def test_zero_failures_line_does_not_mask_reported_failures_line():
    """Section-wide zero-fail must not suppress bare failure nouns on another line."""
    from lib.normalize import extract_validation

    body = (
        "## Validation\n\n"
        "Core suite: 0 failures\n"
        "Sanitizer reported failures on the GPU path\n"
    )
    events = extract_validation({"pull": {"body": body}, "checks": {}})
    assert events[0]["result"] == "fail"


def test_override_lookup_is_case_insensitive():
    """Repo slugs are case-insensitive; overrides must not depend on CLI casing."""
    from lib.normalize import domain_for, enrich_linked_issues, task_type_for

    assert task_type_for("RMEMS/GROK-OZEMPIC", 26, {"pull": {}}) == "feature"
    assert domain_for("RMEMS/Corinth-Canal", 82, {}, {}) == "gpu-compute"

    raw = {
        "source": {"repo": "RMEMS/GROK-OZEMPIC", "pr_number": 26},
        "pull": {"number": 26, "body": "Implements GitHub #22"},
        "linked_issues": [],
        "commits": [],
    }
    assert [i["number"] for i in enrich_linked_issues(raw)] == [22]


def test_failure_behavior_noun_alone_is_not_an_expected_failure():
    """"failure behavior/mode" without intent is an ordinary report (Codex P1)."""
    from lib.normalize import extract_validation

    for body in (
        "## Validation\n\nCI showed failure behavior on Linux\n",
        "## Validation\n\nObserved failure mode in cargo test\n",
    ):
        events = extract_validation({"pull": {"body": body}, "checks": {}})
        assert events[0]["result"] == "fail", body

    # A deliberately invalid fixture still reads as an expected failure.
    events = extract_validation(
        {
            "pull": {
                "body": "## Validation\n\nInvalid schema fixture confirms ingest failure behavior\n"
            },
            "checks": {},
        }
    )
    assert events[0]["result"] == "pass"


def test_pre_collected_self_referential_issue_is_dropped():
    """A self-reference already in the raw record must not survive (Codex P2)."""
    from lib.normalize import enrich_linked_issues

    raw = {
        "source": {"repo": "rmems/widget", "pr_number": 26},
        "pull": {"number": 26, "body": ""},
        "linked_issues": [
            {
                "number": 26,
                "repo": "rmems/widget",
                "html_url": "https://github.com/rmems/widget/issues/26",
            },
            {
                "number": 22,
                "repo": "rmems/widget",
                "html_url": "https://github.com/rmems/widget/issues/22",
            },
        ],
        "commits": [],
    }
    assert [i["number"] for i in enrich_linked_issues(raw)] == [22]


def test_copilot_reviewer_is_not_ci_validation():
    from lib.normalize import extract_validation

    raw = {
        "pull": {"body": ""},
        "checks": {
            "check_runs": [
                {"name": "fmt / clippy / test", "status": "completed", "conclusion": "success"},
                {
                    "name": "copilot-pull-request-reviewer",
                    "status": "completed",
                    "conclusion": "success",
                },
            ]
        },
    }
    events = extract_validation(raw)
    ci = [e for e in events if e["type"] == "ci"]
    assert len(ci) == 1
    assert "copilot" not in ci[0]["detail"].lower()
    assert any("copilot" in e["detail"].lower() for e in events if e["type"] == "other")


def test_local_agent_config_paths_are_filtered_from_patches():
    """Tracker/agent state carries emails and local config, never trajectory."""
    from lib.normalize import _is_noise_patch_path

    for path in (
        ".beads/config.yaml",
        ".beads/issues.jsonl",
        "./.claude/settings.json",
        "a/.beads/hooks/pre-push",
    ):
        assert _is_noise_patch_path(path), path
    for path in ("src/core/alignment.rs", "AGENTS.md", "beads/x.rs", ".beadsfoo/y.rs"):
        assert not _is_noise_patch_path(path), path


def test_bad_adjective_alone_does_not_suppress_a_real_failure():
    """"Invalid fixture" is not intent unless it asserts the failure (Codex P1)."""
    from lib.normalize import extract_validation

    for body in (
        "## Validation\n\nInvalid fixture was repaired, but cargo test failed on Linux\n",
        "## Validation\n\nInvalid fixture was repaired but cargo test failed on Linux\n",
    ):
        events = extract_validation({"pull": {"body": body}, "checks": {}})
        assert events[0]["result"] == "fail", body

    # The fixture asserting the failure is still an expected failure.
    for body in (
        "## Validation\n\nInvalid schema fixture confirms ingest failure behavior\n",
        "## Validation\n\nMalformed manifest fixture triggers the expected failure\n",
    ):
        events = extract_validation({"pull": {"body": body}, "checks": {}})
        assert events[0]["result"] == "pass", body


def test_noise_dir_only_diff_is_still_filtered():
    """The cheap prefilter must not let a .beads/-only diff bypass it (Codex P1)."""
    from lib.normalize import _filter_noise_from_diff

    # Deliberately contains no _NOISE_PATCH_BASENAMES token.
    diff = (
        "diff --git a/.beads/config.yaml b/.beads/config.yaml\n"
        "+owner: someone@example.com\n"
        "diff --git a/.claude/settings.json b/.claude/settings.json\n"
        '+{"hooks": {}}\n'
        "diff --git a/src/core/alignment.rs b/src/core/alignment.rs\n"
        "+fn align() {}\n"
    )
    out = _filter_noise_from_diff(diff)
    assert ".beads" not in out
    assert ".claude" not in out
    assert "someone@example.com" not in out
    assert "src/core/alignment.rs" in out


def test_nested_agent_state_dirs_are_filtered():
    """Monorepos nest agent state below the root (Codex P1)."""
    from lib.normalize import _is_noise_patch_path

    for path in (
        "pkg/.claude/settings.json",
        "workspace/.beads/config.yaml",
        "a/crates/app/.beads/issues.jsonl",
        ".beads/config.yaml",
    ):
        assert _is_noise_patch_path(path), path
    for path in ("src/core/alignment.rs", "beads/x.rs", ".beadsfoo/y.rs", "pkg/beads/x.rs"):
        assert not _is_noise_patch_path(path), path


def test_generic_copilot_named_ci_is_not_a_review_app():
    """Only the reviewer check is a review app, not any check saying "copilot"."""
    from lib.normalize import _is_review_app_check

    assert _is_review_app_check("copilot-pull-request-reviewer")
    assert not _is_review_app_check("Copilot integration tests")

    from lib.normalize import extract_validation

    events = extract_validation(
        {
            "pull": {"body": ""},
            "checks": {
                "check_runs": [
                    {
                        "name": "Copilot integration tests",
                        "status": "completed",
                        "conclusion": "success",
                    }
                ]
            },
        }
    )
    ci = [e for e in events if e["type"] == "ci"]
    assert len(ci) == 1 and ci[0]["result"] == "pass"


def test_expected_failure_that_did_not_happen_is_a_failure():
    """Intent without an observed failure means the negative test failed (Codex P2)."""
    from lib.normalize import extract_validation

    for body in (
        "## Validation\n\nThe invalid fixture was expected to fail, but it passed unexpectedly\n",
        "## Validation\n\nNegative test: malformed manifest did not fail\n",
    ):
        events = extract_validation({"pull": {"body": body}, "checks": {}})
        assert events[0]["result"] == "fail", body


def test_no_fail_words_is_not_all_expected():
    from lib.normalize import _fail_words_all_expected

    assert not _fail_words_all_expected("expected to fail")


def test_absence_of_expected_failure_wording_is_a_failure():
    """"did not occur" / "was not observed" mean the negative test passed (Codex P2)."""
    from lib.normalize import extract_validation

    for body in (
        "## Validation\n\nThe expected failure did not occur\n",
        "## Validation\n\nThe expected failure was not observed\n",
        "## Validation\n\nExpected failure never triggered\n",
    ):
        events = extract_validation({"pull": {"body": body}, "checks": {}})
        assert events[0]["result"] == "fail", body

    # The contradiction only applies alongside an expected-failure cue, so
    # ordinary resolved-failure prose is still a pass.
    events = extract_validation(
        {"pull": {"body": "## Validation\n\nPreviously failed tests are now passing\n"}, "checks": {}}
    )
    assert events[0]["result"] == "pass"


def test_absence_wording_must_share_a_sentence_with_the_cue():
    """An unrelated later clause must not force fail (Codex P2)."""
    from lib.normalize import extract_validation

    for body in (
        "## Validation\n\nInvalid fixture fails as expected. The warning did not occur\n",
        "## Validation\n\nNegative test added. The deprecation notice was not observed\n",
        # Separate list items are separate statements too.
        "## Validation\n\n- Invalid fixture fails as expected\n- The warning did not occur\n",
    ):
        events = extract_validation({"pull": {"body": body}, "checks": {}})
        assert events[0]["result"] == "pass", body

    # Same sentence still forces fail.
    events = extract_validation(
        {"pull": {"body": "## Validation\n\nThe expected failure did not occur\n"}, "checks": {}}
    )
    assert events[0]["result"] == "fail"


def test_soft_wrapped_sentences_keep_cue_and_contradiction_together():
    """Markdown soft-wraps prose; a bare newline is not a statement boundary."""
    from lib.normalize import extract_validation

    for body in (
        "## Validation\n\nThe expected failure\nwas not observed\n",
        "## Validation\n\nThe invalid fixture was expected to fail, but it\npassed unexpectedly\n",
    ):
        events = extract_validation({"pull": {"body": body}, "checks": {}})
        assert events[0]["result"] == "fail", body

    # Real boundaries — sentence end, list item, blank line — still separate.
    for body in (
        "## Validation\n\nInvalid fixture fails as expected. The warning did not occur\n",
        "## Validation\n\n- Invalid fixture fails as expected\n- The warning did not occur\n",
        "## Validation\n\nInvalid fixture fails as expected\n\nThe warning did not occur\n",
    ):
        events = extract_validation({"pull": {"body": body}, "checks": {}})
        assert events[0]["result"] == "pass", body


def test_macroscope_note_stripped_without_eating_earlier_content():
    """Only the attributed NOTE is dropped, not everything before it (Codex P2)."""
    from lib.bots import strip_bot_boilerplate

    body = (
        "## Validation\n\n"
        "> [!NOTE]\n> Human note: run the ingest fixture first.\n\n"
        "- cargo test --features cli\n"
        "- invalid schema fixture confirms failure behavior\n\n"
        "> [!NOTE]\n> ### Bot summary\n"
        '> <sup>Generated by <a href="https://macroscope.com">Macroscope</a> '
        "summarized this PR.</sup>\n\n"
    )
    out = strip_bot_boilerplate(body)
    assert "Bot summary" not in out
    assert "Human note" in out
    assert "cargo test --features cli" in out


def test_known_broken_ci_described_as_expected_is_not_a_pass():
    """A known-broken run is not a negative test (Codex P2)."""
    from lib.normalize import extract_validation

    events = extract_validation(
        {
            "pull": {
                "body": "## Validation\n\nThe CI was expected to be failing on "
                "Linux until the runner is repaired\n"
            },
            "checks": {},
        }
    )
    assert events[0]["result"] == "fail"


def test_kilo_agent_state_is_filtered_from_patches():
    """.kilo/ is agent state like .beads/ and .claude/ (Codex P1)."""
    from lib.normalize import _is_noise_patch_path

    for path in (".kilo/settings.json", "pkg/.kilo/state.json", "a/.kilo/mcp.json"):
        assert _is_noise_patch_path(path), path
    for path in ("kilo/x.rs", ".kilofoo/y.rs", "src/kilo_backend.rs"):
        assert not _is_noise_patch_path(path), path


def test_asserted_negative_test_failure_is_a_pass():
    """"Negative test confirms failure behavior" is the assertion succeeding."""
    from lib.normalize import extract_validation

    for body in (
        "## Validation\n\nNegative test confirms failure behavior\n",
        "## Validation\n\nNegative test observed a validation failure\n",
    ):
        events = extract_validation({"pull": {"body": body}, "checks": {}})
        assert events[0]["result"] == "pass", body

    # An ordinary failure report that merely mentions a negative test stays fail.
    for body in (
        "## Validation\n\nNegative test suite reported 3 failures\n",
        "## Validation\n\nNegative tests failed on Windows\n",
        "## Validation\n\nNegative test added. CI checks failed on Linux\n",
    ):
        events = extract_validation({"pull": {"body": body}, "checks": {}})
        assert events[0]["result"] == "fail", body


def test_macroscope_removal_keeps_surrounding_lines_separate():
    """_NOTE_BLOCK eats the preceding newline, so removal must restore one."""
    from lib.bots import strip_bot_boilerplate

    body = (
        "- cargo test --features cli\n"
        "> [!NOTE]\n"
        '> <sup>by <a href="https://macroscope.com">Macroscope</a> summarized</sup>\n'
        "- invalid fixture confirms failure behavior\n"
    )
    out = strip_bot_boilerplate(body)
    assert "Macroscope" not in out
    assert "cli- invalid" not in out
    lines = [ln for ln in out.splitlines() if ln.strip()]
    assert lines == [
        "- cargo test --features cli",
        "- invalid fixture confirms failure behavior",
    ]
