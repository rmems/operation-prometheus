"""HF export: license injection, determinism, and card completeness."""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_every_record_gets_source_license():
    import export_hf_dataset as ex

    records = ex.load_records()
    assert records, "expected committed jsonl records"
    for rec in records:
        assert rec["source_license"] == ex.REPO_LICENSES[rec["repo"]]


def test_export_is_deterministic():
    import export_hf_dataset as ex

    records = ex.load_records()
    assert ex.records_jsonl(records) == ex.records_jsonl(ex.load_records())
    ids = [r["id"] for r in records]
    assert ids == sorted(ids)


def test_repo_license_map_covers_all_jsonl_repos():
    import export_hf_dataset as ex

    records = ex.load_records()
    assert {r["repo"] for r in records} <= set(ex.REPO_LICENSES)


def test_renamed_repos_are_canonicalized():
    import export_hf_dataset as ex

    records = ex.load_records()
    repos = {r["repo"] for r in records}
    for old, new in ex.REPO_ALIASES.items():
        assert old not in repos
        if new in repos:  # alias only asserted when the repo has records
            assert all(
                f"github.com/{old}/" not in u
                for r in records
                for u in r["source_urls"]
            )


def test_card_lists_every_repo_and_license():
    import export_hf_dataset as ex

    records = ex.load_records()
    manifest = ex.build_manifest(records, ex.records_jsonl(records))
    card = ex.build_card(records, manifest)
    for repo in manifest["repo_counts"]:
        assert repo in card
        assert ex.REPO_LICENSES[repo] in card
    assert "source_license" in card


def test_committed_outputs_fresh():
    """datasets/hf/ must match a regeneration (same as --check)."""
    import export_hf_dataset as ex

    records = ex.load_records()
    blob = ex.records_jsonl(records)
    manifest = ex.build_manifest(records, blob)
    out = ex.OUT_DIR
    assert (out / ex.RECORDS_NAME).read_bytes() == blob
    assert (out / ex.CARD_NAME).read_bytes() == ex.build_card(records, manifest).encode()
    on_disk = json.loads((out / ex.MANIFEST_NAME).read_text(encoding="utf-8"))
    assert on_disk == manifest


def test_duplicate_record_ids_deduped():
    """A re-extracted PR across schema versions must not double-count."""
    import export_hf_dataset as ex

    records = ex.load_records()
    ids = [r["id"] for r in records]
    assert len(ids) == len(set(ids))


def test_manifest_license_table_scoped_to_records():
    import export_hf_dataset as ex

    records = ex.load_records()
    manifest = ex.build_manifest(records, ex.records_jsonl(records))
    assert set(manifest["repo_licenses"]) == set(manifest["repo_counts"])
