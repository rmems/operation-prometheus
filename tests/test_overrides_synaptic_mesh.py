"""Per-PR override regressions for Limen-Neural/synaptic-mesh (GH #66 Wave D)."""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CARD_PATH = ROOT / "datasets" / "cards" / "synaptic-mesh-v0.json"
REPO = "Limen-Neural/synaptic-mesh"


def _card() -> dict:
    return json.loads(CARD_PATH.read_text(encoding="utf-8"))


def _synthetic_raw(pr: int, *, title: str, body: str = "No close keywords here.") -> dict:
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
        "review_comments": [],
        "issue_comments": [],
        "files": [{"filename": "src/router.rs", "status": "modified", "patch": "+x\n"}],
        "checks": {},
        "commits": [],
    }


def test_domain_by_pr_beats_shared_dict():
    from lib.normalize import DOMAIN_OVERRIDE, domain_for

    assert not any(repo == "limen-neural/synaptic-mesh" for repo, _pr in DOMAIN_OVERRIDE)
    card = _card()
    assert domain_for(REPO, 8, {}, {}) == "systems"

    planted = {("limen-neural/synaptic-mesh", 8): "tools", ("limen-neural/synaptic-mesh", 7): "tools"}
    DOMAIN_OVERRIDE.update(planted)
    try:
        assert domain_for(REPO, 8, {}, {}) == "tools"
        assert domain_for(REPO, 8, card, {}) == "snn"
        assert domain_for(REPO, 7, card, {}) == "api"
        assert domain_for(REPO, 30, card, {}) == "snn"
        assert domain_for(REPO, 1, card, {}) == "snn"
    finally:
        for key in planted:
            DOMAIN_OVERRIDE.pop(key, None)


def test_task_type_by_pr_beats_documentation_label():
    from lib.normalize import task_type_for

    card = _card()
    raw7 = {
        "pull": {
            "title": "generalize AhlRouter to ChannelRouter",
            "labels": ["documentation", "size:L"],
        }
    }
    assert task_type_for(REPO, 7, raw7, {}) == "docs"
    assert task_type_for(REPO, 7, raw7, card) == "refactor"


def test_linked_issues_from_close_keywords_in_normalize_record():
    from lib.normalize import normalize_record

    card = _card()
    traj = normalize_record(
        _synthetic_raw(7, title="refactor(router): ChannelRouter", body="Implements Option B from #6."),
        card,
    )
    assert traj["source_urls"][0] == "https://github.com/Limen-Neural/synaptic-mesh/pull/7"
    assert "https://github.com/Limen-Neural/synaptic-mesh/issues/6" in traj["source_urls"]
    assert traj["domain"] == "api"
    assert traj["task_type"] == "refactor"
    assert traj["training_use"] == "repair"
