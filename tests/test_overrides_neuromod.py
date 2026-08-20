"""Per-PR override regressions for Limen-Neural/neuromod (GH #28 Wave B+).

Split out of ``test_collect_and_normalize.py`` so a new extract adds its own file
instead of appending to the shared suite.
"""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CARD_PATH = ROOT / "datasets" / "cards" / "neuromod-v0.json"


def _card() -> dict:
    return json.loads(CARD_PATH.read_text(encoding="utf-8"))


def _synthetic_raw(pr: int, *, title: str, body: str = "No close keywords here.") -> dict:
    return {
        "source": {"repo": "Limen-Neural/neuromod", "pr_number": pr},
        "pull": {
            "title": title,
            "body": body,
            "state": "closed",
            "merged": True,
            "draft": False,
        },
        "linked_issues": [],
        "reviews": [],
        "review_comments": [],
        "issue_comments": [],
        "files": [
            {
                "filename": "src/hodgkin_huxley.rs",
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

    assert not any(repo == "limen-neural/neuromod" for repo, _pr in DOMAIN_OVERRIDE)
    card = _card()
    assert domain_for("Limen-Neural/neuromod", 5, {}, {}) == "systems"

    planted = {
        ("limen-neural/neuromod", 5): "tools",
        ("limen-neural/neuromod", 9): "tools",
        ("limen-neural/neuromod", 15): "tools",
    }
    DOMAIN_OVERRIDE.update(planted)
    try:
        assert domain_for("Limen-Neural/neuromod", 5, {}, {}) == "tools"
        assert domain_for("Limen-Neural/neuromod", 5, card, {}) == "snn"
        assert domain_for("Limen-Neural/neuromod", 8, card, {}) == "snn"
        assert domain_for("Limen-Neural/neuromod", 9, card, {}) == "api"
        assert domain_for("Limen-Neural/neuromod", 2, card, {}) == "snn"
        assert domain_for("Limen-Neural/neuromod", 15, card, {}) == "ml-infra"
    finally:
        for key in planted:
            DOMAIN_OVERRIDE.pop(key, None)


def test_task_type_by_pr_beats_title_hints():
    """#8/#9/#2 card entries must win over Fix:/neutral titles."""
    from lib.normalize import task_type_for

    card = _card()
    raw8 = {"pull": {"title": "Fix bench warnings"}}
    raw9 = {"pull": {"title": "Generalize neuromod core: dynamic dimensions"}}
    raw2 = {"pull": {"title": "SNN Core: Mining & HFT Purge"}}
    assert task_type_for("Limen-Neural/neuromod", 8, raw8, {}) == "bugfix"
    assert task_type_for("Limen-Neural/neuromod", 8, raw8, card) == "refactor"
    assert task_type_for("Limen-Neural/neuromod", 9, raw9, {}) == "other"
    assert task_type_for("Limen-Neural/neuromod", 9, raw9, card) == "refactor"
    assert task_type_for("Limen-Neural/neuromod", 2, raw2, {}) == "other"
    assert task_type_for("Limen-Neural/neuromod", 2, raw2, card) == "refactor"


def test_linked_issues_by_pr_on_card_in_source_urls():
    """#5 names issue #3 without a close keyword — card provenance wins."""
    from lib.normalize import normalize_record

    card = _card()
    traj = normalize_record(
        _synthetic_raw(
            5,
            title="feat: add Lapicque, Hodgkin-Huxley, FitzHugh-Nagumo, and Hebbian neuron models",
            body="Implements the four foundational neuroscience models requested in issue #3.",
        ),
        card,
    )
    assert traj["source_urls"][0] == "https://github.com/Limen-Neural/neuromod/pull/5"
    assert "https://github.com/Limen-Neural/neuromod/issues/3" in traj["source_urls"]
    assert traj["domain"] == "snn"
    assert traj["task_type"] == "feature"
    assert traj["language"] == "Rust"
    assert traj["training_use"] == "feature"
