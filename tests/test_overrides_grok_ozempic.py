"""Per-PR override regressions for rmems/grok-ozempic (GH #17, #20).

Split out of ``test_collect_and_normalize.py`` so a new extract adds its own file
instead of appending to the shared suite.
"""

from __future__ import annotations


def test_linked_issue_override_table_entries():
    from lib.normalize import LINKED_ISSUE_OVERRIDE

    assert LINKED_ISSUE_OVERRIDE[("rmems/grok-ozempic", 26)] == (22,)
    assert LINKED_ISSUE_OVERRIDE[("rmems/grok-ozempic", 42)] == (37,)


def test_linked_issue_override_adds_referenced_issues():
    from lib.normalize import normalize_record

    raw = {
        "source": {"repo": "rmems/grok-ozempic", "pr_number": 26},
        "pull": {
            "title": "Verify grok-ozempic aligns with xai-dissect inventory",
            "body": "Implements GitHub #22 / Linear MET-108.",
            "state": "closed",
            "merged": True,
            "draft": False,
        },
        "linked_issues": [],
        "reviews": [],
        "review_comments": [],
        "issue_comments": [],
        "files": [{"filename": "src/core/alignment.rs", "status": "added", "patch": "+x\n"}],
        "checks": {},
        "commits": [],
    }
    urls = normalize_record(raw, {})["source_urls"]
    assert urls == [
        "https://github.com/rmems/grok-ozempic/pull/26",
        "https://github.com/rmems/grok-ozempic/issues/22",
    ]


def test_linked_issue_override_grok_ozempic_42_supports_37():
    """GH #20: PR #42 names #37 via URL / Supports, not a close keyword."""
    from lib.normalize import normalize_record

    raw = {
        "source": {"repo": "rmems/grok-ozempic", "pr_number": 42},
        "pull": {
            "title": "feat: export Grok-1 embedding pickle → .npy (#37 / RM-189)",
            "body": (
                "Supports #37 / RM-189.\n"
                "https://github.com/rmems/grok-ozempic/issues/37\n"
            ),
            "state": "closed",
            "merged": True,
            "draft": False,
        },
        "linked_issues": [],
        "reviews": [],
        "review_comments": [
            {
                "user": {"login": "chatgpt-codex-connector[bot]"},
                "body": "P2: Reject negative payload offsets before mmap slice.",
                "path": "scripts/export_grok1_embedding_npy.py",
                "line": 10,
            }
        ],
        "issue_comments": [],
        "files": [
            {
                "filename": "scripts/export_grok1_embedding_npy.py",
                "status": "added",
                "patch": "+def main():\n+    pass\n",
            }
        ],
        "checks": {},
        "commits": [],
    }
    card = {
        "language": "Rust",
        "language_by_pr": {"42": "Python"},
        "domain_by_pr": {"42": "ml-infra"},
        "training_use_buckets": {"review-to-patch": [42]},
    }
    traj = normalize_record(raw, card)
    assert traj["language"] == "Python"
    assert traj["domain"] == "ml-infra"
    assert traj["training_use"] == "review-to-patch"
    assert "https://github.com/rmems/grok-ozempic/issues/37" in traj["source_urls"]
    assert traj["review_signals"]
