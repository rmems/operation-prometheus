"""Per-PR override regressions for Limen-Neural/brainstem-daemon (GH #28 Wave B+).

Split out of ``test_collect_and_normalize.py`` so a new extract adds its own file
instead of appending to the shared suite.
"""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CARD_PATH = ROOT / "datasets" / "cards" / "brainstem-daemon-v0.json"


def _card() -> dict:
    return json.loads(CARD_PATH.read_text(encoding="utf-8"))


def _synthetic_raw(pr: int, *, title: str, body: str = "No close keywords here.") -> dict:
    return {
        "source": {"repo": "Limen-Neural/brainstem-daemon", "pr_number": pr},
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
                "body": "Please keep the local IngressPacket trait independent of corpus-ipc types so the stub backend stays compile-clean.",
                "path": "src/backend.rs",
                "line": 10,
            }
        ],
        "issue_comments": [],
        "files": [
            {
                "filename": "src/daemon.rs",
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

    assert not any(
        repo == "limen-neural/brainstem-daemon" for repo, _pr in DOMAIN_OVERRIDE
    )
    card = _card()
    assert domain_for("Limen-Neural/brainstem-daemon", 8, {}, {}) == "systems"

    planted = {
        ("limen-neural/brainstem-daemon", 8): "tools",
        ("limen-neural/brainstem-daemon", 24): "tools",
        ("limen-neural/brainstem-daemon", 25): "tools",
    }
    DOMAIN_OVERRIDE.update(planted)
    try:
        assert domain_for("Limen-Neural/brainstem-daemon", 8, {}, {}) == "tools"
        assert domain_for("Limen-Neural/brainstem-daemon", 8, card, {}) == "infra"
        assert domain_for("Limen-Neural/brainstem-daemon", 24, card, {}) == "api"
        assert domain_for("Limen-Neural/brainstem-daemon", 25, card, {}) == "snn"
        assert domain_for("Limen-Neural/brainstem-daemon", 3, card, {}) == "snn"
    finally:
        for key in planted:
            DOMAIN_OVERRIDE.pop(key, None)


def test_task_type_by_pr_beats_title_hints():
    """#8/#24/#3 card entries must win over feat: / unlabeled titles."""
    from lib.normalize import task_type_for

    card = _card()
    raw8 = {"pull": {"title": "feat: resolve open issues #4, #5, #6, #7"}}
    raw24 = {
        "pull": {
            "title": "feat: temporary corpus-ipc decoupling (issues #10, #11, #12, #14)"
        }
    }
    raw3 = {"pull": {"title": "Migrate daemon to corpus-ipc and neuromod v0.4.0"}}
    assert task_type_for("Limen-Neural/brainstem-daemon", 8, raw8, {}) == "feature"
    assert task_type_for("Limen-Neural/brainstem-daemon", 8, raw8, card) == "refactor"
    assert task_type_for("Limen-Neural/brainstem-daemon", 24, raw24, {}) == "feature"
    assert task_type_for("Limen-Neural/brainstem-daemon", 24, raw24, card) == "refactor"
    assert task_type_for("Limen-Neural/brainstem-daemon", 3, raw3, {}) == "other"
    assert task_type_for("Limen-Neural/brainstem-daemon", 3, raw3, card) == "feature"

    raw25 = {
        "pull": {
            "title": "Fallible BrainstemDaemon construction with neuron-count validation"
        }
    }
    assert task_type_for("Limen-Neural/brainstem-daemon", 25, raw25, {}) == "other"
    assert task_type_for("Limen-Neural/brainstem-daemon", 25, raw25, card) == "bugfix"


def test_linked_issues_by_pr_on_card_in_source_urls():
    """#24 names issues #10–#14 without close keywords — card provenance wins."""
    from lib.normalize import normalize_record

    card = _card()
    traj = normalize_record(
        _synthetic_raw(
            24,
            title="feat: temporary corpus-ipc decoupling (issues #10, #11, #12, #14)",
            body="Implements the corpus-ipc side of the plan in #9 without close keywords.",
        ),
        card,
    )
    assert traj["source_urls"][0] == (
        "https://github.com/Limen-Neural/brainstem-daemon/pull/24"
    )
    assert len(traj["source_urls"]) == 6
    assert len(traj["source_urls"]) == len(set(traj["source_urls"]))
    for issue in (9, 10, 11, 12, 14):
        assert (
            f"https://github.com/Limen-Neural/brainstem-daemon/issues/{issue}"
            in traj["source_urls"]
        )
    assert traj["domain"] == "api"
    assert traj["task_type"] == "refactor"
    assert traj["training_use"] == "review-to-patch"
    assert traj["language"] == "Rust"
