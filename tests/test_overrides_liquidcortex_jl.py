"""Per-PR override regressions for rmems/LiquidCortex.jl (GH #66 Wave D)."""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CARD_PATH = ROOT / "datasets" / "cards" / "liquidcortex-jl-v0.json"
REPO = "rmems/LiquidCortex.jl"


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
        "files": [{"filename": "src/LiquidCortex.jl", "status": "modified", "patch": "+x\n"}],
        "checks": {},
        "commits": [],
    }


def test_domain_by_pr_beats_shared_dict():
    from lib.normalize import DOMAIN_OVERRIDE, domain_for

    assert not any(repo == "rmems/liquidcortex.jl" for repo, _pr in DOMAIN_OVERRIDE)
    card = _card()
    assert domain_for(REPO, 45, {}, {}) == "systems"

    planted = {("rmems/liquidcortex.jl", 45): "tools"}
    DOMAIN_OVERRIDE.update(planted)
    try:
        assert domain_for(REPO, 45, {}, {}) == "tools"
        assert domain_for(REPO, 45, card, {}) == "gpu-compute"
        assert domain_for(REPO, 12, card, {}) == "snn"
        assert domain_for(REPO, 33, card, {}) == "snn"
    finally:
        for key in planted:
            DOMAIN_OVERRIDE.pop(key, None)


def test_linked_issues_by_pr_on_card_in_source_urls():
    from lib.normalize import normalize_record

    card = _card()
    traj = normalize_record(
        _synthetic_raw(33, title="test: add reference LSM coverage", body="Adds coverage."),
        card,
    )
    assert traj["source_urls"][0] == "https://github.com/rmems/LiquidCortex.jl/pull/33"
    assert "https://github.com/rmems/LiquidCortex.jl/issues/22" in traj["source_urls"]
    assert traj["domain"] == "snn"
    assert traj["task_type"] == "test"
    assert traj["training_use"] == "validation"
    assert traj["language"] == "Julia"
