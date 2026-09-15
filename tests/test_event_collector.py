"""Inventory-driven collector, CAS snapshots, resume, and v1 emit."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import jsonschema
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from lib.cas import ArtifactSpec, ContentAddressedStore, sha256_bytes  # noqa: E402
from lib.collect_events import detect_revert_state  # noqa: E402
from lib.github_client import GitHubError  # noqa: E402
from lib.inventory_targets import load_inventory_targets  # noqa: E402
from lib.normalize_v1 import V1NormalizeOptions, normalize_record_v1  # noqa: E402
from lib.raw_record import CollectOptions, collect_pr, write_raw_record  # noqa: E402
from lib.resume_state import ResumeState  # noqa: E402
from lib.snapshots import GitFetch, SnapshotScope, collect_snapshots  # noqa: E402
import collect_pr_records as collect_mod  # noqa: E402
import build_trajectory_jsonl as build_mod  # noqa: E402

from test_collect_and_normalize import FakeClient, CARD, SCHEMA  # noqa: E402

V1_SCHEMA = ROOT / "schemas" / "trajectory_v1.schema.json"


def _ledger_row(repo: str, number: int, *, owner_state: str = "quarantined") -> dict[str, Any]:
    owner = repo.split("/", 1)[0]
    return {
        "schema_version": "eligibility_ledger_v1",
        "candidate_id": f"github:repository:{owner}:pull:{number}",
        "repository_name_with_owner": repo,
        "pull_request_number": number,
        "state": owner_state,
        "base_oid": "abc",
        "head_oid": "def",
        "source_hash": "a" * 64,
    }


def test_cas_verifies_content_hash_not_filename(tmp_path: Path):
    store = ContentAddressedStore(tmp_path)
    spec = ArtifactSpec(media_type="text/plain", kind="blob")
    meta = store.put_text("hello-cas", spec)
    digest = meta["sha256"]
    assert store.get_text(digest) == "hello-cas"
    obj = tmp_path / "objects" / digest[:2] / digest
    obj.write_bytes(b"tampered")
    with pytest.raises(ValueError, match="content-hash"):
        store.get_bytes(digest)
    store.put_text("hello-cas", spec)
    assert store.get_text(digest) == "hello-cas"


def test_cas_put_is_idempotent(tmp_path: Path):
    store = ContentAddressedStore(tmp_path)
    spec = ArtifactSpec(media_type="text/plain", kind="blob")
    a = store.put_text("same", spec)
    b = store.put_text("same", spec)
    assert a["sha256"] == b["sha256"]
    files = [p for p in (tmp_path / "objects").rglob("*") if p.is_file() and not p.name.endswith(".tmp")]
    assert len(files) == 1


def test_inventory_targets_both_owners_and_stable_order(tmp_path: Path):
    path = tmp_path / "candidates.jsonl"
    rows = [
        _ledger_row("Limen-Neural/neuromod", 5, owner_state="included_positive"),
        _ledger_row("rmems/corinth-canal", 89, owner_state="quarantined"),
        _ledger_row("rmems/corinth-canal", 89, owner_state="quarantined"),
        {"repo": "rmems/corinth-canal", "pr": 1, "state": "excluded"},
    ]
    path.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
    items, digest = load_inventory_targets(path)
    assert digest == sha256_bytes(path.read_bytes())
    repos = [(i["repo"], i["pr_number"]) for i in items]
    assert repos == [("Limen-Neural/neuromod", 5), ("rmems/corinth-canal", 89)]
    again, _ = load_inventory_targets(path)
    assert [i["item_id"] for i in again] == [i["item_id"] for i in items]


def test_inventory_owner_filter(tmp_path: Path):
    path = tmp_path / "candidates.jsonl"
    path.write_text(
        json.dumps(_ledger_row("rmems/corinth-canal", 89))
        + "\n"
        + json.dumps(_ledger_row("Limen-Neural/neuromod", 5, owner_state="included_positive"))
        + "\n",
        encoding="utf-8",
    )
    items, _ = load_inventory_targets(path, owners=("Limen-Neural",))
    assert [i["repo"] for i in items] == ["Limen-Neural/neuromod"]


def test_resume_retries_in_progress_without_duplicate(tmp_path: Path):
    state = ResumeState(tmp_path / "state.json", inventory_sha256="abc")
    state.mark("item-1", "in_progress", extra={"repo": "rmems/corinth-canal", "pr_number": 89})
    reloaded = ResumeState(tmp_path / "state.json")
    assert reloaded.status("item-1") == "in_progress"
    assert not reloaded.is_complete("item-1")
    state.mark("item-1", "complete", extra={"record_sha256": "d" * 64})
    assert ResumeState(tmp_path / "state.json").is_complete("item-1", record_sha256="d" * 64)
    assert not ResumeState(tmp_path / "state.json").is_complete("item-1", record_sha256="e" * 64)


def test_collect_pr_preserves_review_thread_and_timeline():
    record = collect_pr(FakeClient(), "rmems/corinth-canal", 89)
    comments = record["review_comments"]
    human = next(c for c in comments if c["user_login"] == "reviewer-x")
    assert "path" in human
    assert "diff_hunk" in human
    assert "in_reply_to_id" in human
    assert record["timeline"]
    assert record["timeline"][0]["event"] == "merged"
    assert record["merge_state"]["merged"] is True
    assert record["checks"]["check_suites"]
    assert "evidence_complete" in record["collection_meta"]


def test_collect_pr_repo_pr_cli_dry_run_compatible():
    rc = collect_mod.main(["--repo", "rmems/corinth-canal", "--pr", "89", "--dry-run"])
    assert rc == 0


def test_snapshots_quarantine_missing_commit(tmp_path: Path):
    class MissingCommitClient(FakeClient):
        def get_json(self, path_or_url: str) -> Any:
            if "/git/commits/" in path_or_url:
                raise GitHubError("commit gone", status=404)
            return super().get_json(path_or_url)

    store = ContentAddressedStore(tmp_path / "cas")
    pack = collect_snapshots(
        GitFetch(MissingCommitClient(), store, "rmems/corinth-canal"),
        SnapshotScope(
            pull={"base_sha": "abc", "head_sha": "def", "merge_commit_sha": "ghi"},
            commits=[{"sha": "c1"}],
            files=[],
        ),
    )
    assert pack["complete"] is False
    assert pack["quarantine"]
    assert pack["missing_oids"]
    assert all(o["availability"] == "missing" for o in pack["objects"] if o["kind"] == "commit")


def test_snapshots_store_reproducible_blobs(tmp_path: Path):
    store = ContentAddressedStore(tmp_path / "cas")
    files = [{"filename": "src/ok.rs", "status": "modified", "sha": "cafebabe"}]
    pack = collect_snapshots(
        GitFetch(FakeClient(), store, "rmems/corinth-canal"),
        SnapshotScope(
            pull={"base_sha": "abc", "head_sha": "def"},
            commits=[{"sha": "c1"}],
            files=files,
            review_comments=[{"commit_id": "def", "original_commit_id": "abc"}],
        ),
    )
    present = [o for o in pack["objects"] if o["availability"] == "present"]
    assert present
    for obj in present:
        if obj.get("sha256"):
            assert store.get_bytes(obj["sha256"])


def test_collect_with_snapshots_writes_pack(tmp_path: Path):
    store = ContentAddressedStore(tmp_path / "cas")
    record = collect_pr(
        FakeClient(),
        "rmems/corinth-canal",
        89,
        CollectOptions(include_snapshots=True, artifact_store=store),
    )
    path = write_raw_record(record, tmp_path / "raw", artifact_store=store)
    assert path.exists()
    assert (tmp_path / "raw" / "pr-89.pack.json").exists()
    written = json.loads(path.read_text())
    assert written["snapshots"]["pack_path"] == "pr-89.pack.json"
    assert written["diff"]["artifact"]["sha256"]


def test_normalize_v1_from_fixture_validates():
    raw = collect_pr(FakeClient(), "rmems/corinth-canal", 89)
    card = json.loads(CARD.read_text()) if CARD.exists() else {}
    traj = normalize_record_v1(raw, card, V1NormalizeOptions(source_license="Apache-2.0"))
    schema = json.loads(V1_SCHEMA.read_text())
    jsonschema.Draft7Validator(schema).validate(traj)
    assert traj["schema_version"] == "1.0"
    assert traj["trajectory_type"] == "software"
    assert traj["software_payload"]["issue_statement"]
    review_events = [e for e in traj["events"] if e["event_type"] == "review_comment"]
    assert review_events
    assert review_events[0]["code_state"]["head_oid"]
    check_events = [e for e in traj["events"] if e["event_type"] in {"check_run", "check_suite"}]
    assert check_events
    timestamps = [e["timestamp"] for e in traj["events"]]
    assert timestamps == sorted(timestamps)
    from lib.normalize import normalize_record

    v0 = normalize_record(raw, card)
    jsonschema.Draft7Validator(json.loads(SCHEMA.read_text())).validate(v0)


def test_v1_emit_is_deterministic():
    from lib.source_inventory_common import sha256_json

    raw = collect_pr(FakeClient(), "rmems/corinth-canal", 89)
    a = normalize_record_v1(raw, {}, V1NormalizeOptions(source_license="MIT"))
    b = normalize_record_v1(raw, {}, V1NormalizeOptions(source_license="MIT"))
    assert sha256_json(a) == sha256_json(b)


def test_build_trajectory_jsonl_v0_and_v1(tmp_path: Path):
    raw = collect_pr(FakeClient(), "rmems/corinth-canal", 89)
    raw_dir = tmp_path / "raw"
    write_raw_record(raw, raw_dir)
    out_v0 = tmp_path / "v0.jsonl"
    rc0 = build_mod.main(
        [
            "--raw-dir", str(raw_dir), "--card", str(CARD),
            "--out", str(out_v0), "--schema-version", "v0", "--strict",
        ]
    )
    assert rc0 == 0
    out_v1 = tmp_path / "v1.jsonl"
    rc1 = build_mod.main(
        [
            "--raw-dir", str(raw_dir), "--card", str(CARD),
            "--out", str(out_v1), "--schema-version", "v1", "--strict",
        ]
    )
    assert rc1 == 0
    v1 = json.loads(out_v1.read_text().splitlines()[0])
    assert v1["schema_version"] == "1.0"
    v0 = json.loads(out_v0.read_text().splitlines()[0])
    assert "id" in v0


def test_inventory_cli_dry_run_and_resume(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    inv = tmp_path / "candidates.jsonl"
    inv.write_text(
        json.dumps({"repo": "rmems/corinth-canal", "pr": 89, "state": "quarantined"})
        + "\n"
        + json.dumps({"repo": "Limen-Neural/neuromod", "pr": 5, "state": "included_positive"})
        + "\n",
        encoding="utf-8",
    )
    rc = collect_mod.main(["--inventory", str(inv), "--dry-run"])
    assert rc == 0

    collected: list[tuple[str, int]] = []

    def fake_collect_pr(client, repo, pr, **kwargs):  # noqa: ANN001
        collected.append((repo, pr))
        return {
            "source": {"pr_number": pr, "repo": repo},
            "diff": {"inline": "", "bytes": 0},
            "snapshots": {"complete": True, "quarantine": [], "pack_sha256": "a" * 64},
            "collection_meta": {"evidence_complete": True, "warnings": []},
        }

    def fake_write(record, out_dir, **kwargs):  # noqa: ANN001
        out_dir.mkdir(parents=True, exist_ok=True)
        path = out_dir / f"pr-{record['source']['pr_number']}.json"
        path.write_text(json.dumps(record), encoding="utf-8")
        return path

    monkeypatch.setattr(collect_mod, "collect_pr", fake_collect_pr)
    monkeypatch.setattr(collect_mod, "write_raw_record", fake_write)
    monkeypatch.setattr(
        collect_mod.GitHubClient,
        "from_env",
        classmethod(lambda cls, env_name="GITHUB_TOKEN": object()),
    )
    args = [
        "--inventory", str(inv),
        "--out-dir", str(tmp_path / "raw"),
        "--resume-state", str(tmp_path / "state.json"),
        "--artifact-store", str(tmp_path / "cas"),
        "--no-snapshots",
        "--continue-on-error",
    ]
    assert collect_mod.main(args) == 0
    assert ("rmems/corinth-canal", 89) in collected
    assert ("Limen-Neural/neuromod", 5) in collected
    first_count = len(collected)
    assert collect_mod.main(args) == 0
    assert len(collected) == first_count


def test_inventory_missing_commit_marks_quarantined(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    inv = tmp_path / "candidates.jsonl"
    inv.write_text(
        json.dumps({"repo": "rmems/corinth-canal", "pr": 89, "state": "quarantined"}) + "\n",
        encoding="utf-8",
    )

    def fake_collect_pr(client, repo, pr, **kwargs):  # noqa: ANN001
        return {
            "source": {"pr_number": pr, "repo": repo},
            "diff": {"inline": "", "bytes": 0},
            "snapshots": {
                "complete": False,
                "quarantine": [{"reason": "git_commit_inaccessible", "git_oid": "abc"}],
                "pack_sha256": "b" * 64,
            },
            "collection_meta": {"evidence_complete": False, "warnings": ["snapshots_quarantined"]},
        }

    def fake_write(record, out_dir, **kwargs):  # noqa: ANN001
        out_dir.mkdir(parents=True, exist_ok=True)
        path = out_dir / f"pr-{record['source']['pr_number']}.json"
        path.write_text(json.dumps(record), encoding="utf-8")
        return path

    monkeypatch.setattr(collect_mod, "collect_pr", fake_collect_pr)
    monkeypatch.setattr(collect_mod, "write_raw_record", fake_write)
    monkeypatch.setattr(
        collect_mod.GitHubClient,
        "from_env",
        classmethod(lambda cls, env_name="GITHUB_TOKEN": object()),
    )
    state = tmp_path / "state.json"
    rc = collect_mod.main(
        [
            "--inventory", str(inv),
            "--out-dir", str(tmp_path / "raw"),
            "--resume-state", str(state),
            "--artifact-store", str(tmp_path / "cas"),
            "--continue-on-error",
        ]
    )
    assert rc == 0
    saved = json.loads(state.read_text())
    statuses = {item["status"] for item in saved["items"].values()}
    assert statuses == {"quarantined"}


def test_v1_missing_snapshot_not_silently_complete():
    raw = {
        "source": {
            "repo": "rmems/corinth-canal",
            "pr_number": 89,
            "html_url": "https://github.com/rmems/corinth-canal/pull/89",
        },
        "pull": {
            "title": "feat: x",
            "body": "hello",
            "merged": True,
            "merged_at": "2026-05-27T06:13:36Z",
            "created_at": "2026-05-27T00:00:00Z",
            "user_login": "rmems",
            "user_type": "User",
            "base_sha": "abc",
            "head_sha": "def",
        },
        "commits": [
            {"sha": "def", "message": "feat", "date": "2026-05-27T01:00:00Z", "author_login": "rmems"}
        ],
        "files": [],
        "diff": {"inline": "@@\n-a\n+b\n"},
        "checks": {},
        "snapshots": {
            "complete": False,
            "quarantine": [{"reason": "git_commit_inaccessible"}],
            "objects": [],
        },
        "collection_meta": {"warnings": ["snapshots_quarantined"], "evidence_complete": False},
    }
    traj = normalize_record_v1(raw, {}, V1NormalizeOptions(source_license="MIT"))
    assert traj["evidence_quality"]["completeness"] < 1.0
    assert traj["terminal_disposition"] == "successful"
    jsonschema.Draft7Validator(json.loads(V1_SCHEMA.read_text())).validate(traj)


def test_snapshots_do_not_fetch_tree_oids_as_commits(tmp_path: Path):
    tree_oid = "aa" * 20
    commit_sha = "bb" * 20

    class TreeIsNotACommit(FakeClient):
        def get_json(self, path_or_url: str) -> Any:
            if f"/git/commits/{tree_oid}" in path_or_url:
                raise GitHubError("not a commit", status=422)
            return super().get_json(path_or_url)

    store = ContentAddressedStore(tmp_path / "cas")
    pack = collect_snapshots(
        GitFetch(TreeIsNotACommit(), store, "rmems/corinth-canal"),
        SnapshotScope(
            pull={"base_sha": "abc", "head_sha": "def"},
            commits=[
                {
                    "sha": commit_sha,
                    "tree_oid": tree_oid,
                    "commit": {"tree": {"sha": tree_oid}},
                }
            ],
            files=[],
        ),
    )
    assert tree_oid not in pack["required_oids"]
    assert pack["complete"] is True
    assert not pack["quarantine"]
    assert not any(o.get("git_oid") == tree_oid for o in pack["objects"])


def test_v1_attaches_object_pack_using_store_digest(tmp_path: Path):
    store = ContentAddressedStore(tmp_path / "cas")
    record = collect_pr(
        FakeClient(),
        "rmems/corinth-canal",
        89,
        CollectOptions(include_snapshots=True, artifact_store=store),
    )
    path = write_raw_record(record, tmp_path / "raw", artifact_store=store)
    written = json.loads(path.read_text())
    pack = written["snapshots"]
    assert pack["store_sha256"]
    assert store.exists(pack["store_sha256"])
    traj = normalize_record_v1(
        written, {}, V1NormalizeOptions(artifact_store=store, source_license="MIT")
    )
    pack_arts = [a for a in traj["artifacts"] if a.get("id") == "object-pack"]
    assert len(pack_arts) == 1
    assert pack_arts[0]["sha256"] == pack["store_sha256"]
    assert store.exists(pack_arts[0]["sha256"])


def test_v1_emit_reads_sidecar_diff(tmp_path: Path):
    raw = collect_pr(FakeClient(), "rmems/corinth-canal", 89)
    sidecar_text = "diff --git a/x b/x\n--- a/x\n+++ b/x\n@@ -1 +1 @@\n-old\n+new\n"
    raw["diff"] = {
        "inline": sidecar_text * 2000,
        "sidecar_path": None,
        "bytes": 0,
        "truncated": False,
    }
    path = write_raw_record(raw, tmp_path / "raw", max_inline_diff_bytes=64)
    written = json.loads(path.read_text())
    assert written["diff"]["inline"] is None
    assert written["diff"]["sidecar_path"] == "pr-89.diff"
    traj = normalize_record_v1(
        written,
        {},
        V1NormalizeOptions(source_license="MIT", raw_path=path, max_patch_bytes=10_000_000),
    )
    patch = traj["software_payload"]["implementation_patch"]
    assert patch != "patch not collected"
    assert "+new" in patch
    inline_arts = [a for a in traj["artifacts"] if a.get("id") == "inline-patch"]
    assert inline_arts


def test_merged_revert_pr_is_not_self_reverted():
    source_id = "https://github.com/rmems/corinth-canal/pull/90"
    merge = detect_revert_state(
        {
            "title": 'Revert "feat: foo"',
            "merged": True,
            "merged_at": "2026-05-27T06:13:36Z",
            "state": "closed",
        },
        [{"sha": "def", "message": 'Revert "feat: foo"'}],
        [{"id": 2, "event": "committed", "body": 'Revert "feat: foo"'}],
    )
    assert merge["reverted"] is False
    assert merge["revert_evidence"]
    raw = {
        "source": {
            "repo": "rmems/corinth-canal",
            "pr_number": 90,
            "html_url": source_id,
        },
        "pull": {
            "title": 'Revert "feat: foo"',
            "body": "Reverts rmems/corinth-canal#89",
            "merged": True,
            "merged_at": "2026-05-27T06:13:36Z",
            "created_at": "2026-05-27T00:00:00Z",
            "user_login": "rmems",
            "user_type": "User",
            "base_sha": "abc",
            "head_sha": "def",
        },
        "commits": [
            {
                "sha": "def",
                "message": 'Revert "feat: foo"',
                "date": "2026-05-27T01:00:00Z",
                "author_login": "rmems",
            }
        ],
        "files": [],
        "diff": {"inline": "@@\n-a\n+b\n"},
        "checks": {},
        "merge_state": merge,
        "collection_meta": {"warnings": [], "evidence_complete": True},
    }
    traj = normalize_record_v1(raw, {}, V1NormalizeOptions(source_license="MIT"))
    assert traj["terminal_disposition"] == "successful"
    assert traj["lineage"]["reverts"] == []
    jsonschema.Draft7Validator(json.loads(V1_SCHEMA.read_text())).validate(traj)
