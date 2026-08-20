"""Per-PR override regressions for rmems/kinetic-signals (GH #28 Wave B+).

Split out of ``test_collect_and_normalize.py`` so a new extract adds its own file
instead of appending to the shared suite.
"""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CARD_PATH = ROOT / "datasets" / "cards" / "kinetic-signals-v0.json"


def _card() -> dict:
    return json.loads(CARD_PATH.read_text(encoding="utf-8"))


def _synthetic_raw(pr: int, *, title: str, body: str = "No close keywords here.") -> dict:
    return {
        "source": {"repo": "rmems/kinetic-signals", "pr_number": pr},
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
                "filename": "src/hawkes.rs",
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

    assert not any(repo == "rmems/kinetic-signals" for repo, _pr in DOMAIN_OVERRIDE)
    card = _card()
    assert domain_for("rmems/kinetic-signals", 39, {}, {}) == "systems"

    planted = {
        ("rmems/kinetic-signals", 39): "tools",
        ("rmems/kinetic-signals", 17): "tools",
        ("rmems/kinetic-signals", 6): "tools",
        ("rmems/kinetic-signals", 1): "tools",
    }
    DOMAIN_OVERRIDE.update(planted)
    try:
        assert domain_for("rmems/kinetic-signals", 39, {}, {}) == "tools"
        assert domain_for("rmems/kinetic-signals", 39, card, {}) == "telemetry"
        assert domain_for("rmems/kinetic-signals", 35, card, {}) == "telemetry"
        assert domain_for("rmems/kinetic-signals", 17, card, {}) == "snn"
        assert domain_for("rmems/kinetic-signals", 6, card, {}) == "infra"
        assert domain_for("rmems/kinetic-signals", 1, card, {}) == "ml-infra"
    finally:
        for key in planted:
            DOMAIN_OVERRIDE.pop(key, None)


def test_task_type_by_pr_beats_title_hints():
    """#6/#1 card entries must win over enhancement-label / untitled hints."""
    from lib.normalize import task_type_for

    card = _card()
    raw6 = {
        "pull": {
            "title": "Dev environment setup + resolve open issues (#3, #4, #5)",
            "labels": ["documentation", "enhancement"],
        }
    }
    raw1 = {"pull": {"title": "Generalizing"}}
    assert task_type_for("rmems/kinetic-signals", 6, raw6, {}) == "feature"
    assert task_type_for("rmems/kinetic-signals", 6, raw6, card) == "refactor"
    assert task_type_for("rmems/kinetic-signals", 1, raw1, {}) == "other"
    assert task_type_for("rmems/kinetic-signals", 1, raw1, card) == "refactor"


def test_linked_issues_by_pr_on_card_in_source_urls():
    """#39/#35 name issues without close keywords — card provenance wins."""
    from lib.normalize import normalize_record

    card = _card()
    traj39 = normalize_record(
        _synthetic_raw(
            39,
            title="test: expand shared_vectors for streaming APIs (LIM-201, #28)",
            body="Expand fixtures for streaming Hawkes. Mentions issue 28 without closing it.",
        ),
        card,
    )
    assert traj39["source_urls"][0] == (
        "https://github.com/rmems/kinetic-signals/pull/39"
    )
    assert "https://github.com/rmems/kinetic-signals/issues/28" in traj39["source_urls"]
    assert traj39["domain"] == "telemetry"
    assert traj39["task_type"] == "test"
    assert traj39["training_use"] == "validation"
    assert traj39["language"] == "Rust"

    traj35 = normalize_record(
        _synthetic_raw(
            35,
            title="test: expand demo for missing APIs (LIM-199, #26)",
        ),
        card,
    )
    assert "https://github.com/rmems/kinetic-signals/issues/26" in traj35["source_urls"]
    assert traj35["domain"] == "telemetry"
