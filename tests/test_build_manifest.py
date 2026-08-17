"""Manifest generation from curated JSONL (GH #39)."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MANIFESTS = ROOT / "datasets" / "manifests"
JSONL = ROOT / "datasets" / "jsonl"
CARDS = ROOT / "datasets" / "cards"


def test_record_row_shape_and_unique_signals():
    from build_manifest import record_row

    rec = {
        "id": "rmems-widget-7",
        "pr_number": 7,
        "training_use": "repair",
        "task_type": "bugfix",
        "domain": "tools",
        "language": "Rust",
        "quality_score": 0.9,
        "outcome": "merged",
        "issue_context": "Issue #1: broken",
        "review_signals": [
            {"author": "a", "comment": "same"},
            {"author": "b", "comment": "same"},
            {"author": "c", "comment": "different"},
        ],
        "patch": "diff",
        "validation": [{"type": "ci", "result": "pass", "detail": "x"}],
        "source_urls": ["u1", "u2"],
    }
    row = record_row(rec)
    assert row["review_signal_count"] == 3
    assert row["unique_review_signal_count"] == 2
    assert row["has_issue_context"] is True
    assert row["patch_chars"] == 4
    assert row["validation_count"] == 1
    assert row["source_url_count"] == 2


def test_manifest_sha_and_bytes_come_from_the_jsonl():
    from build_manifest import build_manifest

    jsonl = JSONL / "myelin-accelerator-v0.jsonl"
    card = json.loads((CARDS / "myelin-accelerator-v0.json").read_text())
    m = build_manifest(
        jsonl, card, created_at="2026-01-01", created_by="test", name="myelin-accelerator-v0"
    )
    data = jsonl.read_bytes()
    assert m["sha256"] == hashlib.sha256(data).hexdigest()
    assert m["bytes"] == len(data)
    assert m["record_count"] == 5
    assert m["source_repo"] == "rmems/myelin-accelerator"


def test_every_committed_manifest_is_generator_fresh():
    """Each committed manifest must be exactly what build_manifest.py produces
    from the committed JSONL — hand-drift like the stale limen sha256 found in
    GH #39 must never come back."""
    from build_manifest import build_manifest, render

    manifest_paths = sorted(MANIFESTS.glob("*.manifest.json"))
    assert manifest_paths, "no manifests found"
    for path in manifest_paths:
        committed = json.loads(path.read_text(encoding="utf-8"))
        name = path.name.removesuffix(".manifest.json")
        card = json.loads((CARDS / f"{name}.json").read_text(encoding="utf-8"))
        generated = build_manifest(
            JSONL / f"{name}.jsonl",
            card,
            created_at=committed["created_at"],
            created_by=committed["created_by"],
            name=name,
        )
        assert render(generated) == path.read_text(encoding="utf-8"), (
            f"{path.name} is stale — run: python scripts/build_manifest.py "
            f"--jsonl datasets/jsonl/{name}.jsonl"
        )
