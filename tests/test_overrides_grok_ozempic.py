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


def test_v1_card_language_by_pr_and_linked_issue_68():
    """v1 card: Python on #72/#74; #72 names #68 without a close keyword."""
    import json
    from pathlib import Path

    from lib.normalize import language_for, normalize_record

    card = json.loads(
        (
            Path(__file__).resolve().parents[1]
            / "datasets"
            / "cards"
            / "grok-ozempic-v1.json"
        ).read_text(encoding="utf-8")
    )
    raw72 = {
        "source": {"repo": "rmems/grok-ozempic", "pr_number": 72},
        "pull": {
            "title": "research: expert-only ternary multi-block residual fidelity",
            "body": "Implements the #68 multi-block residual fidelity experiment.",
            "state": "closed",
            "merged": True,
            "draft": False,
        },
        "linked_issues": [],
        "reviews": [],
        "review_comments": [
            {
                "user_login": "rmems",
                "user_type": "User",
                "body": "Fixed: version guard is now versions != {3} so v2 packs are rejected.",
            }
        ],
        "issue_comments": [],
        "files": [
            {
                "filename": "scripts/grok1_multiblock_experiment.py",
                "status": "added",
                "patch": "+def main():\n+    pass\n",
            }
        ],
        "checks": {},
        "commits": [],
    }
    assert language_for("rmems/grok-ozempic", 72, card, raw72) == "Python"
    assert (
        language_for(
            "rmems/grok-ozempic",
            74,
            card,
            {"files": [{"filename": "scripts/grok1_multiblock_lib.py"}]},
        )
        == "Python"
    )
    assert (
        language_for(
            "rmems/grok-ozempic",
            69,
            card,
            {"files": [{"filename": "src/core/weight_pack.rs"}]},
        )
        == "Rust"
    )
    traj = normalize_record(raw72, card)
    assert traj["language"] == "Python"
    assert traj["domain"] == "quantization"
    assert traj["training_use"] == "review-to-patch"
    assert traj["task_type"] == "feature"
    assert "https://github.com/rmems/grok-ozempic/issues/68" in traj["source_urls"]
