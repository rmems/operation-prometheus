"""Per-PR override regressions for rmems/worktrees-hives (GH #26).

Split out of ``test_collect_and_normalize.py`` so a new extract adds its own file
instead of appending to the shared suite.
"""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CARD_PATH = ROOT / "datasets" / "cards" / "worktrees-hives-v0.json"

REPO = "rmems/worktrees-hives"
CANONICAL = {
    61: (6,),
    63: (8,),
    65: (24, 25, 26, 28, 30, 40, 42),
    78: (37,),
}


def _card() -> dict:
    return json.loads(CARD_PATH.read_text(encoding="utf-8"))


def _synthetic_raw(pr: int, *, title: str, body: str = "No close keywords here.") -> dict:
    filename = (
        "crates/wh-core/src/worktree.rs"
        if pr == 65
        else "python/src/worktrees_hives/cli.py"
    )
    return {
        "source": {"repo": REPO, "pr_number": pr},
        "pull": {
            "title": title,
            "body": body,
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
                "body": (
                    "Please gate owner discovery behind WH_ALLOWED_OWNERS "
                    "before any gh repository listing."
                ),
            }
        ],
        "issue_comments": [],
        "files": [
            {
                "filename": filename,
                "status": "modified",
                "patch": "+x\n",
            }
        ],
        "checks": {},
        "commits": [],
    }


def test_domain_by_pr_beats_shared_dict():
    """Card domain_by_pr wins even when DOMAIN_OVERRIDE names the same PRs."""
    from lib.normalize import DOMAIN_OVERRIDE, domain_for

    assert not any(repo == "rmems/worktrees-hives" for repo, _pr in DOMAIN_OVERRIDE)
    card = _card()
    assert domain_for(REPO, 61, {}, {}) == "systems"

    planted = {
        ("rmems/worktrees-hives", 61): "tools",
        ("rmems/worktrees-hives", 63): "tools",
        ("rmems/worktrees-hives", 65): "tools",
        ("rmems/worktrees-hives", 78): "snn",
        ("rmems/worktrees-hives", 79): "snn",
    }
    DOMAIN_OVERRIDE.update(planted)
    try:
        assert domain_for(REPO, 61, {}, {}) == "tools"
        assert domain_for(REPO, 61, card, {}) == "agentic-workflow"
        assert domain_for(REPO, 63, card, {}) == "agentic-workflow"
        assert domain_for(REPO, 65, card, {}) == "ml-infra"
        assert domain_for(REPO, 78, card, {}) == "tools"
        assert domain_for(REPO, 79, card, {}) == "tools"
    finally:
        for key in planted:
            DOMAIN_OVERRIDE.pop(key, None)


def test_task_type_by_pr_beats_title_hints():
    """#61/#78 card entries must win over docs:/fix: titles and a bug label."""
    from lib.normalize import task_type_for

    card = _card()
    raw61 = {"pull": {"title": "docs: Issue #6 claim isolation"}}
    raw78 = {"pull": {"title": "fix: Wire discover/plan/babysit", "labels": ["bug"]}}
    raw79 = {"pull": {"title": "feat(cli): address review comments"}}
    assert task_type_for(REPO, 61, raw61, {}) == "docs"
    assert task_type_for(REPO, 61, raw61, card) == "feature"
    assert task_type_for(REPO, 78, raw78, {}) == "bugfix"
    assert task_type_for(REPO, 78, raw78, card) == "feature"
    assert task_type_for(REPO, 79, raw79, {}) == "feature"
    assert task_type_for(REPO, 79, raw79, card) == "bugfix"
    assert task_type_for(REPO, 63, {"pull": {"title": "chore: never auto-merge"}}, card) == "feature"
    assert task_type_for(REPO, 65, {"pull": {"title": "chore: hybrid foundation"}}, card) == "feature"


def test_language_by_pr_rust_on_hybrid_foundation():
    """#65 is mixed .rs/.py; card language is Python, language_by_pr forces Rust."""
    from lib.normalize import language_for

    card = _card()
    mixed = {
        "files": [
            {"filename": "crates/wh-core/src/worktree.rs"},
            {"filename": "python/src/worktrees_hives/bridge.py"},
        ]
    }
    py_only = {"files": [{"filename": "python/src/worktrees_hives/cli.py"}]}
    assert language_for(REPO, 65, {}, mixed) == "Rust"
    assert language_for(REPO, 65, {"language": "Python"}, mixed) == "Python"
    assert language_for(REPO, 65, card, mixed) == "Rust"
    assert language_for(REPO, 78, card, py_only) == "Python"
    assert language_for(REPO, 61, card, py_only) == "Python"


def test_canonical_pr_urls_and_linked_issues():
    """Card linked_issues_by_pr plus close keywords become provenance URLs."""
    from lib.normalize import normalize_record

    card = _card()
    cases = {
        61: ("Issue #6: Claim issue → branch → worktree isolation", "Closes #6"),
        63: ("Issue #8: Issue → PR workflow (never auto-merge)", "Closes #8"),
        65: (
            "Foundation: implement R1-R3, R5, P1, H1, H3",
            "Closes #24 #25 #26 #28 #30 #40 #42",
        ),
        78: (
            "Wire discover/plan/babysit into the CLI",
            "Issue #37 acceptance criterion was unmet.",
        ),
        79: (
            "fix(cli): address CodeAnt/CodeRabbit review comments on PR #78",
            "No close keywords here.",
        ),
    }
    for pr, (title, body) in cases.items():
        traj = normalize_record(_synthetic_raw(pr, title=title, body=body), card)
        assert traj["source_urls"][0] == f"https://github.com/{REPO}/pull/{pr}"
        for issue in CANONICAL.get(pr, ()):
            assert (
                f"https://github.com/{REPO}/issues/{issue}" in traj["source_urls"]
            )
        if pr == 79:
            assert traj["source_urls"] == [f"https://github.com/{REPO}/pull/79"]
        if pr == 61:
            assert traj["domain"] == "agentic-workflow"
            assert traj["task_type"] == "feature"
            assert traj["language"] == "Python"
            assert traj["training_use"] == "feature"
        if pr == 65:
            assert traj["domain"] == "ml-infra"
            assert traj["language"] == "Rust"
            assert traj["training_use"] == "feature"
        if pr == 78:
            assert traj["domain"] == "tools"
            assert traj["task_type"] == "feature"
            assert traj["training_use"] == "review-to-patch"
        if pr == 79:
            assert traj["domain"] == "tools"
            assert traj["task_type"] == "bugfix"
            assert traj["training_use"] == "review-to-patch"
