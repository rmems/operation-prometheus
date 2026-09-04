"""Per-PR override regressions for rmems/agoge-forger (GH #66 Wave D)."""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CARD_PATH = ROOT / "datasets" / "cards" / "agoge-forger-v0.json"
REPO = "rmems/agoge-forger"


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
        "files": [{"filename": "src/agoge_forger/cli.py", "status": "modified", "patch": "+x\n"}],
        "checks": {},
        "commits": [],
    }


def test_domain_by_pr_beats_shared_dict():
    from lib.normalize import DOMAIN_OVERRIDE, domain_for

    assert not any(repo == "rmems/agoge-forger" for repo, _pr in DOMAIN_OVERRIDE)
    card = _card()
    assert domain_for(REPO, 120, {}, {}) == "systems"

    planted = {("rmems/agoge-forger", 120): "tools", ("rmems/agoge-forger", 67): "tools"}
    DOMAIN_OVERRIDE.update(planted)
    try:
        assert domain_for(REPO, 120, {}, {}) == "tools"
        assert domain_for(REPO, 120, card, {}) == "ml-infra"
        assert domain_for(REPO, 67, card, {}) == "training"
        assert domain_for(REPO, 85, card, {}) == "ml-infra"
        assert domain_for(REPO, 86, card, {}) == "training"
    finally:
        for key in planted:
            DOMAIN_OVERRIDE.pop(key, None)


def test_linked_issues_from_close_keywords_in_normalize_record():
    from lib.normalize import normalize_record

    card = _card()
    traj = normalize_record(
        _synthetic_raw(85, title="fix: harden empty JSONL", body="Closes #65"),
        card,
    )
    assert traj["source_urls"][0] == "https://github.com/rmems/agoge-forger/pull/85"
    assert "https://github.com/rmems/agoge-forger/issues/65" in traj["source_urls"]
    assert traj["domain"] == "ml-infra"
    assert traj["task_type"] == "bugfix"
    assert traj["training_use"] == "repair"
    assert traj["language"] == "Python"
