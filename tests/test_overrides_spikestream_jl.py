"""Per-PR override regressions for rmems/SpikeStream.jl (GH #28 Wave B+).

Split out of ``test_collect_and_normalize.py`` so a new extract adds its own file
instead of appending to the shared suite.
"""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CARD_PATH = ROOT / "datasets" / "cards" / "spikestream-jl-v0.json"


def _card() -> dict:
    return json.loads(CARD_PATH.read_text(encoding="utf-8"))


def _synthetic_raw(pr: int, *, title: str, body: str = "No close keywords here.") -> dict:
    return {
        "source": {"repo": "rmems/SpikeStream.jl", "pr_number": pr},
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
                "filename": "src/spike_features.jl",
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

    assert not any(repo == "rmems/spikestream.jl" for repo, _pr in DOMAIN_OVERRIDE)
    card = _card()
    assert domain_for("rmems/SpikeStream.jl", 7, {}, {}) == "systems"

    planted = {
        ("rmems/spikestream.jl", 7): "tools",
        ("rmems/spikestream.jl", 22): "snn",
        ("rmems/spikestream.jl", 21): "snn",
    }
    DOMAIN_OVERRIDE.update(planted)
    try:
        assert domain_for("rmems/SpikeStream.jl", 7, {}, {}) == "tools"
        assert domain_for("rmems/SpikeStream.jl", 7, card, {}) == "snn"
        assert domain_for("rmems/SpikeStream.jl", 25, card, {}) == "snn"
        assert domain_for("rmems/SpikeStream.jl", 22, card, {}) == "api"
        assert domain_for("rmems/SpikeStream.jl", 21, card, {}) == "tools"
    finally:
        for key in planted:
            DOMAIN_OVERRIDE.pop(key, None)


def test_task_type_by_pr_beats_title_hints():
    """#22/#21 card entries must win over chore: titles."""
    from lib.normalize import task_type_for

    card = _card()
    raw22 = {
        "pull": {
            "title": "chore(api): remove transitional Hurst/Hawkes/GBM compute_ functions (LIM-47)"
        }
    }
    raw21 = {"pull": {"title": "chore: Add streaming benchmarks (#15)"}}
    assert task_type_for("rmems/SpikeStream.jl", 22, raw22, {}) == "chore"
    assert task_type_for("rmems/SpikeStream.jl", 22, raw22, card) == "refactor"
    assert task_type_for("rmems/SpikeStream.jl", 21, raw21, {}) == "chore"
    assert task_type_for("rmems/SpikeStream.jl", 21, raw21, card) == "test"


def test_language_and_buckets_on_card():
    from lib.normalize import normalize_record

    card = _card()
    traj = normalize_record(
        _synthetic_raw(
            7,
            title="Re-scope SpikeStream around spike-stream feature extraction",
        ),
        card,
    )
    assert traj["source_urls"][0] == "https://github.com/rmems/SpikeStream.jl/pull/7"
    assert traj["domain"] == "snn"
    assert traj["language"] == "Julia"
    assert traj["training_use"] == "feature"
    assert traj["task_type"] == "feature"
