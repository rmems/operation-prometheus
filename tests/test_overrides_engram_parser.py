"""Per-PR override regressions for rmems/engram-parser (GH #29 Wave C).

Split out of ``test_collect_and_normalize.py`` so a new extract adds its own file
instead of appending to the shared suite.
"""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CARD_PATH = ROOT / "datasets" / "cards" / "engram-parser-v0.json"
REPO = "rmems/engram-parser"


def _card() -> dict:
    return json.loads(CARD_PATH.read_text(encoding="utf-8"))


def test_domain_by_pr_beats_shared_dict():
    """Card domain_by_pr wins even when DOMAIN_OVERRIDE names the same PRs."""
    from lib.normalize import DOMAIN_OVERRIDE, domain_for

    assert not any(repo == "rmems/engram-parser" for repo, _pr in DOMAIN_OVERRIDE)
    card = _card()
    assert domain_for(REPO, 44, {}, {}) == "systems"

    planted = {("rmems/engram-parser", 44): "tools"}
    DOMAIN_OVERRIDE.update(planted)
    try:
        assert domain_for(REPO, 44, {}, {}) == "tools"
        assert domain_for(REPO, 44, card, {}) == "ml-infra"
    finally:
        for key in planted:
            DOMAIN_OVERRIDE.pop(key, None)
