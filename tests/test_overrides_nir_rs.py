"""Per-PR override regressions for Limen-Neural/nir-rs (GH #66 Wave D)."""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CARD_PATH = ROOT / "datasets" / "cards" / "nir-rs-v0.json"
REPO = "Limen-Neural/nir-rs"


def _card() -> dict:
    return json.loads(CARD_PATH.read_text(encoding="utf-8"))


def test_domain_by_pr_beats_shared_dict():
    from lib.normalize import DOMAIN_OVERRIDE, domain_for

    assert not any(repo == "limen-neural/nir-rs" for repo, _pr in DOMAIN_OVERRIDE)
    card = _card()
    assert domain_for(REPO, 20, {}, {}) == "systems"

    planted = {("limen-neural/nir-rs", 20): "tools", ("limen-neural/nir-rs", 24): "tools"}
    DOMAIN_OVERRIDE.update(planted)
    try:
        assert domain_for(REPO, 20, {}, {}) == "tools"
        assert domain_for(REPO, 20, card, {}) == "io"
        assert domain_for(REPO, 23, card, {}) == "io"
        assert domain_for(REPO, 18, card, {}) == "io"
        assert domain_for(REPO, 24, card, {}) == "api"
    finally:
        for key in planted:
            DOMAIN_OVERRIDE.pop(key, None)


def test_task_type_by_pr_beats_title_hints():
    from lib.normalize import task_type_for

    card = _card()
    raw23 = {"pull": {"title": "fix(io): harden untrusted reads and atomic writes"}}
    assert task_type_for(REPO, 23, raw23, {}) == "bugfix"
    assert task_type_for(REPO, 23, raw23, card) == "security"
