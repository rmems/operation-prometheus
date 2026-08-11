"""Filesystem layout helpers for collectors (sibling data root support)."""

from __future__ import annotations

import os
from pathlib import Path

from .github_client import repo_slug

# Env var for large raw/full outputs (issue #14). Prefer sibling of the git repo.
DATA_ROOT_ENV = "PROMETHEUS_DATA_ROOT"


def repo_root() -> Path:
    """operation-prometheus repository root (parent of scripts/)."""
    return Path(__file__).resolve().parent.parent.parent


def data_root_from_env() -> Path | None:
    """Return PROMETHEUS_DATA_ROOT if set and non-empty, else None."""
    raw = (os.environ.get(DATA_ROOT_ENV) or "").strip()
    if not raw:
        return None
    return Path(raw).expanduser().resolve()


def resolve_raw_out_dir(repo: str, out_dir: Path | None = None) -> Path:
    """Resolve directory for pr-N.json raw records.

    Priority:
    1. Explicit ``out_dir`` argument
    2. ``$PROMETHEUS_DATA_ROOT/raw/<owner_repo>`` when env is set
    3. ``<repo>/datasets/raw/<owner_repo>`` (in-tree gitignored default)
    """
    if out_dir is not None:
        return Path(out_dir)
    slug = repo_slug(repo)
    root = data_root_from_env()
    if root is not None:
        return root / "raw" / slug
    return repo_root() / "datasets" / "raw" / slug
