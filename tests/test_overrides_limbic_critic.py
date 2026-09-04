"""Per-PR override regressions for rmems/limbic-critic (GH #66 Wave D)."""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CARD_PATH = ROOT / "datasets" / "cards" / "limbic-critic-v0.json"
REPO = "rmems/limbic-critic"


def _card() -> dict:
    return json.loads(CARD_PATH.read_text(encoding="utf-8"))


def test_domain_by_pr_beats_shared_dict():
    from lib.normalize import DOMAIN_OVERRIDE, domain_for

    assert not any(repo == "rmems/limbic-critic" for repo, _pr in DOMAIN_OVERRIDE)
    card = _card()
    assert domain_for(REPO, 30, {}, {}) == "systems"

    planted = {("rmems/limbic-critic", 30): "tools", ("rmems/limbic-critic", 29): "tools"}
    DOMAIN_OVERRIDE.update(planted)
    try:
        assert domain_for(REPO, 30, {}, {}) == "tools"
        assert domain_for(REPO, 30, card, {}) == "snn"
        assert domain_for(REPO, 29, card, {}) == "api"
        assert domain_for(REPO, 2, card, {}) == "snn"
        assert domain_for(REPO, 3, card, {}) == "api"
    finally:
        for key in planted:
            DOMAIN_OVERRIDE.pop(key, None)


def test_task_type_by_pr_beats_title_hints():
    from lib.normalize import task_type_for

    card = _card()
    raw3 = {"pull": {"title": "Updating crate to fit nre modular crate goals"}}
    assert task_type_for(REPO, 3, raw3, {}) == "other"
    assert task_type_for(REPO, 3, raw3, card) == "refactor"
