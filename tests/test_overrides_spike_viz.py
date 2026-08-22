"""Per-PR override regressions for rmems/spike-viz (GH #29 Wave C).

Split out of ``test_collect_and_normalize.py`` so a new extract adds its own file
instead of appending to the shared suite.
"""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CARD_PATH = ROOT / "datasets" / "cards" / "spike-viz-v0.json"
REPO = "rmems/spike-viz"


def _card() -> dict:
    return json.loads(CARD_PATH.read_text(encoding="utf-8"))


def test_domain_by_pr_beats_shared_dict():
    """Card domain_by_pr wins even when DOMAIN_OVERRIDE names the same PRs."""
    from lib.normalize import DOMAIN_OVERRIDE, domain_for

    assert not any(repo == "rmems/spike-viz" for repo, _pr in DOMAIN_OVERRIDE)
    card = _card()
    assert domain_for(REPO, 24, {}, {}) == "systems"

    planted = {
        ("rmems/spike-viz", 24): "tools",
        ("rmems/spike-viz", 22): "tools",
        ("rmems/spike-viz", 23): "tools",
    }
    DOMAIN_OVERRIDE.update(planted)
    try:
        assert domain_for(REPO, 24, {}, {}) == "tools"
        assert domain_for(REPO, 24, card, {}) == "visualization"
        assert domain_for(REPO, 22, card, {}) == "io"
        assert domain_for(REPO, 23, card, {}) == "io"
    finally:
        for key in planted:
            DOMAIN_OVERRIDE.pop(key, None)
