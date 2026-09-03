from __future__ import annotations

from pathlib import Path

from lib.eligibility_existing import _load_existing_rows

ROOT = Path(__file__).resolve().parents[1]


def test_current_repo_regression_detects_grok_ozempic_42_duplicate():
    rows = _load_existing_rows(ROOT)
    matches = [
        row
        for row in rows
        if row["repo"] == "rmems/grok-ozempic" and row["pr_number"] == 42
    ]
    assert len(matches) == 2
    assert len({row["canonical_sha256"] for row in matches}) == 1
