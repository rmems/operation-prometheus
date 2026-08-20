"""Per-PR override regressions for rmems/xai-dissect (GH #29 Wave C).

Split out of ``test_collect_and_normalize.py`` so a new extract adds its own file
instead of appending to the shared suite.
"""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CARD_PATH = ROOT / "datasets" / "cards" / "xai-dissect-v0.json"
REPO = "rmems/xai-dissect"


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
            "labels": ["documentation"] if pr == 34 else [],
        },
        "linked_issues": [],
        "reviews": [],
        "review_comments": [],
        "issue_comments": [],
        "files": [
            {
                "filename": "src/exports/mod.rs",
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

    assert not any(repo == "rmems/xai-dissect" for repo, _pr in DOMAIN_OVERRIDE)
    card = _card()
    assert domain_for(REPO, 32, {}, {}) == "systems"

    planted = {
        ("rmems/xai-dissect", 32): "tools",
        ("rmems/xai-dissect", 34): "tools",
        ("rmems/xai-dissect", 24): "tools",
        ("rmems/xai-dissect", 36): "tools",
    }
    DOMAIN_OVERRIDE.update(planted)
    try:
        assert domain_for(REPO, 32, {}, {}) == "tools"
        assert domain_for(REPO, 32, card, {}) == "export"
        assert domain_for(REPO, 34, card, {}) == "export"
        assert domain_for(REPO, 24, card, {}) == "ml-infra"
        assert domain_for(REPO, 36, card, {}) == "quantization"
    finally:
        for key in planted:
            DOMAIN_OVERRIDE.pop(key, None)


def test_task_type_by_pr_beats_title_hints_and_docs_label():
    """#32/#24 unconventional titles and #34 documentation label must not win."""
    from lib.normalize import task_type_for

    card = _card()
    raw32 = {"pull": {"title": "Define xai-dissect export contract for grok-ozempic"}}
    raw24 = {"pull": {"title": "Implement strict Grok-1 coverage manifest validation"}}
    raw34 = {
        "pull": {
            "title": "Export conversion-ready Grok-1 tensor manifest for SAAQ sprint",
            "labels": ["documentation"],
        }
    }
    assert task_type_for(REPO, 32, raw32, {}) == "other"
    assert task_type_for(REPO, 32, raw32, card) == "feature"
    assert task_type_for(REPO, 24, raw24, {}) == "other"
    assert task_type_for(REPO, 24, raw24, card) == "feature"
    assert task_type_for(REPO, 34, raw34, {}) == "docs"
    assert task_type_for(REPO, 34, raw34, card) == "feature"


def test_linked_issues_from_close_keywords_in_normalize_record():
    from lib.normalize import normalize_record

    card = _card()
    cases = {
        32: (21, "Define xai-dissect export contract for grok-ozempic", "Closes #21"),
        34: (
            23,
            "Export conversion-ready Grok-1 tensor manifest for SAAQ sprint",
            "Closes #23",
        ),
        24: (22, "Implement strict Grok-1 coverage manifest validation", "Closes #22."),
    }
    for pr, (issue, title, body) in cases.items():
        traj = normalize_record(_synthetic_raw(pr, title=title, body=body), card)
        assert traj["source_urls"][0] == f"https://github.com/{REPO}/pull/{pr}"
        assert f"https://github.com/{REPO}/issues/{issue}" in traj["source_urls"]
        assert traj["task_type"] == "feature"
        if pr in (32, 34):
            assert traj["domain"] == "export"
        if pr == 24:
            assert traj["domain"] == "ml-infra"
