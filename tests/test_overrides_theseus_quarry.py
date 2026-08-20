"""Per-PR override regressions for rmems/Theseus-Quarry (GH #27).

Split out of ``test_collect_and_normalize.py`` so a new extract adds its own file
instead of appending to the shared suite.
"""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CARD_PATH = ROOT / "datasets" / "cards" / "theseus-quarry-v0.json"


def _card() -> dict:
    return json.loads(CARD_PATH.read_text(encoding="utf-8"))


def _synthetic_raw(pr: int, *, title: str, body: str = "No close keywords here.") -> dict:
    return {
        "source": {"repo": "rmems/Theseus-Quarry", "pr_number": pr},
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
                "filename": "crates/telemetry-collector/src/main.rs",
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

    assert not any(repo == "rmems/theseus-quarry" for repo, _pr in DOMAIN_OVERRIDE)
    card = _card()
    assert domain_for("rmems/Theseus-Quarry", 8, {}, {}) == "systems"

    planted = {
        ("rmems/theseus-quarry", 8): "tools",
        ("rmems/theseus-quarry", 9): "tools",
        ("rmems/theseus-quarry", 12): "tools",
    }
    DOMAIN_OVERRIDE.update(planted)
    try:
        assert domain_for("rmems/Theseus-Quarry", 8, {}, {}) == "tools"
        assert domain_for("rmems/Theseus-Quarry", 8, card, {}) == "infra"
        assert domain_for("rmems/Theseus-Quarry", 9, card, {}) == "gpu-compute"
        assert domain_for("rmems/Theseus-Quarry", 12, card, {}) == "telemetry"
        assert domain_for("rmems/Theseus-Quarry", 13, card, {}) == "telemetry"
        assert domain_for("rmems/Theseus-Quarry", 11, card, {}) == "telemetry"
    finally:
        for key in planted:
            DOMAIN_OVERRIDE.pop(key, None)


def test_task_type_by_pr_beats_title_hints():
    """#8/#12 card entries must win over arch:/feat: titles."""
    from lib.normalize import task_type_for

    card = _card()
    raw8 = {"pull": {"title": "arch: remove theseus-mining supervisor"}}
    raw12 = {"pull": {"title": "feat(telemetry): align miner API ports"}}
    assert task_type_for("rmems/Theseus-Quarry", 8, raw8, {}) == "other"
    assert task_type_for("rmems/Theseus-Quarry", 8, raw8, card) == "refactor"
    assert task_type_for("rmems/Theseus-Quarry", 12, raw12, {}) == "feature"
    assert task_type_for("rmems/Theseus-Quarry", 12, raw12, card) == "bugfix"


def test_linked_issues_from_close_keywords_in_normalize_record():
    """Resolves/Closes in the body become issue provenance URLs (no card map)."""
    from lib.normalize import normalize_record

    card = _card()
    cases = {
        13: (5, "Telemetry: Migrate MinerPerf collection to HTTP APIs", "Resolves #5"),
        9: (4, "Port GPU thermal throttling process signaling", "Resolves #4"),
        12: (7, "feat(telemetry): align miner API ports", "Resolves #7."),
        11: (6, "feat(telemetry): implement file rotation", "Resolves #6."),
        8: (3, "arch: remove theseus-mining supervisor", "Closes #3"),
    }
    for pr, (issue, title, body) in cases.items():
        traj = normalize_record(_synthetic_raw(pr, title=title, body=body), card)
        assert traj["source_urls"][0] == (
            f"https://github.com/rmems/Theseus-Quarry/pull/{pr}"
        )
        assert (
            f"https://github.com/rmems/Theseus-Quarry/issues/{issue}"
            in traj["source_urls"]
        )
        if pr == 8:
            assert traj["domain"] == "infra"
            assert traj["task_type"] == "refactor"
        if pr == 12:
            assert traj["domain"] == "telemetry"
            assert traj["task_type"] == "bugfix"
        if pr == 9:
            assert traj["domain"] == "gpu-compute"
            assert traj["language"] == "Rust"
