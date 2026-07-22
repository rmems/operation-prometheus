"""Unit tests for GitHub client helpers (no network)."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from lib.github_client import _parse_next_link, parse_repo, repo_slug  # noqa: E402


def test_parse_repo_and_slug():
    assert parse_repo("rmems/corinth-canal") == ("rmems", "corinth-canal")
    assert parse_repo("https://github.com/rmems/corinth-canal") == ("rmems", "corinth-canal")
    assert repo_slug("rmems/corinth-canal") == "rmems_corinth-canal"


def test_parse_next_link():
    header = (
        '<https://api.github.com/resource?page=2>; rel="next", '
        '<https://api.github.com/resource?page=5>; rel="last"'
    )
    assert _parse_next_link(header) == "https://api.github.com/resource?page=2"
    assert _parse_next_link("") is None
