"""Unit tests for PROMETHEUS_DATA_ROOT paths and scale CLI helpers."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from lib.paths import DATA_ROOT_ENV, data_root_from_env, resolve_raw_out_dir  # noqa: E402
from list_merged_prs import list_merged_prs  # noqa: E402
import collect_pr_records as collect_mod  # noqa: E402


def test_resolve_raw_out_dir_explicit(tmp_path: Path):
    out = resolve_raw_out_dir("rmems/corinth-canal", tmp_path / "custom")
    assert out == tmp_path / "custom"


def test_resolve_raw_out_dir_data_root(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    monkeypatch.setenv(DATA_ROOT_ENV, str(tmp_path / "pdata"))
    out = resolve_raw_out_dir("Limen-Neural/neuromod", None)
    assert out == (tmp_path / "pdata").resolve() / "raw" / "Limen-Neural_neuromod"


def test_resolve_raw_out_dir_in_tree_default(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv(DATA_ROOT_ENV, raising=False)
    out = resolve_raw_out_dir("rmems/corinth-canal", None)
    assert out.name == "rmems_corinth-canal"
    assert out.parent.name == "raw"
    assert "operation-prometheus" in str(out)


def test_data_root_from_env_empty(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv(DATA_ROOT_ENV, raising=False)
    assert data_root_from_env() is None
    monkeypatch.setenv(DATA_ROOT_ENV, "  ")
    assert data_root_from_env() is None


def test_collect_skip_existing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """--skip-existing does not call GitHub when pr-N.json already exists."""
    out = tmp_path / "raw"
    out.mkdir()
    (out / "pr-89.json").write_text('{"source":{"pr_number":89}}', encoding="utf-8")

    called: list[int] = []

    def fake_collect_pr(client, repo, pr, **kwargs):  # noqa: ANN001
        called.append(pr)
        return {
            "source": {"pr_number": pr, "repo": repo},
            "diff": {"inline": "", "bytes": 0},
        }

    def fake_write(record, out_dir, **kwargs):  # noqa: ANN001
        path = out_dir / f"pr-{record['source']['pr_number']}.json"
        path.write_text(json.dumps(record), encoding="utf-8")
        return path

    class DummyClient:
        pass

    monkeypatch.setattr(collect_mod, "collect_pr", fake_collect_pr)
    monkeypatch.setattr(collect_mod, "write_raw_record", fake_write)
    monkeypatch.setattr(
        collect_mod.GitHubClient,
        "from_env",
        classmethod(lambda cls, env_name="GITHUB_TOKEN": DummyClient()),
    )

    rc = collect_mod.main(
        [
            "--repo",
            "rmems/corinth-canal",
            "--pr",
            "89,91",
            "--out-dir",
            str(out),
            "--skip-existing",
        ]
    )
    assert rc == 0
    assert called == [91]
    assert (out / "pr-91.json").exists()


def test_list_merged_prs_filters_unmerged():
    class FakeClient:
        def paginate(self, path: str, *, per_page: int = 100):
            yield [
                {
                    "number": 1,
                    "title": "closed no merge",
                    "merged_at": None,
                    "user": {"login": "a"},
                    "html_url": "https://example/1",
                },
                {
                    "number": 2,
                    "title": "merged",
                    "merged_at": "2026-01-01T00:00:00Z",
                    "user": {"login": "b"},
                    "html_url": "https://example/2",
                    "additions": 1,
                    "deletions": 0,
                    "changed_files": 1,
                },
            ]

    items = list_merged_prs(FakeClient(), "rmems/corinth-canal", limit=10)
    assert len(items) == 1
    assert items[0]["number"] == 2


def test_github_client_falls_back_to_gh_token(monkeypatch: pytest.MonkeyPatch):
    from lib.github_client import GitHubClient

    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    monkeypatch.setenv("GH_TOKEN", "gh-fallback-token")
    client = GitHubClient.from_env("GITHUB_TOKEN")
    assert client.token == "gh-fallback-token"
