"""Deterministic global merge of corpus shards (Linear RM-1345)."""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

import pytest

from corpus_shard_fixtures import (
    REPOSITORY_IDS,
    build_valid_tree,
    valid_records,
    write_shard,
)
from lib.corpus_shards import (
    ASSIGNMENT_RULE,
    RECORD_SCHEMA_VERSION,
    assign_shard,
    merge_corpus_shards,
)
from merge_corpus_shards import main, validate_merge_artifacts


def _inventory_revision(inventory_dir: Path) -> str:
    return json.loads((inventory_dir / "manifest.json").read_text())["snapshot_sha256"]


def _rewrite_shard(root: Path, case: dict[str, Any]) -> tuple[Path, Path]:
    inventory_dir, shards_dir = build_valid_tree(root)
    number = int(case["number"])
    spec = {
        "number": number,
        "inventory_revision": _inventory_revision(inventory_dir),
        "records": valid_records()[number],
        **case.get("spec", {}),
    }
    write_shard(shards_dir / f"shard-{number}", spec)
    return inventory_dir, shards_dir


def _assert_rejected(root: Path, case: dict[str, Any]) -> None:
    inventory_dir, shards_dir = _rewrite_shard(root, case)
    with pytest.raises(ValueError, match=case["match"]):
        merge_corpus_shards(inventory_dir, shards_dir)


def test_assignment_rule_maps_fixture_repositories():
    for number, repository_id in REPOSITORY_IDS.items():
        assert assign_shard(repository_id) == number
    assert ASSIGNMENT_RULE == "int(sha256(github_repository_node_id)[0:8], 16) % 3"


def test_valid_three_shard_fixture_merges_deterministically(tmp_path):
    inventory_dir, shards_dir = build_valid_tree(tmp_path / "valid")
    manifest, rendered = merge_corpus_shards(inventory_dir, shards_dir)
    validate_merge_artifacts(shards_dir, manifest, rendered)

    assert manifest["counts"]["record_count"] == 5
    assert manifest["counts"]["repository_count"] == 3
    assert manifest["exclusion_total"] == 1
    assert manifest["quarantine_total"] == 1
    assert manifest["counts"]["included_positive"] == 1
    assert manifest["counts"]["included_negative"] == 1
    assert manifest["counts"]["watchlist_open"] == 1
    assert [row["shard_number"] for row in manifest["shards"]] == [0, 1, 2]

    lines = [
        line for line in rendered["records.jsonl"].decode("utf-8").splitlines() if line
    ]
    candidate_ids = [json.loads(line)["candidate_id"] for line in lines]
    assert candidate_ids == sorted(candidate_ids)
    assert candidate_ids[0].startswith("github:repository:R_test_0:")

    second_manifest, second_rendered = merge_corpus_shards(inventory_dir, shards_dir)
    assert second_rendered == rendered
    assert second_manifest == manifest


def test_preserves_shard_owned_record_bytes(tmp_path):
    inventory_dir, shards_dir = build_valid_tree(tmp_path / "bytes")
    _manifest, rendered = merge_corpus_shards(inventory_dir, shards_dir)
    original = valid_records()[0][0]
    assert original in rendered["records.jsonl"].split(b"\n")
    assert b'"state": "included_positive"' in original
    assert original != json.dumps(
        json.loads(original.decode("utf-8")),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def test_cli_check_determinism_and_check_round_trip(tmp_path):
    inventory_dir, shards_dir = build_valid_tree(tmp_path / "cli")
    out_dir = tmp_path / "out"
    assert (
        main(
            [
                "--inventory-dir",
                str(inventory_dir),
                "--shards-dir",
                str(shards_dir),
                "--out-dir",
                str(out_dir),
                "--check-determinism",
            ]
        )
        == 0
    )
    assert (out_dir / "manifest.json").is_file()
    assert (
        main(
            [
                "--inventory-dir",
                str(inventory_dir),
                "--shards-dir",
                str(shards_dir),
                "--out-dir",
                str(out_dir),
                "--check",
            ]
        )
        == 0
    )


def test_missing_shard_is_rejected(tmp_path):
    inventory_dir, shards_dir = build_valid_tree(tmp_path / "missing")
    shutil.rmtree(shards_dir / "shard-2")
    with pytest.raises(ValueError, match="Missing corpus shard 2"):
        merge_corpus_shards(inventory_dir, shards_dir)


def test_duplicate_repository_is_rejected(tmp_path):
    _assert_rejected(
        tmp_path / "dup-repo",
        {
            "match": "Duplicate repository",
            "number": 1,
            "spec": {"repositories": sorted([REPOSITORY_IDS[1], REPOSITORY_IDS[0]])},
        },
    )


def test_wrong_modulus_foreign_shard_member_is_rejected(tmp_path):
    foreign = json.dumps(
        {
            "schema_version": RECORD_SCHEMA_VERSION,
            "candidate_id": "github:repository:R_test_4:pull:PR_foreign",
            "repository_id": REPOSITORY_IDS[0],
            "state": "excluded",
            "reason_codes": ["foreign"],
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    _assert_rejected(
        tmp_path / "modulus",
        {
            "match": "wrong modulus",
            "number": 1,
            "spec": {
                "records": [*valid_records()[1], foreign],
                "repositories": [REPOSITORY_IDS[1]],
            },
        },
    )


def test_digest_mismatch_is_rejected(tmp_path):
    inventory_dir, shards_dir = build_valid_tree(tmp_path / "digest")
    manifest_path = shards_dir / "shard-0" / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["manifest_sha256"] = "0" * 64
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    with pytest.raises(ValueError, match="manifest digest mismatch"):
        merge_corpus_shards(inventory_dir, shards_dir)


def test_schema_mismatch_is_rejected(tmp_path):
    _assert_rejected(
        tmp_path / "schema",
        {
            "match": "schema mismatch",
            "number": 0,
            "spec": {"schema_version": "corpus_shard_manifest_v0"},
        },
    )


def test_inventory_revision_mismatch_is_rejected(tmp_path):
    _assert_rejected(
        tmp_path / "revision",
        {
            "match": "inventory revision mismatch",
            "number": 0,
            "spec": {"inventory_revision": "ab" * 32},
        },
    )


def test_uncovered_inventory_row_is_rejected(tmp_path):
    _assert_rejected(
        tmp_path / "uncovered",
        {
            "match": "Unaccounted inventory row",
            "number": 2,
            "spec": {"records": [], "repositories": [REPOSITORY_IDS[2]]},
        },
    )


def test_duplicate_record_is_rejected(tmp_path):
    duplicated = valid_records()[0] + valid_records()[0][:1]
    _assert_rejected(
        tmp_path / "dup-record",
        {
            "match": "Duplicate record",
            "number": 0,
            "spec": {"records": duplicated},
        },
    )


def test_cli_rejects_missing_shard(tmp_path):
    inventory_dir, shards_dir = build_valid_tree(tmp_path / "cli-missing")
    shutil.rmtree(shards_dir / "shard-1")
    assert (
        main(
            [
                "--inventory-dir",
                str(inventory_dir),
                "--shards-dir",
                str(shards_dir),
                "--out-dir",
                str(tmp_path / "out"),
            ]
        )
        == 1
    )
