"""Card-first per-PR overrides (GH #37).

New extracts declare their per-PR labelling on their own dataset card
(``domain_by_pr`` / ``task_type_by_pr`` / ``linked_issues_by_pr``) instead of
appending to the shared tables in ``lib.normalize``. The module-level dicts stay
as the fallback for the extracts that predate this, and the two sources must
never disagree about the same PR — see ``test_no_card_and_dict_override_overlap``.
"""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CARDS = ROOT / "datasets" / "cards"


def test_card_pr_map_accepts_str_and_int_keys():
    from lib.normalize import card_pr_map

    card = {"task_type_by_pr": {"41": "feature", 50: "security", "bad": "x"}}
    assert card_pr_map(card, "task_type_by_pr") == {41: "feature", 50: "security"}


def test_card_pr_map_tolerates_missing_and_malformed():
    from lib.normalize import card_pr_map

    assert card_pr_map({}, "task_type_by_pr") == {}
    assert card_pr_map({"task_type_by_pr": None}, "task_type_by_pr") == {}
    assert card_pr_map({"task_type_by_pr": ["nope"]}, "task_type_by_pr") == {}


def test_task_type_by_pr_beats_title_hint():
    from lib.normalize import task_type_for

    raw = {"pull": {"title": "docs: update readme"}}
    card = {"task_type_by_pr": {"7": "feature"}}
    assert task_type_for("rmems/widget", 7, raw, card) == "feature"
    # Without the card entry the title hint still wins.
    assert task_type_for("rmems/widget", 7, raw, {}) == "docs"


def test_task_type_by_pr_beats_shared_dict():
    """Card is consulted before TASK_TYPE_OVERRIDE."""
    from lib.normalize import task_type_for

    raw = {"pull": {"title": "[WIP] something"}}
    assert task_type_for("rmems/myelin-accelerator", 7, raw, {}) == "feature"
    card = {"task_type_by_pr": {"7": "refactor"}}
    assert task_type_for("rmems/myelin-accelerator", 7, raw, card) == "refactor"


def test_domain_by_pr_beats_shared_dict():
    """Card is consulted before DOMAIN_OVERRIDE (precedence inverted in GH #37)."""
    from lib.normalize import domain_for

    assert domain_for("rmems/corinth-canal", 82, {}, {}) == "gpu-compute"
    card = {"domain_by_pr": {"82": "tools"}}
    assert domain_for("rmems/corinth-canal", 82, card, {}) == "tools"


def test_linked_issues_by_pr_on_card_adds_stubs():
    from lib.normalize import normalize_record

    raw = {
        "source": {"repo": "rmems/widget", "pr_number": 12},
        "pull": {
            "title": "feat: add thing",
            "body": "No close keywords here.",
            "state": "closed",
            "merged": True,
            "draft": False,
        },
        "linked_issues": [],
        "reviews": [],
        "review_comments": [],
        "issue_comments": [],
        "files": [{"filename": "src/lib.rs", "status": "modified", "patch": "+x\n"}],
        "checks": {},
        "commits": [],
    }
    card = {"linked_issues_by_pr": {"12": [4, 5]}}
    urls = normalize_record(raw, card)["source_urls"]
    assert urls == [
        "https://github.com/rmems/widget/pull/12",
        "https://github.com/rmems/widget/issues/4",
        "https://github.com/rmems/widget/issues/5",
    ]


def test_linked_issues_by_pr_rejects_non_positive_numbers():
    """A card typo like 0 or -1 must not mint an issues/0 provenance URL."""
    from lib.normalize import normalize_record

    raw = {
        "source": {"repo": "rmems/widget", "pr_number": 12},
        "pull": {
            "title": "feat: add thing",
            "body": "No close keywords here.",
            "state": "closed",
            "merged": True,
            "draft": False,
        },
        "linked_issues": [],
        "reviews": [],
        "review_comments": [],
        "issue_comments": [],
        "files": [{"filename": "src/lib.rs", "status": "modified", "patch": "+x\n"}],
        "checks": {},
        "commits": [],
    }
    card = {"linked_issues_by_pr": {"12": [0, -1, "-3", 5, "junk"]}}
    urls = normalize_record(raw, card)["source_urls"]
    assert urls == [
        "https://github.com/rmems/widget/pull/12",
        "https://github.com/rmems/widget/issues/5",
    ]


def test_linked_issues_by_pr_beats_shared_dict():
    from lib.normalize import enrich_linked_issues

    raw = {
        "source": {"repo": "rmems/grok-ozempic", "pr_number": 26},
        "pull": {"number": 26, "body": "No close keywords."},
        "linked_issues": [],
        "commits": [],
    }
    # Fallback table supplies #22 …
    assert [i["number"] for i in enrich_linked_issues(raw, {})] == [22]
    # … but the card wins when it declares the same PR.
    card = {"linked_issues_by_pr": {"26": [99]}}
    assert [i["number"] for i in enrich_linked_issues(raw, card)] == [99]


def test_no_card_and_dict_override_overlap():
    """A (repo, pr) pair must be declared in exactly one place, never both.

    Both sources are consulted for every record, so an overlap is a silent
    ambiguity: the card would win and the dict entry would look effective while
    doing nothing. Extracts land in parallel, so this has to be mechanical.
    """
    from lib.normalize import (
        CARD_OVERRIDE_KEYS,
        DOMAIN_OVERRIDE,
        LINKED_ISSUE_OVERRIDE,
        TASK_TYPE_OVERRIDE,
        card_pr_map,
    )

    dicts = {
        CARD_OVERRIDE_KEYS["domain"]: DOMAIN_OVERRIDE,
        CARD_OVERRIDE_KEYS["task_type"]: TASK_TYPE_OVERRIDE,
        CARD_OVERRIDE_KEYS["linked_issues"]: LINKED_ISSUE_OVERRIDE,
    }

    overlaps: list[str] = []
    for card_path in sorted(CARDS.glob("*.json")):
        card = json.loads(card_path.read_text(encoding="utf-8"))
        repo = str(card.get("source_repo") or "").strip().lower()
        if not repo:
            continue
        for card_key, table in dicts.items():
            for pr in card_pr_map(card, card_key):
                if (repo, pr) in table:
                    overlaps.append(f"{card_path.name}: {card_key} {repo}#{pr}")

    assert not overlaps, "override declared in both card and shared dict: " + "; ".join(
        overlaps
    )
