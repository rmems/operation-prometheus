"""Per-PR override regressions for rmems/corinth-canal (GH #24 / epic #32).

Split out of ``test_collect_and_normalize.py`` so a new extract adds its own file
instead of appending to the shared suite.
"""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CARD_PATH = ROOT / "datasets" / "cards" / "corinth-canal-v0.json"


def _card() -> dict:
    return json.loads(CARD_PATH.read_text(encoding="utf-8"))


def _synthetic_raw(pr: int, *, title: str, body: str = "No close keywords here.") -> dict:
    return {
        "source": {"repo": "rmems/corinth-canal", "pr_number": pr},
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
        "files": [{"filename": "src/moe/adapter.rs", "status": "modified", "patch": "+x\n"}],
        "checks": {},
        "commits": [],
    }


def test_domain_by_pr_beats_shared_dict():
    """Card is consulted before DOMAIN_OVERRIDE (same contract as test_card_overrides)."""
    from lib.normalize import domain_for

    assert domain_for("rmems/corinth-canal", 82, {}, {}) == "gpu-compute"
    overlay = {"domain_by_pr": {"82": "tools"}}
    assert domain_for("rmems/corinth-canal", 82, overlay, {}) == "tools"

    card = _card()
    assert "82" not in card["domain_by_pr"]
    assert domain_for("rmems/corinth-canal", 125, {}, {}) == "systems"
    assert domain_for("rmems/corinth-canal", 125, card, {}) == "ml-infra"
    assert domain_for("rmems/corinth-canal", 126, card, {}) == "gpu-compute"
    assert domain_for("rmems/corinth-canal", 127, card, {}) == "tools"
    assert domain_for("rmems/corinth-canal", 128, card, {}) == "ml-infra"
    assert domain_for("rmems/corinth-canal", 138, card, {}) == "gpu-compute"
    assert domain_for("rmems/corinth-canal", 142, card, {}) == "ml-infra"


def test_task_type_by_pr_beats_shared_dict():
    """Card is consulted before TASK_TYPE_OVERRIDE / title hints."""
    from lib.normalize import task_type_for

    raw82 = {"pull": {"title": "feat(moe): add Q6_K dequantized GPU synapse path"}}
    assert task_type_for("rmems/corinth-canal", 82, raw82, {}) == "feature"
    overlay = {"task_type_by_pr": {"82": "refactor"}}
    assert task_type_for("rmems/corinth-canal", 82, raw82, overlay) == "refactor"

    card = _card()
    assert "82" not in card["task_type_by_pr"]
    # Neutral title: no TITLE_TASK_HINTS prefix, so these results require task_type_by_pr.
    raw_neutral = {"pull": {"title": "unify GGUF/Safetensors family inference"}}
    assert task_type_for("rmems/corinth-canal", 125, raw_neutral, {}) == "other"
    assert task_type_for("rmems/corinth-canal", 125, raw_neutral, card) == "refactor"
    assert task_type_for("rmems/corinth-canal", 128, raw_neutral, card) == "refactor"
    assert task_type_for("rmems/corinth-canal", 138, raw_neutral, card) == "refactor"
    assert task_type_for("rmems/corinth-canal", 142, raw_neutral, card) == "bugfix"


def test_linked_issues_by_pr_on_card_in_source_urls():
    """normalize_record: canonical PR URL then card-declared issue provenance."""
    from lib.normalize import normalize_record

    card = _card()
    expected = {
        125: [133],
        126: [134],
        127: [135],
        128: [],
        138: [134],
        142: [140],
    }
    titles = {
        125: "refactor(moe): unify GGUF/Safetensors family inference",
        126: "refactor(moe): priority-ordered GGUF synapse source selection",
        127: "refactor(model): extract config validation helpers",
        128: "refactor(moe): split checkpoint.rs into private gguf/ modules",
        138: "refactor(moe): recover priority-ordered GGUF synapse source selection",
        142: "fix(examples): accept dense_sim/stub_uniform in ROUTING_MODE",
    }
    for pr, issues in expected.items():
        traj = normalize_record(_synthetic_raw(pr, title=titles[pr]), card)
        urls = traj["source_urls"]
        assert urls[0] == f"https://github.com/rmems/corinth-canal/pull/{pr}"
        assert urls[1:] == [
            f"https://github.com/rmems/corinth-canal/issues/{n}" for n in issues
        ]
