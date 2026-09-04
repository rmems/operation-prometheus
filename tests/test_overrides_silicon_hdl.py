"""Per-PR override regressions for rmems/silicon-hdl (GH #66 Wave D)."""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CARD_PATH = ROOT / "datasets" / "cards" / "silicon-hdl-v0.json"
REPO = "rmems/silicon-hdl"


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
        "reviews": [{"user_login": "reviewer", "body": "Please add a CDC synchronizer on UartRx.", "state": "CHANGES_REQUESTED"}],
        "review_comments": [],
        "issue_comments": [],
        "files": [{"filename": "spikenaut-core-sv/rtl/LifNeuron.sv", "status": "modified", "patch": "+x\n"}],
        "checks": {},
        "commits": [],
    }


def test_domain_by_pr_beats_shared_dict():
    from lib.normalize import DOMAIN_OVERRIDE, domain_for

    assert not any(repo == "rmems/silicon-hdl" for repo, _pr in DOMAIN_OVERRIDE)
    card = _card()
    assert domain_for(REPO, 81, {}, {}) == "systems"

    planted = {("rmems/silicon-hdl", 81): "tools"}
    DOMAIN_OVERRIDE.update(planted)
    try:
        assert domain_for(REPO, 81, {}, {}) == "tools"
        assert domain_for(REPO, 81, card, {}) == "hdl"
        assert domain_for(REPO, 51, card, {}) == "hdl"
        assert domain_for(REPO, 15, card, {}) == "hdl"
    finally:
        for key in planted:
            DOMAIN_OVERRIDE.pop(key, None)


def test_task_type_by_pr_beats_title_hints():
    from lib.normalize import task_type_for

    card = _card()
    raw11 = {"pull": {"title": "Clean up basys3.xdc, fix LifNeuron spike-reset bug"}}
    assert task_type_for(REPO, 11, raw11, {}) == "other"
    assert task_type_for(REPO, 11, raw11, card) == "bugfix"


def test_review_to_patch_and_systemverilog_language():
    from lib.normalize import normalize_record

    card = _card()
    traj = normalize_record(
        _synthetic_raw(15, title="fix(gh-14): address unresolved bot review", body="Closes #14."),
        card,
    )
    assert traj["language"] == "SystemVerilog"
    assert traj["training_use"] == "review-to-patch"
    assert traj["task_type"] == "bugfix"
    assert traj["review_signals"]
    assert "https://github.com/rmems/silicon-hdl/issues/14" in traj["source_urls"]
