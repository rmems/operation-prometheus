"""STATUS.md generation from datasets/manifests/ (GH #37)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def _manifest(name: str, created: str, records: list[dict]) -> dict:
    return {
        "name": name,
        "schema_version": "pr_trajectory_v0",
        "created_at": created,
        "source_repo": f"rmems/{name.removesuffix('-v0')}",
        "record_count": len(records),
        "records": records,
    }


def _record(pr: int, **over) -> dict:
    base = {
        "id": f"rmems-widget-{pr}",
        "pr_number": pr,
        "training_use": "repair",
        "task_type": "bugfix",
        "domain": "tools",
        "language": "Rust",
        "quality_score": 0.9,
        "outcome": "merged",
        "review_signal_count": 8,
        "unique_review_signal_count": 8,
        "validation_count": 3,
    }
    base.update(over)
    return base


def test_render_block_covers_every_extract():
    """The old hand-written table showed only the newest extract and overwrote the rest."""
    from build_status import render_block

    block = render_block(
        [
            _manifest("alpha-v0", "2026-01-01", [_record(1)]),
            _manifest("beta-v0", "2026-02-01", [_record(2), _record(3)]),
        ]
    )
    assert "### alpha-v0" in block
    assert "### beta-v0" in block
    assert "**Extracts:** 2" in block
    assert "**Trajectories:** 3" in block
    # Newest extract date wins for "Last updated".
    assert "**Last updated:** 2026-02-01" in block


def test_render_block_orders_oldest_first_and_prs_descending():
    from build_status import render_block

    block = render_block(
        [_manifest("alpha-v0", "2026-01-01", [_record(5), _record(42), _record(7)])]
    )
    rows = [ln for ln in block.splitlines() if ln.startswith("| #")]
    assert [r.split()[1] for r in rows] == ["#42", "#7", "#5"]


def test_signals_column_shows_dedupe_when_counts_differ():
    from build_status import render_block

    block = render_block(
        [
            _manifest(
                "alpha-v0",
                "2026-01-01",
                [_record(1, review_signal_count=8, unique_review_signal_count=1)],
            )
        ]
    )
    assert "| 1 of 8 |" in block


def test_splice_replaces_only_the_marked_region():
    from build_status import BEGIN_MARKER, END_MARKER, splice

    doc = f"# Title\n\nkeep me\n\n{BEGIN_MARKER}\nstale\n{END_MARKER}\n\nkeep me too\n"
    out = splice(doc, f"{BEGIN_MARKER}\nfresh\n{END_MARKER}")
    assert "keep me" in out and "keep me too" in out
    assert "stale" not in out and "fresh" in out


def test_splice_without_markers_is_an_error():
    from build_status import splice

    with pytest.raises(SystemExit, match="missing the generated-block markers"):
        splice("# Title\n\nno markers here\n", "block")


def test_status_regenerates_without_committed_rewrite():
    """Data extracts must not commit STATUS.md (shared-files-guard).

    Adding a manifest is enough: the generator splices a complete block into
    the existing marked region. Requiring the committed file to already match
    would make every data-labeled extract fail CI.
    """
    from build_status import BEGIN_MARKER, END_MARKER, load_manifests, render_block, splice

    status = (ROOT / "STATUS.md").read_text(encoding="utf-8")
    manifests = load_manifests(ROOT / "datasets" / "manifests")
    assert manifests, "no manifests found"
    updated = splice(status, render_block(manifests))
    assert BEGIN_MARKER in updated and END_MARKER in updated
    for manifest in manifests:
        assert f"### {manifest['name']}" in updated


def test_new_manifest_is_allowed_to_leave_committed_status_stale(tmp_path):
    """An extract PR adds a manifest and leaves STATUS.md untouched."""
    from build_status import load_manifests, render_block, splice

    status = (ROOT / "STATUS.md").read_text(encoding="utf-8")
    dest = tmp_path / "manifests"
    dest.mkdir()
    for path in (ROOT / "datasets" / "manifests").glob("*.manifest.json"):
        (dest / path.name).write_text(path.read_text(encoding="utf-8"), encoding="utf-8")
    extra = _manifest("new-extract-v0", "2099-01-01", [_record(99)])
    (dest / "new-extract-v0.manifest.json").write_text(
        json.dumps(extra), encoding="utf-8"
    )

    updated = splice(status, render_block(load_manifests(dest)))
    assert "### new-extract-v0" in updated
    assert updated != status


def test_generated_totals_match_the_jsonl_on_disk():
    """The generated record counts must reflect real data, not just the manifests."""
    from build_status import load_manifests

    for manifest in load_manifests(ROOT / "datasets" / "manifests"):
        jsonl = ROOT / str(manifest["jsonl_path"])
        actual = sum(1 for line in jsonl.read_text(encoding="utf-8").splitlines() if line.strip())
        assert actual == manifest["record_count"], f"{manifest['name']}: manifest count drift"
        ids = {json.loads(line)["id"] for line in jsonl.read_text().splitlines() if line.strip()}
        assert ids == {r["id"] for r in manifest["records"]}, f"{manifest['name']}: id drift"
